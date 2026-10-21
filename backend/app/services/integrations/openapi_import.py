"""Analyse d'une spécification OpenAPI fournie par fichier (Studio d'intégration API, Phase 4).

Le fichier est une donnée non fiable :
- aucun accès réseau : une référence ``$ref`` non locale n'est jamais chargée, les URL (``servers``,
  flux OAuth, ``openIdConnectUrl``) restent des métadonnées, ``callbacks`` et ``links`` ne sont pas importés ;
- aucun code exécuté : JSON strict ou YAML sans ancres, alias ni étiquettes applicatives ;
- taille, profondeur, nombre de nœuds, d'opérations et expansion des schémas bornés ;
- ce qui ressemble à un secret (JWT, clé privée, en-tête Bearer) bloque l'import ; les exemples de
  champs sensibles (mot de passe, jeton, clé) sont masqués.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

TAILLE_MAX = 2 * 1024 * 1024
PROFONDEUR_MAX = 64
NOEUDS_MAX = 200_000
CHAINE_MAX = 100_000
OPERATIONS_MAX = 2_000
SCHEMA_PROFONDEUR_MAX = 8
SCHEMA_EXPANSION_MAX = 20_000
CHAMPS_MAX = 100
ENUM_MAX = 20
MESSAGES_MAX = 200

VERSION_SUPPORTEE = re.compile(r"^3\.(0|1)\.\d+$")
METHODES = ("get", "put", "post", "delete", "patch", "head", "options", "trace")
EXTENSIONS = {".json": "json", ".yaml": "yaml", ".yml": "yaml"}

# Chemin relatif sûr : pas d'espace, de guillemet, de $, de `, de \ ni de ! (repris tel quel dans les exemples).
CHEMIN_VALIDE = re.compile(r"^/(?:[A-Za-z0-9\-._~%:@,;=+*()/]|\{[A-Za-z0-9_.\-]{1,100}\})*$")
PLACEHOLDER = re.compile(r"\{([^{}/]+)\}")
NOM_ENTETE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,100}$")

SECRET_FORT = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\bbearer\s+[A-Za-z0-9._~+/=-]{20,}",
    re.I,
)
NOM_SENSIBLE = re.compile(
    r"pass(word|wd)?|pwd|mot.?de.?passe|secret|token|jeton|api.?key|apikey|credential|private.?key|authorization",
    re.I,
)
_URL_AVEC_IDENTIFIANTS = re.compile(r"^\s*[A-Za-z][A-Za-z0-9+.-]*://[^/?#\s]*@")
_RESERVE = re.compile(r"^(<[^<>]*>|\{\{?[^{}]*\}?\}|\$\{?[A-Z0-9_]+\}?|x+|\*+|string|\.\.\.|)$", re.I)
MASQUE = "<masqué>"


class AnalyseInterrompue(Exception):
    pass


@dataclass
class Message:
    niveau: str
    code: str
    message: str
    emplacement: str | None = None

    def dict(self) -> dict:
        return {"niveau": self.niveau, "code": self.code, "message": self.message, "emplacement": self.emplacement}


@dataclass
class Analyse:
    nom_fichier: str
    taille: int
    empreinte: str
    format: str | None = None
    openapi_version: str | None = None
    titre: str | None = None
    version_api: str | None = None
    description: str | None = None
    serveurs: list[dict] = field(default_factory=list)
    securite: list[dict] = field(default_factory=list)
    operations: list[dict] = field(default_factory=list)
    erreurs: list[Message] = field(default_factory=list)
    avertissements: list[Message] = field(default_factory=list)
    document: dict | None = None

    @property
    def valide(self) -> bool:
        return not self.erreurs and self.document is not None

    def erreur(self, code: str, message: str, emplacement: str | None = None) -> None:
        if len(self.erreurs) < MESSAGES_MAX:
            self.erreurs.append(Message("erreur", code, message, emplacement))

    def avertir(self, code: str, message: str, emplacement: str | None = None) -> None:
        if len(self.avertissements) < MESSAGES_MAX:
            self.avertissements.append(Message("avertissement", code, message, emplacement))

    def resume(self) -> dict:
        return {
            "serveurs": self.serveurs,
            "securite": self.securite,
            "nb_operations": len(self.operations),
            "description": self.description,
        }


# ------------------------------------------------------------------------------------------- lecture


def nom_fichier_sur(nom: str | None) -> str:
    base = re.split(r"[\\/]", nom or "")[-1]
    propre = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")[:255]
    return propre or "specification"


class _ChargeurYaml(yaml.SafeLoader):
    """YAML de données seulement : ni ancre ni alias (expansion exponentielle), clés uniques."""

    def compose_node(self, parent, index):  # noqa: ANN001
        if self.check_event(yaml.AliasEvent):
            raise AnalyseInterrompue("Alias YAML (*) non autorisés.")
        evenement = self.peek_event()
        if getattr(evenement, "anchor", None):
            raise AnalyseInterrompue("Ancres YAML (&) non autorisées.")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):  # noqa: ANN001
        if isinstance(node, yaml.MappingNode):
            vues = set()
            for cle_noeud, _valeur in node.value:
                if cle_noeud.tag == "tag:yaml.org,2002:merge":
                    raise AnalyseInterrompue("Fusion YAML (<<) non autorisée.")
                cle = cle_noeud.value
                if cle in vues:
                    raise AnalyseInterrompue(f"Clé dupliquée : {str(cle)[:80]}")
                vues.add(cle)
        return super().construct_mapping(node, deep=deep)


def _paires_json(paires: list[tuple[str, Any]]) -> dict:
    resultat: dict = {}
    for cle, valeur in paires:
        if cle in resultat:
            raise AnalyseInterrompue(f"Clé dupliquée : {cle[:80]}")
        resultat[cle] = valeur
    return resultat


def _constante_json(nom: str) -> Any:
    raise AnalyseInterrompue(f"Valeur numérique non finie ({nom}) non autorisée.")


def _normaliser(racine: Any) -> Any:
    """Copie bornée (profondeur, nœuds, chaînes) en types JSON stricts, sans récursion Python."""
    compteur = 0

    def convertir(v: Any) -> tuple[Any, bool]:
        if isinstance(v, bool) or v is None or isinstance(v, int):
            return v, False
        if isinstance(v, float):
            if not math.isfinite(v):
                raise AnalyseInterrompue("Valeur numérique non finie non autorisée.")
            return v, False
        if isinstance(v, str):
            if len(v) > CHAINE_MAX:
                raise AnalyseInterrompue("Chaîne de caractères trop longue.")
            return v, False
        if isinstance(v, (datetime, date)):
            return v.isoformat(), False
        if isinstance(v, (dict, list)):
            return v, True
        raise AnalyseInterrompue(f"Type de valeur non pris en charge ({type(v).__name__}).")

    def cle(k: Any) -> str:
        if isinstance(k, bool) or k is None:
            raise AnalyseInterrompue("Clé non textuelle non autorisée.")
        if isinstance(k, (int, float)):
            return str(k)
        if isinstance(k, (datetime, date)):
            return k.isoformat()
        if not isinstance(k, str):
            raise AnalyseInterrompue("Clé non textuelle non autorisée.")
        return k

    sortie, conteneur = convertir(racine)
    if not conteneur:
        return sortie
    copie: Any = {} if isinstance(racine, dict) else []
    pile: list[tuple[Any, Any, int]] = [(racine, copie, 1)]
    while pile:
        source, cible, profondeur = pile.pop()
        if profondeur > PROFONDEUR_MAX:
            raise AnalyseInterrompue(f"Imbrication trop profonde (> {PROFONDEUR_MAX}).")
        elements = source.items() if isinstance(source, dict) else enumerate(source)
        for k, v in elements:
            compteur += 1
            if compteur > NOEUDS_MAX:
                raise AnalyseInterrompue(f"Document trop complexe (> {NOEUDS_MAX} éléments).")
            valeur, est_conteneur = convertir(v)
            if est_conteneur:
                valeur = {} if isinstance(v, dict) else []
                pile.append((v, valeur, profondeur + 1))
            if isinstance(cible, dict):
                cible[cle(k)] = valeur
            else:
                cible.append(valeur)
    return copie


def lire(contenu: bytes, nom_fichier: str) -> tuple[str, Any]:
    extension = "." + nom_fichier.rsplit(".", 1)[-1].lower() if "." in nom_fichier else ""
    fmt = EXTENSIONS.get(extension)
    if fmt is None:
        raise AnalyseInterrompue("Extension non prise en charge : .json, .yaml ou .yml attendu.")
    if contenu.startswith(b"\xef\xbb\xbf"):
        contenu = contenu[3:]
    try:
        texte = contenu.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnalyseInterrompue("Encodage invalide : UTF-8 attendu.") from exc
    if not texte.strip():
        raise AnalyseInterrompue("Fichier vide.")
    try:
        if fmt == "json":
            brut = json.loads(texte, object_pairs_hook=_paires_json, parse_constant=_constante_json)
        else:
            brut = yaml.load(texte, Loader=_ChargeurYaml)  # noqa: S506 — chargeur dérivé de SafeLoader
    except AnalyseInterrompue:
        raise
    except RecursionError as exc:
        raise AnalyseInterrompue(f"Imbrication trop profonde (> {PROFONDEUR_MAX}).") from exc
    except json.JSONDecodeError as exc:
        raise AnalyseInterrompue(f"JSON malformé (ligne {exc.lineno}, colonne {exc.colno}).") from exc
    except yaml.YAMLError as exc:
        position = getattr(exc, "problem_mark", None)
        ou = f" (ligne {position.line + 1})" if position else ""
        raise AnalyseInterrompue(f"YAML malformé{ou}.") from exc
    return fmt, _normaliser(brut)


# ------------------------------------------------------------------------------------- sécurité


def _pointeur(parties: list[str]) -> str:
    return "#/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parties)


def _est_reserve(valeur: Any) -> bool:
    return isinstance(valeur, str) and bool(_RESERVE.match(valeur.strip()))


def assainir(document: dict, analyse: Analyse) -> None:
    """Bloque les secrets évidents ; masque les exemples des champs sensibles ; retire les identifiants d'URL."""
    pile: list[tuple[Any, list[str]]] = [(document, [])]
    while pile:
        noeud, chemin = pile.pop()
        if isinstance(noeud, dict):
            sensible = (
                (len(chemin) >= 2 and chemin[-2] == "properties" and NOM_SENSIBLE.search(chemin[-1]))
                or (isinstance(noeud.get("name"), str) and NOM_SENSIBLE.search(noeud["name"]))
            )
            for cle in list(noeud):
                valeur = noeud[cle]
                if sensible and cle in ("example", "default", "x-example") and not _est_reserve(valeur):
                    noeud[cle] = MASQUE
                    analyse.avertir("EXEMPLE_MASQUE", "Exemple d'un champ sensible masqué.", _pointeur(chemin + [cle]))
                    continue
                if sensible and cle == "examples" and isinstance(valeur, dict):
                    for ex in valeur.values():
                        if isinstance(ex, dict) and "value" in ex and not _est_reserve(ex["value"]):
                            ex["value"] = MASQUE
                    analyse.avertir("EXEMPLE_MASQUE", "Exemples d'un champ sensible masqués.", _pointeur(chemin + [cle]))
                    continue
                if isinstance(valeur, str) and _URL_AVEC_IDENTIFIANTS.match(valeur):
                    noeud[cle] = valeur = url_metadonnee(valeur, analyse, _pointeur(chemin + [cle]))
                pile.append((valeur, chemin + [cle]))
        elif isinstance(noeud, list):
            for i, v in enumerate(noeud):
                if isinstance(v, str) and _URL_AVEC_IDENTIFIANTS.match(v):
                    noeud[i] = v = url_metadonnee(v, analyse, _pointeur(chemin + [str(i)]))
                pile.append((v, chemin + [str(i)]))
        elif isinstance(noeud, str) and SECRET_FORT.search(noeud):
            analyse.erreur(
                "SECRET_SUSPECT",
                "Valeur ressemblant à un secret (jeton JWT, clé privée ou en-tête Bearer) : la retirer du fichier.",
                _pointeur(chemin),
            )


