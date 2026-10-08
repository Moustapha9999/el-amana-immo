# Phase 0 — Audit d'architecture : Référentiel clients, Imports ORION, Classification

Date : 08/10/2026. Périmètre : Audit, Contrôle & Conformité → Conformité & sécurité financière.
Méthode : lecture du code (`backend/`, `frontend/angular20/`, `docker-compose.yml`), de la
documentation, et requêtes **en lecture seule** sur la base Docker `bea_digital`.
**Aucune table créée, aucune donnée modifiée.**

## 1. État réel constaté

| Élément | Valeur |
|---------|--------|
| Révision Alembic en base | `20261008_admin_powers` (= head du dépôt) |
| Tables `public` | 134 |
| PostgreSQL | 17.11, collation `en_US.utf8`, 38 MB |
| Rôle applicatif | `admin`, **superuser** |
| Tables avec RLS | 0 |
| Agences | 17 (code 5 chiffres, `code_banque = 00007`) |
| Utilisateurs / rôles / permissions | 44 / 50 / 170 |
| Dossiers EER | 6 (dont 2 avec `racine_client`, valeur `004545`) |

`docs/db/schema.sql` et `docs/db/relations.md` datent du 30/09 (révision `20260929`) :
ils **ignorent** `eer_*` (22 tables), `formation_*` (9), `plateforme_domaines`,
`core_query_*`. À régénérer avant la phase 1 (documentation seulement).

## 2. Ce qui existe déjà dans le département

```text
Audit, Contrôle & Conformité (plateforme_espaces : audit-controle-conformite)
└── Conformité & sécurité financière (domaine, actif)
    ├── KYC (sous-domaine, actif)
    │   └── module eer (actif)  — /eer/..., 22 permissions eer.*, 5 rôles
    ├── module formation (actif) — /formation/...
    └── sous-domaines « bientôt » : lbc-ft, fatca, dossiers-clients, demandes-pret,
        declarations-bcm, correspondants-bancaires, verification-procurations
```

Conséquence directe sur l'architecture proposée :

| Bloc proposé | Existant | Décision recommandée |
|--------------|----------|----------------------|
| 5. KYC / EER | Module `eer` complet (workflow, checklist, contrôles, anomalies, compléments, versions, GED cloisonnée, reporting, exports) | **Réutiliser, ne pas refaire.** Brancher plus tard sur le référentiel |
| 1. Référentiel clients + 2. Imports ORION | Rien (aucune table client / compte / RIB) | **Créer** (phase 1-2) |
| 3. Classification | Rien ; `eer_evaluations_risque` = risque **par dossier EER**, pas par client | Créer, rattacher au sous-domaine `lbc-ft` |
| 4. Filtrage & alertes | Rien | Créer plus tard (`lbc-ft`) |
| 6. Reporting BCM | Sous-domaine `declarations-bcm` vide | Créer plus tard |
| Dashboard / Historique | `audit_logs`, `notifications`, reporting EER | Réutiliser le CORE |

## 3. Tables réutilisables

| Table | Usage pour le référentiel | Remarque |
|-------|---------------------------|----------|
| `agences` | `comptes.agence_id` | `agences.code` = **code guichet du RIB** (voir §5) |
| `users` (+ `agence_id`) | importeur, valideur, portée agence | Pattern `eer_access.resolve_eer_access_scope` réutilisable |
| `roles`, `permissions`, `role_permissions`, `user_roles` | nouvelles permissions `{module}.*` | Colonnes `code`, `label`, `module` |
| `plateforme_espaces` / `plateforme_domaines` / `plateforme_modules` / `user_*_acces` | rattachement des nouveaux modules | Domaine n'ouvre aucun droit |
| `audit_logs` | chaque import, validation, export, reclassement | `module_code`, `request_id` |
| `notifications` | fin d'import, rejets, changement de classification | |
| `ged_documents` | stockage du fichier ORION importé (pièce probante) | Cloisonner comme EER (`ged_service.est_cloisonne`) |
| `eer_parties.racine_client`, `eer_dossiers.racine_client` / `numero_compte` | **lien logique** EER ↔ référentiel | Déjà présents, nullable, sans FK |
| `eer_referentiels` | modèle de référentiel paramétrable (domaine/code/libellé/parent) | Pattern à copier, pas à partager |

