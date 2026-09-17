"""Catalogue figé des espaces / modules BEA DIGITAL."""

from __future__ import annotations

from typing import TypedDict


class EspaceDef(TypedDict):
    code: str
    label: str
    description: str
    route: str | None
    statut: str
    sort_order: int


class ModuleDef(TypedDict):
    code: str
    espace_code: str
    label: str
    description: str
    entry_path: str | None
    statut: str
    sort_order: int


DEFAULT_ESPACE_CODE = "comptabilite"
DEFAULT_MODULE_CODE = "immobilisations"

PLATEFORME_ESPACES: list[EspaceDef] = [
    {
        "code": "comptabilite",
        "label": "Comptabilité",
        "description": (
            "Immobilisations, amortissements, pièces et contrôles autour d’ORION "
            "— sans remplacer le core banking."
        ),
        "route": "/comptabilite",
        "statut": "actif",
        "sort_order": 1,
    },
    {
        "code": "credit",
        "label": "Crédit",
        "description": "Processus crédit autour d’ORION (dossiers, contrôles, workflows).",
        "route": None,
        "statut": "bientot",
        "sort_order": 2,
    },
    {
        "code": "rh",
        "label": "RH",
        "description": "Processus ressources humaines internes.",
        "route": None,
        "statut": "bientot",
        "sort_order": 3,
    },
    {
        "code": "informatique",
        "label": "Informatique",
        "description": "Demandes, suivi et outils internes DSI.",
        "route": None,
        "statut": "bientot",
        "sort_order": 4,
    },
    {
        "code": "achats",
        "label": "Achats",
        "description": "Demandes d’achat, validations et suivi documentaire.",
        "route": None,
        "statut": "bientot",
        "sort_order": 5,
    },
]

PLATEFORME_MODULES: list[ModuleDef] = [
    {
        "code": "immobilisations",
        "espace_code": "comptabilite",
        "label": "Immobilisations & Amortissements",
        "description": (
            "Parc, dotations, cessions, rebuts, réévaluations, inventaire, écritures, "
            "archives et rapports."
        ),
        "entry_path": "/dashboard",
        "statut": "actif",
        "sort_order": 1,
    },
    {
        "code": "rapprochements",
        "espace_code": "comptabilite",
        "label": "Rapprochements",
        "description": "Rapprochements Excel / ORION et contrôles de cohérence.",
        "entry_path": None,
        "statut": "bientot",
        "sort_order": 2,
    },
    {
        "code": "controles",
        "espace_code": "comptabilite",
        "label": "Contrôles comptables",
        "description": "Contrôles périodiques et anomalies.",
        "entry_path": None,
        "statut": "bientot",
        "sort_order": 3,
    },
    {
        "code": "cloture",
        "espace_code": "comptabilite",
        "label": "Clôture comptable",
        "description": "Préparation et suivi de clôture.",
        "entry_path": None,
        "statut": "bientot",
        "sort_order": 4,
    },
    {
        "code": "reporting-compta",
        "espace_code": "comptabilite",
        "label": "Reporting comptable",
        "description": "Tableaux de bord et exports transverses.",
        "entry_path": None,
        "statut": "bientot",
        "sort_order": 5,
    },
]

FUNCTIONAL_PERMISSIONS: list[tuple[str, str, str]] = [
    ("immobilisations.read", "Consultation immobilisations", "immobilisations"),
    ("immobilisations.create", "Création immobilisations", "immobilisations"),
    ("immobilisations.update", "Modification immobilisations", "immobilisations"),
    ("immobilisations.validate", "Validation immobilisations", "immobilisations"),
    ("immobilisations.delete", "Suppression immobilisations", "immobilisations"),
    ("immobilisations.cession", "Cessions", "immobilisations"),
    ("immobilisations.rebut", "Rebuts", "immobilisations"),
    ("immobilisations.reevaluation", "Réévaluations", "immobilisations"),
    ("immobilisations.amortissement", "Amortissements", "immobilisations"),
    ("immobilisations.reporting", "Reporting immobilisations", "immobilisations"),
    ("immobilisations.admin", "Administration du module", "immobilisations"),
]

# Rôles figés Login 2 / module Immobilisations.
# Consultation ⊂ les rôles métier (lecture toujours requise pour agir).
RBAC_ROLES: list[tuple[str, str, str]] = [
    ("consultation", "Consultation", "Lecture du module Immobilisations"),
    ("lecture_seule", "Lecture seule", "Alias historique de Consultation"),
    ("creation", "Création", "Création d'immobilisations"),
    ("modification", "Modification", "Modification d'immobilisations"),
    ("validation", "Validation", "Validation / mise en service"),
    ("comptable", "Comptable", "Opérations courantes du module"),
    ("auditeur", "Auditeur", "Consultation et reporting"),
    ("administrateur", "Administration", "Toutes les permissions du module"),
]

_IMMO_ALL = tuple(code for code, _label, _module in FUNCTIONAL_PERMISSIONS)

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "consultation": ("immobilisations.read",),
    "lecture_seule": ("immobilisations.read",),
    "creation": ("immobilisations.read", "immobilisations.create"),
    "modification": ("immobilisations.read", "immobilisations.update"),
    "validation": ("immobilisations.read", "immobilisations.validate"),
    "auditeur": ("immobilisations.read", "immobilisations.reporting"),
    "comptable": (
        "immobilisations.read",
        "immobilisations.create",
        "immobilisations.update",
        "immobilisations.cession",
        "immobilisations.rebut",
        "immobilisations.reevaluation",
        "immobilisations.amortissement",
        "immobilisations.reporting",
    ),
    "administrateur": _IMMO_ALL,
}


def permissions_for_role(role_code: str) -> tuple[str, ...]:
    return ROLE_PERMISSIONS.get(role_code, ())
