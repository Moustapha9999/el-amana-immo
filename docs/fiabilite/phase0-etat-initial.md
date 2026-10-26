# Phase 0 — État initial BEA DIGITAL (fiabilité, sécurité, production)

Référentiel : `BEA_DIGITAL_RELIABILITY_SECURITY_ROADMAP.md`.
Date : 26/10/2026. Audit **en lecture seule** (aucun code modifié), poste local
(Docker Compose, PostgreSQL 17, un seul backend uvicorn).

Statuts de preuve : **C** = constaté (code/config/commande), **D** = déduit,
**NV** = non vérifié. Priorités proposées, à valider avec la DSI.
Aucun contrôle n'est « VÉRIFIÉ » tant qu'un test n'a pas été exécuté.

## 1. Synthèse

BEA DIGITAL a un socle solide sur plusieurs points (révocation des sessions à
chaque requête, SSRF des intégrations, GED : liste blanche + signature réelle +
anti-traversée, erreurs 500 sans stack trace, SQL paramétré, scripts de
déploiement/rollback avec garde Alembic). Mais **il n'est pas prêt pour la
production** : 5 P0 confirmés, plusieurs P1, et aucune preuve de restauration
périodique, de charge ni de supervision.

## 2. P0 — à corriger en premier

| ID | Constat | Preuve | Statut |
|----|---------|--------|--------|
| SEC-P0-01 | **Élévation de privilèges** : `PATCH/POST /api/v1/users` accessible au rôle immo `administrateur` ; `is_superuser` et `role_codes` du payload appliqués sans garde → un admin Immobilisations peut se rendre superuser (donc CORE ADMIN, CORE QUERY). | `endpoints/users.py` L33-47, L114-130 ; `schemas/auth.py` L113, L125-126 ; `services/auth_service.py` L118, L176-182 | C (code), NV (exploitation) |
| SEC-P0-02 | `SECRET_KEY` par défaut `change-me`, démarrage non bloqué (signalé seulement dans CORE ADMIN). Même clé pour JWT et chiffrement TOTP. `.env` locaux : clé non défaut. | `core/config.py` L26 ; `core/secret_box.py` | C |
| INFRA-P0-01 | PostgreSQL (rôle **superuser**) publié sur `0.0.0.0:5432`. | `docker-compose.yml` L25-26 ; `docker ps` | C |
| INFRA-P0-02 | pgAdmin publié sur `0.0.0.0:5050`, image sans tag. | `docker-compose.yml` L149, L172-173 ; `docker ps` | C |
| INFRA-P0-03 | `backend/.env.docker` (secrets) **copié dans l'image** backend (`.dockerignore` sans `.env*`, `COPY . .`). Toute image exportée (`release.ps1` → `images.tar`) transporte les secrets. | `backend/.dockerignore` ; `backend/Dockerfile` ; `/app/.env.docker` présent dans `bea-backend` | C |

Avant toute mise en production (P0 « prod ») : TLS réel (modèle prêt,
certificats absents) et sauvegardes externalisées hors du disque de l'hôte.

## 3. P1 — avant production

