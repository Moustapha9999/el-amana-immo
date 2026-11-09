# Plan de nettoyage PostgreSQL — BEA DIGITAL

Date : 05/11/2026. Branche : `chore/audit-nettoyage-pre-deploiement` (commit `c2fc26a`).
Statut : **proposition — aucune suppression effectuée**. Toute suppression de base, de volume
ou de fichier attend l'approbation explicite du responsable.

Opérations réalisées pendant cette préparation : un dump `pg_dump -Fc` de `bea_digital`, un
export `pg_dumpall --globals-only`, puis des lectures seules (catalogues, `count(*)`,
`pg_restore -l`, lecture des dumps existants, `pg_dump … | wc -c` sans écriture). Aucune base,
aucun rôle, aucune configuration, aucun volume, aucun conteneur et aucun fichier source n'a été
modifié.

---

## 1. État initial des deux clusters

### `bea-postgres` (cluster de l'application, volume `bea_postgres_data`)

PostgreSQL 17.11 (`postgres:17-alpine`), `archive_mode=off`, `wal_level=replica`,
démarré le 05/11/2026 à 09:35 UTC. Collation `en_US.utf8` partout.

| Base | Taille | Créée vers (UTC) | Révision Alembic | Tables | Sessions au moment de l'analyse |
|---|---|---|---|---|---|
| `bea_digital` | 51 Mo | 08/10/2026 | `20261105_mg_stock_mvt_ref_uq` (head) | 211 | 6 `bea_app` (bea-backend / bea-worker) + pgAdmin |
| `bea_digital_loadtest` | 43 Mo | 05/11/2026 12:48 | head | 211 | 5 `bea_app` (pile `bea-loadtest`) |
| `bea_digital_restore_test` | 37 Mo | 05/11/2026 14:51 | head | 211 | 1 pgAdmin |
| `bea_digital_stock_test` | 23 Mo | 02/11/2026 19:54 | `20261102_mg_stock_periodes_02` | 211 | 0 |
| `bea_digital_clientele_test` | 732 Mo | 19/10/2026 10:10 | `20261020_clientele_14` | 200 | 0 |
| `bea_digital_phase0_test` | 816 Mo | 20/10/2026 19:48 | `20261020_clientele_14` | 200 | 0 |
| `bea_digital_phase2_test` | 821 Mo | 20/10/2026 21:57 | `20261021_integrations_01` | 203 | 0 |
| `bea_digital_phase4_test` | 821 Mo | 21/10/2026 08:43 | `20261021_integrations_02` | 206 | 0 |
| `bea_digital_phase56_test` | 826 Mo | 21/10/2026 10:08 | `20261026_auth_01` | 210 | 0 |

PostgreSQL ne conserve pas la date de création d'une base : elle est estimée par la date du
fichier `base/<oid>/PG_VERSION`.

Vérification des connexions de l'application (mots de passe masqués) :
`bea-backend` → `postgres/bea_digital`, `bea-worker` → `bea_digital`,
`bea-lt-backend` / `bea-lt-worker` → `bea_digital_loadtest`.

### `bea-lt-pitr` (laboratoire PITR de la Validation 4, projet compose `bea-pitr`)

| Élément | État |
|---|---|
| Conteneur | `bea-lt-pitr`, `postgres:17-alpine`, en marche (healthy), `archive_mode=on`, pas en recovery |
| Bases | `postgres` (7,5 Mo), `bea_digital_loadtest` (38 Mo, 0 session, head, 8 467 mouvements, table `pitr_marqueurs`) |
| Volume `bea_lt_pitr_data` | 125 Mo (PGDATA restauré par PITR) |
| Volume `bea_lt_pitr_wal` | 128 Mo (10 segments WAL archivés) |
| Volume `bea_lt_pitr_base` | 77 Mo (`pg_basebackup` de référence `ref/`) |

### Espace disque

- Hôte C: : 43,7 Go libres (91 % utilisé). `backups/` est un montage lié sur C:.
- Disque de la VM Docker : 924,6 Go disponibles. Les bases vivent dans ce disque virtuel ;
  supprimer une base libère de la place **dans** la VM, mais le fichier disque virtuel sur C:
  ne rétrécit pas sans compactage explicite (opération DSI, hors périmètre).

