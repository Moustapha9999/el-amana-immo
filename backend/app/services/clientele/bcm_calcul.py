"""Calcul de la Déclaration mensuelle BCM (tableaux 1 et 4) à partir des données réelles.

Deux étapes séparées pour rester vérifiable et reproductible :
1. ``charger`` : une requête SQL, une ligne par client ORION (entrée en relation, comptes, catégorie juridique,
   statut de gel, risque à la fin du mois précédent et à la fin du mois, dernière mise à jour dans la fenêtre) ;
2. ``agreger`` : fonction pure appliquant les règles enregistrées (``app/data/clientele_bcm_regles.py``).

Un client n'est compté qu'une fois par cellule (clé = racine). Une donnée absente ne devient jamais zéro :
la cellule est « non calculable » avec sa raison.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

NIVEAUX = ("FAIBLE", "MOYEN", "ELEVE", "INTERDIT")
COLONNES_RISQUE = {"ELEVE": "eleve", "MOYEN": "moyen", "FAIBLE": "faible"}
EER_STATUTS_REALISE = ("VALIDE", "CLOTURE", "ARCHIVE")
TZ = "Africa/Nouakchott"
LIGNES_T1 = ("stock_m1", "cible", "maj_mois", "maj_5ans")
REGLES_LIGNE = {
    "stock_m1": ("stock.date_entree", "stock.perimetre"),
    "cible": ("stock.date_entree", "actif.valeurs_gel", "actif.agregation"),
    "maj_mois": ("eer.source",),
    "maj_5ans": ("stock.date_entree", "maj.fenetre", "maj.evenements"),
}


@dataclass(frozen=True)
class DatesBcm:
    debut: date
    fin: date
    fin_mois_precedent: date
    fenetre_maj_debut: date

    def as_dict(self) -> dict:
        return {k: v.isoformat() for k, v in asdict(self).items()}


@dataclass(frozen=True)
class ClientBcm:
    racine: str
    d_entree: date | None
    a_ouvert: bool
    categorie: str | None = None
    profil: str | None = None
    gel: str | None = None
    risque_m1: str | None = None
    risque_fin: str | None = None
    d_maj: date | None = None


def _norm(v: Any) -> str:
    return " ".join(str(v or "").upper().split())


def debut_fenetre_maj(fin: date, regle: dict) -> date:
    annees = int(regle.get("annees") or 5)
    if regle.get("type") == "GLISSANTE":
        mois = fin.year * 12 + fin.month - 12 * annees
        a, m = divmod(mois, 12)
        return date(a, m + 1, 1)
    return date(fin.year - annees, 1, 1)


# --------------------------------------------------------------------------- règles appliquées
def forme_client(c: ClientBcm, regles: dict) -> str:
    """PP / PM / CJ, ou EXC_FORME_VIDE / EXC_FORME_NON_RATTACHEE (jamais affecté par défaut)."""
    cat = _norm(c.categorie)
    for forme, cats in (regles["forme.correspondance"] or {}).items():
        if cat and cat in {_norm(x) for x in cats}:
            return forme
    if not cat:
        if regles.get("forme.repli_profil") and c.profil in ("PP", "PM"):
            return c.profil
        return "EXC_FORME_VIDE"
    return "EXC_FORME_NON_RATTACHEE"


def risque_bcm(niveau: str | None, regles: dict) -> str:
    """Colonne BCM (eleve / moyen / faible) ou NON_CLASSE / INVALIDE / INTERDIT. Ne modifie aucun classement."""
    if not niveau:
        return "NON_CLASSE"
    if niveau not in NIVEAUX:
        return "INVALIDE"
    if niveau == "INTERDIT":
        return "eleve" if regles.get("interdit.rattachement") == "ELEVE" else "INTERDIT"
    return COLONNES_RISQUE[niveau]


def statut_actif(c: ClientBcm, regles: dict) -> str:
    """ACTIF / INACTIF / INDETERMINE. Compte ouvert et statut de gel restent deux conditions distinctes."""
    if not c.a_ouvert:
        return "INACTIF"
    if not _norm(c.gel):
        return "INDETERMINE"
    return "ACTIF" if _norm(c.gel) in {_norm(v) for v in regles["actif.valeurs_gel"]} else "INACTIF"


def dans_ligne(c: ClientBcm, ligne: str, dates: DatesBcm, regles: dict) -> bool:
    if c.d_entree is None:
        return False
    if ligne == "stock_m1":
        return c.d_entree <= dates.fin_mois_precedent
    if ligne == "cible":
        return c.d_entree <= dates.fin and statut_actif(c, regles) == "ACTIF"
    if ligne == "maj_mois":
        return dates.debut <= c.d_entree <= dates.fin
    if ligne == "maj_5ans":
        return c.d_entree <= dates.fin and c.d_maj is not None
    if ligne == "t4":
        return c.d_entree <= dates.fin
    raise ValueError(ligne)


def _risque_ligne(c: ClientBcm, ligne: str, regles: dict) -> str:
    return risque_bcm(c.risque_m1 if ligne == "stock_m1" else c.risque_fin, regles)


def selection(clients: list[ClientBcm], regles: dict, dates: DatesBcm, ligne: str,
              colonne: str | None = None) -> list[str]:
    """Racines d'une cellule (``colonne`` = pp / pm / cj / eleve / moyen / faible / total ou un code d'exception)."""
    out = []
    for c in clients:
        if not dans_ligne(c, ligne, dates, regles):
            continue
        if colonne in (None, "total", "valeur"):
            out.append(c.racine)
        elif colonne in ("pp", "pm", "cj") or colonne.startswith("EXC_FORME"):
            if forme_client(c, regles) == (colonne.upper() if colonne in ("pp", "pm", "cj") else colonne):
                out.append(c.racine)
        elif _risque_ligne(c, ligne, regles) == colonne:
            out.append(c.racine)
    return sorted(out)


def exception(clients: list[ClientBcm], regles: dict, dates: DatesBcm, code: str) -> list[str]:
    """Populations de contrôle (jamais affectées à une colonne)."""
    if code == "gel_indetermine":
        return sorted(c.racine for c in clients if c.d_entree and c.d_entree <= dates.fin
                      and statut_actif(c, regles) == "INDETERMINE")
    if code == "sans_date_entree":
        return sorted(c.racine for c in clients if c.d_entree is None)
    if code.startswith("t4_"):
        return selection(clients, regles, dates, "t4", code[3:])
    if code.startswith("forme_"):
        return selection(clients, regles, dates, "t4", code[6:].upper())
    raise ValueError(code)


# --------------------------------------------------------------------------- agrégation
def _cellule(valeur: int | float | None, *, regles_utilisees: tuple[str, ...], statuts: dict,
             raison: str | None = None, fiabilite: str | None = None) -> dict:
    a_valider = sorted(r for r in regles_utilisees if statuts.get(r) != "CONFIRMEE")
    if valeur is None:
        fiab = fiabilite or "NON_CALCULABLE"
    else:
        fiab = fiabilite or ("AVEC_RESERVE" if a_valider else "CALCULE")
    return {"valeur": valeur, "calculable": valeur is not None, "fiabilite": fiab, "raison": raison,
            "regles": list(regles_utilisees), "regles_a_valider": a_valider}


def agreger(clients: list[ClientBcm], regles: dict, statuts: dict, dates: DatesBcm, couverture: dict) -> dict:
    """Tableaux 1A, 1B, 4 + exceptions + éléments de contrôle. Fonction pure (aucun accès base)."""
    h_min = couverture.get("historique_classif_min")
    classif_ok = {
        "m1": h_min is not None and h_min <= dates.fin_mois_precedent,
        "fin": h_min is not None and h_min <= dates.fin,
    }
    maj_min = couverture.get("maj_min")
    maj_ok = maj_min is not None and maj_min <= dates.fenetre_maj_debut
    interdit_regle = ("interdit.rattachement",) if regles.get("interdit.rattachement") == "ELEVE" else ()

    populations: dict[str, list[ClientBcm]] = {
        ligne: [c for c in clients if dans_ligne(c, ligne, dates, regles)] for ligne in (*LIGNES_T1, "t4")}
    gel_indetermine = [c for c in clients if c.d_entree and c.d_entree <= dates.fin
                       and statut_actif(c, regles) == "INDETERMINE"]

    raison_ligne: dict[str, str | None] = {ligne: None for ligne in LIGNES_T1}
    if gel_indetermine:
        raison_ligne["cible"] = (f"Statut de gel inconnu pour {len(gel_indetermine)} client(s) ayant un compte "
                                 "ouvert : le nombre d'actifs n'est pas déterminable.")
    if not maj_ok:
        raison_ligne["maj_5ans"] = (
            "Historique des mises à jour disponible depuis le "
            f"{maj_min.strftime('%d/%m/%Y') if maj_min else '— (aucun événement)'} : il ne couvre pas la fenêtre "
            f"débutant le {dates.fenetre_maj_debut.strftime('%d/%m/%Y')}.")

    t1a: dict[str, dict] = {}
    t1b: dict[str, dict] = {}
    repartition: dict[str, dict] = {}
    for ligne in LIGNES_T1:
        pop = populations[ligne]
        raison = raison_ligne[ligne]
        formes: dict[str, int] = {}
        risques: dict[str, int] = {}
        for c in pop:
            f = forme_client(c, regles)
            formes[f] = formes.get(f, 0) + 1
            r = _risque_ligne(c, ligne, regles)
            risques[r] = risques.get(r, 0) + 1
        repartition[ligne] = {"formes": formes, "risques": risques, "total": len(pop)}
        base = REGLES_LIGNE[ligne]
        t1a[ligne] = {
            col: _cellule(None if raison else formes.get(col.upper(), 0),
                          regles_utilisees=(*base, "forme.correspondance", "forme.repli_profil"),
                          statuts=statuts, raison=raison)
            for col in ("pp", "pm", "cj")}
        t1a[ligne]["total"] = _cellule(None if raison else len(pop), regles_utilisees=base, statuts=statuts,
                                       raison=raison)
        cle_classif = "m1" if ligne == "stock_m1" else "fin"
        raison_risque = raison or (None if classif_ok[cle_classif] else (
            "Aucun historique de classification à la date "
            f"({(dates.fin_mois_precedent if cle_classif == 'm1' else dates.fin).strftime('%d/%m/%Y')} ; "
            f"premier événement : {h_min.strftime('%d/%m/%Y') if h_min else '—'})."))
        fiab_risque = None if raison or classif_ok[cle_classif] else "HISTORIQUE_INDISPONIBLE"
        t1b[ligne] = {
            col: _cellule(None if raison_risque else risques.get(col, 0),
                          regles_utilisees=(*base, "risque.date_reference", *interdit_regle), statuts=statuts,
                          raison=raison_risque, fiabilite=fiab_risque)
            for col in ("eleve", "moyen", "faible")}
        t1b[ligne]["total"] = _cellule(None if raison else len(pop), regles_utilisees=base, statuts=statuts,
                                       raison=raison)

    pop4 = populations["t4"]
    risques4: dict[str, int] = {}
    formes4: dict[str, int] = {}
    for c in pop4:
        r = risque_bcm(c.risque_fin, regles)
        risques4[r] = risques4.get(r, 0) + 1
        f = forme_client(c, regles)
        formes4[f] = formes4.get(f, 0) + 1
    total4 = len(pop4)
    raison4 = None if classif_ok["fin"] else (
        f"Aucun historique de classification au {dates.fin.strftime('%d/%m/%Y')} "
        f"(premier événement : {h_min.strftime('%d/%m/%Y') if h_min else '—'}).")
    t4: dict[str, dict] = {}
    for niveau in ("eleve", "moyen", "faible"):
        n = None if raison4 else risques4.get(niveau, 0)
        ratio = None if n is None or not total4 else round(n * 100 / total4, 2)
        regles4 = ("stock.date_entree", "stock.perimetre", "risque.date_reference", *interdit_regle)
        fiab = None if not raison4 else "HISTORIQUE_INDISPONIBLE"
        t4[niveau] = {
            "valeur": _cellule(n, regles_utilisees=regles4, statuts=statuts, raison=raison4, fiabilite=fiab),
            "ratio": _cellule(ratio, regles_utilisees=regles4, statuts=statuts,
                              raison=raison4 or (None if total4 else "Total nul : ratio non calculable."),
                              fiabilite=fiab),
        }
    t4["total"] = {
        "valeur": _cellule(total4, regles_utilisees=("stock.date_entree", "stock.perimetre"), statuts=statuts),
        "ratio": _cellule(100.0 if total4 else None, regles_utilisees=("stock.date_entree", "stock.perimetre"),
                          statuts=statuts, raison=None if total4 else "Total nul : ratio non calculable."),
    }

    racines = [c.racine for c in clients]
    eer_module = set(couverture.get("eer_module_racines") or [])
    eer_orion = {c.racine for c in populations["maj_mois"]}
    exceptions = {
        "forme": {k: v for k, v in formes4.items() if k.startswith("EXC_")},
        "categories_non_rattachees": couverture.get("categories_non_rattachees") or {},
        "risque_fin": {k: risques4.get(k, 0) for k in ("INTERDIT", "NON_CLASSE", "INVALIDE")},
        "risque_m1": {k: repartition["stock_m1"]["risques"].get(k, 0) for k in ("INTERDIT", "NON_CLASSE", "INVALIDE")},
        "gel_indetermine": len(gel_indetermine),
        "sans_date_entree": sum(1 for c in clients if c.d_entree is None),
        "sans_compte_orion": int(couverture.get("sans_compte_orion") or 0),
        "doublons": len(racines) - len(set(racines)),
        "eer_module": {"realises": len(eer_module), "hors_premier_compte": len(eer_module - eer_orion),
                       "premier_compte_sans_dossier": len(eer_orion - eer_module)},
    }
    return {
        "dates": dates.as_dict(),
        "t1a": t1a, "t1b": t1b, "t4": t4,
        "repartition": repartition,
        "t4_risques": risques4, "t4_formes": formes4, "t4_total": total4,
        "exceptions": exceptions,
        "couverture": {
            "classif_m1": classif_ok["m1"], "classif_fin": classif_ok["fin"], "maj": maj_ok,
            "historique_classif_min": h_min.isoformat() if h_min else None,
            "maj_min": maj_min.isoformat() if maj_min else None,
        },
    }


# --------------------------------------------------------------------------- chargement
_SQL_CLIENTS = f"""
WITH cpt AS (
    SELECT racine_client, min(date_ouverture) AS d_entree, bool_or(etat_compte = 'OUVERT') AS a_ouvert
    FROM clientele_comptes GROUP BY racine_client
), h_m1 AS (
    SELECT DISTINCT ON (racine_client) racine_client, nouvelle_classe
    FROM clientele_classif_historique
    WHERE (created_at AT TIME ZONE '{TZ}')::date <= :m1
    ORDER BY racine_client, created_at DESC
), h_fin AS (
    SELECT DISTINCT ON (racine_client) racine_client, nouvelle_classe
    FROM clientele_classif_historique
    WHERE (created_at AT TIME ZONE '{TZ}')::date <= :fin
    ORDER BY racine_client, created_at DESC
), evt AS (
    SELECT racine_client, (created_at AT TIME ZONE '{TZ}')::date AS d FROM clientele_journal
    WHERE :classement AND type_action IN ('MODIFICATION', 'ACCEPTATION') AND champ = 'classification'
    UNION ALL
    SELECT racine_client, (created_at AT TIME ZONE '{TZ}')::date FROM clientele_journal
    WHERE :donnees AND type_action = 'MAJ_DONNEES'
    UNION ALL
    SELECT racine_client, (created_at AT TIME ZONE '{TZ}')::date FROM clientele_classif_historique
    WHERE :classement AND source IN ('MANUEL', 'MANUEL_SURCHARGE')
    UNION ALL
    SELECT racine_client, date_maj_client FROM clientele_kyc
    WHERE :kyc AND date_maj_client IS NOT NULL
), maj AS (
    SELECT racine_client, max(d) AS d_maj FROM evt WHERE d BETWEEN :w_debut AND :fin GROUP BY racine_client
)
SELECT c.racine_client, cpt.d_entree, cpt.a_ouvert, c.categorie_juridique, s.profil_derive, k.statut_gel,
       h_m1.nouvelle_classe AS risque_m1, h_fin.nouvelle_classe AS risque_fin, maj.d_maj