| ID | Domaine | Constat | Preuve |
|----|---------|---------|--------|
| SEC-P1-01 | GED | IDOR : `GET /ged/documents/{id}/download` sans contrôle d'espace ni niveau de sécurité (idem liste/upload `/ged/documents`). | `endpoints/ged.py` L64-152 |
| SEC-P1-02 | Front | Tokens (access + refresh) en `localStorage` **et** aucune CSP sur l'application (CSP posée seulement sur `/api`). | `core/services/auth.service.ts` L98-138 ; `frontend/nginx.conf` |
| SEC-P1-03 | CORE QUERY | Mode admin = SQL libre en écriture avec COMMIT, accessible à tout superuser. | `services/core_query/executor.py` L207-268 |
| SEC-P1-04 | Auth | MFA non obligatoire pour CORE ADMIN par défaut. | `core/config.py` L45 |
| SEC-P1-05 | Sessions | Rejeu de refresh token refusé mais session non révoquée (vol non détecté), pas de `FOR UPDATE`. | `services/auth_session_service.py` L142-182 |
| SEC-P1-06 | Auth | Verrouillage par e-mail seul → blocage du compte d'un tiers possible. | `services/login_attempt_service.py` L48-59 |
| SEC-P1-07 | Auth | Mot de passe temporaire sans changement imposé à la 1ʳᵉ connexion. | `endpoints/core_admin_users.py` L140-155 |
| SEC-P1-08 | Autorisations | Contrôle objet par agence/entité dans les modules métier : **non audité**. | — (NV) |
| INFRA-P1-01 | Docker | Conteneurs backend/worker/frontend en root. | Dockerfiles sans `USER` ; `id` = uid 0 |
| INFRA-P1-02 | PostgreSQL | Rôle applicatif superuser (local et schéma prévu en prod). | `SELECT rolsuper` = t |
| DATA-P1-01 | Sauvegarde | Aucune planification, aucun chiffrement, tout sur le même disque ; `backup-local.ps1` n'inclut pas `storage/ged`. ~50 dumps non chiffrés (données clientèle) dans `backups/`. | `scripts/backup-local.ps1` ; `celery_app.py` ; `backups/` |
| DATA-P1-02 | Reprise | RPO/RTO non définis ; pas de test de restauration périodique. | `docs/deployment/00-inventaire-bea.md` |
| CICD-P1-01 | CI | Tests sans PostgreSQL (tests DB et permissions ignorés), pas de scan dépendances/images, front buildé en `development`, pas de `ng test`. | `.gitlab-ci.yml` |
| OBS-P1-01 | Alertes | Alertes uniquement in-app, aucune supervision externe. | `workers/tasks_supervision.py` |

## 4. P2 notables

- Rate limit en mémoire par process (remis à zéro au redémarrage, faux avec plusieurs workers) — `middleware/rate_limit.py`.
- `APP_DEBUG=True` par défaut (docs OpenAPI + `echo` SQL si variable absente) — `core/config.py` L21.
- Pool SQLAlchemy et `statement_timeout` non configurés — `db/session.py`.
- Celery : pas de `time_limit`, pas d'`acks_late`, beat embarqué (`-B`) → doublons si 2ᵉ worker ; Redis prod sans persistance.
- Pas de limites CPU/RAM dans les compose.
- Neutralisation des formules CSV/XLSX absente hors supervision des intégrations.
- Archives immo : type de fichier non validé (MIME client).
- Logs INFO probablement non émis (aucune config logging).
- Contrôle optimiste absent hors réclamations/intégrations/formation/EER (dernière écriture gagne).
- Énumération de comptes par timing au login ; TOTP sans anti-rejeu ; python-jose peu maintenu.
- Sauvegarde globale exécutée dans la requête HTTP (504 nginx au-delà de 120 s).

## 5. Points forts constatés

Révocation serveur des sessions à chaque requête ; désactivation de compte =
révocation ; bcrypt coût 12 + politique de mot de passe + historique ;
SSRF intégrations (HTTPS, IP figée, réseaux privés refusés) ; GED (liste
blanche, signature réelle, anti-traversée) ; ~60 `with_for_update` sur les
opérations sensibles ; idempotence Redis (`Idempotency-Key`) ; compose prod
sans ports DB exposés ; `deploy.sh`/`rollback.sh` avec garde Alembic ;
`release.ps1` (tête Alembic unique, `retour_arriere` obligatoire).

## 6. Test de charge (Locust) — préconditions non remplies

`loadtest/locustfile.py` (lecture seule) existe, mais selon le référentiel §12.1
il ne doit **pas** être lancé sur la base actuelle : elle contient des données
réelles (dump restauré). Il faut d'abord : base de test avec données
synthétiques ou anonymisées approuvées, compte de test dédié, seuils d'arrêt,
autorisation. Rate limit par IP à prendre en compte (300 req/min).

