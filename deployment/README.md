# Squelettes déploiement production BEA-DIGITAL
#
# | Fichier | Rôle |
# |---------|------|
# | docker-compose.prod.yml | Stack prod (images taguées, PG non exposé) |
# | env.production.example | Modèle secrets (copier → .env.production hors git) |
# | nginx/bea-digital.conf.template | Reverse proxy HTTPS (IT) |
# | scripts/backup-pre-deploy.sh | Backup vérifié avant deploy |
# | scripts/deploy.sh | Pull + recreate + healthcheck |
# | scripts/rollback.sh | Retour image précédente |
# | inventory.template.md | Inventaire DSI |
#
# Documentation : docs/deployment/
