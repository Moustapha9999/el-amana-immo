# Livraison et mises à jour — TEST puis PRODUCTION

Principe : **une version = des images construites une seule fois**, identiques en TEST et en
PRODUCTION. Rien n'est compilé sur les serveurs. Frontend et backend portent toujours le même
numéro (`vX.Y.Z`) ; `/version` indique ce qui tourne réellement.

## Composants déployés (5 conteneurs, un seul hôte)

| Service | Image | Rôle | Exposition |
|---------|-------|------|------------|
| `frontend` | `bea-digital/frontend:vX.Y.Z` | Angular + nginx, proxifie `/api/`, `/health`, `/version` | `127.0.0.1:8080` (reverse proxy HTTPS de l'hôte) |
| `backend` | `bea-digital/backend:vX.Y.Z` | API FastAPI | réseau interne |
| `worker` | même image que backend | tâches de fond (échéances, OCR, supervision) | réseau interne |
| `postgres` | `postgres:17` (Debian) | base unique BEA DIGITAL | réseau interne, volume `bea_postgres_data` |
| `redis` | `redis:7-alpine` | file de tâches, anti-doublon | réseau interne |

Données persistantes sur l'hôte : volume `bea_postgres_data`, `storage/uploads` (pièces),
`storage/ged` (GED), `backups/`. Logs Docker limités à 5 × 20 Mo par conteneur.

## Côté développement — produire une version

```powershell
.\scripts\release.ps1 -Version v1.0.0 -Tests -PousserTag
```

Produit `dist\releases\v1.0.0\` :

| Fichier | Contenu |
|---------|---------|
| `images.tar` + `images.tar.sha256` | 4 images (backend, frontend, postgres, redis) + empreinte d'intégrité |
| `deploiement.tar.gz` | compose, scripts, modèles `.env`, nginx, documentation |
| `manifest.json` | version, commit, date, révision de base attendue, identifiants des images |
| `LISEZMOI.txt` | commandes exactes à lancer sur le serveur |

Le script refuse de livrer si le code n'est pas commité, si la version existe déjà, si l'API ne
démarre pas ou s'il existe plusieurs têtes de migration.

Numérotation : `vMAJEUR.MINEUR.CORRECTIF` — nouveau module = MINEUR (`v1.1.0`), correction = CORRECTIF
(`v1.1.1`), rupture (changement de base non rétrocompatible) = MAJEUR.

## Côté serveur — dossier `/opt/bea-digital`

```text
/opt/bea-digital/
  .env.production          secrets (chmod 600, hors Git)
  deployment/              scripts + compose (extraits de deploiement.tar.gz)
  deployment/state/        version_courante, version_precedente, historique.log
  releases/vX.Y.Z/         livraisons reçues
  backups/                 sauvegardes (à répliquer hors serveur)
  storage/uploads, storage/ged
```

### Première installation

```bash
cd /opt/bea-digital
tar -xzf releases/v1.0.0/deploiement.tar.gz
cp deployment/env.production.example .env.production && chmod 600 .env.production   # renseigner
IMAGES_TAR=releases/v1.0.0/images.tar ./deployment/scripts/restore.sh backups/reprise.dump backups/reprise_fichiers.tar.gz
BEA_VERSION=v1.0.0 IMAGES_TAR=releases/v1.0.0/images.tar ./deployment/scripts/deploy.sh
```

`restore.sh` refuse une base non vide et affiche les contrôles de rapprochement (utilisateurs,
immobilisations, valeur brute, clients, classifications).

### Mise à jour

```bash
cd /opt/bea-digital
tar -xzf releases/v1.1.0/deploiement.tar.gz
BEA_VERSION=v1.1.0 IMAGES_TAR=releases/v1.1.0/images.tar ./deployment/scripts/deploy.sh
```

Étapes automatiques de `deploy.sh` :

1. contrôle SHA-256 de l'archive, chargement des images (ou téléchargement depuis un registre) ;
2. refus si la base est vide (les migrations ne s'appliquent jamais sur une base vide) ;
3. **sauvegarde vérifiée** : dump PostgreSQL (taille minimale + relecture `pg_restore --list`),
   archive des pièces et de la GED, empreintes, purge au-delà de 30 jours ;
4. migrations `alembic upgrade head` avec l'image de la nouvelle version — en cas d'échec, rien
   n'est redémarré, l'ancienne version reste en service ;
5. redémarrage `backend`, `worker`, `frontend` ;
6. contrôle `/health/ready` (base + Redis) **et** `/version` = version attendue ;
7. échec du contrôle → **retour automatique** à la version précédente, code de sortie ≠ 0.

### Retour arrière / reprise

| Situation | Commande |
|-----------|----------|
| Revenir à la version précédente | `./deployment/scripts/rollback.sh` |
| Revenir à une version donnée | `./deployment/scripts/rollback.sh v1.0.0` |
| Restaurer une sauvegarde (incident de données) | `REMPLACER=1 ./deployment/scripts/restore.sh backups/bea_….dump backups/bea_…_fichiers.tar.gz` |

Le retour arrière ne touche pas la base : les migrations sont additives, l'ancienne version
fonctionne sur la base migrée. `REMPLACER=1` sauvegarde d'abord l'état actuel, puis remplace la base
et relance l'application.

### Sauvegarde planifiée (en plus des sauvegardes de déploiement)

```cron
30 1 * * * cd /opt/bea-digital && ./deployment/scripts/backup-pre-deploy.sh nuit >> backups/backup.log 2>&1
```

Le dossier `backups/` doit être répliqué hors du serveur (politique DSI).

## Registre (quand la DSI fournit GitLab)

Même `deploy.sh`, sans `IMAGES_TAR` : renseigner `BEA_IMAGE_BACKEND` / `BEA_IMAGE_FRONTEND` dans
`.env.production`. La pipeline `.gitlab-ci.yml` construit et publie les images sur tag `v*`, puis
`deploy:production` (manuel) se connecte au serveur et lance `deploy.sh`.

## Validation effectuée (20/10/2026)

Serveur Linux simulé (Docker isolé), livraison hors ligne `v0.9.0-essai`, copie de la base réelle :
première installation (200 tables, révision `20261020_clientele_14`), déploiement, mise à jour,
mise à jour volontairement cassée (retour automatique), retour arrière manuel, reprise après
incident (`REMPLACER=1`). Reste à valider sur l'infrastructure réelle : reverse proxy HTTPS,
SMTP, sauvegardes externalisées, supervision.

**Interdit : `docker compose down -v`** (efface la base).
