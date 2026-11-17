# T3.5-3-A — Audit de l’état réel du dépôt

**Conception uniquement. Aucune implémentation. Aucune migration exécutée par ce lot.**  
Lecture seule de Git, du code, des rapports et de PostgreSQL DEV (`SELECT` uniquement).

Date de constat : 16/11/2026.

---

## 1. Git

| Élément | Valeur constatée |
|---------|------------------|
| Branche | `feat/reporting-bcm-sm-t3` |
| HEAD | `091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32` (`091b57c`) |
| Message | `docs(deploiement): aligner transmission srvsuividep et porte de release` |
| Auteur / date | Moustapha9999 · 2026-11-15 12:57:37 +0000 |
| Tracking | branche locale dirty, **aucun commit T3** depuis ce HEAD |

Le HEAD historique de référence `091b57c` **est toujours** le HEAD Git. Tout le chantier T3 (code, migrations, docs, front) est **non commité**.

### 1.1 Fichiers réellement modifiés (tracked)

```
M backend/app/api/v1/router.py
M backend/app/data/module_backup_scopes.py
M backend/app/data/plateforme_catalogue.py
M backend/app/models/__init__.py
M frontend/angular20/angular.json
M frontend/angular20/src/app/app.routes.ts
M frontend/angular20/src/app/layout/shell/shell-nav.ts
M frontend/angular20/src/app/plateforme/espace-hub.guard.ts
M frontend/angular20/src/app/plateforme/module-routing.contract.ts
```

### 1.2 Fichiers réellement ajoutés (untracked, extraits)

| Zone | Contenu |
|------|---------|
| Migrations | `backend/alembic/versions/20261116_rbcm_01` … `_04` |
| Backend module | `models/reporting_bcm_sm.py`, `schemas/`, `endpoints/reporting_bcm_sm.py`, `services/reporting_bcm_sm/` |
| Tests | `test_reporting_bcm_sm.py`, `_t35_1`, `_t35_2`, `_t35_2_review` |
| Front | `frontend/angular20/src/app/reporting-bcm-sm/` |
| Docs | `docs/comptabilite/` (dont T3.5-1/2/T0) |
| e2e | `e2e/` |

`engine/runner.py` est présent (untracked, livré T3.3/T3.4). **Non modifié par T3.5-3-A.**

`BEA-SM-10-2026.xlsx` : SHA-256 `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658`, 78 202 octets — **non modifié**.

Reliquat T0 (non livrable) : `_t353_t0_scratch/` — dumps d’inspection openpyxl. **Q12 :** inspecté à la révision ; **non supprimé**. Voir `T3_5_3_A_REVISION_DOCUMENTAIRE.md` § scratch.

---

## 2. Docker / bases (lecture seule)

Conteneurs constatés **en cours** : `bea-postgres`, `bea-backend`, `bea-frontend`, `bea-worker`, `bea-redis`, `bea-pgadmin`.  
Aucun `docker compose down`, aucun rebuild, aucun `upgrade` lancé par cet audit.

Deux bases PostgreSQL sur le volume unique `bea_postgres_data` :

| Base | Rôle | `alembic_version` lu |
|------|------|----------------------|
| `bea_digital` | DEV réelle (SM BEA, module rbcm) | **`20261116_rbcm_04`** |
| `bea_digital_test` | Base de test unique (copie / scripts test-db) | **`20261105_mg_stock_mvt_ref_uq`** |

`bea_digital_test` : **0 table `rbcm_*`**. Les tests T3.5-2 qui ont touché PostgreSQL l’ont fait sur `bea_digital` (campagnes jetables `T352R` ensuite supprimées — rapport de revue).

Production `v1.0.0` : **non interrogée**.

---

## 3. Migrations : existantes, appliquées, contradiction README

### 3.1 Fichiers présents dans le dépôt

Chaîne unique, head fichiers = `20261116_rbcm_04` :

