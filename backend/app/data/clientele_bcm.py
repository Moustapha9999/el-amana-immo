"""Grille de la Déclaration mensuelle BCM (modèle août 2026).

Aucune formule inventée : les cellules ``A_CONFIGURER`` n'ont jamais de nombre.
Les valeurs calculées viennent exclusivement du moteur d'indicateurs.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from app.data.clientele_indicateurs import IndicateurStatut, par_code

BCM_GRILLE_VERSION = "2026.10.bcm.2"

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
                "BCM : nbre de client jusqu'au mois précédent le mois de déclaration, actif+inactif. "
                "Photographie à la clôture, pas le stock vivant.",
                "PRET_SOUS_RESERVE",
                reserve="Reconstituable seulement si une extraction ORION (ou historique d'existence) couvre la date. "
                "premiere_extraction = date d'import BEA DIGITAL, pas l'entrée en relation.",
                indicateur_total="cli.stock",
                cutoff="fin_mois_precedent",
            ),
            _ligne(
                "cible",
                "Nombre cible de clients à mettre à jour pendant le mois de référence",
                "BCM : les clients actifs jusqu'au mois de déclaration. Actif n'est pas porté par ORION.",
                "A_CONFIGURER",
                reserve="Ne pas substituer silencieusement OUVERT. Ne pas remplir avec le stock T1 ligne 1.",
                indicateur_total="cli.actifs",
                cutoff="date_fin",
            ),
            _ligne(
                "maj_mois",
                "Nombre de clients dont les données ont été mises à jour au cours du mois considéré",
                "BCM : les EER du mois de déclaration. Ne pas remplacer silencieusement par les ouvertures de compte.",
                "PRET_SOUS_RESERVE",
                reserve="Source : eer_dossiers. En août 2026 le fichier BCM (292) coincide avec les ouvertures de "
                "compte ORION (259 PP + 33 PM) : arbitrage Conformité requis.",
                indicateur_total="eer.maj_periode",
                cutoff="mois",
            ),
            _ligne(
                "maj_5ans",
                "Nombre de clients dont les données ont été mises à jour au cours des cinq dernières années",
                "BCM : tous les clients actifs à partir de (5 ans avant l'année courante). "
                "Ce n'est pas une date de mise à jour KYC tant que la Conformité ne l'a pas confirmé.",
                "A_CONFIGURER",
                reserve="Le fichier août 2026 porte 6 883 PM ici contre 5 692 au stock : incohérence interne du "
                "classeur si la ligne est un sous-ensemble. Ne pas hardcoder 5 ni copier 6 883.",
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
                "BCM : nbre de client jusqu'au mois précédent, actif+inactif, par degré de risque. "
                "Niveau connu à cette date, pas le SCORE d'une date ultérieure.",
                "PRET_SOUS_RESERVE",
                reserve="INTERDIT et non classés hors colonnes. Historique SCORE postérieur à la clôture = "
                "photographie impossible.",
                indicateur_total="cli.stock",
                cutoff="fin_mois_precedent",
            ),
            _ligne(
                "cible",
                "Nombre cible de clients à mettre à jour pendant le mois de référence",
                "BCM : les clients actifs jusqu'au mois de déclaration, par degré de risque.",
                "A_CONFIGURER",
                reserve="Même trou Actif que T1A ligne 2.",
                indicateur_total="cli.actifs",
                cutoff="date_fin",
            ),
            _ligne(
                "maj_mois",
                "Nombre de clients dont les données ont été mises à jour au cours du mois considéré",
                "BCM : les EER du mois de déclaration, par degré de risque.",
                "PRET_SOUS_RESERVE",
                reserve="Ne pas attribuer le SCORE d'octobre aux EER d'août.",
                indicateur_total="eer.maj_periode",
                cutoff="mois",
            ),
            _ligne(
                "maj_5ans",
                "Nombre de clients dont les données ont été mises à jour au cours des cinq dernières années",
                "BCM : tous les clients actifs à partir de (5 ans avant l'année courante), par degré de risque.",
                "A_CONFIGURER",
                reserve="Même définition que T1A ligne 4. Ne pas assimiler à une MAJ KYC.",
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
                "BCM : Alertes déclarées du début d'année jusqu'au mois de déclaration.",
                "A_CONFIGURER",
                reserve="clientele_alertes = correspondances de listes ORION, pas le système d'alertes déclarées "
                "du fichier (2 492 en août 2026). Ne pas assimiler.",
                indicateur_total="bcm.t2.extraites",
                cutoff="ytd",
            ),
            _ligne(
                "analysees",
                "Nombre d'opérations analysées à partir de ces opérations",
                "BCM : toutes les opérations en cours d'analyse, clôturées et déclarées.",
                "A_CONFIGURER",
                reserve="Pas de module d'opérations inhabituelles. Mapping de statuts d'alertes de listes interdit.",
                indicateur_total="bcm.t2.analysees",
                cutoff="ytd",
            ),
            _ligne(
                "suivi",
                "Nombre d'opérations pour lesquelles l'examen a donné lieu à un suivi continu",
                "BCM : toutes les opérations en cours d'analyse et en attente de réponse.",
                "A_CONFIGURER",
                reserve="Pas d'état « attente de réponse ». Ne pas compter les alertes NOUVELLE de listes.",
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
                "BCM : nombre de déclarations effectuées durant le mois de déclaration (pas YTD).",
                "A_CONFIGURER",
                reserve="Pas d'entité UMEF ni de date d'envoi. Le fichier août porte 2 : ne pas copier ce chiffre.",
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
                "BCM : tous les clients actifs / inactifs, jusqu'au mois de déclaration inclus, niveau élevé. "
                "Niveau à la date de clôture, pas le SCORE ultérieur.",
                "PRET_SOUS_RESERVE",
                reserve="INTERDIT non mappé. Photographie impossible sans historique à la clôture.",
                indicateur_total="cli.risque.eleve",
                cutoff="date_fin",
            ),
            _ligne(
                "moyen",
                "Clients à risque moyen",
                "BCM : tous les clients actifs / inactifs, jusqu'au mois de déclaration inclus, niveau moyen.",
                "PRET_SOUS_RESERVE",
                reserve="Même contrainte d'historique que T4 élevé.",
                indicateur_total="cli.risque.moyen",
                cutoff="date_fin",
            ),
            _ligne(
                "faible",
                "Clients à faible risque",
                "BCM : tous les clients actifs / inactifs, jusqu'au mois de déclaration inclus, niveau faible.",
                "PRET_SOUS_RESERVE",
                reserve="Les non classés ne sont pas du FAIBLE. SCORE octobre ≠ faible août (38 685 dans le fichier).",
                indicateur_total="cli.risque.faible",
                cutoff="date_fin",
            ),
            _ligne(
                "total",
                "Total clients",
                "BCM : total des clients (actifs et inactifs) à la clôture du mois. COUNT DISTINCT racine. "
                "Les non classés restent dans ce total.",
                "PRET_SOUS_RESERVE",
                reserve="T4 − T1 = 292 dans le fichier août : égal aux EER déclarés et aux ouvertures de compte, "
                "pas une règle à imposer.",
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
        "formule": (
            "À CONFIGURER" if ligne["statut"] == "A_CONFIGURER"
            else (indic or {}).get("formule")),
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
