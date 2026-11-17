# T3.5-2 — Contrôles métier et file des informations à compléter

Branche : `feat/reporting-bcm-sm-t3` · HEAD de référence `091b57c`  
**Aucun commit / push / déploiement production.** DEV uniquement.

Référence métier : `T3_5_WORKFLOW_CONCEPTION.md`.  
Prérequis : T3.5-1 validé (`T3_5_1_REPORT.md`).  
Hors périmètre : T3.5-3 à T3.5-6, canevas Excel, mapping ACTIVE, ECART, PDF, production v1.0.0.

---

## 1. Audit initial (avant modification)

### 1.1 Suppression des anciennes anomalies

`run_det_coherence_controls` (T3.4-A2) **supprimait toutes** les `rbcm_reconcile_issue` de la SM avant d’en réécrire un jeu. `reconcile_det_cond_legacy` faisait de même.

Conséquence : impossible de consulter un rapport précédent, d’identifier les anomalies résolues, ou d’attribuer une exécution à un utilisateur.

### 1.2 Modèle existant

| Table | Constat |
|-------|---------|
| `rbcm_reconcile_issue` | Anomalies plates (code, gravité, message, `resolved`). Pas de `run_id`, pas de catégorie A/B/C/D. |
| `rbcm_parameter_value` | Huit codes, append-only, NULL ≠ zéro déjà refusé. Pas de `justificatif_ref` ni d’optimistic lock. |
| `rbcm_calculation_run` | Run du **moteur** (hors périmètre). Ne pas réutiliser pour les contrôles métier. |
| Mapping | 242 règles `A_VALIDER`, 0 `ACTIVE`. |
| DEV | SM `11/2026` `CALCULEE` `a9c8832b-…` ; SM `01/2026` ; paramètre `caisse_devises = 0.00 CALCULE` ; 2 issues SUMMARY. |

### 1.3 Permissions (catalogue inchangé)

| Rôle Login 2 | Permissions pertinentes |
|--------------|-------------------------|
| Lecteur | `view`, `export` |
| Préparateur | `prepare`, `import`, `parameters.write`, `confirm`, `correct`, `mapping.propose` |
| Contrôleur | `control`, `mapping.validate`, `confirm` |
| Approbateur | `approve`, `reopen` |
| Admin module | toutes les permissions `reporting-bcm-sm.*` |

`reporting_owner_id` n’était **pas** un garde API (bonne base). `POST /reconcile` était limité à `import` uniquement — trop étroit pour la collaboration.

### 1.4 Plan d’intégration retenu

1. Une table `rbcm_control_run` + colonnes sur `rbcm_reconcile_issue` (pas de JSONB unique, pas de table d’anomalies parallèle).
2. Snapshots **immuables** : une nouvelle exécution **insère**, jamais `DELETE` / `UPDATE` des issues d’un run précédent. La résolution se déduit du diff de `item_key`.
3. File « Informations à compléter » = dernier run + overlay live des paramètres (saisie après contrôle → « à recontrôler »).
4. Droits : permissions Login 2, **pas** le responsable. Optimistic lock `expected_value_id` sur les paramètres. Pas de verrou global de SM.
5. `engine/runner.py` non modifié.

---

## 2. Architecture retenue

```
Importer BAL DET (confirm)
        │
        ▼
run_sm_controls()  ── SELECT campaign FOR UPDATE
        │              INSERT rbcm_control_run (run_id, actor_id, previous_run_id)
        │              INSERT rbcm_reconcile_issue[]  (catégorie A/B/C/D)
        ▼
GET /controls/runs          historique chronologique
GET /controls/runs/{id}     rapport figé
GET /complements            file A/B/C/D + overlay live + actions autorisées
POST /parameters            saisie C (acteur réel, motif, justificatif_ref)
POST /controls/runs         relance (nouveau run, ancien conservé)
```

Résultat global d’un run (ordre) :

1. `BLOCKING` — anomalie fichier A bloquante  
2. `INCOMPLETE` — B ou C encore ouverts  
3. `DECISIONS_PENDING` — D non arbitrées  
4. `WARNINGS`  
5. `OK`

Decimal exclusivement. `display_amount(None)` reste `None` (jamais `0.00`).  
`caisse_devises = 0.00 CALCULE` est un **zéro réel saisi**, pas un manquant.

---

## 3. Migration

Fichier : `backend/alembic/versions/20261116_rbcm_03_control_runs.py`  
Révision : `20261116_rbcm_02` → `20261116_rbcm_03`