| Révision | Fichier | Revises | Rôle |
|----------|---------|---------|------|
| `20261116_rbcm_01` | `…_rbcm_01_fondations.py` | `20261105_mg_stock_mvt_ref_uq` | Tables `rbcm_*` fondations + catalogue module |
| `20261116_rbcm_02` | `…_rbcm_02_reporting_owner.py` | `rbcm_01` | Responsable SM + historique (T3.5-1) |
| `20261116_rbcm_03` | `…_rbcm_03_control_runs.py` | `rbcm_02` | Runs de contrôle (T3.5-2) |
| `20261116_rbcm_04` | `…_rbcm_04_control_integrity.py` | `rbcm_03` | `FAILED` + unique `(run_id, item_key)` |

Aucune `rbcm_05`. Aucune table template / document_decision.

### 3.2 Appliquées

| Environnement | Head réel | Conclusion |
|---------------|-----------|------------|
| `bea_digital` (DEV) | `20261116_rbcm_04` | **rbcm_01 à rbcm_04 appliquées** |
| `bea_digital_test` | `20261105_mg_stock_mvt_ref_uq` | **rbcm_* non appliquées** |
| Dépôt Git (HEAD) | pas de fichier rbcm commité | les 4 fichiers existent seulement en working tree |

Cela **confirme** les rapports T3.5-1 (`rbcm_02`), T3.5-2 (`rbcm_03`) et T3.5-2 revue (`rbcm_04`).

### 3.3 Contradiction README / T3_PHASE_STATUS

| Document | Phrase | Verdict |
|----------|--------|---------|
| `README.md` L15 | « migration DEV non appliquée » | **Obsolète** |
| `T3_PHASE_STATUS.md` | T3.2 « `rbcm_01` — **non appliquée** (Docker DEV arrêté) » | **Obsolète** (état d’avant démarrage Docker) |
| T3.5-1 / T3.5-2 / revue | migrations appliquées, `alembic_version` cité | **Aligné avec la base DEV actuelle** |

**Résolution (constat d’audit, inchangé) :** il n’y a **pas** deux vérités concurrentes sur `bea_digital` : la base dit `rbcm_04`. Le README et `T3_PHASE_STATUS.md` décrivaient un état T3.2 (Docker arrêté).  
`bea_digital_test` reste volontairement en retard (pas de schéma rbcm) — ce n’est pas la DEV métier.

**Suite documentaire (révision T3.5-3-A, Q11) :** le README et `T3_PHASE_STATUS.md` sont **alignés** sur ce constat. Relu `alembic_version` en `SELECT` uniquement le 16/11/2026 (révision) : `bea_digital` = `20261116_rbcm_04` ; `bea_digital_test` = `20261105_mg_stock_mvt_ref_uq`. Aucun `upgrade` lancé.

---

## 4. Tables `rbcm_*` réellement présentes (`bea_digital`)

20 tables. **Absentes** : `rbcm_template`, `rbcm_template_cell`, `rbcm_document_decision`.

```
rbcm_balance_ncg
rbcm_calculation_run
rbcm_campaign
rbcm_cell_decision
rbcm_cell_result
rbcm_control_result
rbcm_control_run
rbcm_deliverable
rbcm_ecart_snapshot
rbcm_import
rbcm_import_line_det
rbcm_mapping_rule
rbcm_mapping_rule_source
rbcm_mapping_version
rbcm_parameter_definition
rbcm_parameter_value
rbcm_reconcile_issue
rbcm_reporting_owner_history
rbcm_unmapped_rubric
rbcm_validation_event
```

Données métier lues (aucune écriture) :

| Objet | Constat |
|-------|---------|
| Campagnes | 2 : BEA `01/2026` `CALCULEE`, BEA `11/2026` `CALCULEE` |
| Mapping | **242** `A_VALIDER`, **0** `ACTIVE` |
| `rbcm_unmapped_rubric` | **0** ligne (les 67 rubriques ne sont pas matérialisées) |
| `rbcm_calculation_run` | 2 |
| `rbcm_cell_result` | 92 (préfixes `BCM:…`, `ECART`, `ETAT_B_PROVISOIRE`, `ETAT_C_PROVISOIRE`) |
| `rbcm_cell_decision` | **0** |
| `rbcm_deliverable` | **0** |

Les SM `11/2026` et `01/2026` n’ont **pas** été modifiées.

---

## 5. Modèles inspectés (code + DDL vivant)

