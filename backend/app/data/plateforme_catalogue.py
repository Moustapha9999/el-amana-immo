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
            "Immobilisations, amortissements, pièces et contrôles autour d'ORION "
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

# Permissions CORE (tous les départements). `{module}.admin` couvre `{module}.*`.
CORE_PERMISSIONS: list[tuple[str, str, str]] = [
    ("plateforme.users.read", "Consultation des utilisateurs", "plateforme"),
    ("plateforme.users.admin", "Administration des utilisateurs et des accès", "plateforme"),
    ("plateforme.audit.read", "Consultation de l'audit plateforme", "plateforme"),
    ("ged.read", "Consultation GED (réservée)", "ged"),
]

# CORE ADMIN — catalogue seulement. Ne pas lier au rôle immo `administrateur`.
CORE_ADMIN_PERMISSIONS: list[tuple[str, str, str]] = [
    ("core.admin.access", "Accès BEA DIGITAL CORE ADMIN", "core"),
    ("core.admin.users", "Administration des utilisateurs (CORE ADMIN)", "core"),
    ("core.admin.roles", "Administration des rôles (CORE ADMIN)", "core"),
    ("core.admin.permissions", "Administration des permissions (CORE ADMIN)", "core"),
    ("core.admin.departments", "Administration des départements (CORE ADMIN)", "core"),
    ("core.admin.modules", "Administration des modules (CORE ADMIN)", "core"),
    ("core.admin.sessions", "Administration des sessions (CORE ADMIN)", "core"),
    ("core.admin.audit", "Consultation de l'audit (CORE ADMIN)", "core"),
    ("core.admin.security", "Supervision sécurité (CORE ADMIN)", "core"),
    ("core.admin.settings", "Paramètres plateforme (CORE ADMIN)", "core"),
    ("core.admin.backup.view", "Consultation des sauvegardes (CORE ADMIN)", "core"),
    ("core.admin.backup.create", "Création de sauvegardes (CORE ADMIN)", "core"),
    ("core.admin.backup.delete", "Suppression de sauvegardes (CORE ADMIN)", "core"),
    ("core.admin.recovery.view", "Consultation recovery (CORE ADMIN)", "core"),
    ("core.admin.recovery.execute", "Exécution recovery (CORE ADMIN)", "core"),
    ("core.admin.monitoring.view", "Supervision plateforme (CORE ADMIN)", "core"),
    ("core.admin.maintenance.view", "Consultation maintenance (CORE ADMIN)", "core"),
    ("core.admin.maintenance.manage", "Gestion maintenance (CORE ADMIN)", "core"),
    ("core.admin.module_status.view", "Consultation état des modules (CORE ADMIN)", "core"),
    ("core.admin.module_status.manage", "Gestion état des modules (CORE ADMIN)", "core"),
    ("core.admin.versions.view", "Consultation versions modules (CORE ADMIN)", "core"),
    ("core.admin.versions.manage", "Gestion versions modules (CORE ADMIN)", "core"),
]

FUNCTIONAL_PERMISSIONS: list[tuple[str, str, str]] = [
    *CORE_PERMISSIONS,
    *CORE_ADMIN_PERMISSIONS,
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

# Rôles figés Login 2 / module Immobilisations (codes courts = legacy).
# Convention nouveaux modules : "{module}.{profil}" (ex. credit.admin, rh.lecteur).
# Ne jamais réutiliser un code court nu (comptable, administrateur, …) hors Immobilisations.
# Consultation ⊂ les rôles métier (lecture toujours requise pour agir).
RBAC_ROLES: list[tuple[str, str, str]] = [
    ("consultation", "Consultation", "Lecture du module Immobilisations"),
    ("lecture_seule", "Lecture seule", "Alias historique de Consultation"),
    ("creation", "Création", "Création d'immobilisations"),
    ("modification", "Modification", "Modification d'immobilisations"),
    ("validation", "Validation", "Validation / mise en service"),
    ("comptable", "Comptable", "Opérations courantes du module"),
    ("auditeur", "Auditeur", "Consultation et reporting"),
    ("administrateur", "Administration", "Permissions immobilisations + utilisateurs plateforme"),
]

# Codes courts réservés au module Immobilisations (ne pas créer pour Crédit / RH / …).
IMMO_LEGACY_ROLE_CODES = frozenset(code for code, _label, _desc in RBAC_ROLES)

_IMMO_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "immobilisations"
)
_CORE_ADMIN = (
    "plateforme.users.read",
    "plateforme.users.admin",
    "plateforme.audit.read",
    "ged.read",
)

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "consultation": ("immobilisations.read",),
    "lecture_seule": ("immobilisations.read",),
    "creation": ("immobilisations.read", "immobilisations.create"),
    "modification": ("immobilisations.read", "immobilisations.update"),
    "validation": ("immobilisations.read", "immobilisations.validate"),
    "auditeur": ("immobilisations.read", "immobilisations.reporting", "plateforme.audit.read"),
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
    "administrateur": _IMMO_ALL + _CORE_ADMIN,
}

SYSTEM_ROLE_CODES = frozenset(code for code, _label, _desc in RBAC_ROLES)
SYSTEM_PERMISSION_CODES = frozenset(code for code, _label, _module in FUNCTIONAL_PERMISSIONS)
CORE_ADMIN_PERMISSION_CODES = frozenset(code for code, _label, _module in CORE_ADMIN_PERMISSIONS)
IMMO_ADMIN_ROLE_CODE = "administrateur"


def permissions_for_role(role_code: str) -> tuple[str, ...]:
    return ROLE_PERMISSIONS.get(role_code, ())


def module_role_code(module_code: str, profil: str) -> str:
    """Construit le code rôle d’un module.

    Immobilisations → codes courts legacy (`comptable`).
    Autres modules → `{module}.{profil}` (`credit.admin`).
    """
    module = (module_code or "").strip().lower()
    short = (profil or "").strip().lower()
    if not module or not short:
        raise ValueError("module_code et profil sont obligatoires")
    if module == "immobilisations":
        if short.startswith("immobilisations."):
            short = short.split(".", 1)[1]
        return short
    if short.startswith(f"{module}."):
        return short
    if "." in short:
        raise ValueError(f"Profil invalide pour {module} : utiliser un segment sans autre module")
    return f"{module}.{short}"


def role_module_code(role_code: str) -> str | None:
    """Module propriétaire d’un rôle, ou None si code libre non namespacé."""
    code = (role_code or "").strip().lower()
    if not code:
        return None
    if code in IMMO_LEGACY_ROLE_CODES:
        return "immobilisations"
    if "." in code:
        return code.split(".", 1)[0]
    return None


def is_legacy_immo_role(role_code: str) -> bool:
    return (role_code or "").strip().lower() in IMMO_LEGACY_ROLE_CODES