def url_metadonnee(url: Any, analyse: Analyse, emplacement: str) -> str | None:
    """URL conservée comme texte : identifiants retirés, jamais résolue ni contactée."""
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()[:500]
    try:
        parts = urlsplit(url)
    except ValueError:
        analyse.avertir("URL_INVALIDE", "URL déclarée illisible, conservée sans interprétation.", emplacement)
        return url
    if parts.username or parts.password:
        hote = parts.hostname or ""
        if parts.port:
            hote = f"{hote}:{parts.port}"
        url = urlunsplit((parts.scheme, hote, parts.path, parts.query, parts.fragment))
        analyse.avertir("URL_IDENTIFIANTS_RETIRES", "Identifiants retirés d'une URL déclarée.", emplacement)
    return url


# ------------------------------------------------------------------------------------ références


class _Resolveur:
    def __init__(self, document: dict, analyse: Analyse):
        self.document = document
        self.analyse = analyse
        self.externes: set[str] = set()
        self.introuvables: set[str] = set()

    def cible(self, ref: str) -> Any:
        """Référence locale (``#/...``) uniquement ; ``None`` si externe ou introuvable (signalé une fois)."""
        if not ref.startswith("#"):
            if ref not in self.externes:
                self.externes.add(ref)
                self.analyse.avertir(
                    "REFERENCE_EXTERNE",
                    f"Référence non locale non résolue (jamais chargée) : {ref[:200]}",
                )
            return None
        if ref == "#":
            return self.document
        if not ref.startswith("#/"):
            return self._introuvable(ref)
        noeud: Any = self.document
        for partie in ref[2:].split("/"):
            partie = partie.replace("~1", "/").replace("~0", "~")
            if isinstance(noeud, dict) and partie in noeud:
                noeud = noeud[partie]
            elif isinstance(noeud, list) and partie.isdigit() and int(partie) < len(noeud):
                noeud = noeud[int(partie)]
            else:
                return self._introuvable(ref)
        return noeud

    def _introuvable(self, ref: str) -> None:
        if ref not in self.introuvables:
            self.introuvables.add(ref)
            self.analyse.erreur("REFERENCE_INTROUVABLE", f"Référence locale introuvable : {ref[:200]}")
        return None

    def deref(self, noeud: Any, limite: int = 16) -> Any:
        """Suit une chaîne de ``$ref`` locales (objets paramètre, corps, réponse, chemin)."""
        vus: set[str] = set()
        while isinstance(noeud, dict) and isinstance(noeud.get("$ref"), str) and limite > 0:
            ref = noeud["$ref"]
            if ref in vus:
                self.analyse.erreur("REFERENCE_CIRCULAIRE", f"Référence circulaire : {ref[:200]}")
                return None
            vus.add(ref)
            noeud = self.cible(ref)
            limite -= 1
        return noeud


