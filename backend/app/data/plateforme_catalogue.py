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

# Toujours (re)créés s’ils manquent. Le reste du catalogue = seed **bootstrap**
# seulement (CORE ADMIN peut supprimer sans resurrection au refresh).
SEED_LOCKED_ESPACE_CODES = frozenset({DEFAULT_ESPACE_CODE, "moyens-generaux", "archives"})
SEED_LOCKED_MODULE_CODES = frozenset(
    {
        DEFAULT_MODULE_CODE,
        "stock-fournitures",
        "achats-appro",
        "notes-frais",
        "contrats-echeances",
        "archives-mg",
        "archives-generales",
    }
)

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
        "route": "/credit",
        "statut": "bientot",
        "sort_order": 2,
    },
    {
        "code": "rh",
        "label": "RH",
        "description": "Processus ressources humaines internes.",
        "route": "/rh",
        "statut": "bientot",
        "sort_order": 3,
    },
    {
        "code": "informatique",
        "label": "Informatique",
        "description": "Demandes, suivi et outils internes DSI.",
        "route": "/informatique",
        "statut": "bientot",
        "sort_order": 4,
    },
    {
        "code": "achats",
        "label": "Achats",
        "description": "Demandes d’achat, validations et suivi documentaire.",
        "route": "/achats",
        "statut": "bientot",
        "sort_order": 5,
    },
    {
        "code": "moyens-generaux",
        "label": "Moyens Généraux",
        "description": (
            "Achats, stock & fournitures, notes de frais, contrats et archives "
            "documentaires — digitalisation des processus internes MG."
        ),
        "route": "/moyens-generaux",
        "statut": "actif",
        "sort_order": 6,
    },
    {
        "code": "archives",
        "label": "Archives",
        "description": (
            "Archive Générale BEA-DIGITAL — vue transverse sur la GED centrale, "
            "recherche et OCR selon permissions."
        ),
        # Pas /archives : segment réservé Immobilisations (LEGACY_ROOT_PATH_SEGMENTS).
        "route": "/archive-generale",
        "statut": "actif",
        "sort_order": 7,
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
    # --- Futurs (catalogue Étape 8 — statut bientôt, pas encore de shell métier) ---
    {
        "code": "credit",
        "espace_code": "credit",
        "label": "Dossiers crédit",
        "description": (
            "Instruction et suivi interne des dossiers autour d’ORION "
            "(checklists, validations, GED) — sans remplacer le core banking."
        ),
        "entry_path": "/credit",
        "statut": "bientot",
        "sort_order": 1,
    },
    {
        "code": "rh",
        "espace_code": "rh",
        "label": "Demandes RH",
        "description": "Congés, absences et demandes administratives internes.",
        "entry_path": "/rh",
        "statut": "bientot",
        "sort_order": 1,
    },
    {
        "code": "tickets-si",
        "espace_code": "informatique",
        "label": "Tickets SI",
        "description": "Incidents et demandes internes DSI (SLA, files, catégories).",
        "entry_path": "/tickets-si",
        "statut": "bientot",
        "sort_order": 1,
    },
    {
        "code": "demandes-achat",
        "espace_code": "achats",
        "label": "Demandes d’achat",
        "description": "Demandes, validations et suivi documentaire des achats.",
        "entry_path": "/demandes-achat",
        "statut": "bientot",
        "sort_order": 1,
    },
    # --- Moyens Généraux (CDC v1 — Phase 1 = stock-fournitures) ---
    {
        "code": "stock-fournitures",
        "espace_code": "moyens-generaux",
        "label": "Stock & Fournitures",
        "description": (
            "Articles, familles, entrées/sorties, demandes de fournitures, "
            "états de stock et rapports de consommation."
        ),
        "entry_path": "/stock-fournitures/dashboard",
        "statut": "actif",
        "sort_order": 1,
    },
    {
        "code": "achats-appro",
        "espace_code": "moyens-generaux",
        "label": "Achats & Approvisionnements",
        "description": (
            "Cycle d’achat : demandes, fournisseurs, "
            "bons de commande (PDF signataires dynamiques, TVA/TTC via paramètres), "
            "réceptions, factures, paiements, GED et rapports."
        ),
        "entry_path": "/achats-appro/dashboard",
        "statut": "actif",
        "sort_order": 2,
    },
    {
        "code": "notes-frais",
        "espace_code": "moyens-generaux",
        "label": "Notes de Frais",
        "description": (
            "Saisie avec agence ou intitulé libre, validation, paiement, "
            "modification et suppression hors paiement, fiche PDF A4 portrait ou paysage, "
            "rapports Excel et PDF."
        ),
        "entry_path": "/notes-frais",
        "statut": "actif",
        "sort_order": 3,
    },
    {
        "code": "contrats-echeances",
        "espace_code": "moyens-generaux",
        "label": "Contrats & Échéances",
        "description": (
            "Cycle de vie des contrats : fournisseur et agence du référentiel, "
            "échéances, paiements suivis, alertes, renouvellement, GED et rapports."
        ),
        "entry_path": "/contrats-echeances/dashboard",
        "statut": "actif",
        "sort_order": 4,
    },
    {
        "code": "archives-mg",
        "espace_code": "moyens-generaux",
        "label": "Archives",
        "description": (
            "Mémoire documentaire MG : registre GED, recherche, dossiers métier, "
            "corbeille, documents manquants, rapports."
        ),
        "entry_path": "/archives-mg/dashboard",
        "statut": "actif",
        "sort_order": 5,
    },
    {
        "code": "archives-generales",
        "espace_code": "archives",
        "label": "Archive Générale",
        "description": (
            "Centre documentaire transverse : recherche métadonnées + OCR, "
            "tous départements selon permissions."
        ),
        "entry_path": "/archives-generales",
        "statut": "actif",
        "sort_order": 1,
    },
]