Fichier : `backend/app/models/reporting_bcm_sm.py`.  
Migration fondatrice : `20261116_rbcm_01_fondations.py`.  
rbcm_02–04 n’altèrent pas campaign / cell_result / cell_decision / deliverable / calculation_run (hors owner sur campaign).

### 5.1 `RbcmCampaign`

| Champ / contrainte | Code | Base DEV |
|--------------------|------|----------|
| UNIQUE `(bank_code, year, month, campaign_version)` | oui | `uq_rbcm_campaign_period_version` |
| `campaign_version` | Integer ≥ 1 | CHECK `ck_rbcm_campaign_version` |
| `status` CHECK `IN (BROUILLON…ROUVERTE)` | **déclaré dans le modèle** | **absent** de `rbcm_01` et de la base |
| `template_version_id` | UUID nullable | UUID nullable, **aucune FK** |
| `mapping_version_id` | UUID nullable | UUID nullable, **aucune FK** |
| `reporting_owner_id` | T3.5-1 | FK `users` SET NULL (rbcm_02) |

`CampaignOut` **n’expose pas** `template_version_id`.

Trois notions à ne pas confondre (aucune n’est implémentée pour le document) :

1. `campaign_version` — version de **SM** après réouverture.
2. Version de **canevas** — table absente.
3. Version de **fichier WORK** — table deliverable sans statut WORK.

### 5.2 `RbcmCalculationRun`

- Pas d’UNIQUE campagne → N runs.
- `status` String(24) défaut `RUNNING`, pas de CHECK SQL.
- `fingerprint_template` String(64) existe, **jamais alimenté** par un SHA canevas.
- FK `campaign_id` RESTRICT, `started_by_id` SET NULL.

### 5.3 `RbcmCellResult`

| | Code | Base |
|--|------|------|
| UNIQUE | `(run_id, cell_ref)` | `uq_rbcm_cell_result_run_cell` |
| `cell_ref` | `String(32)` | `varchar(32)` NOT NULL |
| montants | `Numeric(18,2)` nullable | precision 18 scale 2 |
| `value_status` | String(32) défaut `NON_RENSEIGNE` | pas de CHECK |
| Index `campaign_id` / `cell_ref` seuls | `index=True` modèle | **non créés** (seulement PK + UNIQUE run+cell) |

Longueurs réelles des `cell_ref` stockés : min 5 (`ECART`), max 17 (`ETAT_B_PROVISOIRE`).  
Clés moteur observées hors `BCM:nnn` : `ECART`, `ETAT_B_PROVISOIRE`, `ETAT_C_PROVISOIRE`.  
Clés moteur composites (mapping) : `BCM:234 / 235`, `BCM:327 / 328`, `BCM:131 / 321` (longueur 13, toujours namespace moteur).

**Aucun `A:102:D` en base.** Insérer `A:102:D` dans la même table **passerait** le UNIQUE (chaîne différente de `BCM:102`) — c’est le mélange sémantique à interdire, pas une erreur SQL.

Le runner **INSERT** des `RbcmCellResult` ; aucun `UPDATE calculated_value` dans les services.

### 5.4 `RbcmCellDecision`

- Table créée, **0 ligne**, **aucun service, aucune route**.
- `cell_ref` varchar(32) — même espace que le moteur.
- `reason` TEXT **nullable**.
- `document_id` UUID **sans FK** GED.
- Pas de `justificatif_ref`.
- `supersedes_decision_id` SET NULL (pattern append-only prévu, inutilisé).
- Pas d’UNIQUE « décision courante ».

Réutiliser cette table pour `A:102:D` polluerait un contrat moteur encore vide mais déjà typé `BCM:`.

### 5.5 `RbcmDeliverable`

- **Aucun UNIQUE** hors PK → plusieurs lignes / campagne déjà possibles.
- `kind` varchar(16), `status` varchar(24) défaut `GENERATED`, **pas de CHECK**.
- `run_id` SET NULL.
- `warnings` JSONB.
- `stored_path` varchar(500), `sha256` varchar(64), `filename` varchar(255).
- **Pas** de `template_version_id` sur le livrable.
- 0 ligne en DEV.

Le service actuel `excel_export.generate_excel` :

