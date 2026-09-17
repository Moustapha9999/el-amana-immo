# Pack opérateur Supabase — BEA DIGITAL

Une seule PostgreSQL : **la base actuelle** (projet `kriknulbclbghbmrzsbq`, base physique `postgres`).
Ce pack **n’en crée pas une seconde**, ne renomme rien, n’active pas RLS.

Le module Immobilisations (tables, VNC, URLs `/api/v1/...`, `/dashboard`, `/immobilisations`, …) reste le même.

## Ne pas faire

- Renommer le volume Docker `bea_postgres_data` à la volée, ou les tables métier
- `docker compose down -v`
- Activer RLS sur `public`
- Recréer `departments` / `modules` / `user_departments` (le catalogue = `plateforme_espaces` / `plateforme_modules`)
- Pointer Alembic sur une base **vide**

CORE : [docs/core-bea-digital.md](../../docs/core-bea-digital.md). GED = table `ged_documents` (réservée).

## Chemin recommandé (Alembic)

Depuis la **racine du dépôt** (`el-amana-immo\`, pas `backend\`). Le venv n’est pas requis pour `backup`.

```powershell
cd C:\Users\sallm\el-amana-immo
.\scripts\bea-supabase.ps1 backup
.\scripts\bea-supabase.ps1 migrate
.\scripts\bea-supabase.ps1 verify
```

Si le prompt est déjà dans `backend\` :

```powershell
.\scripts\bea-supabase.ps1 backup
```

Dump Docker local (même schéma, volume `bea_postgres_data`) :

```powershell
.\scripts\bea-supabase.ps1 -Target docker backup
.\scripts\bea-supabase.ps1 -Target docker migrate
.\scripts\bea-supabase.ps1 -Target docker verify
```

## Chemin SQL Editor (sans Python)

Dans Supabase → SQL Editor, dans cet ordre :

1. `01_upgrade.sql` — colonnes / tables plateforme (IF NOT EXISTS)
2. `02_catalogue.sql` — espaces, modules, permissions, grants immo
3. `03_comments.sql` — COMMENT ON (zéro donnée)
4. `06_stamp.sql` — **seulement** si vous n’avez pas utilisé Alembic
5. `04_verify.sql` — contrôles (lecture)

`05_droits_immo.sql` : ré-accorde Comptabilité + Immobilisations à tous les users actifs.

## Auth

L’application authentifie `public.users` (JWT FastAPI). `auth.users` Supabase n’est pas le login BEA DIGITAL.
Le bucket Storage `pieces-jointes` est inchangé.