## 2. État de la nouvelle sauvegarde de `bea_digital`

Dossier : `backups/bea_digital-frais-20261105-160808/` (ignoré par Git : `.gitignore` → `backups/*`).

| Fichier | Taille | SHA-256 |
|---|---|---|
| `bea_digital.dump` (`pg_dump -Fc`) | 3 883 367 octets | `4da7ec0d3e9517dc590e41218d7c32546a81895caf5ff35dfdbdf4b2eedfddba` |
| `globals.sql` (`pg_dumpall --globals-only`) | 1 600 octets | `9c6623a04153e13c9d89cc2db232ca2bf73772f607327a23ef27ca43b089e58a` |
| `pg_restore-list.txt` | sommaire du dump | — |
| `SHA256SUMS` | empreintes ci-dessus | — |

Contrôles :

- `pg_dump` et `pg_dumpall` : code retour 0 ; fichiers non vides.
- `pg_restore -l` : code retour 0, 2 080 entrées, 211 `TABLE DATA`, `alembic_version` présente,
  index `uq_mg_stock_mouvements_reference` présent.
- `globals.sql` contient les rôles `admin`, `bea_app`, `bea_core_query_reader`, `immo_user`
  **avec leurs empreintes de mot de passe** : fichier sensible. Droits restreints :
  `chmod 600` côté conteneur et ACL Windows réduite au seul compte `PC-MOUSTAPHA\sallm`
  (héritage supprimé). Ne jamais le copier hors du poste ni dans Git.
- Aucun dump existant n'a été supprimé ni modifié.

## 3. Analyse de chaque base candidate

Méthode : comptage exact (`count(*)`) des tables importantes, puis comparaison **par
identifiants** (et pas seulement par noms de tables) avec les dumps existants :
`avant_purge_clientele_20261022_104012.dump` (`bea_digital` juste avant la purge de la Base
Clientèle, 45 tables `clientele_*`) et `local-20261021-115657.dump` (`bea_digital` complet du
21/10). Les comparaisons ont été faites dans le conteneur, sans afficher de donnée personnelle.

### Comptages (lignes)

| Table | réelle | loadtest | restore | stock | clientele | phase0 | phase2 | phase4 | phase56 |
|---|---|---|---|---|---|---|---|---|---|
| `clientele_clients` | 0 | 0 | 0 | 0 | 42 912 | 42 912 | 42 912 | 42 912 | 42 912 |
| `clientele_classifications` | 0 | 0 | 0 | 0 | 42 250 | 42 250 | 42 250 | 42 250 | 42 250 |
| `clientele_classif_evaluations` | 0 | 0 | 0 | 0 | 57 286 | 56 571 | 56 764 | 56 764 | 56 775 |
| `clientele_classif_evaluation_lignes` | 0 | 0 | 0 | 0 | 1 432 150 | 1 414 275 | 1 419 100 | 1 419 100 | 1 419 375 |
| `clientele_sic_lignes` | 0 | 0 | 0 | 0 | 0 | 78 345 | 78 345 | 78 345 | 78 345 |
| `clientele_comptes` | 0 | 0 | 0 | 0 | 59 902 | 59 902 | 59 902 | 59 902 | 59 902 |
| `clientele_alertes` | 0 | 0 | 0 | 0 | 7 347 | 7 347 | 7 347 | 7 347 | 7 347 |
| `eer_dossiers` | 33 | 0 | 0 | 0 | 60 | 78 | 87 | 87 | 96 |
| `immobilisations` | 1 206 | 1 500 | 1 500 | 0 | 1 206 | 1 206 | 1 206 | 1 206 | 1 206 |
| `amortissements` | 4 465 | 0 | 0 | 0 | 4 458 | 4 448 | 4 448 | 4 448 | 4 448 |
| `mg_stock_mouvements` | 8 227 | 8 467 | 8 467 | 0 | 8 089 | 8 089 | 8 089 | 8 089 | 8 089 |
| `mg_employee_requests` | 0 | 2 422 | 2 422 | 0 | 1 | 1 | 1 | 1 | 1 |
| `users` | 63 | 150 | 150 | 108 | 62 | 95 | 241 | 283 | 723 |
| `audit_logs` | 7 987 | 8 944 | 8 943 | 191 | 7 354 | 10 286 | 10 794 | 10 892 | 12 393 |
| `ged_documents` | 6 | 0 | 0 | 0 | 27 | 29 | 30 | 30 | 33 |

