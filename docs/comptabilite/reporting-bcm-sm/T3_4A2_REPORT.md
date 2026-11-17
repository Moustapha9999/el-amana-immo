# T3.4-A2 — BAL DET source unique

Branche : `feat/reporting-bcm-sm-t3` · Aucun commit / push / déploiement prod.

## Décision

Chaque campagne mensuelle utilise **exclusivement BAL DET** comme source comptable importée.

BAL COND : plus d’upload ni d’exigence dans le workflow. Tables, modèles et imports historiques **conservés** (lecture archives).

## Référence historique T1 (oct. 2026)

| Source | Σ classes 1–8 (doc.) |
|--------|----------------------|
| BAL COND | ≈ 2 873 223 |
| BAL DET | ≈ 2 873 238,05 |
| Écart | ≈ 15,05 |

Ces valeurs restent **documentaires**. Les calculs utilisent désormais les soldes **BAL DET**. Aucune constante COND dans le moteur. Pas de modification des valeurs historiques déjà validées.

## Services BAL COND identifiés

| Zone | Avant | Après |
|------|-------|-------|
| `import_service.upload_and_analyze` | DET + COND | COND → `410 IMPORT_COND_DEPRECATED` |
| `import_service.confirm_import` | reconcile DET/COND | contrôles internes DET |
| `import_service.reconcile_campaign` | DET vs COND | → `run_det_coherence_controls` |
| `reconcile_det_cond_legacy` | — | conservé, non appelé |
| `analyze_bal_cond` / agrégats COND | actifs | parsers historiques conservés |
| `engine/runner.py` | soldes COND requis | soldes DET uniquement |
| `campaign_service.campaign_progress` | étapes DET+COND | DET → contrôles → params |
| `parameter_service.propose_caisse_devises` | déjà DET | inchangé |
| API `GET …/cond-lines` | lecture | conservée (archives) |
| API upload COND | accepté | refusé |

## Contrôles remplacés

Ancien rapprochement DET/COND (écarts NCG, CREDIT_GAP, NCG_ONLY_COND…) **retiré du workflow**.

Nouveaux codes (issues `rbcm_reconcile_issue`) :

- `DET_MISSING_NCG`
- `DET_ANALYSIS_WARNINGS`
- `DET_NO_NCG` (BLOCKING)
- `DET_NO_DEVISE`
- `SUMMARY` (mode `DET_INTERNAL` + note T1)

## Modifications calculs

- Prérequis : BAL DET validée seule.
- Soldes NCG : `source=BAL_DET`.
- Empreinte imports : SHA DET seul.
- Snapshot ECART : formule `SUM_SIGNED_CLASSES_1_8_DET`, toujours **inactif** (D02).
- Contrôle moteur : `IMP_DET` (plus `IMP_DET_COND`).
- Mapping 242 règles : non activé.
- Bases D / C / SD / SC / SIGNED : inchangées.

## Frontend

- Imports : formulaire DET seul, carte de référence, historique DET.
- Accueil / fiche campagne / campagnes : plus d’étape ni bouton COND.
- Menu : entrée BAL COND retirée ; « Rapprochement » → « Contrôles ».
- Route `/bal-cond` conservée (archives + bandeau dépréciation).
- Page contrôles : KPI internes DET.

## Migrations

Aucune. Pas de suppression de tables ni de données.

## Tests

Exécution conteneur : **21 passed, 1 skipped**.

- `test_det_only_aggregation_and_controls_helpers`
- `test_upload_rejects_bal_cond`
- `test_engine_requires_det_only_not_cond`
- Tests agrégation / unicité / analyse DET existants
- `rbcm-nav.spec.ts` : menu sans bal-cond

## Capture UI

DEV `http://localhost/reporting-bcm-sm/imports` :

- Sous-titre « Source comptable unique : BAL DET »
- KPI : Imports DET 1 · Confirmé · NCG 228 · Comptes 55192
- Menu sans BAL COND ; entrée « Contrôles »
- Aucun upload COND

## État Git

Pas de commit (consigne). Branche `feat/reporting-bcm-sm-t3` dirty (module RBCM + docs).