Infrastructure réutilisable sans nouvelle dépendance : Celery + Redis (`bea-worker`) pour
les imports lourds, `openpyxl` / `xlrd` déjà dans `requirements.txt`, pattern d'import
`formation_imports` (empreinte SHA-256, statuts `ANALYSE → IMPORTE`, ré-import détecté),
`FeedbackService` / `UiDialogService` côté Angular, erreurs standard `api_errors.py`.

## 4. Doublons et confusions à éviter

1. **`soldes_compte_orion` n'est pas un compte client** : soldes des comptes comptables
   d'immobilisations (module immo, 3 lignes). Ne pas réutiliser, ne pas nommer une nouvelle
   table de façon ambiguë (préférer `cl_comptes` / `ref_comptes`).
2. **Deux identités client, deux rôles distincts** :
   - `eer_parties` = données **déclarées** au KYC (fiche, pièces), propres au dossier EER ;
   - futur référentiel = **miroir ORION** (source de vérité bancaire), clé `racine_client`.
   Ne pas fusionner : la comparaison des deux est précisément le contrôle « axe SYSTÈME »
   de l'EER, aujourd'hui `MANUEL` (`eer-matrices.md`, ligne « Vérification données système »).
3. `departements` = organisation immo ≠ `plateforme_espaces` (rappel AGENTS.md).
4. `formation_employes`, `fournisseurs` : identités sans rapport avec la clientèle.

## 5. Règles d'identité confirmées sur les données réelles

```text
RIB 23 car. = 00007 | 00001 | 00000100001 | 59
              banque  guichet  compte (11)   clé
                       │        └─ racine (6) 000001 + suffixe (5) 00001
                       └─ agences.code « AGENCE CENTRALE PARTICULIERS »
```

- Clé RIB vérifiée : `97 − ((89×banque + 15×guichet + 3×compte) mod 97)` = 59 sur l'exemple.
- `code_banque` 00007 = valeur de `agences.code_banque`.

Contrôles d'import possibles **sans hypothèse** : longueur 23, clé RIB, banque = 00007,
guichet ∈ `agences.code`, unicité RIB et compte.

**Correction après analyse de l'extrait réel** ([clientele-phase1.md](clientele-phase1.md)) :
`compte[0:6] = racine` n'est vrai que pour 9 121 comptes sur 59 903 ; les autres ont la
racine précédée d'un `0` (`compte[1:7]`). La racine est toujours lue dans la colonne `CLIENT`,
jamais déduite du numéro de compte.

Types imposés : `racine_client varchar(6)`, `compte varchar(11)`, `rib varchar(23)` —
**jamais d'entier** (zéros de tête). Clients = `COUNT(DISTINCT racine_client)`, comptes =
`COUNT(*)` des comptes.

## 6. Structures à ne pas modifier

| Élément | Raison |
|---------|--------|
| `backend/app/services/amortissement_engine.py`, règle VNC | AGENTS.md §5 |
| Routes immo racine (`/dashboard`, `/comptes`, `/audit`, `/archives`, …) | `LEGACY_ROOT_PATH_SEGMENTS` : **`comptes` et `audit` sont réservés** → le futur écran « Comptes » sera `/{module}/comptes` |
| Socle Login 1 / Login 2, `core.admin.access` | AGENTS.md §7 |
| Tables `eer_*`, moteur `services/eer/`, triggers `trg_eer_*_immuable` | Module en production ; seul ajout envisageable plus tard : lecture du référentiel |
| Cloisonnement GED EER | Pièces KYC hors `/ged/*` |
| `app/` et `alembic/` à la racine | Dette, ne pas y coder |
| Valeurs CORE ADMIN (statuts, ordres, icônes des domaines / modules) | Insertions `ON CONFLICT DO NOTHING`, jamais de réécriture |

## 7. Risques de régression