Constat principal : la Base Clientèle (42 912 clients, vraisemblablement issus des fichiers
réels de la banque) **n'existe plus dans `bea_digital`** — elle a été purgée le 22/10/2026
après le dump `avant_purge_clientele_20261022_104012.dump` — et ne subsiste en base que dans
les 5 copies `clientele/phase*`.

### Couverture par les dumps existants (lignes présentes en base mais absentes des dumps)

| Base | Clients | Décisions MANUEL | Évaluations moteur | Dossiers EER | GED | Users | Immos |
|---|---|---|---|---|---|---|---|
| `clientele_test` | 0 / 42 912 | 0 / 3 | 910 | 27 | 3 | 1 | 0 |
| `phase0_test` | 0 | 0 / 3 | 193 | 45 | 5 | 34 | 0 |
| `phase2_test` | 0 | 0 / 3 | 386 | 54 | 6 | 180 | 0 |
| `phase4_test` | 0 | 0 / 3 | 386 | 54 | 6 | 222 | 0 |
| `phase56_test` | 0 | 0 / 3 | 397 | 63 | 9 | 662 | 0 |

Nature des lignes non couvertes (toutes identifiées comme artefacts de tests) :

- **Utilisateurs** : comptes `…@el-amana.mr` de motif `studio-clients-#`, `studio-api-#`,
  `verif-studio-#`, `core-admin-deny-#`, `core-rbac-deny-#`, `cookie-#` (créés par les suites
  de tests CORE / Studio).
- **Documents GED** : `nni.pdf` de 45 octets inactifs (module `eer`), `a.pdf` 13 octets et
  `contrat.pdf` 10 octets (`contrats-echeances`) — fichiers factices de tests.
- **Dossiers EER** : cycles répétitifs `BROUILLON` / `AFFECTE` / `ARCHIVE` par paquets de
  3, 5, 6 ou 7 (un par exécution des tests EER), créés du 19 au 26/10. Le module EER est
  désactivé (`docs/conformite/eer-desactivation.md`).
- **Évaluations moteur** : recalculs automatiques des 19, 20 et 26/10 (tests du moteur de
  scoring), données dérivées et recalculables.
- **Classifications** : sur 42 250, **2** diffèrent du dump (niveau `ELEVE` → `FAIBLE`,
  `mode_decision=MOTEUR`, recalcul le 19/10 à 10:11, une minute après la création de la base).
  Les **3 décisions manuelles** (`MANUEL`, à préserver absolument selon AGENTS.md) sont
  identiques à celles du dump d'avant purge.

### Fiches par base

**`bea_digital_stock_test`** — base synthétique créée le 02/11 (schéma seul, migrée), utilisée par
`backend/tests/test_mg_stock_regularisation_db.py` et `test_mg_stock_recloture_db.py`
(`BASE_TEST = "bea_digital_stock_test"`, tests ignorés sur toute autre base) et citée par
`BEA_STOCK_OCTOBRE_2026_CLOTURE_DIAGNOSTIC.md` et `docs/moyens-generaux/stock-periodes-regularisation.md`.
Données : 108 utilisateurs `@synthetique-stock.test` du 02/11, aucune donnée métier réelle.
Une révision de retard sur le head. Reconstructible (`pg_restore --schema-only` d'un dump de
`bea_digital` + rôles), mais **dépendance active des tests** → à conserver.

**`bea_digital_clientele_test`** — copie de `bea_digital` du 19/10, utilisée par
`scripts/release.ps1` (étape « Tests backend », `DATABASE_URL` réécrite vers cette base) et par
`backend/tests/test_clientele_db.py` / `test_clientele_decision_db.py` (copie `_test` avec
données Base Clientèle). Seule base disposant à la fois des données clientèle et d'un usage
outillé. Données non-test entièrement couvertes par les dumps. **Dépendance active** → à
conserver tant que `release.ps1` n'est pas modifié (modification de source hors périmètre).

