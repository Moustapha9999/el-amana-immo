# Architecture des données — BEA DIGITAL

> Audit du 22/10/2026. Les chiffres proviennent des modèles SQLAlchemy (`backend/app/models/`) et
> de requêtes de **comptage** en lecture seule sur l'instance locale. Aucune donnée personnelle ou
> bancaire n'a été extraite. Le schéma complet est documenté dans `docs/db/schema.sql` et
> `docs/db/relations.md`.

## 1. Principes

- **Une seule base** PostgreSQL 17 (`bea_digital`) pour le socle et tous les modules
  (`AGENTS.md`, `docs/base-de-donnees-unique.md`). Pas de schéma séparé par module : tout est dans
  `public`, avec des préfixes de table (`mg_`, `clientele_`, `eer_`, `integration_`, …).
- **ORION reste la source de vérité** bancaire : BEA DIGITAL stocke des **copies importées** de
  données ORION (clients, comptes, soldes), datées par import, sans écriture vers ORION.
- 210 tables en base locale ; 205 classes mappées + 4 tables d'association dans le code.
- Valeurs monétaires stockées brutes ; le formatage fr-FR est appliqué à l'affichage et à l'export.

## 2. Vue conceptuelle des domaines

Source éditable : [diagrams/08-domaines-donnees.mmd](diagrams/08-domaines-donnees.mmd).

```mermaid
flowchart LR
    subgraph IAM["Identités et accès"]
        USR["users, roles, permissions,<br/>user_roles, role_permissions,<br/>user_espace_acces, user_module_acces"]
        SES["auth_sessions,<br/>auth_login_attempts,<br/>password_history, password_reset_jtis"]
    end
    subgraph CAT["Configuration plateforme"]
        PLT["plateforme_espaces,<br/>plateforme_domaines,<br/>plateforme_modules"]
        OPS["platform_ops_flags (politique sécurité,<br/>maintenance), platform_module_versions"]
    end
    subgraph ORG["Référentiel organisationnel"]
        ORGT["departements, org_postes,<br/>org_affectations, agences,<br/>centres_cout, directions"]
    end
    subgraph TRACE["Traçabilité et technique"]
        AUD["audit_logs"]
        NOT["notifications"]
        ERR["api_error_events,<br/>security_incidents"]
        CQ["core_query_logs,<br/>core_query_favorites"]
        BKP["platform_backups,<br/>platform_restores"]
    end
    subgraph DOC["Documents"]
        GED["ged_documents<br/>(+ fichiers storage/ged)"]
        PJ["pieces_jointes, archive_*<br/>(+ fichiers storage/uploads)"]
    end
    subgraph METIER["Données métier"]
        IMMO["Comptabilité / immobilisations<br/>(21 tables)"]
        MG["Moyens Généraux<br/>(52 tables mg_*)"]
        CLI["Base Clientèle<br/>(46 tables clientele_*)<br/>données personnelles"]
        EER["EER (22 tables eer_*)<br/>module désactivé"]
        FOR["Formation (9 tables)"]
        REC["Réclamations (18 tables)"]
    end
    subgraph INT["Intégrations"]
        INTG["integration_* (9 tables)<br/>fiches, specs OpenAPI,<br/>destinations, exécutions, alertes"]
    end
    USR --> SES
    USR --> ORGT
    USR --> PLT
    AUD --> USR
    NOT --> USR
    CQ --> USR
    METIER --> USR
    METIER --> ORGT
    GED -. "espace_code, module_code,<br/>entity / entity_id" .-> METIER
    PJ --> IMMO
    EER -. "racine ORION" .-> CLI
    REC -. "racine ORION facultative" .-> CLI
    INTG --> ORGT
    INTG --> USR
    classDef sensible fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#1b1b1b;
    classDef normal fill:#e3f2fd,stroke:#1565c0,stroke-width:1px,color:#1b1b1b;
    classDef inactif fill:#f5f5f5,stroke:#757575,stroke-width:1px,stroke-dasharray:2 3,color:#424242;
    class USR,SES,CLI,REC,GED,PJ,AUD,BKP sensible;
    class PLT,OPS,ORGT,NOT,ERR,CQ,IMMO,MG,FOR,INTG normal;
    class EER inactif;
```

*Légende : rouge = domaine à forte sensibilité (identités, données clients, documents, journaux,
sauvegardes) ; bleu = domaine standard ; gris = module désactivé, données conservées. Flèche pleine =
clé étrangère principale ; pointillé = rattachement logique (identifiant ORION ou couple
`entity`/`entity_id`), sans contrainte d'intégrité garantie.*

## 3. Fiches par domaine

