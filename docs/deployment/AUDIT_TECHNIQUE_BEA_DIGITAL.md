# Audit technique BEA DIGITAL — phase 1, périmètre corrigé

Date : 9 novembre 2026, mis à jour le même jour après confirmation du périmètre.  
Périmètre de ce document : code source du dépôt. Aucune commande n’a été exécutée sur `srv-classification`.  
Les fichiers Compose et les scripts de déploiement ne sont pas encore modifiés : la section 18 décrit la proposition, en attente d’accord.

Les documents `00` à `08` de ce dossier décrivent une cible antérieure (GitLab, serveur de test distinct). Ils ne décrivent pas l’état constaté de la VM.

## 1. Périmètre confirmé

CORE ADMIN est la console `/admin` de BEA DIGITAL. Elle part avec le déploiement, dans la même application Angular, la même API FastAPI et la même base PostgreSQL. Aucune architecture séparée ne sera créée pour elle.

| Élément | Où il vit |
|---|---|
| Écran | `/admin`, Login 1, permission `core.admin.access` |
| API | mêmes processus, préfixes `/api/v1/plateforme/admin…` |
| Données | `users`, `roles`, `permissions`, `plateforme_espaces`, `plateforme_modules`, `auth_sessions`, `audit_logs` |

Le rôle Immobilisations `administrateur` n’ouvre pas cette console.

Le seul système externe hors périmètre est ORION, le core banking. BEA DIGITAL ne l’appelle pas en HTTP et ne sera pas modifié pour s’y intégrer. ORION apparaît seulement comme source de fichiers importés.

### Premier déploiement

La même image contient tout le code. On ne retire pas de module du dépôt. L’accès réel dépend du statut en base : `require_module_access` n’autorise l’API que si `plateforme_modules.statut` vaut `actif` (`backend/app/api/deps.py`). Le catalogue source est `backend/app/data/plateforme_catalogue.py`.

| Composant | Décision |
|---|---|
| Angular, `/admin`, FastAPI, PostgreSQL 17, Redis 7, worker Celery | Déployés |
| EER | Reste désactivé : catalogue `inactif`, tables `eer_*` conservées |
| Base Clientèle | Catalogue actuel : `developpement`. L’API refuse déjà ce statut. Code conservé |
| Réclamations | Catalogue actuel : `actif`. L’API l’autorise. Voir la décision ouverte ci-dessous |
| Autres modules dont le catalogue est `actif` (Immobilisations, stock, achats, demandes, formation, etc.) | Présents dans l’image. Le périmètre signé du premier jour reste à figer avec la décision ouverte |

Décision ouverte, non tranchée dans le code : le cadrage du 9 novembre demande de différer Clientèle et Réclamations, puis de les valider dans une version ultérieure. La stratégie écrite dans le même message demande d’installer au premier déploiement les modules déjà opérationnels, notamment Clientèle et Réclamations. Tant que ce point n’est pas tranché, aucun statut de catalogue n’est modifié. Différer Réclamations voudrait dire passer son statut de `actif` à `developpement` ou `inactif`. Le laisser `actif` l’ouvre aux utilisateurs dès le premier démarrage.

### DSI, confirmé et encore ouvert

Confirmé : IP cible `192.168.1.22`, accès au serveur opérationnel, connectivité nécessaire confirmée.

Encore à écrire dans la configuration finale, pas encore fourni : nom DNS, FQDN, certificat HTTPS, règles précises de publication. `AUTH_COOKIE_SECURE=true` reste obligatoire. Sans HTTPS, le cookie de rafraîchissement n’est pas envoyé vers `http://192.168.1.22`. L’ouverture aux postes utilisateurs attend donc le certificat. Un contrôle technique sur `127.0.0.1` du serveur peut précéder cette ouverture.

## 2. Architecture réellement découverte

Une seule application, quatre processus utiles en exécution Docker, une seule instance PostgreSQL.

```text
Navigateur (réseau interne BEA)
        |
        |  HTTPS attendu, reverse proxy de la DSI (non installé dans ce dépôt)
        v
nginx du conteneur frontend  (écoute 8080, fichiers Angular statiques)
        |  /api/  , /health , /version  →  http://backend:8000
        v
FastAPI / uvicorn             (un processus, port 8000, non publié)
        |
        +---- PostgreSQL 17   (réseau Docker privé, base bea_digital)
        |
        +---- Redis 7         (broker Celery, rate limit, idempotence)
        |
        +---- worker Celery   (même image backend, file d’attente + beat)

Hors du chemin de requête :
  service compose « migrate » (profil outils, local seulement)
  pgAdmin (local seulement, 127.0.0.1:5050)
```

Le backend canonique est `backend/`. Le dossier `app/` et l’Alembic à la racine du dépôt sont une dette Immobilisations ancienne. Le `Dockerfile` à la racine construit cette dette. Aucun compose ne l’utilise. Le build réel est `backend/Dockerfile`, contexte `./backend`.

Le frontend canonique est `frontend/angular20/`. `frontend/package.json` ne fait que relancer npm dans `angular20`. L’image de production ne lance pas `ng serve` : elle sert le build statique avec nginx.

Aucun fichier Compose ne crée la base `bea_digital_test`. Cette base n’existe aujourd’hui que comme base de pytest, fabriquée sur le poste de développement par `scripts/test-db.ps1`.

## 3. Stack et versions

Versions lues dans les fichiers de dépendances et les Dockerfiles. Les versions exactes résolues d’Angular sont dans `frontend/angular20/package-lock.json` (lockfile npm v3) ; le tableau indique les plages déclarées.

| Composant | Version constatée | Source |
|---|---|---|
| Python | 3.13 (image `python:3.13-slim`, correctif non épinglé) | `backend/Dockerfile` |
| FastAPI | 0.115.6 | `backend/requirements.txt` |
| Uvicorn | 0.34.0 | idem |
| SQLAlchemy asyncio | 2.0.36 | idem |
| Pilote API | asyncpg 0.30.0 | idem |
| Pilote Alembic / scripts | psycopg2-binary 2.9.10 | idem |
| Alembic | 1.14.0 | idem |
| Pydantic | 2.10.3 | idem |
| Celery | 5.4.0, kombu 5.6.2 | idem |
| Redis (client) | 5.2.1 | idem |
| JWT | python-jose 3.3.0, algorithme HS256 | idem |
| Mots de passe | bcrypt 4.2.1 | idem |
| MFA | pyotp 2.9.0 | idem |
| Excel | openpyxl 3.1.5, xlrd 2.0.1 | idem |
| PDF | reportlab 4.2.5, pdfplumber 0.11.5 | idem |
| OCR | pytesseract 0.3.13, pdf2image 1.17.0, Pillow 11.0.0 ; paquets image `tesseract-ocr-fra`, `tesseract-ocr-eng`, `poppler-utils` | idem |
| Angular | 20.3.x | `frontend/angular20/package.json` |
| Node de build | 22 (image `node:22-alpine`) | `frontend/Dockerfile` |
| TypeScript | 5.9.x | package.json |
| nginx de l’image | 1.27-alpine | `frontend/Dockerfile` |
| PostgreSQL local | `postgres:17-alpine` | `docker-compose.yml` |
| PostgreSQL visé banque | `postgres:17` (Debian, pas Alpine) | `deployment/docker-compose.prod.yml` |
| Redis | `redis:7-alpine` | les deux compose |
| Gestionnaires | pip (requirements épinglés), npm (`npm ci`) | Dockerfiles |