**`bea_digital_phase0_test`, `phase2_test`, `phase4_test`, `phase56_test`** — copies jetables des
phases de fiabilisation (20–26/10), citées comme **contexte de preuve** dans
`docs/fiabilite/phase0-etat-initial.md` et `docs/studio-integration-api.md` (migrations
upgrade/downgrade, tests `bea_app`). Aucune référence dans compose, `.env`, scripts ou code :
pas de dépendance active. Aucune session depuis le redémarrage du cluster. Données non-test
couvertes par les dumps ; le reste = artefacts de tests. Les preuves elles-mêmes sont dans la
documentation et le code des tests, pas dans les bases. Chacune pèse ~820 Mo.

**`bea_digital_restore_test`** — produit de la Validation 3 (restauration de
`bea_digital_loadtest`), session pgAdmin ouverte. Preuves conservées dans
`loadtest/reports/validation3-20261105-145057/` (rapport, inventaires source/restauré,
`pg_restore.log`) avec le dump source (`bea_digital_loadtest.dump`, aussi copié dans
`backups/validation3-20261105-145057/`). Recréée à l'identique par
`loadtest/validation_sauvegarde.py` (qui la supprime et la recrée elle-même). Données
synthétiques (copie de loadtest). Aucune dépendance active.

**Hors candidats, rappel** : `bea_digital_loadtest` est la source des Validations 2, 3 et 4 et la
base de la pile `bea-loadtest` (connectée) → à conserver.

### Anomalies relevées

- **Données clientèle vraisemblablement réelles dans 5 copies de test** dont l'ACL de base est
  vide (droit `CONNECT` par défaut pour `PUBLIC`) : `bea_app` peut s'y connecter. Cela
  contredit l'intention de la purge du 22/10. Point de conformité à arbitrer (DSI / conformité).
- Les copies `phase*` ont des révisions Alembic intermédiaires (non head) : elles ne sont plus
  représentatives du schéma actuel.
- `bea_digital_stock_test` a une révision de retard (`20261102_mg_stock_periodes_02`).
- Aucune clé étrangère orpheline recherchée hors `exercices_comptables.archive_dossier_id`
  (traitée sur loadtest en Validation 3).

## 4. Dépendances trouvées

| Base | Références | Type |
|---|---|---|
| `bea_digital_stock_test` | `backend/tests/test_mg_stock_regularisation_db.py`, `test_mg_stock_recloture_db.py`, diagnostic stock octobre, doc stock | **Active (tests)** |
| `bea_digital_clientele_test` | `scripts/release.ps1`, `backend/tests/test_clientele_db.py`, `test_clientele_decision_db.py`, docs conformité, docstrings de 3 migrations | **Active (script de livraison + tests)** |
| `bea_digital_phase0_test` | `docs/studio-integration-api.md` | Documentaire (historique) |
| `bea_digital_phase2_test` | `docs/studio-integration-api.md` | Documentaire |
| `bea_digital_phase4_test` | `docs/studio-integration-api.md` | Documentaire |
| `bea_digital_phase56_test` | `docs/fiabilite/phase0-etat-initial.md` | Documentaire |
| `bea_digital_restore_test` | `loadtest/validation_sauvegarde.py`, `docs/fiabilite/sauvegarde-postgresql.md` | Outil de validation (recrée la base) |

Aucune des bases candidates n'apparaît dans `docker-compose*.yml`, `.env*` ou la configuration
applicative.

## 5. Données uniques identifiées

- **Aucune donnée métier unique** dans les 7 bases candidates : clients, comptes, alertes,
  décisions manuelles, immobilisations et mouvements de stock sont tous présents dans les dumps
  existants (`avant_purge_clientele_20261022_104012.dump`, `local-20261021-115657.dump`).
- Lignes uniques = artefacts de tests (utilisateurs de tests, PDF factices, cycles EER,
  recalculs du moteur, 2 classifications moteur recalculées).
- Point d'attention : les dumps qui couvrent la Base Clientèle (`avant_purge_clientele_…`,
  `local-20261021-…`) deviennent la **seule** copie restante de ces données une fois les bases
  `phase*` supprimées. Ils doivent rester intouchés (voir section 11).

## 6. Bases à conserver

