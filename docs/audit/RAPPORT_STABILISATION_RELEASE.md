# Stabilisation release — 2026-11-05

Branche : `chore/audit-nettoyage-pre-deploiement` (base `484f5db`).
Aucun commit. `bea_digital` n'a pas reçu de migration, de restauration ni de
changement de configuration. `archive_mode` n'a pas été activé.
L'ancien `app/` racine n'a pas été supprimé.

## 1. Inventaire à conserver

Modifications suivies (18 fichiers, +581 / −74) :

| Fichier | Pourquoi le garder |
|---|---|
| `backend/app/services/sequences.py` (nouveau) | Verrou de numérotation par préfixe et année |
| `backend/alembic/versions/20261105_mg_stock_mvt_reference_unique.py` | UNIQUE sur `mg_stock_mouvements.reference`, `retour_arriere = compatible` |
| `backend/app/models/mg_stock.py` | Colonne alignée sur l'index UNIQUE |
| `backend/app/services/mg_stock_service.py`, `mg_requests_service.py` | Appellent le verrou |
| `backend/app/services/mg_stock_periodes.py`, `clientele/taches.py` | Verrous de concurrence déjà validés |
| `backend/app/middleware/rate_limit.py`, `backend/app/main.py` | Limiteur Redis partagé entre les 4 processus |
| `backend/requirements.txt` | `kombu==5.6.2` (kombu ≥ 5.7 casse Celery avec redis 5.2.1) |
| `backend/tests/test_rate_limit_partage.py`, `test_mg_stock_recloture_db.py` | Tests du limiteur et de la reclôture |
| `docker-compose.yml`, `deployment/docker-compose.prod.yml` | `WEB_CONCURRENCY=4`, pool 5+5 |
| `frontend/.../stock-periodes-panel.component.ts` | Écran de réouverture / régularisation |
| `docs/socle-bea-digital.md`, `catalogue-erreurs.md`, `architecture-fonctionnelle.md` | Session module unique |
| `docs/fiabilite/numerotation-references.md`, `sauvegarde-postgresql.md` | Règles figées |
| `docs/architecture/architecture-technique.md` | 4 processus, 103 révisions, tête Alembic à jour |
| `docs/moyens-generaux/conception-technique-stock.md` | Index UNIQUE des références |
| `loadtest/*` (harnais, compose charge et PITR, seed, validations) | Rejouer les validations 1 à 4 |
| `loadtest/preuves/20261105-references-mouvements-dupliquees.json` | Preuve des doublons avant le verrou |
| `docs/audit/*`, `docs/DEPLOYMENT_GUIDE.md` | Audit et guide Ubuntu |
| `.gitignore` | Rapports de charge, `.env.loadtest`, `.cursor/mcp.json` |

Rapports `loadtest/reports/` et dumps `backups/` : présents sur le disque, gitignorés. On ne les committe pas.

À laisser hors du commit de release :

- `.cursor/mcp.json` (config locale, maintenant ignorée)
- `BEA_STOCK_OCTOBRE_2026_CLOTURE_DIAGNOSTIC.md` (diagnostic métier, pas le livrable de release)

Rien de cet inventaire n'a été écrasé.

## 2. Chemins canoniques

Compose local, compose dev et CI (`.github/workflows/ci.yml`, `.gitlab-ci.yml`) construisent et testent `backend/`. Nginx résout `backend:8000` par le DNS Docker (`resolver 127.0.0.11`), pas par une IP figée.

Toujours présents, non utilisés par le compose : `app/`, `alembic/` racine, `Dockerfile` racine, `requirements.txt` racine. Non supprimés.

## 3. Tests backend

Commande réelle, 4 min 09 s, interpréteur du virtualenv :

```text
pytest -q --tb=line
15 failed, 1623 passed, 130 skipped, 123 warnings
```

