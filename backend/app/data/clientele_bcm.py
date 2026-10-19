"""Grille de la Déclaration mensuelle BCM (modèle « Déclaration mensuelle - BEA - août - 2026 »).

Tableaux 1 et 4 : calculés par ``services/clientele/bcm_calcul.py`` selon les règles enregistrées
(``app/data/clientele_bcm_regles.py``). Tableaux 2 et 3 : aucune source dans BEA DIGITAL, cellules
``A_CONFIGURER`` sans nombre. Les chiffres du modèle ne sont jamais repris.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from app.data.clientele_indicateurs import IndicateurStatut, par_code

BCM_GRILLE_VERSION = "2026.10.bcm.3"

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

RISQUE_BCM = ("eleve", "moyen", "faible")
RISQUE_MOTEUR = {"eleve": "ELEVE", "moyen": "MOYEN", "faible": "FAIBLE"}

SRC_STOCK = "clientele_clients ⋈ clientele_comptes (min date_ouverture)"
SRC_RISQUE = "clientele_classif_historique (dernière entrée ≤ date)"
SRC_FORME = "clientele_clients.categorie_juridique (correspondance forme.correspondance)"


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
    source: str | None
    formule: str | None


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
    source: str | None = None,
    formule: str | None = None,
) -> LigneDef:
    return {
        "code": code,
        "libelle": libelle,
        "definition": definition,
        "statut": statut,
        "reserve": reserve,
        "indicateur_total": indicateur_total,
        "cutoff": cutoff,
        "source": source,
        "formule": formule,
    }


def _lignes_t1(par_risque: bool) -> tuple[LigneDef, ...]:
    ventilation = ("niveau de risque à la date (INTERDIT, non classés et invalides hors colonnes)"
                   if par_risque else "catégorie juridique ORION (exceptions hors colonnes)")
    return (
        _ligne(
            "stock_m1",
            "Le nombre à la fin du mois précédent le mois de déclaration",
            "BCM : nbre de client jusqu'au mois précédent le mois de déclaration, actif+inactif. "
            f"Clients entrés en relation au plus tard le dernier jour du mois précédent ; ventilation : {ventilation}.",
            "PRET_SOUS_RESERVE",
            reserve="ORION ne contient que les clients présents dans l'extraction : un client sorti avant "
            "l'extraction n'est pas reconstituable.",
            indicateur_total="cli.stock",
            cutoff="fin_mois_precedent",
            source=f"{SRC_STOCK} ; {SRC_RISQUE if par_risque else SRC_FORME}",
            formule="COUNT(DISTINCT racine) WHERE min(date_ouverture) ≤ fin du mois précédent",
        ),
        _ligne(
            "cible",
            "Nombre cible de clients à mettre à jour pendant le mois de référence",
            "BCM : les clients actifs jusqu'au mois de déclaration. Actif = au moins un compte ORION ouvert "
            "et statut de gel du client « Actif ».",
            "PRET_SOUS_RESERVE",
            reserve="Statut de gel : source = fichier hebdomadaire KYC (clientele_kyc.statut_gel). Statut de "
            "compte = état actuel ORION (pas d'historique de fermeture).",
            indicateur_total="cli.actifs",
            cutoff="date_fin",
            source=f"{SRC_STOCK} ; clientele_comptes.etat_compte ; clientele_kyc.statut_gel",
            formule="COUNT(DISTINCT racine) WHERE entrée ≤ fin du mois AND ∃ compte OUVERT AND gel ∈ actif.valeurs_gel",
        ),
        _ligne(
            "maj_mois",
            "Nombre de clients dont les données ont été mises à jour au cours du mois considéré",
            "BCM : les EER du mois de déclaration. Clients distincts dont le premier compte ORION a été ouvert "
            "pendant le mois (entrée en relation).",
            "PRET_SOUS_RESERVE",
            reserve="Contrôle croisé avec les dossiers du module EER (VALIDE / CLOTURE / ARCHIVE).",
            indicateur_total="eer.maj_periode",
            cutoff="mois",
            source=f"{SRC_STOCK} ; contrôle : eer_dossiers",
            formule="COUNT(DISTINCT racine) WHERE min(date_ouverture) ∈ [1er jour ; dernier jour du mois]",
        ),
        _ligne(
            "maj_5ans",
            "Nombre de clients dont les données ont été mises à jour au cours des cinq dernières années",
            "BCM : tous les clients actifs à partir de (5 ans avant l'année courante). Clients ayant au moins "
            "un événement de mise à jour validé dans la fenêtre (maj.fenetre).",
            "PRET_SOUS_RESERVE",
            reserve="Non calculable tant que l'historique des mises à jour ne couvre pas le début de la fenêtre.",
            indicateur_total="eer.maj_5ans",
            cutoff="date_fin",
            source="clientele_journal (classement, MAJ_DONNEES) ; clientele_classif_historique (MANUEL) ; "
            "clientele_kyc.date_maj_client",
            formule="COUNT(DISTINCT racine) WHERE ∃ événement de mise à jour ∈ [début fenêtre ; fin du mois]",
        ),
    )


TABLEAUX: tuple[TableauDef, ...] = (
    {
        "code": "T1A",
        "titre": "Mise à jour des données clients",
        "sous_titre": "Selon la forme juridique",
        "type": "matrice",
        "colonnes": tuple(_col(code, libelle) for code, libelle in COL_JURIDIQUE),
        "lignes": _lignes_t1(False),
    },
    {
        "code": "T1B",
        "titre": "Mise à jour des données clients",
        "sous_titre": "Selon le degré de risque",
        "type": "matrice",
        "colonnes": tuple(_col(code, libelle) for code, libelle in COL_RISQUE),
        "lignes": _lignes_t1(True),
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
                reserve="Source absente : clientele_alertes = correspondances de listes ORION, pas les alertes "
                "transactionnelles. Registre des opérations inhabituelles à créer.",
                indicateur_total="bcm.t2.extraites",
                cutoff="ytd",
            ),
            _ligne(
                "analysees",
                "Nombre d'opérations analysées à partir de ces opérations",
                "BCM : toutes les opérations en cours d'analyse, clôturées et déclarées.",
                "A_CONFIGURER",
                reserve="Source absente : aucun statut d'analyse d'opération enregistré.",
                indicateur_total="bcm.t2.analysees",
                cutoff="ytd",
            ),
            _ligne(
                "suivi",
                "Nombre d'opérations pour lesquelles l'examen a donné lieu à un suivi continu",
                "BCM : toutes les opérations en cours d'analyse et en attente de réponse.",
                "A_CONFIGURER",
                reserve="Source absente : pas d'état « en attente de réponse ».",
                indicateur_total="bcm.t2.suivi",
                cutoff="date_fin",
            ),
            _ligne(
                "enregistrees",
                "Nombre d'opérations enregistrées à partir de ces processus",
                "Définition BCM non fournie.",
                "A_CONFIGURER",
                reserve="Définition à établir avec la Conformité.",
                indicateur_total="bcm.t2.enregistrees",
                cutoff="mois",
            ),
            _ligne(
                "umef_mois",
                "Nombre de déclarations de soupçon envoyées à l'UMEF (mois)",
                "BCM : nombre de déclarations effectuées durant le mois de déclaration (pas YTD).",
                "A_CONFIGURER",
                reserve="Source absente : aucune déclaration UMEF ni date d'envoi enregistrée.",
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
                "Signalements des employés reçus par le Département de la conformité.",
                "A_CONFIGURER",
                reserve="Source absente : aucun registre de signalements internes.",
                indicateur_total="bcm.t3.suspectes_personnel",
                cutoff="mois",
            ),
            _ligne(
                "analysees",
                "Opérations analysées à partir de ces opérations",
                "Signalements dont l'analyse a commencé.",
                "A_CONFIGURER",
                reserve="Source absente.",
                indicateur_total="bcm.t3.analysees",
                cutoff="mois",
            ),
            _ligne(
                "suivi",
                "Opérations dont l'examen a donné lieu à un suivi continu",
                "Signalements en suivi continu.",
                "A_CONFIGURER",
                reserve="Source absente.",
                indicateur_total="bcm.t3.suivi",
                cutoff="mois",
            ),
            _ligne(
                "enregistrees",
                "Opérations enregistrées à partir de ces processus",
                "Définition BCM non fournie.",
                "A_CONFIGURER",
                reserve="Définition à établir avec la Conformité.",
                indicateur_total="bcm.t3.enregistrees",
                cutoff="mois",
            ),
            _ligne(
                "umef",
                "Déclarations de soupçon UMEF à partir de ces opérations",
                "Déclarations de soupçon envoyées à l'UMEF sur la base de ces signalements.",
                "A_CONFIGURER",
                reserve="Source absente.",
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
        "lignes": tuple(
            _ligne(
                code,
                libelle,
                f"BCM : tous les clients actifs / inactifs, jusqu'au mois de déclaration inclus, niveau {niv}. "
                "Niveau retenu = dernière entrée de l'historique au dernier jour du mois.",
                "PRET_SOUS_RESERVE",
                reserve="INTERDIT, non classés et invalides restent dans le total, hors colonnes, et sont contrôlés.",
                indicateur_total=f"cli.risque.{code}",
                cutoff="date_fin",
                source=f"{SRC_STOCK} ; {SRC_RISQUE}",
                formule=f"COUNT(DISTINCT racine) WHERE entrée ≤ fin du mois AND niveau à la date = {niv.upper()} ; "
                "ratio = nombre / total × 100, arrondi à 2 décimales",
            )
            for code, libelle, niv in (
                ("eleve", "Clients à risque élevé", "élevé"),
                ("moyen", "Clients à risque moyen", "moyen"),
                ("faible", "Clients à faible risque", "faible"),
            )
        ) + (
            _ligne(
                "total",
                "Total clients",
                "BCM : total des clients (actifs et inactifs) à la fin du mois. Inclut INTERDIT et non classés.",
                "PRET_SOUS_RESERVE",
                reserve="Égal par construction à T1 ligne 1 + T1 ligne 3.",
                indicateur_total="cli.stock",
                cutoff="date_fin",
                source=SRC_STOCK,
                formule="COUNT(DISTINCT racine) WHERE min(date_ouverture) ≤ fin du mois",
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
    source = ligne.get("source") or (indic or {}).get("source")
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
        "population": "RACINE" if ligne.get("source") else (indic or {}).get("cle"),
        "source": source,
        "formule": (
            "À CONFIGURER" if ligne["statut"] == "A_CONFIGURER"
            else ligne.get("formule") or (indic or {}).get("formule")),
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
                if tab["code"] == "T4" and col["code"] == "ratio":
                    continue
                out.append(fiche_champ(tab, ligne, col["code"], ligne["indicateur_total"]))
    return out