- exige un run moteur `DONE` (`EXPORT_NO_RUN` sinon) ;
- crée un `Workbook()` **vide** aux noms `ETAT A/B/C`, `Informations`, `FPN`, `Ratios`, `Controles`, `Alertes` — **pas** les 8 noms officiels (`informations à fournir`, `CALCUL FPN`, `RATIO COUVERTURE DE RISQUE`, …) ;
- écrit `cell_ref` moteur en liste ;
- fichier `{upload_root}/reporting-bcm-sm/{campaign_id}/exports/BCM_SM_{YYYYMM}_v{campaign_version}.xlsx` ;
- **`path.write_bytes` sur un nom fixe** → **écrasement binaire** du fichier précédent malgré un nouvel INSERT SQL.

C’est incompatible avec la règle « plusieurs WORK sans écrasement ». Le WORK futur **ne doit pas** réutiliser ce service tel quel. L’export technique peut rester, libellé distinct.

### 5.6 Écart modèle SQLAlchemy / migration / base

| Sujet | Modèle | `rbcm_01` | Base `bea_digital` |
|-------|--------|-----------|-------------------|
| `ck_rbcm_campaign_status` | oui | **non** | **non** |
| FK `template_version_id` | non | non | non |
| Index `cell_result.campaign_id` | `index=True` | non créé | absent |

Hors périmètre T3.5-3-A (pas de correctif maintenant).

---

## 6. Services, schémas, routes

### 6.1 Services (`backend/app/services/reporting_bcm_sm/`)

| Fichier | Rôle actuel | Lien document |
|---------|-------------|----------------|
| `campaign_service.py` | CRUD SM, P2 | `template_version_id` ignoré |
| `import_service.py` | BAL DET | — |
| `parameter_service.py` | Append-only paramètres + lock | **modèle à imiter** pour les décisions documentaires |
| `control_service.py` | File A/B/C/D, FAILED | portes Dxx |
| `workflow_service.py` | Statuts campagne | pas de WORK |
| `dashboard_service.py` | Accueil / KPI | — |
| `access.py` | Groupes OU Login 2 | prepare/control/import/correct |
| `mapping_seed.py` | 242 `A_VALIDER` | `cell_ref` = `BCM:nnn` |
| `engine/runner.py` | Calcul Decimal, INSERT `CellResult` | **ne pas appeler** pour WORK |
| `excel_export.py` | Export technique | **pas** le canevas officiel |

### 6.2 Schémas Pydantic

`backend/app/schemas/reporting_bcm_sm.py` : campagnes, imports, paramètres, mapping, contrôles.  
**Aucun** schéma Deliverable / CellResult / CellDecision / Document / Template.

### 6.3 Routes documentaires

Préfixe API : `/api/v1/reporting-bcm-sm/`.

Existantes liées export :

- `POST /campaigns/{id}/exports/excel` — `PERM_EXPORT` → `generate_excel`
- `GET /campaigns/{id}/exports/{deliverable_id}/download`
- `GET /pdf-status` — PDF indisponible

Absentes (T3.5-3 futur) : GET document par feuille, POST génération WORK, POST décision documentaire, liste des versions WORK.

`POST /campaigns/{id}/calculate` existe (moteur). Ne pas le brancher sur la préparation de canevas.

### 6.4 Frontend

Fiche guidée 7 étapes (`SM_GUIDED_STEPS`). T3.5-2 : l’étape courante s’arrête à 4 (compléter). Étapes 5–7 **non implémentées** (préparer / vérifier / valider).  
Aucun composant 8 onglets feuilles officielles.  
Pas de Material/Tailwind ajouté dans `plateforme/`.

### 6.5 Permissions (rappel T3.5-2, à réutiliser plus tard)

| Action future T3.5-3 | Permission déjà définie |
|----------------------|-------------------------|
| Voir le document | `view` |
| Préparer / régénérer WORK | `prepare` ∪ `control` ∪ `import` |
| Corriger une LEAF | `parameters.write` ∪ `prepare` ∪ `control` ∪ `correct` |
| Télécharger | `export` |
| Approuver réglementaire | **hors T3.5-3** |

`view` seul : lecture. CORE ADMIN attribue les rôles.