Pas de Java. Pas de Gunicorn : la commande réelle est un seul `uvicorn`, sans `--workers`. Pas de `pyproject.toml` backend. Material et Tailwind sont déclarés dans le `package.json` Angular ; le chrome plateforme (`src/app/plateforme/`) ne doit pas recevoir de dépendance supplémentaire.

Paquets système de l’image backend : compilateur, `libpq-dev`, client PostgreSQL, Tesseract français et anglais, Poppler. L’image est donc lourde à construire, surtout pour l’OCR. L’OCR ne tourne que lorsqu’une pièce est soumise au worker.

Utilisateur du conteneur backend : `bea`, uid/gid **10001**. Les dossiers montés (`storage/uploads`, `storage/ged`, `backups`) doivent appartenir à cet uid sur l’hôte.

## 4. Services nécessaires

| Service | Rôle | Obligatoire |
|---|---|---|
| `frontend` | SPA + reverse proxy interne vers l’API | Oui |
| `backend` | API FastAPI | Oui |
| `postgres` | Données, une instance | Oui |
| `redis` | Broker Celery, résultats, rate limit, idempotence, `/health/ready` | Oui pour le worker et pour l’état « ready » |
| `worker` | OCR GED, purge d’erreurs API, alerte de pic d’erreurs, rappels contrats, seuils de stock | Oui si ces traitements doivent vivre |
| `migrate` | `alembic upgrade head` avec le compte propriétaire | Présent seulement dans le compose local, profil `outils`, jamais démarré par `up` |
| `pgAdmin` | Console SQL locale | Non. Absente du compose banque. Ne pas l’exposer sur le serveur |
| ClamAV | Antivirus des pièces jointes | Optionnel. Hôte vide = analyse désactivée. Hôte renseigné et injoignable = rejet du fichier |
| SMTP | E-mails (rappels, liens) | Optionnel. Hôte vide = notifications dans l’application seulement |
| Reverse proxy HTTPS de l’hôte | Terminaison TLS, domaine interne | Requis pour un usage réel. Modèle : `deployment/nginx/bea-digital.conf.template`. Certificats et DNS : DSI |
| ORION, Supabase, MinIO, S3 | — | Pas des services d’exécution. Supabase n’est qu’un historique de dump. Aucun client Supabase dans les dépendances |

Tâches planifiées, fuseau `Africa/Nouakchott`, beat embarqué dans le worker (`celery worker -B`) :

| Tâche | Rythme |
|---|---|
| Purge des événements d’erreur API | 02:30 |
| Détection de pic d’erreurs serveur | toutes les 5 minutes |
| Rappels de contrats | 07:30 |
| Contrôle des seuils de stock | 07:00 |
| OCR d’un document GED | à la demande |

Une boucle asyncio dans le processus API (pas Celery) rafraîchit le cache de politique de sécurité toutes les 30 secondes, et peut lancer les échéances EER si `EER_ECHEANCES_INTERVAL_HEURES` > 0 (défaut 6). Le module EER est désactivé : cette boucle ne doit pas être considérée comme un traitement métier actif.

Redis, dans le compose banque, est démarré sans snapshot et sans AOF (`--save "" --appendonly no`), et sans volume. Un redémarrage efface files, résultats Celery, compteurs de rate limit et clés d’idempotence. C’est acceptable pour un courtier de files courtes. Ce n’est pas un stockage de données bancaires. PostgreSQL et les dossiers `storage/` portent les données durables.

## 5. Points d’entrée

| Entrée | Valeur |
|---|---|
| Processus API | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Objet ASGI | `backend/app/main.py`, `app = create_app()` |
| Préfixe API | `/api/v1` |
| Santé processus | `GET /health` — ne teste ni PostgreSQL ni Redis |
| Santé dépendances | `GET /health/ready` — `SELECT 1` et `PING` Redis ; 503 si l’un des deux échoue |
| Version | `GET /version` |
| Worker | `celery -A app.workers.celery_app worker -B -Q default,celery` |
| Page d’accueil après Login 1 | `/accueil` |
| Console admin | `/admin` |

Le healthcheck Docker du backend appelle `/health`, pas `/health/ready`. Un conteneur peut donc être « healthy » alors que la base est indisponible après le démarrage.

`WEB_CONCURRENCY` est posé dans les compose (défaut 4) et commenté comme nombre de processus uvicorn. Uvicorn ne lit pas cette variable, et la commande ne passe pas `--workers`. Le backend tourne en **un** processus. Sur 2 vCPU, c’est le bon point de départ. Il ne faut pas « activer » 4 workers sans mesure : le commentaire de dimensionnement des connexions (`WEB_CONCURRENCY × (pool + overflow)`) est inexact tant que le flag n’existe pas.

Pool SQLAlchemy par processus : `DB_POOL_SIZE` 5, `DB_MAX_OVERFLOW` 5 dans les compose (10 dans le code si la variable est absente), `DB_POOL_TIMEOUT` 30 s. Avec un processus API et un worker, l’ordre de grandeur reste très en dessous de `max_connections` 100. Saturation du pool → HTTP 503 `DATABASE_BUSY`.

## 6. Authentification et sessions

Deux sessions, une seule table `auth_sessions`.

| | Login 1 — plateforme | Login 2 — module |
|---|---|---|
| Route | `POST /api/v1/auth/login` | `POST /api/v1/auth/modules/{code}/login` |
| Condition | E-mail, mot de passe, TOTP si activé sur le compte | Jeton plateforme encore valide, puis le mot de passe à nouveau |
| Jeton d’accès | JWT Bearer, en mémoire côté navigateur | JWT Bearer de module |
| Rafraîchissement | Cookie HttpOnly `bea_rt` si l’en-tête `X-BEA-Auth: cookie` est envoyé | Cookie `bea_mrt_{module}` |
| Durée par défaut du code | Accès 15 min, refresh plateforme 1 jour, refresh module 45 min | idem |
| Durée dans `.env.docker.example` | Accès 30 min, refresh 7 jours | le refresh module reste à 45 min si non surchargé |

