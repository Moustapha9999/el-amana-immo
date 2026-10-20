#!/usr/bin/env bash
# Sauvegarde vérifiée : base PostgreSQL + pièces (storage/uploads) + GED (storage/ged).
# Utilisée par deploy.sh avant toute mise à jour ; peut aussi être planifiée (cron) chaque nuit.
# Échoue (code ≠ 0) si le dump est absent, trop petit ou illisible par pg_restore.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
# shellcheck source=lib.sh
source deployment/scripts/lib.sh

LABEL="${BEA_VERSION:-${1:-manuel}}"
STAMP="$(date +%Y%m%d-%H%M%S)"
NOM="bea_${LABEL}_${STAMP}"
MIN_BYTES="${BACKUP_MIN_BYTES:-102400}"
RETENTION_JOURS="${BACKUP_RETENTION_DAYS:-30}"

charger_env
mkdir -p backups

etape "pg_dump → backups/${NOM}.dump"
compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom --no-owner --no-acl --file="/backups/${NOM}.dump"

DUMP="backups/${NOM}.dump"
[[ -f "$DUMP" ]] || echec "dump manquant : $DUMP"
TAILLE="$(wc -c < "$DUMP" | tr -d ' ')"
[[ "$TAILLE" -ge "$MIN_BYTES" ]] || echec "dump trop petit (${TAILLE} o < ${MIN_BYTES} o) : sauvegarde inexploitable"
compose exec -T postgres pg_restore --list "/backups/${NOM}.dump" > /dev/null \
  || echec "dump illisible par pg_restore : $DUMP"

FICHIERS=()
for d in storage/uploads storage/ged; do
  [[ -d "$d" ]] && FICHIERS+=("$d")
done
if [[ ${#FICHIERS[@]} -gt 0 ]]; then
  etape "Archive des fichiers (${FICHIERS[*]}) → backups/${NOM}_fichiers.tar.gz"
  tar -czf "backups/${NOM}_fichiers.tar.gz" "${FICHIERS[@]}"
fi

( cd backups && sha256sum "${NOM}"* > "${NOM}.sha256" )

if [[ "$RETENTION_JOURS" -gt 0 ]]; then
  find backups -maxdepth 1 -type f -name 'bea_*' -mtime "+${RETENTION_JOURS}" -print -delete || true
fi

if [[ -n "${NOTER_SAUVEGARDE:-}" ]]; then
  ARCHIVE=""
  [[ -f "backups/${NOM}_fichiers.tar.gz" ]] && ARCHIVE=" backups/${NOM}_fichiers.tar.gz"
  echo "${DUMP}${ARCHIVE}" > "$NOTER_SAUVEGARDE"
fi

echo "BACKUP_OK=${DUMP} (${TAILLE} octets)"
