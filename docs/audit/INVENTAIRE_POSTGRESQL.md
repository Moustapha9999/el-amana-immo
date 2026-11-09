# Inventaire PostgreSQL — 2026-11-05

Lecture seule. Aucune base supprimée, aucun volume supprimé, aucun
`archive_mode` modifié, aucun service redéployé.
`BEA_STOCK_OCTOBRE_2026_CLOTURE_DIAGNOSTIC.md` n'a pas été touché.

Deux clusters distincts tournent. Une base qui s'appelle
`bea_digital_loadtest` existe **dans les deux**. Ce n'est pas le même
fichier de données.

## 1. Clusters et volumes

| Conteneur | Image | Volume de données | Autres montages | Réglage |
|---|---|---|---|---|
| `bea-postgres` | `postgres:17-alpine`, sain, port `127.0.0.1:5432` | **`bea_postgres_data` — 5,05 Go** | `./backups` → `/backups`, `./database/init` | `archive_mode=off`, `wal_level=replica` |
| `bea-lt-pitr` | `postgres:17-alpine`, sain, port non publié | **`bea_lt_pitr_data` — 131 Mo** | `bea_lt_pitr_wal` 134 Mo, `bea_lt_pitr_base` 80 Mo, `./backups` en lecture | `archive_mode=on` (labo PITR seulement) |

`bea_pgadmin_data` (314 Ko) est la config pgAdmin, pas PostgreSQL.

Volume anonyme `464b5109…` : vide, sans conteneur, créé le 2026-11-05 à
10:38 UTC. Pas un volume de données BEA. On ne le supprime pas dans cet
inventaire.

## 2. Bases de `bea-postgres`

Toutes en UTF-8 / `en_US.utf8`. Connexions observées au moment de la lecture.

| Base | Taille | Tables | Alembic | Connexions | Rôle |
|---|---|---|---|---|---|
| `bea_digital` | 51 Mo | 211 | `20261105_mg_stock_mvt_ref_uq` | `bea_app` depuis `bea-backend` (5) et `bea-worker` (1), pgAdmin | **Base réelle locale.** À conserver. |
| `bea_digital_loadtest` | 43 Mo | 211 | même tête | `bea_app` depuis `bea-lt-backend` (4) et `bea-lt-worker` (1) | Charge et validations 1–2. Source du dump de la validation 3. **Pas** la base réelle. Encore utilisée par la pile `http://127.0.0.1:8081`. |
| `bea_digital_restore_test` | 37 Mo | 211 | même tête | 1 session pgAdmin, aucune application | Cible de la validation 3. L'application a été rétablie ensuite sur `bea_digital_loadtest`. |
| `bea_digital_stock_test` | 23 Mo | 211 | `20261102_mg_stock_periodes_02` | aucune | Copie des tests stock (pytest). Tête Alembic **en retard** d'une révision. |
| `bea_digital_clientele_test` | 732 Mo | 200 | `20261020_clientele_14` | aucune | Copie de test clientèle, octobre. |
| `bea_digital_phase0_test` | 816 Mo | 200 | `20261020_clientele_14` | aucune | Copie de test phase 0. |
| `bea_digital_phase2_test` | 821 Mo | 203 | `20261021_integrations_01` | aucune | Copie de test phase 2. |
| `bea_digital_phase4_test` | 821 Mo | 206 | `20261021_integrations_02` | aucune | Copie de test phase 4. |
| `bea_digital_phase56_test` | 826 Mo | 210 | `20261026_auth_01` | aucune | Copie de test phases 5–6. |
| `postgres` | 7,6 Mo | — | — | session d'inventaire | Base catalogue du serveur. On la garde. |

Les cinq copies `*_test` d'octobre représentent environ **4 Go** des
5,05 Go du volume. Aucune n'a de connexion applicative. Elles ne sont
pas la base réelle, mais ce sont des copies de travail encore présentes.
Décision de conservation, d'archive ou de suppression : **pas prise ici**.

