"""Libellés français et synonymes métier du catalogue CORE QUERY.

Uniquement de la présentation / du vocabulaire : la structure (tables,
colonnes, clés) vient toujours de l'introspection PostgreSQL.
"""

from __future__ import annotations

# table -> (libellé, synonymes normalisés sans accents)
TABLE_LABELS: dict[str, tuple[str, list[str]]] = {
    "users": ("Utilisateurs", ["utilisateur", "utilisateurs", "user", "users", "compte", "comptes"]),
    "roles": ("Rôles", ["role", "roles"]),
    "permissions": ("Permissions", ["permission", "permissions"]),
    "user_roles": ("Rôles des utilisateurs", []),
    "role_permissions": ("Permissions des rôles", []),
    "auth_sessions": ("Sessions de connexion", ["session", "sessions", "connexion", "connexions"]),
    "auth_login_attempts": (
        "Tentatives de connexion",
        ["tentative", "tentatives", "echec de connexion", "echecs de connexion"],
    ),
    "audit_logs": ("Journal d'audit", ["audit", "operation", "operations", "action", "actions", "journal"]),
    "notifications": ("Notifications", ["notification", "notifications"]),
    "agences": ("Agences", ["agence", "agences"]),
    "directions": ("Directions", ["direction", "directions"]),
    "departements": ("Départements (organisation)", ["departement", "departements", "service", "services"]),
    "plateforme_espaces": ("Départements BEA DIGITAL", ["espace", "espaces"]),
    "plateforme_modules": ("Modules", ["module", "modules"]),
    "plateforme_domaines": ("Domaines plateforme", []),
    "immobilisations": ("Immobilisations", ["immobilisation", "immobilisations", "immo", "immos", "actif", "actifs"]),
    "categories_immobilisation": ("Catégories d'immobilisation", ["categorie", "categories"]),
    "amortissements": ("Amortissements", ["amortissement", "amortissements", "dotation", "dotations"]),
    "cessions": ("Cessions", ["cession", "cessions"]),
    "rebuts": ("Rebuts", ["rebut", "rebuts"]),
    "fournisseurs": ("Fournisseurs", ["fournisseur", "fournisseurs"]),
    "mg_demandes_fourniture": (
        "Demandes de fournitures (stock)",
        ["demande de stock", "demandes de stock", "demande de fourniture", "demandes de fourniture",
         "demandes de fournitures"],
    ),
    "mg_articles": ("Articles de stock", ["article", "articles", "fourniture", "fournitures"]),
    "mg_stock_mouvements": ("Mouvements de stock", ["mouvement", "mouvements", "mouvements de stock"]),
    "mg_stock_soldes": ("Soldes de stock", ["solde de stock", "soldes de stock"]),
    "mg_employee_requests": ("Demandes employés", ["demande employe", "demandes employes", "demandes des employes"]),
    "mg_achat_demandes": ("Demandes d'achat", ["demande d achat", "demandes d achat"]),
    "mg_achat_factures": ("Factures d'achat", ["facture", "factures"]),
    "mg_bons_commande": ("Bons de commande", ["bon de commande", "bons de commande"]),
    "mg_contrats": ("Contrats", ["contrat", "contrats"]),
    "mg_contrat_echeances": ("Échéances de contrats", ["echeance", "echeances"]),
    "mg_notes_frais": ("Notes de frais", ["note de frais", "notes de frais"]),
    "formation_sessions": ("Sessions de formation", ["formation", "formations", "sessions de formation"]),
    "formation_participants": ("Participants aux formations", ["participant", "participants"]),
    "formation_employes": ("Employés (formation)", ["employe", "employes"]),
    "eer_dossiers": ("Dossiers d'entrée en relation", ["dossier eer", "dossiers eer", "entree en relation",
                                                      "entrees en relation"]),
    "ged_documents": ("Documents GED", ["document", "documents", "ged"]),
    "archive_fichiers": ("Fichiers d'archives", ["archive", "archives", "fichier d archive", "fichiers d archives"]),
    "archive_dossiers": ("Dossiers d'archives", ["dossier d archives", "dossiers d archives"]),
    "security_incidents": ("Incidents de sécurité", ["incident", "incidents"]),
    "platform_backups": ("Sauvegardes", ["sauvegarde", "sauvegardes", "backup", "backups"]),
    "platform_restores": ("Restaurations", ["restauration", "restaurations", "recovery"]),
    "api_error_events": ("Erreurs API", ["erreur", "erreurs"]),
    "core_query_logs": ("Historique CORE QUERY", []),
    "core_query_favorites": ("Favoris CORE QUERY", []),
}

COLUMN_LABELS: dict[str, str] = {
    "id": "Identifiant",
    "code": "Code",
    "libelle": "Libellé",
    "label": "Libellé",
    "designation": "Désignation",
    "full_name": "Utilisateur",
    "email": "E-mail",
    "phone": "Téléphone",
    "is_active": "Actif",
    "is_superuser": "Super administrateur",
    "last_login_at": "Dernière connexion",
    "created_at": "Créé le",
    "updated_at": "Modifié le",
    "deleted_at": "Supprimé le",
    "statut": "Statut",
    "status": "Statut",
    "reference": "Référence",
    "ip_address": "Adresse IP",
    "module_code": "Module",
    "espace_code": "Département",
    "action": "Action",
    "entity": "Objet",
    "valeur_brute": "Valeur brute",
    "date_demande": "Date de demande",
    "filename": "Fichier",
    "title": "Titre",
    "ville": "Ville",
}

# Colonnes candidates pour représenter une ligne (ordre de préférence).
DISPLAY_COLUMNS = (
    "full_name",
    "libelle",
    "label",
    "designation",
    "raison_sociale",
    "nom",
    "name",
    "title",
    "intitule",
    "reference",
    "request_number",
    "numero",
    "code_inventaire",
    "code",
    "filename",
    "email",
)

STATUS_COLUMNS = ("statut", "status")
DATE_COLUMNS = ("created_at", "date_demande", "date_document", "submitted_at", "updated_at")


def table_label(name: str) -> str:
    entry = TABLE_LABELS.get(name)
    if entry:
        return entry[0]
    return name.replace("_", " ").capitalize()


def column_label(name: str) -> str:
    return COLUMN_LABELS.get(name) or name.replace("_", " ").capitalize()
