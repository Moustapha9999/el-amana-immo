# Rapport de nettoyage — 2026-11-05

Branche : `chore/audit-nettoyage-pre-deploiement` (depuis `484f5db`).
Aucun commit. Les modifications déjà présentes (fiabilité, loadtest) n’ont
pas été écrasées.

Priorité respectée : aucune donnée `bea_digital`, aucun volume, aucun secret,
aucune migration Alembic supprimée, aucun rapport de validation 1 à 4 supprimé.

## Chiffres

| | Nombre |
|---|---|
| Fichiers Git examinés (inventaire) | 1 399 suivis |
| Fichiers de travail hors dépendances installées | 2 389 |
| Fichiers source supprimés | **0** |
| Fichiers déplacés | 0 |
| Fichiers fusionnés | 0 |
| Caches supprimés | 30 `__pycache__/` hors `.venv`, 2 `.ruff_cache/`, 1 `.pytest_cache/` |
| Dépendances retirées | 0 |
| Tests backend conservés | 132 fichiers |
| Tests exécutés dans ce lot | 64 réussis, 0 échec |
| Modifications PostgreSQL proposées | revoir `immo_user` ; ne pas activer `archive_mode` ici |
| Modifications PostgreSQL appliquées | **0** (lecture seule) |

Les caches sont gitignorés. Les retirer n’allège pas l’historique Git.
`node_modules/`, `dist/`, `.angular/` et `.venv/` ont été laissés en place.

## Tests exécutés

```text
pytest tests/test_mg_stock_entrees.py tests/test_mg_stock_sorties.py
       tests/test_rate_limit_partage.py tests/test_format_montant.py
       tests/test_api_errors.py tests/test_config_database_url.py
64 passed, 1 warning (reportlab / ast.NameConstant)
```

Durée : 11,5 s. Ces fichiers couvrent entrées/sorties de stock (idempotence
unitaire), le limiteur partagé, les montants, le format d’erreur API et
l’URL de base. Ils ne rejouent pas la charge Locust ni le PITR.

Non exécutés dans ce lot (déjà prouvés plus tôt le même jour, rapports
conservés) : Locust 10→100, validation 2, validation 3, validation 4.
Non exécutés : la suite `backend/tests` entière, `ng build`. On ne les
déclare pas verts.

## Pourquoi rien d’autre n’a été supprimé

| Candidat | Décision |
|---|---|
| `app/`, `alembic/`, `Dockerfile` racine | Dette versionnée. Suppression = décision explicite |
| `@ngx-translate/*` | Aucun import dans `src/`, lockfile non régénéré |
| `backups/*.dump` | Sauvegardes locales de la base réelle |
| Rapports `loadtest/reports/validation*` | Preuves 2, 3 et 4 |
| Scripts `loadtest/validation_*.py` | Seul moyen de rejouer les validations |
| Migrations | Interdit par la mission |

## Documentation touchée

- Créés : `docs/audit/AUDIT_INITIAL.md`, `docs/audit/AUDIT_POSTGRESQL.md`,
  `docs/DEPLOYMENT_GUIDE.md`, ce rapport.
- Corrigé : `docs/architecture/architecture-technique.md` — 4 processus
  Uvicorn, 103 révisions, tête `20261105_mg_stock_mvt_ref_uq`.

## PostgreSQL

Lecture seule sur `bea_digital` : tête Alembic
`20261105_mg_stock_mvt_ref_uq`, 211 tables, 537 FK, 0 index invalide,
0 doublon de référence / numéro / clé d’idempotence, 0 exercice pointant
vers un dossier d’archive absent. `archive_mode=off`. Détail :
[AUDIT_POSTGRESQL.md](AUDIT_POSTGRESQL.md).

## Préparation Ubuntu

Le guide d’installation est [../DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md).

Le dépôt n’est pas « prêt à déployer » tant que :

1. Le travail non commité de fiabilité n’est pas revu et commité.
2. Les secrets de production ne sont pas sortis du poste de développement.
3. L’image PostgreSQL Debian et les trois emplacements (données, WAL,
   sauvegardes hors serveur) ne sont pas décidés avec la DSI.
4. Le rôle `immo_user` (superuser sur le cluster local) n’est pas arbitré.

La structure actuelle (`backend/`, `frontend/angular20/`, `deployment/`,
`docs/`) est celle qu’il faut emmener. Elle n’a pas été réorganisée.
