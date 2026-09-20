# Git — branches et versioning

## Branches

| Branche | Rôle |
|---------|------|
| `main` | Stable, source des releases production |
| `develop` | Intégration des développements (à créer sur GitLab si absent) |
| `feature/*` | Nouvelles fonctionnalités |
| `fix/*` | Corrections |
| `hotfix/*` | Correctifs urgents depuis `main` |

Exemples : `feature/module-credit`, `fix/amortissement-vnc`, `hotfix/security-authentication`.

**Règles :**

- Ne jamais développer directement sur `main`.
- Ne jamais modifier le code de production hors pipeline.
- Merge Request obligatoire avant merge vers `main` / `develop`.

## Semantic Versioning

Format : `MAJOR.MINOR.PATCH` — tags Git `v1.4.2`, `v2.0.0`.

| Niveau | Quand |
|--------|--------|
| MAJOR | Rupture de compatibilité |
| MINOR | Fonctionnalité compatible |
| PATCH | Bugfix / sécurité |

Chaque release production = **tag Git** + image registry au même tag + SHA court.

Exemple d’images :

```text
registry.example/bea-digital/backend:v1.5.0
registry.example/bea-digital/backend:abc1234
registry.example/bea-digital/frontend:v1.5.0
```

## Affichage dans CORE ADMIN

- Runtime : `GET /version` (et `/health`) exposent `version` + `git_sha` injectés au build (`APP_VERSION`, `GIT_SHA`).
- UI `/admin/versions` : notes ops par module (existantes) — **ne remplacent pas** les releases GitLab.
- Phase 2 éventuelle : historique des déploiements — voir [07-core-admin-vs-cicd.md](07-core-admin-vs-cicd.md).

## Hotfix

```text
main → hotfix/... → tests → tag vX.Y.Z → approval → backup → deploy
→ merger le hotfix dans develop
```
