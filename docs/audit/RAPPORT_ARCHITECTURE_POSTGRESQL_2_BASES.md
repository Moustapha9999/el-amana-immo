# Architecture PostgreSQL — deux bases

Date : 05/11/2026. Clôture du chantier de structuration et de nettoyage PostgreSQL.
Cluster `bea-postgres` (PostgreSQL 17, volume `bea_postgres_data`). `archive_mode` inchangé
(`off`). CORE ADMIN non modifié.

## État final

Bases applicatives, et seulement celles-là :

| Base | Rôle | Contrôle |
|---|---|---|
| `bea_digital` | Production. Application officielle. | head `20261105_mg_stock_mvt_ref_uq`, 211 tables, 0 client, 63 utilisateurs, 63 empreintes de mot de passe distinctes, 1 206 immobilisations, 4 465 amortissements, 8 227 mouvements. `bea_app` ne peut pas effacer `audit_logs`. |
| `bea_digital_test` | Test unique : pytest, charge, validations, répétitions. Reconstruite par `scripts/test-db.ps1`. | Même head, 211 tables. Copie de `bea_digital`, puis Base Clientèle du dump protégé (42 912 clients, 3 décisions `MANUEL` dans `clientele_classifications`). Accès neutralisés, module EER toujours `inactif`. Après le seed de charge : 213 comptes, 2 706 immobilisations, 8 783 mouvements, 0 session. |

La base système `postgres` reste (catalogue du cluster). Ce n’est pas une base applicative.

`http://localhost/health/ready` et `http://127.0.0.1:8081/health` répondent 200.

## Comment `bea_digital_test` est construite

`scripts/test-db.ps1` (appelé par `loadtest/setup-env.ps1 -Recreer`) :

1. `pg_dump -Fc` de `bea_digital`, puis `pg_restore` dans une base neuve `bea_digital_test` (même collation).
2. Rechargement des seules tables `clientele_*` vides, depuis `backups/avant_purge_clientele_20261022_104012.dump`.
3. Neutralisation : mot de passe aléatoire, TOTP effacé, sessions et historique de mots de passe vidés, limites de débit de `security_policy` retirées.
4. Compte `admin@el-amana.mr` : mot de passe `BEA_TEST_PASSWORD`, sinon `Admin@2026`, `must_change_password = false`.
5. `GRANT DELETE` sur `public.audit_logs` pour `bea_app`, **dans cette base seulement** (les tests de stock retirent leurs lignes d’audit). En production ce droit reste absent.

La pile de charge (`loadtest/`) et `scripts/release.ps1` pointent vers `bea_digital_test`. Locust n’écrit que sur les articles synthétiques `LT*`.

## Tests

Suite complète sur `bea_digital_test`, après reconstruction : **1 733 réussites, 11 échecs, 24 ignorés** (1 h 12).

Les quatre échecs hors facturation (hub EER, login module EER, deux cycles du service EER) venaient du module désactivé : il disparaît du hub, son login répond 404, et les droits `eer.*` ne sont résolus que si le module est actif. Les tests l’acceptent désormais ; le cycle dossier réactive le module dans sa transaction, annulée au rollback. Rejoués ensuite : les quatre passent. Le module reste `inactif` / `is_active = false`.

Échecs connus, déjà présents sur une copie de `bea_digital` : les 7 tests `test_mg_facturation_phase3` et `test_mg_facturation_profils`. Ils attendent les profils fournisseurs (`MATTEL_SMS`, `SNDE`, `RIMATEL`, `SOMELEC`, …) qui ne sont plus dans la base réelle. Ils ne sont pas corrigés par des données de production inventées.

Plusieurs tests s’ignorent avec « Base PostgreSQL indisponible » au milieu de la suite longue (moteur global et boucle d’événements). Relancés seuls, ils se connectent. La base était bien là.

Une campagne de charge courte et la validation sauvegarde avaient déjà réussi plus tôt le même soir sur cette base (`loadtest/reports/20261105-192324-20u`, `loadtest/reports/validation3-20261105-192450`). La base temporaire `bea_digital_restauration_tmp` a été supprimée. Elles n’ont pas été rejouées après la reconstruction finale. L’ACL du dump de ce rapport (données clients) est limitée au compte propriétaire.

## Archives puis suppressions

Dossier `backups/archive/20261105-bases-historiques/` (hors Git, ACL limitée au compte propriétaire). `pg_dump -Fc` et `pg_restore -l` code 0, `alembic_version` présente.

| Archive | Taille | SHA-256 |
|---|---|---|
| `bea_digital_loadtest.dump` | 3 583 094 | `260bcb0d722b5620e0122fd968befb5edf5869614bbcdac621c366f7e89436e5` |
| `bea_digital_stock_test.dump` | 1 023 249 | `d8492c476fd6d9973074851fd522a7f78765f633a08c07128eec9770f57f5efd` |
| `bea_digital_clientele_test.dump` | 59 503 171 | `bed9750a23a6e8e5fb3de07cc62476bb9997886ba3a3f5bdb1b9511e26f7b4b3` |

Aucune session. `DROP DATABASE` sur ces trois noms seulement, après contrôle que `bea_digital` et `bea_digital_test` étaient présentes. `bea_digital` identique avant et après (mêmes comptes que le tableau ci-dessus).

Laboratoire PITR : conteneur `bea-lt-pitr` arrêté et supprimé, volumes `bea_lt_pitr_data`, `bea_lt_pitr_wal`, `bea_lt_pitr_base` supprimés. Pas de `docker compose down -v` sur le compose racine. Le script `loadtest/validation_pitr.py` et `loadtest/docker-compose.pitr.yml` restent pour recréer le laboratoire à la demande. Le volume anonyme `464b5109ec02…` est toujours là, inutilisé ; il n’a pas été supprimé.

Dumps protégés toujours présents : `avant_purge_clientele_20261022_104012.dump`, `local-20261021-115657.dump`, ainsi que les archives du nettoyage précédent (`backups/archive/20261105-phase-tests/`).

## Compromis de la base de test

C’est une copie des données réelles, avec la Base Clientèle. Les mots de passe copiés sont remplacés, mais le mot de passe du compte admin de test est connu (`Admin@2026` par défaut) et les comptes `lt.*@loadtest.example.com` ont le mot de passe de `loadtest/.env.loadtest`. Cette base ne doit pas être exposée comme la production.

## Retour arrière des trois bases retirées

```text
docker exec bea-postgres createdb -U admin -T template0 <base>
docker exec bea-postgres pg_restore -U admin -d <base> /backups/archive/20261105-bases-historiques/<base>.dump
```

Jamais sur `bea_digital`.
