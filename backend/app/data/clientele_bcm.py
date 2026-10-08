"""Grille de la Déclaration mensuelle BCM (modèle août 2026).

Aucune formule inventée : les cellules ``A_CONFIGURER`` n'ont jamais de nombre.
Les valeurs calculées viennent exclusivement du moteur d'indicateurs.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from app.data.clientele_indicateurs import IndicateurStatut, par_code

BCM_GRILLE_VERSION = "2026.10.bcm.1"

STATUTS_DECLARATION = (
    "BROUILLON",
    "CALCULEE",
    "A_CONTROLER",
    "VALIDEE",
    "CLOTUREE",
    "ARCHIVEE",
)

STATUTS_OUVERTS = ("BROUILLON", "CALCULEE", "A_CONTROLER")
STATUTS_FIGES = ("VALIDEE", "CLOTUREE", "ARCHIVEE")

COL_JURIDIQUE = (
    ("pp", "Personnes physiques"),
    ("pm", "Personnes morales"),
    ("cj", "Constructions juridiques"),
    ("total", "TOTAL"),
)
COL_RISQUE = (
    ("eleve", "Clients à risque élevé"),
    ("moyen", "Clients à risque moyen"),
    ("faible", "Clients à faible risque"),
    ("total", "TOTAL"),
)

# Mapping INTERDIT → colonne BCM : non tranché. INTERDIT n'entre dans aucune colonne.
RISQUE_BCM = ("eleve", "moyen", "faible")
RISQUE_MOTEUR = {"eleve": "ELEVE", "moyen": "MOYEN", "faible": "FAIBLE"}


class ColonneDef(TypedDict):
    code: str
    libelle: str


class LigneDef(TypedDict):
    code: str
    libelle: str
    definition: str
    statut: IndicateurStatut
    reserve: str | None
    indicateur_total: str | None
    cutoff: Literal["fin_mois_precedent", "date_fin", "mois", "ytd"]


class TableauDef(TypedDict):
    code: str
    titre: str
    sous_titre: str
    colonnes: tuple[ColonneDef, ...]
    lignes: tuple[LigneDef, ...]
    type: Literal["matrice", "liste", "classif"]


def _col(code: str, libelle: str) -> ColonneDef:
    return {"code": code, "libelle": libelle}


def _ligne(
    code: str,
    libelle: str,
    definition: str,
    statut: IndicateurStatut,
    *,
    reserve: str | None,
    indicateur_total: str | None,
    cutoff: Literal["fin_mois_precedent", "date_fin", "mois", "ytd"],
) -> LigneDef:
    return {
        "code": code,
        "libelle": libelle,
        "definition": definition,
        "statut": statut,
        "reserve": reserve,
        "indicateur_total": indicateur_total,
        "cutoff": cutoff,
    }


TABLEAUX: tuple[TableauDef, ...] = (
    {
        "code": "T1A",
        "titre": "Mise à jour des données clients",
        "sous_titre": "Selon la forme juridique",
        "type": "matrice",
        "colonnes": tuple(_col(code, libelle) for code, libelle in COL_JURIDIQUE),
        "lignes": (
            _ligne(
                "stock_m1",
                "Le nombre à la fin du mois précédent le mois de déclaration",
                "Nombre de clients jusqu'au mois précédent (actif + inactif) — stock connu à cette date.",
                "PRET_SOUS_RESERVE",
                reserve="Équivaut à tout le stock si la Conformité confirme que « actifs + inactifs » désigne la population connue.",
                indicateur_total="cli.stock",
                cutoff="fin_mois_precedent",
            ),
            _ligne(
                "cible",
                "Nombre cible de clients à mettre à jour pendant le mois de référence",
                "Clients actifs jusqu'au mois de déclaration. Actif n'est pas porté par ORION.",
                "A_CONFIGURER",
                reserve="Ne pas substituer silencieusement OUVERT.",
                indicateur_total="cli.actifs",
                cutoff="date_fin",
            ),
            _ligne(
                "maj_mois",
                "Nombre de clients dont les données ont été mises à jour au cours du mois considéré",
                "EER du mois de déclaration, racine 6 chiffres, statuts VALIDE / CLOTURE (sous réserve).",
                "PRET_SOUS_RESERVE",
                reserve="Statut EER « mis à jour » à valider. MISE_A_JOUR n'est pas ouvert en V1.",
                indicateur_total="eer.maj_periode",
                cutoff="mois",
            ),
            _ligne(
                "maj_5ans",
                "Nombre de clients dont les données ont été mises à jour au cours des cinq dernières années",
                "Clients actifs depuis 5 ans avant l'année courante. Fenêtre et Actif à valider.",
                "A_CONFIGURER",
                reserve="Ne pas hardcoder 5.",
                indicateur_total="eer.maj_5ans",
                cutoff="date_fin",
            ),
        ),
    },
    {
        "code": "T1B",
        "titre": "Mise à jour des données clients",
        "sous_titre": "Selon le degré de risque",
        "type": "matrice",
        "colonnes": tuple(_col(code, libelle) for code, libelle in COL_RISQUE),
        "lignes": (
            _ligne(
                "stock_m1",
                "Le nombre à la fin du mois précédent le mois de déclaration",
                "Même stock que T1A, ventilé par classification historique à fin mois précédent.",
                "PRET_SOUS_RESERVE",
                reserve="INTERDIT n'entre dans aucune colonne BCM (mapping à configurer).",
                indicateur_total="cli.stock",
                cutoff="fin_mois_precedent",
            ),
            _ligne(
                "cible",
                "Nombre cible de clients à mettre à jour pendant le mois de référence",
                "Clients actifs, par degré de risque. Actif à valider.",
                "A_CONFIGURER",
                reserve=None,
                indicateur_total="cli.actifs",
                cutoff="date_fin",
            ),
            _ligne(
                "maj_mois",
                "Nombre de clients dont les données ont été mises à jour au cours du mois considéré",
                "EER du mois, ventilés par classification à la date de fin du mois de déclaration.",
                "PRET_SOUS_RESERVE",
                reserve="Classification à date_fin, pas le niveau courant.",
                indicateur_total="eer.maj_periode",
                cutoff="mois",
            ),
            _ligne(
                "maj_5ans",
                "Nombre de clients dont les données ont été mises à jour au cours des cinq dernières années",
                "Fenêtre et Actif à valider.",
                "A_CONFIGURER",
                reserve=None,
                indicateur_total="eer.maj_5ans",
                cutoff="date_fin",
            ),
        ),
    },
    {
        "code": "T2",
        "titre": "Opérations inhabituelles",
        "sous_titre": "Le nombre à la fin du mois de déclaration",
        "type": "liste",
        "colonnes": (_col("valeur", "Le nombre à la fin du mois de déclaration"),),
        "lignes": (
            _ligne(
                "extraites",
                "Nombre d'opérations inhabituelles extraites du système",
                "Alertes du début d'année jusqu'à la fin du mois de déclaration (YTD).",
                "PRET_SOUS_RESERVE",
                reserve="Quels statuts = « déclarées » ?",
                indicateur_total="bcm.t2.extraites",
                cutoff="ytd",
            ),
            _ligne(
                "analysees",
                "Nombre d'opérations analysées à partir de ces opérations",
                "En cours d'analyse, clôturées et déclarées — mapping de statuts provisoire.",
                "PRET_SOUS_RESERVE",
                reserve=None,
                indicateur_total="bcm.t2.analysees",
                cutoff="ytd",
            ),
            _ligne(
                "suivi",
                "Nombre d'opérations pour lesquelles l'examen a donné lieu à un suivi continu",
                "En cours d'analyse et en attente de réponse — mapping provisoire.",
                "PRET_SOUS_RESERVE",
                reserve="Pas d'état « attente réponse » dédié aujourd'hui.",
                indicateur_total="bcm.t2.suivi",
                cutoff="date_fin",
            ),
            _ligne(
                "enregistrees",
                "Nombre d'opérations enregistrées à partir de ces processus",
                "Définition BCM non fournie.",
                "A_CONFIGURER",
                reserve="Ne pas produire de chiffre.",
                indicateur_total="bcm.t2.enregistrees",
                cutoff="mois",
            ),
            _ligne(
                "umef_mois",
                "Nombre de déclarations de soupçon envoyées à l'UMEF (mois)",
                "Déclarations effectuées durant le mois — pas YTD. Pas d'entité UMEF en base.",
                "A_CONFIGURER",
                reserve=None,
                indicateur_total="bcm.t2.umef_mois",
                cutoff="mois",
            ),
        ),
    },
    {
        "code": "T3",
        "titre": "Opérations suspectes",
        "sous_titre": "Le nombre à la fin du mois de déclaration",
        "type": "liste",
        "colonnes": (_col("valeur", "Le nombre à la fin du mois de déclaration"),),
        "lignes": (
            _ligne(
                "recues",
                "Transactions suspectes reçues du personnel",
                "Aucune formule fournie.",
                "A_CONFIGURER",
                reserve="Les 5 lignes du Tableau 3 restent À CONFIGURER.",
                indicateur_total="bcm.t3.suspectes_personnel",
                cutoff="mois",
            ),
            _ligne(
                "analysees",
                "Opérations analysées à partir de ces opérations",
                "Aucune formule fournie.",
                "A_CONFIGURER",
                reserve=None,
                indicateur_total="bcm.t3.analysees",
                cutoff="mois",
            ),
            _ligne(
                "suivi",
                "Opérations dont l'examen a donné lieu à un suivi continu",
                "Aucune formule fournie.",
                "A_CONFIGURER",
                reserve=None,
                indicateur_total="bcm.t3.suivi",
                cutoff="mois",
            ),
            _ligne(
                "enregistrees",
                "Opérations enregistrées à partir de ces processus",
                "Aucune formule fournie.",
                "A_CONFIGURER",
                reserve=None,
                indicateur_total="bcm.t3.enregistrees",
                cutoff="mois",
            ),
            _ligne(
                "umef",
                "Déclarations de soupçon UMEF à partir de ces opérations",
                "Aucune formule fournie.",
                "A_CONFIGURER",
                reserve=None,
                indicateur_total="bcm.t3.umef",
                cutoff="mois",
            ),
        ),
    },
    {
        "code": "T4",
        "titre": "Classification des clients selon les risques BC/FT",
        "sous_titre": "Le nombre à la fin du mois de déclaration",
        "type": "classif",
        "colonnes": (
            _col("valeur", "Le nombre à la fin du mois de déclaration"),
            _col("ratio", "Ratio %"),
        ),
        "lignes": (
            _ligne(
                "eleve",
                "Clients à risque élevé",
                "Stock connu jusqu'au mois de déclaration inclus, classification historique ÉLEVÉ.",
                "PRET_SOUS_RESERVE",
                reserve="INTERDIT non mappé.",
                indicateur_total="cli.risque.eleve",
                cutoff="date_fin",
            ),
            _ligne(
                "moyen",
                "Clients à risque moyen",
                "Idem, niveau MOYEN.",
                "PRET_SOUS_RESERVE",
                reserve=None,
                indicateur_total="cli.risque.moyen",
                cutoff="date_fin",
            ),
            _ligne(
                "faible",
                "Clients à faible risque",
                "Idem, niveau FAIBLE.",
                "PRET_SOUS_RESERVE",
                reserve="Les non classés ne sont pas du FAIBLE.",
                indicateur_total="cli.risque.faible",
                cutoff="date_fin",
            ),
            _ligne(
                "total",
                "Total clients",
                "Stock connu à la date de fin (COUNT DISTINCT racine). Contrôle : E+M+F vs total.",
                "PRET_SOUS_RESERVE",
                reserve="L'identité T4.total − T1.stock_m1 = EER du mois est documentée, pas une règle figée.",
                indicateur_total="cli.stock",
                cutoff="date_fin",
            ),
        ),
    },
)


def tableaux() -> tuple[TableauDef, ...]:
    return TABLEAUX


def fiche_champ(
    tableau: TableauDef,
    ligne: LigneDef,
    colonne_code: str,
    indicateur: str | None,
) -> dict:
    """Fiche de correspondance BCM → BEA-DIGITAL. Aucune formule inventée."""
    indic = par_code(indicateur) if indicateur else None
    source = (indic or {}).get("source")
    if not source:
        source = "ABSENT" if ligne["statut"] == "A_CONFIGURER" else None
    col = next((c for c in tableau["colonnes"] if c["code"] == colonne_code), None)
    return {
        "libelle_officiel": ligne["libelle"],
        "tableau": tableau["code"],
        "ligne": ligne["code"],
        "colonne": colonne_code,
        "colonne_libelle": col["libelle"] if col else colonne_code,
        "definition": ligne["definition"],
        "periode": ligne["cutoff"],
        "population": (indic or {}).get("cle"),
        "source": source,
        "formule": (indic or {}).get("formule") or (
            "À CONFIGURER" if ligne["statut"] == "A_CONFIGURER" else None),
        "classification_utilisee": (
            "historique à la date de cutoff"
            if source and "classif" in source else "non"),
        "eer_utilise": bool(source and "eer" in source),
        "historique_utilise": bool(source and "historique" in source),
        "validation_metier": ligne["statut"],
        "reserve": ligne["reserve"],
    }


def fiches() -> list[dict]:
    out: list[dict] = []
    for tab in TABLEAUX:
        for ligne in tab["lignes"]:
            for col in tab["colonnes"]:
                indic = ligne["indicateur_total"]
                if tab["code"] == "T1A" and col["code"] == "cj":
                    indic = "cli.construction_juridique"
                elif tab["code"] == "T1A" and col["code"] == "pp":
                    indic = "cli.pp" if ligne["code"] == "stock_m1" else ligne["indicateur_total"]
                elif tab["code"] == "T1A" and col["code"] == "pm":
                    indic = "cli.pm" if ligne["code"] == "stock_m1" else ligne["indicateur_total"]
                elif tab["code"] == "T1B" and col["code"] in RISQUE_BCM:
                    indic = f"cli.risque.{col['code']}" if ligne["code"] == "stock_m1" else ligne["indicateur_total"]
                elif tab["code"] == "T4" and col["code"] == "ratio":
                    continue
                out.append(fiche_champ(tab, ligne, col["code"], indic))
    return out
