"""Catalogue figé des espaces / modules BEA DIGITAL."""

from __future__ import annotations

from typing import TypedDict


class EspaceDef(TypedDict, total=False):
    code: str
    label: str
    description: str
    route: str | None
    statut: str
    sort_order: int
    icon: str


class ModuleDef(TypedDict, total=False):
    code: str
    espace_code: str
    label: str
    description: str
    entry_path: str | None
    statut: str
    sort_order: int
    icon: str
    domaine_code: str
    status_message: str


class DomaineDef(TypedDict, total=False):
    code: str
    espace_code: str
    parent_code: str | None
    label: str
    description: str
    icon: str
    statut: str
    sort_order: int


DEFAULT_ESPACE_CODE = "comptabilite"
DEFAULT_MODULE_CODE = "immobilisations"
ACC_ESPACE_CODE = "audit-controle-conformite"
EER_MODULE_CODE = "eer"
FORMATION_MODULE_CODE = "formation"

# Toujours (re)créés s’ils manquent. Le reste du catalogue = seed **bootstrap**
# seulement (CORE ADMIN peut supprimer sans resurrection au refresh).
SEED_LOCKED_ESPACE_CODES = frozenset(
    {DEFAULT_ESPACE_CODE, "credit", "rh", "informatique", "moyens-generaux", "archives"}
)
SEED_LOCKED_MODULE_CODES = frozenset(
    {
        DEFAULT_MODULE_CODE,
        "stock-fournitures",
        "achats-appro",
        "notes-frais",
        "contrats-echeances",
        "facturation-fournisseurs",
        "archives-mg",
        "archives-generales",
        "demandes-mg",
        "demandes-comptabilite",
        "demandes-credit",
        "demandes-rh",
        "demandes-informatique",
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
        "statut": "actif",
        "sort_order": 2,
    },
    {
        "code": "rh",
        "label": "RH",
        "description": "Processus ressources humaines internes.",
        "route": "/rh",
        "statut": "actif",
        "sort_order": 3,
    },
    {
        "code": "informatique",
        "label": "Informatique",
        "description": "Demandes, suivi et outils internes DSI.",
        "route": "/informatique",
        "statut": "actif",
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
    {
        # Pas /audit : segment réservé Immobilisations (LEGACY_ROOT_PATH_SEGMENTS).
        "code": ACC_ESPACE_CODE,
        "label": "Audit, Contrôle & Conformité",
        "description": (
            "Audit interne, contrôle permanent, conformité & sécurité financière (KYC), "
            "organisation & processus, management & qualité."
        ),
        "route": f"/{ACC_ESPACE_CODE}",
        "statut": "actif",
        "sort_order": 8,
        "icon": "verified_user",
    },
]

# Domaines / sous-domaines (regroupement visuel des modules, pas un niveau d'accès).
# Insérés par migration Alembic (20261003_acc_departement) puis administrés en CORE ADMIN :
# pas de statut « verrouillé » réécrit au refresh.
PLATEFORME_DOMAINES: list[DomaineDef] = [
    {
        "code": "audit-interne",
        "espace_code": ACC_ESPACE_CODE,
        "parent_code": None,
        "label": "Audit interne",
        "description": "Missions d'audit, recommandations et suivi des plans d'action.",
        "icon": "manage_search",
        "statut": "bientot",
        "sort_order": 1,
    },
    {
        "code": "controle-permanent",
        "espace_code": ACC_ESPACE_CODE,
        "parent_code": None,
        "label": "Contrôle permanent & périmètre opérationnel",
        "description": "Plans de contrôle de niveau 1 et 2, anomalies et périmètre opérationnel.",
        "icon": "fact_check",
        "statut": "bientot",
        "sort_order": 2,
    },
    {
        "code": "conformite-securite-financiere",
        "espace_code": ACC_ESPACE_CODE,
        "parent_code": None,
        "label": "Conformité & sécurité financière",
        "description": "KYC, LBC-FT, PPE, FATCA et conformité réglementaire.",
        "icon": "shield",
        "statut": "actif",
        "sort_order": 3,
    },
    {
        "code": "kyc",
        "espace_code": ACC_ESPACE_CODE,
        "parent_code": "conformite-securite-financiere",
        "label": "KYC",
        "description": "Connaissance client : entrées en relation, vérifications et pièces.",
        "icon": "badge",
        "statut": "actif",
        "sort_order": 1,
    },
    {
        "code": "organisation-processus",
        "espace_code": ACC_ESPACE_CODE,
        "parent_code": None,
        "label": "Organisation & Processus",
        "description": "Cartographie des processus, procédures et notes d'organisation.",
        "icon": "account_tree",
        "statut": "bientot",
        "sort_order": 4,
    },
    {
        "code": "management-qualite",
        "espace_code": ACC_ESPACE_CODE,
        "parent_code": None,
        "label": "Management & Qualité",
        "description": "Démarche qualité, indicateurs et amélioration continue.",
        "icon": "workspace_premium",
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
        "sort_order": 2,
    },
    {
        "code": "demandes-comptabilite",
        "espace_code": "comptabilite",
        "label": "Demandes",
        "description": (
            "Déposer et suivre les demandes internes du département "
            "(fournitures, matériel, achat) — routées vers le service destinataire."
        ),
        "entry_path": "/demandes-comptabilite/accueil",
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
        "code": "demandes-credit",
        "espace_code": "credit",
        "label": "Demandes",
        "description": (
            "Déposer et suivre les demandes internes du département Crédit."
        ),
        "entry_path": "/demandes-credit/accueil",
        "statut": "actif",
        "sort_order": 1,
    },
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
        "sort_order": 2,
    },
    {
        "code": "demandes-rh",
        "espace_code": "rh",
        "label": "Demandes",
        "description": "Déposer et suivre les demandes internes du département RH.",
        "entry_path": "/demandes-rh/accueil",
        "statut": "actif",
        "sort_order": 1,
    },
    {
        "code": "rh",
        "espace_code": "rh",
        "label": "Congés & dossiers RH",
        "description": "Congés, absences et demandes administratives internes.",
        "entry_path": "/rh",
        "statut": "bientot",
        "sort_order": 2,
    },
    {
        "code": "demandes-informatique",
        "espace_code": "informatique",
        "label": "Demandes",
        "description": "Déposer et suivre les demandes internes du département Informatique.",
        "entry_path": "/demandes-informatique/accueil",
        "statut": "actif",
        "sort_order": 1,
    },
    {
        "code": "tickets-si",
        "espace_code": "informatique",
        "label": "Tickets SI",
        "description": "Incidents et demandes internes DSI (SLA, files, catégories).",
        "entry_path": "/tickets-si",
        "statut": "bientot",
        "sort_order": 2,
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
        "sort_order": 2,
    },
    {
        "code": "demandes-mg",
        "espace_code": "moyens-generaux",
        "label": "Demandes",
        "description": (
            "Centre de traitement : recevoir les demandes des départements, "
            "contrôler, regrouper, servir depuis le stock ou lancer un achat."
        ),
        "entry_path": "/demandes-mg/dashboard",
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
        "sort_order": 3,
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
        "sort_order": 4,
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
        "sort_order": 5,
    },
    {
        "code": "facturation-fournisseurs",
        "espace_code": "moyens-generaux",
        "label": "Facturation Fournisseurs",
        "description": (
            "Factures récurrentes (SOMELEC, télécoms, eau…) : fournisseurs, points de facturation, "
            "contrôles, échéances, paiements multiples, pièces GED, dashboard 360° et reporting."
        ),
        "entry_path": "/facturation-fournisseurs/dashboard",
        "statut": "actif",
        "sort_order": 6,
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
        "sort_order": 7,
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
    # --- Audit, Contrôle & Conformité → Conformité & sécurité financière → KYC ---
    {
        "code": EER_MODULE_CODE,
        "espace_code": ACC_ESPACE_CODE,
        "domaine_code": "kyc",
        "label": "Gestion des Entrées en Relation",
        "description": (
            "Dossiers EER reçus par e-mail : checklist KYC dynamique, contrôles, "
            "non-conformités, compléments sur le même dossier, validation et archivage."
        ),
        "entry_path": "/eer/dashboard",
        # Passe à « actif » via CORE ADMIN quand le dossier EER est livré.
        "statut": "developpement",
        "status_message": "Module en cours de construction — ouverture après livraison du dossier EER.",
        "icon": "person_add",
        "sort_order": 1,
    },
    # --- Audit, Contrôle & Conformité → Conformité & sécurité financière ---
    {
        "code": FORMATION_MODULE_CODE,
        "espace_code": ACC_ESPACE_CODE,
        "domaine_code": "conformite-securite-financiere",
        "label": "Formation & Sensibilisation",
        "description": (
            "Sessions de formation Conformité (LBC-FT, EER, FATCA…) : employés attendus, "
            "feuille de présence PDF, présents / absents, historique, statistiques et rapports."
        ),
        "entry_path": "/formation/dashboard",
        "statut": "actif",
        "icon": "school",
        "sort_order": 2,
    },
]

# Permissions CORE (tous les départements). `{module}.admin` couvre `{module}.*`.
CORE_PERMISSIONS: list[tuple[str, str, str]] = [
    ("plateforme.users.read", "Consultation des utilisateurs", "plateforme"),
    ("plateforme.users.admin", "Administration des utilisateurs et des accès", "plateforme"),
    ("plateforme.audit.read", "Consultation de l'audit plateforme", "plateforme"),
    ("ged.read", "Consultation GED", "ged"),
    ("ged.write", "Dépôt / suppression GED", "ged"),
    ("ged.download", "Téléchargement GED", "ged"),
    ("ged.export", "Export rapports GED", "ged"),
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
    ("mg.stock.inventory.adjust", "Génération des ajustements d'inventaire", "stock-fournitures"),
    ("mg.stock.inventory.manage", "Administration inventaire (forçage, annulation, suppression)", "stock-fournitures"),
    ("mg.stock.approve", "Validation demandes de fournitures", "stock-fournitures"),
    ("mg.stock.export", "Exports / rapports stock", "stock-fournitures"),
    ("mg.stock.period.view", "Consultation des périodes de stock", "stock-fournitures"),
    ("mg.stock.period.close", "Clôture mensuelle de stock", "stock-fournitures"),
    ("mg.stock.period.reopen", "Réouverture de période et suppression administrateur (périodes clôturées, workflows)", "stock-fournitures"),
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
    ("mg.contrats.validate", "Validation / rejet / annulation contrats", "contrats-echeances"),
    ("mg.contrats.settings", "Paramètres contrats", "contrats-echeances"),
    ("mg.contrats.export", "Exports contrats", "contrats-echeances"),
    ("mg.factures.view", "Consultation des factures (facturation)", "facturation-fournisseurs"),
    ("mg.factures.create", "Saisie des factures", "facturation-fournisseurs"),
    ("mg.factures.update", "Modification / contrôle des factures", "facturation-fournisseurs"),
    ("mg.factures.delete", "Suppression de brouillons / annulation de factures", "facturation-fournisseurs"),
    ("mg.factures.validate", "Validation / contestation des factures", "facturation-fournisseurs"),
    ("mg.factures.archive", "Archivage des factures", "facturation-fournisseurs"),
    ("mg.factures.export", "Exports des factures", "facturation-fournisseurs"),
    ("mg.factures.payment.view", "Consultation des paiements de factures", "facturation-fournisseurs"),
    ("mg.factures.payment.create", "Enregistrement des paiements de factures", "facturation-fournisseurs"),
    ("mg.factures.payment.update", "Modification des paiements de factures", "facturation-fournisseurs"),
    ("mg.factures.payment.delete", "Annulation des paiements de factures", "facturation-fournisseurs"),
    ("mg.factures.documents.view", "Consultation des pièces de factures", "facturation-fournisseurs"),
    ("mg.factures.documents.create", "Dépôt de pièces sur les factures", "facturation-fournisseurs"),
    ("mg.factures.documents.delete", "Détachement de pièces de factures", "facturation-fournisseurs"),
    ("mg.factures.analytics.view", "Dashboard 360° et analyses de facturation", "facturation-fournisseurs"),
    ("mg.factures.reports.export", "Rapports de facturation (PDF, Excel, CSV)", "facturation-fournisseurs"),
    ("mg.facturation.manage", "Points de facturation, import et paramètres de facturation", "facturation-fournisseurs"),
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
    ("mg.request.mine.view", "Consultation de mes demandes internes", "demandes"),
    ("mg.request.mine.create", "Création de mes demandes internes", "demandes"),
    ("mg.request.mine.update", "Modification de mes demandes internes", "demandes"),
    ("mg.request.mine.cancel", "Annulation de mes demandes internes", "demandes"),
    ("mg.request.view", "Consultation des demandes reçues (traitant)", "demandes-mg"),
    ("mg.request.validate", "Validation des demandes", "demandes-mg"),
    ("mg.request.reject", "Refus des demandes", "demandes-mg"),
    ("mg.request.request_info", "Demande de complément", "demandes-mg"),
    ("mg.request.group", "Regroupement des demandes", "demandes-mg"),
    ("mg.request.serve", "Servir une demande depuis le stock", "demandes-mg"),
    ("mg.request.assign", "Affectation d’une demande", "demandes-mg"),
    ("mg.request.export", "Exports demandes", "demandes-mg"),
    ("mg.request.admin", "Administration des types et du moteur Demandes", "demandes-mg"),
    ("mg.batch.view", "Consultation des regroupements achats", "demandes-mg"),
    ("mg.batch.create", "Création des regroupements achats", "demandes-mg"),
    ("mg.batch.update", "Modification des regroupements achats", "demandes-mg"),
    ("mg.batch.validate", "Validation des regroupements (création DA)", "demandes-mg"),
    # Gestion des Entrées en Relation (Conformité → KYC)
    ("eer.view", "Consultation des dossiers EER", "eer"),
    ("eer.create", "Création de dossiers EER", "eer"),
    ("eer.update", "Modification de dossiers EER", "eer"),
    ("eer.submit", "Soumission des dossiers EER au contrôle", "eer"),
    ("eer.assign", "Affectation des dossiers EER", "eer"),
    ("eer.control", "Contrôle KYC (checklist, anomalies)", "eer"),
    ("eer.avis", "Avis Conformité KYC", "eer"),
    ("eer.validate", "Validation des dossiers EER", "eer"),
    ("eer.reject", "Rejet des dossiers EER", "eer"),
    ("eer.complement.request", "Demande de complément EER", "eer"),
    ("eer.complement.receive", "Réception de complément EER", "eer"),
    ("eer.archive", "Clôture / archivage des dossiers EER", "eer"),
    ("eer.export", "Exports EER", "eer"),
    ("eer.report.view", "Reporting EER", "eer"),
    ("eer.rules.view", "Consultation des règles KYC", "eer"),
    ("eer.rules.manage", "Paramétrage des règles KYC", "eer"),
    ("eer.document.view", "Consultation des pièces EER", "eer"),
    ("eer.document.upload", "Dépôt de pièces EER", "eer"),
    ("eer.document.download", "Téléchargement des pièces EER", "eer"),
    ("eer.scope.all", "Périmètre EER : toutes les agences", "eer"),
    ("eer.audit.view", "Consultation de l'audit EER", "eer"),
    ("eer.admin", "Administration du module EER", "eer"),
    ("formation.view", "Consultation des formations", "formation"),
    ("formation.create", "Création de formations", "formation"),
    ("formation.update", "Modification de formations et des participants", "formation"),
    ("formation.cancel", "Annulation de formations", "formation"),
    ("formation.close", "Clôture, réouverture et archivage des formations", "formation"),
    ("formation.employees.view", "Consultation du référentiel employés formation", "formation"),
    ("formation.employees.manage", "Gestion du référentiel employés formation", "formation"),
    ("formation.attendance.view", "Consultation des présences", "formation"),
    ("formation.attendance.manage", "Saisie des présences / absences", "formation"),
    ("formation.references.view", "Consultation des référentiels formation", "formation"),
    ("formation.references.manage", "Gestion des référentiels formation", "formation"),
    ("formation.import.view", "Consultation des imports Excel formation", "formation"),
    ("formation.import.execute", "Import de l'historique Excel des formations", "formation"),
    ("formation.reporting.view", "Reporting formation", "formation"),
    ("formation.reporting.export", "Exports PDF / Excel formation", "formation"),
    ("formation.admin", "Administration du module Formation & Sensibilisation", "formation"),
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
    ("contrats-echeances.valideur", "Contrats — Valideur", "Validation, annulation, rapports et paramètres"),
    ("contrats-echeances.admin", "Contrats — Admin", "Administration contrats"),
    ("facturation-fournisseurs.lecteur", "Facturation — Lecteur", "Consultation des factures, paiements et analyses"),
    ("facturation-fournisseurs.gestionnaire", "Facturation — Gestionnaire", "Saisie des factures, paiements et pièces"),
    ("facturation-fournisseurs.valideur", "Facturation — Valideur", "Validation, archivage, points et paramètres"),
    ("facturation-fournisseurs.admin", "Facturation — Admin", "Administration complète de la facturation fournisseurs"),
    ("archives-mg.lecteur", "Archives MG — Lecteur", "Consultation archives MG"),
    ("archives-mg.admin", "Archives MG — Admin", "Administration archives MG"),
    ("archives-generales.lecteur", "Archive Générale — Lecteur", "Consultation Archive Générale"),
    ("archives-generales.admin", "Archive Générale — Admin", "Administration Archive Générale"),
    ("demandes-comptabilite.demandeur", "Demandes Comptabilité — Demandeur", "Dépôt et suivi de ses demandes"),
    ("demandes-credit.demandeur", "Demandes Crédit — Demandeur", "Dépôt et suivi de ses demandes"),
    ("demandes-rh.demandeur", "Demandes RH — Demandeur", "Dépôt et suivi de ses demandes"),
    ("demandes-informatique.demandeur", "Demandes Informatique — Demandeur", "Dépôt et suivi de ses demandes"),
    ("demandes-mg.demandeur", "Demandes MG — Demandeur", "Dépôt et suivi de ses propres demandes"),
    ("demandes-mg.lecteur", "Demandes MG — Lecteur", "Consultation des demandes reçues"),
    ("demandes-mg.gestionnaire", "Demandes MG — Gestionnaire", "Traitement et regroupement des demandes"),
    ("demandes-mg.valideur", "Demandes MG — Valideur", "Validation / refus des demandes"),
    ("demandes-mg.admin", "Demandes MG — Admin", "Administration des demandes employés"),
    ("eer.charge", "EER — Chargé de clientèle", "Création, saisie et soumission des dossiers de son agence"),
    ("eer.lecteur", "EER — Lecteur", "Consultation des dossiers et du reporting EER"),
    ("eer.analyste", "EER — Analyste conformité", "Saisie, contrôle KYC et compléments"),
    ("eer.superviseur", "EER — Superviseur", "Affectation, validation, rejet et archivage"),
    ("eer.admin", "EER — Admin", "Administration complète du module EER et des règles KYC"),
    ("formation.lecteur", "Formation — Lecteur", "Consultation des formations, présences et du reporting"),
    ("formation.gestionnaire", "Formation — Gestionnaire", "Sessions, participants, présences, employés et exports"),
    ("formation.admin", "Formation — Admin", "Administration complète : référentiels, imports, clôtures"),
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
_MG_FACTURATION_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "facturation-fournisseurs"
)
_MG_FACTURES_LECTURE = (
    "mg.factures.view",
    "mg.factures.payment.view",
    "mg.factures.documents.view",
    "mg.factures.analytics.view",
)
_MG_ARCHIVES_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "archives-mg"
)
_ARCHIVES_GENERALES_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "archives-generales"
)
_MG_REQUEST_EMP_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "demandes"
)
_MG_REQUEST_MG_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "demandes-mg"
)
_EER_ALL = tuple(code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "eer")
# Pas de ged.* sur les rôles EER : les pièces KYC passent uniquement par les endpoints EER
# (eer.document.*), jamais par la GED générique / Archive Générale.
_EER_ANALYSTE = (
    "eer.view",
    "eer.create",
    "eer.update",
    "eer.submit",
    "eer.control",
    "eer.complement.request",
    "eer.complement.receive",
    "eer.export",
    "eer.report.view",
    "eer.rules.view",
    "eer.document.view",
    "eer.document.upload",
    "eer.document.download",
    "eer.scope.all",
)
_EER_CHARGE = (
    "eer.view",
    "eer.create",
    "eer.update",
    "eer.submit",
    "eer.document.view",
    "eer.document.upload",
    "eer.document.download",
)
_FORMATION_ALL = tuple(
    code for code, _label, module in FUNCTIONAL_PERMISSIONS if module == "formation"
)
_FORMATION_LECTEUR = (
    "formation.view",
    "formation.employees.view",
    "formation.attendance.view",
    "formation.references.view",
    "formation.reporting.view",
)
_FORMATION_GESTIONNAIRE = _FORMATION_LECTEUR + (
    "formation.create",
    "formation.update",
    "formation.cancel",
    "formation.close",
    "formation.employees.manage",
    "formation.attendance.manage",
    "formation.import.view",
    "formation.reporting.export",
)
_CORE_ADMIN = (
    "plateforme.users.read",
    "plateforme.users.admin",
    "plateforme.audit.read",
    "ged.read",
    "ged.write",
    "ged.download",
    "ged.export",
)
_GED_RW = ("ged.read", "ged.write", "ged.download", "ged.export")

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
        "mg.stock.inventory.adjust",
        "mg.stock.period.view",
    ),
    "stock-fournitures.admin": _MG_STOCK_ALL + _GED_RW,
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
    "achats-appro.admin": _MG_ACHATS_ALL + _GED_RW,
    "notes-frais.lecteur": ("mg.notes.view",),
    "notes-frais.redacteur": ("mg.notes.view", "mg.notes.create", "mg.notes.export"),
    "notes-frais.valideur": (
        "mg.notes.view",
        "mg.notes.control",
        "mg.notes.approve",
        "mg.notes.reject",
        "mg.notes.export",
    ),
    "notes-frais.admin": _MG_NOTES_ALL + _GED_RW,
    "contrats-echeances.lecteur": ("mg.contrats.view", "ged.read", "ged.download"),
    "contrats-echeances.gestionnaire": (
        "mg.contrats.view",
        "mg.contrats.create",
        "mg.contrats.manage",
        "mg.contrats.export",
        "ged.read",
        "ged.write",
        "ged.download",
    ),
    "contrats-echeances.valideur": (
        "mg.contrats.view",
        "mg.contrats.validate",
        "mg.contrats.settings",
        "mg.contrats.export",
        "ged.read",
        "ged.download",
    ),
    "contrats-echeances.admin": _MG_CONTRATS_ALL + _GED_RW,
    "facturation-fournisseurs.lecteur": ("ged.read", "ged.download") + _MG_FACTURES_LECTURE,
    "facturation-fournisseurs.gestionnaire": ("ged.read", "ged.write", "ged.download")
    + _MG_FACTURES_LECTURE
    + (
        "mg.factures.create",
        "mg.factures.update",
        "mg.factures.delete",
        "mg.factures.export",
        "mg.factures.payment.create",
        "mg.factures.payment.update",
        "mg.factures.documents.create",
        "mg.factures.documents.delete",
        "mg.factures.reports.export",
    ),
    "facturation-fournisseurs.valideur": ("ged.read", "ged.download")
    + _MG_FACTURES_LECTURE
    + (
        "mg.factures.validate",
        "mg.factures.archive",
        "mg.factures.delete",
        "mg.factures.export",
        "mg.factures.payment.delete",
        "mg.factures.reports.export",
        "mg.facturation.manage",
    ),
    "facturation-fournisseurs.admin": _MG_FACTURATION_ALL + _GED_RW,
    "archives-mg.lecteur": (
        "mg.archives.view",
        "mg.archives.download",
        "ged.read",
        "ged.download",
    ),
    "archives-mg.admin": _MG_ARCHIVES_ALL + _GED_RW,
    "archives-generales.lecteur": (
        "archives.general.view",
        "archives.general.download",
        "ged.read",
        "ged.download",
    ),
    "archives-generales.admin": _ARCHIVES_GENERALES_ALL + _GED_RW,
    "demandes-comptabilite.demandeur": _MG_REQUEST_EMP_ALL + ("ged.read", "ged.write", "ged.download"),
    "demandes-credit.demandeur": _MG_REQUEST_EMP_ALL + ("ged.read", "ged.write", "ged.download"),
    "demandes-rh.demandeur": _MG_REQUEST_EMP_ALL + ("ged.read", "ged.write", "ged.download"),
    "demandes-informatique.demandeur": _MG_REQUEST_EMP_ALL + ("ged.read", "ged.write", "ged.download"),
    "demandes-mg.demandeur": _MG_REQUEST_EMP_ALL + ("ged.read", "ged.write", "ged.download"),
    "demandes-mg.lecteur": ("mg.request.view", "mg.batch.view", "ged.read", "ged.download"),
    "demandes-mg.gestionnaire": (
        "mg.request.view",
        "mg.request.request_info",
        "mg.request.group",
        "mg.request.serve",
        "mg.request.assign",
        "mg.request.export",
        "mg.batch.view",
        "mg.batch.create",
        "mg.batch.update",
        "ged.read",
        "ged.write",
        "ged.download",
    ),
    "demandes-mg.valideur": (
        "mg.request.view",
        "mg.request.validate",
        "mg.request.reject",
        "mg.request.request_info",
        "mg.request.assign",
        "mg.request.export",
        "mg.batch.view",
        "mg.batch.validate",
        "ged.read",
        "ged.download",
    ),
    "demandes-mg.admin": _MG_REQUEST_MG_ALL + _GED_RW,
    "eer.charge": _EER_CHARGE,
    "eer.lecteur": ("eer.view", "eer.report.view", "eer.document.view", "eer.scope.all"),
    "eer.analyste": _EER_ANALYSTE,
    "eer.superviseur": _EER_ANALYSTE
    + ("eer.assign", "eer.avis", "eer.validate", "eer.reject", "eer.archive", "eer.audit.view"),
    "eer.admin": _EER_ALL,
    "formation.lecteur": _FORMATION_LECTEUR,
    "formation.gestionnaire": _FORMATION_GESTIONNAIRE,
    "formation.admin": _FORMATION_ALL,
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
