# Invariants BEA DIGITAL

Ce dépôt **est** la plateforme BEA DIGITAL (Banque El Amana, Mauritanie).
Premier module : Immobilisations & Amortissements, espace Comptabilité.

ORION = core banking (source de vérité). BEA DIGITAL = plateforme interne
complémentaire (Excel, contrôles, workflows, reporting, GED) — pas un
remplacement d’ORION.

## Stratégie figée (ne pas renégocier)

1. **Un seul dépôt vivant** = celui-ci. Pas de second repo produit en parallèle.
   Le dépôt GitHub `bea-digital` n’est plus la cible vivante.
2. **Une seule application Angular** (`frontend/angular20/`). Pas de rewrite,
   pas de second front React/Next. Zéro dépendance ajoutée au `package.json`
   pour le chrome plateforme (pas de Material / Tailwind / police d’icônes
   supplémentaires dans `src/app/plateforme/`).
3. **Une seule PostgreSQL 17** = la base de BEA DIGITAL **et** la base immo.
   Pas de 2ᵉ DB « plateforme ». Pas Alembic sur base vide.
4. **Source backend canonique** = `backend/` (le Dockerfile compose pointe
   déjà dessus). `app/` + `alembic/` à la racine = **dette** : ne pas déployer,
   ne pas y coder.
5. **Ne JAMAIS modifier** `backend/app/services/amortissement_engine.py` ni la
   règle VNC :
   - VNC = 0 → aucune dotation ;
   - dotation plafonnée à la VNC restante ;
   - VNC jamais négative.
6. **Ne pas casser** les URLs métier `/api/v1/...` ni les routes front du
   module (`/dashboard`, `/immobilisations`, `/amortissements`, …).
   Ne pas préfixer sous `/comptabilite/immobilisations/` : ~60 liens absolus
   + liens de notification produits par le backend et ouverts via
   `router.navigateByUrl(link)`.

## Base de données

- Une seule `DATABASE_URL` vers le service `postgres` du compose racine.
- Loopback Postgres : `127.0.0.1:…`.
- Volume nommé unique (`immo_postgres_data`). **Jamais** `docker compose down -v`.
- `SKIP_MIGRATIONS=1` par défaut jusqu’au restore du dump Supabase.
  Alembic sur base vide = schéma faux (1ʳᵉ révision = `ALTER` de tables déjà
  présentes).
- Dump Supabase → `pg_restore` (scripts `scripts/db-restore.ps1` /
  `scripts/db-restore.sh`). Seed `backend/scripts/init_db.py` + `seed_data.py`
  = base **jetable de test**, pas le chemin prod.
- Ne pas forcer `LANG=fr_FR.utf8` sur `postgres:17-alpine` (musl : collation
  réelle = `C`). TEST/PROD banque : image Debian `postgres:17`, collation
  alignée sur le dump.

## Front plateforme

- Chrome greffé dans `frontend/angular20/src/app/plateforme/`.
- Après login et `guestGuard` (déjà connecté) → `/accueil` (pas `/dashboard`).
- `PLATEFORME_ROUTES` **avant** la route `''` de `ShellComponent`.
- Fil d’Ariane **dans** le shell, sous la topbar (ne pas empiler un bandeau
  au-dessus de `height: 100vh`).
- Wildcard `**` → `accueil`.

## Secrets

Ne jamais committer `.env`, `.env.docker`, dumps, `storage/uploads`, backups.
