# Sauvegarde PostgreSQL — stratégie logique (validation 3)

CORE ADMIN (`/admin/sauvegardes`) n’est pas dans ce périmètre : ses
sauvegardes applicatives restent indépendantes.

## Environnement

PostgreSQL **17** tourne dans le conteneur Docker `bea-postgres`
(`postgres:17-alpine` du compose racine). Ce n’est pas une installation
Windows. Volume unique `bea_postgres_data`. Une seule instance, **deux**
bases applicatives (plus la base système `postgres`) :

| Base | Rôle |
|---|---|
| `bea_digital` | Base réelle de l’application — **intouchable** |
| `bea_digital_test` | Base de test unique : tests, charge, validations, répétitions (`scripts/test-db.ps1`) |

## Méthode validée

Sauvegarde logique `pg_dump -Fc` (format personnalisé), restauration
`pg_restore` dans une **nouvelle** base — jamais par-dessus `bea_digital`
ni `bea_digital_test`. `loadtest/validation_sauvegarde.py` restaure dans
`bea_digital_restauration_tmp`, contrôle, puis supprime cette base.

```text
pg_dump -U admin -Fc -d bea_digital_test -f bea_digital_test.dump
createdb bea_digital_restauration_tmp
pg_restore --dbname=bea_digital_restauration_tmp bea_digital_test.dump
GRANT CONNECT, TEMPORARY ON DATABASE bea_digital_restauration_tmp TO bea_app;
```

`scripts/test-db.ps1` construit lui-même `bea_digital_test` par
`pg_dump` de `bea_digital` puis `pg_restore` : chaque reconstruction de la
base de test prouve donc aussi que le dump de la base réelle se restaure.

`pg_dump` d’une base **ne contient pas** les rôles globaux du serveur
(`admin`, `bea_app`, `bea_core_query_reader`, …) ni le `GRANT CONNECT`
sur l’objet DATABASE. Pour reconstruire un cluster vide :

1. `pg_dumpall --globals-only` (rôles et mots de passe) **avant**
2. `createdb` + `pg_restore` du dump de base
3. `GRANT CONNECT` au rôle applicatif

Sur le même serveur (cas de la validation 3), les rôles existent déjà ;
seul le `GRANT CONNECT` sur la nouvelle base est à rejouer.

## Contrôles après restauration

Tables, vues, fonctions, PK / FK, UNIQUE (y compris
`uq_mg_stock_mouvements_reference`,
`uq_mg_stock_mouvements_cle_idempotence`,
`ix_mg_employee_requests_number`), index, séquences et `last_value`,
extensions, révision `alembic_version`, privilèges `bea_app`, comptages
de lignes. Puis reconnexion de la pile isolée (`http://127.0.0.1:8081`)
à la base restaurée : Login 1, Login 2, lectures module.

Preuve : `loadtest/reports/validation3-*/rapport.md`.

## Constat sur `bea-postgres` (instance locale)

| Élément | Valeur |
|---|---|
| Conteneur | `bea-postgres`, image `postgres:17-alpine`, `command: postgres` |
| Entrypoint | `docker-entrypoint.sh` (aucun `command` custom dans le compose) |
| `PGDATA` | `/var/lib/postgresql/data` |
| Volume | nommé `bea_postgres_data` → `/var/lib/docker/volumes/bea_postgres_data/_data` |
| Conf | `postgresql.conf` + `postgresql.auto.conf` **dans le volume** (pas de fichier monté depuis le dépôt) |
| `wal_level` | `replica` (défaut) |
| `archive_mode` | **`off`** (défaut) — aucun WAL n’est copié hors de `pg_wal` |
| `archive_command` | `(disabled)` |
| Bind mounts | `./backups` → `/backups`, `./database/init` → `/docker-entrypoint-initdb.d` |

PITR est une opération **de cluster**, pas de base. Un `pg_basebackup` de
`bea-postgres` emporterait `bea_digital` et toutes les bases de test du
même volume. Restaurer ce backup dans `bea_postgres_data` **écraserait**
`bea_digital`. On n’active donc **pas** `archive_mode` sur `bea-postgres`.

## Sauvegardes physiques + WAL + PITR (validation 4)

Cluster **dédié** `bea-lt-pitr` (`loadtest/docker-compose.pitr.yml`), recréé
à la demande par `loadtest/validation_pitr.py` puis retiré après usage
(`docker compose -p bea-pitr -f loadtest/docker-compose.pitr.yml down`, puis
suppression explicite des volumes `bea_lt_pitr_*`) :

| Volume | Rôle |
|---|---|
| `bea_lt_pitr_data` | PGDATA du labo (jamais `bea_postgres_data`) |
| `bea_lt_pitr_wal` | Archives WAL **hors** du volume de données |
| `bea_lt_pitr_base` | Copie `pg_basebackup` |

`archive_mode=on` et `archive_command` (copie vers `/wal-archive`) sont
passés en arguments de `postgres`, uniquement sur ce conteneur.
`archive_timeout=10` pour le labo ; en banque on choisira une valeur DSI.

Chaîne validée :

1. Charger `bea_digital_test` (dump logique) dans le cluster isolé.
2. `pg_basebackup -Fp -Xs` = sauvegarde physique de référence.
3. Transactions « bonnes », puis erreur métier volontaire.
4. Arrêt, remplacement de PGDATA par le basebackup, `recovery.signal` +
   `restore_command` + `recovery_target_time` **avant** l’erreur.
5. Reconnexion de la pile isolée (`http://127.0.0.1:8081`) au cluster
   restauré, puis retour sur `bea-postgres` / `bea_digital_test`.

Preuve : `loadtest/reports/validation4-*/rapport.md`.

Pour TEST/PROD banque : même schéma (volume données ≠ volume WAL ≠
stockage des basebackup), hors du disque de l’hôte applicatif, à
définir avec la DSI. Image Debian `postgres:17`, pas Alpine.