def _nom_ref(ref: str) -> str:
    return ref.rsplit("/", 1)[-1][:120]


class _Schemas:
    def __init__(self, resolveur: _Resolveur):
        self.r = resolveur
        self.budget = SCHEMA_EXPANSION_MAX
        self.tronque = False

    def resumer(self, schema: Any, profondeur: int = 0, pile: tuple[str, ...] = ()) -> dict:
        self.budget -= 1
        if self.budget <= 0 or profondeur > SCHEMA_PROFONDEUR_MAX:
            self.tronque = True
            return {"tronque": True}
        if isinstance(schema, bool):
            return {"type": "quelconque" if schema else "aucun"}
        if not isinstance(schema, dict):
            return {"type": "invalide"}
        ref = schema.get("$ref")
        if isinstance(ref, str):
            if ref in pile:
                return {"ref": _nom_ref(ref), "circulaire": True}
            cible = self.r.cible(ref)
            if cible is None:
                return {"ref": ref[:200], "non_resolue": True, "externe": not ref.startswith("#")}
            resume = self.resumer(cible, profondeur, pile + (ref,))
            return {"ref": _nom_ref(ref), **resume}
        sortie: dict[str, Any] = {}
        type_ = schema.get("type")
        if isinstance(type_, list):
            sortie["type"] = " | ".join(str(t) for t in type_[:5])
        elif isinstance(type_, str):
            sortie["type"] = type_
        for cle in ("format", "title"):
            if isinstance(schema.get(cle), str):
                sortie[cle] = schema[cle][:120]
        if isinstance(schema.get("description"), str):
            sortie["description"] = schema["description"][:300]
        if schema.get("nullable") is True:
            sortie["nullable"] = True
        if isinstance(schema.get("enum"), list):
            sortie["enum"] = [str(v)[:80] for v in schema["enum"][:ENUM_MAX]]
        proprietes = schema.get("properties")
        if isinstance(proprietes, dict):
            requis = schema.get("required") if isinstance(schema.get("required"), list) else []
            champs = []
            for nom, sous in list(proprietes.items())[:CHAMPS_MAX]:
                champs.append({"nom": nom[:120], "requis": nom in requis,
                               "schema": self.resumer(sous, profondeur + 1, pile)})
            sortie["champs"] = champs
            if len(proprietes) > CHAMPS_MAX:
                sortie["champs_tronques"] = True
            sortie.setdefault("type", "object")
        if "items" in schema:
            sortie["items"] = self.resumer(schema["items"], profondeur + 1, pile)
            sortie.setdefault("type", "array")
        for comp in ("allOf", "oneOf", "anyOf"):
            if isinstance(schema.get(comp), list):
                sortie[comp] = [self.resumer(s, profondeur + 1, pile) for s in schema[comp][:10]]
        return sortie


