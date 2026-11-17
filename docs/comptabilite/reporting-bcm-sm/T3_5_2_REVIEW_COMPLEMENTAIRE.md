# T3.5-2 — Revue complémentaire (intégrité et collaboration)

Branche : `feat/reporting-bcm-sm-t3` · HEAD Git inchangé `091b57c`  
**Aucun commit, push, reset, rebuild d’image, ni déploiement.** DEV uniquement.  
T3.5-3 **non commencé**. `engine/runner.py` **non modifié**. Mapping 242 `A_VALIDER` et ECART **non activés**.  
SM `11/2026` et `01/2026` **non réécrites**.

Décision d’orientation (cette revue) : tous les utilisateurs de la Comptabilité qui reçoivent les habilitations Login 2 dans **CORE ADMIN** doivent pouvoir contribuer à la préparation d’une SM. `view` reste lecture seule. L’approbation finale reste un rôle distinct (SoD, T3.5-5).

---

## 1. Fichiers et fonctions inspectés

### Backend — contrôles et paramètres

| Fichier | Fonctions / points lus |
|---------|------------------------|
| `backend/app/services/reporting_bcm_sm/control_service.py` | `run_sm_controls`, `_run_sm_controls_body`, `persist_failed_run`, `global_result`, `_det_category_a`, `_category_c_params`, `_category_b_other_sources`, `_category_d_decisions`, `build_complements`, `serialize_run`, `serialize_issue`, `list_runs`, `param_is_filled`, `display_amount` |
| `backend/app/services/reporting_bcm_sm/parameter_service.py` | `set_parameter`, `current_values`, `parameter_catalog`, `propose_caisse_devises`, `history` |
| `backend/app/services/reporting_bcm_sm/access.py` | `SAISIR_PARAM_PERMS`, `CONTROL_RUN_PERMS`, `IMPORT_PERMS`, `can_saisir_parametre`, `can_lancer_controles`, `can_importer` |
| `backend/app/services/reporting_bcm_sm/constants.py` | `PARAMETER_CODES`, `CONTROL_RUN_RESULTS` (dont `FAILED`) |
| `backend/app/api/v1/endpoints/reporting_bcm_sm.py` | `require_permission` sur import, contrôles, saisie, visa, lecture |
| `backend/app/api/deps.py` | `require_permission` = **OU** des codes ; `{module}.admin` couvre le module |
| `backend/app/services/permission_service.py` | `user_has_permission_codes`, `load_user_permission_codes` (grants **vivants** `role_permissions`, pas seulement le catalogue) |
| `backend/app/services/plateforme_access_service.py` | `ensure_catalogue` : liens rôle→permission **additifs** au Login 1 |
| `backend/app/data/plateforme_catalogue.py` | `_RBCM_LECTEUR` / `_PREPARATEUR` / `_CONTROLEUR` / `_APPROBATEUR`, `ROLE_PERMISSIONS` |
| `backend/app/models/reporting_bcm_sm.py` | `RbcmControlRun`, `RbcmReconcileIssue`, `RbcmParameterValue` |
| `backend/app/db/session.py` | `get_db` : `commit` si succès, **`rollback` si exception** |
| `backend/alembic/versions/20261116_rbcm_03_control_runs.py` | table runs, colonnes issues, backfill SUMMARY |
| `backend/alembic/versions/20261116_rbcm_04_control_integrity.py` | `FAILED` + unique `(run_id, item_key)` |

### Frontend

| Fichier | Points lus |
|---------|------------|
| `frontend/angular20/src/app/reporting-bcm-sm/pages/rbcm-campagne-detail.component.ts` | `canSaisir`, `canControl`, `canImport`, `showImportAction`, `showControlAction`, `resultTone`, bannière `technical_failure`, `enregistrerSaisie` (`expected_value_id`) |
| `frontend/angular20/src/app/reporting-bcm-sm/pages/rbcm-parametres.component.ts` | `expected_value_id: p.value_id` |
| `frontend/angular20/src/app/reporting-bcm-sm/rbcm.models.ts` | `FAILED: 'Échec technique'`, `can_saisir` / `can_control` / `can_importer` / `technical_failure` |

