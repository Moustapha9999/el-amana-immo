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

### Activer les migrations après restore

`.env.docker` :

```env
SKIP_MIGRATIONS=0
```

Puis :

```powershell
docker compose --env-file .env.docker up -d backend
# ou dans le conteneur :
docker compose exec backend alembic upgrade head
```

Vérifier : `docker compose exec backend alembic current`

## Nouvelle révision (développeur)

Toujours depuis `backend/` (source canonique) :

```powershell
cd backend
.\.venv\Scripts\alembic.exe revision -m "description_courte"
# Éditer le fichier sous alembic/versions/
.\.venv\Scripts\alembic.exe upgrade head   # sur une DB déjà restorée
```

Contraintes :

- Révisions **additives** (CREATE TABLE / ADD COLUMN) de préférence.
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