FROM clientele_clients c
JOIN cpt ON cpt.racine_client = c.racine_client
LEFT JOIN clientele_situation s ON s.racine_client = c.racine_client
LEFT JOIN clientele_kyc k ON k.racine_client = c.racine_client
LEFT JOIN h_m1 ON h_m1.racine_client = c.racine_client
LEFT JOIN h_fin ON h_fin.racine_client = c.racine_client
LEFT JOIN maj ON maj.racine_client = c.racine_client
ORDER BY c.racine_client
"""

_SQL_COUVERTURE = f"""
SELECT
    (SELECT min((created_at AT TIME ZONE '{TZ}')::date) FROM clientele_classif_historique) AS h_min,
    (SELECT min(d) FROM (
        SELECT min((created_at AT TIME ZONE '{TZ}')::date) AS d FROM clientele_journal
        WHERE (:classement AND type_action IN ('MODIFICATION', 'ACCEPTATION') AND champ = 'classification')
           OR (:donnees AND type_action = 'MAJ_DONNEES')
        UNION ALL
        SELECT min((created_at AT TIME ZONE '{TZ}')::date) FROM clientele_classif_historique
        WHERE :classement AND source IN ('MANUEL', 'MANUEL_SURCHARGE')
        UNION ALL
        SELECT min(date_maj_client) FROM clientele_kyc WHERE :kyc
    ) x) AS maj_min,
    (SELECT count(*) FROM clientele_clients c
     WHERE NOT EXISTS (SELECT 1 FROM clientele_comptes k WHERE k.racine_client = c.racine_client)) AS sans_compte