### Non touchés (vérifié)

- `backend/app/services/reporting_bcm_sm/engine/runner.py`
- Données SM BEA `11/2026` et `01/2026`
- Production `v1.0.0`

---

## 2. Constats prouvés par le code

### 2.1 Permissions — écarts du lot T3.5-2 tel que livré

Le rapport T3.5-2 indiquait « saisie C = `parameters.write` uniquement » et un catalogue contrôleur sans `prepare` / `parameters.write`. Conséquences constatées dans le code d’origine :

1. Un utilisateur avec seulement `reporting-bcm-sm.control` **ne pouvait pas** `POST /parameters` (dépendance `PERM_PARAMS` exclusive).
2. `reporting_owner_id` n’était **pas** un garde d’écriture (déjà correct) — mais les endpoints n’étaient pas alignés sur « tout contributeur Login 2 ».
3. `view` seul n’ouvrait aucune écriture (`require_permission` est un OU de codes demandés ; `view` ∉ groupes d’écriture).

### 2.2 Matrice définitive retenue (cette revue)

Les habilitations **vivantes** sont celles de CORE ADMIN (`role_permissions` + rôles utilisateur).  
`ROLE_PERMISSIONS` est le **plancher catalogue** : `ensure_catalogue()` au Login 1 **ajoute** les liens manquants, sans retirer de grants manuels.

Règle métier : tout utilisateur de la Comptabilité à qui CORE ADMIN donne un rôle de contribution peut préparer la SM. On ne donne **pas** l’écriture aux comptes `view` seuls.

| Action | Permission API (OU) | Lecteur | Préparateur | Contrôleur | Approbateur | Admin module |
|--------|---------------------|---------|-------------|------------|-------------|--------------|
| Consulter SM, file, rapports | `view` | oui | oui | oui | oui | oui |
| Importer / confirmer BAL DET | `import` ∪ `prepare` ∪ `control` | non | oui | oui | non | oui |
| Lancer / relancer les contrôles | `prepare` ∪ `control` ∪ `import` | non | oui | oui | non | oui |
| Saisir / réviser un paramètre C (et confirmer caisse A) | `parameters.write` ∪ `prepare` ∪ `control` ∪ `correct` | non | oui | oui | non | oui |
| Visa paramètre (valider / rejeter) | `control` | non | non | oui | non | oui |
| Approuver / rouvrir la SM | `approve` / `reopen` | non | non | non | oui | oui |

Correspondance catalogue (plancher) :

| Rôle Login 2 | Permissions de contribution |
|--------------|-----------------------------|
| `reporting-bcm-sm.lecteur` | `view`, `export` — **aucune écriture** |
| `reporting-bcm-sm.preparateur` | lecture + `prepare`, `import`, `parameters.write`, `confirm`, `correct`, `mapping.propose` |
| `reporting-bcm-sm.controleur` | lecture + `prepare`, `import`, `parameters.write`, `correct`, `control`, `confirm`, `mapping.validate` — **pas** `approve` |
| `reporting-bcm-sm.approbateur` | lecture + `approve`, `reopen` — **pas** de préparation (SoD) |
| `reporting-bcm-sm.admin` | toutes les permissions `reporting-bcm-sm.*` |

Affectation recommandée CORE ADMIN pour la Comptabilité :

- Contributeurs SM : rôle **préparateur** et/ou **contrôleur** (un utilisateur peut avoir les deux).
- Consultation seule : **lecteur**.
- Visa final : **approbateur** en plus, sans lui donner automatiquement `prepare` via le plancher.
- Super-utilisateur module : **admin**.

`{module}.admin` (`reporting-bcm-sm.admin`) couvre toutes les actions du module via `user_has_permission_codes`.

Frontend = mêmes ensembles :