`AUTH_COOKIE_SECURE` vaut `true` par défaut. Un navigateur n’envoie ce cookie que sur HTTPS, sauf sur `localhost`. Un accès `http://192.168.1.22` cassera donc le rafraîchissement de session tant que la DSI n’aura pas terminé TLS, ou tant qu’une dérogation explicite n’aura pas été décidée. Le jeton d’accès n’est pas stocké dans `localStorage`.

Verrouillage : 5 échecs / 10 minutes. Réinitialisation de mot de passe par e-mail : les routes existent et répondent 403 (`PASSWORD_RESET_DISABLED`). `MFA_REQUIRED_FOR_CORE_ADMIN` est `false` dans le code et dans l’exemple Docker local, `true` dans `deployment/env.production.example`.

`APP_ENV=test` est, dans le code, un environnement qui **accepte une SECRET_KEY faible**. `deployment/env.test.example` pose justement `APP_ENV=test`. Sur un serveur de banque, l’instance de recette devra une clé longue et un `APP_ENV` qui refuse la clé par défaut. Ce point est à trancher en phase 3, avant toute copie du fichier d’exemple.

## 7. Fichiers, exports, intégrations

Stockage local, pas d’objet S3 :

| Usage | Chemin conteneur | Variable |
|---|---|---|
| Pièces uploadées | `/app/storage/uploads` | `UPLOAD_DIR` (défaut `storage/uploads`) |
| GED | `/app/storage/ged/{module}/{entité}/{id}/` | `GED_DIR` |
| Sauvegardes vues par l’application | `/backups` si le montage existe, sinon `BACKUP_DIR` | `BACKUP_DIR` |

Taille maximale d’une pièce : 25 Mio côté politique applicative. nginx accepte un corps jusqu’à 50 Mio. Les imports Clientèle ont un proxy à 600 s ; le reste de l’API à 120 s. Ce sont les traitements longs à mesurer, pas le nombre d’utilisateurs simultanés (2 à 3 par département).

Génération : Excel (openpyxl / xlrd), PDF (reportlab), lecture PDF (pdfplumber), QR (qrcode). `python-barcode` est installé ; aucun import correspondant n’a été trouvé sous `backend/`.

Intégrations HTTP sortantes : destinations en base, client `httpx`, blocage SSRF des adresses locales. Rien n’est appelé tant qu’une destination n’est pas configurée dans CORE ADMIN. Ce n’est pas un prérequis de démarrage.

## 8. PostgreSQL réellement utilisé

| Sujet | Constat |
|---|---|
| Moteur visé | PostgreSQL 17. Une seule instance. Une seule `DATABASE_URL` par processus |
| Base créée par les compose | `bea_digital` uniquement (`POSTGRES_DB`) |
| Base de test du code | `bea_digital_test`, créée par `scripts/test-db.ps1` sur le conteneur local `bea-postgres`. Les tests qui utilisent la fixture `base_jetable` refusent de tourner si la base courante s’appelle `bea_digital` |
| Extension à l’init du volume vide | `pgcrypto` (`database/init/01-extensions.sql`), exécutée seulement à la première création du volume |
| Révision Alembic de tête | `20261105_mg_stock_mvt_ref_uq` (`backend/alembic/versions/20261105_mg_stock_mvt_reference_unique.py`) |
| Alembic racine (dette) | autre chaîne, tête `20260730_periodes_categories`. Ne pas l’appliquer |
| Démarrage conteneur | `SKIP_MIGRATIONS=1` : l’entrypoint ne lance pas Alembic |
| Règle de migrate | `deployment/scripts/deploy.sh` refuse une base à 0 table. Il sauvegarde, puis `alembic upgrade head` avec l’image de la version cible. Alembic sur une base vide produirait un schéma faux : la première révision est un `ALTER` de tables déjà présentes dans le dump |
| Compte local | Superutilisateur `admin` pour migrations, restaurations et pgAdmin. Compte applicatif `bea_app` (`NOSUPERUSER`, pas de DDL), script `database/roles/bea_app.sql`, mot de passe lu dans l’environnement, jamais écrit dans le SQL |
| Compte du compose banque | `POSTGRES_USER` défaut `bea_digital_app`, utilisé **à la fois** comme superutilisateur du conteneur officiel et comme utilisateur de `DATABASE_URL`. Le script `bea_app.sql` n’est référencé par aucun script de `deployment/scripts/` |
| Publication réseau | Compose local : `127.0.0.1:5432`. Compose banque : aucun port. À conserver : PostgreSQL ne doit pas écouter sur le LAN |
| Image | Alpine acceptable en local. Banque : image Debian `postgres:17`, collation alignée sur le dump. Ne pas forcer `fr_FR.utf8` sur Alpine (collation réelle `C`) |
| SSL | `DATABASE_SSL=false` dans les compose (réseau Docker). Un hôte `supabase.co` dans l’URL forcerait SSL. Sans objet sur le serveur banque |
| Volume | Nom figé `bea_postgres_data`. `docker compose down -v` détruit la base. Interdit |

Les chiffres de données (211 tables, 1 206 immobilisations, 42 912 clients, etc.) décrivent le PostgreSQL **local** déjà validé. Ils ne décrivent pas `srv-classification`, où PostgreSQL n’est pas encore présumé installé.

Séparation test / réel demandée : deux bases, `bea_digital` et `bea_digital_test`, dans cette instance, sans troisième base applicative. Le compose banque actuel ne sait pas faire cohabiter les deux environnements. Voir le risque R1.

## 9. Fichiers Docker et Compose déjà présents

| Fichier | Rôle réel | À utiliser sur le serveur banque |
|---|---|---|
| `docker-compose.yml` | Instance locale Windows / Docker Desktop. Frontend publié sur le port **80**. Postgres sur `127.0.0.1:5432`. pgAdmin inclus. Volume `bea_postgres_data` | Non. Il publie l’interface sur toutes les interfaces et embarque pgAdmin |
| `docker-compose.dev.yml` | Rechargement du code, ports 8000, 8080 et Redis 6379, volume **distinct** `bea_postgres_data_dev` | Non |
| `deployment/docker-compose.prod.yml` | Cible banque : Postgres Debian non publié, frontend sur `127.0.0.1:8088`, logs json bornés, images versionnées | Base de départ, après correction des écarts R1–R4. Ne pas le lancer tel quel sur ce serveur |
| `loadtest/docker-compose.loadtest.yml` | Charge locale, base `bea_digital_test`, réseau `bea_internal` externe | Non, pas sur le serveur |
| `loadtest/docker-compose.pitr.yml` | Essai de restauration ponctuelle, isolé | Non |
| `backend/Dockerfile` | Image API et worker | Oui |
| `frontend/Dockerfile` | Build Angular puis nginx | Oui |
| `Dockerfile` (racine) | Image de la dette `app/` | Ne pas construire |

Compose banque, services et ports :

