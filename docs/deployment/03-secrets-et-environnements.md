# Secrets et environnements

## Règle

Ne **jamais** committer : mots de passe, clés SSH privées, JWT secrets, `.env` / `.env.docker` / `.env.production`, dumps, certificats privés, credentials BEA.

Fichiers autorisés (exemples sans secrets) :

- [`.env.example`](../../.env.example)
- [`.env.docker.example`](../../.env.docker.example)
- [`deployment/env.production.example`](../../deployment/env.production.example)

## Séparation

| Environnement | Fichier typique | Où |
|---------------|-----------------|-----|
| DEV local | `.env.docker` | Machine développeur |
| Kit comptable | `.env.docker` | PC comptable (USB) |
| PROD banque | `.env.production` | Serveur BEA uniquement |

Ne jamais copier un `.env` DEV vers PROD.

## Variables applicatives (noms)

Alignées sur la config backend (`APP_*`, `SECRET_KEY`, `POSTGRES_*`, `DATABASE_URL`, `SKIP_MIGRATIONS`, `CORS_ORIGINS`, …) — détail dans `deployment/env.production.example`.

Build / runtime version :

| Variable | Rôle |
|----------|------|
| `APP_VERSION` | SemVer ex. `v1.5.0` |
| `GIT_SHA` | SHA court du commit |
| `BEA_VERSION` | Tag d’image compose prod (souvent = `APP_VERSION`) |

## Variables GitLab CI/CD (à créer dans l’UI GitLab — masked / protected)

| Variable | Usage |
|----------|--------|
| `CI_REGISTRY` / login registry | Push/pull images (souvent fourni par GitLab) |
| `SSH_PRIVATE_KEY` | Clé deploy (masked, file ou variable) |
| `DEPLOY_HOST` | Hôte SSH serveur PROD |
| `DEPLOY_USER` | Compte technique (ex. `bea-deploy`) |
| `DEPLOY_PATH` | Répertoire déploiement sur le serveur |

Le Runner tagué `bea-prod` doit pouvoir joindre le serveur et le registry selon la politique IT.

## Compte technique

- SSH par **clé uniquement**, pas de mot de passe.
- Permissions limitées : Docker compose du projet, lecture backups, pas d’admin OS global.
- CORE ADMIN n’implique **pas** d’accès SSH / GitLab / PostgreSQL shell.