- `canSaisir()` ↔ `SAISIR_PARAM_PERMS` + `admin`
- `canControl()` ↔ `CONTROL_RUN_PERMS` + `admin`
- `canImport()` ↔ `IMPORT_PERMS` + `admin`
- File « Informations à compléter » : `available_actions` calculées **backend** (`build_complements`) avec les mêmes helpers. Un lecteur ne voit que `CONSULTER`.

Les actions interdites sont refusées **aussi** par `Depends(require_permission(...))` : un appel API direct avec un jeton `view` seul reçoit 403.

### 2.3 Concurrence des paramètres — écart puis règle stricte

Écart livré : `expected_value_id` facultatif. Deux sessions pouvaient enregistrer une nouvelle ligne append-only sans détecter que l’autre avait déjà écrit → dernière écriture « gagnante » à l’affichage (`current_values` = plus récente), historique conservé mais **écrasement silencieux du courant**.

Règle maintenant dans `set_parameter` :

1. `pg_advisory_xact_lock(hashtextextended('rbcm-param:{campaign}:{code}', 0))` — sérialise les saisies du même paramètre sur la même SM.
2. Lecture du courant `SELECT … FOR UPDATE`.
3. Première saisie (`prev is None`) : `expected_value_id` doit être absent ; s’il est fourni → 409 `PARAM_CONFLICT`.
4. Révision (`prev` existe) : `expected_value_id` **obligatoire** sinon 409 `PARAM_VERSION_REQUIRED` ; s’il ne correspond pas à `prev.id` → 409 `PARAM_CONFLICT`.
5. Insert append-only (`supersedes_value_id = prev.id`). Aucun `UPDATE` / `DELETE` de l’historique.

Pas d’unicité SQL « une seule ligne par (SM, code) » : cela casserait l’historique. L’unicité **courante** est garantie par le verrou + la version.

Angular envoie déjà `expected_value_id` (fiche et écran paramètres).

### 2.4 Concurrence des contrôles

`_run_sm_controls_body` :

1. `SELECT rbcm_campaign … FOR UPDATE` **avant** `latest_run`.
2. Insert du run + des issues dans **la même** transaction SQLAlchemy.
3. Le verrou est un verrou de transaction : libéré au `commit` (`get_db`) ou au `rollback`.
4. Deux lancements sur la **même** SM sont sérialisés ; le second voit le run du premier (`previous_run_id`).
5. Deux SM distinctes = deux lignes campagne = pas de contention.

Écart constaté à l’exécution réelle (pas à la seule lecture) : persister un run `FAILED` **sans** rollback préalable deadlockait. L’INSERT FK vers `rbcm_campaign` demande `FOR KEY SHARE` alors que la transaction fautive tenait encore `FOR UPDATE`. Corrigé (voir § 6).

### 2.5 Échecs techniques

Trois issues distinctes :

| Situation | `result` | Présentation |
|-----------|----------|----------------|
| Contrôle allé au bout, file saine | `OK` / `WARNINGS` | métier |
| Contrôle allé au bout, anomalies B/C/D/A | `INCOMPLETE` / `DECISIONS_PENDING` / `BLOCKING` | métier |
| Exception non métier pendant le traitement | `FAILED` | **échec technique**, jamais `OK` |

Séquence actuelle :

1. Exception non-`AppError` dans le corps.
2. Capture de `campaign.id` / `user.id` (identité, avant expiration).
3. `rollback()` de la transaction partielle (run/issues non commitées disparaît ; verrou libéré).
4. Insert d’un run `FAILED` + audit `rbcm.control.technical_failure` + **`commit`**.
5. `AppError` 500 `CONTROL_TECHNICAL_FAILURE`.
6. `get_db` rollback d’une transaction **vide** : le run `FAILED` survit.

Sans le `commit` interne, `get_db` effacerait le run d’échec.  
Sans le rollback préalable, l’INSERT `FAILED` restait bloqué sur le `FOR UPDATE`.  
Sans recharger l’utilisateur après rollback, SQLAlchemy levait `MissingGreenlet` (objet expiré).

