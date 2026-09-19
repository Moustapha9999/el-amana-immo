"""Périmètres de backup / recovery par module — tables exclusives vs dépendances partagées."""

from __future__ import annotations

from typing import TypedDict


class ModuleBackupScope(TypedDict):
    exclusive_tables: list[str]
    shared_dependencies: list[str]
    uploads_subdir: str | None
    label: str


# CORE / auth / audit / notifications / GED / plateforme_* ne sont jamais
# écrasés par un recovery MODULE ou DÉPARTEMENT.
_SHARED = [
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "agences",
    "directions",
    "departements",
    "centres_cout",
    "fournisseurs",
    "journaux",
    "comptes_plan_comptable",
    "plateforme_espaces",
    "plateforme_modules",
    "user_espace_acces",
    "user_module_acces",
    "auth_sessions",
    "auth_login_attempts",
    "audit_logs",
    "notifications",
    "ged_documents",
    "platform_backups",
    "platform_restores",
    "platform_module_versions",
    "platform_ops_flags",
]

MODULE_BACKUP_SCOPES: dict[str, ModuleBackupScope] = {
    "immobilisations": {
        "label": "Immobilisations & Amortissements",
        "uploads_subdir": "immobilisations",
        "exclusive_tables": [
            "categories_immobilisation",
            "exercices_comptables",
            "periodes_amortissement",
            "parametrage_amortissement",
            "parametrage_ecriture",
            "immobilisations",
            "pieces_jointes",
            "amortissements",
            "cessions",
            "rebuts",
            "reevaluations",
            "ajustements",
            "ecritures_comptables",
            "soldes_ouverture_immobilisations",
            "soldes_compte_orion",
            "inventaire_scans",
            "archive_dossiers",
            "archive_fichiers",
            "archive_lignes",
        ],
        "shared_dependencies": list(_SHARED),
    },
}

ESPACE_MODULES: dict[str, list[str]] = {
    "comptabilite": ["immobilisations"],
}


def scope_for_module(module_code: str) -> ModuleBackupScope | None:
    return MODULE_BACKUP_SCOPES.get(module_code)


def modules_for_espace(espace_code: str) -> list[str]:
    return list(ESPACE_MODULES.get(espace_code, []))


def merge_scopes(module_codes: list[str]) -> ModuleBackupScope | None:
    scopes = [MODULE_BACKUP_SCOPES[c] for c in module_codes if c in MODULE_BACKUP_SCOPES]
    if not scopes:
        return None
    tables: list[str] = []
    shared: list[str] = []
    for s in scopes:
        for t in s["exclusive_tables"]:
            if t not in tables:
                tables.append(t)
        for d in s["shared_dependencies"]:
            if d not in shared:
                shared.append(d)
    subdirs = [s["uploads_subdir"] for s in scopes if s.get("uploads_subdir")]
    return {
        "label": ", ".join(s["label"] for s in scopes),
        "exclusive_tables": tables,
        "shared_dependencies": shared,
        "uploads_subdir": subdirs[0] if len(subdirs) == 1 else None,
    }
