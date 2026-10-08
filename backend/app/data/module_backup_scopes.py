"""Périmètres de backup / recovery par module — tables exclusives vs dépendances partagées.

Pour un nouveau module :
1. Ajouter une entrée dans MODULE_BACKUP_SCOPES (tables exclusives et/ou préfixes,
   sous-dossiers uploads, codes GED).
2. Le rattachement module → département est lu dans ``plateforme_modules``
   (CORE ADMIN). ESPACE_MODULES ne sert que de repli hors base.
3. Ne jamais y mettre users / roles / plateforme_* / ged_documents / audit
   (restent dans SHARED_CORE_TABLES).

Les fichiers GED d'un module vivent dans ``storage/ged/{code GED}`` et ses
lignes dans ``ged_documents`` (filtrées par ``module_code``) : elles sont
sauvegardées / restaurées ligne à ligne, sans jamais écraser la GED des autres
modules.
"""

from __future__ import annotations

from typing import TypedDict


class ModuleBackupScope(TypedDict):
    exclusive_tables: list[str]
    table_prefixes: list[str]
    shared_dependencies: list[str]
    uploads_subdir: str | None
    uploads_subdirs: list[str]
    ged_module_codes: list[str] | None
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
    "plan_comptable",
    "comptes_plan_comptable",
    "plateforme_espaces",
    "plateforme_domaines",
    "plateforme_modules",
    "user_espace_acces",
    "user_module_acces",
    "auth_sessions",
    "auth_login_attempts",
    "password_history",
    "password_reset_jtis",
    "security_incidents",
    "audit_logs",
    "api_error_events",
    "notifications",
    "ged_documents",
    "platform_backups",
    "platform_restores",
    "platform_module_versions",
    "platform_ops_flags",
    "core_query_logs",
    "core_query_favorites",
    "alembic_version",
]

# Recovery GLOBAL : journaux et état ops jamais réécrits (la trace de la
# restauration elle-même et les sauvegardes postérieures doivent survivre).
GLOBAL_RESTORE_JOURNAL_TABLES: list[str] = [
    "alembic_version",
    "audit_logs",
    "api_error_events",
    "notifications",
    "platform_backups",
    "platform_restores",
    "platform_ops_flags",
    "platform_module_versions",
    "auth_sessions",
    "auth_login_attempts",
    "password_reset_jtis",
    "security_incidents",
    "core_query_logs",
]

# Plan sécurité : restauré en GLOBAL uniquement sur option explicite
# (un ancien snapshot réactiverait des comptes désactivés / anciens mots de passe).
SECURITY_PLANE_TABLES: list[str] = [
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "user_espace_acces",
    "user_module_acces",
    "password_history",
    "plateforme_espaces",
    "plateforme_domaines",
    "plateforme_modules",
]

_SHARED = SHARED_CORE_TABLES


def make_module_scope(
    *,
    label: str,
    exclusive_tables: list[str],
    uploads_subdir: str | None = None,
    uploads_subdirs: list[str] | None = None,
    table_prefixes: list[str] | None = None,
    ged_module_codes: list[str] | None = None,
    extra_shared: list[str] | None = None,
) -> ModuleBackupScope:
    """Factory pour enregistrer un nouveau module sans recopier le CORE.

    ``ged_module_codes=None`` → le code module lui-même ; ``[]`` → aucune GED propre.
    """
    shared = list(SHARED_CORE_TABLES)
    for name in extra_shared or []:
        if name not in shared:
            shared.append(name)
    subdirs = list(uploads_subdirs or [])
    if uploads_subdir and uploads_subdir not in subdirs:
        subdirs.insert(0, uploads_subdir)
    return {
        "label": label,
        "uploads_subdir": subdirs[0] if subdirs else None,
        "uploads_subdirs": subdirs,
        "exclusive_tables": [t for t in exclusive_tables if t not in SHARED_CORE_TABLES],
        "table_prefixes": list(table_prefixes or []),
        "ged_module_codes": list(ged_module_codes) if ged_module_codes is not None else None,
        "shared_dependencies": shared,
    }


