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

| Contrôle | Ce qu'il vérifie | Utilisé par |
|----------|------------------|-------------|
| `GET /health` | processus API vivant (ne teste **ni** PostgreSQL **ni** Redis) | healthcheck Docker du conteneur `backend` |
| `GET /health/ready` | `SELECT 1` sur PostgreSQL **et** `PING` Redis ; 503 si l'un échoue | `deploy.sh`, `rollback.sh`, `restore.sh`, supervision |
| `GET /version` | version / git_sha / env (sans secrets) | `deploy.sh` (version servie = version attendue) |
| `pg_isready` | PostgreSQL accepte les connexions | healthcheck Docker `postgres` |
| `redis-cli ping` | Redis répond | healthcheck Docker `redis` |
| `celery inspect ping` | worker Celery actif | healthcheck Docker `worker`, lu par `deploy.sh` |

Le healthcheck Docker du backend reste volontairement sur `/health` : une panne de base ou de Redis
ne doit pas faire redémarrer l'API en boucle. Le feu vert de déploiement exige `/health/ready`, la bonne
version et le worker sain. La supervision doit interroger `/health/ready`.

## Journaux Docker

Pilote `json-file`, `max-size: 20m`, `max-file: 5` (ancre `x-logging` de
`deployment/docker-compose.prod.yml`) : au plus 5 fichiers de 20 Mo, soit **100 Mo par conteneur**,
500 Mo pour les 5 conteneurs. Au-delà, les journaux les plus anciens sont supprimés : la conservation
longue durée relève d'une collecte centrale (DSI).