`build_complements` expose `technical_failure: run.result == "FAILED"`. La fiche affiche : *« Le dernier contrôle a échoué techniquement. Il n’est pas un résultat métier OK. »*

### 2.6 Classification `caisse_devises`

Le catalogue conserve **huit** codes (dont `caisse_devises`, `calculable=true`).  
Double demande évitée :

- **A** : item unique `item_key = PARAM:caisse_devises` (proposition DET, confirmation manuelle, jamais d’auto-save).
- **C** : `_category_c_params` **saute** `caisse_devises`.

Si la DET est absente, A pose `DET:REQUIRED` (bloquant) ; C n’est pas évalué. Une seule file de saisie caisse, côté A, dès que la DET existe.

SM `11/2026` : `caisse_devises = 0.00` / `CALCULE` / source `BAL_DET_DERIVE` — **inchangé**. `param_is_filled(0.00, CALCULE)` est vrai (zéro réel ≠ absence).

### 2.7 Migration et historique

`rbcm_03` :

- Backfill : un `rbcm_control_run` par campagne qui avait déjà des issues (`summary.backfill = true`, `origin = T3.5-2`).
- Issues existantes rattachées, **jamais supprimées**.
- `item_key = COALESCE(..., 'LEGACY:' || code)`, `category = COALESCE(..., 'A')`.
- `resolution_state = RESOLVED` si `resolved` sinon **`OK`**.

Les « deux issues SUMMARY » du rapport T3.5-2 sont **une par SM** :

| SM | Issue | `item_key` | Catégorie | État | Message |
|----|-------|------------|-----------|------|---------|
| `11/2026` BEA | `SUMMARY` | `LEGACY:SUMMARY` | A | OK | Contrôles internes BAL DET (source unique T3.4-A2) |
| `01/2026` BEA | `SUMMARY` | `LEGACY:SUMMARY` | A | OK | idem |

Ce ne sont pas des écarts métier courants : snapshots informatifs T3.4-A2. Le reclassement A/OK est **cohérent**. Aucune réécriture effectuée.

`rbcm_04` (additif, DEV) :

- `ck_rbcm_control_run_result` inclut `FAILED`.
- Unique partiel `uq_rbcm_reconcile_issue_run_item` `(run_id, item_key)` WHERE les deux NOT NULL.

Endpoints : **aucun** `PATCH` / `DELETE` d’issue. La « résolution » est un **diff de `item_key`** entre runs (`resolved_since_previous` / `new_since_previous` / `still_open`). L’anomalie du run N reste consultable via `GET …/controls/runs/{id}`.

`item_key` stable : `PARAM:{code}`, `DET:REQUIRED`, `PARAM:caisse_devises`, `FPN:ANNEXES`, `LEGACY:SUMMARY`.

---

## 3. Risques identifiés

| Risque | Gravité | Traitement |
|--------|---------|------------|
| Contrôleur incapable de saisir C | Élevé ( collab ) | Corrigé : OR des perms + plancher catalogue contrôleur |
| `expected_value_id` omis → écrasement du courant | Élevé | Corrigé : obligatoire si valeur existante |
| Run `FAILED` perdu au rollback `get_db` | Élevé | Corrigé : commit dédié après rollback du travail partiel |
| Deadlock INSERT `FAILED` vs `FOR UPDATE` | Élevé (observé) | Corrigé : rollback avant persist |
| `MissingGreenlet` après rollback (user expiré) | Élevé (observé en test PG) | Corrigé : IDs capturés puis `db.get(User)` |
| Double saisie caisse A+C | Moyen | Corrigé : C ignore `caisse_devises` |
| Plancher catalogue ≠ grants DEV déjà en base | Moyen | `ensure_catalogue` additif au prochain Login 1 / CORE ADMIN |
| `import` seul lance les contrôles mais ne saisit pas C | Faible | Voulu : CORE ADMIN ajoute `preparateur` si besoin |
| Visa `validate_parameter` limité à `control` | Faible | Voulu (SoD auteur / visa) |
| Tests PG sur `bea_digital` (pas `bea_digital_test`, schéma rbcm absent là-bas) | Accepté | Isolation `bank_code=T352R` année 2099 + cleanup |

