# Rapport de nettoyage PostgreSQL — BEA DIGITAL

État du 05/11/2026 au soir, dépassé : les trois bases encore listées ci-dessous
(`bea_digital_loadtest`, `bea_digital_stock_test`, `bea_digital_clientele_test`) ont été
archivées puis retirées. Architecture retenue : `docs/audit/RAPPORT_ARCHITECTURE_POSTGRESQL_2_BASES.md`.

Date : 05/11/2026. Exécution du plan `docs/audit/PLAN_NETTOYAGE_POSTGRESQL.md` après
approbation explicite du responsable. Cluster : `bea-postgres`.

## Contrôles préalables

| Contrôle | Résultat |
|---|---|
| Dump frais `backups/bea_digital-frais-20261105-160808/bea_digital.dump` | SHA-256 conforme à `SHA256SUMS` |
| `avant_purge_clientele_20261022_104012.dump` (seule copie restante de la Base Clientèle avec `local-…`) | `pg_restore -l` OK, SHA-256 `65e2349a12d6152f6f631557bd1a9a63f55f18c55a47abf791f4f0d750236a7d` |
| `local-20261021-115657.dump` | `pg_restore -l` OK, SHA-256 `ad685cf080fd7c97214bda2f838728802ee37f1c5f59b03a2dfab862fc695495` |

Empreintes consignées dans `backups/archive/20261105-phase-tests/SHA256SUMS-dumps-clientele-reference`.

## Archives créées (`backups/archive/20261105-phase-tests/`)

| Archive | Taille | `TABLE DATA` / tables | SHA-256 |
|---|---|---|---|
| `bea_digital_phase0_test.dump` | 65 054 128 | 200 / 200 | `e8ae5a5a3918a05d521dc8029aa347590fb20b7386bd5d987e5d7a39b451d33e` |
| `bea_digital_phase2_test.dump` | 65 372 040 | 203 / 203 | `5f01d3d71f0bd40091a1de2dfa4d6e4a6ca8c8ddfea0cbc8db668427bfe9897f` |
| `bea_digital_phase4_test.dump` | 65 424 236 | 206 / 206 | `aa8e638f1ded72e15d32bc1f3a70702f890e5e56121f0b1d08e064bc6ad55eaf` |
| `bea_digital_phase56_test.dump` | 65 903 644 | 210 / 210 | `14715802b04c4a43f0cb7bc689c2fbf0d69a377d01a9a6dd6ee5dcd0c4114d7b` |

`pg_dump` et `pg_restore -l` : code 0 pour chacune ; `alembic_version` présente. ACL Windows
restreinte au compte propriétaire (données clientèle). Hors Git (`backups/*` ignoré).

## Bases supprimées

| Base | Taille avant | Sessions fermées |
|---|---|---|
| `bea_digital_phase0_test` | 855 758 515 | 0 |
| `bea_digital_phase2_test` | 860 575 411 | 0 |
| `bea_digital_phase4_test` | 861 279 923 | 0 |
| `bea_digital_phase56_test` | 866 203 315 | 0 |
| `bea_digital_restore_test` | 39 220 915 | 1 (pgAdmin) |
| **Total libéré** | **≈ 3,48 Go (3 483 038 079 octets)** | |

Liste blanche appliquée ; `DROP DATABASE` code 0 pour chacune.

## État après

Bases restantes : `bea_digital` (51 Mo), `bea_digital_loadtest` (43 Mo),
`bea_digital_stock_test` (23 Mo), `bea_digital_clientele_test` (732 Mo), `postgres`.

| Vérification | Résultat |
|---|---|
| `bea_digital` | head `20261105_mg_stock_mvt_ref_uq`, 211 tables, 63 users, 1 206 immobilisations, 4 465 amortissements, 8 227 mouvements de stock — inchangé |
| `bea_digital_loadtest` | head, 8 467 mouvements — inchangé |
| `http://localhost/health/ready` | 200 |
| Pile loadtest `http://127.0.0.1:8081/health` | 200 |
| `bea-backend`, `bea-worker`, `bea-postgres` | healthy |
| `git status` | aucun fichier de sauvegarde suivi |

Non touchés : volumes Docker (dont `bea_postgres_data` et `bea_lt_pitr_*`), conteneurs,
rôles, configuration PostgreSQL, cluster `bea-lt-pitr`, dumps existants.

## Retour arrière

```
docker exec bea-postgres createdb -U admin -T template0 <base>
docker exec bea-postgres pg_restore -U admin -d <base> /backups/archive/20261105-phase-tests/<base>.dump
```

`bea_digital_restore_test` : relancer `loadtest/validation_sauvegarde.py`.
