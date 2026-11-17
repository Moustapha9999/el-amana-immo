# T3.4-A — Diagnostic import + UI Imports (DEV)

Branche : `feat/reporting-bcm-sm-t3` · Aucun commit / push / déploiement prod.

## 1. Diagnostic — refus de confirmation (« Cette donnée existe déjà »)

### Cause exacte

La confirmation du **BAL COND** insérait **une ligne `rbcm_balance_ncg` par ligne Excel**, en forçant `ncg = ncg or "?"`.

Le fichier `BAL COND 31-10-2026.xlsx` contient **9 lignes sans NCG**. Toutes étaient mappées sur `"?"`, ce qui violait la contrainte UNIQUE :

`uq_rbcm_balance_ncg (import_id, ncg)`

SQLAlchemy levait `IntegrityError` → converti par le catalogue d’erreurs en message générique **« Cette donnée existe déjà »** (code DUPLICATE). La référence support `REQ-2026-11-16-0FB1A5` n’est qu’un identifiant de toast, pas la cause.

Ce n’était **pas** un conflit DET vs COND sur `uq_rbcm_import_sha (campaign_id, file_type, sha256)` : les deux types coexistaient déjà (DET = VALIDATED, COND = ANALYZED).

### Preuves DEV (campagne `11/2026 · v1`)

| Import | Type | Statut avant | Lignes | SHA |
|--------|------|--------------|--------|-----|
| `d566fb2b-…` | BAL_DET | VALIDATED | 55192 | `59aa0a01ebb1…` |
| `97d66f67-…` | BAL_COND | ANALYZED | 237 | `050430d4581f…` |

Analyse COND : 237 lignes, **228 NCG uniques**, **9 NCG manquants**.

### Fichier / fonction / contrainte

| Élément | Valeur |
|---------|--------|
| Fichier | `backend/app/services/reporting_bcm_sm/import_service.py` |
| Fonction | `confirm_import` (branche `BAL_COND`) |
| Contrainte | `uq_rbcm_balance_ncg` sur `rbcm_balance_ncg (import_id, ncg)` |
| Données | Lignes COND sans NCG → placeholder `"?"` répété |

### Correction appliquée (sans suppression de données)

1. **`aggregate_cond_balances` / `aggregate_det_balances`** : agrégation par NCG ; exclusion des NCG vides (plus jamais de `"?"`).
2. **`analyze_bal_cond`** : compte `missing_ncg_count`, `duplicate_ncg_count`, `ready_to_confirm`.
3. **`confirm_import`** : utilise l’agrégation ; `SELECT … FOR UPDATE` anti double confirmation ; `IntegrityError` → `IMPORT_BALANCE_CONFLICT` explicite.
4. Aucune migration : la contrainte UNIQUE reste correcte ; le bug était applicatif.

### Vérification live DEV

Après rebuild backend :

```
before ANALYZED 237
analyze missing_ncg= 9 ncg= 228 ready= True
after VALIDATED balances= 228 skipped= 9
```

DET et COND sont tous deux **VALIDATED** sur la même campagne.

## 2. Règle métier / idempotence

| Cas | Comportement |
|-----|----------------|
| DET confirmé puis COND | Autorisé (clés indépendantes `file_type`) |
| COND puis DET | Autorisé |
| Même fichier (même SHA + type) | Idempotence `uq_rbcm_import_sha` → réutilise l’import |
| Nouveau contenu même type | Remplacement contrôlé (`replace_validated` → SUPERSEDED) |
| Confirmations concurrentes | `FOR UPDATE` + contrainte UNIQUE soldes |

### Statuts import (machine à états existante)

| Statut | Sens UI | Suite |
|--------|---------|-------|
| ANALYZED | Analysé | Confirmer |
| VALIDATED | Confirmé | Importer / confirmer le complémentaire ou rapprochement |
| SUPERSEDED | Remplacé | Consultation historique |
| REJECTED | Rejeté | Corriger et réimporter |

## 3. Campagne / période

- **Campagne (mois de reporting)** : sélection utilisateur (`11/2026 · v1`) — non modifiée automatiquement.
- **Période de référence campagne** : `period_month` / `period_year`.
- **Date de situation (fichier)** : détectée dans le nom (`31-10-2026` → 10/2026) ; affichée distinctement sur l’écran Imports.