---

## 4. Tests exécutés et résultats

```
backend/.venv/Scripts/python.exe -m pytest
  tests/test_reporting_bcm_sm.py
  tests/test_reporting_bcm_sm_t35_1.py
  tests/test_reporting_bcm_sm_t35_2.py
  tests/test_reporting_bcm_sm_t35_2_review.py
73 passed in 8.89s
```

Ruff : fichiers de la revue **propres**.

Les tests PG utilisent **deux sessions SQLAlchemy / connexions PostgreSQL distinctes** (`NullPool`, hôte `127.0.0.1` — le hostname Docker `postgres` n’est pas résolvable depuis Windows). Banque jetable `T352R` / 2099. Cleanup systématique.

| Cas demandé | Test | Résultat |
|-------------|------|----------|
| Contrôleur peut saisir | `test_controleur_peut_saisir`, `test_catalogue_controleur_a_la_saisie` | OK |
| `view` seul lecture | `test_view_cannot_write`, `test_lecteur_complements_has_no_saisir` | OK |
| prepare / import contribuent | `test_prepare_et_import_peuvent_contribuer` | OK |
| Deux saisies concurrentes (version périmée) | `test_pg_param_concurrent_second_refused` | OK — 409 `PARAM_CONFLICT`, historique ≥ 2 |
| Deux sessions, première saisie encore ouverte | `test_pg_param_two_sessions_second_refused` | OK — 409 `PARAM_VERSION_REQUIRED`, **une** valeur `1.00` |
| Deux contrôles simultanés même SM | `test_pg_two_control_runs_same_sm_chained` | OK — 2 runs, `previous_run_id` chaîné, issues ≥ 2 |
| Verrou PG réel 2e session | `test_pg_lock_timeout_second_session_same_sm` | OK — `SET lock_timeout` + `FOR UPDATE` |
| Deux SM en parallèle | `test_pg_two_sm_controls_independent` | OK — 1 run chacune, pas de `previous_run_id` |
| Échec technique en cours de contrôle | `test_pg_technical_failure_not_ok` | OK — 500 `CONTROL_TECHNICAL_FAILURE`, run `FAILED`, 0 run `OK` |
| Paramètre absent / nul / zéro | `test_parametre_absent_nul_zero`, tests T3.5-2 existants | OK — `None` ≠ `0.00` |
| Anomalie historique non mutée | `test_anomaly_historique_pas_mutee_dans_le_service` | OK |
| Classification caisse | `test_caisse_devises_pas_dupliquee_en_c` | OK — pas de `PARAM:caisse_devises` en C |
| SM 11/2026 intacte | `test_pg_does_not_touch_sm_novembre` | OK — `CALCULEE`, caisse `0.00`, 242 `A_VALIDER` |

Non simulé : un mock de verrou. Les six tests `test_pg_*` parlent à PostgreSQL 17 DEV.

---

## 5. Corrections recommandées

1. Aligner saisie / import / contrôles sur des groupes OU Login 2, sans `reporting_owner_id`, sans écrire pour `view`. **Fait.**
2. Élargir le plancher rôle **contrôleur** (pas le lecteur, pas l’approbateur). **Fait.** CORE ADMIN reste la source d’affectation utilisateurs.
3. Verrou de version strict sur `set_parameter`. **Fait.**
4. `FAILED` distinct, persisté hors de la transaction annulée, sans deadlock. **Fait.**
5. Une seule file pour `caisse_devises` (A). **Fait.**
6. Contrainte `FAILED` + unicité `(run_id, item_key)`. **Fait** (`rbcm_04`).
7. Ne pas réécrire les SUMMARY T3.4. **Respecté.**
8. Ne pas commencer T3.5-3. **Respecté.**

