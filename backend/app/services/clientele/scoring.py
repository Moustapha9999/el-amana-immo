"""Moteur de scoring LBC/FT — SCORE uniquement (CDC 1.0).

Pas de moteur MAX_NIVEAU concurrent. INTERDIT = blocage métier, le score reste calculé.
Une donnée absente n'est jamais FAIBLE. Les conflits V1/V4 n'entrent pas dans la somme.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

from app.data.clientele_classif_matrice import (
    FAMILLES,
    POIDS_ECHELLE,
    RANG,
    SEUILS_CDC,
    VERSION_MOTEUR,
    VERSION_REGLES,
    critere_par_code,
)
from app.data.clientele_classif_referentiel import REFERENTIEL
from app.data.clientele_sources import FICHE, MATRICE, SOURCES_LIBELLES, libelle_sources, nommer

_STATUTS_HORS_SOMME = frozenset({"A_ARBITRER", "A_CONFIGURER", "A_VERIFIER"})
_LISTE_NON = frozenset({"NON", "N", "NO", "FALSE", "0", "NEANT", "AUCUN"})

_ACCENTS = str.maketrans({
    "À": "A", "Á": "A", "Â": "A", "Ã": "A", "Ä": "A", "Å": "A",
    "È": "E", "É": "E", "Ê": "E", "Ë": "E",
    "Ì": "I", "Í": "I", "Î": "I", "Ï": "I",
    "Ò": "O", "Ó": "O", "Ô": "O", "Õ": "O", "Ö": "O",
    "Ù": "U", "Ú": "U", "Û": "U", "Ü": "U",
    "Ç": "C", "Ñ": "N", "Ÿ": "Y", "Œ": "O", "Æ": "A",
    "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a", "å": "a",
    "è": "e", "é": "e", "ê": "e", "ë": "e",
    "ì": "i", "í": "i", "î": "i", "ï": "i",
    "ò": "o", "ó": "o", "ô": "o", "õ": "o", "ö": "o",
    "ù": "u", "ú": "u", "û": "u", "ü": "u",
    "ç": "c", "ñ": "n", "ÿ": "y", "œ": "o", "æ": "a",
})

_MAURITANIE = frozenset({
    "MAURITANIE", "MAURITANIA", "MAURITANIENNE", "MAURITANIEN",
    "RIM", "ISLAMIC REPUBLIC OF MAURITANIA",
})

FAMILLE_CRITERE = {
    "PROFIL": "CLIENT", "FORME_JURIDIQUE": "CLIENT", "ASSOCIATION": "CLIENT",
    "RESIDENCE": "CLIENT", "NATIONALITE": "CLIENT", "SECTEUR": "CLIENT",
    "LISTE_INTERDICTION": "CLIENT", "FILTRAGE": "CLIENT", "PPE": "CLIENT",
    "PPE_LISTE": "CLIENT", "PROCURATION": "CLIENT", "AGE_PP": "CLIENT",
    "REVENUS_PP": "CLIENT", "REVENUS_PM": "CLIENT", "ORIGINE_FONDS": "CLIENT",
    "BENEFICIAIRE_EFFECTIF": "CLIENT", "ENTREPRISE_RECENTE": "CLIENT",
    "JUGEMENT_TRANSACTIONS": "CLIENT", "ETAPE_EER": "CLIENT",
    "PAYS_RESIDENCE": "GEOGRAPHIE", "PAYS_PROVENANCE_FONDS": "GEOGRAPHIE",
    "PAYS_DESTINATION_FONDS": "GEOGRAPHIE",
    "PRODUIT": "PRODUIT_SERVICE_OPERATION", "TYPE_OPERATION": "PRODUIT_SERVICE_OPERATION",
    "CANAL": "CANAL",
}


def normaliser(valeur: object | None) -> str:
    if valeur is None:
        return ""
    s = str(valeur).strip().translate(_ACCENTS).upper()
    s = " ".join(s.replace("_", " ").split())
    return s


def slug_cle(valeur: object | None) -> str:
    s = normaliser(valeur)
    out = []
    for ch in s:
        out.append(ch if ch.isalnum() else "_")
    return "_".join(p for p in "".join(out).split("_") if p)


def poids_vers_niveau(poids: int | None) -> str | None:
    if poids is None or poids <= 0:
        return None
    if poids >= POIDS_ECHELLE["ELEVE"]:
        return "ELEVE"
    if poids >= POIDS_ECHELLE["MOYEN"]:
        return "MOYEN"
    return "FAIBLE"


def niveau_depuis_score_v4(score: int) -> str | None:
    """Formule C39 telle quelle (inégalités strictes). score==10000 → None (incomplet)."""
    if score > 100_000:
        return "ELEVE"
    if score > 10_000:
        return "MOYEN"
    if score < 10_000:
        return "FAIBLE"
    return None


def niveau_depuis_score_cdc(score: int, nb_evalues: int) -> str | None:
    """CDC 1.0 §4. 0 critère évalué → None, jamais FAIBLE."""
    if nb_evalues <= 0:
        return None
    if score >= SEUILS_CDC["ELEVE_MIN"]:
        return "ELEVE"
    if score >= SEUILS_CDC["FAIBLE_MAX"]:
        return "MOYEN"
    return "FAIBLE"


def niveau_depuis_score_proposition(score: int, nb_evalues: int) -> str | None:
    return niveau_depuis_score_cdc(score, nb_evalues)


@dataclass
class DonneesClient:
    racine: str
    nationalite: str | None = None
    statut_resident: str | None = None
    categorie_juridique: str | None = None
    situation_juridique: str | None = None
    secteur_activite: str | None = None
    famille_secteur: str | None = None
    agent_economique: str | None = None
    type_client: str | None = None
    date_naissance: date | None = None
    date_creation_pm: date | None = None
    liste_interdiction: str | None = None
    ppe: bool | None = None
    procuration: bool | None = None
    pays_residence: str | None = None
    origine_fonds: str | None = None
    filtrage_confirme: bool | None = None
    eer_present: bool = False
    eer_operation: str | None = None


@dataclass
class LigneEvaluation:
    critere: str
    libelle: str
    etat: str
    valeur: str | None
    source_donnee: str | None
    poids: int | None
    niveau_matrice: str | None
    niveau_v4: str | None
    niveau_retenu: str | None
    type_decision: str
    motif: str
    divergence: bool = False
    blocking_propose: bool = False
    statut_regle: str = "A_ARBITRER"
    famille: str = "CLIENT"
    contribue_au_score: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "critere": self.critere,
            "libelle": self.libelle,
            "famille": self.famille,
            "etat": self.etat,
            "valeur": self.valeur,
            "source_donnee": self.source_donnee,
            "poids": self.poids,
            "niveau_matrice": self.niveau_matrice,
            "niveau_v4": self.niveau_v4,
            "niveau_retenu": self.niveau_retenu,
            "type_decision": self.type_decision,
            "motif": libelle_sources(self.motif),
            "divergence": self.divergence,
            "blocking_propose": self.blocking_propose,
            "is_blocking": self.blocking_propose,
            "statut_regle": self.statut_regle,
            "contribue_au_score": self.contribue_au_score,
        }


@dataclass
class Evaluation:
    racine: str
    date_evaluation: str
    version_moteur: str
    version_regles: str
    mode: str
    score_total: int
    nb_evalues: int
    niveau_score: str | None
    niveau_score_v4: str | None
    niveau_max: str | None
    niveau_final: str | None
    statut: str
    coherence: str
    motif_principal: str | None
    autres_facteurs: list[str]
    blocking_proposes: list[str]
    divergences: list[str]
    completude: str = "INCOMPLETE"
    scores_familles: dict[str, int] = field(default_factory=dict)
    motif_genere: str = ""
    lignes: list[LigneEvaluation] = field(default_factory=list)
    avertissement: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "racine_client": self.racine,
            "date_evaluation": self.date_evaluation,
            "version_moteur": self.version_moteur,
            "version_regles": self.version_regles,
            "mode": self.mode,
            "score_total": self.score_total,
            "nb_evalues": self.nb_evalues,
            "niveau_score": self.niveau_score,
            "niveau_score_v4": self.niveau_score_v4,
            "niveau_max": self.niveau_max,
            "niveau_final": self.niveau_final,
            "statut": self.statut,
            "coherence": self.coherence,
            "motif_principal": self.motif_principal,
            "autres_facteurs": self.autres_facteurs,
            "blocking_proposes": self.blocking_proposes,
            "divergences": self.divergences,
            "completude": self.completude,
            "scores_familles": self.scores_familles,
            "motif_genere": self.motif_genere,
            "lignes": [lg.to_dict() for lg in self.lignes],
            "avertissement": libelle_sources(self.avertissement),
            "seuils": SEUILS_CDC,
            "sources_libelles": SOURCES_LIBELLES,
        }


@lru_cache(maxsize=1)
def _index() -> dict[str, Any]:
    ref = REFERENTIEL
    pays_par_alias: dict[str, dict] = {}
    for p in ref["pays"]:
        for a in p.get("aliases") or []:
            k = slug_cle(a)
            if k:
                pays_par_alias[k] = p
        for champ in ("nom_fr", "nom_en", "nationalite", "code"):
            k = slug_cle(p.get(champ))
            if k:
                pays_par_alias[k] = p
    nat_v4 = {slug_cle(x["libelle"]): x for x in (ref.get("listes_v4") or {}).get("ppe_oui_non", [])}
    # nationalités : mauritanienne vs le reste via pays
    formes: list[dict] = []
    for bloc, profil in (
        ("personne_physique", "Personne_Physique"),
        ("personne_morale_publique", "Personne_Morale_Publique"),
        ("personne_morale_privee", "Personne_Morale_Privee"),
        ("personne_morale_association", "Personne_Morale_Association"),
    ):
        for it in (ref.get("listes_v4") or {}).get(bloc, []):
            formes.append({**it, "profil_v4": profil, "source": "SCORING_V4"})
    for dim, items in (ref.get("matrice_client") or {}).items():
        if dim in (
            "Personne_Physique", "Personne_Morale_Publique",
            "Personne_Morale_Privée", "Personne_Morale_Association",
        ):
            for it in items:
                formes.append({
                    "libelle": it["libelle"],
                    "niveau_matrice": it.get("niveau_matrice"),
                    "profil_matrice": dim,
                    "source": "MATRICE_V1",
                })
    secteurs_m = list((ref.get("matrice_client") or {}).get("Sous secteur d'activité") or [])
    secteurs_v4 = list((ref.get("listes_v4") or {}).get("secteur") or [])
    profils_m = {normaliser(x["libelle"]): x for x in (ref.get("matrice_client") or {}).get("Profil") or []}
    profils_v4 = {normaliser(x["libelle"]): x for x in (ref.get("listes_v4") or {}).get("profil") or []}
    assoc_lib = [
        slug_cle(x["libelle"])
        for x in (ref.get("listes_v4") or {}).get("personne_morale_association") or []
    ]
    assoc_lib += [
        slug_cle(x["libelle"])
        for x in (ref.get("matrice_client") or {}).get("Personne_Morale_Association") or []
    ]
    return {
        "pays": pays_par_alias,
        "formes": formes,
        "secteurs_m": secteurs_m,
        "secteurs_v4": secteurs_v4,
        "profils_m": profils_m,
        "profils_v4": profils_v4,
        "assoc": frozenset(x for x in assoc_lib if x),
        "ppe_v4": nat_v4,
        "residence_m": {
            normaliser(x["libelle"]): x
            for x in (ref.get("matrice_client") or {}).get("RESIDENT") or []
        },
        "nationalite_m": {
            normaliser(x["libelle"]): x
            for x in (ref.get("matrice_client") or {}).get("Nationalité") or []
        },
        "ppe_m": {
            normaliser(x["libelle"]): x
            for x in (ref.get("matrice_client") or {}).get("PPE") or []
        },
        "procuration_m": {
            normaliser(x["libelle"]): x
            for x in (ref.get("matrice_client") or {}).get("PROCURATION SUR COMPTE") or []
        },
        "filtrage_m": {
            normaliser(x["libelle"]): x
            for x in (ref.get("matrice_client") or {}).get("Filtrage (présence sur liste de sanction)") or []
        },
        "procuration_v4": (ref.get("listes_v4") or {}).get("procuration") or [],
    }


def _ligne_base(code: str, **kwargs: Any) -> LigneEvaluation:
    meta = critere_par_code(code) or {}
    return LigneEvaluation(
        critere=code,
        libelle=str(meta.get("libelle") or code),
        etat=kwargs.pop("etat", "NON_DISPONIBLE"),
        valeur=kwargs.pop("valeur", None),
        source_donnee=kwargs.pop("source_donnee", None),
        poids=kwargs.pop("poids", None),
        niveau_matrice=kwargs.pop("niveau_matrice", None),
        niveau_v4=kwargs.pop("niveau_v4", None),
        niveau_retenu=kwargs.pop("niveau_retenu", None),
        type_decision=str(kwargs.pop("type_decision", meta.get("type_decision") or "SCORE")),
        motif=kwargs.pop("motif", meta.get("note") or ""),
        divergence=bool(kwargs.pop("divergence", False)),
        blocking_propose=bool(kwargs.pop("blocking_propose", False)),
        statut_regle=str(kwargs.pop("statut_regle", meta.get("statut") or "A_ARBITRER")),
        famille=str(kwargs.pop("famille", FAMILLE_CRITERE.get(code, "CLIENT"))),
        contribue_au_score=bool(kwargs.pop("contribue_au_score", False)),
    )


def _indispo(code: str, motif: str, source: str | None = None) -> LigneEvaluation:
    return _ligne_base(code, etat="NON_DISPONIBLE", motif=motif, source_donnee=source, poids=None)


def _chercher_pays(valeur: str | None) -> dict | None:
    if not valeur:
        return None
    idx = _index()["pays"]
    k = slug_cle(valeur)
    if k in idx:
        return idx[k]
    # nationalité « afghane » etc.
    for alias, p in idx.items():
        nat = slug_cle(p.get("nationalite"))
        if nat and (k == nat or k.startswith(nat) or nat.startswith(k)):
            return p
    return None


def _est_mauritanie(valeur: str | None) -> bool:
    k = slug_cle(valeur)
    return k in {slug_cle(x) for x in _MAURITANIE} or k in _MAURITANIE


def _match_texte(valeur: str, candidats: list[dict], cle: str = "libelle") -> dict | None:
    nv = normaliser(valeur)
    if not nv:
        return None
    sv = slug_cle(nv)
    exact = []
    partiel = []
    for it in candidats:
        lib = normaliser(it.get(cle))
        if not lib:
            continue
        sl = slug_cle(lib)
        if nv == lib or sv == sl:
            exact.append(it)
        elif sv and (sv in sl or sl in sv):
            partiel.append(it)
    if exact:
        return exact[0]
    if len(partiel) == 1:
        return partiel[0]
    return None


def _profil_derive(d: DonneesClient) -> tuple[str | None, str]:
    """Retourne (libellé matrice/V4, source). Ne force pas PP/PM ORION en profil LBC."""
    if d.type_client == "ASSOCIATION":
        return "Personne_Morale_Association", "ORION_TYPE_CLIENT"
    if d.type_client == "PM_PUBLIQUE":
        return "Personne_Morale_Publique", "ORION_TYPE_CLIENT"
    if d.type_client == "PM_PRIVEE":
        return "Personne_Morale_Privee", "ORION_TYPE_CLIENT"
    if d.type_client == "PP":
        return "Personne_Physique", "ORION_TYPE_CLIENT"
    cat = " ".join(x for x in (d.categorie_juridique, d.situation_juridique) if x)
    if cat:
        if _match_texte(cat, [
            {"libelle": x} for x in (
                "ONG", "ASSOCIATION", "ASSOCIATIONS", "FONDATION", "FONDATIONS",
                "COOPERATIVE", "COOPERATIVES", "PARTI POLITIQUE", "PARTIS POLITIQUES",
                "ORGANISATION", "ORGANISATIONS",
            )
        ]):
            return "Personne_Morale_Association", "ORION_CATEGORIE"
        idx = _index()
        f = _match_texte(cat, idx["formes"])
        if f:
            return (
                f.get("profil_matrice") or f.get("profil_v4"),
                "ORION_CATEGORIE",
            )
    ag = normaliser(d.agent_economique)
    if ag in ("PARTICULIERS", "PERSONNEL BANQUE"):
        return "Personne_Physique", "ORION_AGENT"
    if ag:
        return None, "ORION_AGENT_NON_MAPPE"
    return None, "ABSENT"


def _eval_profil(d: DonneesClient) -> LigneEvaluation:
    profil, src = _profil_derive(d)
    if not profil:
        return _indispo("PROFIL", "Profil LBC non déterminé (ORION PP/PM trop grossier ou catégorie absente).", src)
    idx = _index()
    m = idx["profils_m"].get(normaliser(profil.replace("_Privee", "_Privée")))
    if not m:
        m = idx["profils_m"].get(normaliser(profil))
    v = idx["profils_v4"].get(normaliser(profil.replace("_Privee", "_Privée")))
    if not v:
        v = idx["profils_v4"].get(normaliser(profil))
    nm = m.get("niveau_matrice") if m else None
    pv = v.get("poids_v4") if v else None
    nv = v.get("niveau_v4") if v else poids_vers_niveau(pv)
    div = bool(nm and nv and nm != nv)
    poids = None if div else (POIDS_ECHELLE.get(nm) if nm and nm != "INTERDIT" else pv)
    return _ligne_base(
        "PROFIL", etat="EVALUE", valeur=profil, source_donnee=src,
        poids=poids,
        niveau_matrice=nm, niveau_v4=nv,
        niveau_retenu=None if div else (nm or nv),
        divergence=div,
        statut_regle="A_ARBITRER" if div else ("ALIGNEE" if nv else "SOURCE_V1"),
        motif=(
            f"Matrice {nm or '—'} / V4 {nv or '—'} (poids {pv})."
            + (" Conflit de référentiel : non additionné tant que non arbitrée." if div else "")
        ),
    )


def _fusion_forme(brut: str) -> dict | None:
    """Fusionne V1 + V4 pour un même libellé. Ne choisit pas silencieusement une source."""
    sv, nv = slug_cle(brut), normaliser(brut)
    hits: list[dict] = []
    for f in _index()["formes"]:
        lib = normaliser(f.get("libelle"))
        sl = slug_cle(lib)
        if nv == lib or sv == sl:
            hits.append(f)
    if not hits:
        partiel = []
        for f in _index()["formes"]:
            sl = slug_cle(f.get("libelle"))
            if sv and sl and (sv in sl or sl in sv):
                partiel.append(f)
        libs = {slug_cle(f.get("libelle")) for f in partiel}
        if len(libs) == 1:
            hits = partiel
        elif partiel:
            return {"ambigu": True}
    if not hits:
        return None
    nm = next((f.get("niveau_matrice") for f in hits if f.get("niveau_matrice")), None)
    pv = next((f.get("poids_v4") for f in hits if f.get("poids_v4") is not None), None)
    nv4 = next((f.get("niveau_v4") for f in hits if f.get("niveau_v4")), None) or poids_vers_niveau(pv)
    lib = next((f.get("libelle") for f in hits if f.get("libelle")), brut)
    return {"libelle": lib, "niveau_matrice": nm, "poids_v4": pv, "niveau_v4": nv4}


def _eval_forme(d: DonneesClient) -> LigneEvaluation:
    brut = d.categorie_juridique or d.situation_juridique
    if not brut:
        return _indispo("FORME_JURIDIQUE", "Catégorie / situation juridique ORION absente.", "ORION")
    f = _fusion_forme(brut)
    if not f or f.get("ambigu"):
        return _ligne_base(
            "FORME_JURIDIQUE", etat="A_VERIFIER", valeur=brut, source_donnee="ORION",
            motif="Libellé ORION non rapproché (ou ambigu) des listes Matrice / V4. Pas de FAIBLE par défaut.",
            statut_regle="A_VERIFIER",
        )
    nm = f.get("niveau_matrice")
    pv = f.get("poids_v4")
    nv = f.get("niveau_v4") or poids_vers_niveau(pv)
    div = bool(nm and nv and nm != nv)
    poids = None if div else (POIDS_ECHELLE.get(nm) if nm and nm != "INTERDIT" else pv)
    return _ligne_base(
        "FORME_JURIDIQUE", etat="EVALUE", valeur=f.get("libelle") or brut, source_donnee="ORION",
        poids=poids,
        niveau_matrice=nm, niveau_v4=nv, niveau_retenu=None if div else (nm or nv),
        divergence=div, statut_regle="A_ARBITRER" if div else ("ALIGNEE" if nv else "SOURCE_V1"),
        motif=f"Rapproché de « {f.get('libelle')} ». Matrice {nm or '—'} / V4 {nv or '—'}."
              + (" Conflit : non additionné." if div else ""),
    )


def _eval_association(d: DonneesClient) -> LigneEvaluation:
    brut = " ".join(x for x in (d.categorie_juridique, d.situation_juridique, d.secteur_activite) if x)
    if not brut:
        return _indispo("ASSOCIATION", "Pas de libellé juridique/secteur pour tester association/ONG.", "ORION")
    sl = slug_cle(brut)
    hit = None
    for a in _index()["assoc"]:
        if a and (a in sl or sl in a):
            hit = a
            break
    mots = ("ONG", "ASSOCIATION", "FONDATION", "COOPERATIVE", "PARTI_POLITIQUE", "ORGANISATION")
    if not hit:
        for m in mots:
            if m in sl:
                hit = m
                break
    if not hit:
        return _ligne_base(
            "ASSOCIATION", etat="EVALUE", valeur="Non", source_donnee="ORION",
            poids=0, niveau_matrice=None, niveau_v4=None, niveau_retenu=None,
            motif="Aucun libellé association/ONG/fondation/coop/parti détecté. Poids 0 (pas un Faible inventé).",
            statut_regle="ALIGNEE",
        )
    return _ligne_base(
        "ASSOCIATION", etat="EVALUE", valeur=hit, source_donnee="ORION",
        poids=100_000, niveau_matrice="ELEVE", niveau_v4="ELEVE", niveau_retenu="ELEVE",
        motif="Matrice et V4 alignés : association/ONG/fondation/coop/parti = ÉLEVÉ (100000).",
        statut_regle="ALIGNEE",
    )


def _eval_residence(d: DonneesClient) -> LigneEvaluation:
    st = (d.statut_resident or "").strip().upper()
    if st not in ("R", "N"):
        return _indispo("RESIDENCE", "Statut résident ORION absent (ni R ni N).", "ORION")
    if st == "N":
        return _ligne_base(
            "RESIDENCE", etat="EVALUE", valeur="N", source_donnee="ORION",
            poids=100_000, niveau_matrice="ELEVE", niveau_v4=None, niveau_retenu="ELEVE",
            motif="Matrice : non-résident = ÉLEVÉ. V4 n'a pas le champ R/N.",
            statut_regle="ALIGNEE",
        )
    return _ligne_base(
        "RESIDENCE", etat="EVALUE", valeur="R", source_donnee="ORION",
        poids=100, niveau_matrice="FAIBLE", niveau_v4=None, niveau_retenu="FAIBLE",
        motif="Matrice : résident = Faible.",
        statut_regle="ALIGNEE",
    )


def _eval_nationalite(d: DonneesClient) -> LigneEvaluation:
    if not d.nationalite:
        return _indispo("NATIONALITE", "Nationalité ORION absente.", "ORION")
    if _est_mauritanie(d.nationalite):
        return _ligne_base(
            "NATIONALITE", etat="EVALUE", valeur=d.nationalite, source_donnee="ORION",
            poids=100, niveau_matrice="FAIBLE", niveau_v4="FAIBLE", niveau_retenu="FAIBLE",
            motif="Mauritanienne : Matrice Faible / V4 100. Aligné.",
            statut_regle="ALIGNEE",
        )
    p = _chercher_pays(d.nationalite)
    if p or d.nationalite.strip():
        # étrangère si on a une valeur non mauritanienne
        if not p:
            return _ligne_base(
                "NATIONALITE", etat="A_VERIFIER", valeur=d.nationalite, source_donnee="ORION",
                motif="Nationalité non rapprochée du référentiel pays. Pas de Moyen inventé.",
                statut_regle="A_VERIFIER",
            )
        pv = p.get("poids_nationalite_v4")
        return _ligne_base(
            "NATIONALITE", etat="EVALUE", valeur=d.nationalite, source_donnee="ORION",
            poids=pv if pv is not None else 10_000,
            niveau_matrice="MOYEN", niveau_v4=poids_vers_niveau(pv) or "MOYEN",
            niveau_retenu="MOYEN",
            motif=f"Étrangère ({p.get('nom_fr')}). Matrice Moyen / V4 nationalité {pv}. Aligné sur Moyen.",
            statut_regle="ALIGNEE",
        )
    return _indispo("NATIONALITE", "Nationalité vide après normalisation.", "ORION")


def _eval_pays_residence(d: DonneesClient) -> LigneEvaluation:
    if not d.pays_residence:
        return _indispo("PAYS_RESIDENCE", "Pays de résidence absent d'ORION ; EER non renseigné.", "EER")
    p = _chercher_pays(d.pays_residence)
    if not p:
        return _ligne_base(
            "PAYS_RESIDENCE", etat="A_VERIFIER", valeur=d.pays_residence, source_donnee="EER",
            motif="Pays non rapproché de la table de réconciliation.",
            statut_regle="A_VERIFIER",
        )
    nm, nv = p.get("niveau_matrice"), p.get("niveau_pays_v4")
    if not nm:
        return _ligne_base(
            "PAYS_RESIDENCE", etat="A_VERIFIER", valeur=p.get("nom_fr") or d.pays_residence,
            source_donnee="EER",
            motif="Pays sans niveau V1. V4 n'est pas substitué (CDC §17, §26).",
            statut_regle="A_VERIFIER", famille="GEOGRAPHIE",
        )
    blocking = nm == "INTERDIT"
    poids = 100_000 if blocking else POIDS_ECHELLE.get(nm)
    return _ligne_base(
        "PAYS_RESIDENCE", etat="EVALUE", valeur=p.get("nom_fr"), source_donnee="EER",
        poids=poids,
        niveau_matrice=nm, niveau_v4=nv, niveau_retenu=nm,
        divergence=bool(nv and nv != nm and nm != "INTERDIT"),
        blocking_propose=blocking,
        type_decision="BLOCKING" if blocking else "SCORE",
        statut_regle="SOURCE_V1",
        famille="GEOGRAPHIE",
        motif=(
            f"Zone géographique V1 {nm} / contrôle V4 {p.get('label_v4') or nv or '—'}."
            + (" INTERDIT bloquant (CDC §5, §17). Le score reste calculé." if blocking else "")
        ),
    )


def _eval_secteur(d: DonneesClient) -> LigneEvaluation:
    brut = d.secteur_activite or d.famille_secteur
    if not brut:
        return _indispo("SECTEUR", "Secteur ORION absent.", "ORION")
    idx = _index()
    m = _match_texte(brut, idx["secteurs_m"])
    v = _match_texte(brut, idx["secteurs_v4"])
    if not m:
        return _ligne_base(
            "SECTEUR", etat="A_VERIFIER", valeur=brut, source_donnee="ORION",
            motif="Non rapproché des 119 sous-secteurs V1. Le code V4 n'est pas substitué (CDC §13).",
            statut_regle="A_VERIFIER",
        )
    nm = m.get("niveau_matrice")
    pv = v.get("poids_v4") if v else None
    nv = (v.get("niveau_v4") if v else None) or poids_vers_niveau(pv)
    blocking = nm == "INTERDIT"
    poids = 100_000 if blocking else POIDS_ECHELLE.get(nm)
    return _ligne_base(
        "SECTEUR", etat="EVALUE",
        valeur=m.get("libelle") or brut, source_donnee="ORION",
        poids=poids, niveau_matrice=nm, niveau_v4=nv,
        niveau_retenu=nm,
        divergence=False, blocking_propose=blocking,
        type_decision="BLOCKING" if blocking else "SCORE",
        statut_regle="SOURCE_V1",
        motif=(
            f"Sous-secteur V1 {nm} (CDC §13)."
            + (" INTERDIT bloquant." if blocking else "")
        ),
    )


def _eval_liste_interdiction(d: DonneesClient) -> LigneEvaluation:
    if d.liste_interdiction is None:
        return _indispo(
            "LISTE_INTERDICTION",
            "Liste d'interdiction ORION non collectée. Donnée absente ≠ Non/Faible (CDC §48).",
            "ORION",
        )
    val = d.liste_interdiction.strip()
    if not val or slug_cle(val) in _LISTE_NON:
        return _ligne_base(
            "LISTE_INTERDICTION", etat="EVALUE", valeur="Non", source_donnee="ORION",
            poids=100, niveau_matrice="FAIBLE", niveau_v4=None, niveau_retenu="FAIBLE",
            motif="ORION LISTE_INTERDICTION vide/Non = Non (CDC §19). Score 100.",
            statut_regle="SOURCE_V1",
        )
    return _ligne_base(
        "LISTE_INTERDICTION", etat="EVALUE", valeur=val, source_donnee="ORION",
        poids=100_000, niveau_matrice="ELEVE", niveau_v4=None, niveau_retenu="ELEVE",
        blocking_propose=False, type_decision="SCORE",
        motif="Matrice filtrage sanctions Oui = ÉLEVÉ (CDC §19). Pas INTERDIT (distinct §5).",
        statut_regle="SOURCE_V1",
    )


def _eval_filtrage(d: DonneesClient) -> LigneEvaluation:
    if d.filtrage_confirme is True:
        return _ligne_base(
            "FILTRAGE", etat="EVALUE", valeur="Oui", source_donnee="ALERTES",
            poids=100_000, niveau_matrice="ELEVE", niveau_retenu="ELEVE",
            motif="Alerte confirmée. Matrice = ÉLEVÉ. INTERDIT vs ÉLEVÉ : A_ARBITRER.",
            statut_regle="A_ARBITRER",
        )
    return _indispo(
        "FILTRAGE",
        "Pas d'alerte confirmée. Ce n'est pas un « Non » métier : le client n'est pas certifié hors liste.",
        "ALERTES",
    )


def _eval_ppe(d: DonneesClient) -> LigneEvaluation:
    if d.ppe is None:
        return _indispo(
            "PPE",
            "PPE inconnu (pas d'EER lié, ou champ vide). Ne pas traiter comme Non/Faible.",
            "EER" if d.eer_present else None,
        )
    if d.ppe:
        return _ligne_base(
            "PPE", etat="EVALUE", valeur="Oui", source_donnee="EER",
            poids=100_000, niveau_matrice="ELEVE", niveau_v4="ELEVE", niveau_retenu="ELEVE",
            motif="PPE confirmé. Matrice Élevé / V4 100000. Aligné.",
            statut_regle="ALIGNEE",
        )
    return _ligne_base(
        "PPE", etat="EVALUE", valeur="Non", source_donnee="EER",
        poids=100, niveau_matrice="FAIBLE", niveau_v4="FAIBLE", niveau_retenu="FAIBLE",
        motif="PPE déclaré Non dans EER. V4 ajoute 100 (Faible), matrice Faible. Aligné.",
        statut_regle="ALIGNEE",
    )


def _eval_procuration(d: DonneesClient) -> LigneEvaluation:
    if d.procuration is None:
        return _indispo("PROCURATION", "Mandataire / procuration EER non renseigné.", "EER")
    if d.procuration:
        return _ligne_base(
            "PROCURATION", etat="EVALUE", valeur="Oui", source_donnee="EER",
            poids=100_000, niveau_matrice="ELEVE", niveau_v4="ELEVE", niveau_retenu="ELEVE",
            motif="Matrice Oui=Élevé / V4 100000. Aligné.",
            statut_regle="ALIGNEE",
        )
    return _ligne_base(
        "PROCURATION", etat="EVALUE", valeur="Non", source_donnee="EER",
        poids=100, niveau_matrice="FAIBLE", niveau_v4="FAIBLE", niveau_retenu="FAIBLE",
        motif="Sans procuration. V4 100 / matrice Faible.",
        statut_regle="ALIGNEE",
    )


def _eval_age_pp(d: DonneesClient, au_jour: date) -> LigneEvaluation:
    profil, _ = _profil_derive(d)
    if profil and profil != "Personne_Physique" and d.type_client not in (None, "PP"):
        return _ligne_base(
            "AGE_PP", etat="NON_APPLICABLE", valeur=profil, source_donnee="ORION",
            motif="Formule V4 d'âge réservée aux personnes physiques.",
            statut_regle="ALIGNEE",
        )
    if profil != "Personne_Physique" and d.type_client != "PP" and not d.date_naissance:
        return _indispo("AGE_PP", "Pas une PP identifiée, ou date de naissance absente.", "ORION")
    if not d.date_naissance:
        return _indispo("AGE_PP", "Date de naissance ORION absente.", "ORION")
    jours = (au_jour - d.date_naissance).days
    if jours > 6580:
        niv = "FAIBLE"
        motif = f"V4 H23 : {jours} j > 6580 → 100. Absent de la matrice."
    else:
        niv = "MOYEN"
        motif = f"V4 H23 : {jours} j ≤ 6580 (mineur) → 10000 Moyen. Absent de la matrice."
    return _ligne_base(
        "AGE_PP", etat="EVALUE", valeur=str(d.date_naissance), source_donnee="ORION",
        poids=None, niveau_matrice=None, niveau_v4=niv, niveau_retenu=None,
        divergence=True, statut_regle="A_CONFIGURER",
        motif=motif + " Seuil paramétrable (CDC §21), non additionné.",
    )


def _motif_genere(
    niveau: str | None,
    score: int,
    evalues: list[LigneEvaluation],
    blocking: list[LigneEvaluation],
) -> str:
    if blocking:
        p = blocking[0]
        return (
            f"Risque INTERDIT — Score {score}. "
            f"Blocage métier : {p.libelle} « {p.valeur} » classé INTERDIT "
            f"dans le référentiel BEA (CDC §5). Le score reste calculé."
        )
    if not evalues:
        return "Aucun critère validé n'entre dans le score. Donnée absente ≠ FAIBLE."
    principal = max(evalues, key=lambda lg: lg.poids or 0)
    autres_faibles = all(
        (lg.niveau_retenu or "FAIBLE") == "FAIBLE" for lg in evalues if lg is not principal)
    niv_lib = {"FAIBLE": "FAIBLE", "MOYEN": "MOYEN", "ELEVE": "ÉLEVÉ"}.get(niveau or "", niveau or "NON CLASSÉ")
    txt = f"Risque {niv_lib} — Score {score}."
    if principal.poids and principal.poids >= 10_000:
        txt += (
            f" Le score est principalement influencé par {principal.libelle.lower()} "
            f"« {principal.valeur} », classé {principal.niveau_retenu} dans le référentiel BEA."
        )
        if autres_faibles:
            txt += " Les autres critères applicables sont classés FAIBLE."
    else:
        txt += " Tous les critères applicables sont classés FAIBLE."
    return txt


def evaluer(d: DonneesClient, *, au_jour: date | None = None, mode: str = "SCORE") -> Evaluation:
    # CDC §3 : SCORE uniquement — le paramètre mode est ignoré (pas de MAX_NIVEAU concurrent).
    _ = mode
    jour = au_jour or date.today()
    lignes = [
        _eval_profil(d),
        _eval_forme(d),
        _eval_association(d),
        _eval_residence(d),
        _eval_nationalite(d),
        _eval_pays_residence(d),
        _eval_secteur(d),
        _eval_liste_interdiction(d),
        _eval_filtrage(d),
        _eval_ppe(d),
        _eval_procuration(d),
        _eval_age_pp(d, jour),
        _indispo("PPE_LISTE", "Liste PPE de filtrage non branchée.", None),
        _indispo("ORIGINE_FONDS", "Libellés V4 non mappés sur EER.origine_fonds (texte libre).", "EER"),
        _indispo("BENEFICIAIRE_EFFECTIF", "Mapping V4 des 3 états BE non validé.", "EER"),
        _indispo("REVENUS_PP", "Tranches matrice absentes d'ORION et du V4.", None),
        _indispo("REVENUS_PM", "Tranches matrice absentes d'ORION et du V4.", None),
        _indispo("ENTREPRISE_RECENTE", "Date de création PM = EER, pas DATOUV ORION.", "EER"),
        _indispo("CANAL", "Canal d'ouverture non disponible dans ORION État des comptes.", None),
        _indispo("PRODUIT", "Feuille Produit matrice : pas de source opérations.", None),
        _indispo("TYPE_OPERATION", "Pas de source opérations.", None),
        _indispo("PAYS_PROVENANCE_FONDS", "Pas de source opérations.", None),
        _indispo("PAYS_DESTINATION_FONDS", "Pas de source opérations.", None),
        _indispo("JUGEMENT_TRANSACTIONS", "Jugement V4 non saisi dans EER.", "EER"),
        _ligne_base(
            "ETAPE_EER",
            etat="EVALUE" if d.eer_operation else "NON_DISPONIBLE",
            valeur=d.eer_operation,
            source_donnee="EER" if d.eer_operation else None,
            poids=0,
            motif="V4 : Nouvelle_ouverture / Mise_à_jour = poids 0.",
            statut_regle="ALIGNEE",
        ),
    ]

    for lg in lignes:
        lg.contribue_au_score = (
            lg.etat == "EVALUE"
            and lg.poids is not None
            and lg.poids > 0
            and lg.statut_regle not in _STATUTS_HORS_SOMME
        )
    evalues = [lg for lg in lignes if lg.contribue_au_score]
    score = sum(lg.poids or 0 for lg in evalues)
    nb = len(evalues)
    niveau_score = niveau_depuis_score_cdc(score, nb)
    niveau_v4 = niveau_depuis_score_v4(score) if nb else None
    scores_familles = {
        fam: sum(lg.poids or 0 for lg in evalues if lg.famille == fam) for fam in FAMILLES
    }
    niveaux_contrib = [
        lg.niveau_retenu for lg in evalues if lg.niveau_retenu in RANG and lg.niveau_retenu != "INTERDIT"
    ]
    niveau_max = max(niveaux_contrib, key=lambda n: RANG[n]) if niveaux_contrib else None

    blocking = [lg for lg in lignes if lg.blocking_propose and lg.etat == "EVALUE"]
    conflits = [lg for lg in lignes if lg.statut_regle == "A_ARBITRER" and lg.etat == "EVALUE"]
    divergences = [lg for lg in lignes if lg.divergence]

    if blocking:
        statut, coherence, niveau_final = "BLOQUANT", "BLOQUANT", "INTERDIT"
    elif nb == 0 and not conflits:
        statut, coherence, niveau_final = "NON_CLASSE", "SANS_CRITERE", None
    elif conflits:
        statut, coherence, niveau_final = "A_ARBITRER", "CONFLIT_REFERENTIEL", niveau_score
    else:
        statut, coherence, niveau_final = "EVALUE", "OK", niveau_score

    evalues_tri = sorted(evalues, key=lambda lg: lg.poids or 0, reverse=True)
    motif = evalues_tri[0].libelle if evalues_tri else (blocking[0].libelle if blocking else None)
    autres = [lg.libelle for lg in evalues_tri[1:6]]
    par_code = {lg.critere: lg for lg in lignes}
    essentiels = ("PPE", "FILTRAGE", "RESIDENCE", "NATIONALITE")
    manquants = [c for c in essentiels if par_code.get(c) and par_code[c].etat != "EVALUE"]
    completude = "INCOMPLETE" if manquants or nb == 0 else "OK"
    motif_txt = _motif_genere(niveau_final, score, evalues, blocking)

    return Evaluation(
        racine=d.racine,
        date_evaluation=jour.isoformat(),
        version_moteur=VERSION_MOTEUR,
        version_regles=VERSION_REGLES,
        mode="SCORE",
        score_total=score,
        nb_evalues=nb,
        niveau_score=niveau_score,
        niveau_score_v4=niveau_v4,
        niveau_max=niveau_max,
        niveau_final=niveau_final,
        statut=statut,
        coherence=coherence,
        motif_principal=motif,
        autres_facteurs=autres,
        blocking_proposes=[f"{lg.critere}: {lg.valeur}" for lg in blocking],
        divergences=[
            f"{lg.critere} : {MATRICE} = {lg.niveau_matrice} / {FICHE} = {lg.niveau_v4}" for lg in divergences
        ],
        completude=completude,
        scores_familles=scores_familles,
        motif_genere=motif_txt,
        lignes=lignes,
        avertissement=(
            "Moteur SCORE uniquement (CDC 1.0). Aucune classification de production n'est écrite. "
            "INTERDIT = blocage métier, le score reste calculé. "
            f"Conflit {MATRICE} / {FICHE} non arbitré : exclu de la somme. Donnée absente ≠ Faible. "
            "0 critère évalué → NON CLASSÉ, pas FAIBLE."
        ),
    )


def matrice_maitre_dict() -> dict[str, Any]:
    from app.data.clientele_classif_matrice import CRITERES_MAITRE, QUESTIONS_CONFORMITE

    ref = REFERENTIEL
    return nommer({
        "meta": ref["meta"],
        "version_moteur": VERSION_MOTEUR,
        "version_regles": VERSION_REGLES,
        "seuils": SEUILS_CDC,
        "familles": list(FAMILLES),
        "formules_v4": ref.get("formules_v4"),
        "criteres": CRITERES_MAITRE,
        "questions_conformite": QUESTIONS_CONFORMITE,
        "synthese_pays": ref.get("synthese_pays"),
        "synthese_secteurs": ref.get("synthese_secteurs"),
        "liste_v4_avertissement": ref.get("liste_v4_avertissement"),
        "nb_pays": len(ref.get("pays") or []),
        "nb_divergences": len(ref.get("divergences") or []),
    }) | {"sources_libelles": SOURCES_LIBELLES}


def divergences_dict() -> dict[str, Any]:
    div = list(REFERENTIEL.get("divergences") or [])
    return {"total": len(div), "items": nommer(div), "sources_libelles": SOURCES_LIBELLES}


def valeurs_maitre_dict(
    *, dimension: str | None = None, statut: str | None = None,
    page: int = 1, taille: int = 80,
) -> dict[str, Any]:
    from app.data.clientele_classif_valeurs import synthese_valeurs, valeurs_maitres

    rows = list(valeurs_maitres())
    if dimension:
        rows = [r for r in rows if r["dimension"] == dimension]
    if statut:
        rows = [r for r in rows if r["statut"] == statut]
    page = max(1, page)
    taille = max(1, min(taille, 500))
    debut = (page - 1) * taille
    return {
        **synthese_valeurs(),
        "page": page,
        "taille": taille,
        "total_filtre": len(rows),
        "items": [
            {**nommer(r), "source_libelle": " + ".join(
                SOURCES_LIBELLES.get(s, s) for s in str(r.get("source") or "").split("+") if s)}
            for r in rows[debut:debut + taille]
        ],
        "sources_libelles": SOURCES_LIBELLES,
    }
