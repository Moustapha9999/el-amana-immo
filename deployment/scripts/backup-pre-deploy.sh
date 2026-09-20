#!/usr/bin/env bash
# Backup vérifié avant déploiement production.
# Prérequis : exécuter depuis la racine du dépôt déployé sur le serveur,
#             Docker Compose + .env.production + conteneur postgres healthy.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deployment/docker-compose.prod.yml}"
VERSION_LABEL="${BEA_VERSION:-unknown}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DUMP_NAME="prod_before_${VERSION_LABEL}_${STAMP}.dump"
MIN_BYTES="${BACKUP_MIN_BYTES:-1024}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERREUR: $ENV_FILE introuvable" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
# Extraire POSTGRES_* sans sourcer tout le fichier (valeurs avec espaces/quotes)
POSTGRES_USER="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
POSTGRES_DB="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
set +a
POSTGRES_USER="${POSTGRES_USER:-bea_digital_app}"
POSTGRES_DB="${POSTGRES_DB:-bea_digital}"

mkdir -p backups

echo "==> pg_dump → backups/${DUMP_NAME}"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom --no-owner --no-acl \
  --file="/backups/${DUMP_NAME}"

HOST_DUMP="backups/${DUMP_NAME}"
if [[ ! -f "$HOST_DUMP" ]]; then
  echo "ERREUR: dump manquant: $HOST_DUMP" >&2
  exit 1
fi
SIZE="$(wc -c < "$HOST_DUMP" | tr -d ' ')"
if [[ "$SIZE" -lt "$MIN_BYTES" ]]; then
  echo "ERREUR: dump trop petit (${SIZE} o < ${MIN_BYTES}) — backup non exploitable" >&2
  exit 1
fi

echo "==> Dump OK (${SIZE} octets): $HOST_DUMP"

if [[ -d storage/uploads ]]; then
  UP_DST="backups/uploads_${VERSION_LABEL}_${STAMP}"
  echo "==> Copie storage/uploads → ${UP_DST}"
  cp -a storage/uploads "$UP_DST"
fi

echo "BACKUP_OK=${HOST_DUMP}"
