#!/usr/bin/env bash
# Diagnostics non destructifs BEA DIGITAL (lecture seule).
#
# Usage recommandé (fichier sur le serveur) :
#   cd /opt/bea-digital && bash deployment/scripts/diagnose-readonly.sh
# ou :
#   BEA_ROOT=/opt/bea-digital bash /chemin/vers/diagnose-readonly.sh
#
# Ne crée, ne supprime, ne redémarre et ne modifie rien.
# Ne lit jamais le contenu de .env.production (uniquement présence / permissions).
set -eo pipefail

resoudre_racine() {
  local candidat
  if [[ -n "${BEA_ROOT:-}" ]]; then
    echo "$BEA_ROOT"
    return
  fi
  # Fichier script (échoue si collé dans un shell interactif)
  if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "bash" && "${BASH_SOURCE[0]}" != "-bash" ]]; then
    candidat="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" || candidat=""
    if [[ -n "$candidat" && -f "$candidat/.env.production" ]]; then
      echo "$candidat"
      return
    fi
  fi
  for candidat in /opt/bea-digital /home/moustapha/bea-digital "$PWD"; do
    if [[ -f "$candidat/.env.production" ]]; then
      echo "$candidat"
      return
    fi
  done
  # Dernier recours : /opt même sans .env visible (permissions)
  if [[ -d /opt/bea-digital ]]; then
    echo /opt/bea-digital
    return
  fi
  echo "${PWD:-/}"
}

ROOT_DIR="$(resoudre_racine)"
cd "$ROOT_DIR" || { echo "ERREUR: impossible d'entrer dans $ROOT_DIR" >&2; exit 1; }

HOST_ATTENDU="${BEA_HEALTH_HOST:-192.168.1.55}"
BASE_URL="${BASE_URL:-https://127.0.0.1}"

echo "=== BEA DIGITAL — diagnostic lecture seule ==="
echo "Date     : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Racine   : $ROOT_DIR"
echo "Hôte     : $(hostname 2>/dev/null || echo inconnu)"
if [[ ! -f "$ROOT_DIR/.env.production" ]]; then
  echo "NOTE     : .env.production introuvable sous $ROOT_DIR"
  echo "           Relancer avec : BEA_ROOT=/opt/bea-digital bash diagnose-readonly.sh"
  echo "           (ne pas coller le script dans le shell — l'enregistrer puis l'exécuter)"
fi
echo

echo "==> Système"
uname -a || true
df -h / 2>/dev/null || true
free -h 2>/dev/null || true
uptime 2>/dev/null || true
echo

echo "==> Conteneurs Docker"
if command -v docker >/dev/null 2>&1; then
  sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null \
    || docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null \
    || echo "(docker ps indisponible)"
  echo
  echo "==> Volumes"
  sudo docker volume ls 2>/dev/null || docker volume ls 2>/dev/null || true
  echo
  echo "==> Ressources Docker"
  sudo docker system df 2>/dev/null || docker system df 2>/dev/null || true
else
  echo "docker absent du PATH"
fi
echo

echo "==> Santé / version (Host: ${HOST_ATTENDU})"
if command -v curl >/dev/null 2>&1; then
  curl -ksS --connect-timeout 5 "${BASE_URL}/health/ready" -H "Host: ${HOST_ATTENDU}" || echo "health/ready: echec"
  echo
  curl -ksS --connect-timeout 5 "${BASE_URL}/version" -H "Host: ${HOST_ATTENDU}" || echo "version: echec"
  echo
else
  echo "curl absent"
fi
echo

echo "==> Fichiers sensibles (presence / permissions uniquement)"
for f in .env.production deployment/state/secret_key.sha256 deployment/state/version_courante; do
  if [[ -e "$f" ]]; then
    ls -l "$f" 2>/dev/null || true
  else
    echo "absent : $ROOT_DIR/$f"
  fi
done
if [[ -f deployment/state/version_courante ]]; then
  echo "version_courante=$(cat deployment/state/version_courante)"
fi
if [[ -f deployment/state/secret_key.sha256 ]]; then
  echo "secret_key.sha256=$(tr -d '[:space:]' < deployment/state/secret_key.sha256 | cut -c1-16)…"
fi
echo

echo "==> Montages GED / uploads / backups (inspect lecture seule)"
for c in bea-backend bea-worker bea-postgres; do
  echo "-- $c"
  sudo docker inspect --format '{{json .Mounts}}' "$c" 2>/dev/null \
    || docker inspect --format '{{json .Mounts}}' "$c" 2>/dev/null \
    || echo "inspect indisponible"
done
echo

echo "==> Alerte release-source"
if sudo docker inspect bea-backend 2>/dev/null | grep -q 'release-source' \
  || docker inspect bea-backend 2>/dev/null | grep -q 'release-source'; then
  echo "ATTENTION: montage sous import/incoming/release-source detecte — migrer avant prochaine release."
else
  echo "Aucun chemin release-source detecte dans inspect backend (ou inspect indisponible)."
fi
echo

echo "=== Fin diagnostic (aucune modification) ==="