"""


async def charger(db: AsyncSession, dates: DatesBcm, regles: dict) -> tuple[list[ClientBcm], dict]:
    evenements = set(regles["maj.evenements"])
    params = {"m1": dates.fin_mois_precedent, "fin": dates.fin, "w_debut": dates.fenetre_maj_debut,
              "classement": "CLASSEMENT_VALIDE" in evenements, "donnees": "DONNEES_VALIDEES" in evenements,
              "kyc": "DATE_MAJ_KYC" in evenements}
    rows = (await db.execute(text(_SQL_CLIENTS), params)).all()
    clients = [ClientBcm(racine=r[0], d_entree=r[1], a_ouvert=bool(r[2]), categorie=r[3], profil=r[4],
                         gel=r[5], risque_m1=r[6], risque_fin=r[7], d_maj=r[8]) for r in rows]
    cov = (await db.execute(text(_SQL_COUVERTURE), params)).one()
    eer = []
    if await db.scalar(text("SELECT to_regclass('public.eer_dossiers') IS NOT NULL")):
        eer = list((await db.scalars(text(
            "SELECT DISTINCT racine_client FROM eer_dossiers WHERE deleted_at IS NULL "
            "AND statut = ANY(:st) AND date_eer BETWEEN :d AND :f AND racine_client ~ '^[0-9]{6}$'"),
            {"st": list(EER_STATUTS_REALISE), "d": dates.debut, "f": dates.fin})).all())
    connues = {_norm(x) for cats in (regles["forme.correspondance"] or {}).values() for x in cats}
    non_rattachees: dict[str, int] = {}
    for c in clients:
        cat = _norm(c.categorie)
        if cat and cat not in connues and c.d_entree and c.d_entree <= dates.fin:
            non_rattachees[cat] = non_rattachees.get(cat, 0) + 1
    couverture = {
        "historique_classif_min": cov[0], "maj_min": cov[1], "sans_compte_orion": int(cov[2] or 0),
        "eer_module_racines": eer,
        "categories_non_rattachees": dict(sorted(non_rattachees.items(), key=lambda kv: -kv[1])),
    }
    return clients, couverture