def resumer_schema(schema: dict | None) -> dict | None:
    """Résumé d'un schéma autonome (configuration manuelle, sans ``$ref``)."""
    if schema is None:
        return None
    analyse = Analyse(nom_fichier="manuel", taille=0, empreinte="")
    return _Schemas(_Resolveur({}, analyse)).resumer(schema)


def type_libelle(resume: dict | None) -> str:
    if not resume:
        return "non précisé"
    if resume.get("ref") and not resume.get("type"):
        return resume["ref"]
    base = resume.get("type") or ("objet" if resume.get("champs") else "non précisé")
    if base == "array" and isinstance(resume.get("items"), dict):
        return f"array<{type_libelle(resume['items'])}>"
    return f"{base} ({resume['format']})" if resume.get("format") else base


# ------------------------------------------------------------------------------------ opérations


def empreinte_operation(op: dict) -> str:
    stable = {k: v for k, v in op.items() if k not in ("empreinte",)}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _texte(v: Any, n: int) -> str | None:
    return v.strip()[:n] or None if isinstance(v, str) else None


def _parametre(brut: Any, r: _Resolveur, s: _Schemas, ou: str, analyse: Analyse) -> dict | None:
    p = r.deref(brut)
    if not isinstance(p, dict):
        analyse.erreur("PARAMETRE_INVALIDE", "Paramètre illisible.", ou)
        return None
    nom, emplacement = p.get("name"), p.get("in")
    if not isinstance(nom, str) or not nom or emplacement not in ("path", "query", "header", "cookie"):
        analyse.erreur("PARAMETRE_INVALIDE", "Paramètre sans nom ou emplacement valide.", ou)
        return None
    schema = p.get("schema")
    if schema is None and isinstance(p.get("content"), dict):
        media = next(iter(p["content"].values()), None)
        schema = media.get("schema") if isinstance(media, dict) else None
    return {
        "nom": nom[:100],
        "emplacement": emplacement,
        "requis": bool(p.get("required")) or emplacement == "path",
        "description": _texte(p.get("description"), 500),
        "schema": s.resumer(schema) if schema is not None else None,
        "deprecie": bool(p.get("deprecated")),
    }


