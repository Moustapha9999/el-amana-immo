# T3.5-3-C — Rapport de livraison

Graphe Decimal documentaire + génération WORK.  
**DEV Docker local uniquement.** Pas de phase D/E/F. Pas de commit.

Date : 16/11/2026.  
Autorisation : écrite, ce lot, après revue B `VALIDABLE SOUS RÉSERVE` et convention **`C:STRUCT:F44/F46/F48`**.

**Verdict : livrable C accepté sur DEV** (charte modèle §15.2).  
T3.5-3-D **n’est pas autorisée** par ce rapport.

---

## 1. Branche et HEAD

| Élément | Valeur |
|---------|--------|
| Branche | `feat/reporting-bcm-sm-t3` |
| HEAD | `091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32` (`091b57c`) |
| Checkout / reset / commit | **aucun** |

---

## 2. Environnement

Inchangé vs B : `bea-postgres` `127.0.0.1:5432` / `172.18.0.2`, base **`bea_digital`**, Alembic **`20261116_rbcm_05`**.  
**Aucune migration C.** Production non contactée.

`upload_root` : `/app/storage/uploads` (montage `storage/uploads`).

---

## 3. Convention de clés (R-B1) et contrat

Intégré avant le graphe, comme exigé par l’autorisation.

| Avant (anomalie B) | Après C |
|--------------------|---------|
| `C:HDR:F44/F46/F48` (SUM structurels, pas HEADER) | **`C:STRUCT:F44/F46/F48`** |
| HEADER A1/A2/B2/B3/A3 | **`A\|B\|C:HDR:`** inchangé |

- Seed `_document_key` : A/B/C sans code BCM → `:STRUCT:` ; nature `HEADER` → `:HDR:`.
- Patch idempotent `apply_struct_key_convention` : `UPDATE` des lignes `nature <> HEADER` encore en `:HDR:`.
- Live DEV : 3 clés STRUCT présentes, 0 `C:HDR:F44`.
- Contrat : `T3_5_3_A_MODELE_DOCUMENTAIRE.md` §2.2 + `T3_5_3_A_DECISIONS` R5.

Pas de nouvelle table. Pas de changement SHA du canevas. Pas de re-seed complet.

---

## 4. Graphe Decimal

Fichiers : `document_graph.py`, `formula_parser.py`, `document_keys.py`.

- Parseur : `SUM`, `IF`, `+ - * /`, `%`, comparaisons, refs `'Feuille'!A1`. **663/663** formules officielles parsées.
- `Decimal` uniquement. Référence vide → **NULL**, jamais 0.
- `OCTOBER_CONSTANT_FORMULA` / `OCTOBER_LEAF` : formule officielle **conservée en métadonnée**, **non évaluée** (WORK les vide).
- Statuts : `NON_RENSEIGNE`, `FORMULE_PARTIELLE`, `FORMULE_NON_INTERPRETABLE`, `CONTROLE_NON_INTERPRETABLE`, `PROVISOIRE_D09`, `NORME_CANEVAS`, `FORMULE_COMPLETE`.
- Portes D01/D02/D06/D09/D15/D16-D17/D22 **ouvertes** (O1). `runner.py` **non importé**.

Exemples mesurés (tests unitaires) :

| DOC | Cellule | Résultat |
|-----|---------|----------|
| 11 | `A:102:H` (D9 vide, F9=100) | `FORMULE_PARTIELLE`, value `None` |
| 12 | `FPN:C36` | `FORMULE_NON_INTERPRETABLE` |
| 13 | L11 / I8 | `CONTROLE_NON_INTERPRETABLE` |
| 14 | H28, C26, C16 | `FORMULE_NON_INTERPRETABLE` |
| 22 | `B:207:E` 30 % | `PROVISOIRE_D09` |
| 35 | `RCR:H31` | nature `CANVAS_SCALE_FORMULA`, `FORMULE_NON_INTERPRETABLE` |

---

## 5. Génération WORK

Fichier : `work_fill.py`.

- Verrou `pg_advisory_xact_lock('rbcm-work-gen:{campaign_id}')`.
- `document_seq = max+1`. Concurrent : n puis n+1, **pas 409**.
- Un seul `WORK` : l’ancien passe `SUPERSEDED` **avant** l’INSERT du nouveau.
- Copie du template persistant (SHA contrôlé), **pas** le xlsx git, **pas** `excel_export`.
- Feuille **`AVERTISSEMENT`** en 1re position. Header/footer banner. **Aucune** insertion de ligne sur les 8 feuilles.
- Neutralisation `OCTOBER_LEAF` + 9 `OCTOBER_CONSTANT_FORMULA`.
- Conservation formules structurelles, D09 30/70 %, I147, H31, INFO C9.
- B2/B3 = arrêté / banque (overlay de génération).
- Overlay décisions si `decision_allowed` (aucune API F).
- Path `{upload_root}/reporting-bcm-sm/{campaign_id}/work/`.
- `run_id` NULL. `campaign.template_version_id` posé à la **1re** WORK (tests : banque jetable `T353C` seulement).
- Échec IO : `STORAGE_UNAVAILABLE`, rollback, ancien WORK intact, nouveau fichier non référencé supprimé.