# Permissions CORE (tous les départements). `{module}.admin` couvre `{module}.*`.
CORE_PERMISSIONS: list[tuple[str, str, str]] = [
    ("plateforme.users.read", "Consultation des utilisateurs", "plateforme"),
    ("plateforme.users.admin", "Administration des utilisateurs et des accès", "plateforme"),
    ("plateforme.audit.read", "Consultation de l'audit plateforme", "plateforme"),
    ("ged.read", "Consultation GED", "ged"),
    ("ged.write", "Dépôt / suppression GED", "ged"),
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
    # Stock & Fournitures (Moyens Généraux — Phase 1)
    ("mg.stock.view", "Consultation stock & fournitures", "stock-fournitures"),
    ("mg.stock.create", "Création articles / demandes", "stock-fournitures"),
    ("mg.stock.entry", "Entrées de stock", "stock-fournitures"),
    ("mg.stock.exit", "Sorties de stock", "stock-fournitures"),
    ("mg.stock.adjust", "Ajustements de stock", "stock-fournitures"),
    ("mg.stock.inventory", "Inventaire stock", "stock-fournitures"),
    ("mg.stock.inventory.validate", "Validation / clôture d'inventaire", "stock-fournitures"),
    ("mg.stock.approve", "Validation demandes de fournitures", "stock-fournitures"),
    ("mg.stock.export", "Exports / rapports stock", "stock-fournitures"),
    ("mg.stock.period.view", "Consultation des périodes de stock", "stock-fournitures"),
    ("mg.stock.period.close", "Clôture mensuelle de stock", "stock-fournitures"),
    ("mg.stock.period.reopen", "Réouverture d'une période clôturée", "stock-fournitures"),
    ("mg.stock.negative", "Autoriser un stock négatif (exception auditée)", "stock-fournitures"),
    ("mg.purchase.view", "Consultation achats / bons de commande", "achats-appro"),
    ("mg.purchase.create", "Création / modification BC, paramètres achats (TVA…)", "achats-appro"),
    ("mg.purchase.approve", "Validation / visas bons de commande", "achats-appro"),
    ("mg.purchase.export", "Exports achats et PDF bon de commande", "achats-appro"),
    ("mg.purchase.receive", "Réceptions marchandises", "achats-appro"),
    ("mg.purchase.invoice", "Factures fournisseurs / rapprochement", "achats-appro"),
    ("mg.purchase.pay", "Paiements fournisseurs", "achats-appro"),
    ("mg.purchase.demande", "Demandes d'achat", "achats-appro"),
    ("mg.notes.view", "Consultation notes de frais", "notes-frais"),
    ("mg.notes.create", "Création / modification notes de frais", "notes-frais"),
    ("mg.notes.control", "Contrôle notes de frais", "notes-frais"),
    ("mg.notes.approve", "Visas / validation notes de frais", "notes-frais"),
    ("mg.notes.reject", "Rejet / annulation notes de frais", "notes-frais"),
    ("mg.notes.payment", "Mise en paiement / paiement notes de frais", "notes-frais"),
    ("mg.notes.archive", "Archivage notes de frais", "notes-frais"),
    ("mg.notes.export", "Exports / rapports notes de frais", "notes-frais"),
    ("mg.notes.settings", "Paramètres notes de frais", "notes-frais"),
    ("mg.contrats.view", "Consultation contrats", "contrats-echeances"),
    ("mg.contrats.create", "Création contrats", "contrats-echeances"),
    ("mg.contrats.manage", "Gestion / alertes contrats", "contrats-echeances"),
    ("mg.contrats.export", "Exports contrats", "contrats-echeances"),
    ("mg.archives.view", "Consultation archives MG", "archives-mg"),
    ("mg.archives.create", "Ajout / archivage manuel archives MG", "archives-mg"),
    ("mg.archives.update", "Modification metadonnees archives MG", "archives-mg"),
    ("mg.archives.download", "Telechargement archives MG", "archives-mg"),
    ("mg.archives.export", "Exports archives MG", "archives-mg"),
    ("mg.archives.archive", "Archivage automatique / manuel archives MG", "archives-mg"),
    ("mg.archives.restore", "Restauration corbeille archives MG", "archives-mg"),
    ("mg.archives.delete", "Purge definitive archives MG", "archives-mg"),
    ("mg.archives.manage", "Parametres archives MG", "archives-mg"),
    ("archives.general.view", "Consultation Archive Générale", "archives-generales"),
    ("archives.general.download", "Téléchargement Archive Générale", "archives-generales"),
    ("archives.general.ocr.retry", "Relance OCR Archive Générale", "archives-generales"),
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
    ("stock-fournitures.lecteur", "Stock — Lecteur", "Consultation stock & fournitures"),
    ("stock-fournitures.magasinier", "Stock — Magasinier", "Entrées / sorties / articles"),
    ("stock-fournitures.valideur", "Stock — Valideur", "Visas demandes de fournitures"),
    ("stock-fournitures.admin", "Stock — Admin", "Administration stock & fournitures"),
    ("achats-appro.lecteur", "Achats — Lecteur", "Consultation cycle d’achat et PDF"),
    ("achats-appro.acheteur", "Achats — Acheteur", "Création BC, paramètres, réceptions, factures, PDF"),
    ("achats-appro.valideur", "Achats — Valideur", "Visas BC, demandes et export PDF"),
    ("achats-appro.admin", "Achats — Admin", "Administration complète achats MG + GED"),
    ("notes-frais.lecteur", "Notes — Lecteur", "Consultation notes de frais"),
    ("notes-frais.redacteur", "Notes — Rédacteur", "Création notes de frais"),
    ("notes-frais.valideur", "Notes — Valideur", "Visas notes de frais"),
    ("notes-frais.admin", "Notes — Admin", "Administration notes de frais"),
    ("contrats-echeances.lecteur", "Contrats — Lecteur", "Consultation contrats"),
    ("contrats-echeances.gestionnaire", "Contrats — Gestionnaire", "Création / alertes contrats"),
    ("contrats-echeances.admin", "Contrats — Admin", "Administration contrats"),
    ("archives-mg.lecteur", "Archives MG — Lecteur", "Consultation archives MG"),
    ("archives-mg.admin", "Archives MG — Admin", "Administration archives MG"),
    ("archives-generales.lecteur", "Archive Générale — Lecteur", "Consultation Archive Générale"),
    ("archives-generales.admin", "Archive Générale — Admin", "Administration Archive Générale"),
]

