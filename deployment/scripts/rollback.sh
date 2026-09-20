#!/usr/bin/env bash
# Rollback images vers un tag précédent connu.
# Ne restaure PAS automatiquement la base — voir docs/deployment/06-procedures.md
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deployment/docker-compose.prod.yml}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/health}"
RETRIES="${HEALTH_RETRIES:-30}"
SLEEP_S="${HEALTH_SLEEP:-2}"

: "${BEA_VERSION:?BEA_VERSION requis (tag précédent, ex. v1.4.2)}"
: "${BEA_IMAGE_BACKEND:?BEA_IMAGE_BACKEND requis}"
: "${BEA_IMAGE_FRONTEND:?BEA_IMAGE_FRONTEND requis}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERREUR: $ENV_FILE introuvable" >&2
  exit 1
fi

export BEA_VERSION BEA_IMAGE_BACKEND BEA_IMAGE_FRONTEND
export GIT_SHA="${GIT_SHA:-rollback}"

echo "==> Rollback vers ${BEA_VERSION}"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull backend frontend
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend frontend

ok=0
for i in $(seq 1 "$RETRIES"); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Health OK après rollback (tentative $i)"
    ok=1
    break
  fi
  sleep "$SLEEP_S"
done

if [[ "$ok" -ne 1 ]]; then
  echo "ERREUR: healthcheck rollback échoué" >&2
  exit 1
fi

echo "ROLLBACK_OK version=${BEA_VERSION}"
echo "NOTE: restauration DB = procédure manuelle si migration incompatible."
