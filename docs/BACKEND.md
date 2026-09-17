# Backend — structure

Source **canonique** : `backend/` (Dockerfile compose). `app/` et `alembic/`
à la racine du dépôt = dette, ne pas y coder ni déployer.

Ne pas modifier `backend/app/services/amortissement_engine.py` (règle VNC).

```
backend/app/
├── api/
│   ├── deps.py              # JWT, RBAC
│   └── v1/
│       ├── router.py
│       └── endpoints/       # auth, users, organisation, immobilisations, comptabilite, operations, reporting
├── core/                    # config, security, exceptions, pagination
├── db/                      # Base SQLAlchemy, session async
├── models/                  # domaine découpé (auth, organisation, immobilisation, comptabilite, operations, audit)
├── schemas/                 # Pydantic v2 par domaine
├── repositories/          # BaseRepository (CRUD générique)
├── services/                # logique métier / cas d'usage
├── storage/                 # fichiers locaux (pièces jointes)
└── workers/                 # Celery
```

## Scripts

- `backend/scripts/init_db.py` — création des tables
- `backend/scripts/seed_data.py` — admin, agence, rôles (+ plan El Amana à la première installation)
- `backend/scripts/seed_plan_comptable_el_amana.py` — plan 140/142/147/148/681 et 14 types (idempotent)
- `backend/scripts/bea_digital_ops.py` — contrôles catalogue / totaux (Supabase ou Docker)
- Pack SQL : `scripts/supabase/` (racine dépôt) + `scripts/bea-supabase.ps1`
- Tests : `backend/tests/` (`pytest -q` depuis `backend/` ou la racine du dépôt)

Migration Alembic (base existante Supabase) :

```powershell
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python scripts/seed_plan_comptable_el_amana.py
```

Référentiel métier : `backend/app/data/el_amana_referentiel.py`.

## Démarrage

```powershell
cd backend
$env:DATABASE_URL="postgresql+asyncpg://immo_user:immo_pass@localhost:5432/bea_digital"
python scripts/seed_data.py
uvicorn app.main:app --reload
```

Documentation API : http://localhost:8000/docs

Socle Login 1 / Login 2 / permissions : [docs/socle-bea-digital.md](socle-bea-digital.md).
