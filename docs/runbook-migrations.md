# Runbook — migrations Alembic (base réelle uniquement)

## Règle d’or

**Jamais** `alembic upgrade head` sur une base **vide**.
La 1ʳᵉ révision (`20260723_el_amana`) est un `ALTER` de tables déjà présentes
(dump Supabase / historique). Sur vide → schéma faux.

`SKIP_MIGRATIONS=1` reste le défaut compose / `.env.docker` jusqu’au restore.

## Chemin correct (local / TEST)

```text
1. docker compose up (SKIP_MIGRATIONS=1)
2. Restore dump → scripts/db-restore.ps1 | .sh
3. Contrôles métier (nb immos, VB, cumul, VNC)
4. Recopier storage/uploads (+ storage/ged si utilisé)
5. SKIP_MIGRATIONS=0  UNIQUEMENT pour appliquer les nouvelles
   révisions incrémentales (20260917_*, 20260918_*, 20260919_*, …)
6. Relancer le backend
```

### Appliquer les migrations

Le backend et le worker se connectent avec `bea_app` (`database/roles/bea_app.sql`),
qui n'a aucun droit de structure : `SKIP_MIGRATIONS` reste à `1` et les migrations
passent par le service `migrate` (compte `admin`, jamais démarré par `up`) :

```powershell
docker compose --env-file .env.docker build
docker compose --env-file .env.docker run --rm migrate
docker compose --env-file .env.docker up -d --no-build
```

Vérifier : `docker compose --env-file .env.docker run --rm migrate current`

Les tables créées par une migration reçoivent automatiquement les droits de `bea_app`
(privilèges par défaut). Après restauration d'un dump ou création d'une copie `*_test`,
rejouer le script sur la base concernée :

```powershell
$env:BEA_APP_DB_PASSWORD = (Select-String -Path .env.docker -Pattern '^BEA_APP_DB_PASSWORD=(.*)$').Matches[0].Groups[1].Value.Trim()
Get-Content database\roles\bea_app.sql -Raw | docker exec -i -e BEA_APP_DB_PASSWORD bea-postgres psql -U admin -d bea_digital -X -q
Remove-Item Env:BEA_APP_DB_PASSWORD
```

### Droits des dossiers

Backend et worker tournent sans root (uid 10001). Après une recopie de `storage/uploads`,
`storage/ged` ou `backups` (restauration, nouveau serveur, fichiers déposés en root),
redonner les dossiers à ce compte :

```powershell
docker run --rm --user 0 --entrypoint sh -v "${PWD}/storage/uploads:/u" -v "${PWD}/storage/ged:/g" -v "${PWD}/backups:/b" bea-digital-backend:latest -c "chown -R 10001:10001 /u /g /b"
```

Sur le serveur Linux TEST/PROD : `sudo chown -R 10001:10001 storage/uploads storage/ged backups`.

## Nouvelle révision (développeur)

Toujours depuis `backend/` (source canonique) :

```powershell
cd backend
.\.venv\Scripts\alembic.exe revision -m "description_courte"
# Éditer le fichier sous alembic/versions/
.\.venv\Scripts\alembic.exe upgrade head   # sur une DB déjà restorée
```

Contraintes :

- Déclarer au niveau du module, juste après `depends_on` :

  ```python
  retour_arriere = "compatible"    # la version précédente du code fonctionne sur le schéma migré
  # ou
  retour_arriere = "restauration"  # revenir à la version précédente exige la sauvegarde d'avant
  ```

  `compatible` seulement si l'ancien code lit **et écrit** sans erreur après migration : ajout de table,
  ajout de colonne nullable ou avec valeur par défaut, ajout d'index. Tout le reste est `restauration` :
  suppression ou renommage, colonne `NOT NULL` sans défaut, changement de type, contrainte nouvelle que
  l'ancien code peut violer, réécriture de données (`UPDATE` / `DELETE`) dont l'ancien code dépend.
  Vérifié par `python scripts/migrations_retour.py --verifier` (tests, `release.ps1`) et appliqué par
  `deployment/scripts/rollback.sh`.
- Révisions **additives** (CREATE TABLE / ADD COLUMN) de préférence.
- Pas d'`autocommit_block` (ex. `CREATE INDEX CONCURRENTLY`) sans le signaler : il sort de la transaction
  unique et un échec laisserait la base partiellement migrée.
- Pas de `DROP` destructif sans plan backup + validation Comptabilité.
- Ne pas coder dans `app/` + `alembic/` à la **racine** du dépôt (dette).

## Production banque

```text
BACKUP (pg_dump + storage)
  → Maintenance / version CORE ADMIN
  → Déployer image backend
  → alembic upgrade head (ou entrypoint si SKIP_MIGRATIONS=0)
  → Smoke tests Login 1 / Login 2 / immo
  → Si échec : STOP + restore backup
```

Pipeline / scripts serveur : [deployment/06-procedures.md](deployment/06-procedures.md),
[`deployment/scripts/`](../deployment/scripts/), [runbook GitLab](deployment/05-pipeline-gitlab.md).

## Dette à ne pas toucher

| Chemin | Statut |
|--------|--------|
| `backend/alembic/` | **Canonique** |
| `alembic/` (racine) | Dette — ne pas déployer |
| `app/` (racine) | Dette — ne pas coder |

Voir aussi : [base-de-donnees-unique.md](base-de-donnees-unique.md), [demarrer.md](demarrer.md), `AGENTS.md`.