---

## 6. Conservation T3.5-1/2

| Objet | Après C |
|-------|---------|
| Alembic | `20261116_rbcm_05` (pas de rbcm_06) |
| SM BEA 01/2026 et 11/2026 | 2, `CALCULEE`, `template_version_id` **NULL** |
| Mapping | **242** `A_VALIDER`, **0** `ACTIVE` |
| `rbcm_control_run` | 2 |
| `rbcm_cell_result` | 92 |
| Livrables BEA | **0** |
| Campagnes `T353C` | **0** (nettoyées) |
| `runner.py` | non importé, non modifié |

---

## 7. Tests DOC exécutés (phase C)

Fichier : `backend/tests/test_reporting_bcm_sm_t35_3_c.py`  
**5 passed** (pytest Docker, overlay `backend:/app` + `storage/uploads`).

| ID | Couverture | Résultat |
|----|------------|----------|
| R-B1 STRUCT | inventaire + SQL `C:STRUCT:F44` | OK |
| Parseur 663 | toutes les formules officielles | OK |
| DOC-11, 12, 13, 14, 22, 35 | graphe unitaire | OK |
| DOC-01 | littéraux octobre absents du WORK | OK |
| DOC-08 | 2 générations concurrentes, seq 1 et 2, un WORK | OK |
| DOC-24 | E7/E17/E20/E25 vidés | OK |
| DOC-25 | INFO C6/C8/C10/C20 vides ; C9 formule | OK |
| DOC-26 | `AVERTISSEMENT` 1re feuille ; D9 reste D9 | OK |
| DOC-34 | I147 formule `=+H147-H81` | OK |
| DOC-28 / 32 | 2ᵉ génération `STORAGE_UNAVAILABLE` ; 1er fichier + SHA intacts | OK |

Jeux : banque **`T353C` / 2099**, jamais SM BEA.

---

## 8. Tests non exécutés

| ID | Raison |
|----|--------|
| DOC-23 (G / 0,1 / 0,2 dans le xlsx WORK) | Non asserté fichier par fichier ; formules/normes non vidées par le fill |
| DOC-10, 15, 16, 18, 19 | D ou hors C |
| DOC-05, 07, 17, 20, 21, 27 | F (API décisions) |
| API GET / download | Phase D |

`bea_digital_test` : toujours sans `rbcm_*` (D6).

---

## 9. Risques et réserves

| Point | Traitement |
|-------|------------|
| O1 portes | toujours ouvertes |
| Header/footer openpyxl | banner surtout dans la feuille `AVERTISSEMENT` ; API header Excel variable selon openpyxl |
| Graphe vs Excel affiché | Excel peut montrer 0/TRUE ; vérité = graphe + AVERTISSEMENT |
| Pas d’API | génération via service uniquement (D) |
| `extra` JSONB | inchangé vs B |
| Restauration dump B | toujours non rejouée |

---

## 10. Fichiers créés ou modifiés (ce lot)

Créés :

- `backend/app/services/reporting_bcm_sm/document_keys.py`
- `backend/app/services/reporting_bcm_sm/formula_parser.py`
- `backend/app/services/reporting_bcm_sm/document_graph.py`
- `backend/app/services/reporting_bcm_sm/work_fill.py`
- `backend/tests/test_reporting_bcm_sm_t35_3_c.py`
- `docs/comptabilite/reporting-bcm-sm/T3_5_3_C_REPORT.md`

Modifiés :

- `backend/app/services/reporting_bcm_sm/template_seed.py` (STRUCT + patch idempotent)
- `docs/comptabilite/reporting-bcm-sm/T3_5_3_A_MODELE_DOCUMENTAIRE.md` §2.2
- `docs/comptabilite/reporting-bcm-sm/T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md` R5
- `docs/comptabilite/reporting-bcm-sm/README.md`
- `docs/comptabilite/reporting-bcm-sm/T3_PHASE_STATUS.md`

Non modifiés : `engine/runner.py`, `excel_export.py`, mapping, SM BEA, Excel officiel, rapports B historiques.

---

## 11. Commit / push

**Aucun commit. Aucun push. Aucun déploiement.**

---

## Arrêt

- Pas d’API documentaire (D)
- Pas d’UI (E)
- Pas d’API décisions (F)
- Pas d’activation mapping
- Portes métier ouvertes
- Production intacte

**STOP. Attendre l’examen utilisateur avant T3.5-3-D.**
