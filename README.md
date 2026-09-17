# BEA DIGITAL

Plateforme interne de digitalisation des processus de **Banque El Amana (BEA), Mauritanie**.

Ce dépôt **est** BEA DIGITAL. Le premier module métier intégré est **Immobilisations & Amortissements**, dans l’espace **Comptabilité**. Ce n’est pas un second logiciel : c’est la même application (FastAPI + Angular 20 + une PostgreSQL 17).

**ORION** reste le core banking (source de vérité). BEA DIGITAL digitalise ce qui gravit autour (Excel, contrôles, workflows, reporting, GED) — elle ne remplace pas ORION.

Le dépôt GitHub `bea-digital` n’est **plus** la cible vivante. Toute évolution produit se fait ici (`el-amana-immo`).

## Structure fonctionnelle

```text
BEA DIGITAL
├── Accueil
└── Comptabilité                          ← espace actif
    └── Immobilisations & Amortissements  ← premier module
├── Crédit        — bientôt
├── RH            — bientôt
├── Informatique  — bientôt
└── Achats        — bientôt
```

Parcours utilisateur : connexion → **Accueil** → **Comptabilité** → **Immobilisations & Amortissements** (`/dashboard`, `/immobilisations`, `/amortissements`, …).

Les URLs du module immo **ne sont pas préfixées** sous `/comptabilite/immobilisations/` : ~60 liens absolus et des notifications backend ouvrent `router.navigateByUrl(link)`. La hiérarchie est dans la navigation et le fil d’Ariane, pas dans le chemin d’URL. Détail : [docs/frontend-plateforme.md](docs/frontend-plateforme.md).

## Stack (inchangée)

| Couche | Technologie | Emplacement |
|--------|-------------|-------------|
| Frontend | Angular 20 | `frontend/angular20/` — **une seule** application |
| Backend | FastAPI, Python 3.13 | **`backend/`** (canonique ; le `Dockerfile` compose pointe ici) |
| Base | PostgreSQL 17 | **une seule** instance — [docs/base-de-donnees-unique.md](docs/base-de-donnees-unique.md) |

`app/` et `alembic/` à la racine = **dette**. Ne pas y coder, ne pas les déployer.

## Démarrage

Guide : [docs/demarrer.md](docs/demarrer.md). Instance Docker comptable : [docs/DEPLOIEMENT_LOCAL.md](docs/DEPLOIEMENT_LOCAL.md).

```powershell
copy .env.docker.example .env.docker   # puis renseigner SECRET_KEY et mot de passe
docker compose --env-file .env.docker up -d
```

Ouvrir **http://localhost**. Ne **jamais** lancer `docker compose down -v` (le `-v` efface PostgreSQL).

`SKIP_MIGRATIONS=1` est le défaut jusqu’au restore du dump Supabase. **Alembic sur une base vide = schéma faux** (la 1ʳᵉ révision est un `ALTER` de tables déjà présentes).

## Invariants

- Une seule PostgreSQL, une seule `DATABASE_URL`, un seul front Angular.
- Ne pas modifier `backend/app/services/amortissement_engine.py` ni la règle VNC : VNC = 0 → aucune dotation ; dotation plafonnée à la VNC restante ; VNC jamais négative.
- Ne pas casser les URLs métier `/api/v1/...` ni les routes front du module.
- Ne jamais committer `.env`, `.env.docker`, dumps, `storage/uploads`.

Voir [AGENTS.md](AGENTS.md).
