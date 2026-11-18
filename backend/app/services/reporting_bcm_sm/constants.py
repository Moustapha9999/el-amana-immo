"""Constantes métier Reporting BCM SM — alignées T2 (pas de règles inventées)."""

from __future__ import annotations

MODULE_CODE = "reporting-bcm-sm"
ESPACE_CODE = "comptabilite"
BANK_CODE_DEFAULT = "BEA"
ENGINE_VERSION = "0.2.0-sm"

# Cycle de vie SM / campagne technique (T2 §4.2) — UI métier = « Situation Mensuelle »
CAMPAIGN_STATUSES = (
    "BROUILLON",
    "IMPORTS",
    "RAPPROCHEE",
    "PARAMETREE",
    "CALCULEE",
    "A_CONTROLER",
    "APPROUVEE",
    "CLOTUREE",
    "ROUVERTE",
)
# Période encore « active » (création / unicité) — hors clôture/archivage.
OPEN_CAMPAIGN_STATUSES = tuple(s for s in CAMPAIGN_STATUSES if s not in ("CLOTUREE",))

# Classification KPI dashboard (T3.4-C) — CALCULEE ≠ ouverte.
SM_OPEN_STATUSES = ("BROUILLON", "IMPORTS", "RAPPROCHEE", "PARAMETREE", "ROUVERTE")
SM_IN_PROGRESS_STATUSES = ("IMPORTS", "RAPPROCHEE", "PARAMETREE", "ROUVERTE")
SM_PENDING_VALIDATION_STATUSES = ("A_CONTROLER",)
SM_CALCULATED_STATUSES = ("CALCULEE",)
SM_APPROVED_STATUSES = ("APPROUVEE",)
SM_CLOSED_STATUSES = ("CLOTUREE",)  # archivage métier = clôture conservatrice

# Imports — T3.4-A2 : BAL DET = source unique du workflow normal.
# BAL_COND conservé en lecture historique uniquement (plus d'upload).
IMPORT_FILE_TYPES = ("BAL_DET", "BAL_COND")
IMPORT_FILE_TYPES_ACTIVE = ("BAL_DET",)
IMPORT_FILE_TYPES_DEPRECATED = ("BAL_COND",)
IMPORT_STATUSES = (
    "UPLOADED",
    "ANALYZED",
    "VALIDATED",
    "REJECTED",
    "SUPERSEDED",
)
# Non confirmés : suppression physique autorisée (tests / analyses abandonnées).
IMPORT_STATUSES_UNCONFIRMED = ("UPLOADED", "ANALYZED", "REJECTED")
# Confirmés : traçabilité — pas de DELETE, remplacement (SUPERSEDED) ou archivage SM.
IMPORT_STATUSES_CONFIRMED = ("VALIDATED", "SUPERSEDED")

# Références documentaires T1 (oct. 2026) — pas des constantes de calcul.
HIST_T1_COND_CLASSES_1_8 = "2873223"
HIST_T1_DET_CLASSES_1_8_APPROX = "2873238.05"
HIST_T1_DET_COND_GAP_APPROX = "15.05"

# Mapping lifecycle — un seul champ (T2 §4.4)
MAPPING_LIFECYCLES = ("A_VALIDER", "ACTIVE", "REJECTED", "SUPERSEDED")

# Orientations NCG → cellules SM (catalogue central unique, activation manuelle).
NCG_ORIENTATION_STATUSES = (
    "A_ORIENTER",
    "EN_ATTENTE_VALIDATION",
    "VALIDE_ACTIF",
    "REJETE",
    "DESACTIVE",
)
NCG_ORIENTATION_OPERATIONS = (
    "ADD_DEBIT",
    "ADD_CREDIT",
    "SUB_DEBIT",
    "SUB_CREDIT",
)
NCG_ORIENTATION_CURRENCIES = ("ALL", "LOCAL", "FX")
NCG_ORIENTATION_RESIDENCES = ("RESIDENTS", "NON_RESIDENTS", "ALL")
NCG_ORIENTATION_SHEETS = ("ETAT_A", "ETAT_B")

# Bases de montant. D15 validée (Cellules SM) : DEBIT / CREDIT / NET / FX.
# SD/SC NATURAL conservés pour l'ancien seed SCD A_VALIDER (non utilisé au calcul).
AMOUNT_BASES = ("D", "C", "SD", "SC", "SIGNED")
SIGNED_BALANCE_MODES = ("NATURAL", "RAW_POSITIVE_LEG", "CUSTOM")

# Paramètres mensuels (T1 / T2 §10) — jamais reconduits
PARAMETER_CODES = (
    "caisse_devises",
    "publics_mru",
    "publics_dev",
    "prives_dev",
    "projets",
    "dat_public",
    "amort_frais_immo",
    "cautions_dev",
)

PARAMETER_VALUE_STATUSES = (
    "EN_ATTENTE",
    "SAISI",
    "CALCULE",
    "VALIDE",
    "REJETE",
)

# Statuts cellule (T2 §6)
CELL_VALUE_STATUSES = (
    "AUTOMATIQUE",
    "A_CONFIRMER",
    "CORRECTION_MANUELLE",
    "ZERO_CONFIRME",
    "ZERO_MANUEL",
    "NON_RENSEIGNE",
    "EN_ATTENTE_DECISION",
    "BLOQUE_PAR_ECART",
    "NON_MAPPEE",
    "PROVISOIRE",
    "A_AJUSTER",
    "SAISIE_MANUELLE",
)

# ECART — jamais de constante 2873223 dans le moteur
ECART_STATES = ("DESACTIVE", "EN_ATTENTE_D02", "ACTIF")

# Contrôles
CONTROL_SEVERITIES = ("INFO", "WARNING", "BLOCKING")
CONTROL_CATEGORIES = ("A", "B", "C", "D")
CONTROL_RESOLUTION_STATES = (
    "OPEN",
    "IN_PROGRESS",
    "RESOLVED",
    "STILL_BLOCKING",
    "PENDING_DECISION",
    "OK",
)
CONTROL_RUN_RESULTS = (
    "OK",
    "WARNINGS",
    "INCOMPLETE",
    "DECISIONS_PENDING",
    "BLOCKING",
    "FAILED",
)

# Workflow events
VALIDATION_ACTIONS = (
    "SUBMIT_CONTROL",
    "CONTROL_OK",
    "CONTROL_REJECT",
    "APPROVE",
    "REJECT_APPROVAL",
    "REOPEN",
    "CLOSE",
)

# Permissions
PERM_VIEW = "reporting-bcm-sm.view"
PERM_PREPARE = "reporting-bcm-sm.prepare"
PERM_IMPORT = "reporting-bcm-sm.import"
PERM_PARAMS = "reporting-bcm-sm.parameters.write"
PERM_MAP_PROPOSE = "reporting-bcm-sm.mapping.propose"
PERM_MAP_VALIDATE = "reporting-bcm-sm.mapping.validate"
PERM_CONFIRM = "reporting-bcm-sm.confirm"
PERM_CORRECT = "reporting-bcm-sm.correct"
PERM_CONTROL = "reporting-bcm-sm.control"
PERM_APPROVE = "reporting-bcm-sm.approve"
PERM_EXPORT = "reporting-bcm-sm.export"
PERM_REOPEN = "reporting-bcm-sm.reopen"
PERM_ADMIN = "reporting-bcm-sm.admin"