Opérations **additives** :

1. Table `rbcm_control_run` (`campaign_id`, `actor_id`, `result`, `previous_run_id`, `summary`, `created_at`).
2. Colonnes `run_id`, `category`, `item_key`, `title`, `resolution_state` sur `rbcm_reconcile_issue`.
3. Colonne `justificatif_ref` sur `rbcm_parameter_value`.
4. Backfill : un run par SM ayant déjà des issues ; les lignes existantes sont rattachées, **jamais supprimées**.

Appliquée en DEV (volume source monté sur le service `migrate`, pas un rebuild d’image) :

```
Running upgrade 20261116_rbcm_02 -> 20261116_rbcm_03
alembic_version = 20261116_rbcm_03
```

**Non fait :** `DELETE` métier, `docker compose down -v`, reset Git, rebuild/push des images, production.

---

## 4. Modèles

| Entité | Rôle |
|--------|------|
| `RbcmControlRun` | Exécution identifiable (`id` = `run_id`), chaînée via `previous_run_id`. |
| `RbcmReconcileIssue` | Snapshot d’un run : catégorie A/B/C/D, `item_key`, gravité, `resolution_state`, observé/attendu dans `details`. |
| `RbcmParameterValue.justificatif_ref` | Référence textuelle (GED métier non branchée — AGENTS.md). |

États de résolution persistés : `OPEN`, `IN_PROGRESS`, `RESOLVED`, `STILL_BLOCKING`, `PENDING_DECISION`, `OK`.  
L’état « saisie à recontrôler » est un **overlay live** (le snapshot du run précédent n’est pas muté).

---

## 5. API

| Méthode | Chemin | Permission | Rôle |
|---------|--------|------------|------|
| `POST` | `/campaigns/{id}/controls/runs` | `prepare` **ou** `control` **ou** `import` | Lancer / relancer (append-only) |
| `POST` | `/campaigns/{id}/reconcile` | idem | Alias conservé |
| `GET` | `/campaigns/{id}/controls/runs` | `view` | Liste chronologique |
| `GET` | `/campaigns/{id}/controls/runs/{run_id}` | `view` | Rapport historique |
| `GET` | `/campaigns/{id}/complements` | `view` | File A/B/C/D + actions réelles |
| `GET` | `/campaigns/{id}/reconcile` | `view` | Vue expert du **dernier** run |
| `GET` | `/campaigns/{id}/reconcile/issues` | `view` | Par défaut le dernier `run_id` (`all_runs=true` pour l’historique brut) |
| `POST` | `/campaigns/{id}/parameters` | `parameters.write` | Saisie C ; `expected_value_id` ; `justificatif_ref` |

Codes nouveaux :

| Code | Sens |
|------|------|
| `PARAM_CONFLICT` | 409 — autre préparateur a déjà enregistré une version plus récente |
| `CONTROL_RUN_NOT_FOUND` | 404 — rapport inexistant pour cette SM |

Audit : `rbcm.control.run` (acteur réel, `previous_run_id`) ; `rbcm.parameter.set` (avant / après, **pas** attribué au responsable).

`GET /progress` ajoute `last_control_run_id`, `last_control_result`, `last_control_at`, `complements_open`.

---

## 6. Classification A/B/C/D

### A — Calculable depuis la BAL DET

Soldes NCG, totaux D/C, classes 1–8, devises, lignes sans NCG, proposition `caisse_devises` (NCG 101* EUR, DEB−CRE).  
La proposition n’est **jamais** enregistrée automatiquement. Si le paramètre est déjà renseigné (y compris `0.00 CALCULE`), la proposition est `OK`.

### B — Autre source (D09)

Crédits, dépôts, maturités. Action unique : **Consulter**. Pas de répartition 70/30, pas de bouton « Joindre » fictif, pas de saisie inventée.

### C — Saisie manuelle

Les huit paramètres existants + un item FPN (annexes du canevas) en `CONSULTER` jusqu’à T3.5-3.  
Saisie : valeur (nullable), source, justification, `justificatif_ref`, utilisateur, date. NULL sans justification refusé. Pas de conversion NULL → 0.

### D — Décisions métier

D01 (242 `A_VALIDER`), D02 (ECART désactivé), D06 (non mappées), D16/D17 (résidence), D22 (multi-cellules).  
Toujours `PENDING_DECISION` (sauf D22 sans conflit → `OK` informatif). **Aucune** activation de règle, **aucun** ECART.

---

