# Système de Gestion des Immobilisations Bancaires (Mauritanie)

Application web pour la gestion des immobilisations, amortissements, cessions, rebuts, transferts, réévaluations, écritures comptables, rapports et tableaux de bord — conforme au plan comptable bancaire mauritanien.

## Stack

| Couche | Technologies |
|--------|--------------|
| Frontend | Angular 20, TypeScript, Angular Material, Tailwind CSS, ngx-translate |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, JWT, Celery |
| Data | PostgreSQL 17, Redis |
| Ops | Docker, Docker Compose, Nginx, GitHub Actions |

## Structure

```
el-amana-immo/
├── frontend/angular20/   # SPA Angular
├── backend/app/        # API REST (Clean Architecture)
├── database/           # init, migrations, backup
├── docker-compose.yml
├── docs/               # cahier des charges & architecture
└── scripts/
```

## Démarrage rapide (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API : http://localhost:8000/docs  
- Frontend : http://localhost:4200  

## Démarrage local (dev)

### Backend + Supabase

Voir **`docs/SUPABASE.md`** (`.env` à la racine avec `DATABASE_URL` Supabase + `DATABASE_SSL=true`).

```powershell
.\scripts\dev-backend.ps1
```

Ou manuellement : `backend/scripts/test_db_connection.py` puis `seed_data.py`, puis `uvicorn`.

Compte seed : `admin@el-amana.mr` / `Admin@2026`

### Frontend

```bash
cd frontend/angular20
npm install
npm start
```

## Phases de livraison (A → Z)

1. **Fondation (en cours)** — monorepo, Docker, auth JWT + RBAC, modèle immobilisations, dashboard KPI minimal.
2. **Référentiels** — agences, directions, départements, centres de coût, catégories, plan comptable.
3. **Amortissements** — calcul auto/manuel, simulation, validation, écritures 681xxx / 148xxx.
4. **Sorties** — cessions, rebuts, plus/moins-values, écritures.
5. **Inventaire** — QR / codes-barres, scan mobile.
6. **Rapports & audit** — PDF/Excel, journal d’audit complet.
7. **Production** — durcissement sécurité, 2FA, CI/CD complet, tests E2E.

Voir `docs/CAHIER_DES_CHARGES.md` pour le détail fonctionnel.
