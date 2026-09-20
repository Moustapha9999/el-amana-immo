# CORE ADMIN vs GitLab CI/CD

## Séparation des responsabilités

| Domaine | Outil |
|---------|--------|
| Code, MR, tests, build, registry, release, deploy | **GitLab** |
| Supervision app, backups applicatifs, recovery scoped, maintenance métier, états modules, notes de version module | **CORE ADMIN** |

Un utilisateur CORE ADMIN **n’obtient pas** automatiquement SSH, shell PostgreSQL, GitLab ou secrets infra.

## Existant (ne pas casser)

| Route UI | Rôle |
|----------|------|
| `/admin/backups` | Sauvegardes plateforme |
| `/admin/recovery` | Restauration scoped (dépendances CORE) |
| `/admin/supervision` | État plateforme (données réelles) |
| `/admin/maintenance` | Maintenance globale / message |
| `/admin/module-states` | Statut modules |
| `/admin/versions` | Notes de version **ops** par module (pas le pipeline) |

Permissions : `core.admin.backup.*`, `recovery.*`, `monitoring.view`, `maintenance.*`, `module_status.*`, `versions.*`.

## Corrélation version runtime

Après deploy, vérifier :

```http
GET /version
GET /health
```

Réponse attendue (exemple) : `version`, `git_sha`, `service` — injectés via `APP_VERSION` / `GIT_SHA` au build.

Optionnel : reporter manuellement la version plateforme dans les notes `/admin/versions`.

## Phase 2 (hors livrable actuel)

- Table / API « historique des déploiements » (version, commit, auteur, backup, durée, statut).
- Affichage « Versions & Updates » branché sur métadonnées runtime + historique.
- Notifications déploiement (succès / échec) vers admins autorisés.

Ne pas implémenter ces migrations tant que l’inventaire IT et le premier pipeline prod ne sont pas validés.
