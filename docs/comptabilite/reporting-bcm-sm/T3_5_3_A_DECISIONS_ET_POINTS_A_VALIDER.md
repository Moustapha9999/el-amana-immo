# T3.5-3-A — Arbitrages (révision consolidée)

À lire avec `T3_5_3_A_MODELE_DOCUMENTAIRE.md`, `T3_5_3_A_REVISION_DOCUMENTAIRE.md` et `T3_5_3_A_LEVEE_RESERVES_D1_D9.md`.

Les R1–R15, Q1–Q12 et D1–D9 ci-dessous sont des **arbitrages de conception**. Ils **ne valent pas** visa Comptabilité / DSI sur une SM, ni autorisation d’implémenter T3.5-3-B.

T3.5-3-B **non commencé**.

---

## 1. Décisions R1–R15 — acceptées

| # | Décision | Précision technique intégrée |
|---|---------|------------------------------|
| **R1** | `rbcm_document_decision` dédiée | Hors `rbcm_cell_decision` |
| **R2** | Interdiction d’utiliser `rbcm_cell_result` pour une cellule Excel | Défense API : pas d’INSERT `A:…` dans `cell_ref` moteur |
| **R3** | `rbcm_cell_decision` réservé au moteur | Reste vide en T3.5-3 |
| **R4** | `rbcm_template` + `rbcm_template_cell` | SHA unique ; FK campagne à la 1re WORK |
| **R5** | Clés A/B/C/FPN/RCR/LIQ/FPAI/INFO + `A:CTRL:I147` | Regex **par type** ; axe A = C–H ; contrôle I147 = `^A:CTRL:I147$` ; jamais `A:427:I` ; HEADER `^(A\|B\|C):HDR:…` ; formules sans code BCM `^(A\|B\|C):STRUCT:…` (`C:STRUCT:F44/F46/F48`) |
| **R6** | Portée **campagne** des décisions | Overlay sur chaque WORK ; pas liées à un seul fichier |
| **R7** | WORK distinct de `GENERATED` | Statuts `WORK` / `SUPERSEDED` / `GENERATED` ; pas de `VALIDATED` |
| **R8** | Fichiers immuables, chemins distincts | `templates/` ≠ `work/` ≠ `exports/` ; pas `excel_export` |
| **R9** | Un seul WORK courant | **et** unique **partiel** `(campaign_id, document_seq) WHERE document_seq IS NOT NULL` — `GENERATED` sans seq (D1) |
| **R10** | Statuts dérivés du graphe Decimal | Jamais le cache Excel ; propagation des formules partielles |
| **R11** | `CONTROLE_NON_INTERPRETABLE` | TRUE Excel + sources vides ≠ OK |
| **R12** | 30 % et 70 % conservés | Badge `PROVISOIRE_D09` |
| **R13** | Feuille `AVERTISSEMENT` + header/footer | **Aucune** insertion de ligne |
| **R14** | Aucun fill `A_VALIDER` / `ACTIVE` | Runner non invoqué |
| **R15** | Migration additive après `rbcm_04` | Lot **T3.5-3-B**, pas A |

---

## 2. Réponses Q1–Q12

| ID | Réponse retenue |
|----|-----------------|
| **Q1** | Aucun fill des 242 règles `A_VALIDER`. |
| **Q2** | Saisie : `INFO:C6`–`C8` et `INFO:C10`–`C20` (`OCTOBER_LEAF`). `INFO:C9` = formule `='ETAT A'!D146` **conservée**, non saisissable. File C T3.5-2 **inchangée**. Ces saisies **ne ferment aucune** porte. |
| **Q3** | 30 % et 70 % restent dans le xlsx, statut D09 provisoire. |
| **Q4** | Motif obligatoire pour **toutes** les décisions (y compris `ZERO_CONFIRME`). `justificatif_ref` obligatoire pour `ZERO_MANUEL` et `VALEUR_DECIDEE`. |
| **Q5** | Montants partiels affichés **grisés + statut**, jamais comme montants complets, jamais `0,00` nu. |
| **Q6** | Copie persistante sous `{upload_root}/reporting-bcm-sm/templates/{id}/`. Inspection du chemin **résolu** = **1ʳᵉ tâche de B** (O3). Chemins calculés, refus `..` (D5). Pas `backend/app/data/…`. |
| **Q7** | UPDATE `status=SUPERSEDED` autorisé ; binaire, SHA, path **intacts**. |
| **Q8** | `expected_current_id` **sur les décisions uniquement** ; 201 puis 409. Générations WORK concurrentes : seq+1, **pas** 409 (D8). |
| **Q9** | `campaign.template_version_id` posé à la **première** génération WORK. |
| **Q10** | Export technique conservé, libellé **« Export moteur (technique) »**, jamais Situation Mensuelle officielle. |
| **Q11** | README et `T3_PHASE_STATUS.md` **corrigés dans cette révision** après relecture `alembic_version`. |
| **Q12** | `_t353_t0_scratch/` inspecté ; **non supprimé**. Voir rapport de révision. |

---

## 3. Six corrections techniques — statut

| # | Sujet | Statut conception |
|---|--------|-------------------|
| 4.1 | D9 / `OCTOBER_CONSTANT_FORMULA` saisissable via `decision_allowed`, sans muter `writable` | **Intégré** au modèle §4.2 |
| 4.2 | FK : `decided_by_id` nullable + SET NULL ; historiques RESTRICT | **Intégré** §5.1 |
| 4.3 | Changement de canevas sans transfert silencieux | **Intégré** §6 |
| 4.4 | `expected_current_id` (décisions) + lock WORK seq+1 + UNIQUE partiel | **Intégré** §5.3, §7.2–7.4 (D8) |
| 4.5 | Template sous `upload_root`, pas dans l’image | **Intégré** §8 |
| 4.6 | Contrat graphe Decimal + propagation | **Intégré** §9.1 |

