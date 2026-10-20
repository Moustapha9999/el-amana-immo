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

# Attend /health/ready (base + Redis) puis vérifie que /version annonce la version attendue.
controle_sante() {
  local attendue="$1" i
  for i in $(seq 1 "$HEALTH_RETRIES"); do
    if curl -fsS "$BASE_URL/health/ready" > /tmp/bea-ready.json 2>/dev/null; then
      local v
      v="$(curl -fsS "$BASE_URL/version" 2>/dev/null | sed -n 's/.*"version" *: *"\([^"]*\)".*/\1/p')"
      if [[ "$v" == "$attendue" ]]; then
        echo "Santé OK (tentative $i) — version ${v}"
        cat /tmp/bea-ready.json; echo
        return 0
      fi
      echo "  version servie « ${v} » ≠ « ${attendue} » (tentative $i)"
    fi
    sleep "$HEALTH_SLEEP"
  done
  return 1
}
