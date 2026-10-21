"""Exemples de code pour une opération d'un fournisseur externe (cURL, Python httpx, TypeScript fetch).

Les exemples ne sont jamais exécutés. Ils lisent l'URL de base et les identifiants dans des variables
d'environnement (aucune valeur par défaut, aucun secret) et signalent que l'appel n'a pas été testé.
Les chaînes issues d'une spécification importée sont des données non fiables : elles sont échappées
(guillemets shell, littéraux JSON/Python) ou écartées, jamais insérées brutes dans le code.
"""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import quote

from app.services.integrations.openapi_import import NOM_ENTETE, PLACEHOLDER

VAR_BASE_URL = "EXTERNAL_API_BASE_URL"
VAR_JETON = "EXTERNAL_API_TOKEN"
VAR_UTILISATEUR = "EXTERNAL_API_USERNAME"
VAR_MOT_DE_PASSE = "EXTERNAL_API_PASSWORD"

AVERTISSEMENT = "Exemple généré — appel NON testé, aucune connexion au fournisseur n'a été établie."
_NOM_VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,60}$")


def _ligne(texte: str | None, n: int = 160) -> str:
    """Texte sûr dans un commentaire d'une ligne (aucun saut de ligne, y compris U+2028/U+2029)."""
    propre = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in texte or "")
    return " ".join(propre.split())[:n]


def _sh(texte: str) -> str:
    return "'" + texte.replace("'", "'\"'\"'") + "'"


def _fictif(resume: dict | None, nom: str) -> object:
    t = str((resume or {}).get("type") or "").split(" ")[0]
    if t == "integer":
        return 1
    if t == "number":
        return 0
    if t == "boolean":
        return False
    if t == "array":
        return []
    if t == "object":
        return {}
    return f"<{_ligne(nom, 60)}>"


def _chemin_exemple(chemin: str) -> str:
    return PLACEHOLDER.sub(lambda m: f"<{m.group(1)}>", chemin)


def _requete(op: dict) -> dict[str, object]:
    return {
        p["nom"]: _fictif(p.get("schema"), p["nom"])
        for p in op.get("parametres") or []
        if p.get("emplacement") == "query" and p.get("requis")
    }


def _corps(op: dict) -> dict | None:
    corps = op.get("corps") or {}
    for contenu in corps.get("contenus") or []:
        if str(contenu.get("type_contenu", "")).startswith("application/json"):
            schema = contenu.get("schema") or {}
            return {c["nom"]: _fictif(c.get("schema"), c["nom"]) for c in schema.get("champs") or [] if c.get("requis")}
    return None


def _plan_auth(op: dict, mecanismes: dict[str, dict]) -> tuple[list[tuple[str, str]], dict[str, str], bool, list[str]]:
    """En-têtes (nom, variable), paramètres de requête (nom → variable), Basic, notes — première alternative."""
    entetes: list[tuple[str, str]] = []
    requete: dict[str, str] = {}
    basic = False
    notes: list[str] = []
    alternatives = op.get("authentification") or []
    noms = alternatives[0].get("mecanismes", []) if alternatives else []
    if not noms:
        notes.append("Aucune authentification déclarée pour cette opération.")
    for nom in noms:
        m = mecanismes.get(nom)
        if m is None:
            notes.append(f"Mécanisme « {_ligne(nom, 60)} » non décrit : non repris.")
            continue
        type_ = m.get("type")
        if type_ == "http" and str(m.get("schema_http") or "").lower() == "basic":
            basic = True
        elif type_ in ("http", "oauth2", "openIdConnect"):
            entetes.append(("Authorization", VAR_JETON))
            if type_ != "http":
                notes.append("Jeton à obtenir selon le flux déclaré par le fournisseur (non implémenté).")
        elif type_ == "apiKey" and m.get("nom_parametre"):
            nom_param = m["nom_parametre"]
            if m.get("emplacement") == "query":
                requete[nom_param] = VAR_JETON
            elif m.get("emplacement") == "header" and NOM_ENTETE.match(nom_param):
                entetes.append((nom_param, VAR_JETON))
            else:
                notes.append("Clé d'API dans un cookie ou nom d'en-tête invalide : non reprise.")
        elif type_ == "mutualTLS":
            notes.append("Certificat client (mTLS) déclaré : à configurer hors de l'exemple.")
        else:
            notes.append(f"Mécanisme « {_ligne(nom, 60)} » ({_ligne(str(type_), 30)}) non repris.")
    if len(alternatives) > 1:
        notes.append("Plusieurs alternatives d'authentification déclarées : seule la première est montrée.")
    return entetes, requete, basic, notes


def _query(params: dict[str, object], auth: dict[str, str]) -> str:
    morceaux = [f"{quote(str(k), safe='')}={quote(str(v), safe='<>')}" for k, v in params.items()]
    morceaux += [f"{quote(str(k), safe='')}=${{{v}}}" for k, v in auth.items()]
    return ("?" + "&".join(morceaux)) if morceaux else ""


def _curl(op: dict, entetes, auth_requete, basic, corps, params) -> str:
    url = f'"${{{VAR_BASE_URL}}}{_chemin_exemple(op["chemin"])}{_query(params, auth_requete)}"'
    lignes = [
        f"# {AVERTISSEMENT}",
        f': "${{{VAR_BASE_URL}:?définir {VAR_BASE_URL}}}"',
        f'curl -sS -X {op["methode"]} {url} \\',
    ]
    if basic:
        lignes.append(f'  -u "${{{VAR_UTILISATEUR}}}:${{{VAR_MOT_DE_PASSE}}}" \\')
    for nom, variable in entetes:
        prefixe = "Bearer " if nom == "Authorization" else ""
        lignes.append(f'  -H {_sh(f"{nom}: {prefixe}")}"${{{variable}}}" \\')
    if corps is not None:
        lignes.append("  -H 'Content-Type: application/json' \\")
        lignes.append(f"  --data {_sh(json.dumps(corps, ensure_ascii=False))} \\")
    lignes.append("  -H 'Accept: application/json'")
    return "\n".join(lignes)