La variable d'environnement du poste pointe sur `bea_digital`. Les tests qui créent des comptes (`base_jetable`) et ceux réservés à un nom `*_test` ont été ignorés. D'autres tests PostgreSQL (facturation, EER) se sont connectés à `bea_digital` parce que les migrations y sont déjà appliquées. Leurs fixtures annulent la transaction en fin de test. Le fichier EER indique qu'un compteur de références peut avancer même dans ce cas : ce n'est pas une édition de lignes métier, mais ce n'est pas non plus une exécution sur copie. À ne pas relancer tel quel.

Les 15 échecs :

| Test | Constat |
|---|---|
| `test_acc_departement` (2) | Hub / login EER : 404 « Module introuvable » sur les données réelles, le test attend 400, 403 ou 423 |
| `test_core_query` (3) | 429 du limiteur au lieu de 400 ; corps d'erreur sans la clé attendue. Le limiteur Redis du poste est celui de l'application |
| `test_eer_dossier_service` (2) | L'agent du jeu réel n'a pas `eer.control` sur l'agence |
| `test_mg_facturation_*` (7) | Profils `MATTEL_SMS`, `SNDE`, etc. absents de `bea_digital` ; ces tests sont écrits pour `bea_digital_eer_test` |
| `test_org_import` (1) | L'aperçu et le fichier ne correspondent pas |

Aucun de ces 15 échecs n'a été « corrigé » en assouplissant une règle métier. Les tests de stock unitaire, du limiteur partagé, des montants, des erreurs API et de la déclaration `retour_arriere` des migrations font partie des 1 623 réussites. Tête Alembic lue sans migration : `20261105_mg_stock_mvt_ref_uq (head)`, une seule tête.

## 4. Frontend

`npm ci` : 559 paquets, code de sortie 0. `npm audit` signale 43 vulnérabilités ; `npm audit fix` n'a pas été lancé (pas de montée de versions non revue).

`@ngx-translate/core` et `@ngx-translate/http-loader` n'étaient importés nulle part dans `src/`. Ils ont été retirés de `package.json` et du lockfile (`npm uninstall`, 2 paquets en moins).

`ng build --configuration=production` : code de sortie 0, 43,8 s, bundle initial 2,60 Mo (transfert estimé 470 ko). Avertissements de budget (bundle 2,00 Mo dépassé, plusieurs feuilles CSS au-dessus de 8 ko). Le build n'est pas en erreur. L'image Docker `bea-digital-frontend:latest` date de 10:08 UTC et ne contient pas encore ce build.

## 5. Docker

`docker compose --env-file .env.docker -f docker-compose.yml config -q` : code 0.

Revu dans les fichiers, sans redéploiement :

- `restart: unless-stopped` sur postgres, redis, backend, worker, frontend
- healthchecks postgres, redis, backend, worker
- `WEB_CONCURRENCY=4`, pool 5+5, Redis 0/1/2 pour cache, broker et résultats
- `SKIP_MIGRATIONS=1` au démarrage ; migrations par le service `migrate` ou `deploy.sh`
- prod : image `postgres:17` Debian, PostgreSQL non publié, TLS décrit comme reverse proxy hôte
- images locales déjà construites aujourd'hui (`bea-digital-backend:latest` 12:35 UTC). Pas de reconstruction dans cette mission, pour ne pas remplacer l'image servie par la pile en cours

`immo_user`, volumes WAL et `archive_mode` : inchangés, décision DSI.

## 6. Préparation

La branche est cohérente et testée sur le périmètre charge / reprise / sauvegarde / PITR déjà prouvé, plus 1 623 tests backend et un build Angular de production.

Elle n'est pas encore une release identifiée : pas de commit, pas de tag, l'image frontend n'a pas été reconstruite, 15 tests liés à la base réelle ou à Redis restent rouges, et Ubuntu n'est pas installé.

## 7. Commit

Le commit de stabilisation reprend uniquement l'inventaire de la section 1, sans `.cursor/mcp.json`, sans le diagnostic d'octobre, sans rapports Locust ni dumps.

Les **15 échecs backend restent ouverts**. Ils ont été constatés avec `DATABASE_URL` pointant sur `bea_digital` ou avec le limiteur Redis du poste. Ce commit les enregistre comme dette de test. Il **n'autorise pas** un déploiement en production.
