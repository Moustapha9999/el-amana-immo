#!/usr/bin/env bash
# Restaure un dump PostgreSQL dans le Postgres unique de BEA DIGITAL.
# Refuse si le schéma public contient déjà des tables (pas d'écrasement).
# Usage : ./scripts/db-restore.sh backups/LE_DUMP.dump [dossier_uploads]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE=".env.docker"
if [[ ! -f "$ENV_FILE" ]]; then
  echo ".env.docker introuvable. Copiez .env.docker.example vers .env.docker." >&2
  exit 1
fi

dotenv_val() {
  local key="$1" default="$2"
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n1 || true)"
  if [[ -z "$line" ]]; then
    printf '%s' "$default"
    return
  fi
  printf '%s' "${line#*=}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//'
}

DB_USER="$(dotenv_val POSTGRES_USER immo_user)"
DB_NAME="$(dotenv_val POSTGRES_DB immobilisations)"

DUMP_ARG="${1:-}"
UPLOADS_ARG="${2:-}"
if [[ -z "$DUMP_ARG" ]]; then
  echo "Usage : $0 <dump> [dossier_uploads]" >&2
  exit 1
fi

DUMP_PATH="$DUMP_ARG"
if [[ ! -f "$DUMP_PATH" && -f "backups/$DUMP_ARG" ]]; then
  DUMP_PATH="backups/$DUMP_ARG"
fi
if [[ ! -f "$DUMP_PATH" ]]; then
  echo "Dump introuvable : $DUMP_ARG" >&2
  exit 1
fi

DUMP_NAME="$(basename "$DUMP_PATH")"
DUMP_ABS="$(cd "$(dirname "$DUMP_PATH")" && pwd)/$DUMP_NAME"
BACKUPS_ABS="$(cd backups && pwd)"
case "$DUMP_ABS" in
  "$BACKUPS_ABS"/*) ;;
  *) cp -f "$DUMP_ABS" "backups/$DUMP_NAME" ;;
esac

echo "BEA DIGITAL — restore non destructif de $DUMP_NAME"
echo "  (refuse si public contient déjà des tables)"
echo

N_TABLES="$(docker compose --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")"
N_TABLES="$(echo "$N_TABLES" | tr -d '[:space:]')"
if [[ -z "$N_TABLES" ]]; then
  echo "Impossible d'interroger PostgreSQL. Le service postgres est-il healthy ?" >&2
  exit 1
fi
if [[ "$N_TABLES" -gt 0 ]]; then
  echo "Refus : le schéma public contient déjà $N_TABLES table(s). Pas d'écrasement." >&2
  exit 1
fi

echo "public est vide — pg_restore..."
set +e
docker compose --env-file "$ENV_FILE" exec -T postgres \
  pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl "/backups/$DUMP_NAME"
RESTORE_RC=$?
set -e
if [[ "$RESTORE_RC" -ne 0 ]]; then
  echo "pg_restore a renvoyé le code $RESTORE_RC — contrôle des tables..."
fi

AFTER="$(docker compose --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")"
AFTER="$(echo "$AFTER" | tr -d '[:space:]')"
if [[ "$AFTER" -lt 5 ]]; then
  echo "Restauration incomplète : seulement $AFTER table(s) dans public." >&2
  exit 1
fi
echo "Tables public : $AFTER"
echo
echo "Contrôles à rapprocher de la Comptabilité (nb immos, VB, cumul amort., VNC) :"

docker compose --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT count(*) AS nb_immobilisations FROM immobilisations;"
docker compose --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT coalesce(sum(valeur_brute), 0) AS valeur_brute_totale FROM immobilisations;"
docker compose --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT coalesce(sum(montant), 0) AS cumul_dotations FROM amortissements WHERE NOT annule AND NOT simule;"
docker compose --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT count(*) AS nb_users FROM users;"
docker compose --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT count(*) AS nb_pieces_jointes FROM pieces_jointes;"

echo
echo "VNC métier = valeur brute − cumul (moteur amortissement) : jamais négative ; VNC = 0 → pas de dotation."
echo "Rapprocher ces totaux du rapport Comptabilité. Recopier aussi storage/uploads (GED)."

if [[ -n "$UPLOADS_ARG" ]]; then
  if [[ ! -d "$UPLOADS_ARG" ]]; then
    echo "Dossier documents introuvable : $UPLOADS_ARG" >&2
    exit 1
  fi
  echo "Restauration documents -> storage/uploads"
  mkdir -p storage/uploads
  cp -R "$UPLOADS_ARG"/. storage/uploads/
else
  echo "Pas de dossier uploads en argument : vérifier manuellement que storage/uploads correspond au dump."
fi

echo
echo "Restore terminé. SKIP_MIGRATIONS reste à 1 tant que vous n'appliquez pas de nouvelles révisions incrémentales."
echo "Ne jamais : docker compose down -v"