---

## 7. Écarts code ↔ documentation T0 / conception T3.5

| Source | Affirmation | État réel |
|--------|-------------|-----------|
| Conception T3.5 §10.1 | WORK = propositions `A_VALIDER` | **Rejeté** par T0 ; toujours 0 `ACTIVE` ; runner ignore `A_VALIDER` pour le livrable officiel |
| Conception T3.5 §10.3 | Édition → `RbcmCellDecision` | Table vide, aucun code ; **à remplacer** par une table documentaire |
| T0 §9 | Réutiliser `CellResult` avec `A:102:D` | **Incompatible** (complément T0 + cet audit) |
| T0 §9 | `campaign.template_version_id` à brancher | Colonne orpheline, pas de table cible |
| README | migration DEV non appliquée | **Faux** pour `bea_digital` (`rbcm_04`) |
| `excel_export` docstring | « huit feuilles cibles du modèle officiel » | Noms **incorrects** ; classeur technique |
| 67 non mappées | table `rbcm_unmapped_rubric` | **0 ligne** |

Portes D01, D02, D06, D09, D15, D16/D17, D22 : **inchangées**. ECART inactif (`is_active_in_run` non relu ici ; runner force `False`).

---

## 8. Canevas officiel (contraintes, non modifié)

Reprise T0 + complément, vérifiée par SHA :

- 8 feuilles, 663 formules ;
- 9 formules à constantes d’octobre → **neutraliser** dans le WORK, jamais règles métier ;
- 3 × 30 % + 3 compléments 70 % → `PROVISOIRE_D09` ;
- 27 IF concordance ; 4 IF métier ; 5 divisions/ratios ;
- normes G / `0,1` / `0,2` / `*10` à **conserver** ;
- WORK futur : feuille `AVERTISSEMENT` + en-tête/pied de page, **sans insertion de ligne**.

---

## 9. Ce que T3.5-3-A ne fait pas

- Pas de `rbcm_05`.
- Pas de copie du xlsx vers un stockage applicatif.
- Pas d’API, pas d’UI étapes 5–6.
- Pas d’activation mapping / ECART.
- Pas de modification des SM 11/2026 et 01/2026.

Les constats des §1–8 restent ceux de l’audit initial. Les **corrections de conception** (saisissabilité D9, FK, concurrence, graphe Decimal, stockage template, changement de canevas) sont dans le modèle révisé, pas dans ce constat historique.

Suite : `T3_5_3_A_MODELE_DOCUMENTAIRE.md` (cible révisée, D1–D9) · `T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md` · `T3_5_3_A_REVISION_DOCUMENTAIRE.md` · `T3_5_3_A_LEVEE_RESERVES_D1_D9.md`.

---

## 10. Addendum — révision documentaire

Date : 16/11/2026. Relecture `alembic_version` : inchangée (`rbcm_04` / `mg_stock_mvt_ref_uq`). HEAD Git inchangé `091b57c`.

| Sujet | Traitement |
|-------|------------|
| Six corrections techniques | Intégrées au modèle cible |
| R1–R15 / Q1–Q12 | Intégrés aux arbitrages |
| Découpage A–F | T3.5-3-A = conception seule ; B = `rbcm_05` + seed |
| README / `T3_PHASE_STATUS.md` | Alignés sur les migrations DEV réelles |
| `_t353_t0_scratch/` | Inspecté, non supprimé |

---

## 11. Addendum — levée D1–D9 (16/11/2026)

Les constats §1–8 **restent** ceux de l’audit (état réel du code et de la base). Précisions de conception **sans** muter ces constats :

- `excel_export` / `GENERATED` : conservés ; `rbcm_05` ajoutera `template_id` et `document_seq` **nullable** (D1).
- Contrôle `ETAT A!I147` : clé cible `A:CTRL:I147` (D2) — n’existait pas dans le code.
- `*10` (H31) : T0 « conserver_norme » → nature cible `CANVAS_SCALE_FORMULA` (D3), distincte des valeurs G / 0,1 / 0,2.
- `bea_digital_test` toujours sans `rbcm_*` (D6).

Aucune migration, aucun seed, aucun Excel modifié par cet addendum.
