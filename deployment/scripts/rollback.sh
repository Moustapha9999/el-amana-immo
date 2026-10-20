#!/usr/bin/env bash
# Retour à une version précédente du code (images déjà présentes sur le serveur, sinon registre).
#   ./deployment/scripts/rollback.sh            → version_precedente enregistrée par deploy.sh
#   ./deployment/scripts/rollback.sh v1.5.2     → version donnée
#
# Ne modifie PAS la base. Avant de relancer l'ancien code, compare la révision Alembic en base à celle
# sous laquelle la version cible tournait (deployment/state/revisions/<version>) :
#   - identique                                   → retour autorisé ;
#   - migrations intermédiaires toutes déclarées
#     retour_arriere = "compatible"               → retour autorisé ;
#   - sinon (restauration, non déclarée, inconnue) → refus, avec la commande de restauration.
# SCHEMA_VERIFIE=1 : l'exploitant atteste la compatibilité (vérifiée hors script) et force le retour.
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

ACTUELLE="$(cat "$ETAT_DIR/version_courante" 2>/dev/null || true)"
BEA_VERSION="$CIBLE"
charger_env
BEA_VERSION="$CIBLE"; export BEA_VERSION
export GIT_SHA="${GIT_SHA:-rollback}"

etape "Compatibilité du schéma avec ${CIBLE}"
compose up -d --wait postgres redis
REV_BASE="$(revision_base)"
REV_CIBLE="$(cat "$ETAT_DIR/revisions/$CIBLE" 2>/dev/null || true)"
echo "Révision en base : ${REV_BASE:-inconnue} ; révision de ${CIBLE} : ${REV_CIBLE:-non enregistrée}"

if [[ "${SCHEMA_VERIFIE:-0}" == "1" ]]; then
  echo "SCHEMA_VERIFIE=1 : compatibilité attestée par l'exploitant"
elif [[ -n "$REV_CIBLE" && "$REV_CIBLE" == "$REV_BASE" ]]; then
  echo "Schéma identique : retour sans risque"
else
  RETOUR_ARRIERE="restauration"
  if [[ -n "$REV_CIBLE" && -n "$ACTUELLE" ]]; then
    analyser_retour "$ACTUELLE" "$REV_CIBLE"
  fi
  if [[ "$RETOUR_ARRIERE" != "compatible" ]]; then
    SAUV="$(cat "$ETAT_DIR/sauvegardes/avant_${ACTUELLE}" 2>/dev/null || true)"
    echec "retour à ${CIBLE} refusé : compatibilité du schéma non établie (${REV_CIBLE:-révision inconnue} → ${REV_BASE}).
  Options :
    - restaurer la base d'avant ${ACTUELLE:-la mise à jour} et relancer ${CIBLE} dessus
      (les données saisies depuis cette sauvegarde sont perdues) :
        REMPLACER=1 VERSION_APPLI=${CIBLE} ./deployment/scripts/restore.sh ${SAUV:-<sauvegarde avant_${ACTUELLE}>}
    - ou, si la compatibilité a été vérifiée migration par migration : SCHEMA_VERIFIE=1 ./deployment/scripts/rollback.sh ${CIBLE}"
  fi
fi

etape "Retour à ${CIBLE}"
if ! image_presente "${BEA_IMAGE_BACKEND}:${CIBLE}" || ! image_presente "${BEA_IMAGE_FRONTEND}:${CIBLE}"; then
  compose pull backend frontend || echec "images ${CIBLE} introuvables (charger l'archive de cette version)"
fi
DEMARRE=1
compose up -d --no-deps --force-recreate backend worker frontend || DEMARRE=0

if [[ "$DEMARRE" -eq 1 ]] && controle_sante "$CIBLE"; then
  echo "$CIBLE" > "$ETAT_DIR/version_courante"
  [[ -n "$ACTUELLE" && "$ACTUELLE" != "$CIBLE" ]] && echo "$ACTUELLE" > "$ETAT_DIR/version_precedente"
  echo "$(date '+%F %T') ROLLBACK ${CIBLE} OK (depuis: ${DEPUIS:-${ACTUELLE:-?}}, rev: ${REV_BASE})" >> "$ETAT_DIR/historique.log"
  echo "ROLLBACK_OK version=${CIBLE}"
else
  echo "$(date '+%F %T') ROLLBACK ${CIBLE} ECHEC" >> "$ETAT_DIR/historique.log"
  echec "contrôle de santé en échec après retour à ${CIBLE} — escalader (logs : docker compose logs backend)"
fi