| Service | Image | Port hôte | Port conteneur |
|---|---|---|---|
| postgres | `postgres:17` | aucun | 5432 |
| redis | `redis:7-alpine` | aucun | 6379 |
| backend | `bea-digital/backend:${BEA_VERSION}` | aucun | 8000 |
| worker | même image | aucun | — |
| frontend | `bea-digital/frontend:${BEA_VERSION}` | `127.0.0.1:8088` (variable `BEA_HTTP_BIND`) | 8080 |

Le nom de conteneur est figé (`bea-postgres`, `bea-backend`, `bea-frontend`, `bea-redis`, `bea-worker`), ainsi que le nom du volume et du réseau (`bea_internal`). Deux projets Compose de ce fichier ne peuvent pas tourner ensemble sur le même Docker.

Scripts de livraison déjà écrits, non exécutés ici : `deployment/scripts/deploy.sh`, `backup-pre-deploy.sh`, `restore.sh`, `rollback.sh`, `lib.sh`. Côté poste de développement : `scripts/release.ps1` (archive d’images), `scripts/db-restore.ps1` / `db-restore.sh`, `scripts/backup-local.ps1`, `scripts/test-db.ps1`. Les scripts `scripts/windows-cmd/*.cmd` et `install-on-comptable.ps1` visent un poste comptable Windows, pas la VM Ubuntu.

## 10. Variables d’environnement

Aucune valeur secrète n’est recopiée ici. Les fichiers `.env`, `.env.docker` et `.env.production` réels n’ont pas été lus. Statut « à définir » = obligatoire sur le serveur, absent du dépôt sous une valeur utilisable en production.

| Variable | Statut | Remarque |
|---|---|---|
| `SECRET_KEY` | À définir | 32 caractères minimum hors `development` / `test`. Refus du placeholder `change-me` |
| `POSTGRES_PASSWORD` | À définir | Éviter `@`, `:`, `/`, `?` ou accepter l’encodage fait par l’application |
| `POSTGRES_DB` | Présente dans les exemples | Valeur `bea_digital`. Ne pas pointer la recette sur cette base |
| `POSTGRES_USER` | Présente | Local : `admin`. Exemple banque : `bea_digital_app`. Écart de privilèges, voir R2 |
| `BEA_APP_DB_USER` | Présente en local | `bea_app`. Absente des exemples banque |
| `BEA_APP_DB_PASSWORD` | À définir si le rôle limité est retenu | 24 caractères minimum exigés par `bea_app.sql` |
| `DATABASE_URL` | Construite par le compose | Le code contient une valeur de développement vers `localhost`. Ne jamais démarrer l’API sans la surcharge du compose |
| `DATABASE_SSL` | Présente | `false` sur le réseau Docker interne |
| `APP_ENV` | À définir | `production` pour l’instance réelle. Ne pas réutiliser `test` tel que le code le traite aujourd’hui |
| `APP_DEBUG` | Présente | `false` |
| `APP_VERSION`, `GIT_SHA`, `BEA_VERSION` | À définir au déploiement | Identifient l’image et `/version` |
| `BEA_IMAGE_BACKEND`, `BEA_IMAGE_FRONTEND` | Présentes | Défaut `bea-digital/backend` et `bea-digital/frontend` |
| `BEA_HTTP_BIND` | Présente | Production `127.0.0.1:8088`. Recette `127.0.0.1:8089`. Le port 8080 de l’hôte reste à l’autre démon |
| `PUBLIC_APP_URL` | À définir | URL HTTPS interne fournie par la DSI |
| `CORS_ORIGINS` | À définir | Doit être cette même origine. Le compose local force `http://localhost` |
| `TRUSTED_PROXIES` | À définir | Défaut `frontend`, plus l’adresse réelle du reverse proxy vue par le conteneur. Pas de `0.0.0.0/0` |
| `AUTH_COOKIE_SECURE` | Présente | `true`. Compatible avec HTTPS |
| `SKIP_MIGRATIONS` | Présente | Figée à `1` sur le backend banque. Les migrations passent par `deploy.sh` |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Construites | `redis://redis:6379/0`, `/1`, `/2`. Redis sans mot de passe, non publié |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT` | Présentes | Ne pas les augmenter sans symptôme `database_pool_exhausted` |
| `WEB_CONCURRENCY` | Présente et sans effet | Voir §5 |
| `API_DOCS_ENABLED` | Présente | `false` en production, `true` dans l’exemple de test |
| `MFA_REQUIRED_FOR_CORE_ADMIN` | À confirmer | `true` dans l’exemple de production |
| `ACHATS_MODE_TEST` | À confirmer | `false` / `0` sur la base réelle. L’exemple de test le met à `true` : ne pas l’appliquer à `bea_digital` |
| `CLIENTELE_CLASSEMENT_MASSE_ACTIF` | Présente | Rester faux tant que la Conformité n’a pas validé |
| `CLIENTELE_CLASSEMENT_MASSE_VALIDATION` | Vide tant que le classement de masse est fermé | Référence de PV, pas un secret |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | À définir si la DSI fournit un relais | Vides = pas d’e-mail |
| `CLAMAV_HOST`, `CLAMAV_PORT` | Optionnel | Ne pas inventer un hôte |
| `UPLOAD_DIR`, `GED_DIR`, `BACKUP_DIR` | Défauts suffisants dans l’image | Les montages compose priment |
| `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD` | Locales seulement | Ne pas les poser sur le serveur |
| `SUPABASE_*` | Absentes du chemin banque | Ne pas les recopier |

Fichiers d’exemple déjà dans le dépôt : `.env.example`, `.env.docker.example`, `deployment/env.production.example`, `deployment/env.test.example`. Aucun ne doit être commité une fois rempli.

## 11. Procédure de démarrage actuelle

Poste de développement :

1. Copier `.env.docker.example` vers `.env.docker` et remplacer les secrets.
2. `docker compose --env-file .env.docker up -d` (ou `scripts/start-local.ps1`).
3. Ouvrir `http://localhost`. nginx du frontend est publié sur le port 80 et proxifie `/api/` vers le backend.
4. Les migrations ne partent pas toutes seules. Après un dump restauré : `docker compose --env-file .env.docker run --rm migrate`.

Chemin décrit pour un serveur, non constaté sur `srv-classification` :

1. Produire une archive versionnée avec `scripts/release.ps1` (images + manifeste).
2. Déposer le code de déploiement et un `.env.production` hors Git, droits restreints.
3. Restaurer un dump dans un volume neuf avec `deployment/scripts/restore.sh` si la base est vide.
4. `BEA_VERSION=… ./deployment/scripts/deploy.sh` : charge les images, refuse une base vide, sauvegarde, migre, redémarre, contrôle `/health/ready`, `/version` et le worker. Retour arrière automatique seulement si aucune migration n’a été appliquée ou si elles se déclarent compatibles.

