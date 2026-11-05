# Audit PostgreSQL — `bea_digital` (lecture seule)

Date : 2026-11-05. Cluster : conteneur `bea-postgres`, PostgreSQL **17.11**,
image `postgres:17-alpine`. Aucun `INSERT`, `UPDATE`, `DELETE`, `ALTER`,
`DROP`, `pg_restore` ni changement de `postgresql.conf`.

`archive_mode` reste **off**. Les volumes n’ont pas été touchés.

## A. Migrations

| Contrôle | Résultat |
|---|---|
| `alembic_version` | une ligne : `20261105_mg_stock_mvt_ref_uq` |
| Fichier | `backend/alembic/versions/20261105_mg_stock_mvt_reference_unique.py` (non commité) |
| Révisions canoniques | 103 fichiers |
| Révisions dette `alembic/` racine | 13 — ne pas les appliquer sur cette base |

La tête de la base réelle est la migration d’unicité des références de
mouvements. Écart schéma / fichiers Alembic non rejoué au-delà de cette tête
(pas de `alembic check` : il écrirait éventuellement l’historique). La tête
SQL et le fichier portent le même identifiant.

## B. Numérotation

Mécanisme applicatif : `backend/app/services/sequences.py`
(`pg_advisory_xact_lock` par préfixe et année). Non modifié ici.

Index présents sur `bea_digital` :

| Index | Définition |
|---|---|
| `uq_mg_stock_mouvements_reference` | UNIQUE sur `mg_stock_mouvements.reference` |
| `uq_mg_stock_mouvements_cle_idempotence` | UNIQUE partiel si `cle_idempotence` non nulle |
| `ix_mg_employee_requests_number` | UNIQUE sur `mg_employee_requests.request_number` |

Doublons : **0** référence de mouvement, **0** numéro de demande, **0** clé
d’idempotence en double.

## C. Idempotence

Colonne `mg_stock_mouvements.cle_idempotence` + index ci-dessus.
Rejeu HTTP : middleware Redis (`Idempotent-Replayed` / `409 DUPLICATE_REQUEST`),
prouvé en validation 2 sur la base isolée, pas rejoué sur `bea_digital`.

## D. Intégrité

| Contrôle | Résultat |
|---|---|
| Tables `public` | 211 |
| Clés primaires | 211 |
| Clés étrangères | 537 |
| Index invalides | 0 |
| `exercices_comptables.archive_dossier_id` orphelin | **0** |

L’orphelin vu en validation 3 venait du seed `bea_digital_loadtest`
(`exercices_comptables` copié sans `archive_dossiers`). Il n’est pas dans
`bea_digital`.

Volumes de lignes (`pg_stat_user_tables`, estimations) : `api_error_events`
13 576, `audit_logs` 7 912, `mg_stock_soldes` 4 022, `auth_sessions` 2 827,
`mg_stock_mouvements` 138, `users` 62. Aucune table métier « géante » au
sens d’un problème d’index à traiter dans ce lot. Pas de `DROP INDEX`.

## E. Connexions et rôles

| Réglage | Valeur |
|---|---|
| `max_connections` | 100 |
| `wal_level` | replica |
| `archive_mode` | off |
| `WEB_CONCURRENCY` | 4 |
| Pool par processus | 5 + 5 overflow |

Plafond applicatif indicatif : 4 × (5+5) = 40 connexions backend, plus le
worker et pgAdmin. Sous 100. Inchangé.

| Rôle | Superuser | Login |
|---|---|---|
| `admin` | oui | oui |
| `bea_app` | non | oui |
| `bea_core_query_reader` | non | non |
| `immo_user` | **oui** | non |

`bea_app` est le compte de l’API (documenté, non superuser). `immo_user`
superuser est un écart de durcissement. **Aucune modification de rôle.**

## F. Performance

`pg_stat_statements` n’a pas été consulté (extension non listée sur le
catalogue des extensions du cluster de charge ; non activée pour cet audit).
Pas de création ni suppression d’index.

## Modifications

| | |
|---|---|
| Proposées | Revoir `immo_user` avec la DSI. Ne pas activer `archive_mode` ici. Garder verrou + UNIQUE. Séparer plus tard données / WAL / basebackup sur Ubuntu. |
| Appliquées sur `bea_digital` pendant cet audit | **Aucune.** |
