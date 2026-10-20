#!/usr/bin/env bash
# Restauration d'une sauvegarde BEA DIGITAL sur le serveur (premier chargement ou reprise après incident).
#
#   ./deployment/scripts/restore.sh backups/bea_xxx.dump [backups/bea_xxx_fichiers.tar.gz]
#   Premier chargement d'un serveur sans Internet : IMAGES_TAR=releases/vX.Y.Z/images.tar (charge postgres/redis).
#
# Par défaut, refuse si la base contient déjà des tables (premier chargement).
# Reprise après incident : REMPLACER=1 → sauvegarde de l'état actuel, puis remplacement du schéma public.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
# shellcheck source=lib.sh
source deployment/scripts/lib.sh

DUMP="${1:?usage : restore.sh <dump> [archive_fichiers.tar.gz]}"
FICHIERS="${2:-}"
charger_env
[[ -f "$DUMP" ]] || echec "dump introuvable : $DUMP"
mkdir -p backups
NOM="$(basename "$DUMP")"
[[ "$(cd "$(dirname "$DUMP")" && pwd)" == "$(cd backups && pwd)" ]] || cp -f "$DUMP" "backups/$NOM"

charger_archive_images
compose up -d --wait postgres redis
compose exec -T postgres pg_restore --list "/backups/$NOM" > /dev/null || echec "dump illisible : $NOM"

sql() { compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -tAc "$1"; }
NB="$(sql "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';" | tr -d '[:space:]')"

if [[ "$NB" -gt 0 ]]; then
  [[ "${REMPLACER:-0}" == "1" ]] || echec "la base contient déjà ${NB} table(s). Reprise après incident : REMPLACER=1 (l'état actuel est sauvegardé avant)."
  etape "Sauvegarde de l'état actuel avant remplacement"
  BEA_VERSION="avant_restauration" bash deployment/scripts/backup-pre-deploy.sh
  etape "Arrêt de l'application et remplacement du schéma public"
  compose stop backend worker frontend || true
  sql "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" > /dev/null
fi

etape "pg_restore ${NOM}"
set +e
compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl "/backups/$NOM"
RC=$?
set -e
APRES="$(sql "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';" | tr -d '[:space:]')"
[[ "$APRES" -ge 5 ]] || echec "restauration incomplète : ${APRES} table(s) (code pg_restore ${RC})"
[[ "$RC" -eq 0 ]] || echo "ATTENTION: pg_restore a renvoyé ${RC} (avertissements) — ${APRES} tables présentes, vérifier les contrôles ci-dessous"

if [[ -n "$FICHIERS" ]]; then
  [[ -f "$FICHIERS" ]] || echec "archive de fichiers introuvable : $FICHIERS"
  etape "Restauration des pièces et de la GED"
  tar -xzf "$FICHIERS"
fi

etape "Contrôles de rapprochement"
sql "SELECT 'révision alembic', coalesce((SELECT version_num FROM alembic_version LIMIT 1), 'aucune');" || true
for q in \
  "SELECT 'utilisateurs', count(*) FROM users" \
  "SELECT 'immobilisations', count(*) FROM immobilisations" \
  "SELECT 'valeur brute totale', coalesce(sum(valeur_brute),0) FROM immobilisations" \
  "SELECT 'clients (base clientèle)', count(*) FROM clientele_situation" \
  "SELECT 'classifications retenues', count(*) FROM clientele_classifications"; do
  sql "$q" 2>/dev/null || true
done

echo
echo "RESTORE_OK tables=${APRES}. Déployer ensuite la version : deployment/scripts/deploy.sh"
echo "Ne jamais : docker compose down -v"