MODULE_BACKUP_SCOPES: dict[str, ModuleBackupScope] = {
    "immobilisations": make_module_scope(
        label="Immobilisations & Amortissements",
        uploads_subdirs=["pieces", "archives"],
        ged_module_codes=["immos", "immobilisations"],
        exclusive_tables=[
            "categories_immobilisation",
            "exercices_comptables",
            "periodes_amortissement",
            "periodes_amortissement_categories",
            "parametrage_amortissement",
            "parametrage_ecritures",
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
        exclusive_tables=["mg_bons_commande", "mg_bc_lignes"],
        table_prefixes=["mg_achat_"],
    ),
    "notes-frais": make_module_scope(
        label="Notes de Frais",
        exclusive_tables=["mg_notes_frais"],
        table_prefixes=["mg_note_frais_"],
    ),
    "contrats-echeances": make_module_scope(
        label="Contrats & Échéances",
        exclusive_tables=[
            "mg_contrats",
            "mg_contrat_echeances",
            "mg_contrat_paiements",
            "mg_contrat_historique",
            "mg_contrat_types",
            "mg_contrat_parametres",
        ],
        table_prefixes=["mg_contrat_"],
    ),
    "facturation-fournisseurs": make_module_scope(
        label="Facturation Fournisseurs",
        exclusive_tables=["mg_points_facturation"],
        table_prefixes=["mg_facturation_"],
    ),
    # Registre transverse : consulte la GED des autres modules MG.
    "archives-mg": make_module_scope(
        label="Archives MG", exclusive_tables=[], ged_module_codes=[]
    ),
    "archives-generales": make_module_scope(
        label="Archive Générale", exclusive_tables=[], ged_module_codes=[]
    ),
    "demandes-mg": make_module_scope(
        label="Demandes (MG — centre de traitement)",
        exclusive_tables=[
            "mg_request_categories",
            "mg_employee_requests",
            "mg_employee_request_items",
            "mg_request_approvals",
            "mg_request_comments",
            "mg_procurement_batches",
            "mg_procurement_batch_items",
        ],
        table_prefixes=["mg_request_", "mg_employee_request", "mg_procurement_"],
    ),
    # Vitrines du moteur de demandes : pas de tables ni de GED propres.
    "demandes-comptabilite": make_module_scope(
        label="Demandes Comptabilité", exclusive_tables=[], ged_module_codes=[]
    ),
    "demandes-credit": make_module_scope(
        label="Demandes Crédit", exclusive_tables=[], ged_module_codes=[]
    ),
    "demandes-rh": make_module_scope(
        label="Demandes RH", exclusive_tables=[], ged_module_codes=[]
    ),
    "demandes-informatique": make_module_scope(
        label="Demandes Informatique", exclusive_tables=[], ged_module_codes=[]
    ),
    "eer": make_module_scope(
        label="Gestion des Entrées en Relation",
        uploads_subdir="eer",
        exclusive_tables=[],
        table_prefixes=["eer_"],
    ),
    "formation": make_module_scope(
        label="Formation & Sensibilisation",
        exclusive_tables=[
            "formation_referentiels",
            "formation_entites",
            "formation_imports",
            "formation_employes",
            "formation_sessions",
            "formation_session_themes",
            "formation_session_formateurs",
            "formation_participants",
            "formation_compteurs",
        ],
        table_prefixes=["formation_"],
    ),
    "clientele": make_module_scope(
        label="Référentiel clients",
        exclusive_tables=[
            "clientele_clients",
            "clientele_comptes",
            "clientele_imports",
            "clientele_import_lignes",
            "clientele_import_anomalies",
            "clientele_import_clients",
            "clientele_import_comptes",
            "clientele_rapprochements",
            "clientele_rapprochement_ecarts",
            "clientele_classif_niveaux",
            "clientele_classif_criteres",
            "clientele_classif_versions",
            "clientele_classif_regles",
            "clientele_classifications",
            "clientele_classif_historique",
            "clientele_filtrage_listes",
            "clientele_filtrage_entrees",
            "clientele_alertes",
            "clientele_alerte_evenements",
            "clientele_alerte_justificatifs",
            "clientele_filtrage_empreintes",
            "clientele_declarations_bcm",
        ],
        table_prefixes=["clientele_"],
        uploads_subdir="clientele",
    ),
}

ESPACE_MODULES: dict[str, list[str]] = {
    "comptabilite": ["immobilisations", "demandes-comptabilite"],
    "credit": ["credit", "demandes-credit"],
    "rh": ["rh", "demandes-rh"],
    "informatique": ["tickets-si", "demandes-informatique"],
    "achats": ["demandes-achat"],
    "moyens-generaux": [
        "stock-fournitures",
        "achats-appro",
        "notes-frais",
        "contrats-echeances",
        "facturation-fournisseurs",
        "archives-mg",
        "demandes-mg",
    ],
    "archives": ["archives-generales"],
    "audit-controle-conformite": ["eer", "formation", "clientele"],
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


def ged_codes_for(module_code: str) -> list[str]:
    scope = MODULE_BACKUP_SCOPES.get(module_code)
    if scope is None:
        return []
    codes = scope.get("ged_module_codes")
    return [module_code] if codes is None else list(codes)


def resolve_tables(module_code: str, existing_tables: set[str]) -> list[str]:
    """Tables exclusives réellement présentes en base (liste explicite + préfixes)."""
    scope = MODULE_BACKUP_SCOPES.get(module_code)
    if scope is None:
        return []
    tables: list[str] = [t for t in scope["exclusive_tables"] if t in existing_tables]
    for prefix in scope.get("table_prefixes") or []:
        for name in sorted(existing_tables):
            if name.startswith(prefix) and name not in tables and name not in _SHARED:
                tables.append(name)
    return tables


def missing_tables(module_code: str, existing_tables: set[str]) -> list[str]:
    scope = MODULE_BACKUP_SCOPES.get(module_code)
    if scope is None:
        return []
    return [t for t in scope["exclusive_tables"] if t not in existing_tables]


def merge_scopes(module_codes: list[str]) -> ModuleBackupScope | None:
    scopes = [MODULE_BACKUP_SCOPES[c] for c in module_codes if c in MODULE_BACKUP_SCOPES]
    if not scopes:
        return None
    tables: list[str] = []
    prefixes: list[str] = []
    shared: list[str] = []
    subdirs: list[str] = []
    for s in scopes:
        for t in s["exclusive_tables"]:
            if t not in tables:
                tables.append(t)
        for p in s.get("table_prefixes") or []:
            if p not in prefixes:
                prefixes.append(p)
        for d in s["shared_dependencies"]:
            if d not in shared:
                shared.append(d)
        for sub in s.get("uploads_subdirs") or []:
            if sub not in subdirs:
                subdirs.append(sub)
    ged: list[str] = []
    for code in module_codes:
        for g in ged_codes_for(code):
            if g not in ged:
                ged.append(g)
    return {
        "label": ", ".join(s["label"] for s in scopes),
        "exclusive_tables": tables,
        "table_prefixes": prefixes,
        "shared_dependencies": shared,
        "uploads_subdir": subdirs[0] if len(subdirs) == 1 else None,
        "uploads_subdirs": subdirs,
        "ged_module_codes": ged,
    }