| Domaine | Tables (exemples) | Accès applicatif | Dépendances | Risques de confidentialité | Conservation / sauvegarde |
|---|---|---|---|---|---|
| Identités et accès | `users`, `roles`, `permissions`, associations | CORE ADMIN (`core.admin.users`, `.roles`, `.permissions`) ; `/users` (rôle immo `administrateur`) | Toutes les tables métier (auteurs, valideurs) | Hachages bcrypt, secrets TOTP chiffrés, e-mails | Aucune durée de conservation définie ; à confirmer |
| Sessions | `auth_sessions`, `auth_login_attempts`, `password_reset_jtis` | Interne (deps), CORE ADMIN Sessions | `users` | IP, user-agent, identifiants de jeton | Pas de purge identifiée pour les sessions expirées — à confirmer |
| Configuration plateforme | `plateforme_*`, `platform_ops_flags`, `platform_module_versions` | CORE ADMIN ; synchronisation additive du catalogue au démarrage | Gardes d'accès | Faible | Incluses dans les sauvegardes globales |
| Référentiel organisationnel | `departements`, `org_postes`, `org_affectations`, `agences`, `centres_cout` | CORE ADMIN Organisation ; lecture `/organisation/*` | Tous modules via `org_entite_id` | Affectations nominatives | — |
| Traçabilité | `audit_logs`, `notifications`, `api_error_events`, `security_incidents`, `core_query_logs` | CORE ADMIN Audit / Activité / Erreurs | `users` | Valeurs avant / après des objets audités (peuvent contenir des données personnelles), IP | `api_error_events` purgée par tâche planifiée ; aucune politique de rétention pour `audit_logs` — à définir |
| Documents | `ged_documents` + `storage/ged` ; `pieces_jointes`, `archive_*` + `storage/uploads` | `/documents`, `/ged`, archives des modules (permissions `ged.*`, `mg.archives.*`, `archives.general.*`) | Modules métier, OCR | Pièces justificatives, factures, feuilles signées ; texte OCR indexé en clair | Fichiers sur le disque hôte, sauvegardés avec la base par les scripts ; pas de chiffrement au repos |
| Comptabilité / immobilisations | `immobilisations`, `amortissements`, `ecritures_comptables`, `plan_comptable`, `exercices_comptables`, `soldes_compte_orion`, `cessions`, `rebuts`, `reevaluations` | Login 2 `immobilisations` | Référentiels, ORION (saisie de soldes) | Données financières internes | Archives annuelles (`archive_*`), exercice 2025 à ne pas recalculer |
| Moyens Généraux | `mg_articles`, `mg_stock_*`, `mg_achat_*`, `mg_notes_frais`, `mg_contrats`, `mg_points_facturation`, `mg_employee_requests` | Login 2 des modules MG | Org, GED, fournisseurs | Notes de frais nominatives, coordonnées fournisseurs | — |
| Base Clientèle | `clientele_clients`, `clientele_comptes`, `clientele_imports`, `clientele_classifications`, `clientele_kyc`, `clientele_declarations_bcm`, `clientele_declarations_sic`, `clientele_filtrage_*` | Login 2 `clientele`, 23 permissions | Imports ORION (fichiers), référentiels BCM/SIC | **Très élevé** : identité, NIF/NNI, nationalité, comptes, RIB, classification LBC-FT | Aucune suppression d'un client absent d'un import (règle métier) ; rétention non définie |
| EER | `eer_dossiers`, `eer_parties*`, `eer_pieces_identite`, `eer_decisions` | Module désactivé ; tables lues par la SIC | Base Clientèle | **Très élevé** (KYC) | Conservées ; ne pas supprimer |
| Formation | `formation_employes`, `formation_sessions`, `formation_participants` | Login 2 `formation` | GED | Données d'employés | — |
| Réclamations | `reclamations`, `reclamation_comptes`, `reclamation_documents`, `reclamation_evenements` | Login 2 `reclamations` | Base Clientèle, GED | Élevé : client, comptes, opérations contestées | Suppression définitive possible par l'administrateur du module (documentée) |
| Intégrations | `integration_clients`, `integration_fournisseurs`, `integration_destinations`, `integration_executions`, `integration_alertes` | CORE ADMIN Studio (permissions non attribuées) | Org, utilisateurs | Faible : aucune colonne de secret par conception ; extraits de réponse assainis | Rétention d'exécutions documentée à 90 jours, purge non automatique |
| Sauvegardes | `platform_backups` + fichiers `backups/` | CORE ADMIN Continuité | Toute la base | **Très élevé** : copie intégrale | Même disque que la base localement ; externalisation non identifiée |

## 4. Données d'authentification et de configuration

- Politique de sécurité : variables d'environnement, surchargées par `platform_ops_flags.security_policy`
  (en base), chargée en cache mémoire au démarrage (`SecurityPolicyService.ensure_cache`).
- Catalogue des modules et permissions : déclaré dans `backend/app/data/plateforme_catalogue.py`,
  synchronisé de façon additive ; CORE ADMIN reste la source de vérité pour les statuts (exemple
  constaté : `clientele` déclaré `developpement` dans le code, `actif` en base locale).

## 5. Migrations et cohérence du schéma

- 98+ révisions Alembic, une seule tête. Révisions Stock / notifications :
  `20261022_notifications_01` puis `20261022_mg_stock_alertes` (`retour_arriere = compatible`).
- La première révision suppose des tables existantes (issues de l'historique Supabase) : toute
  nouvelle instance doit partir d'un dump restauré, jamais d'une base vide.
- 31 des 93 révisions antérieures au 20/10/2026 contiennent des opérations non additives
  (`docs/deployment/08-livraison-et-mises-a-jour.md`) : un retour arrière de code n'est sûr qu'après
  analyse.

## 6. Points à confirmer

1. Classification des données (public, interne, confidentiel, secret bancaire) et propriétaires
   métier par domaine.
2. Durées de conservation et règles de purge (audit, sessions, OCR, sauvegardes, Base Clientèle).
3. Exigences de chiffrement au repos (base, fichiers, sauvegardes) et de pseudonymisation des copies
   de test (les tests documentés utilisent des copies de la base réelle).
4. Fréquence d'import ORION, responsable de l'extraction et contrôle d'intégrité des fichiers sources.
5. Localisation et protection des fichiers d'analyse nominatifs générés localement
   (`backend/storage/rapports/`, ignoré par Git mais présent sur le poste).