Action **humaine** restante (pas du code) : se reconnecter Login 1 une fois (ou ouvrir CORE ADMIN) pour que `ensure_catalogue` pousse les nouveaux liens du rôle contrôleur, puis attribuer préparateur/contrôleur aux utilisateurs Comptabilité concernés.

---

## 6. Corrections effectivement réalisées

Autorisées par la demande de revue + la consigne « tous les users de la compta peuvent tous faire et les permissions seront données dans CORE ADMIN ».

| Zone | Modification |
|------|----------------|
| `access.py` | Groupes `SAISIR_PARAM_PERMS`, `CONTROL_RUN_PERMS`, `IMPORT_PERMS` |
| Endpoints | Import / contrôles / saisie / proposition caisse utilisent ces groupes |
| Catalogue | Contrôleur : `prepare`, `import`, `parameters.write`, `correct` (en plus de `control`) |
| `parameter_service.set_parameter` | Advisory lock + `FOR UPDATE` + `PARAM_VERSION_REQUIRED` / `PARAM_CONFLICT` |
| `control_service` | Caisse uniquement en A ; `FAILED` après rollback + commit + audit ; complements alignés |
| `rbcm_04` | Check `FAILED` + unique `(run_id, item_key)` — appliquée en DEV (`migrate` volume, pas de rebuild) |
| Fiche Angular | `canSaisir` / `canImport` / `canControl` ; bannière échec technique ; `expected_value_id` |
| Tests | `test_reporting_bcm_sm_t35_2_review.py` (unitaires + PG deux sessions) |

Non faits : commit, push, prod, activation mapping/ECART, T3.5-3, modification `runner.py`, `docker compose down -v`.

---

## 7. État des données DEV avant / après

| Élément | Avant cette revue | Après tests de revue |
|---------|-------------------|----------------------|
| `alembic_version` | `20261116_rbcm_03` puis `rbcm_04` (revue) | `20261116_rbcm_04` |
| SM `11/2026` BEA | `a9c8832b-…` `CALCULEE` | identique |
| `caisse_devises` 11/2026 | `0.00` `CALCULE` `BAL_DET_DERIVE` | identique |
| Issues 11/2026 | 1 × `SUMMARY` `LEGACY:SUMMARY` A/OK | identique |
| Run 11/2026 | 1 backfill T3.5-2 `OK` | identique |
| SM `01/2026` | `CALCULEE`, 1 × `SUMMARY` A/OK | identique |
| Mapping `A_VALIDER` | 242 | 242 |
| Banque jetable `T352R` | leftover d’un test interrompu (nettoyé) | **0** campagne |

Aucune donnée métier BEA n’a été mise à jour. Les campagnes `T352R`/2099 créées par les tests ont été supprimées.

---

## 8. Décisions métier encore nécessaires

1. **CORE ADMIN** : liste nominative des utilisateurs Comptabilité → rôles `preparateur` / `controleur` / `lecteur` / `approbateur`. Le code ne les auto-accorde pas.
2. **SoD approbation** (T3.5-5) : interdire qu’un même utilisateur soit dernier préparateur et approbateur ? Non implémenté.
3. **Visa paramètre** : rester sur `control` seul (choix actuel) ou l’ouvrir à `prepare` ?
4. **Méthode caisse** (D04/D05) : préfixe NCG `101` + EUR toujours provisoire ; la confirmation manuelle reste obligatoire.
5. **FPN annexes** : item C en `CONSULTER` jusqu’à T3.5-3.
6. Validation explicite de **cette** revue avant tout démarrage de T3.5-3.

---

## Hors périmètre (respecté)

- T3.5-3 (canevas / préparation officielle)
- Activation des 242 règles `A_VALIDER`
- ECART
- Production `v1.0.0`
- Rebuild images Docker
- Commit / push / reset Git