Un fichier d’octobre dans une campagne novembre n’est pas bloqué automatiquement (convention métier à confirmer côté métier) ; l’UI rend les trois notions visibles.

## 4–7. UI

Écran Imports refondu :

- En-tête + barre de périodes + KPI API.
- Formulaire compact (type / fichier / analyser) avec `bea-mg__field`.
- Cartes sources BAL DET / BAL COND.
- Historique paginé + drawer (SHA complet, téléchargement, remplacer, prochaine étape).
- Styles partagés RBCM : overflow, grilles, filtres stylisés sur Accueil/Campagnes/BAL/Mapping.

Endpoint ajouté : `GET /campaigns/{id}/imports/{import_id}/download`.

## 8. Tests

Fichier : `backend/tests/test_reporting_bcm_sm.py`

- `test_analyze_bal_cond_missing_and_duplicate_ncg`
- `test_aggregate_det_skips_empty_ncg`
- `test_import_sha_unique_includes_file_type`
- `test_balance_ncg_unique_is_per_import`
- `test_confirm_workflow_det_then_cond_aggregation_independent`
- `test_confirm_workflow_cond_then_det_same_result`

Exécution conteneur (fichier copié en `/tmp`, `PYTHONPATH=/app`) : **17 passed**, 1 skipped (Correspondance absente), 3 failed path-resolution préexistants (`__file__` sous `/tmp` → chemins `services/…` incorrects ; OK depuis `backend/tests`).

Critère d’acceptation live : DET VALIDATED + COND VALIDATED, même campagne — **OK**.

## 9. Fichiers modifiés

### Backend

- `backend/app/services/reporting_bcm_sm/import_service.py`
- `backend/app/api/v1/endpoints/reporting_bcm_sm.py` (download)
- `backend/tests/test_reporting_bcm_sm.py`

### Frontend

- `frontend/.../pages/rbcm-imports.component.ts` (refonte)
- `frontend/.../rbcm-ui.component.ts`
- `frontend/.../rbcm.models.ts` (`IMPORT_STATUS_LABELS`)
- `frontend/.../rbcm-campaign-picker.component.ts`
- `frontend/.../pages/rbcm-bal-det.component.ts`
- `frontend/.../pages/rbcm-bal-cond.component.ts`
- `frontend/.../pages/rbcm-campagnes.component.ts`
- `frontend/.../pages/rbcm-mapping.component.ts`

### Docs

- `docs/comptabilite/reporting-bcm-sm/T3_4A_REPORT.md`

### Migrations

Aucune. Pas de changement de contrainte SQL.

## 10. Captures / responsive

Rebuild DEV effectué (`backend` + `frontend`). Vérification navigateur DEV :

- Imports : KPI DET/COND **Confirmé**, campagne `11/2026 · v1` passée **Rapprochée**.
- Cartes sources : fichiers, lignes, SHA, message « Les deux sources sont confirmées ».
- Formulaire compact + historique filtré (`bea-mg__field`).
- Correctif encapsulation : `ViewEncapsulation.None` sur `bea-rbcm-styles` (sinon styles RBCM ignorés).
- Captures locales : `page-2026-11-16T16-54-52-219Z.png`, `page-2026-11-16T16-55-24-916Z.png`.
- Responsive à revalider aux largeurs 1920 / 1571 / 1366 / 1024 / 768.

## 11. Problèmes restants

- Les 9 lignes COND sans NCG sont **ignorées** à la confirmation (documentées dans `control_report.skipped_no_ncg`) — à traiter métier si ces lignes doivent être corrigées à la source.
- Tests path-based du fichier (ecart/parameter/delete) échouent si le fichier n’est pas sous `backend/tests/` (artefact d’exécution `/tmp`).
- Pas de tests UI automatisés Cypress/Playwright dans ce lot.
- Mapping toujours non activé ; ECART hors périmètre.

## 12. État Git

Pas de commit (consigne). Voir `git status` local pour la liste des fichiers dirty sur `feat/reporting-bcm-sm-t3`.
