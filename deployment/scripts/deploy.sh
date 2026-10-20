#!/usr/bin/env bash
# Déploiement d'une version BEA DIGITAL (TEST ou PRODUCTION).
#
#   Hors ligne (archive produite par scripts/release.ps1) :
#     BEA_VERSION=v1.6.0 IMAGES_TAR=/opt/bea/releases/v1.6.0/images.tar ./deployment/scripts/deploy.sh
#   Registre (GitLab / registre interne) :
#     BEA_VERSION=v1.6.0 BEA_IMAGE_BACKEND=registre/bea/backend BEA_IMAGE_FRONTEND=registre/bea/frontend ./deployment/scripts/deploy.sh
#
# Étapes : images → base non vide → sauvegarde vérifiée → migrations (nouvelle image) → redémarrage
#          → contrôle /health/ready + /version. Échec du contrôle : retour automatique à la version précédente.
# Ne supprime jamais de volume ni de donnée.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
# shellcheck source=lib.sh
source deployment/scripts/lib.sh

: "${BEA_VERSION:?BEA_VERSION requis (ex. v1.6.0)}"
CIBLE="$BEA_VERSION"
charger_env
BEA_VERSION="$CIBLE"; export BEA_VERSION
export GIT_SHA="${GIT_SHA:-unknown}"
mkdir -p "$ETAT_DIR" backups storage/uploads storage/ged

PRECEDENTE=""
[[ -f "$ETAT_DIR/version_courante" ]] && PRECEDENTE="$(cat "$ETAT_DIR/version_courante")"
IMG_BE="${BEA_IMAGE_BACKEND}:${CIBLE}"
IMG_FE="${BEA_IMAGE_FRONTEND}:${CIBLE}"

etape "Déploiement ${CIBLE} (version en place : ${PRECEDENTE:-aucune}) — $(date '+%F %T')"

# 1. Images ------------------------------------------------------------------
if [[ -n "${IMAGES_TAR:-}" ]]; then
  charger_archive_images
elif ! image_presente "$IMG_BE" || ! image_presente "$IMG_FE"; then
  etape "Téléchargement des images depuis le registre"
  compose pull backend frontend
fi
for img in "$IMG_BE" "$IMG_FE"; do
  image_presente "$img" || echec "image absente après chargement : $img"
done

# 2. Infrastructure + base ---------------------------------------------------
etape "PostgreSQL et Redis"
compose up -d --wait postgres redis

NB_TABLES="$(compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';" | tr -d '[:space:]')"
[[ -n "$NB_TABLES" ]] || echec "PostgreSQL ne répond pas"
if [[ "$NB_TABLES" -eq 0 ]]; then
  echec "base vide : restaurer d'abord le dump de référence (deployment/scripts/restore.sh). \
Les migrations ne s'appliquent jamais sur une base vide."
fi

# 3. Sauvegarde vérifiée -----------------------------------------------------
if [[ "${SKIP_BACKUP:-0}" == "1" ]]; then
  echo "ATTENTION: sauvegarde ignorée (SKIP_BACKUP=1)"
else
  BEA_VERSION="avant_${CIBLE}" bash deployment/scripts/backup-pre-deploy.sh
fi

# 4. Migrations avec l'image de la nouvelle version ---------------------------
etape "Migrations de base (alembic upgrade head)"
REV_AVANT="$(compose run --rm --no-deps -T --entrypoint alembic backend current 2>/dev/null | tail -1 || true)"
echo "Révision avant : ${REV_AVANT:-inconnue}"
compose run --rm --no-deps -T --entrypoint alembic backend upgrade head \
  || echec "migrations en échec : aucune application redémarrée, version ${PRECEDENTE:-précédente} toujours en place. \
Restaurer la sauvegarde si la base est incohérente (deployment/scripts/restore.sh)."
REV_APRES="$(compose run --rm --no-deps -T --entrypoint alembic backend current 2>/dev/null | tail -1 || true)"
echo "Révision après : ${REV_APRES:-inconnue}"

# 5. Redémarrage applicatif --------------------------------------------------
etape "Redémarrage backend, worker, frontend en ${CIBLE}"
compose up -d --no-deps --force-recreate backend worker frontend

# 6. Contrôle ----------------------------------------------------------------
etape "Contrôle de santé ${BASE_URL}"
if controle_sante "$CIBLE"; then
  [[ -n "$PRECEDENTE" && "$PRECEDENTE" != "$CIBLE" ]] && echo "$PRECEDENTE" > "$ETAT_DIR/version_precedente"
  echo "$CIBLE" > "$ETAT_DIR/version_courante"
  echo "$(date '+%F %T') DEPLOY ${CIBLE} OK (avant: ${PRECEDENTE:-aucune}, sha: ${GIT_SHA}, rev: ${REV_APRES})" >> "$ETAT_DIR/historique.log"
  compose ps
  echo "DEPLOY_OK version=${CIBLE}"
  exit 0
fi

echo "ERREUR: contrôle de santé en échec pour ${CIBLE}" >&2
compose logs --tail=80 backend worker >&2 || true
echo "$(date '+%F %T') DEPLOY ${CIBLE} ECHEC" >> "$ETAT_DIR/historique.log"
if [[ -n "$PRECEDENTE" && "$PRECEDENTE" != "$CIBLE" ]]; then
  etape "Retour automatique à ${PRECEDENTE}"
  BEA_VERSION="$PRECEDENTE" bash deployment/scripts/rollback.sh "$PRECEDENTE" || true
fi
exit 1
