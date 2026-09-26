"""Périmètres de backup / recovery par module — tables exclusives vs dépendances partagées.

Pour un nouveau module :
1. Ajouter une entrée dans MODULE_BACKUP_SCOPES (tables exclusives + uploads_subdir).
2. Lier le code module à son espace dans ESPACE_MODULES.
3. Ne jamais y mettre users / roles / plateforme_* / ged_documents / audit
   (restent dans SHARED_CORE_TABLES).
"""

from __future__ import annotations

from typing import TypedDict


class ModuleBackupScope(TypedDict):
    exclusive_tables: list[str]
    shared_dependencies: list[str]
    uploads_subdir: str | None
    label: str


# CORE / auth / audit / notifications / GED / plateforme_* ne sont jamais
# écrasés par un recovery MODULE ou DÉPARTEMENT.
SHARED_CORE_TABLES: list[str] = [
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

_SHARED = SHARED_CORE_TABLES


def make_module_scope(
    *,
    label: str,
    exclusive_tables: list[str],
    uploads_subdir: str | None = None,
    extra_shared: list[str] | None = None,
) -> ModuleBackupScope:
    """Factory pour enregistrer un nouveau module sans recopier le CORE."""
    shared = list(SHARED_CORE_TABLES)
    for name in extra_shared or []:
        if name not in shared:
            shared.append(name)
    return {
        "label": label,
        "uploads_subdir": uploads_subdir,
        "exclusive_tables": list(exclusive_tables),
        "shared_dependencies": shared,
    }


MODULE_BACKUP_SCOPES: dict[str, ModuleBackupScope] = {
    "immobilisations": make_module_scope(
        label="Immobilisations & Amortissements",
        uploads_subdir="immobilisations",
        exclusive_tables=[
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
    ),
    "stock-fournitures": make_module_scope(
        label="Stock & Fournitures",
        uploads_subdir="stock-fournitures",
        exclusive_tables=[
            "mg_article_familles",
            "mg_articles",
            "mg_stock_mouvements",
            "mg_demandes_fourniture",
            "mg_demande_fourniture_lignes",
            "mg_inventaires",
            "mg_inventaire_lignes",
            "mg_stock_parametres",
            "mg_stock_periodes",
            "mg_stock_soldes",
        ],
    ),
    "achats-appro": make_module_scope(
        label="Achats & Approvisionnements",
        uploads_subdir="achats-appro",
        exclusive_tables=["mg_bons_commande", "mg_bc_lignes"],
    ),
    "notes-frais": make_module_scope(
        label="Notes de Frais",
        uploads_subdir="notes-frais",
        exclusive_tables=[
            "mg_notes_frais",
            "mg_note_frais_lignes",
            "mg_note_frais_categories",
            "mg_note_frais_historique",
            "mg_note_frais_parametres",
        ],
    ),
    "contrats-echeances": make_module_scope(
        label="Contrats & Échéances",
        uploads_subdir="contrats-echeances",
        exclusive_tables=[
            "mg_contrats",
            "mg_contrat_echeances",
            "mg_contrat_paiements",
            "mg_contrat_historique",
            "mg_contrat_types",
            "mg_contrat_parametres",
        ],
    ),
    "archives-mg": make_module_scope(
        label="Archives MG",
        uploads_subdir="archives-mg",
        exclusive_tables=[],
    ),
}

ESPACE_MODULES: dict[str, list[str]] = {
    "comptabilite": ["immobilisations"],
    "credit": ["credit"],
    "rh": ["rh"],
    "informatique": ["tickets-si"],
    "achats": ["demandes-achat"],
    "moyens-generaux": [
        "stock-fournitures",
        "achats-appro",
        "notes-frais",
        "contrats-echeances",
        "archives-mg",
    ],
}


def register_module_scope(module_code: str, scope: ModuleBackupScope) -> None:
    """Enregistrement dynamique (tests / plugins) — préfère MODULE_BACKUP_SCOPES en prod."""
    MODULE_BACKUP_SCOPES[module_code] = scope


def register_espace_modules(espace_code: str, module_codes: list[str]) -> None:
    ESPACE_MODULES[espace_code] = list(module_codes)


def scope_for_module(module_code: str) -> ModuleBackupScope | None:
    return MODULE_BACKUP_SCOPES.get(module_code)


def modules_for_espace(espace_code: str) -> list[str]:
    return list(ESPACE_MODULES.get(espace_code, []))


def known_module_codes() -> list[str]:
    return sorted(MODULE_BACKUP_SCOPES.keys())


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
