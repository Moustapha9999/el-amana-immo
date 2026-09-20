#!/usr/bin/env bash
# Déploiement production : pull images taguées, recreate FE/BE, healthcheck.
# Ne touche PAS au volume PostgreSQL (jamais down -v).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deployment/docker-compose.prod.yml}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/health}"
VERSION_URL="${VERSION_URL:-http://127.0.0.1:8080/version}"
RETRIES="${HEALTH_RETRIES:-30}"
SLEEP_S="${HEALTH_SLEEP:-2}"

: "${BEA_VERSION:?BEA_VERSION requis (ex. v1.5.0)}"
: "${BEA_IMAGE_BACKEND:?BEA_IMAGE_BACKEND requis}"
: "${BEA_IMAGE_FRONTEND:?BEA_IMAGE_FRONTEND requis}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERREUR: $ENV_FILE introuvable" >&2
  exit 1
fi

export BEA_VERSION BEA_IMAGE_BACKEND BEA_IMAGE_FRONTEND
export GIT_SHA="${GIT_SHA:-unknown}"

echo "==> Pull ${BEA_IMAGE_BACKEND}:${BEA_VERSION} + frontend"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull backend frontend

echo "==> Recreate backend + frontend (volumes conservés)"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend frontend

echo "==> Healthcheck ${HEALTH_URL}"
ok=0
for i in $(seq 1 "$RETRIES"); do
  if curl -fsS "$HEALTH_URL" >/tmp/bea-health.json 2>/dev/null; then
    echo "Health OK (tentative $i)"
    cat /tmp/bea-health.json
    ok=1
    break
  fi
  sleep "$SLEEP_S"
done

if [[ "$ok" -ne 1 ]]; then
  echo "ERREUR: healthcheck échoué après ${RETRIES} tentatives" >&2
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps || true
  exit 1
fi

if curl -fsS "$VERSION_URL" >/tmp/bea-version.json 2>/dev/null; then
  echo "==> /version"
  cat /tmp/bea-version.json
  echo
fi

echo "DEPLOY_OK version=${BEA_VERSION} sha=${GIT_SHA}"
