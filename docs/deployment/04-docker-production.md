# Docker production

## Compose

Fichier canonique prod : [`deployment/docker-compose.prod.yml`](../../deployment/docker-compose.prod.yml).

Différences vs [`docker-compose.yml`](../../docker-compose.yml) (local / kit) :

| Point | Local | Prod |
|-------|-------|------|
| Images | build local `*:latest` | Registry tag `${BEA_VERSION}` |
| Postgres | `postgres:17-alpine`, port **5432** publié | `postgres:17` (Debian), **pas** de publish public |
| Env | `.env.docker` | `.env.production` |
| HTTPS | HTTP :80 | Reverse proxy TLS devant (template nginx) |

## Volumes persistants

| Volume / chemin | Contenu |
|-----------------|--------|
| `bea_postgres_data` | Données PostgreSQL |
| `storage/uploads` | Pièces métier |
| `storage/ged` | GED |
| `backups/` | Dumps `pg_dump` |

**Interdit :** `docker compose down -v` sur la prod.

## Migrations

Voir [runbook-migrations.md](../runbook-migrations.md).

- Premier déploiement / restore dump : `SKIP_MIGRATIONS=1` jusqu’à schéma réel.
- Ensuite : `SKIP_MIGRATIONS=0` uniquement pour révisions incrémentales contrôlées, **après backup**.

## Reverse proxy

Template : [`deployment/nginx/bea-digital.conf.template`](../../deployment/nginx/bea-digital.conf.template).

Chemins certificats, domaine et ports = décisions IT (inventaire).

## Santé

- `GET /health` — liveness (status + service + version + git_sha)
- `GET /version` — version / git_sha / env (sans secrets)
- Compose healthcheck backend : HTTP `/health`
