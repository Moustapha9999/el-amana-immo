#!/usr/bin/env bash
# Retour à une version précédente (images déjà présentes sur le serveur, sinon registre).
#   ./deployment/scripts/rollback.sh            → version_precedente enregistrée par deploy.sh
#   ./deployment/scripts/rollback.sh v1.5.2     → version donnée
# Ne restaure PAS la base : les migrations sont additives, l'ancienne version fonctionne sur la base
# migrée. Si une restauration est nécessaire : deployment/scripts/restore.sh (procédure DSI).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
# shellcheck source=lib.sh
source deployment/scripts/lib.sh

CIBLE="${1:-}"
if [[ -z "$CIBLE" && -f "$ETAT_DIR/version_precedente" ]]; then
  CIBLE="$(cat "$ETAT_DIR/version_precedente")"
fi
[[ -n "$CIBLE" ]] || echec "aucune version précédente connue : préciser la version (ex. v1.5.2)"

BEA_VERSION="$CIBLE"
charger_env
BEA_VERSION="$CIBLE"; export BEA_VERSION
export GIT_SHA="${GIT_SHA:-rollback}"

etape "Retour à ${CIBLE}"
if ! image_presente "${BEA_IMAGE_BACKEND}:${CIBLE}" || ! image_presente "${BEA_IMAGE_FRONTEND}:${CIBLE}"; then
  compose pull backend frontend || echec "images ${CIBLE} introuvables (charger l'archive de cette version)"
fi
compose up -d --no-deps --force-recreate backend worker frontend

if controle_sante "$CIBLE"; then
  ACTUELLE="$(cat "$ETAT_DIR/version_courante" 2>/dev/null || true)"
  echo "$CIBLE" > "$ETAT_DIR/version_courante"
  echo "$(date '+%F %T') ROLLBACK ${CIBLE} OK (depuis: ${ACTUELLE:-?})" >> "$ETAT_DIR/historique.log"
  echo "ROLLBACK_OK version=${CIBLE}"
else
  echo "$(date '+%F %T') ROLLBACK ${CIBLE} ECHEC" >> "$ETAT_DIR/historique.log"
  echec "contrôle de santé en échec après retour à ${CIBLE} — escalader (logs : docker compose logs backend)"
fi