| Base | Raison |
|---|---|
| `bea_digital` | Base réelle de l'application |
| `bea_digital_loadtest` | Pile `bea-loadtest`, source des Validations 2 à 4 |
| `bea_digital_stock_test` | Dépendance active des tests stock (23 Mo) |
| `bea_digital_clientele_test` | Dépendance active de `scripts/release.ps1` et des tests clientèle |

## 7. Bases à archiver puis supprimer

| Base | Taille en base | Archive estimée (mesurée par `pg_dump -Fc \| wc -c`) | Emplacement proposé |
|---|---|---|---|
| `bea_digital_phase0_test` | 816 Mo | 62,0 Mo (mesuré) | `backups/archive/20261105-phase-tests/bea_digital_phase0_test.dump` |
| `bea_digital_phase2_test` | 821 Mo | ~62,5 Mo (estimé) | idem `…/bea_digital_phase2_test.dump` |
| `bea_digital_phase4_test` | 821 Mo | ~62,5 Mo (estimé) | idem `…/bea_digital_phase4_test.dump` |
| `bea_digital_phase56_test` | 826 Mo | 62,9 Mo (mesuré) | idem `…/bea_digital_phase56_test.dump` |

Total archive ≈ 250 Mo sur C: (43,7 Go libres). Justification de l'archivage malgré l'absence
de donnée métier unique : elles sont citées comme contexte de preuve et contiennent des données
clientèle sensibles ; une archive compressée et vérifiée coûte peu et rend la suppression
réversible.

Pour chaque archive :

1. `pg_dump -Fc` vers `backups/archive/20261105-phase-tests/` (montage `/backups`).
2. Contrôle : taille non nulle, `pg_restore -l` code 0, nombre de `TABLE DATA` = nombre de
   tables de la base, présence de `alembic_version`.
3. `SHA-256` consigné dans `backups/archive/20261105-phase-tests/SHA256SUMS`.
4. ACL Windows restreinte au compte propriétaire (données clientèle).
5. Test de restauration : non requis au sens strict (pas de donnée unique). Proposé
   optionnellement sur `phase56_test` uniquement, vers une base temporaire
   `bea_digital_archive_verif` du cluster `bea-lt-pitr` (jamais sur `bea-postgres`), comparaison
   des `count(*)` des tables clés, puis suppression de cette base temporaire.

**Jamais dans Git** : `backups/*` est ignoré ; vérifier `git status` après coup.

## 8. Bases à supprimer sans archive

| Base | Taille | Justification |
|---|---|---|
| `bea_digital_restore_test` | 37 Mo (dump 3,4 Mo) | Copie synthétique de loadtest ; preuves dans `loadtest/reports/validation3-20261105-145057/` ; dump source conservé dans ce dossier et dans `backups/validation3-20261105-145057/` ; recréée à l'identique par `validation_sauvegarde.py`. |

Prérequis : fermer l'onglet pgAdmin connecté à cette base (ou laisser `pg_terminate_backend`
sur cette seule base).

## 9. Volumes Docker concernés

Aucune suppression de volume n'est incluse dans la proposition de suppression des bases.

| Volume | Taille | État | Recommandation |
|---|---|---|---|
| `bea_postgres_data` | 5,05 Go | Cluster de l'application | **Conserver** (jamais `down -v`) |
| `bea_lt_pitr_data` | 125 Mo | PGDATA du laboratoire PITR | Conserver pour l'instant (voir ci-dessous) |
| `bea_lt_pitr_wal` | 128 Mo | 10 segments WAL archivés | idem |
| `bea_lt_pitr_base` | 77 Mo | `pg_basebackup` de référence | idem |
| `464b5109ec02…95ee55` | vide | Volume anonyme créé le 05/11 10:38, attaché à aucun conteneur | Candidat à suppression (décision séparée) |
| `9e186432…`, `801b09b1…` | — | Volumes Redis de `bea-lt-redis` / `bea-redis` | Conserver |

**Recommandation séparée — cluster PITR `bea-lt-pitr`** :

- Preuves de la Validation 4 conservées hors volumes : `loadtest/reports/validation4-20261105-150733/`
  (rapport OK, `pg_basebackup.log`, `restore-pgdata.log`, `recovery-append.conf`,
  `pg_restore-pitr.log`, dump source, journal).
