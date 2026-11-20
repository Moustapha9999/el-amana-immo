# Cahier des charges — `scripts/neutralize-dev-copy.ps1`

Statut : implémentation dans `scripts/neutralize-dev-copy.ps1`.  
Cible exclusive : base tampon `bea_digital_prod_YYYYMMDD` (copie **complète** PROD déjà restaurée).

## Objectif

Rendre la copie bancaire utilisable en DEV **sans effets réels** vers la banque, en neutralisant accès et intégrations, tout en **conservant intégralement** les données comptables, historiques et relations de **toute** la base.

## Entrées

| Paramètre | Règle |
|-----------|--------|
| `-Database` | Obligatoire ; motif `^bea_digital_prod_[0-9]{8}$` |
| `-DevAdminEmail` | Compte admin DEV (**obligatoire**, identité validée DSI) |
| `-DevAdminPassword` | Via env `BEA_DEV_ADMIN_PASSWORD` (jamais logué) |
| `-AnonymizePii` | `None` \| `Minimal` \| `Strict` — **obligatoire explicite** (pas de défaut silencieux métier) |
| `-WhatIf` / simulation | Aucune écriture |
| Confirmation | Prompt `OUI-NEUTRALISER-COPIE-DEV` (sauf `-WhatIf`) |

## Garde-fous

- Refus si base ∈ {`bea_digital`, `bea_digital_test`} ou hors motif.
- Refus hors contexte Docker DEV local.
- Exiger worker arrêté ou `-ConfirmWorkerStopped`.
- Snapshot des totaux comptables **avant** toute écriture ; échec si dérive après.
- Rapport dans `backups/rapports/` sans secrets.

## A. Comptes, MFA, sessions (toujours)

1. Tous les `hashed_password` → bcrypt d’un secret aléatoire.
2. `totp_secret = null`, `totp_enabled = false`.
3. Purge `auth_sessions`, `password_history` (+ `auth_login_attempts` si présent).
4. Compte admin DEV contrôlé (`-DevAdminEmail` / env password).
5. Option : désactiver les autres comptes.

## B. Intégrations et secrets en base (toujours)

- Invalider / nullifier secrets, tokens, credentials des tables d’intégration.
- Destinations / URLs externes → non routables ou vides.
- Ne pas écrire dans `.env.docker`.

## C. Données conservées intégralement (toujours)

Immobilisations, amortissements, soldes Orion, exercices, historiques, FK, `alembic_version`, montants.  
**Interdit :** toucher au moteur d’amortissement / VNC ; purge métier.

## D. Anonymisation PII

Uniquement selon `-AnonymizePii` explicite (décision DSI). Comptabilité toujours intacte.

## E. Effets externes

SMTP vide (rappel), worker arrêté ou confirmé, `SECRET_KEY` local, compose reste sur `bea_digital` jusqu’à bascule manuelle. GED/uploads hors scope.