## 7. Interface fiche SM

Parcours 1–7 inchangé visuellement. **Fonctionnels dans ce lot : 2, 3, 4.**

| Étape | Comportement T3.5-2 |
|-------|---------------------|
| 1 Informations | Créateur / responsable (T3.5-1) |
| 2 BAL DET | Bouton Importer si DET absente |
| 3 Contrôles | Historique des runs + Consulter un ancien rapport |
| 4 Informations à compléter | File A/B/C/D, actions contextuelles uniquement |
| 5–7 | Marquées « Plus tard — D01/D02 », sans bouton fictif de préparation / validation |

Actions affichées seulement si le backend les autorise : Consulter, Saisir, Relancer, Importer.  
Pas de « Joindre un justificatif » (GED non branchée) : le champ référence est dans le formulaire de saisie C.

Guidage : après DET + au moins un run, l’étape courante est **4** même si le statut technique est `CALCULEE` (la préparation T3.5-3 n’est pas ouverte).

---

## 8. Collaboration multi-utilisateurs

Décisions retenues :

| Sujet | Choix |
|-------|--------|
| Qui prépare | Tout utilisateur Login 2 avec la permission adéquate, **pas** seulement `reporting_owner_id` |
| Contrôles | `prepare` ∪ `control` ∪ `import` (préparateur **et** contrôleur) |
| Saisie C | `parameters.write` (préparateur / admin) — le contrôleur du catalogue n’a pas cette permission |
| Traçabilité | `actor_id` du run ; `authored_by_id` de la saisie ; audit avant/après |
| Concurrence contrôles | `SELECT … FOR UPDATE` sur la SM : sérialisation, pas d’écrasement, `previous_run_id` chaîné |
| Concurrence paramètres | `expected_value_id` → 409 `PARAM_CONFLICT` ; pas de lock global |
| SoD validation finale | **Non tranchée** — reportée à T3.5-5 |
| Catalogue | **Non modifié** (pas de droit magique Login 1) |

Matrice :

| Action | Lecteur | Préparateur | Contrôleur | Approbateur |
|--------|---------|-------------|------------|-------------|
| Consulter SM / file / rapports | oui | oui | oui | oui |
| Importer DET | non | oui | non | non |
| Lancer / relancer contrôles | non | oui | oui | non |
| Saisir / corriger paramètre C | non | oui | non | non |
| Valider un paramètre (SoD auteur) | non | non | oui | non |
| Approuver la SM | non | non | non | oui (T3.5-5) |

---

## 9. Conservation des historiques

- Une exécution = un `run_id`.  
- Relance = nouveau run + `previous_run_id`.  
- `resolved_since_previous` / `new_since_previous` / `still_open` dans `summary`.  
- Une anomalie `PARAM_MISSING` du run N reste visible dans `GET …/runs/{id}` après saisie et run N+1 (`PARAM_FILLED`).  
- Les issues SUMMARY T3.4 sont backfillées en catégorie A / état OK, non détruites.

---

## 10. Tests et résultats

```
backend/tests/test_reporting_bcm_sm.py
backend/tests/test_reporting_bcm_sm_t35_1.py
backend/tests/test_reporting_bcm_sm_t35_2.py
58 passed in 3.91s
```

| # | Cas | Résultat |
|---|-----|----------|
| 1 | Exécution avec `run_id` (modèle + service) | OK |
| 2 | Deux rapports successifs (`previous_run_id`, diff de clés) | OK |
| 3 | Consultation d’un run par id (API 404 si absent) | OK |
| 4 | Classification A/B/C/D | OK |
| 5 | Information manquante (8 params + B D09 + FPN) | OK |
| 6 | Saisie paramètre C (acteur, justificatif_ref) | OK |
| 7 | Historique append-only des valeurs | OK (modèle existant + nouveau champ) |
| 8 | NULL non converti en zéro (`display_amount`, refus sans motif) | OK |
| 9 | Décision D reste `PENDING_DECISION` | OK |
| 10 | 242 A_VALIDER : lecture seule, pas d’`UPDATE` mapping / moteur | OK |
| 11 | Overlay « saisie à recontrôler » sans muter l’ancien snapshot | OK |
| 12 | Source : plus de `DELETE` des issues dans le workflow | OK |
| 13 | Lecteur : CONSULTER seulement ; contrôles = prepare/control/import | OK |
| 14 | Concurrence : `FOR UPDATE` + `PARAM_CONFLICT` | OK (inspection + 409) |
| 15 | SM 11/2026 conservée (SQL DEV ci-dessous) | OK |

