# Audit initial — BEA DIGITAL

Date : 2026-11-05. Branche : `chore/audit-nettoyage-pre-deploiement`
(créée depuis `main` à `484f5db`, **sans commit**). Le travail non commité
des validations 1 à 4 est conservé tel quel.

Périmètre : inventaire et classification. Aucune donnée `bea_digital`,
aucun volume Docker, aucun secret.

## État du dépôt

| Mesure | Valeur |
|---|---|
| Fichiers suivis par Git | 1 399 |
| Fichiers de travail hors `node_modules`, `.venv`, `dist`, caches | 2 389 |
| Python (hors caches) | 736 |
| TypeScript | 361 |
| Markdown | 85 |
| SQL | 20 |
| Révisions Alembic canoniques | 103 (`backend/alembic/versions/`) |
| Révisions Alembic dette | 13 (`alembic/versions/` à la racine) |
| Tests backend | 132 fichiers `backend/tests/test_*.py` |
| Documentation | 70 fichiers `docs/**/*.md` |

Arborescence utile :

| Dossier | Rôle |
|---|---|
| `backend/` | API canonique (FastAPI, Alembic, Celery) |
| `frontend/angular20/` | SPA Angular 20 |
| `frontend/` | Dockerfile nginx |
| `database/` | `init/01-extensions.sql`, rôle `bea_app` |
| `deployment/` | Compose prod, scripts DSI, nginx TLS |
| `docs/` | Architecture, déploiement, conformité, fiabilité |
| `loadtest/` | Charge, reprise, sauvegarde, PITR (isolé) |
| `scripts/` | Restauration dump, opérations locales |
| `app/` + `alembic/` + `Dockerfile` racine | **Dette** : ne pas déployer (AGENTS.md) |

## Validations déjà faites (preuves conservées)

| Validation | Preuve | Git |
|---|---|---|
| 1 Charge | `loadtest/reports/20261105-*` | ignoré |
| 2 Reprise | `loadtest/reports/validation2-20261105-133023/` | ignoré |
| 3 Dump / restore | `loadtest/reports/validation3-20261105-145057/` | ignoré |
| 4 PITR | `loadtest/reports/validation4-20261105-150733/` | ignoré |

Scripts reproductibles (non suivis, à garder) : `loadtest/locustfile.py`,
`integrite.py`, `validation_reprise.py`, `validation_sauvegarde.py`,
`validation_pitr.py`, `docker-compose.loadtest.yml`, `docker-compose.pitr.yml`.

## Problèmes identifiés

1. **Deux backends.** `backend/` est celui du compose. `app/`, `alembic/`,
   `Dockerfile` et `requirements.txt` à la racine lancent `uvicorn app.main:app`.
   Les CI GitHub et GitLab ciblent déjà `backend/`. La racine n’est pas morte
   dans Git (117 fichiers suivis) : la supprimer sans revue casserait un
   chemin encore documenté comme dette, pas comme abandon prouvé fichier par fichier.
2. **Documentation en retard d’un fait.** L’architecture technique indiquait
   encore « un seul processus Uvicorn » et la révision `20261022_mg_stock_alertes`.
   Corrigé dans ce lot (4 processus, tête `20261105_mg_stock_mvt_ref_uq`).
3. **`@ngx-translate/*`** est dans `package.json` et **aucun import** dans
   `frontend/angular20/src`. Material et Tailwind sont utilisés (architecture
   technique : Material hors `plateforme/`, Tailwind marginal). On ne retire
   pas translate dans ce lot : le `package-lock` et un build n’ont pas été
   rejoués.
4. **Dumps locaux volumineux** dans `backups/` (plusieurs > 50 Mo), gitignorés.
   Ce sont des sauvegardes de la base réelle. On ne les supprime pas.
5. **`immo_user` est superutilisateur** sur le cluster local (lecture seule).
   Hors correction : changement de rôle = autorisation explicite.
6. **`archive_mode=off`** sur `bea-postgres`. Volontaire : le PITR a été
   prouvé sur `bea-lt-pitr`, pas sur le cluster qui contient `bea_digital`.

## Classification

### A. À conserver

`backend/`, `frontend/`, `database/`, `deployment/`, `docs/` (y compris
fiabilité, sessions, numérotation, sauvegarde), `loadtest/` (harnais +
rapports), migrations Alembic, tests, `.gitignore`, compose racine et prod.

### B. À nettoyer (fait dans ce lot)

Caches générés, déjà gitignorés : 30 `__pycache__/` hors `.venv`,
2 `.ruff_cache/`, 1 `.pytest_cache/`. `node_modules/`, `dist/`, `.angular/`
et `.venv/` restent sur le poste : les supprimer obligerait une
réinstallation sans alléger Git.

### C. À supprimer

Aucun fichier source. Les candidats (dette `app/`, Dockerfile racine,
traduction inutilisée, dumps) ne sont pas démontrés comme supprimables
sans risque ou sont des sauvegardes.

### D. À fusionner

Aucun doublon strict. `docs/demarrer.md`, `docs/DEPLOIEMENT_LOCAL.md` et
`docs/deployment/` se complètent (poste local vs Ubuntu). Le guide
`docs/DEPLOYMENT_GUIDE.md` pointe vers eux, il ne les remplace pas.

### E. À déplacer

Rien. Déplacer `app/` ou les rapports gitignorés n’apporte rien au déploiement.

### F. À vérifier avant toute suppression

| Élément | Pourquoi on s’arrête |
|---|---|
| `app/`, `alembic/`, `Dockerfile`, `requirements.txt` racine | Dette documentée, encore versionnée |
| `@ngx-translate/core` et `http-loader` | Aucun import, lockfile non rejoué |
| `backups/*.dump` | Sauvegardes métier locales |
| Rôle `immo_user` superuser | Sécurité, pas un fichier |
| `archive_mode` sur `bea-postgres` | Toucherait `bea_digital` |

## Dépendances

Backend `backend/requirements.txt` : FastAPI, Uvicorn, SQLAlchemy, asyncpg,
Alembic, Redis 5.2.1, Celery 5.4.0, **kombu 5.6.2** (épinglé : kombu ≥ 5.7
casse le worker avec redis 5.2.1). openpyxl, xlrd, pdfplumber, reportlab,
pytesseract, pdf2image sont importés (GED, imports, PDF). Aucun paquet
retiré.

Frontend : Angular 20, CDK, Material, RxJS. Tailwind en devDependency.
`@ngx-translate` : suspect, non retiré.

## Recommandations (non exécutées)

1. Décider explicitement le sort de `app/` + `alembic/` racine (archiver
   hors du chemin de build, pas un `rm` silencieux).
2. Retirer `@ngx-translate` après `npm ci` et `ng build`.
3. Ne pas activer l’archivage WAL sur `bea-postgres` tant que les volumes
   données / WAL / basebackup ne sont pas séparés (voir
   `docs/fiabilite/sauvegarde-postgresql.md`).
4. Faire examiner `immo_user` (superuser) par la DSI avant Ubuntu.
5. Commiter le travail de fiabilité (migrations, verrou de numérotation,
   loadtest) avant tout déploiement : il n’est pas encore dans `484f5db`.
