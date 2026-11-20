# PROD → DEV — workflow complet (base `bea_digital`)

Statut : **SCRIPTS IMPLÉMENTÉS — exécution PROD→DEV uniquement sur ordre DSI écrit**  
Scripts : `scripts/prod-to-dev-restore.ps1`, `scripts/neutralize-dev-copy.ps1` (avec `-WhatIf`).

## Décision figée

| Point | Décision |
|-------|----------|
| Périmètre | **Toute** la base PostgreSQL PROD `bea_digital` (schéma + données + relations) |
| Non-périmètre | Extraction limitée Immobilisations **interdite** ; GED et `storage/uploads` **exclus** |
| Transfert | Canal sécurisé validé par la DSI |
| Cible DEV | Nouvelle base tampon `bea_digital_prod_YYYYMMDD` |
| Préservé | `bea_digital` (DEV actuel) et `bea_digital_test` — jamais écrasés automatiquement |
| Métier | Données comptables et historiques **conservés intégralement** |
| Accès | Comptes, mots de passe, MFA, sessions, intégrations externes **neutralisés** avant usage |
| Postgres DEV | Image **Debian** `postgres:17` **recommandée avant** le premier import |

Usage métier visé après synchro : Immobilisations & amortissements (et tout autre module) sur une copie complète cohérente.

## Documents

| Document | Rôle |
|----------|------|
| [01-runbook-recuperation-prod.md](01-runbook-recuperation-prod.md) | Dump PROD complet, contrôles, transfert |
| [02-cdc-prod-to-dev-restore.md](02-cdc-prod-to-dev-restore.md) | Cahier des charges restore → tampon |
| [03-cdc-neutralize-dev-copy.md](03-cdc-neutralize-dev-copy.md) | Cahier des charges neutralisation |
| [04-postgres-alpine-vers-debian.md](04-postgres-alpine-vers-debian.md) | Alignement Postgres DEV (fait : Debian) |
| [05-fiche-operatoire-dsi.md](05-fiche-operatoire-dsi.md) | Fiche opératoire dump PROD → DEV (autorisation DSI) |

## Séquence cible

1. ~~Migrer Postgres DEV Alpine → Debian~~ **fait**.  
2. Dump complet PROD `bea_digital` + SHA-256 + TOC (sur ordre DSI).  
3. Transfert DSI → poste DEV.  
4. `prod-to-dev-restore` → `bea_digital_prod_YYYYMMDD` (sans toucher `bea_digital` / `bea_digital_test`).  
5. `neutralize-dev-copy` sur le tampon.  
6. Contrôles ; bascule manuelle éventuelle de l’appli DEV vers le tampon.

## Interdit sans ordre DSI

Connexion PROD, dump, transfert, restore, migration volume, implémentation des scripts, commit/push/déploiement, `docker compose down -v`.

## Références (ne pas confondre)

- `deployment/scripts/backup-pre-deploy.sh` — modèle dump serveur  
- `scripts/restore-local.ps1` — **écrase** `bea_digital` : **ne pas** l’utiliser pour ce workflow  
- `scripts/test-db.ps1` — pattern neutralisation accès (base de test uniquement)

## Décisions DSI encore nécessaires

Voir la liste unique en fin de [01-runbook-recuperation-prod.md](01-runbook-recuperation-prod.md) § Décisions DSI restantes.