def _contenus(contenu: Any, s: _Schemas) -> list[dict]:
    if not isinstance(contenu, dict):
        return []
    sortie = []
    for type_contenu, media in list(contenu.items())[:10]:
        schema = media.get("schema") if isinstance(media, dict) else None
        sortie.append({"type_contenu": str(type_contenu)[:100], "schema": s.resumer(schema) if schema else None})
    return sortie


def _schemes_requis(securite: Any) -> list[list[str]] | None:
    if not isinstance(securite, list):
        return None
    alternatives = []
    for exigence in securite[:10]:
        if isinstance(exigence, dict):
            alternatives.append([str(n)[:100] for n in exigence])
    return alternatives


def _securite_declaree(document: dict, analyse: Analyse) -> list[dict]:
    composants = document.get("components") if isinstance(document.get("components"), dict) else {}
    schemes = composants.get("securitySchemes") if isinstance(composants.get("securitySchemes"), dict) else {}
    sortie = []
    for nom, brut in list(schemes.items())[:50]:
        ou = _pointeur(["components", "securitySchemes", nom])
        if not isinstance(brut, dict):
            analyse.avertir("SECURITE_ILLISIBLE", "Mécanisme d'authentification illisible.", ou)
            continue
        if isinstance(brut.get("$ref"), str):
            brut = _Resolveur(document, analyse).deref(brut) or {}
        type_ = brut.get("type")
        if type_ not in ("apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"):
            analyse.avertir("SECURITE_INCONNUE", f"Type d'authentification non reconnu : {str(type_)[:40]}", ou)
        entree: dict[str, Any] = {"nom": nom[:100], "type": str(type_)[:40], "description": _texte(brut.get("description"), 300)}
        if type_ == "apiKey":
            entree["emplacement"] = brut.get("in") if brut.get("in") in ("header", "query", "cookie") else None
            entree["nom_parametre"] = _texte(brut.get("name"), 100)
        elif type_ == "http":
            entree["schema_http"] = _texte(brut.get("scheme"), 40)
            entree["format_jeton"] = _texte(brut.get("bearerFormat"), 40)
        elif type_ == "oauth2" and isinstance(brut.get("flows"), dict):
            flux = []
            for nom_flux, f in list(brut["flows"].items())[:5]:
                if not isinstance(f, dict):
                    continue
                flux.append({
                    "flux": str(nom_flux)[:40],
                    "url_jeton": url_metadonnee(f.get("tokenUrl"), analyse, ou),
                    "url_autorisation": url_metadonnee(f.get("authorizationUrl"), analyse, ou),
                    "scopes": [str(x)[:100] for x in list((f.get("scopes") or {}))[:50]]
                    if isinstance(f.get("scopes"), dict) else [],
                })
            entree["flux"] = flux
        elif type_ == "openIdConnect":
            entree["url_openid"] = url_metadonnee(brut.get("openIdConnectUrl"), analyse, ou)
        sortie.append(entree)
    return sortie


