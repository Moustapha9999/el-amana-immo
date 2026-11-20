# Cahier des charges — `scripts/prod-to-dev-restore.ps1`

Statut : implémenté dans `scripts/prod-to-dev-restore.ps1` (`-WhatIf` pour simulation).

## Objectif

Restaurer un dump **complet** de la base PROD `bea_digital` dans une **base tampon DEV** nommée explicitement, en restaurant **toutes** les tables et dépendances relationnelles du dump, sans toucher à `bea_digital` ni `bea_digital_test`, sans viser un hôte de production, **sans** restaurer GED/uploads.

## Entrées

| Paramètre | Règle |
|-----------|--------|
| `-DumpPath` | Chemin vers `*.dump` (format custom, base entière) |
| `-Sha256Path` | Fichier empreinte (ou `-Sha256` chaîne) |
| `-TargetDatabase` | **Obligatoire.** Motif `^bea_digital_prod_[0-9]{8}$` (ex. `bea_digital_prod_20261119`) |
| Confirmation | Prompt `OUI-RESTAURER-DEV-TAMPON` |

Pas de paramètre « tables immo seulement ». Le restore est toujours **complet**.

## Garde-fous (refus immédiat)

1. Contexte local : `docker-compose.yml` + conteneur `bea-postgres` ; refus si env-file actif = `.env.production`.
2. Cible ∈ {`bea_digital`, `bea_digital_test`, `postgres`, `template0`, `template1`} → refus.
3. Cible hors motif `bea_digital_prod_YYYYMMDD` → refus.
4. Base cible **déjà existante** → refus (**aucun** drop/replace automatique).
5. Aucune commande vers hôtes banque (`192.168.1.55`, etc.).
6. Dump dont le TOC montre un sous-ensemble volontaire de tables (si détectable / flag opérateur) → refus ; exiger dump de base entière.

## Étapes obligatoires

1. Vérifier présence et taille du dump (≥ seuil, défaut 100 KiB).
2. Recalculer SHA-256 = empreinte fournie.
3. `pg_restore --list` → TOC dans `backups/rapports/` ; confirmer présence de `alembic_version` et d’un volume de tables cohérent avec une base complète.
4. Version Postgres DEV : majeure **17** ; si image Alpine alors que dump PROD Debian → **avertissement fort** ; avec `-RequireDebianPostgres` (recommandé) → **refus**.
5. Espace disque ≥ `max(3 × taille dump, seuil)`.
6. Sauvegarde locale préalable de `bea_digital` (logique `backup-local.ps1`) → `backups/local-pre-prod-import-*.dump`.
7. `CREATE DATABASE` tampon (`TEMPLATE template0`, UTF8, collation/ctype du serveur DEV) — **création uniquement**, jamais sur une base existante.
8. `pg_restore -d <tampon> --no-owner --no-acl` du dump **entier** (pas de `-t` / `-L` filtrant le métier). Échec si nombre de tables public &lt; seuil (ex. 5, idéalement calé sur le TOC).
9. `GRANT CONNECT, TEMPORARY ON DATABASE … TO bea_app` ; **pas** d’`alembic upgrade`.
10. Ne pas modifier `DATABASE_URL` du compose ; ne pas démarrer l’appli sur le tampon.
11. Rapport sous `backups/rapports/prod-to-dev-YYYYMMDD-HHMMSS.md`.

## Contrôles après restauration (obligatoires dans le rapport)

| Contrôle | Attendu |
|----------|---------|
| SHA-256 | Identique à l’empreinte DSI |
| `alembic_version` | Lisible ; notée pour comparaison code DEV |
| Nombre de tables `public` | Cohérent avec le TOC (base complète) |
| FK / restore | Pas d’échec bloquant `pg_restore` ; warnings listés |
| Counts métier | Au minimum : `users`, `immobilisations`, `exercices_comptables`, `soldes_compte_orion`, + totaux utiles (ex. `sum(valeur_brute)`, solde `142000`) |
| Bases préservées | `bea_digital` et `bea_digital_test` toujours présentes, non modifiées par ce script |
| GED/uploads | Non restaurés (hors scope) |
| Compose | Toujours branché sur `bea_digital` |

Prochaine étape documentée : `neutralize-dev-copy.ps1 -Database <tampon>`.

## Hors scope

- Remplacement de `bea_digital` / `bea_digital_test`
- Neutralisation / anonymisation
- GED et uploads
- Dump ou connexion PROD
- Commit Git

## Critères d’acceptation (quand implémenté)

- 2ᵉ run même cible → refus (base existante).
- `-TargetDatabase bea_digital` → refus, zéro DDL.
- SHA faux → refus avant `CREATE DATABASE`.
- Restore = dump entier (pas d’option tables immo).
