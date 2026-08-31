Application web pour la gestion des immobilisations, amortissements, cessions, rebuts, transferts, réévaluations, écritures comptables, rapports et tableaux de bord — conforme au plan comptable bancaire mauritanien.

## Accès (instance Docker locale)

Ouvrir **http://localhost** — le comptable n'a pas à manipuler Docker au quotidien.

Guide complet : [docs/DEPLOIEMENT_LOCAL.md](docs/DEPLOIEMENT_LOCAL.md)

```powershell
.\scripts\backup-from-supabase.ps1   # une fois, avant l'installation
.\scripts\start-local.ps1
.\scripts\restore-local.ps1 -DumpFile backups\LE_DUMP.dump
.\scripts\backup-local.ps1           # quotidien
```

Ne jamais exécuter `docker compose down -v`.

## Développement

- Backend FastAPI : `backend/` (Python 3.13) — `uvicorn app.main:app --reload --port 8000`
- Frontend Angular 20 : `frontend/angular20/`
- Variables cloud : `.env` (gitignoré)
- Variables Docker comptable : `.env.docker` (gitignoré)
