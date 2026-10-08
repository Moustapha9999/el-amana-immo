"""Référentiel maître de classification — LOT 1 du CDC 1.0 (oct. 2026).

Chaque ligne : Dimension → Critère → Valeur → Score → Niveau → Source → Version
→ Conflit → Statut de validation.

Aucune valeur n'est ACTIVEE en production. Les conflits V1/V4 restent A_ARBITRER.
Les scores « retenus » n'existent que si V1 et V4 s'accordent, ou si le CDC
désigne explicitement V1 comme référentiel métier (géographie, sous-secteurs,
produits, canaux V1) sans inventer un score V4 absent.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.data.clientele_classif_matrice import POIDS_ECHELLE, VERSION_REGLES
from app.data.clientele_classif_referentiel import REFERENTIEL

_ACC = str.maketrans({
    "À": "A", "Á": "A", "Â": "A", "Ã": "A", "Ä": "A", "È": "E", "É": "E", "Ê": "E",
    "Ë": "E", "Ì": "I", "Í": "I", "Î": "I", "Ï": "I", "Ò": "O", "Ó": "O", "Ô": "O",
    "Ö": "O", "Ù": "U", "Ú": "U", "Û": "U", "Ü": "U", "Ç": "C", "à": "a", "á": "a",
    "â": "a", "ä": "a", "è": "e", "é": "e", "ê": "e", "ë": "e", "ì": "i", "í": "i",
    "î": "i", "ï": "i", "ò": "o", "ó": "o", "ô": "o", "ö": "o", "ù": "u", "ú": "u",
    "û": "u", "ü": "u", "ç": "c",
})


def slug_cle(valeur: object | None) -> str:
    s = " ".join(str(valeur or "").strip().translate(_ACC).upper().replace("_", " ").split())
    out = [ch if ch.isalnum() else "_" for ch in s]
    return "_".join(p for p in "".join(out).split("_") if p) or "X"

DIMENSIONS = (
    {"code": "CLIENT", "libelle": "Risque client"},
    {"code": "GEOGRAPHIE", "libelle": "Risque géographique"},
    {"code": "PRODUIT_SERVICE_OPERATION", "libelle": "Produit / service / opération"},
    {"code": "CANAL", "libelle": "Canal de distribution"},
)


def _score(niveau: str | None) -> int | None:
    if not niveau or niveau == "INTERDIT":
        return None
    return POIDS_ECHELLE.get(niveau)


def _ligne(
    dimension: str, critere: str, code: str, libelle: str, *,
    niveau_v1: str | None = None, score_v4: int | None = None, niveau_v4: str | None = None,
    is_blocking: bool = False, source: str, statut: str, note: str = "",
    conflit: bool = False,
) -> dict[str, Any]:
    score_v1 = 100_000 if niveau_v1 == "INTERDIT" else _score(niveau_v1)
    if niveau_v4 is None and score_v4 is not None:
        if score_v4 >= 100_000:
            niveau_v4 = "ELEVE"
        elif score_v4 >= 10_000:
            niveau_v4 = "MOYEN"
        elif score_v4 > 0:
            niveau_v4 = "FAIBLE"
    retenu_n = retenu_s = None
    if statut in ("ALIGNEE", "SOURCE_V1") and not conflit:
        if niveau_v1 == "INTERDIT":
            retenu_n, retenu_s = "INTERDIT", 100_000
        elif niveau_v1:
            retenu_n, retenu_s = niveau_v1, score_v1
        elif score_v4 is not None:
            retenu_n, retenu_s = niveau_v4, score_v4
    if conflit:
        retenu_n, retenu_s = None, None
        statut = "A_ARBITRER"
    return {
        "dimension": dimension,
        "critere": critere,
        "code": code[:80],
        "libelle": (libelle or "")[:255],
        "score_v1": score_v1,
        "niveau_v1": niveau_v1,
        "score_v4": score_v4,
        "niveau_v4": niveau_v4,
        "score_retenu": retenu_s,
        "niveau_retenu": retenu_n,
        "is_blocking": bool(is_blocking or niveau_v1 == "INTERDIT"),
        "source": source,
        "version": VERSION_REGLES,
        "conflit": conflit,
        "statut": statut,
        "note": note,
        "actif": False,
    }


def _pairer_niveau(v1: str | None, v4: str | None, score_v4: int | None) -> tuple[bool, str]:
    nv4 = v4
    if nv4 is None and score_v4 is not None:
        if score_v4 >= 100_000:
            nv4 = "ELEVE"
        elif score_v4 >= 10_000:
            nv4 = "MOYEN"
        elif score_v4 > 0:
            nv4 = "FAIBLE"
    if v1 == "INTERDIT":
        note = "CDC §5 : INTERDIT V1 = blocage métier."
        if nv4 and nv4 != "INTERDIT":
            note += f" V4 {nv4} documenté, non substitué."
        return False, note
    if v1 and nv4 and v1 != nv4:
        return True, f"V1 {v1} vs V4 {nv4}."
    return False, ""


@lru_cache(maxsize=1)
def valeurs_maitres() -> tuple[dict[str, Any], ...]:
    ref = REFERENTIEL
    out: list[dict[str, Any]] = []

    # --- CLIENT : profils ---
    profils_v1 = {x["libelle"]: x for x in (ref.get("matrice_client") or {}).get("Profil") or []}
    profils_v4 = {x["libelle"]: x for x in (ref.get("listes_v4") or {}).get("profil") or []}
    for lib, v1 in profils_v1.items():
        v4 = profils_v4.get(lib) or profils_v4.get(lib.replace("é", "e"))
        if not v4:
            for k, item in profils_v4.items():
                if slug_cle(k) == slug_cle(lib):
                    v4 = item
                    break
        n1 = v1.get("niveau_matrice")
        p4 = (v4 or {}).get("poids_v4")
        n4 = (v4 or {}).get("niveau_v4")
        conflit, note = _pairer_niveau(n1, n4, p4)
        out.append(_ligne(
            "CLIENT", "PROFIL", slug_cle(lib), lib,
            niveau_v1=n1, score_v4=p4, niveau_v4=n4,
            source="MATRICE_V1+SCORING_V4" if v4 else "MATRICE_V1",
            statut="ALIGNEE" if (v4 and not conflit) else ("A_ARBITRER" if conflit else "SOURCE_V1"),
            conflit=conflit, note=note or "CDC §8.1",
        ))

    # --- CLIENT : catégories / formes ---
    for dim, critere, bloc_v4 in (
        ("Personne_Physique", "CATEGORIE_PP", "personne_physique"),
        ("Personne_Morale_Publique", "CATEGORIE_PM_PUBLIQUE", "personne_morale_publique"),
        ("Personne_Morale_Privée", "CATEGORIE_PM_PRIVEE", "personne_morale_privee"),
        ("Personne_Morale_Association", "CATEGORIE_ASSOCIATION", "personne_morale_association"),
    ):
        v1s = list((ref.get("matrice_client") or {}).get(dim) or [])
        v4s = {(x.get("libelle") or ""): x for x in (ref.get("listes_v4") or {}).get(bloc_v4) or []}
        vus = set()
        for it in v1s:
            lib = (it.get("libelle") or "").strip()
            if not lib:
                continue
            v4 = v4s.get(lib)
            if not v4:
                for k, item in v4s.items():
                    if slug_cle(k) == slug_cle(lib):
                        v4 = item
                        break
            n1 = it.get("niveau_matrice")
            p4 = (v4 or {}).get("poids_v4")
            n4 = (v4 or {}).get("niveau_v4")
            conflit, note = _pairer_niveau(n1, n4, p4)
            out.append(_ligne(
                "CLIENT", critere, slug_cle(lib), lib,
                niveau_v1=n1, score_v4=p4, niveau_v4=n4,
                source="MATRICE_V1+SCORING_V4" if v4 else "MATRICE_V1",
                statut="ALIGNEE" if (v4 and not conflit) else ("A_ARBITRER" if conflit else "SOURCE_V1"),
                conflit=conflit, note=note or f"CDC formes {dim}",
            ))
            vus.add(slug_cle(lib))
        for lib, v4 in v4s.items():
            if slug_cle(lib) in vus or not lib:
                continue
            out.append(_ligne(
                "CLIENT", critere, slug_cle(lib), lib,
                score_v4=v4.get("poids_v4"), niveau_v4=v4.get("niveau_v4"),
                source="SCORING_V4", statut="SOURCE_V4",
                note="Présent V4 seulement — ne remplace pas V1.",
            ))

    # --- CLIENT : oui/non simples ---
    simples = [
        ("PPE", "PPE", "PPE", "CDC §18"),
        ("PPE_LISTE", "Filtrage (présence sur liste PPE)", "PPE_LISTE", "CDC §18 filtrage PPE"),
        ("SANCTIONS", "Filtrage (présence sur liste de sanction)", "LISTE_INTERDICTION", "CDC §19"),
        ("PROCURATION", "PROCURATION SUR COMPTE", "PROCURATION", "CDC §20"),
        ("RESIDENCE", "RESIDENT", "RESIDENCE", "CDC §16"),
        ("NATIONALITE_BINAIRE", "Nationalité", "NATIONALITE", "CDC §15 binaire mauritanienne/étrangère"),
    ]
    ppe_v4 = {(x.get("libelle") or ""): x for x in (ref.get("listes_v4") or {}).get("ppe_oui_non") or []}
    proc_v4 = {(x.get("libelle") or ""): x for x in (ref.get("listes_v4") or {}).get("procuration") or []}
    for critere, cle_m, _code, cdc in simples:
        for it in (ref.get("matrice_client") or {}).get(cle_m) or []:
            lib = (it.get("libelle") or "").strip()
            if not lib:
                continue
            v4 = None
            if critere == "PPE":
                v4 = ppe_v4.get(lib)
            if critere == "PROCURATION":
                cible = "Compte avec procuration" if lib.lower() == "oui" else "Compte sans procuration"
                v4 = proc_v4.get(cible)
            n1 = it.get("niveau_matrice")
            p4 = (v4 or {}).get("poids_v4")
            n4 = (v4 or {}).get("niveau_v4")
            conflit, note = _pairer_niveau(n1, n4, p4)
            out.append(_ligne(
                "CLIENT", critere, slug_cle(f"{critere}_{lib}"), lib,
                niveau_v1=n1, score_v4=p4, niveau_v4=n4,
                source="MATRICE_V1+SCORING_V4" if v4 else "MATRICE_V1",
                statut="ALIGNEE" if not conflit else "A_ARBITRER",
                conflit=conflit, note=note or cdc,
            ))

    for it in (ref.get("matrice_client") or {}).get("Tranche de revenus PP") or []:
        lib = (it.get("libelle") or "").strip()
        if lib:
            out.append(_ligne(
                "CLIENT", "REVENUS_PP", slug_cle(lib), lib,
                niveau_v1=it.get("niveau_matrice"), source="MATRICE_V1",
                statut="SOURCE_V1", note="CDC §14. Absent du scoring V4.",
            ))
    for it in (ref.get("matrice_client") or {}).get("Tranche de revenus PM") or []:
        lib = (it.get("libelle") or "").strip()
        if lib:
            out.append(_ligne(
                "CLIENT", "REVENUS_PM", slug_cle(lib), lib,
                niveau_v1=it.get("niveau_matrice"), source="MATRICE_V1",
                statut="SOURCE_V1", note="CDC §14. Absent du scoring V4.",
            ))

    # --- CLIENT : 119 sous-secteurs V1 (CDC §13 : référentiel détaillé) ---
    v4_sect = {(x.get("libelle") or ""): x for x in (ref.get("listes_v4") or {}).get("secteur") or []}
    vus_s: set[str] = set()
    for it in (ref.get("matrice_client") or {}).get("Sous secteur d'activité") or []:
        lib = (it.get("libelle") or "").strip()
        if not lib:
            continue
        n1 = it.get("niveau_matrice")
        # Pas de fusion silencieuse avec les 71 codes V4 (libellés différents).
        out.append(_ligne(
            "CLIENT", "SOUS_SECTEUR", slug_cle(lib) or f"S{len(vus_s)}", lib,
            niveau_v1=n1, is_blocking=n1 == "INTERDIT",
            source="MATRICE_V1",
            statut="SOURCE_V1",
            note="CDC §13. Référentiel détaillé V1. V4 n'est pas substitué.",
        ))
        vus_s.add(slug_cle(lib))
    for lib, v4 in v4_sect.items():
        if not lib:
            continue
        out.append(_ligne(
            "CLIENT", "SOUS_SECTEUR_V4", slug_cle(lib), lib,
            score_v4=v4.get("poids_v4"), niveau_v4=v4.get("niveau_v4"),
            source="SCORING_V4", statut="SOURCE_V4",
            note="Contrôle V4 — ne remplace pas les 119 sous-secteurs V1.",
        ))

    # --- GEOGRAPHIE : pays V1 + contrôle V4 ---
    for p in ref.get("pays") or []:
        n1 = p.get("niveau_matrice")
        n4 = p.get("niveau_pays_v4")
        p4 = p.get("poids_pays_v4")
        if p.get("categorie_v4") == "INACCEPTABLE_V4":
            n4 = "ELEVE"
        conflit, note = _pairer_niveau(n1, n4, p4)
        sources = "+".join(p.get("sources") or ["MATRICE_V1"])
        statut = "A_ARBITRER" if conflit else ("ALIGNEE" if n1 and n4 else "SOURCE_V1" if n1 else "SOURCE_V4")
        out.append(_ligne(
            "GEOGRAPHIE", "PAYS", p.get("code") or slug_cle(p.get("nom_fr")), p.get("nom_fr") or "",
            niveau_v1=n1, score_v4=p4, niveau_v4=n4,
            is_blocking=n1 == "INTERDIT",
            source=sources, statut=statut, conflit=conflit,
            note=note or "CDC §17–26. V1 = référentiel géographique ; V4 = contrôle, pas de remplacement silencieux.",
        ))

    # --- PRODUIT / OPERATION ---
    for it in ref.get("produits_matrice") or []:
        lib = (it.get("libelle") or "").strip()
        if not lib:
            continue
        fam = it.get("famille") or "OPERATION"
        out.append(_ligne(
            "PRODUIT_SERVICE_OPERATION", f"OPERATION_{fam}", slug_cle(f"{fam}_{lib}"), lib,
            niveau_v1=it.get("niveau_matrice"), source="MATRICE_V1",
            statut="SOURCE_V1",
            note="CDC §27–29. Classification permanente du client ≠ évaluation d'une opération.",
        ))

    # --- CANAL V1 ---
    for it in ref.get("canaux_matrice") or []:
        lib = (it.get("libelle") or "").strip()
        if not lib:
            continue
        out.append(_ligne(
            "CANAL", "CANAL_OPERATION", slug_cle(lib), lib,
            niveau_v1=it.get("niveau_matrice"), source="MATRICE_V1",
            statut="SOURCE_V1", note="CDC §31. Canal d'opération (Agence / À distance).",
        ))
    for it in (ref.get("listes_v4") or {}).get("canal") or []:
        lib = (it.get("libelle") or "").strip()
        if not lib:
            continue
        out.append(_ligne(
            "CANAL", "CANAL_ENTREE_RELATION", slug_cle(lib), lib,
            score_v4=it.get("poids_v4"), niveau_v4=it.get("niveau_v4"),
            source="SCORING_V4", statut="SOURCE_V4",
            note="CDC §33. Canal d'entrée en relation (distinct du canal d'opération V1).",
        ))
    for extra in ("DIGITAL", "APPLICATION", "WEB", "INTERMEDIAIRE", "AUTRE"):
        out.append(_ligne(
            "CANAL", "CANAL_OPERATION", extra, extra,
            source="RESERVE_TECHNIQUE", statut="A_CONFIGURER",
            note="CDC §32. Prévu techniquement, aucun score inventé.",
        ))

    return tuple(out)


def synthese_valeurs() -> dict[str, Any]:
    rows = valeurs_maitres()
    par_dim: dict[str, int] = {}
    par_stat: dict[str, int] = {}
    conflits = 0
    blocking = 0
    for r in rows:
        par_dim[r["dimension"]] = par_dim.get(r["dimension"], 0) + 1
        par_stat[r["statut"]] = par_stat.get(r["statut"], 0) + 1
        if r["conflit"]:
            conflits += 1
        if r["is_blocking"]:
            blocking += 1
    return {
        "version": VERSION_REGLES,
        "total": len(rows),
        "par_dimension": par_dim,
        "par_statut": par_stat,
        "nb_conflits": conflits,
        "nb_blocking": blocking,
        "avertissement": (
            "Référentiel maître CDC 1.0. Aucune valeur n'est ACTIVE. "
            "Les conflits restent A_ARBITRER. Pas de chargement production."
        ),
    }