---

## 4. Alternatives écartées (inchangées, plus 4.5)

| Alternative | Pourquoi |
|-------------|---------|
| `CellResult` avec `A:102:D` | Mélange sémantique |
| Namespace sur `cell_decision` | Contrat moteur `BCM:` |
| Décision liée au seul `deliverable_id` | Perdue à la régénération |
| `current_work_deliverable_id` sur la campagne | Désync |
| Insert row d’avertissement | Casse les formules |
| Réécrire `IFERROR` / `ISBLANK` | Masque le faux zéro |
| Fill 242 `A_VALIDER` | D01 |
| Fichier unique `BCM_SM_YYYYMM_vN.xlsx` | Écrasement |
| `backend/app/data/…` comme copie définitive | Perdu au rebuild |
| Muter `writable` du template pour D9 | Contredit le canevas officiel |
| `decided_by_id NOT NULL` + `ON DELETE SET NULL` | Incompatible SQL |
| Recopier auto `template_cell_id` vers un nouveau canevas | Perte / équivalence non prouvée |
| Statut `VALIDATED` dans rbcm_05 | Hors périmètre |
| `UNIQUE(campaign_id, document_seq)` sans `WHERE` | Casse les `GENERATED` NULL (D1) |
| Clé `A:427:I` pour I147 | Colonne I n’est pas un axe A (D2) |
| `RCR:H31` en `CANVAS_NORM` ou `RATIO_DIV` | Formule ×10, nature `CANVAS_SCALE_FORMULA` (D3) |
| 409 sur la 2ᵉ génération WORK | Confusion avec les décisions (D8) |
| Feuille `AVERTISSEMENT` dans le seed | Appartient au WORK, pas au canevas (D4) |

---

## 5. Décisions D1–D9 — acceptées (levée des réserves)

| ID | Décision figée |
|----|----------------|
| **D1** | `template_id` et `document_seq` **nullable**. `GENERATED` sans seq ni template. UNIQUE partiel `WHERE document_seq IS NOT NULL`. `excel_export` intact. |
| **D2** | Contrôle `ETAT A!I147` → clé **`A:CTRL:I147`**, formule `=+H147-H81` conservée. |
| **D3** | `RCR:H31` → `CANVAS_SCALE_FORMULA` (`C39*10`). Idem `LIQ:D20`, `FPN:F33` (T0). |
| **D4** | Seed fichier-driven, 663 formules, 9 constantes, INFO, E7:E25, I147, H31 ; pas d’AVERTISSEMENT ; **idempotent** sur SHA. |
| **D5** | Chemins calculés sous `upload_root` + UUID ; refus `..` ; erreurs SHA/path/stockage nommées. |
| **D6** | `bea_digital` : rbcm_05 après inspection `rbcm_04`. `bea_digital_test` : **pas prête** ; préparation via test-db, jamais upgrade improvisé. |
| **D7** | Tests stables `DOC-01`…`DOC-36` ; T0-19–34 réintégrés (E7:E25, INFO, 403, 400). |
| **D8** | Décisions : 201/409. WORK : seq+1, un courant, rollback, pas de 409 systématique. |
| **D9** | Charte B au modèle §15.1. **Cette fiche n’autorise pas B.** |

---

## 6. Points encore ouverts

**Pas des propositions déguisées en décisions métier.**

| ID | Qui | Sujet |
|----|-----|--------|
| O1 | Comptabilité | Portes D01, D02, D06, D09, D15, D16/D17, D22 — **inchangées** |
| O2 | Comptabilité | Inventaire INFO **figé pour le seed** (C6–C8, C10–C20 saisissables ; C9 formule). Toute **autre** cellule FPN saisissable non listée par T0 reste hors seed. |
| O3 | DSI / implémentation B | Chemin **résolu** de `upload_root` — 1ʳᵉ tâche de B |
| O4 | Product owner | Autorisation **écrite** de démarrer T3.5-3-B — **non donnée** |
| O5 | Docs | Suppression éventuelle de `_t353_t0_scratch/` — **interdit** tant que O5 n’est pas tranché |
| O6 | DSI-PDF / DSI-SRV | Hors T3.5-3 |

La conception T3.5-3-A (D1–D9 inclus) est **cohérente pour revue** ; elle n’est **pas** « validée SM » et **B n’est pas autorisée**.

---

## 7. Découpage — T3.5-3-B interdit ici

| Phase | Périmètre |
|-------|-----------|
| **T3.5-3-A** | Conception (audit + modèle + levée D1–D9) |
| **T3.5-3-B** | `rbcm_05`, modèles, copie template, seed — charte modèle §15.1 |
| **T3.5-3-C** | Service génération WORK + graphe |
| **T3.5-3-D** | API GET / générer / télécharger |
| **T3.5-3-E** | UI documentaire |
| **T3.5-3-F** | Décisions, corrections, régénération |

Il n’existe plus de « T3.5-3-A code ».

Critères pour **autoriser B** (décision utilisateur distincte) :

- modèle §7 (D1), §2.2 (D2), §4.1 (D3), §12 (D4/D6), §8 (D5), §13 (D7), §7.3–7.4 (D8), §15.1 (D9) non contestés ;
- O3 inspecté **au démarrage** de B, pas comme préalable d’autorisation documentaire ;
- aucun fill mapping, aucun runner, aucun Excel source.

Tests : modèle §13 (`DOC-*`) — à coder avec B–F, **pas maintenant**.