Ce chemin suppose un serveur où les noms `bea-postgres` et le volume `bea_postgres_data` sont libres. Le frontend banque écoute sur `127.0.0.1:8088`, pas sur le port 8080 déjà occupé.

## 12. Modules présents et niveau indiqué par la documentation

Le code contient les routes. Le niveau ci-dessous reprend uniquement ce que les documents du dépôt affirment. Il ne s’agit pas d’une recette fonctionnelle réalisée pour cet audit.

| Module | Chemin | Lecture documentaire |
|---|---|---|
| Immobilisations et amortissements | URLs racine (`/dashboard`, `/immobilisations`, `/amortissements`, …) | Module livré, en usage |
| Stock, achats, notes de frais, contrats, facturation, archives MG, archive générale, demandes, formation | préfixes dédiés | Présents ; plusieurs sont marqués « actif — non vérifié » |
| Base Clientèle | `/clientele` | En construction. Classement de masse fermé |
| Réclamations | `/reclamations` | En construction. Ne pas le déclarer validé sans la Conformité |
| EER | `/eer` | Désactivé le 19/10/2026, tables conservées, API 403. Ne pas supprimer les tables `eer_*` |
| Demandes employés | redirection vers l’accueil | Retiré |
| Crédit, RH, tickets SI, rapprochements, contrôles, clôture, reporting comptable | cartes ou espaces, pas de coquille métier branchée | Pas des modules à annoncer comme opérationnels |
| CORE ADMIN | `/admin` | Fait partie de l’application déployée |

Le moteur d’amortissement `backend/app/services/amortissement_engine.py` et la règle VNC ne doivent pas être modifiés.

## 13. Tests disponibles

| Suite | Emplacement | Lancement documenté | Exécutée pendant cet audit |
|---|---|---|---|
| API | `backend/tests/` (134 fichiers), `backend/pytest.ini` | Depuis `backend/` : `python -m pytest tests`. `scripts/release.ps1` redirige `DATABASE_URL` vers `bea_digital_test` | Non |
| Garde-fou base réelle | `conftest.py`, fixture `base_jetable` | Saute si la base courante est `bea_digital` | Non |
| Base de test | `scripts/test-db.ps1` | Copie de `bea_digital` aux accès neutralisés + rechargement Clientèle. Script PowerShell, conteneur nommé `bea-postgres` | Non |
| Front | `ng test` (Karma / Jasmine) | Pas de navigateur exigé par le Dockerfile de production | Non |
| Charge | `loadtest/` | Projet Compose séparé, port local 8081 | Non |

Aucun résultat de test n’est produit par cette phase.

## 14. Problèmes et risques

Classement : bloquant = à traiter avant de copier des données ou de publier un port ; majeur = à trancher dans l’architecture (phase 3) ; surveillé = connu, pas un motif pour modifier le code maintenant.

### R1 — Test et production ne peuvent pas cohabiter avec le compose actuel (bloquant)

`deployment/docker-compose.prod.yml` fixe les noms de conteneurs, le volume `bea_postgres_data` et le réseau `bea_internal`. `deployment/env.test.example` utilise la même base `bea_digital`, le même port `127.0.0.1:8080` et `ACHATS_MODE_TEST=true`. Lancer « le test » puis « la production » avec ces fichiers les ferait partager les mêmes données, ou échouer sur un nom déjà pris.

La séparation demandée (bases `bea_digital` et `bea_digital_test`, le test incapable d’écrire dans la base réelle) n’existe pas encore dans les fichiers de déploiement banque. Elle existe seulement sur le poste de développement, via `scripts/test-db.ps1`.

### R2 — Le compose banque connecte l’application avec le superutilisateur PostgreSQL (majeur)

En local, `bea_app` n’a pas le droit de DDL et ne peut pas modifier `audit_logs` ni `alembic_version`. Sur le compose banque, `DATABASE_URL` reprend `POSTGRES_USER`, qui est le compte créé par l’image officielle, donc superutilisateur. Un défaut applicatif ou un mauvais `DATABASE_URL` de recette peut alors atteindre la base réelle, y compris pour la détruire. `deployment/scripts/` n’applique pas `database/roles/bea_app.sql`.

### R3 — `APP_ENV=test` désarme le contrôle de `SECRET_KEY` (majeur)

Le validateur n’exige une clé longue que hors `development` et `test`. L’exemple de recette choisit `APP_ENV=test`. Une instance joignable sur le réseau de la banque avec une clé courte permettrait de forger des JWT. La recette doit avoir ses propres secrets, distincts de la production, et un environnement qui refuse la clé faible.

### R4 — Cookie de session et HTTPS (bloquant pour l’ouverture aux utilisateurs)

L’IP `192.168.1.22` et la connectivité sont confirmées par la DSI. Le FQDN, le certificat et les règles de publication ne le sont pas. `AUTH_COOKIE_SECURE=true`. Sans HTTPS, le rafraîchissement de session ne fonctionne pas sur `http://192.168.1.22`. Le modèle nginx hôte (`deployment/nginx/bea-digital.conf.template`) contient encore le domaine fictif `REMPLACER_PAR_DOMAINE_BEA`.

Le nginx du conteneur réécrit `X-Forwarded-Proto` avec son propre schéma, qui est HTTP. L’URL publique doit donc être portée par `PUBLIC_APP_URL`, pas déduite de cet en-tête.

### R5 — Ports 8000, 8080 et 9443 tenus par un Docker que le client ne voit pas (bloquant)

Relevé du 9 novembre 2026. `docker-proxy` écoute sur toutes les interfaces, y compris `192.168.1.22` :

| Port | IPv4 | IPv6 |
|---|---|---|
| 8000 | pid 5131 | pid 5137 |
| 8080 | pid 5282 | pid 5289 |
| 9443 | pid 5145 | pid 5152 |

Le client Docker ne voit que trois conteneurs arrêtés depuis 17 mois, code de sortie 255 : `my-app-container` (ports publiés 80 et 8080), `my-mongo-express-container` (8081), `my-mongo-container` (27017). Leurs ports ne sont pas le trio 8000 / 8080 / 9443, et le port 80 n’est pas en écoute. Le pont `resources_default` (`br-5c4fd068ba79`, 172.18.0.0/16) est éteint, ce qui est cohérent avec ces arrêts.

Le pont `br-9a59dafb9f47` (172.19.0.1/16) est allumé, avec sept `veth` rattachés à des espaces réseau distincts (`link-netnsid` 1 à 7). Ce pont n’apparaît pas dans `docker network ls`. Les images visibles par ce client sont seulement `resources_app`, `nginx`, `mongo` et `mongo-express`. Les processus qui tiennent 8080 ne sont donc pas la pile `resources`, et `127.0.0.1:8080` n’est pas libre pour BEA DIGITAL. On n’arrête aucun `docker-proxy` tant que le démon parent n’est pas nommé.

