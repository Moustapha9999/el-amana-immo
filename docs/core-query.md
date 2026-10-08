# CORE QUERY — Data Explorer CORE ADMIN

Interrogation de la base BEA DIGITAL **en lecture seule**, depuis CORE ADMIN
(Login 1). Trois modes : Assistant (question en français), Query Builder
(sans SQL), SQL (édition directe). Historique, favoris, exports Excel / PDF /
CSV. Aucun LLM externe : la compréhension est un moteur de règles
déterministe qui s'appuie sur le schéma réel.

## Pipeline

```
question / builder / SQL
  → analyse (NL Parser | Query Builder)
  → tables et colonnes identifiées (catalogue introspecté)
  → génération SQL (côté serveur)
  → validation (validateur lecture seule)
  → permissions
  → exécution (transaction READ ONLY, timeout, rôle restreint, LIMIT)
  → résultats + journal core_query_logs + audit_logs
```

Pour les modes Assistant et Builder, **le serveur régénère toujours le SQL**
à partir de la question ou de la spécification : le navigateur ne peut pas
injecter son propre SQL dans ces modes. Si le SQL affiché à l'utilisateur
diffère du SQL régénéré (date relative passée minuit, par exemple), la
requête est refusée (`STALE`) et l'utilisateur doit relancer « Analyser ».

## Composants (backend `app/services/core_query/`)

| Composant | Fichier | Rôle |
| --- | --- | --- |
| Schema knowledge | `schema.py` | tables, colonnes, types, PK, FK, enums (cache 5 min) ; secrets masqués |
| NL Parser | `nl_parser.py` | dates relatives, plages horaires, intentions métier, moteur générique |
| Query Builder | `builder.py` | spécification JSON → SQL, jointures via FK réelles uniquement |
| SQL Validator | `validator.py` | analyse lexicale + règles lecture seule |
| Permission Checker | `service.py` | `core.admin.query.*` (endpoint + mode SQL) |
| Query Executor | `executor.py` | READ ONLY, `statement_timeout`, rôle restreint, LIMIT, rollback |
| Audit Logger | `service.py` | `core_query_logs` + `record_audit` (`core_query_execute`, `core_query_refused`, `core_query_error`, `core_query_export`) |

## Sécurité