- Reproductible de bout en bout : `docker compose -f loadtest/docker-compose.pitr.yml -p bea-pitr up -d`
  recrée les volumes s'ils n'existent pas, puis `loadtest/validation_pitr.py` recrée la base,
  la sauvegarde de base, les WAL, l'erreur simulée et la restauration (source :
  `bea_digital_loadtest` sur `bea-postgres`).
- Aucune donnée unique (copie synthétique de loadtest + marqueurs PITR).
- Gain : ~330 Mo seulement. Le laboratoire sert aussi de modèle pour l'activation future de
  l'archivage WAL en TEST/PROD (décision DSI).
- **Recommandation** : le conserver tant que la DSI n'a pas tranché la stratégie WAL/PITR
  de TEST/PROD. Ensuite : arrêt (`docker compose -p bea-pitr down`, **sans `-v`**), puis
  suppression explicite des 3 volumes `bea_lt_pitr_*` après nouvelle approbation.

## 10. Espace récupérable estimé

| Action | Espace libéré dans la VM Docker | Espace consommé sur C: |
|---|---|---|
| Suppression des 4 bases `phase*` | ~3,28 Go | +~250 Mo (archives) |
| Suppression de `bea_digital_restore_test` | ~37 Mo | 0 |
| **Total de la proposition** | **~3,3 Go** | **~250 Mo** |
| Optionnel plus tard : laboratoire PITR | ~330 Mo | 0 |
| Optionnel plus tard : `bea_digital_clientele_test` (si `release.ps1` est réorienté) | ~732 Mo | +~62 Mo |

Le volume `bea_postgres_data` passerait d'environ 5,05 Go à environ 1,75 Go. Le fichier disque
virtuel de Docker sur C: ne rétrécit pas automatiquement.

## 11. Procédure sécurisée de suppression et de vérification

À n'exécuter qu'après approbation explicite, base par base, depuis la racine du dépôt.

**Avant**

1. Vérifier que le dump frais existe et correspond à `SHA256SUMS`
   (`backups/bea_digital-frais-20261105-160808/`).
2. Vérifier que `avant_purge_clientele_20261022_104012.dump` et `local-20261021-115657.dump`
   sont intacts : `pg_restore -l` code 0 ; consigner leur SHA-256 dans
   `backups/archive/20261105-phase-tests/SHA256SUMS`.
3. Créer et vérifier les 4 archives (section 7).
4. Contrôler qu'aucune session n'est ouverte sur la base visée :
   `SELECT count(*) FROM pg_stat_activity WHERE datname = '<base>';`

**Suppression** (une base à la fois, jamais `bea_digital`, jamais `bea_digital_loadtest`) :

```sql
-- garde-fou : refuser toute base hors liste approuvée
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '<base>';
DROP DATABASE "<base>";
```

exécuté via `docker exec bea-postgres psql -U admin -d postgres -v ON_ERROR_STOP=1 -c …` avec
le nom de base littéral, comparé à une liste blanche :
`bea_digital_phase0_test`, `bea_digital_phase2_test`, `bea_digital_phase4_test`,
`bea_digital_phase56_test`, `bea_digital_restore_test`.

**Après**

1. `SELECT datname FROM pg_database` : les bases conservées (section 6) sont toutes présentes.
2. `bea_digital` : `alembic_version` = `20261105_mg_stock_mvt_ref_uq`, 211 tables,
   `count(*)` de `users` (63), `immobilisations` (1 206), `mg_stock_mouvements` (8 227) inchangés.
3. Application : `http://localhost/health/ready` OK, `bea-backend` / `bea-worker` sains.
4. Pile loadtest : `http://127.0.0.1:8081` répond, `bea_digital_loadtest` intacte.
5. `git status` : aucun fichier de sauvegarde suivi.
6. Consigner les tailles avant/après (`pg_database_size`) dans un rapport
   `docs/audit/RAPPORT_NETTOYAGE_POSTGRESQL.md`.

**Retour arrière** : `createdb` + `pg_restore` de l'archive correspondante (rôles existants
requis ; `globals.sql` du dossier frais si le cluster est reconstruit), puis
`GRANT CONNECT` si nécessaire.