### R6 — Docker Snap : la contrainte de disque est levée, le montage `/opt` ne l’est pas

Mesure du 9 novembre 2026 : `DockerRootDir` = `/var/snap/docker/common/var-lib-docker`, sur `/dev/sda2` (ext4, 2 To, 1,9 To libres). Un volume nommé PostgreSQL tiendra sur ce disque. Il n’y a pas de second disque : une sauvegarde laissée sur `sda2` ne protège pas d’une perte du disque. L’interface Snap `home` est connectée. `removable-media` ne l’est pas. Mesure du 9 novembre 2026 : le montage de `$HOME/bea-mount-test` réussit ; le montage de `/opt/bea-mount-test` échoue (`read-only file system`). Le dossier de déploiement est `/home/moustapha/bea-digital`. Le port `8088` n’a aucune ligne `LISTEN`. Le client Docker est en 28.4.0, le moteur Snap en 29.8.0 ; `docker info` présente le moteur comme Ubuntu Core 24, alors que l’hôte est Ubuntu 22.04.5. On ne change pas l’installation.

### R7 — Dette de build à la racine (surveillé)

Construire le `Dockerfile` racine produirait une API Immobilisations ancienne, sur le port 8000, avec une autre chaîne Alembic. Les procédures doivent nommer explicitement `backend/Dockerfile` et `deployment/docker-compose.prod.yml`.

### R8 — Santé, Redis et dimensionnement (surveillé)

`/health` ne prouve pas la base. Redis n’a ni mot de passe, ni volume, ni persistance : acceptable uniquement parce qu’il n’est pas publié et ne porte pas les données métier. Le serveur a 2 vCPU. Le facteur limitant à mesurer plus tard est l’import Clientèle / OCR, pas un pic de 100 sessions. Aucun chiffre de capacité n’est annoncé tant qu’il n’y a pas de mesure sur cette VM.

### R9 — Modules à ne pas déclarer validés (surveillé)

EER reste `inactif`. Clientèle est `developpement` : l’API ne l’ouvre pas. Réclamations est `actif` dans le catalogue : son maintien ou son report est la décision ouverte de la section 1. Achats : `ACHATS_MODE_TEST` reste faux sur `bea_digital`. Classement de masse Clientèle fermé. Pas de SMTP : les rappels de contrats restent des notifications internes. Aucun de ces modules n’est déclaré validé par la Conformité.

### R10 — Données locales à ne pas confondre avec le serveur (bloquant au moment du transfert)

Les volumes, dumps et bases validés sont sur le poste de développement. Le transfert vers la banque n’est pas décrit par un chemin déjà exécuté. Règles déjà figées : ne jamais remplacer `bea_digital` par une base de test ; ne pas lancer de migration sans sauvegarde vérifiée et retour arrière ; ne pas supprimer les dumps Clientèle de référence du poste local (`avant_purge_clientele_20261022_104012.dump`, `local-20261021-115657.dump`).

## 15. Où sont les données aujourd’hui

Elles ne sont pas sur `srv-classification`. Le PostgreSQL validé est le conteneur local `bea-postgres`, volume `bea_postgres_data`, sur le poste de développement.

Le rapport `docs/audit/RAPPORT_ARCHITECTURE_POSTGRESQL_2_BASES.md` (5 novembre 2026) décrit, sur cette instance locale seulement :

| Base | Révision lue alors | Contenu utile au transfert |
|---|---|---|
| `bea_digital` | `20261105_mg_stock_mvt_ref_uq`, identique à la tête du code | Base réelle locale. 211 tables. Pas la base de test |
| `bea_digital_test` | même tête | Copie de travail, comptes neutralisés, Base Clientèle rechargée, `GRANT DELETE` sur `audit_logs` pour les tests. Ne jamais la restaurer à la place de `bea_digital` |

La tête du code est le fichier `backend/alembic/versions/20261105_mg_stock_mvt_reference_unique.py`, qui déclare `retour_arriere = "compatible"`. Les révisions postérieures à `20261020_clientele_14` déclarent toutes `compatible`. Celles qui sont antérieures à cette référence comptent comme `restauration` : revenir en arrière exige le dump d’avant, pas un simple changement d’image (`backend/scripts/migrations_retour.py`).

Conséquence pour le premier chargement : si le dump transféré contient déjà `alembic_version = 20261105_mg_stock_mvt_ref_uq`, `alembic upgrade head` ne change rien. Cette égalité doit être lue dans le dump au moment du transfert (`pg_restore -l` ou requête après restauration dans une base jetable). Elle n’est pas recontrôlée dans cet audit, et elle n’est pas vraie d’un dump plus ancien. Alembic n’est jamais lancé sur une base à 0 table. `SKIP_MIGRATIONS` reste `1` sur les conteneurs qui servent l’API.

## 16. Comparaison des trois configurations

| Sujet | Local `docker-compose.yml` | Exemple test `deployment/env.test.example` | Banque `deployment/docker-compose.prod.yml` |
|---|---|---|---|
| PostgreSQL | `postgres:17-alpine`, port `127.0.0.1:5432` | même fichier prod, donc Debian `postgres:17`, aucun port | Debian `postgres:17`, aucun port |
| Base | `bea_digital` | `bea_digital` (même nom que la production) | `bea_digital` |
| Compte applicatif | `bea_app`, sans superutilisateur | `POSTGRES_USER=bea_digital_app`, qui est aussi le superutilisateur du conteneur | identique à l’exemple test |
| Migrations | service `migrate`, profil `outils`, compte `admin` | `deploy.sh` lance Alembic avec le compte de `DATABASE_URL`, donc le superutilisateur | `SKIP_MIGRATIONS=1`, pas de service `migrate` |
| Redis | un conteneur, non publié, persistance par défaut de l’image | le Redis du compose banque, sans AOF ni volume | `redis-server --save "" --appendonly no`, sans volume |
| Frontend | `80:8080` sur toutes les interfaces, pgAdmin inclus | `127.0.0.1:8089` | `127.0.0.1:8088` |
| `APP_ENV` | forcé `production` dans le compose, au-dessus du fichier | `test`, donc clé faible acceptée | défaut `production` |
| `ACHATS_MODE_TEST` | `0` dans `.env.docker.example` | `true` | non posé par le compose ; dépend du fichier d’environnement |
| Noms figés | `bea-postgres`, volume `bea_postgres_data`, réseau `bea_internal` | les mêmes noms : impossible de lancer les deux piles | les mêmes noms |
| Secrets | `.env.docker`, hors Git | `.env.test` prévu, mais même base et même rôle que la production | `.env.production` prévu |

Le compose local a déjà le bon partage des rôles. Le compose banque et l’exemple de test non. Les corriger ne demande pas un troisième moteur PostgreSQL.

