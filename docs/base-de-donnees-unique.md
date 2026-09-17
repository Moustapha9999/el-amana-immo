# Une seule PostgreSQL — BEA DIGITAL

BEA DIGITAL et le module Immobilisations partagent **la même** base PostgreSQL 17.
Il n’y a pas de seconde base « plateforme », pas de schéma parallèle à créer
avec Alembic, et pas de dump à versionner.

## Pourquoi une seule base

Les tables déjà présentes (utilisateurs, rôles, sessions, audit, notifications,
pièces jointes, archives, agences, directions, départements, centres de coût)
sont le **socle commun** futur du Core BEA DIGITAL. Recréer une DB vide pour la
plateforme casserait cette continuité et dupliquerait l’identité.

ORION reste la source de vérité bancaire. Cette PostgreSQL est la base de
travail interne (saisies, contrôles, GED, reporting immo).

## Instance locale (compose racine)

| Élément | Valeur |
|---------|--------|
| Service | `postgres` dans `docker-compose.yml` |
| Image locale | `postgres:17-alpine` (ne **pas** poser `LANG=fr_FR.utf8`) |
| Écoute | `127.0.0.1:5432` uniquement (loopback) |
| Volume | `immo_postgres_data` — **une** instance, **jamais** `docker compose down -v` |
| Init | `database/init/01-extensions.sql` (`pgcrypto`) |
| Backend | une seule `DATABASE_URL` vers `postgres:5432` (hôte Docker) |

Le volume historique `immo_postgres_data` **est** le volume BEA DIGITAL. Ne pas
en créer un second (`bea_digital_postgres_data` en parallèle).

## Interdiction : Alembic sur une base vide

`backend/docker-entrypoint.py` exécute `alembic upgrade head` **sauf si**
`SKIP_MIGRATIONS=1`.

La première révision Alembic (`20260723_el_amana`) fait des `ALTER TABLE` /
`ALTER TYPE` sur des objets **déjà présents** (dump / historique Supabase).
Sur une base vide :

- les `ALTER` échouent ou produisent un schéma **faux** ;
- les tables métier ne sont pas créées comme en production.

**Règle :** `SKIP_MIGRATIONS=1` par défaut (`.env.example`, `.env.docker.example`,
compose) **jusqu’au restore** du dump Supabase.

Après un restore réussi, on pourra reposer `SKIP_MIGRATIONS=0` uniquement pour
appliquer de **nouvelles** révisions incrémentales sur une base déjà réelle —
jamais pour « créer » le schéma.

## Chemin prod / vraie donnée

```text
Dump PostgreSQL Supabase (hors git)
        → scripts/db-restore.ps1  (Windows)
        → scripts/db-restore.sh   (Linux / Git Bash)
        → contrôles (nb immos, VB, cumul amort., VNC)
        → recopier storage/uploads
```

Le script **refuse** de restaurer si `public` contient déjà des tables
(protection contre un écrasement silencieux).

Seed `backend/scripts/init_db.py` + `seed_data.py` = base **jetable** pour un
smoke test de login. Ce n’est **pas** le chemin Comptabilité / TEST / PROD.

## Alpine vs Debian (collation)

L’image `postgres:17-alpine` (musl) accepte le nom de locale `fr_FR.utf8` mais
la collation réelle reste celle de `C`. **Ne pas** forcer `LANG=fr_FR.utf8`
sur Alpine : ça donne une fausse impression d’alignement.

En **TEST/PROD banque** : image Debian `postgres:17`, collation et locale
alignées sur le dump Supabase (à valider avec la Comptabilité au moment du
restore réel — hors de ce dépôt, credentials banque).

## Dumps

Les fichiers `.dump` / `.backup` / dumps SQL **ne partent pas dans git**
(voir `.gitignore`, dossier `backups/`).
