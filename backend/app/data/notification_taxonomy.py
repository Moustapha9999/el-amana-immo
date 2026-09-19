"""Taxonomie du centre global de notifications (≠ audit_logs)."""

from __future__ import annotations

NOTIFICATION_CATEGORIES: dict[str, str] = {
    "utilisateurs": "Utilisateurs",
    "departements": "Départements",
    "modules": "Modules",
    "securite": "Sécurité",
    "systeme": "Système",
    "maintenance": "Maintenance",
    "backup": "Backup",
    "recovery": "Recovery",
    "documents": "Documents",
    "finance": "Finance",
    "comptabilite": "Comptabilité",
    "immobilisations": "Immobilisations",
    "amortissements": "Amortissements",
    "workflow": "Workflow",
    "rapports": "Rapports",
    "api": "API",
    "integrations": "Intégrations",
    "import_export": "Import / Export",
    "roles_permissions": "Rôles & Permissions",
    "administration": "Administration",
    "erreurs": "Erreurs",
    "alertes": "Alertes",
}

NOTIFICATION_PRIORITIES: dict[str, str] = {
    "info": "Info",
    "attention": "Attention",
    "avertissement": "Avertissement",
    "critique": "Critique",
}

DESTINATAIRE_TYPES: dict[str, str] = {
    "utilisateur": "Utilisateur",
    "utilisateurs": "Utilisateurs",
    "departement": "Département",
    "module": "Module",
    "role": "Rôle",
    "tous": "Tous les utilisateurs",
    "administrateurs": "Administrateurs",
    "securite": "Responsables sécurité",
}

# Mapping type métier historique → catégorie centre.
TYPE_TO_CATEGORIE = {
    "fin_amortissement": "amortissements",
    "inventaire": "immobilisations",
    "assurance": "immobilisations",
    "maintenance": "maintenance",
    "systeme": "systeme",
}


def infer_priorite(titre: str, message: str = "", *, explicit: str | None = None) -> str:
    if explicit and explicit in NOTIFICATION_PRIORITIES:
        return explicit
    blob = f"{titre} {message}".lower()
    if any(w in blob for w in ("critique", "indisponible", "down", "corruption")):
        return "critique"
    if any(w in blob for w in ("échou", "echou", "erreur", "failed", "error", "impossible")):
        return "avertissement"
    if any(w in blob for w in ("attention", "avert", "suspect", "tentative")):
        return "attention"
    return "info"


def categorie_from_type(type_code: str, *, module_code: str | None = None) -> str:
    if type_code in TYPE_TO_CATEGORIE:
        return TYPE_TO_CATEGORIE[type_code]
    if module_code == "immobilisations":
        return "immobilisations"
    return "systeme"
