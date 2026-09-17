# Démarrer BEA DIGITAL

Stack : FastAPI (Python 3.13) + Angular 20 + **une** PostgreSQL 17.
Backend canonique : `backend/`. Front : `frontend/angular20/`.

Ne jamais exécuter `docker compose down -v`.

## 1. Instance Docker (même compose que le comptable)

```powershell
copy .env.docker.example .env.docker
# Renseigner SECRET_KEY et POSTGRES_PASSWORD (et la DATABASE_URL qui va avec)
docker compose --env-file .env.docker up -d
```

- Postgres healthy, base physique locale `bea_digital` (tables métier inchangées).
- Backend healthy avec **`SKIP_MIGRATIONS=1`** (défaut compose / `.env.docker.example`).
- Front : **http://localhost** (nginx proxifie `/api/` vers le backend). Pas de `:4200`.

Sans dump : la base est vide (extensions seulement). Ne **pas** retirer
`SKIP_MIGRATIONS` pour « créer » le schéma.

### Restore du dump (vraie base)

Placer le dump dans `backups/` (hors git), Postgres déjà up, `public` **sans** tables :

```powershell
.\scripts\db-restore.ps1 -DumpFile backups\LE_DUMP.dump
```

Linux / Git Bash :

```bash
./scripts/db-restore.sh backups/LE_DUMP.dump
```

Contrôles attendus après restore : nombre d’immobilisations, somme des valeurs
brutes, cumul des amortissements, VNC, puis copie de `storage/uploads`.

Le script **refuse** si `public` contient déjà des tables.

Kit comptable historique (recréation agressive de la base) :
`.\scripts\restore-local.ps1` — ne pas confondre avec `db-restore`, qui est
non destructif.

## 2. Hors Docker (exception)

Le quotidien est **Docker → http://localhost**. `ng serve` (:4200) et uvicorn
(:8000) ne sont plus le chemin BEA DIGITAL.

Pour un smoke test jetable uniquement, voir `backend/scripts/seed_data.py` —
jamais sur la base Comptabilité.

## 3. Smoke test login (base jetable UNIQUEMENT)

Ce n’est **pas** le chemin prod / Comptabilité :

```powershell
cd backend
$env:PYTHONPATH = "."
$env:DATABASE_URL = "postgresql+asyncpg://immo_user:MOT_DE_PASSE@localhost:5432/bea_digital"
python scripts/init_db.py
python scripts/seed_data.py
```

Puis : login → **Accueil** → Comptabilité → Dashboard / Immobilisations /
Amortissements / Archives ; fil d’Ariane ; retour Accueil.

La prod / la vraie base = `pg_restore` du dump Supabase, **jamais** Alembic à vide.

## 4. Tests backend

Suite unique : `backend/tests/` (ne pas relancer une suite à la racine du dépôt).

```powershell
cd backend
pytest -q
```

Depuis la racine : `pytest -q` (le `pytest.ini` pointe déjà vers `backend/tests`).

## 5. Build front (CI / vérif)

```powershell
cd frontend\angular20
npm install
npm run build
```

## Références

- [base-de-donnees-unique.md](base-de-donnees-unique.md)
- [frontend-plateforme.md](frontend-plateforme.md)
- [DEPLOIEMENT_LOCAL.md](DEPLOIEMENT_LOCAL.md) — kit USB machine comptable
- [AGENTS.md](../AGENTS.md) — invariants
