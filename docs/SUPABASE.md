# Connexion Supabase (PostgreSQL)

Ce projet utilise **FastAPI + SQLAlchemy** en connexion **directe** à Postgres Supabase (pas le client JS pour la couche métier actuelle).

## Variables (fichier `.env` à la racine — déjà gitignoré)

| Variable | Usage |
|----------|--------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:MOT_DE_PASSE@db.<ref>.supabase.co:5432/postgres` |
| `DATABASE_SSL` | `true` (obligatoire en direct Supabase) |
| `SUPABASE_URL` | URL projet (`https://<ref>.supabase.co`) |
| `SUPABASE_PUBLISHABLE_KEY` / `SUPABASE_ANON_KEY` | Frontend / Data API (plus tard) |
| `SUPABASE_SERVICE_ROLE_KEY` | **Backend uniquement**, jamais dans Angular |
| `SUPABASE_JWT_SECRET` | Vérification JWT Supabase Auth (si intégration future) |

**Mot de passe avec `@`** : encoder en `%40` dans `DATABASE_URL`  
Ex. `Utopia2023@Utopia2023` → `Utopia2023%40Utopia2023`

## Vérifier la connexion

```powershell
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\python scripts\test_db_connection.py
```

Si OK : `OK — database=postgres`

## Créer les tables + données initiales

```powershell
.\.venv\Scripts\python scripts\seed_data.py
```

Puis lancer l’API :

```powershell
uvicorn app.main:app --reload --port 8000
```

Swagger : http://localhost:8000/docs

## Dépannage

1. **getaddrinfo / DNS** : vérifier Internet, pare-feu, VPN.
2. **password authentication failed** : recopier le mot de passe depuis Supabase → Settings → Database ; ré-encoder les caractères spéciaux dans l’URL.
3. **`getaddrinfo failed` / Windows** : l’hôte `db.*.supabase.co` est **IPv6-only**. Utilisez le **Session pooler** (IPv4) :
   ```powershell
   cd backend
   $env:PYTHONPATH="."
   python scripts/find_pooler_region.py
   ```
   Copiez la `DATABASE_URL` affichée dans `.env`, puis relancez `test_db_connection.py`.

## Sécurité

- Ne **jamais** commiter `.env`.
- **`service_role`** et **`sb_secret_*`** = accès complet : backend seulement.
- Si les clés ont été exposées (chat, capture d’écran), **les régénérer** dans le dashboard Supabase.

## Prochaines étapes recommandées

1. Exécuter `test_db_connection.py` puis `seed_data.py` en local.
2. Confirmer `/health` et `/api/v1/auth/login` avec `admin@el-amana.mr` / `Admin@2026`.
3. (Optionnel) Lier le frontend Supabase Auth plus tard ; aujourd’hui l’auth reste JWT FastAPI.
4. Activer **RLS** sur les tables si vous exposez aussi l’API REST Supabase (Data API).
