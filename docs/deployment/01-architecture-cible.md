# Architecture cible — GitLab + Runner BEA + production

## Objectif

Permettre le cycle :

```text
PC DEV → Git → GitLab → CI/CD → Registry → Approval
  → Runner (réseau BEA) → Backup → Deploy → Migration → Healthcheck → PROD
```

Le serveur de production BEA **n’est jamais** un environnement de développement.

## Schéma retenu

```text
                 Machine DEV
                      │
                git push HTTPS/SSH
                      │
                      ▼
                ┌───────────┐
                │  GITLAB   │
                │ Git CI/CD │
                │ Registry  │
                └─────┬─────┘
                      │
               Pipeline + approval
                      │
                      ▼
           ┌──────────────────────┐
           │ GitLab Runner BEA    │
           │ (réseau interne)     │
           └──────────┬───────────┘
                      │ SSH (bea-deploy)
                      ▼
           ┌──────────────────────┐
           │ Serveur BEA PROD     │
           │ Reverse proxy HTTPS  │
           │ Docker : FE / BE / PG│
           │ Volumes + backups    │
           └──────────────────────┘
```

Si GitLab n’est pas joignable depuis le réseau BEA sans tunnel : **VPN administré par l’IT**, flux minimaux uniquement (principe du moindre privilège). Les règles exactes sont hors dépôt — voir [00-inventaire-bea.md](00-inventaire-bea.md).

## Principes

1. Runner dans le réseau BEA ; pas d’accès SSH permanent depuis Internet vers la prod.
2. Images taguées SemVer + SHA — jamais `latest` comme référence de production.
3. Secrets hors Git (variables GitLab + `.env.production` sur le serveur).
4. Volume PostgreSQL et `storage/` persistants — **jamais** `docker compose down -v`.
5. CORE ADMIN = supervision applicative ; GitLab = code, build, release, deploy.
6. Compte `bea-deploy` ≠ administrateur système global ; pas d’escalade depuis CORE ADMIN vers SSH/DB/GitLab.

## Chemins parallèles (ne pas confondre)

| Chemin | Usage |
|--------|--------|
| `docker-compose.yml` + kit USB | Local / machine comptable |
| `deployment/docker-compose.prod.yml` | Serveur banque (après inventaire IT) |
| `.github/workflows/ci.yml` | CI GitHub tant que le remote GitHub est actif |
| `.gitlab-ci.yml` | CI/CD GitLab cible |

## Artefacts versionnés

- Compose prod : [`deployment/docker-compose.prod.yml`](../../deployment/docker-compose.prod.yml)
- Scripts : [`deployment/scripts/`](../../deployment/scripts/)
- Pipeline : [`.gitlab-ci.yml`](../../.gitlab-ci.yml)
