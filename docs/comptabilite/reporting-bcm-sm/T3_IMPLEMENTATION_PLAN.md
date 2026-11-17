# T3 — Plan d’implémentation (socle)

**Prérequis :** T2 VALIDÉ + validation explicite utilisateur pour démarrer le code.  
**Cette mission ne code pas T3.**

## 1. Périmètre exact

### Inclus

1. Enregistrement module `reporting-bcm-sm` dans le catalogue (`espace_code=comptabilite`)
2. Carte / accès depuis hub `/comptabilite`
3. Contrat de routes Angular préfixées `/reporting-bcm-sm/...`
4. Navigation shell module
5. Permissions granulaires initiales + Login 2
6. Page d’accueil module
7. Liste / création / consultation campagnes (statuts initiaux)
8. API consultation + création campagnes
9. Audit des actions sensibles (création campagne, changements statut initiaux)
10. Tests associés
11. Migration Alembic **additive** tables campagne minimales (si validée dans le lot T3)

### Exclus (phases suivantes)

- Imports DET/COND, rapprochement, mapping, paramètres, moteur, Excel, workflow 3 niveaux complet, PDF

## 2. Architecture

| Couche | Cible |
|--------|--------|
| Module | `reporting-bcm-sm` |
| Hub | `/comptabilite` |
| UI | `/reporting-bcm-sm/accueil`, `/campagnes`, `/campagnes/:id` |
| API | `/api/v1/reporting-bcm-sm/campaigns` |
| Tables T3 mini | `rbcm_campaign` (+ éventuellement `rbcm_validation_event` si transitions) |
| Auth | `require_module_access("reporting-bcm-sm")` + `require_permission(...)` |

Ne pas coder dans `app/` ou `alembic/` racine.

## 3. Fichiers concernés (prévision)

### Backend

- `backend/app/data/plateforme_catalogue.py` — module + permissions
- `backend/app/models/reporting_bcm_sm.py` — modèle campagne
- `backend/app/schemas/reporting_bcm_sm.py`
- `backend/app/services/reporting_bcm_sm/campaign_service.py`
- `backend/app/api/v1/endpoints/reporting_bcm_sm.py`
- `backend/app/api/v1/router.py` — include_router
- `backend/alembic/versions/YYYYMMDD_rbcm_01_campaigns.py` — après contrôle heads
- `backend/tests/test_reporting_bcm_sm_campaigns.py` (nom à aligner)

### Frontend

- `frontend/angular20/src/app/plateforme/module-routing.contract.ts`
- `frontend/angular20/src/app/app.routes.ts`
- `frontend/angular20/src/app/layout/shell/shell-nav.ts`
- `frontend/angular20/src/app/plateforme/espace-hub.guard.ts` — segment réservé
- `frontend/angular20/src/app/reporting-bcm-sm/` — pages accueil, liste, détail, création
- Consommation catalogue via API plateforme existante (`/plateforme/modules/...`)

### Docs

- Mettre à jour ce dossier + éventuellement `docs/catalogue-modules-futurs.md` / index compta

## 4. Modèle campagne (T3 minimal)

Champs proposés (alignés T2 révisé) :

- `id` UUID PK  
- `period_year`, `period_month`  
- `closing_date` nullable  
- `bank_code` défaut `BEA`  
- `status` : au minimum `BROUILLON` (autres transitions limitées en T3)  
- `campaign_version` INT défaut 1  
- `reopened_from_id` UUID nullable FK self  
- `preparer_id` UUID FK users nullable  
- `created_at` / `updated_at`  

**Unicité proposée (sous réserve P2) :**  
`UNIQUE (bank_code, period_year, period_month, campaign_version)`  
avec règle métier : une seule version « ouverte » (non `CLOTUREE`) par période — à coder en service.

Montants : aucun en T3.  
FK users : `ON DELETE RESTRICT` ou SET NULL selon convention users du dépôt (vérifier avant migration).

## 5. API T3

| Méthode | Chemin | Permission | Comportement |
|---------|--------|------------|--------------|
| GET | `/reporting-bcm-sm/campaigns` | `.view` | Liste filtrée année/mois/statut |
| POST | `/reporting-bcm-sm/campaigns` | `.prepare` | Crée `BROUILLON` ; refuse doublon période ouverte |
| GET | `/reporting-bcm-sm/campaigns/{id}` | `.view` | Détail |
| PATCH | `/reporting-bcm-sm/campaigns/{id}` | `.prepare` | Champs non sensibles seulement (ex. closing_date) |

Erreurs : `api_errors`. Audit : `record_audit` sur POST et transitions.

## 6. Permissions initiales (catalogue)

Proposer au seed catalogue (noms exacts à figer en PR) :

- `reporting-bcm-sm.view`
- `reporting-bcm-sm.prepare`
- (réserver sans UI T3) `import`, `parameters.write`, `mapping.propose`, `mapping.validate`, `confirm`, `correct`, `control`, `approve`, `export`, `reopen`

Rattacher au moins `view` + `prepare` à un rôle Comptabilité de recette (décision produit).

## 7. Routes Angular T3

- `path: 'reporting-bcm-sm'`, `canActivate: [moduleGuard('reporting-bcm-sm')]`, children :
  - `''` → redirect `accueil`
  - `accueil`
  - `campagnes`
  - `campagnes/nouvelle`
  - `campagnes/:id`
- `entryPath`: `/reporting-bcm-sm/accueil`
- `espacePath`: `/comptabilite`
- FeedbackService / UiDialogService / unsavedChangesGuard / montant si formulaires

## 8. Tests T3

- API : auth module absente → 401/403 ; create OK ; doublon période → 409 métier  
- Permission `.prepare` requise pour POST  
- Audit écrit sur création  
- Front : garde module ; hub Comptabilité affiche la carte si catalogue actif  
- Migration : upgrade sur copie `bea_digital_test` uniquement (quand exécuté)

## 9. Critères d’acceptation

Voir [T3_ACCEPTANCE_CRITERIA.md](T3_ACCEPTANCE_CRITERIA.md).

## 10. Procédure de retour arrière (développement)

1. Revert commits de la branche feature T3  
2. Si migration appliquée sur **DB test uniquement** : `alembic downgrade` si `retour_arriere=compatible`, sinon restore dump test  
3. Ne jamais appliquer ni downgrader sur la prod `v1.0.0`  
4. Retirer module catalogue / grants de recette si seedés

## 11. Contrôles avant 1ʳᵉ migration

```text
# Sur environnement DEV uniquement
alembic -c backend/alembic.ini heads
alembic -c backend/alembic.ini current
# Une seule head attendue ; current aligné ou plan de merge documenté
```

Tip fichiers actuel (lecture) : `20261105_mg_stock_mvt_ref_uq` ← `20261102_mg_stock_periodes_02`.  
**À confirmer sur la base de développement réelle** avant génération de `rbcm_01`.