Frontend : `ng build --configuration=production` **exit 0**.  
Avertissement budget CSS `rbcm-ui` 8,35 ko / 8 ko (identique T3.5-1, pas aggravé par ce lot).

---

## 11. Vérification des données DEV

Avant / après `rbcm_03` :

| Objet | Avant | Après |
|-------|-------|-------|
| Alembic | `20261116_rbcm_02` | `20261116_rbcm_03` |
| SM `11/2026` `a9c8832b-…` | `CALCULEE`, owner `6b99bb89-…` | inchangée |
| SM `01/2026` `57b77c73-…` | `CALCULEE` | inchangée |
| Imports 11/2026 | 2 | 2 |
| Issues | 2 | 2 (rattachées, catégorie A, OK) |
| `rbcm_control_run` | — | 2 (backfill, `previous_run_id` NULL) |
| `caisse_devises` | `0.00 CALCULE` | inchangé (`justificatif_ref` NULL) |
| Mapping | 242 `A_VALIDER` | 242 `A_VALIDER` |

Aucune ligne d’import, de calcul ou de mapping n’a été modifiée.

---

## 12. Limites connues

1. L’image Docker `bea-digital-backend` **n’a pas été reconstruite** (consigne aucun déploiement). La migration est en base ; le conteneur en cours sert encore le code T3.5-1 jusqu’à un rebuild local volontaire.
2. Justificatif = référence texte. Pas d’upload GED (socle « à brancher »).
3. Items B restent ouverts tant que D09 n’a pas de source : c’est volontaire.
4. FPN : un item C consultable, pas de saisie cellule (T3.5-3).
5. `IN_PROGRESS` n’est pas écrit en base ; l’overlay live couvre « saisie à recontrôler ».
6. `expected_value_id` est optionnel pour ne pas casser un client qui n’envoie pas encore le jeton ; le front fiche + paramètres l’envoie.
7. Le rapprochement DET/COND legacy retourne désormais un diagnostic sans écrire d’issues (hors workflow).
8. Pas de Playwright Login 2 dans ce lot.

---

## 13. Points restant à arbitrer

1. **SoD T3.5-5** : un préparateur ayant saisi ou corrigé une SM peut-il ensuite l’approuver ? À définir et tester avant validation finale.
2. Le **contrôleur** du catalogue n’a pas `parameters.write`. Faut-il l’ajouter, ou la saisie reste-t-elle aux préparateurs ?
3. Source D09 (crédits / dépôts / maturités) : format et responsable d’import — T3.5-3+.
4. FPN : saisie dans le canevas WORK ou formulaire dédié ?
5. GED : joindre un vrai document vs référence libre.

---

## 14. Fichiers touchés

**Backend**

- `backend/app/models/reporting_bcm_sm.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/reporting_bcm_sm.py`
- `backend/app/services/reporting_bcm_sm/constants.py`
- `backend/app/services/reporting_bcm_sm/control_service.py` *(nouveau)*
- `backend/app/services/reporting_bcm_sm/import_service.py`
- `backend/app/services/reporting_bcm_sm/parameter_service.py`
- `backend/app/services/reporting_bcm_sm/campaign_service.py`
- `backend/app/api/v1/endpoints/reporting_bcm_sm.py`
- `backend/alembic/versions/20261116_rbcm_03_control_runs.py`
- `backend/tests/test_reporting_bcm_sm_t35_2.py`

**Frontend**

- `frontend/angular20/src/app/reporting-bcm-sm/rbcm.models.ts`
- `frontend/angular20/src/app/reporting-bcm-sm/pages/rbcm-campagne-detail.component.ts`
- `frontend/angular20/src/app/reporting-bcm-sm/pages/rbcm-parametres.component.ts`
- `frontend/angular20/src/app/reporting-bcm-sm/rbcm-nav.spec.ts`

**Docs**

- `docs/comptabilite/reporting-bcm-sm/T3_5_2_REPORT.md` (ce fichier)
- `docs/comptabilite/reporting-bcm-sm/README.md`

Non modifiés : `engine/runner.py`, mapping seed, ECART, workflow d’approbation, export canevas.

---

## 15. État Git

- Branche dirty `feat/reporting-bcm-sm-t3`
- HEAD `091b57c`
- **Pas de commit, pas de push**
- Production v1.0.0 hors périmètre
- **T3.5-3 non commencé** — attendre validation explicite de T3.5-2