def _serveurs(liste: Any, analyse: Analyse, ou: str) -> list[dict]:
    if not isinstance(liste, list):
        return []
    sortie = []
    for i, srv in enumerate(liste[:20]):
        if isinstance(srv, dict):
            url = url_metadonnee(srv.get("url"), analyse, f"{ou}/{i}")
            if url:
                sortie.append({"url": url, "description": _texte(srv.get("description"), 300)})
    return sortie


def _operations(document: dict, analyse: Analyse) -> list[dict]:
    r = _Resolveur(document, analyse)
    chemins = document.get("paths")
    if chemins is None:
        analyse.avertir("AUCUN_CHEMIN", "Aucun objet « paths » : aucune opération importée.")
        return []
    if not isinstance(chemins, dict):
        analyse.erreur("PATHS_INVALIDE", "L'objet « paths » doit être un dictionnaire.", "#/paths")
        return []
    securite_globale = _schemes_requis(document.get("security")) or []
    noms_securite = {e["nom"] for e in analyse.securite}
    ids_vus: dict[str, str] = {}
    sortie: list[dict] = []
    s = _Schemas(r)
    for chemin, item_brut in chemins.items():
        ou_chemin = _pointeur(["paths", chemin])
        if chemin.startswith("x-"):
            continue
        if len(chemin) > 300 or not CHEMIN_VALIDE.match(chemin) or "/../" in chemin + "/" or "//" in chemin:
            analyse.erreur("CHEMIN_INVALIDE", f"Chemin non pris en charge : {chemin[:120]}", ou_chemin)
            continue
        item = r.deref(item_brut)
        if not isinstance(item, dict):
            analyse.erreur("CHEMIN_INVALIDE", "Objet de chemin illisible.", ou_chemin)
            continue
        if item.get("servers"):
            analyse.avertir("SERVEURS_CHEMIN", "Serveurs déclarés au niveau du chemin : métadonnées non utilisées.",
                            ou_chemin)
        communs = item.get("parameters") if isinstance(item.get("parameters"), list) else []
        for methode in METHODES:
            if methode not in item:
                continue
            ou = _pointeur(["paths", chemin, methode])
            brut = item[methode]
            if not isinstance(brut, dict):
                analyse.erreur("OPERATION_INVALIDE", "Opération illisible.", ou)
                continue
            if len(sortie) >= OPERATIONS_MAX:
                analyse.erreur("TROP_D_OPERATIONS", f"Plus de {OPERATIONS_MAX} opérations : fichier refusé.")
                return sortie
            op_id = _texte(brut.get("operationId"), 160)
            if op_id:
                if op_id in ids_vus:
                    analyse.erreur("OPERATION_ID_DUPLIQUE", f"operationId en double : {op_id}", ou)
                ids_vus[op_id] = ou
            parametres: dict[tuple[str, str], dict] = {}
            for i, p in enumerate(communs + (brut.get("parameters") if isinstance(brut.get("parameters"), list) else [])):
                lu = _parametre(p, r, s, f"{ou}/parameters/{i}", analyse)
                if lu:
                    parametres[(lu["nom"], lu["emplacement"])] = lu
            places = set(PLACEHOLDER.findall(chemin))
            declares = {n for (n, e) in parametres if e == "path"}
            if places != declares:
                analyse.avertir("PARAMETRES_CHEMIN", "Paramètres de chemin incohérents avec le gabarit.", ou)
            corps = None
            corps_brut = r.deref(brut.get("requestBody"))
            if isinstance(corps_brut, dict):
                corps = {"requis": bool(corps_brut.get("required")),
                         "description": _texte(corps_brut.get("description"), 500),
                         "contenus": _contenus(corps_brut.get("content"), s)}
            reponses = []
            if isinstance(brut.get("responses"), dict):
                for code, rep_brute in list(brut["responses"].items())[:30]:
                    rep = r.deref(rep_brute)
                    if isinstance(rep, dict):
                        reponses.append({"code": str(code)[:10], "description": _texte(rep.get("description"), 500),
                                         "contenus": _contenus(rep.get("content"), s)})
            else:
                analyse.avertir("REPONSES_ABSENTES", "Aucune réponse déclarée.", ou)
            exigences = _schemes_requis(brut.get("security"))
            exigences = securite_globale if exigences is None else exigences
            for alt in exigences:
                for nom in alt:
                    if nom not in noms_securite:
                        analyse.avertir("SECURITE_INCONNUE", f"Mécanisme « {nom} » non déclaré dans components.", ou)
            for ignore in ("callbacks", "links"):
                if brut.get(ignore):
                    analyse.avertir("NON_IMPORTE", f"« {ignore} » non importés : jamais invoqués.", ou)
            if brut.get("servers"):
                analyse.avertir("SERVEURS_OPERATION", "Serveurs propres à l'opération : métadonnées non utilisées.", ou)
            liste = list(parametres.values())
            op = {
                "methode": methode.upper(),
                "chemin": chemin,
                "operation_id": op_id,
                "nom": _texte(brut.get("summary"), 300),
                "description": _texte(brut.get("description"), 4000),
                "tags": [str(t)[:80] for t in brut.get("tags", [])[:10]] if isinstance(brut.get("tags"), list) else [],
                "deprecie": bool(brut.get("deprecated")),
                "parametres": [p for p in liste if p["emplacement"] in ("path", "query", "cookie")],
                "entetes": [
                    {"nom": p["nom"], "requis": p["requis"], "description": p["description"]}
                    for p in liste if p["emplacement"] == "header"
                ],
                "corps": corps,
                "reponses": reponses,
                "authentification": [{"mecanismes": alt} for alt in exigences],
            }
            op["empreinte"] = empreinte_operation(op)
            sortie.append(op)
    if s.tronque:
        analyse.avertir("SCHEMAS_TRONQUES", "Schémas trop profonds ou trop vastes : résumés tronqués.")
    if isinstance(document.get("webhooks"), dict) and document["webhooks"]:
        analyse.avertir("NON_IMPORTE", "« webhooks » non importés : jamais invoqués.", "#/webhooks")
    return sortie


