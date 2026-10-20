#!/usr/bin/env bash
# Déploiement d'une version BEA DIGITAL (TEST ou PRODUCTION).
#
#   Hors ligne (archive produite par scripts/release.ps1) :
#     BEA_VERSION=v1.6.0 IMAGES_TAR=/opt/bea/releases/v1.6.0/images.tar ./deployment/scripts/deploy.sh
#   Registre (GitLab / registre interne) :
#     BEA_VERSION=v1.6.0 BEA_IMAGE_BACKEND=registre/bea/backend BEA_IMAGE_FRONTEND=registre/bea/frontend ./deployment/scripts/deploy.sh
#
# Étapes : images → base non vide → sauvegarde vérifiée → analyse des migrations → migrations (nouvelle
#          image) → redémarrage → contrôle /health/ready + /version + worker.
# Échec du contrôle : retour automatique à la version précédente SEULEMENT si aucune migration n'a été
# appliquée ou si toutes déclarent retour_arriere = "compatible" ; sinon arrêt et commande de restauration.
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
mkdir -p "$ETAT_DIR/revisions" "$ETAT_DIR/sauvegardes" backups storage/uploads storage/ged

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
SAUVEGARDE=""
if [[ "${SKIP_BACKUP:-0}" == "1" ]]; then
  echo "ATTENTION: sauvegarde ignorée (SKIP_BACKUP=1)"
else
  BEA_VERSION="avant_${CIBLE}" NOTER_SAUVEGARDE="$ETAT_DIR/sauvegardes/avant_${CIBLE}" \
    bash deployment/scripts/backup-pre-deploy.sh
  SAUVEGARDE="$(cat "$ETAT_DIR/sauvegardes/avant_${CIBLE}")"
fi

# 4. Migrations avec l'image de la nouvelle version ---------------------------
REV_AVANT="$(revision_base)"
[[ -n "$REV_AVANT" ]] || echec "révision Alembic illisible en base (table alembic_version absente ?)"
[[ -n "$PRECEDENTE" && ! -f "$ETAT_DIR/revisions/$PRECEDENTE" ]] && echo "$REV_AVANT" > "$ETAT_DIR/revisions/$PRECEDENTE"
etape "Analyse des migrations à appliquer (depuis ${REV_AVANT})"
analyser_retour "$CIBLE" "$REV_AVANT"
echo "Retour arrière sans restauration : ${RETOUR_ARRIERE}"

etape "Migrations de base (alembic upgrade head)"
compose run --rm --no-deps -T --entrypoint alembic backend upgrade head \
  || echec "migrations en échec : aucune application redémarrée, version ${PRECEDENTE:-précédente} toujours en place. \
Vérifier la révision en base ; si elle a changé, restaurer : REMPLACER=1 VERSION_APPLI=${PRECEDENTE:-<version>} ./deployment/scripts/restore.sh ${SAUVEGARDE:-<sauvegarde>}"
REV_APRES="$(revision_base)"
echo "Révision : ${REV_AVANT} → ${REV_APRES:-inconnue}"
[[ "$REV_APRES" == "$REV_AVANT" ]] && RETOUR_ARRIERE="aucune_migration"

# 5. Redémarrage applicatif --------------------------------------------------
etape "Redémarrage backend, worker, frontend en ${CIBLE}"
DEMARRE=1
compose up -d --no-deps --force-recreate backend worker frontend || DEMARRE=0

# 6. Contrôle ----------------------------------------------------------------
etape "Contrôle de santé ${BASE_URL}"
if [[ "$DEMARRE" -eq 1 ]] && controle_sante "$CIBLE"; then
  [[ -n "$PRECEDENTE" && "$PRECEDENTE" != "$CIBLE" ]] && echo "$PRECEDENTE" > "$ETAT_DIR/version_precedente"
  echo "$CIBLE" > "$ETAT_DIR/version_courante"
  echo "$REV_APRES" > "$ETAT_DIR/revisions/$CIBLE"
  echo "$(date '+%F %T') DEPLOY ${CIBLE} OK (avant: ${PRECEDENTE:-aucune}, sha: ${GIT_SHA}, rev: ${REV_AVANT} → ${REV_APRES}, retour: ${RETOUR_ARRIERE})" >> "$ETAT_DIR/historique.log"
  compose ps
  echo "DEPLOY_OK version=${CIBLE}"
  exit 0
fi

echo "ERREUR: contrôle de santé en échec pour ${CIBLE}" >&2
compose logs --tail=80 backend worker >&2 || true
echo "$(date '+%F %T') DEPLOY ${CIBLE} ECHEC (rev: ${REV_AVANT} → ${REV_APRES}, retour: ${RETOUR_ARRIERE})" >> "$ETAT_DIR/historique.log"
[[ -n "$PRECEDENTE" && "$PRECEDENTE" != "$CIBLE" ]] || exit 1

if [[ "$RETOUR_ARRIERE" == "aucune_migration" || "$RETOUR_ARRIERE" == "compatible" ]]; then
  etape "Retour automatique à ${PRECEDENTE} (schéma : ${RETOUR_ARRIERE})"
  SCHEMA_VERIFIE=1 DEPUIS="$CIBLE" BEA_VERSION="$PRECEDENTE" bash deployment/scripts/rollback.sh "$PRECEDENTE" || true
  exit 1
fi

cat >&2 <<EOF

ARRÊT SANS RETOUR AUTOMATIQUE : les migrations ${REV_AVANT} → ${REV_APRES} ne sont pas déclarées
compatibles avec ${PRECEDENTE}. Relancer ${PRECEDENTE} sur ce schéma risquerait des erreurs ou des
écritures incohérentes. Décision de l'exploitant (DSI) :
  - corriger et livrer une nouvelle version, ou
  - restaurer la base d'avant la mise à jour et relancer ${PRECEDENTE} dessus :
      REMPLACER=1 VERSION_APPLI=${PRECEDENTE} ./deployment/scripts/restore.sh ${SAUVEGARDE:-<aucune sauvegarde : SKIP_BACKUP=1>}
EOF
exit 1
