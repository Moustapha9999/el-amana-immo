# T3.5-3-A — Rapport de révision documentaire

**Documentation uniquement.** Aucun code, aucune base mutée, aucune migration, aucun Excel.

Date : 16/11/2026.  
Branche : `feat/reporting-bcm-sm-t3` · HEAD : `091b57c` (inchangé).

Cette révision **n’est pas** une validation Comptabilité / DSI de la Situation Mensuelle.

---

## 1. Fichiers modifiés / créés

| Fichier | Action |
|---------|--------|
| `T3_5_3_A_AUDIT_ETAT_REEL.md` | Addendum §10 ; Q11/Q12 ; fin §3.3 |
| `T3_5_3_A_MODELE_DOCUMENTAIRE.md` | Réécriture consolidée (six corrections + R/Q + phases A–F) |
| `T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md` | R1–R15 acceptés, Q1–Q12, points encore ouverts |
| `T3_5_3_A_REVISION_DOCUMENTAIRE.md` | **Créé** (ce rapport) |
| `README.md` | Statut chantier + index |
| `T3_PHASE_STATUS.md` | Alembic DEV réel ; T3.5-3-A/B |

Addendum D1–D9 : voir §11. Fichiers du lot suivant listés dans `T3_5_3_A_LEVEE_RESERVES_D1_D9.md`.

Non modifiés : Python, TypeScript, SQL, Excel, `engine/runner.py`, T3.5-1/2 code, SM 11/2026 et 01/2026, `_t353_t0_scratch/` (aucune suppression).

---

## 2. Décisions R1–R15 intégrées

Toutes **acceptées** comme arbitrages de conception. Précisions :

- **R5** : regex par famille de clés (A/B/C vs FPN/RCR/LIQ/FPAI/INFO).
- **R9** : `UNIQUE(campaign_id, document_seq)` **et** unique partiel un seul `status=WORK` — deux unicités distinctes.

Détail : `T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md` §1.

---

## 3. Six corrections techniques

### 4.1 Saisissabilité D9

`writable` reste `false` sur `OCTOBER_CONSTANT_FORMULA` (canevas officiel).  
`decision_allowed = writable OR nature = OCTOBER_CONSTANT_FORMULA`.  
WORK : D9 **vidée** (plus `=588160767-F9`). Décision manuelle autorisée. Source dépôt intacte.

### 4.2 FK

`decided_by_id` **nullable** + `ON DELETE SET NULL` (compatible).  
`supersedes_decision_id`, `template_cell_id`, `superseded_by_id` : **RESTRICT**. Pas de DELETE applicatif des décisions.

### 4.3 Changement de canevas

Décision collée à `template_cell_id` d’origine. Jointure future par `document_cell_key` seulement si la clé existe et reste `decision_allowed` sur T2. Sinon blocage. Pas de transfert UUID silencieux. Chaque WORK garde son `template_id`.

### 4.4 Concurrence

`expected_current_id` (y compris `null`) vérifié **après** lock. Premier POST 201, second `null` → 409.  
Génération WORK sérialisée par lock ; seq unique ; un seul courant ; rollback si échec.

### 4.5 Stockage template

Source dépôt en lecture seule. Copie `{upload_root}/reporting-bcm-sm/templates/{id}/`.  
`upload_dir` par défaut **déclaré** `storage/uploads` dans `app.core.config` ; chemin **résolu** à inspecter en T3.5-3-B (O3). Pas `backend/app/data/…`.

### 4.6 Graphe Decimal

SUM / + / − / × / ÷ / IF / refs inter-feuilles. Vide = NULL. Division par 0 → non calculable. Formule dépendant d’une formule partielle ≠ complète. Portes Dxx prioritaires. Cache Excel ignoré.

---

## 4. Réponses Q1–Q12

Intégrées (décisions §2). Rappel Q2 : saisie INFO/FPN **ne ferme pas** les portes.  
Q11 : README et `T3_PHASE_STATUS.md` mis à jour **après** relecture Alembic.  
Q12 : voir §6.

---

## 5. Points encore ouverts

O1 portes Dxx · O2 inventaire nominatif INFO/FPN · O3 chemin résolu `upload_root` · O4 autorisation T3.5-3-B · O5 sort du scratch · O6 DSI-PDF/SRV.

---

## 6. `_t353_t0_scratch/` (Q12)

- L’audit initial le décrivait comme dumps openpyxl T0 (JSON de feuilles, `formulas.json`, cartographie, `sha256.txt`, extraits txt).
- À cette révision : un glob d’index listait encore ~20 fichiers ; le listage filesystem du chemin `docs/comptabilite/reporting-bcm-sm/_t353_t0_scratch` **n’a pas trouvé** le répertoire.
- Statut : **reliquat temporaire T0**, redondant avec `T3_5_3_T0_AUDIT.md` / `T3_5_3_T0_COMPLEMENT.md`. **Pas une source de vérité.**
- **Aucune suppression** effectuée. Toute suppression exigera une autorisation distincte (O5).

---

## 7. Vérifications

| Contrôle | Résultat | Mutation |
|----------|----------|----------|
| `git rev-parse HEAD` | `091b57c` | non |
| `alembic_version` `bea_digital` | `20261116_rbcm_04` | `SELECT` seul |
| `alembic_version` `bea_digital_test` | `20261105_mg_stock_mvt_ref_uq` | `SELECT` seul |
| Production | non interrogée | — |
| pytest / seed / WORK / Docker rebuild | non lancés | — |

---

## 8. Git avant / après

**Avant et après :** branche `feat/reporting-bcm-sm-t3`, HEAD `091b57c`, working tree dirty T3.5-1/2 **préservé**.

Après : uniquement des Markdown sous `docs/comptabilite/reporting-bcm-sm/`.

---

## 9. Découpage

T3.5-3-A = conception. Plus de « A code ».  
T3.5-3-B = `rbcm_05` + seed — **interdit** tant que O4 n’est pas tranché.

---

## 10. Confirmation (révision initiale)

Aucun fichier Python / TypeScript / HTML / SCSS / SQL modifié.  
Aucune migration créée ou appliquée.  
Aucune donnée PostgreSQL écrite.  
Aucun Excel modifié.  
Aucun WORK généré.  
Aucun commit / push / reset / checkout / rebuild.

---

## 11. Addendum — levée D1–D9 (16/11/2026)

Lot documentaire distinct. Détail : `T3_5_3_A_LEVEE_RESERVES_D1_D9.md`.

| Réserve | Intégration |
|---------|-------------|
| D1 | modèle §7 — `template_id` / `document_seq` nullable, UNIQUE partiel |
| D2 | modèle §2.2 — `A:CTRL:I147` |
| D3 | modèle §4.1 — `CANVAS_SCALE_FORMULA` |
| D4 | modèle §12 — inventaire + idempotence |
| D5 | modèle §8 — chemins UUID, refus `..` |
| D6 | modèle §12.2 — `bea_digital_test` non prête |
| D7 | modèle §13 — `DOC-01`…`DOC-36` |
| D8 | modèle §7.3–7.4 — 409 ≠ WORK seq+1 |
| D9 | modèle §15.1 — charte B (n’autorise pas B) |

T0 inchangé (constats historiques). `T3_5_3_A_REVUE_FINALE.md` conserve le verdict `VALIDABLE SOUS RÉSERVE` ; la levée est un lot suivant.