# Codes courts réservés au module Immobilisations (ne pas créer pour Crédit / RH / …).
IMMO_LEGACY_ROLE_CODES = frozenset(
    {
        "consultation",
        "lecture_seule",
        "creation",
        "modification",
        "validation",
        "comptable",
        "auditeur",
        "administrateur",
    }
)

_IMMO_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "immobilisations"
)
_MG_STOCK_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "stock-fournitures"
)
_MG_ACHATS_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "achats-appro"
)
_MG_NOTES_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "notes-frais"
)
_MG_CONTRATS_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "contrats-echeances"
)
_MG_ARCHIVES_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "archives-mg"
)
_ARCHIVES_GENERALES_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "archives-generales"
)
_CORE_ADMIN = (
    "plateforme.users.read",
    "plateforme.users.admin",
    "plateforme.audit.read",
    "ged.read",
    "ged.write",
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
    "stock-fournitures.lecteur": ("mg.stock.view", "mg.stock.period.view"),
    "stock-fournitures.magasinier": (
        "mg.stock.view",
        "mg.stock.create",
        "mg.stock.entry",
        "mg.stock.exit",
        "mg.stock.adjust",
        "mg.stock.inventory",
        "mg.stock.period.view",
    ),
    "stock-fournitures.valideur": (
        "mg.stock.view",
        "mg.stock.approve",
        "mg.stock.inventory.validate",
        "mg.stock.period.view",
    ),
    "stock-fournitures.admin": _MG_STOCK_ALL + ("ged.read", "ged.write"),
    "achats-appro.lecteur": ("mg.purchase.view", "mg.purchase.export"),
    "achats-appro.acheteur": (
        "mg.purchase.view",
        "mg.purchase.create",
        "mg.purchase.demande",
        "mg.purchase.receive",
        "mg.purchase.invoice",
        "mg.purchase.export",
    ),
    "achats-appro.valideur": (
        "mg.purchase.view",
        "mg.purchase.approve",
        "mg.purchase.demande",
        "mg.purchase.export",
    ),
    "achats-appro.admin": _MG_ACHATS_ALL + ("ged.read", "ged.write"),
    "notes-frais.lecteur": ("mg.notes.view",),
    "notes-frais.redacteur": ("mg.notes.view", "mg.notes.create", "mg.notes.export"),
    "notes-frais.valideur": (
        "mg.notes.view",
        "mg.notes.control",
        "mg.notes.approve",
        "mg.notes.reject",
        "mg.notes.export",
    ),
    "notes-frais.admin": _MG_NOTES_ALL + ("ged.read", "ged.write"),
    "contrats-echeances.lecteur": ("mg.contrats.view",),
    "contrats-echeances.gestionnaire": (
        "mg.contrats.view",
        "mg.contrats.create",
        "mg.contrats.manage",
        "mg.contrats.export",
    ),
    "contrats-echeances.admin": _MG_CONTRATS_ALL + ("ged.read", "ged.write"),
    "archives-mg.lecteur": (
        "mg.archives.view",
        "mg.archives.download",
    ),
    "archives-mg.admin": _MG_ARCHIVES_ALL + ("ged.read", "ged.write"),
    "archives-generales.lecteur": (
        "archives.general.view",
        "archives.general.download",
        "ged.read",
    ),
    "archives-generales.admin": _ARCHIVES_GENERALES_ALL + ("ged.read", "ged.write"),
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