## 17. Vérifications ordonnées sur srv-classification

Lecture seule. Aucune n’a été lancée depuis le poste de développement. Ne pas renvoyer de secret : pour un fichier d’environnement, indiquer seulement présent ou absent. Ne pas envoyer `kill`, `rm`, `prune`, `down -v`, ni modifier le pare-feu, SSH, le swap ou l’installation Docker.

Bloc 1 — identité, heure, adresse :

```bash
hostnamectl
timedatectl
ip -br addr
ip route
```

Bloc 2 — disque, avant tout volume PostgreSQL :

```bash
df -hT
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
findmnt -D
```

Bloc 3 — mémoire, observation seulement :

```bash
nproc
free -h
swapon --show
vmstat 1 5
```

Bloc 4 — Docker Snap et emplacement réel des données :

```bash
docker version
docker compose version
docker info
snap services docker
snap connections docker
df -hT /var/snap/docker /var/snap/docker/common/var-lib-docker
```

Bloc 5 — qui écoute 8000, 8080 et 9443 :

```bash
sudo ss -lptn 'sport = :8000 or sport = :8080 or sport = :9443'
sudo ps -fp $(sudo ss -lptnH 'sport = :8000 or sport = :8080 or sport = :9443' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u | paste -sd, -)
```

Bloc 6 — inventaire Docker, sans suppression :

```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker volume ls
docker network ls
docker image ls
docker volume inspect 2a3d334e28a9a173152bcadf903030faa7f6f93ce7b578d0fd1050d78a41c3cb 17275b0c3811667982681529d6d6fabd814c56850eb45aaeb78fb6ffe8d64f93
```

Bloc 7 — autre PostgreSQL, Airflow ou Celery déjà présent :

```bash
systemctl list-units --type=service --state=running --no-pager
docker ps -a --format '{{.Names}} {{.Image}}' | grep -Ei 'postgres|airflow|celery|redis' || true
```

Le bloc 4 est passé : `DockerRootDir` est sur le disque de 2 To. On enchaîne par les blocs 5 et 6. On s’arrête si le propriétaire du port 8080 n’est pas identifié.

## 17 bis. Résultats des blocs 1 à 4 (9 novembre 2026)

Relevés exécutés par l’opérateur sur `srv-classification`. Aucune modification n’a été demandée par ces commandes.

| Sujet | Constat |
|---|---|
| Hôte | `srv-classification`, VM VMware, Ubuntu 22.04.5 LTS, noyau 6.8.0-124-generic, x86-64 |
| CPU | 2 |
| RAM | 15 Gio, environ 8,8 Gio utilisés, 5,7 Gio disponibles. Swap fichier `/swapfile` de 2 Gio, entierement occupé. `vmstat` : `si` et `so` à 0 sur les 5 secondes. Un pic CPU à 95 % sur une seconde, puis retour au repos |
| Heure | NTP actif, horloge synchronisée, RTC en UTC. Premier relevé : `Europe/Paris` (CET). Relevés deux minutes plus tard : `Africa/Nouakchott` (GMT). Le second correspond au fuseau de Celery |
| Adresse | `ens34` UP, `192.168.1.22/24`. Passerelle `192.168.1.253`. Le réseau Docker par défaut `docker0` est `172.17.0.0/16` |
| Disque | Un seul disque `sda`, 2 To. `sda2` ext4 monté sur `/`, 50 Go utilisés, 1,9 To libres. Pas de disque de données séparé. ISO Ubuntu encore montée sur `/media/moustapha/…` |
| Docker | Client Community 28.4.0, moteur Snap 29.8.0, Compose 2.39.4, containerd 2.3.4, overlay2, cgroup v2. `docker.dockerd` actif. 3 conteneurs arrêtés, 0 en marche, 10 images. Racine Docker sur `sda2` |
| Snap | `home`, `network`, `network-bind`, `firewall-control` et `docker-support` connectés. `removable-media` non connecté |

Conséquence pour l’architecture encore en proposition : le volume nommé `bea_postgres_data` peut vivre dans la racine Docker. Les dossiers bind-montés (`uploads`, `ged`, sauvegardes) ne seront pas placés sous `/opt` avant un essai de montage. La seconde pile applicative reste conditionnée à la mémoire déjà occupée (8,8 Gio sans conteneur BEA DIGITAL).

### Suite des blocs 5 et 6

`docker volume ls` ne montre que les deux volumes anonymes Mongo déjà connus (`2a3d334e…` et `17275b0c…`). Ils ne sont pas supprimés. `br-7c5a55b29fc6` (172.29.0.0/16), vu éteint au bloc 1, n’est pas non plus dans `docker network ls` : pont orphelin, laissé en place.

Le propriétaire est nommé le 9 novembre 2026, sans arrêt d’aucun processus. Deux démons Docker tournent en même temps :

| Démon | PID | Démarrage | Rôle constaté |
|---|---|---|---|
| `/usr/bin/dockerd -H fd://` | 2019 | 10 juillet 2026, 22:09 | Tient les ports. 8000 et 9443 vers `172.17.0.2`. 8080 vers `172.19.0.5`. Cinq shims depuis juillet, trois autres démarrés le 9 novembre (10:18, 10:55, 11:08) |
| Snap `dockerd --data-root=/var/snap/docker/common/var-lib-docker` | 1749476 | 16 octobre 2026, 13:47 | Seul démon vu par `docker ps`. Les trois conteneurs `resources` y sont arrêtés |

`/var/run/docker.sock` date du 16 octobre : le client parle au Snap. Supprimer `my-app-container`, `my-mongo-container` et `my-mongo-express-container` ne libère ni 8080 ni la RAM. Les ports 8000 et 9443 sur `172.17.0.2` correspondent au couple d’écoute habituel de Portainer ; le nom reste à lire dans le démon de juillet avant toute conclusion. Aucun `docker rm` ni arrêt de ces shims n’est autorisé tant que les images et les noms ne sont pas lus.

Décision appliquée le 9 novembre 2026 : le port hôte de la production est `127.0.0.1:8088` (`BEA_HTTP_BIND`). Le nginx du conteneur reste sur 8080. La recette est prévue sur `127.0.0.1:8089`. Le contrôle `ss` du port 8088 n’a pas été renvoyé ; le choix est celui de l’opérateur. Les ports 8000 et 9443 de l’hôte ne sont pas publiés par le compose banque. Ce déplacement ne libère pas la mémoire occupée par le démon de juillet.

Décision du 9 novembre 2026, premier déploiement : un seul compte PostgreSQL, `bea_digital_app`, créé par l’image comme superutilisateur. FastAPI, Celery, les sauvegardes et Alembic l’utilisent. `SKIP_MIGRATIONS` reste à `1`. Un rôle limité pourra être ajouté plus tard, sans recréer le volume. PostgreSQL n’est pas publié sur le réseau.

