# Procédures opérationnelles

## Déploiement initial (serveur banque)

1. Remplir [00-inventaire-bea.md](00-inventaire-bea.md) avec l’IT.
2. Installer Docker / Compose ; créer compte `bea-deploy` + clé SSH.
3. Préparer volumes, `.env.production` (depuis `deployment/env.production.example`).
4. Configurer reverse proxy HTTPS (template nginx).
5. Créer projet GitLab, Registry, Runner tagué `bea-prod`, variables CI.
6. Premier restore dump si migration depuis kit / Supabase (`scripts/db-restore.*`, `SKIP_MIGRATIONS=1`).
7. Tag `vX.Y.Z` → pipeline → approval → backup → deploy → healthcheck.
8. Smoke : Login 1, Accueil, CORE ADMIN, module Immobilisations (Login 2), VNC.

## Mise à jour (release)

1. MR → `main` → tag SemVer.
2. Pipeline validate / test / security / build / publish.
3. Approval manuelle `deploy_production`.
4. Script backup **vérifié** (fichier présent, taille minimale).
5. Maintenance CORE ADMIN si migration risquée.
6. `deploy.sh` : pull images taguées, recreate FE/BE **sans** `-v`.
7. Migrations selon [runbook-migrations.md](../runbook-migrations.md).
8. Healthcheck `/health` + `/version`.
9. Lever maintenance ; noter version dans les ops CORE ADMIN si utile.

## Hotfix

Branche `hotfix/*` depuis `main` → tests → tag patch → même chaîne approval / backup / deploy → merger dans `develop`.

## Incident / rollback

1. Maintenance si besoin.
2. `rollback.sh` vers tag précédent connu.
3. Healthcheck.
4. Si corruption données : restore backup (procédure DSI) — analyser dépendances CORE / modules avant restore partiel (voir [core-admin-ops.md](../core-admin-ops.md)).

## Maintenance applicative

CORE ADMIN `/admin/maintenance` et flags module — pour message utilisateurs / gel métier.

Ne remplace pas : firewall, SSH, GitLab, secrets OS.

## Kit comptable (parallèle)

Le kit USB ([DEPLOIEMENT_LOCAL.md](../DEPLOIEMENT_LOCAL.md), `scripts/update-on-comptable.ps1`) reste le chemin **hors GitLab** pour le PC comptable. Ne pas le remplacer par ce pipeline tant que la DSI n’a pas basculé.