def _python(op: dict, entetes, auth_requete, basic, corps, params) -> str:
    variables = {VAR_BASE_URL} | {v for _n, v in entetes} | set(auth_requete.values())
    if basic:
        variables |= {VAR_UTILISATEUR, VAR_MOT_DE_PASSE}
    lignes = [f"# {AVERTISSEMENT}", "import os", "", "import httpx", ""]
    for v in sorted(variables):
        lignes.append(f'{v} = os.environ["{v}"]')
    lignes += ["", "response = httpx.request(", f'    "{op["methode"]}",',
               f"    {VAR_BASE_URL} + {json.dumps(_chemin_exemple(op['chemin']))},"]
    tout = dict(params)
    if tout or auth_requete:
        lignes.append("    params={")
        for k, v in tout.items():
            lignes.append(f"        {json.dumps(k)}: {v!r},")
        for k, v in auth_requete.items():
            lignes.append(f"        {json.dumps(k)}: {v},")
        lignes.append("    },")
    if corps is not None:
        lignes.append(f"    json={corps!r},")
    if basic:
        lignes.append(f"    auth=({VAR_UTILISATEUR}, {VAR_MOT_DE_PASSE}),")
    lignes.append("    headers={")
    for nom, variable in entetes:
        valeur = f'f"Bearer {{{variable}}}"' if nom == "Authorization" else variable
        lignes.append(f"        {json.dumps(nom)}: {valeur},")
    lignes += ['        "Accept": "application/json",', "    },", "    timeout=30.0,", ")",
               "response.raise_for_status()", "print(response.json())"]
    return "\n".join(lignes)


def _typescript(op: dict, entetes, auth_requete, basic, corps, params) -> str:
    variables = {VAR_BASE_URL} | {v for _n, v in entetes} | set(auth_requete.values())
    if basic:
        variables |= {VAR_UTILISATEUR, VAR_MOT_DE_PASSE}
    lignes = [f"// {AVERTISSEMENT}", "function env(nom: string): string {",
              "  const valeur = process.env[nom];", "  if (!valeur) throw new Error(`${nom} manquant`);",
              "  return valeur;", "}", ""]
    for v in sorted(variables):
        lignes.append(f"const {v} = env('{v}');")
    lignes.append("")
    lignes.append(f"const url = new URL({VAR_BASE_URL} + {json.dumps(_chemin_exemple(op['chemin']))});")
    for k, v in params.items():
        lignes.append(f"url.searchParams.set({json.dumps(k)}, {json.dumps(str(v))});")
    for k, v in auth_requete.items():
        lignes.append(f"url.searchParams.set({json.dumps(k)}, {v});")
    lignes += ["const response = await fetch(url, {", f"  method: '{op['methode']}',", "  headers: {"]
    for nom, variable in entetes:
        valeur = f"`Bearer ${{{variable}}}`" if nom == "Authorization" else variable
        lignes.append(f"    {json.dumps(nom)}: {valeur},")
    if basic:
        lignes.append(f"    Authorization: `Basic ${{btoa(`${{{VAR_UTILISATEUR}}}:${{{VAR_MOT_DE_PASSE}}}`)}}`,")
    lignes.append("    Accept: 'application/json',")
    if corps is not None:
        lignes.append("    'Content-Type': 'application/json',")
    lignes.append("  },")
    if corps is not None:
        lignes.append(f"  body: JSON.stringify({json.dumps(corps, ensure_ascii=False)}),")
    lignes += ["});", "if (!response.ok) throw new Error(`HTTP ${response.status}`);",
               "console.log(await response.json());"]
    return "\n".join(lignes)


def generer(op: dict, mecanismes: list[dict], origine: str, url_declaree: str | None) -> dict:
    index = {m["nom"]: m for m in mecanismes if isinstance(m, dict) and m.get("nom")}
    entetes, auth_requete, basic, notes = _plan_auth(op, index)
    auth_requete = {k: v for k, v in auth_requete.items() if _NOM_VARIABLE.match(v)}
    params = _requete(op)
    corps = _corps(op)
    source = "la spécification importée" if origine == "openapi" else "une configuration manuelle"
    declares = [
        f"Méthode et chemin : déclarés par {source}.",
        "Paramètres, corps et réponses : déclarés, non vérifiés.",
        "Authentification : " + (", ".join(_ligne(n, 60) for n in (op.get("authentification") or [{}])[0].get(
            "mecanismes", [])) or "aucune") + " (déclarée, non vérifiée).",
    ]
    if url_declaree:
        declares.append(f"URL de base déclarée (non vérifiée, non contactée) : {_ligne(url_declaree, 300)}")
    args = (op, entetes, auth_requete, basic, corps, params)
    return {
        "avertissements": [
            AVERTISSEMENT,
            f"Définir {VAR_BASE_URL} et les identifiants dans l'environnement d'exécution ; "
            "ne jamais écrire de jeton ni de mot de passe dans le code.",
            *notes,
        ],
        "elements_declares": declares,
        "elements_verifies": [],
        "exemples": [
            {"langage": "curl", "libelle": "cURL", "code": _curl(*args)},
            {"langage": "python", "libelle": "Python (httpx)", "code": _python(*args)},
            {"langage": "typescript", "libelle": "TypeScript (fetch)", "code": _typescript(*args)},
        ],
    }