| Risque | Mesure |
|--------|--------|
| Collision de route avec l'immo | Code module préfixé, entrée dans `module-routing.contract.ts` + `MODULES_WITH_METIER_SHELL` |
| Migration Alembic appliquée à chaud sur 134 tables | Révisions **additives** uniquement, testées sur copie (comme `bea_digital_eer_test`), sauvegarde avant |
| Gros fichier ORION bloquant l'API | Analyse + chargement dans Celery, `COPY` / insertion par lots, table de staging |
| Import rejoué deux fois | Empreinte SHA-256 + date d'arrêté unique |
| Données personnelles de toute la clientèle exposées | Permissions dédiées, portée agence, export audité, pas de données nominatives dans les logs / notifications |
| Lien EER cassé | `racine_client` EER reste nullable, **pas de FK** vers le référentiel (un dossier peut précéder l'import ORION) |
| Sauvegarde module incomplète | Ajouter le scope dans `module_backup_scopes.py` + mapping `audit-controle-conformite` |

## 8. Contraintes FK / ON DELETE

Existant : 156 FK `NO ACTION`, 55 `CASCADE`, 30 `RESTRICT`, 62 `SET NULL`.
Recommandation pour les nouvelles tables (alignée sur EER) :

| FK | ON DELETE |
|----|-----------|
| `comptes.racine_client → clients.racine_client` | RESTRICT |
| `comptes.agence_id → agences.id` | RESTRICT |
| `import_lignes.import_id → imports.id` | CASCADE (staging) |
| `*_historique.client/compte → …` | RESTRICT + trigger d'immuabilité |
| `imports.document_id → ged_documents.id` | SET NULL |
| `*.created_by / valide_par → users.id` | SET NULL |

Aucune suppression physique de client ou compte : un compte absent d'un import est marqué
(`absent_depuis_import_id`), jamais supprimé.

## 9. Stratégie RLS

Identique à EER (`README.md` §RLS) : le rôle `admin` est superuser, une politique RLS serait
contournée. V1 = contrôle strict FastAPI (permission par route + portée agence dans le service).
Phase ultérieure commune à `eer_*` et au référentiel : rôle applicatif non superuser,
`SET LOCAL app.user_id / app.agence_id`, politiques testées sur copie.

## 10. Stratégie de migration

1. Régénérer `docs/db/schema.sql` + `relations.md` depuis la base actuelle.
2. Une révision par bloc, chaînée sur la head courante, `upgrade` / `downgrade` testés sur une
   copie de `bea_digital`, idempotente (`has_table`), **aucun ALTER** sur une table existante
   hormis des insertions (`plateforme_modules`, `permissions`, `roles`).
3. Données de référence chargées par script idempotent (modèle `eer_init_referentiel.py`).
4. Sauvegarde avant application ; `SKIP_MIGRATIONS` reste le mode par défaut.

Esquisse de découpage (à valider en phase 1, noms indicatifs) :

| Révision | Contenu |
|----------|---------|
| `cl_01_referentiel` | `cl_clients` (PK métier `racine_client`), `cl_comptes` (UNIQUE `rib`, UNIQUE `compte`), référentiels |
| `cl_02_imports` | `cl_imports`, `cl_import_lignes` (staging), `cl_import_rejets` |
| `cl_03_historique` | historiques client / compte par import, triggers d'immuabilité |
| `cl_04_module` | module, permissions, rôles, scope de sauvegarde |

## 11. Informations manquantes (bloquantes pour la phase 1)

1. **Un fichier « État des comptes » ORION réel** (ou anonymisé) : colonnes, format
   (xlsx / csv / txt), encodage, séparateur, volume, fréquence. Aucune colonne ne sera inventée.
2. Le **cahier des charges** classification / référentiel cité (absent du dépôt).
3. Codification ORION : type client (PP / PM privée / PM publique / association),
   état du compte, catégorie juridique, agent économique.
4. Définition métier de « client actif ».
5. « Procédure classifications risques clients » (déjà demandée pour l'EER).
6. Placement des nouveaux modules : sous-domaine `dossiers-clients` (existant, « bientôt »)
   ou nouveau sous-domaine « Référentiel clients » ; classification sous `lbc-ft`.