`bea_digital_eer_test` n'existe plus sur ce serveur (un dump du
10/10/2026 porte encore ce nom dans `backups/`).

## 3. Bases de `bea-lt-pitr`

| Base | Taille | Alembic | Connexions | Rôle |
|---|---|---|---|---|
| `bea_digital_loadtest` | 38 Mo | `20261105_mg_stock_mvt_ref_uq` | aucune | Copie restaurée par PITR (validation 4), sur **un autre volume**. L'erreur volontaire en a été retirée. Ne pas la confondre avec `bea_digital_loadtest` de `bea-postgres`. |
| `postgres` | 7,5 Mo | — | session d'inventaire | Catalogue de ce cluster. |

La pile de charge ne pointe pas vers ce cluster. Elle pointe vers
`bea-postgres` / `bea_digital_loadtest`.

## 4. Qui utilise quoi

| Processus | Cible |
|---|---|
| `bea-backend`, `bea-worker` | `bea-postgres` / **`bea_digital`** |
| `bea-lt-backend`, `bea-lt-worker` | `bea-postgres` / **`bea_digital_loadtest`** |
| `bea-frontend`, `bea-lt-frontend` | aucun accès SQL (nginx) |
| `bea-pgadmin` | sessions idle sur `bea_digital` et `bea_digital_restore_test` |
| `bea-lt-pitr` | aucune application |

## 5. Sauvegardes déjà sur le disque

Dossier `backups/`, non versionné. 44 fichiers `.dump` ou `.sql`.
Les plus gros dumps datent d'octobre (environ 55 à 61 Mo) :
`local-20261021-115657.dump`, `avant_purge_clientele_20261022_104012.dump`,
série `avant_reclamations_*`, `pre_org_20261014_163711.dump`,
`pre_user_cleanup_20261014_185030.dump`.

Le dump le plus récent dont le nom vise `bea_digital` est
`bea_digital_avant_stock_periodes_02_20261102_2126.dump` (3,6 Mo,
2 novembre). Il est **antérieur** à la révision
`20261105_mg_stock_mvt_ref_uq` et aux validations du 5 novembre.

Les dumps du 5 novembre sont ceux de la **base de charge**, pas de la
base réelle :

- `backups/validation3-20261105-145057/` — restauration logique réussie
- `backups/validation3-20261105-144610/` — tentative précédente (clé étrangère orpheline du seed)

Il n'y a pas, dans `backups/`, de `pg_dump` de `bea_digital` pris après
le commit `c2fc26a`. Il n'y a pas non plus de `pg_dumpall --globals-only`
conservé (les hachages de rôles n'ont pas été écrits dans le rapport de
la validation 3).

## 6. Ce qu'il faudrait avant tout nettoyage

Pas exécuté. À décider ensuite :

1. Un `pg_dump -Fc` frais de **`bea_digital`**, plus `pg_dumpall --globals-only`, vérifiés avec `pg_restore -l`, copiés hors du volume `bea_postgres_data`.
2. Ne rien drop tant que `bea-lt-backend` est connecté à `bea_digital_loadtest`.
3. Ne pas supprimer `bea_lt_pitr_data`, `bea_lt_pitr_wal` ni `bea_lt_pitr_base` en même temps que la base de charge : ce sont le labo PITR.
4. Les copies `phase*`, `clientele_test` et `stock_test` ne sont pas branchées. Les archiver ou les supprimer est une décision séparée, après le dump du point 1.
5. `bea_digital_restore_test` n'est plus utilisée par l'application. Son contenu est déjà dans le dump de validation 3 réussi. Même réserve : pas de `DROP` dans cet inventaire.

## 7. Hors périmètre de cette lecture

`immo_user` superutilisateur, séparation données / WAL / sauvegardes sur
Ubuntu, et `archive_mode` sur `bea-postgres` restent des décisions DSI.
Le cluster réel reste `archive_mode=off`.