## 18. Architecture proposée, non appliquée

Un hôte. Une instance PostgreSQL 17 Debian. Deux bases applicatives, et seulement celles-là : `bea_digital`, `bea_digital_test`. La base système `postgres` reste le catalogue du cluster ; ce n’est pas une base applicative.

```text
Postes BEA
    |
    | HTTPS, reverse proxy DSI vers 127.0.0.1
    |   production : 127.0.0.1:8088 (8080 hôte déjà pris)
    |   recette    : 127.0.0.1:8082
    v
Pile production                Pile recette (démarrée à la demande)
  frontend, backend,             frontend, backend,
  worker, redis propre           worker, redis propre
    |  rôle bea_app                |  rôle bea_app_test
    |  base bea_digital            |  base bea_digital_test
    +--------------+---------------+
                   v
            postgres:17
            aucun port publié
            volume nommé sur sda2 (1,9 To libres)
```

Deux Redis, parce qu’un `FLUSH` ou un redémarrage de la recette ne doit pas vider les files de la production. La pile de recette ne tourne en permanence qu’après la mesure mémoire du bloc 3 : le swap est déjà plein, et deux piles complètes sur 2 vCPU ne sont pas acquises.

Isolement des rôles, calqué sur `database/roles/bea_app.sql` :

| Rôle | Droits |
|---|---|
| Superutilisateur du conteneur (`POSTGRES_USER`, nommé `admin` comme en local) | Restaurations, `CREATE DATABASE`, Alembic. Jamais dans `DATABASE_URL` de l’API ou du worker |
| `bea_app` | `CONNECT` sur `bea_digital` seulement. DML. Pas de DDL. Pas de `UPDATE`/`DELETE` sur `audit_logs`. Lecture seule de `alembic_version` |
| `bea_app_test` | `CONNECT` sur `bea_digital_test` seulement. Mot de passe distinct |

`CONNECT` est retiré à `PUBLIC` sur les deux bases. Sans cela, tout rôle qui peut se connecter au cluster peut ouvrir les deux bases : le script actuel ne fait que `GRANT`, il ne retire pas le droit par défaut. Chaque rôle est créé après la restauration, parce que les `GRANT` portent sur les tables déjà présentes. `deploy.sh` refuse de continuer si la base visée par la recette s’appelle `bea_digital`, ou si l’utilisateur de `DATABASE_URL` est le superutilisateur.

Secrets : `/home/moustapha/bea-digital/secrets/production.env` et `test.env`, droits `600`, hors Git. `/opt` est inutilisable par le Docker Snap. Les exemples du dépôt ne contiennent que des libellés `REMPLACER_*`. `APP_ENV=test` ne sera plus une exception de clé faible : la valeur `test` sort de `_ENV_CLE_FAIBLE_TOLEREE` dans `backend/app/core/config.py`, et `backend/tests/test_config_secret_key.py` est aligné. La recette banque utilise `APP_ENV=production` avec sa propre `SECRET_KEY`, ou la valeur `test-banque` déjà refusée par le test existant si la clé est courte. `AUTH_COOKIE_SECURE=true` des deux côtés. `ACHATS_MODE_TEST=true` seulement dans `test.env`, dont la base est `bea_digital_test`.

Migrations : les conteneurs API gardent `SKIP_MIGRATIONS=1`. Un service `migrate`, profil non lancé par `up`, utilise le superutilisateur, comme en local. Ordre : volume vide, démarrage PostgreSQL, restauration du dump de `bea_digital`, lecture de `alembic_version`, rôles, puis `alembic upgrade head` (sans effet si la révision est déjà la tête). `bea_digital_test` est créée ensuite par copie explicite, comptes neutralisés, jamais par Alembic sur une base vide, jamais en remplaçant `bea_digital`.

Sauvegardes hors du cycle de vie des conteneurs, sur `sda2` faute d’un second disque, puis copie vers un support approuvé par la banque. Le volume PostgreSQL nommé est acceptable : la racine Docker est déjà sur ce disque de 2 To. Un bind mount hors de `/home` attend l’essai Snap.

Arborescence, non créée :

```text
/home/moustapha/bea-digital/
  app/        artefacts de la version
  config/     compose et nginx, sans secrets
  secrets/    production.env et test.env
  data/       uploads et ged de chaque pile, uid 10001
  backups/    dumps, hors volume Docker
  logs/
  deploy/     scripts
```

### Fichiers à modifier après accord

| Fichier | Modification |
|---|---|
| `deployment/docker-compose.prod.yml` | `DATABASE_URL` avec `bea_app` ; superutilisateur réservé à Postgres et au service `migrate` ; noms de la pile production |
| `deployment/env.production.example` | `BEA_APP_DB_USER`, `BEA_APP_DB_PASSWORD`, `APP_ENV=production`, `AUTH_COOKIE_SECURE=true`, `ACHATS_MODE_TEST=false` |
| `deployment/env.test.example` | Base `bea_digital_test`, rôle `bea_app_test`, port `127.0.0.1:8082`, secrets distincts, plus de `APP_ENV=test` |
| `deployment/scripts/lib.sh`, `deploy.sh` | Contrôles : la recette ne vise pas `bea_digital` ; Alembic n’utilise pas le rôle applicatif ; base vide refusée, déjà le cas |
| `backend/app/core/config.py` | Retirer `test` des environnements qui acceptent une `SECRET_KEY` faible |
| `backend/tests/test_config_secret_key.py` | La tolérance reste `development` seul |
| `database/roles/bea_app.sql` ou script voisin | Second rôle, et `REVOKE CONNECT ... FROM PUBLIC` sur les deux bases |

### Fichiers à ajouter après accord

| Fichier | Rôle |
|---|---|
| `deployment/docker-compose.test.yml` | Pile recette : autres noms de conteneurs, autre Redis, autre port, même instance PostgreSQL |
| `deployment/scripts/init-roles.sh` | Applique les rôles après restauration, sans afficher les mots de passe |
| `deployment/scripts/create-test-db.sh` | Crée `bea_digital_test` par copie, refuse d’agir sur `bea_digital` |

Aucun de ces fichiers n’est écrit dans cette étape. Le `Dockerfile` racine et le dossier `app/` ne sont pas le chemin de déploiement. Le moteur d’amortissement n’est pas modifié.

## 19. Ce qui n’a pas été fait

- Aucun fichier Compose, script ou code applicatif modifié. Seul cet audit a été mis à jour.
- Aucune image construite, aucun conteneur lancé, aucune migration, aucun transfert de dump.
- Aucune commande sur `srv-classification`.
- Aucun secret lu.
- Aucun statut de module changé, dans l’attente de la décision Clientèle / Réclamations.
- Aucune capacité utilisateur annoncée.