# --------------------------------------------------------------------------------------- entrée


def analyser(contenu: bytes, nom_fichier: str | None) -> Analyse:
    """Analyse complète, sans effet de bord ni accès réseau. ``valide`` = aucune erreur."""
    nom = nom_fichier_sur(nom_fichier)
    analyse = Analyse(nom_fichier=nom, taille=len(contenu), empreinte=hashlib.sha256(contenu).hexdigest())
    if len(contenu) > TAILLE_MAX:
        analyse.erreur("FICHIER_TROP_VOLUMINEUX", f"Fichier de plus de {TAILLE_MAX // (1024 * 1024)} Mo.")
        return analyse
    try:
        analyse.format, document = lire(contenu, nom)
    except AnalyseInterrompue as exc:
        analyse.erreur("FICHIER_INVALIDE", str(exc))
        return analyse
    if not isinstance(document, dict):
        analyse.erreur("FICHIER_INVALIDE", "Le document doit être un objet OpenAPI.")
        return analyse
    if "swagger" in document:
        analyse.erreur("VERSION_NON_PRISE_EN_CHARGE", "Swagger 2.0 non pris en charge : OpenAPI 3.0 ou 3.1 attendu.")
        return analyse
    version = document.get("openapi")
    if not isinstance(version, str) or not VERSION_SUPPORTEE.match(version):
        analyse.erreur("VERSION_NON_PRISE_EN_CHARGE",
                       f"Version OpenAPI non prise en charge ({str(version)[:20]}) : 3.0.x ou 3.1.x attendu.")
        return analyse
    analyse.openapi_version = version
    info = document.get("info")
    if not isinstance(info, dict) or not isinstance(info.get("title"), str) or not info["title"].strip():
        analyse.erreur("INFO_INVALIDE", "« info.title » obligatoire.", "#/info")
        return analyse
    analyse.titre = info["title"].strip()[:300]
    version_api = info.get("version")
    if isinstance(version_api, (int, float)) and not isinstance(version_api, bool):
        analyse.avertir("INFO_VERSION", "« info.version » numérique converti en texte.", "#/info/version")
        version_api = str(version_api)
    if not isinstance(version_api, str) or not version_api.strip():
        analyse.erreur("INFO_INVALIDE", "« info.version » obligatoire.", "#/info")
        return analyse
    analyse.version_api = version_api.strip()[:100]
    analyse.description = _texte(info.get("description"), 2000)

    assainir(document, analyse)
    analyse.serveurs = _serveurs(document.get("servers"), analyse, "#/servers")
    if analyse.serveurs:
        analyse.avertir("SERVEURS_DECLARES", "URL de serveurs conservées comme métadonnées : jamais contactées.")
    analyse.securite = _securite_declaree(document, analyse)
    analyse.operations = _operations(document, analyse)
    analyse.document = document
    return analyse
