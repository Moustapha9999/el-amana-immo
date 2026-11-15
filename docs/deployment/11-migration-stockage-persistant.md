# Migration stockage persistant — hors `release-source`

**Contexte :** relevés 13/11 et 15/11/2026 ([10-dossier-transmission-2026-11-13.md](10-dossier-transmission-2026-11-13.md)).  
**Risque :** GED, uploads et backups Docker pointent vers  
`/opt/bea-digital/import/incoming/release-source/...` alors que `/srv/bea-digital/{GED,uploads,backups}` existe déjà sur l’hôte sans être monté. Remplacer ou nettoyer `release-source` lors d’une release **effacerait** les données métier montées.

**État 15/11 :** montages `release-source` GED/uploads = **0 octet** (rien écrit via l’appli).  
`/srv/bea-digital/uploads` ≈ 304 Ko avec structure `archives/`, `clientele/`, `pieces/`, `.gitkeep` — **non monté** par les conteneurs. Risque de perte immédiat faible ; migration quand même **avant la prochaine release**.

`deploy.sh` refuse désormais un déploiement si `storage/uploads`, `storage/ged` ou `backups` résolvent vers `import/incoming/release-source`, sauf dérogation explicite `ALLOW_RELEASE_SOURCE_MOUNTS=1`.

---

## 1. Cible

| Rôle | Chemin hôte stable | Montage conteneur |
|------|--------------------|-------------------|
| Pièces | `/srv/bea-digital/uploads` | `/app/storage/uploads` |
| GED | `/srv/bea-digital/GED` (ou `ged`, aligner la casse réelle) | `/app/storage/ged` |
| Backups | `/srv/bea-digital/backups` | `/backups` |
| PostgreSQL | volume Docker `bea_postgres_data` | inchangé |
| Compose relatif | Liens / bind sous la racine de déploiement (`storage/…`, `backups/`) → cibles `/srv/...` | inchangé côté compose si les chemins relatifs sont des liens |

Le compose prod ([`deployment/docker-compose.prod.yml`](../../deployment/docker-compose.prod.yml)) monte déjà `../storage/uploads`, `../storage/ged`, `../backups` depuis la racine du déploiement. La migration consiste à faire pointer ces chemins vers `/srv/bea-digital/...` **sans** passer par `release-source`.

---

## 2. Prérequis (lecture seule d’abord)

1. Exécuter `bash deployment/scripts/diagnose-readonly.sh` et archiver la sortie.
2. Noter les montages actuels :

```bash
sudo docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' bea-backend
sudo docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' bea-worker
sudo docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' bea-postgres
```

3. Mesurer tailles source et cible :

```bash
sudo du -sh /opt/bea-digital/import/incoming/release-source/storage/ged \
           /opt/bea-digital/import/incoming/release-source/storage/uploads \
           /opt/bea-digital/import/incoming/release-source/backups \
           /srv/bea-digital/GED /srv/bea-digital/uploads /srv/bea-digital/backups 2>/dev/null
```

4. Sauvegarde fraîche **avant** toute copie :

```bash
cd /opt/bea-digital   # racine réelle
./deployment/scripts/backup-pre-deploy.sh pre_migration_stockage
# Copier aussi le dump + archive fichiers hors serveur (politique DSI)
```

5. Fenêtre de maintenance courte validée (arrêt contrôlé backend/worker uniquement au moment du basculement des liens — pas de `down -v`).

---

## 3. Procédure proposée

### Étape A — Préparer `/srv` (sans couper le service)

```bash
sudo mkdir -p /srv/bea-digital/uploads /srv/bea-digital/GED /srv/bea-digital/backups
sudo chown -R "$(id -u)":"$(id -g)" /srv/bea-digital/uploads /srv/bea-digital/GED /srv/bea-digital/backups
```

Ajuster propriétaire/uid au compte qui exécute Docker et aux uid des conteneurs (backend non-root `10001` si applicable). Vérifier les droits en écriture **après** bascule.

### Étape B — Copier depuis la source réellement montée

Identifier `SRC_GED`, `SRC_UPLOADS`, `SRC_BACKUPS` d’après l’inspect (§2). Exemple si la source est encore `release-source` :

```bash
SRC_GED=/opt/bea-digital/import/incoming/release-source/storage/ged
SRC_UPLOADS=/opt/bea-digital/import/incoming/release-source/storage/uploads
SRC_BACKUPS=/opt/bea-digital/import/incoming/release-source/backups

# rsync -a conserve droits ; --dry-run d'abord
rsync -a --dry-run "$SRC_GED"/ /srv/bea-digital/GED/
rsync -a "$SRC_GED"/ /srv/bea-digital/GED/
rsync -a "$SRC_UPLOADS"/ /srv/bea-digital/uploads/
rsync -a "$SRC_BACKUPS"/ /srv/bea-digital/backups/
```

Comparer totaux (`du`, comptage de fichiers) avant de continuer. Ne **pas** supprimer la source à ce stade.

### Étape C — Basculer les chemins de la racine de déploiement

Depuis la racine (ex. `/opt/bea-digital`) :

```bash
# Arrêt applicatif bref (PAS postgres volume, PAS -v)
docker compose --env-file .env.production -f deployment/docker-compose.prod.yml stop backend worker frontend

# Remplacer dossiers/liens relatifs par des liens vers /srv
# (adapter si storage/ ou backups/ sont déjà des liens)
mv storage/ged "storage/ged.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
mv storage/uploads "storage/uploads.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
# backups/ : préférer fusion déjà faite sous /srv puis lien
ln -sfn /srv/bea-digital/GED storage/ged
ln -sfn /srv/bea-digital/uploads storage/uploads
ln -sfn /srv/bea-digital/backups backups

readlink -f storage/ged storage/uploads backups
# Doit afficher /srv/bea-digital/... et PAS release-source

docker compose --env-file .env.production -f deployment/docker-compose.prod.yml up -d backend worker frontend
curl -ksS https://127.0.0.1/health/ready -H 'Host: 192.168.1.55'
```

### Étape D — Vérifications

- `diagnose-readonly.sh` : plus d’alerte `release-source`.
- Écriture test contrôlée (fichier temporaire GED/upload) puis suppression.
- `/health/ready` et `/version` OK.
- `deploy.sh` ne refuse plus pour cause de montage `release-source` (sans `ALLOW_RELEASE_SOURCE_MOUNTS`).

### Étape E — Conservation puis retrait de `release-source`

Conserver la copie sous `release-source` **au moins** jusqu’à validation métier + une sauvegarde post-migration externalisée. Suppression ultérieure = décision DSI explicite, jamais un « ménage » opportuniste.

---

## 4. Ce qu’il ne faut pas faire

- `docker compose down -v` / `docker volume prune` / `rm -rf` sur `release-source` avant bascule validée.
- Pointer à la fois compose **et** un second arbre `/srv` sans liens cohérents (double vérité).
- Migrer pendant un `deploy.sh` de nouvelle version (séparer migration stockage et montée de version).
- Modifier `SECRET_KEY` ou MFA « au passage ».

---

## 5. Critères de done

- [ ] Montages backend/worker/postgres : sources sous `/srv/bea-digital/...`
- [ ] `readlink -f storage/ged storage/uploads backups` sans `release-source`
- [ ] Santé OK, test écriture GED/uploads OK
- [ ] Sauvegarde post-migration externalisée
- [ ] Dossier transmission / inventaire mis à jour avec les nouveaux chemins
)