1. **Validateur** :
   - une seule requête, commençant par `SELECT` ou `WITH` ;
   - mots-clés interdits partout : `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `COPY`, `SET`, `INTO`, `FOR SHARE`/`FOR UPDATE`… ;
   - fonctions sur liste blanche (agrégats, dates, texte, fenêtrage) : `pg_sleep`, `set_config`, `current_setting`, `pg_read_file`… sont refusées ;
   - tables du schéma `public` présentes dans le catalogue uniquement (pas de `pg_catalog`, ni `information_schema`) ;
   - colonnes qualifiées vérifiées contre le schéma (une colonne inventée est refusée) ;
   - colonnes secrètes refusées (`hashed_password`, `totp_secret`, `refresh_jti`…), de même que `SELECT *` et la référence ligne entière sur les tables qui les contiennent ;
   - tables `password_history`, `password_reset_jtis` et `alembic_version` non interrogeables.
2. **Exécution** :
   - transaction `READ ONLY`, `statement_timeout` de 15 s, `lock_timeout` de 2 s, `search_path = public` ;
   - résultat enveloppé dans `LIMIT` : 500 lignes par défaut, 5 000 au maximum à l'écran, 20 000 en export Excel / CSV et 2 000 en PDF ;
   - toujours suivie d'un `ROLLBACK`.
3. **Rôle PostgreSQL restreint** `bea_core_query_reader` (NOLOGIN) :
   - créé et synchronisé automatiquement quand l'empreinte du schéma change ;
   - reçoit `SELECT` colonne par colonne, secrets exclus ;
   - l'exécution passe par `SET LOCAL ROLE`, de sorte qu'une requête qui contournerait le validateur se heurte au refus de PostgreSQL.

### Mode administrateur (SQL libre, écriture)

Case « Mode administrateur » de l'écran SQL, réservée à `core.admin.query.admin`.
Toute requête est acceptée : `SELECT` sur toutes les tables et colonnes (secrets
inclus), `INSERT`/`UPDATE`/`DELETE`, DDL (`CREATE`, `ALTER`, `DROP`,
`TRUNCATE`…), scripts multi-instructions (200 000 caractères maximum).

- **Seuls refus** : accès serveur (`COPY`, `ALTER SYSTEM`,
  `CREATE/DROP/ALTER DATABASE`, `LOAD`, `pg_read_file`, `pg_ls_*`, `lo_import`,
  `dblink`, `pg_reload_conf`…) et contrôle de transaction (`BEGIN`, `COMMIT`,
  `ROLLBACK`, `SAVEPOINT`…), puisque l'exécution gère elle-même la transaction.
- **Exécution** : une transaction, `statement_timeout` de 120 s,
  `lock_timeout` de 10 s. `COMMIT` en cas de succès. En cas d'erreur, `ROLLBACK`
  complet : aucune donnée n'est modifiée.
- **Simuler** : exécute la requête puis fait un `ROLLBACK`, ce qui affiche la
  commande et le nombre de lignes touchées sans rien enregistrer.
- **Exécuter une écriture** : motif obligatoire (au moins 5 caractères,
  `REASON_REQUIRED` sinon), demandé dans une boîte de confirmation.
- **Journal** : `core_query_logs` (`admin_mode`, `dry_run`, `command_tag`,
  `reason`) et audit `core_query_admin_execute` / `core_query_admin_simulate` /
  `core_query_admin_export` / `core_query_admin_refused` / `core_query_admin_error`
  (motif, commande, lignes touchées, SQL tronqué à 4 000 caractères).
- Migration : `20261008_admin_powers`.

### Note DSI (TEST / PROD)

Le compte applicatif doit pouvoir créer le rôle (`CREATEROLE`) et accorder
`SELECT` sur les tables (propriétaire des tables). Sinon :

- CORE QUERY continue en mode « transaction lecture seule » derrière le
  validateur ;
- l'écran indique « Rôle restreint indisponible » ;
- la DSI peut créer le rôle une fois avec un compte propriétaire :

```sql
CREATE ROLE bea_core_query_reader NOLOGIN;
GRANT bea_core_query_reader TO <compte_applicatif>;
GRANT USAGE ON SCHEMA public TO bea_core_query_reader;
-- puis SELECT par table / colonnes non secrètes (voir executor.ensure_reader_role)
```

## Permissions

| Code | Effet |
| --- | --- |
| `core.admin.query.view` | écrans, schéma, analyse, génération SQL, historique personnel, favoris |
| `core.admin.query.execute` | exécution Assistant / Builder / favoris |
| `core.admin.query.sql` | exécution du SQL libre (et favoris SQL) |
| `core.admin.query.export` | exports Excel / PDF / CSV |
| `core.admin.query.admin` | mode administrateur : SQL sans restriction, écriture (superuser : implicite) |

L'historique de tous les administrateurs exige en plus `core.admin.audit`
(ou superuser). Le MFA CORE ADMIN s'applique (politique de sécurité).

## Tables

- `core_query_logs` : utilisateur, source, question, SQL, tables, statut
  (`success` | `refused` | `error`), code et message d'erreur, nombre de
  résultats, troncature, durée, format d'export, IP, date. La table
  `audit_logs` garde la trace transverse ; ce journal dédié porte les champs
  propres aux requêtes (SQL complet, durée, nombre de lignes).
- `core_query_favorites` : favoris personnels et favoris système
  (`is_system`, partagés). Six favoris système sont créés par la migration.

Les deux tables sont des journaux CORE : jamais écrasées par un recovery module
ou département (`SHARED_CORE_TABLES`) ; `core_query_logs` survit à un recovery
global (`GLOBAL_RESTORE_JOURNAL_TABLES`).

## Questions reconnues (exemples)

- utilisateurs connectés hier entre 8h et 17h → `auth_sessions` (Login 1), créneau horaire ;
- utilisateurs actuellement actifs → sessions non révoquées et non expirées ;
- pas connectés depuis N jours / jamais connectés → `users.last_login_at` ;
- combien d'utilisateurs, immobilisations par agence, valeur totale des immobilisations → moteur générique ;
- demandes de stock en attente → `mg_demandes_fourniture` (SOUMIS, VISA_AGENCE, VISA_MG, PREPARATION) ;
- dernières opérations administratives → `audit_logs` du module `core` ;
- dernières connexions au module X → sessions Login 2 du module ;
- documents ajoutés aux archives ce mois-ci → `archive_fichiers` ;
- modules les plus utilisés aujourd'hui → connexions Login 2 par module ;
- sessions de plus de 8 heures, activité des administrateurs, tentatives échouées.

Si la question est ambiguë (module homonyme, regroupement inconnu, objet non
identifié), l'assistant demande une précision au lieu d'exécuter. Les
hypothèses retenues sont affichées dans « Compréhension » avant toute
exécution.

## Tests

`backend/tests/test_core_query.py` couvre les refus du validateur, les
acceptations, le parseur sur les exemples ci-dessus (colonnes vérifiées contre
le schéma), le builder (jointures FK, échappement LIKE), le rôle restreint et
l'API (exécution, refus, historique, tableau de bord, export, favoris).