## 7. Décisions attendues (DSI / métier)

1. RPO / RTO et fréquence de sauvegarde ; destination hors site, chiffrement et garde des clés ; rétention.
2. Infrastructure cible (serveur, OS, domaine, certificats, pare-feu) — `00-inventaire-bea.md` vide.
3. Supervision et astreinte (outil, destinataires).
4. Gestion des secrets (coffre / Docker secrets), procédure de rotation de `SECRET_KEY` (impact TOTP).
5. Rôles PostgreSQL (propriétaire migrations vs applicatif non superuser).
6. Sort de CORE QUERY mode admin en PROD.
7. Plateforme CI de référence et scans imposés.
8. Données de test synthétiques/anonymisées pour Locust ; sort des dumps locaux contenant des données clientèle.

## 8. Registre (extrait initial)

| ID | Priorité | Statut | Action / test de validation |
|----|----------|--------|-----------------------------|
| SEC-P0-01 | P0 | VÉRIFIÉ | Corrigé dans `endpoints/users.py` : `is_superuser` refusé (403), rôles limités à `IMMO_LEGACY_ROLE_CODES`, modules/espaces hors Immobilisations refusés, rôles des autres modules conservés, cible superuser intouchable par un non-superuser. Preuve : `tests/test_users_module_scope.py` sur `bea_digital_phase56_test` ; les 4 nouveaux tests échouent sans le correctif. Image reconstruite et déployée le 26/10/2026. |
| SEC-P0-02 | P0 | VÉRIFIÉ | `core/config.py` : démarrage refusé si `SECRET_KEY` par défaut ou < 32 caractères hors `development`/`test`. Preuve : `tests/test_config_secret_key.py` 19/19 ; clé backend/worker = 45 caractères. Image déployée, `/health/ready` OK. |
| INFRA-P0-01 | P0 | VÉRIFIÉ | PostgreSQL publié sur `127.0.0.1:5432` (`docker-compose.yml`, aussi `127.0.0.1:5433` en dev). Preuve 26/10/2026 : `docker ps` ; connexion refusée via l'IP réseau du PC, acceptée en local ; données intactes (61 users, 1 206 immobilisations) ; `/health/ready` OK. |
| INFRA-P0-02 | P0 | VÉRIFIÉ | pgAdmin `127.0.0.1:5050`, image épinglée `9.18@sha256:c332c5f6…` (celle déjà en service). Même preuve que ci-dessus. |
| INFRA-P0-03 | P0 | VÉRIFIÉ | `.env*`, clés, dumps, `backups` exclus (`backend/.dockerignore`, `frontend/.dockerignore`). Preuve 26/10/2026 après rebuild : `/app/.env.docker` absent de `bea-backend`. Décision : rotation des secrets si une ancienne image a quitté le poste. Note : le `Dockerfile` racine (dette `app/`) n'a pas de `.dockerignore` — ne pas l'utiliser. |
| SEC-P1-01 | P1 | DÉPLOYÉ | GED `/ged/documents` : liste, téléchargement et dépôt limités aux départements de l'utilisateur + niveau de sécurité (`endpoints/ged.py`). L'écran GED CORE ADMIN reste réservé à l'admin. Preuve : `tests/test_ged_acces_espace.py` 3/3, échouent sans le correctif. |
| SEC-P1-02 | P1 | DÉPLOYÉ | **CSP** (`frontend/nginx.conf`, application + `index.html`) : `script-src 'self'` (aucun script en ligne ni externe), `style-src 'self' 'unsafe-inline'` (styles de composants Angular), `img-src`/`frame-src`/`object-src` avec `blob:`/`data:` (aperçus PDF, QR codes), `frame-ancestors 'none'`. Script de thème sorti dans `public/theme-init.js`, CSS critique en ligne désactivé (`inlineCritical: false`), impression de la visionneuse sans script injecté. Preuve navigateur : script en ligne et script externe bloqués (violations remontées), aperçu `blob:` et images `data:` acceptés, polices et icônes chargées, aucune ressource en erreur. **Jetons** : refresh tokens en cookies `HttpOnly` + `SameSite=Strict` + `Secure` (`AUTH_COOKIE_SECURE`), chemin `/api/v1/auth`, un cookie plateforme (`bea_rt`) et un par module (`bea_mrt_<code>`) ; actifs uniquement avec l'en-tête `X-BEA-Auth: cookie` (garde CSRF), sinon échange par le corps JSON (tests, Locust). Jetons d'accès en mémoire seulement ; reprise de session au démarrage (`provideAppInitializer`) et à l'entrée d'un module (`moduleGuard`) ; renouvellements sérialisés entre onglets (Web Locks) ; sessions `localStorage` existantes migrées une fois vers le cookie. Preuve : `tests/test_auth_cookies.py` 4/4 (HttpOnly/SameSite/Path, cookie ignoré sans en-tête, rotation, cookie module par code, déconnexion qui efface et révoque, migration), tests auth existants verts ; `localStorage` sans jeton après déploiement. |
| INFRA-P1-01 | P1 | DÉPLOYÉ | Backend et worker : compte `bea` (uid 10001), code `/app` laissé à root (lecture seule pour l'application), seuls `storage/` et `/backups` lui appartiennent. Frontend : nginx sous le compte `nginx`, écoute 8080 (hôte inchangé : `80:8080` local, `127.0.0.1:8080:8080` TEST/PROD). Compose local et `deployment/docker-compose.prod.yml` : `cap_drop: ALL` + `no-new-privileges` sur backend, worker, frontend (et `migrate`). Dossiers hôte `storage/uploads`, `storage/ged`, `backups` passés à l'uid 10001 (commande dans `docs/runbook-migrations.md`). Preuve 26/10/2026 : `id` = 10001 (backend, worker) / 101 (nginx), capacités effectives nulles, `NoNewPrivs=1` ; écriture OK dans les sous-dossiers GED/uploads et `/backups`, écriture refusée dans le code ; `pg_dump` CORE ADMIN vers `/backups` OK ; tesseract/poppler OK ; `/health/ready` OK ; CSP toujours servie ; `migrate current` = head. |
| SEC-P1-03 | P1 | DÉPLOYÉ (durci, décision) | Décision : mode administrateur conservé. Contournement constaté : `COPY … TO PROGRAM` / `pg_read_file` cachés dans un bloc `DO $$…$$` passaient le contrôle (le compte applicatif étant superuser PostgreSQL = exécution de commandes dans le conteneur DB). `check_admin_sql` refuse désormais : `DO`, création/modification de fonctions, procédures, triggers, règles, langages, extensions, `DISABLE TRIGGER`, `CALL`/`PREPARE`/`EXECUTE`, `GRANT`/`REVOKE`/rôles/`SET ROLE`/RLS, serveurs distants, identifiants `U&"…"`, et toute écriture qui cite une table d'authentification, de droits ou d'audit (`ADMIN_PROTECTED_TABLES`, guillemets et schéma compris). Preuve : `tests/test_core_query.py` 107/107 ; vérifié dans le conteneur. Risque résiduel : défense par motif ; la vraie barrière reste INFRA-P1-02 (rôle applicatif non superuser). |
| INFRA-P1-02 | P1 | DÉPLOYÉ (local) | 26/10/2026 : backend et worker se connectent avec `bea_app` (`database/roles/bea_app.sql`, idempotent) : lecture/écriture des données seulement, aucun droit de structure ni de rôle, `audit_logs` et `core_query_logs` en ajout seul, `alembic_version` en lecture seule, `SET ON PARAMETER session_replication_role` pour la restauration CORE ADMIN, administration du rôle `bea_core_query_reader`. `admin` réservé au service compose `migrate` (profil `outils`), à pgAdmin et aux restaurations DSI. Preuves : copie `bea_digital_phase56_test` (159 tests passent en `bea_app`, les 5 échecs dus au limiteur de débit passent seuls ; refus constatés : modification d'audit, `TRUNCATE`, DDL, `DISABLE TRIGGER`, `CREATE ROLE`, `COPY … PROGRAM`, `pg_read_file`, `ALTER SYSTEM`) ; base réelle : `/health/ready` OK, `current_user = bea_app` non superuser, CORE QUERY rôle lecteur disponible, `pg_dump` OK, `migrate current` = head. Sauvegarde avant bascule : `backups/local-20261026-134744.dump`. Retour arrière : `BEA_APP_DB_USER=admin` + `BEA_APP_DB_PASSWORD=<mdp admin>` dans `.env.docker`, puis `up -d --no-build backend worker`. Reste à faire : même découpage dans `deployment/docker-compose.prod.yml` (TEST/PROD, où `POSTGRES_USER` est aussi superuser). Le rôle hérité `immo_user` est le superutilisateur d'installation du serveur (OID 10, ancien volume immo) : impossible à supprimer ; neutralisé le 26/10/2026 (`NOLOGIN`, mot de passe retiré) après sauvegarde `backups/local-20261026-133535.dump`. Retour arrière : `ALTER ROLE immo_user LOGIN PASSWORD '…'`. |
| SEC-P1-04 | P1 | EN COURS (décision) | Blocage backend déjà en place (`require_platform_permission` → 403 `MFA_REQUIRED`), interrupteur CORE ADMIN → Sécurité. Ajouté et déployé : écran `/securite-compte` (activation 2FA avec Login 1 seul, lien depuis le nom d'utilisateur et la barre CORE ADMIN), redirection automatique sur `MFA_REQUIRED`. Décision DSI : l'obligation est activée par l'admin lui-même, après avoir enrôlé son compte (1 compte CORE ADMIN, 2FA non activée au 26/10/2026). |
| UI-001 | P1 | DÉPLOYÉ | Polices (Plus Jakarta Sans, Material Icons) hébergées dans `public/fonts/` : plus aucun appel à Google, icônes correctes sur un poste sans Internet. |
| SEC-P1-05 | P1 | DÉPLOYÉ | Refresh token déjà consommé présenté > 20 s après la rotation → session (et sessions module filles) révoquée, audit `refresh_token_reuse`, révocation validée avant le 401 ; `FOR UPDATE` sur la session. Marge de 20 s = deux onglets qui rafraîchissent en même temps (refus simple, pas de révocation). Preuve : `tests/test_refresh_reuse.py` 3/3. |
| SEC-P1-06 | P1 | ACCEPTÉ (décision) | Décision : 5 échecs → compte bloqué 10 min, ou déblocage par l'admin (CORE ADMIN → Sécurité, `POST /settings/security/unlock`). Défaut config passé de 15 à 10 min ; écrans CORE ADMIN alignés sur la politique en base. Risque résiduel : un tiers peut bloquer un compte 10 min (atténué par la limite de débit par IP). |
| SEC-P1-07 | P1 | DÉPLOYÉ | `users.must_change_password` (migration `20261026_auth_01`) : posé à la création et à toute réinitialisation par un admin, modifiable uniquement depuis la fiche CORE ADMIN (refusé par l'API Immobilisations). Tant qu'il est posé, l'API ne sert que `/auth/me`, `/auth/change-password`, `/auth/logout` (403 `PASSWORD_CHANGE_REQUIRED`) ; écran `/changer-mot-de-passe`. Preuve : `tests/test_must_change_password.py` 3/3. Déploiement : `alembic upgrade head` **avant** la nouvelle image. |
| PERF-001 | P1 | NON AUDITÉ | Smoke puis baseline Locust sur base synthétique autorisée. |
| DATA-002 | P1 | NON AUDITÉ | Restauration complète DB + GED en environnement isolé, durée mesurée. |
