#!/usr/bin/env bash
# Fonctions communes aux scripts de déploiement (à sourcer depuis la racine du dépôt déployé).

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-deployment/docker-compose.prod.yml}"
ETAT_DIR="${ETAT_DIR:-deployment/state}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
HEALTH_RETRIES="${HEALTH_RETRIES:-40}"
HEALTH_SLEEP="${HEALTH_SLEEP:-3}"

etape() { echo; echo "==> $*"; }
echec() { echo "ERREUR: $*" >&2; exit 1; }

valeur_env() {
  grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//'
}

charger_env() {
  [[ -f "$ENV_FILE" ]] || echec "$ENV_FILE introuvable (copier deployment/env.*.example)"
  ENV_FILE_PATH="$(cd "$(dirname "$ENV_FILE")" && pwd)/$(basename "$ENV_FILE")"
  POSTGRES_USER="$(valeur_env POSTGRES_USER)"; POSTGRES_USER="${POSTGRES_USER:-bea_digital_app}"
  POSTGRES_DB="$(valeur_env POSTGRES_DB)"; POSTGRES_DB="${POSTGRES_DB:-bea_digital}"
  BEA_IMAGE_BACKEND="${BEA_IMAGE_BACKEND:-$(valeur_env BEA_IMAGE_BACKEND)}"
  BEA_IMAGE_FRONTEND="${BEA_IMAGE_FRONTEND:-$(valeur_env BEA_IMAGE_FRONTEND)}"
  BEA_IMAGE_BACKEND="${BEA_IMAGE_BACKEND:-bea-digital/backend}"
  BEA_IMAGE_FRONTEND="${BEA_IMAGE_FRONTEND:-bea-digital/frontend}"
  local u; u="$(valeur_env BEA_HTTP_BIND)"
  [[ -n "$u" ]] && BASE_URL="${BASE_URL_OVERRIDE:-http://${u}}"
  export ENV_FILE_PATH BEA_IMAGE_BACKEND BEA_IMAGE_FRONTEND
  # Version courante si non fournie (sauvegarde planifiée, rollback…)
  if [[ -z "${BEA_VERSION:-}" && -f "$ETAT_DIR/version_courante" ]]; then
    BEA_VERSION="$(cat "$ETAT_DIR/version_courante")"
  fi
  export BEA_VERSION="${BEA_VERSION:-}"
}

compose() {
  # BEA_VERSION est requis par le fichier compose même pour postgres/redis seuls (premier chargement).
  BEA_VERSION="${BEA_VERSION:-non-deployee}" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

image_presente() {
  docker image inspect "$1" > /dev/null 2>&1
}

# Charge l'archive IMAGES_TAR (livraison hors ligne) après contrôle de son empreinte SHA-256.
charger_archive_images() {
  [[ -n "${IMAGES_TAR:-}" ]] || return 0
  [[ -f "$IMAGES_TAR" ]] || echec "archive introuvable : $IMAGES_TAR"
  if [[ -f "${IMAGES_TAR}.sha256" ]]; then
    etape "Contrôle d'intégrité de l'archive"
    ( cd "$(dirname "$IMAGES_TAR")" && sha256sum -c "$(basename "$IMAGES_TAR").sha256" ) \
      || echec "empreinte SHA-256 invalide : archive corrompue ou modifiée"
  else
    echo "ATTENTION: pas de fichier ${IMAGES_TAR}.sha256 — intégrité non vérifiée"
  fi
  etape "Chargement des images (docker load)"
  docker load -i "$IMAGES_TAR"
}

# Révision Alembic réellement enregistrée en base (indépendante de l'image qui tourne).
revision_base() {
  compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null | tr -d '[:space:]'
}

# Compatibilité retour arrière des migrations entre <révision> et la head de l'image <version>.
# Affiche le détail ; positionne RETOUR_ARRIERE=aucune_migration|compatible|restauration.
analyser_retour() {
  local version="$1" depuis="$2" sortie
  sortie="$(BEA_VERSION="$version" compose run --rm --no-deps -T --entrypoint python backend \
    scripts/migrations_retour.py "$depuis" 2>&1 || true)"
  echo "$sortie" | grep -v '^RETOUR_ARRIERE=' || true
  RETOUR_ARRIERE="$(echo "$sortie" | sed -n 's/^RETOUR_ARRIERE=//p' | tail -1)"
  RETOUR_ARRIERE="${RETOUR_ARRIERE:-restauration}"
}

# Santé du worker : état du healthcheck Docker (ping Celery), le worker n'ayant pas d'URL.
worker_sain() {
  local id
  id="$(compose ps -q worker 2>/dev/null)"
  [[ -n "$id" ]] && [[ "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$id" 2>/dev/null)" == "healthy" ]]
}

# Attend /health/ready (base + Redis) et /version = version attendue, puis le worker sain.
# /health (sans suffixe) ne teste que le processus API : il sert au healthcheck Docker du conteneur.
controle_sante() {
  local attendue="$1" i api_ok=0
  for i in $(seq 1 "$HEALTH_RETRIES"); do
    if [[ "$api_ok" -eq 0 ]] && curl -fsS "$BASE_URL/health/ready" > /tmp/bea-ready.json 2>/dev/null; then
      local v
      v="$(curl -fsS "$BASE_URL/version" 2>/dev/null | sed -n 's/.*"version" *: *"\([^"]*\)".*/\1/p')"
      if [[ "$v" == "$attendue" ]]; then
        echo "API OK (tentative $i) — version ${v}"
        cat /tmp/bea-ready.json; echo
        api_ok=1
      else
        echo "  version servie « ${v} » ≠ « ${attendue} » (tentative $i)"
      fi
    fi
    if [[ "$api_ok" -eq 1 ]] && worker_sain; then
      echo "Worker OK (tentative $i)"
      return 0
    fi
    sleep "$HEALTH_SLEEP"
  done
  [[ "$api_ok" -eq 1 ]] && echo "ERREUR: worker non sain (healthcheck Celery)" >&2
  return 1
}
