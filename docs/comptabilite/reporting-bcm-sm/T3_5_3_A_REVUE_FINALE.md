# T3.5-3-A — Revue finale contradictoire (avant décision d’autorisation B)

Revue **documentaire uniquement**. Aucun code, aucune migration, aucun seed, aucun Excel.  
**T3.5-3-B n’est pas autorisée par ce document.** Seul l’utilisateur peut l’autoriser.

Date : 16/11/2026.

**Verdict : `VALIDABLE SOUS RÉSERVE`**

La conception est globalement cohérente (clés, D9, FK, portes, pas de fill `A_VALIDER`). Elle **ne suffit pas encore** à figer le DDL `rbcm_05` et le seed sans quelques précisions, sans quoi B improviserait des colonnes et un inventaire de cellules.

---

## 1. Résumé exécutif

Les six corrections 4.1–4.6 et les arbitrages R1–R15 / Q1–Q12 sont **présents et alignés** entre le modèle révisé et le document d’arbitrages. Les règles métier (NULL ≠ 0, WORK ≠ validé, D09 provisoire) tiennent.

Trois familles de réserves **bloquent une autorisation B « sans improvisation »** :

1. **DDL livrable** : `template_id` et `document_seq` ne précisent pas la coexistence avec les lignes `GENERATED` de `excel_export` (même table).
2. **Seed** : regex `A:{code}:{C-H}` **oublie** le contrôle `ETAT A!I147` ; natures `H31` (`*10`), HEADER B2/B3 (écriture génération vs `writable=false`), périmètre exact des lignes `template_cell`, idempotence du seed, `bea_digital_test`.
3. **Numérotation des tests** : le complément T0 a les critères **19–34** ; le modèle les a **renumérotés 1–23**. Pas de table de correspondance. Des cas (INFO C6–C20, E couverture, motif 400) ont disparu de la liste modèle.

Le cœur (séparation `BCM:102` / `A:102:D`, `decision_allowed` sans muter `writable`, 409 **sur les décisions** et non sur la 2ᵉ génération WORK) est **correct** et ne doit pas être dénaturé.

---

## 2. État Git et fichiers examinés

```
branche : feat/reporting-bcm-sm-t3
HEAD    : 091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32  (= 091b57c)
```

`git diff --stat` (tracked) : 9 fichiers T3.1 (router, catalogue, models `__init__`, routes Angular, shell). **T3.5-1/2 préservés** (untracked : `rbcm_01`–`04`, services, tests, front module).

Documents consolidés **présents** (untracked sous `docs/comptabilite/`) : audit, modèle, arbitrages, révision, README, `T3_PHASE_STATUS.md`. Aucun changement inattendu hors docs + chantier T3 déjà dirty.

`SELECT` Alembic (lecture seule) : `bea_digital` = `20261116_rbcm_04` ; `bea_digital_test` = `20261105_mg_stock_mvt_ref_uq`. Production : **non interrogée**.

Fichiers lus pour cette revue : les six docs listés au §1 du prompt, plus `T3_5_3_T0_COMPLEMENT.md` (tests 19–34), extraits T0 I147.

---

## 3. Conformité des six corrections 4.1–4.6

| ID | Attendu | Constat | Note |
|----|---------|---------|------|
| **4.1 D9** | `writable=false` officiel ; `formula_text` conservé ; WORK vide ; `decision_allowed` dérivé ; pas d’UPDATE `writable` | **Conforme** modèle §4.2, exemple `A:102:D` | Conséquence H9 = `SUM(D9:G9)` : exemple §9 **présent**. Les 8 autres formules historiques (D21, D38, …) sont le même contrat, pas détaillées une à une — acceptable si le seed les classe toutes `OCTOBER_CONSTANT_FORMULA`. |
| **4.2 FK** | `decided_by_id` nullable SET NULL ; historiques RESTRICT ; pas NOT NULL+SET NULL | **Conforme** §5.1 | `calculation_run_id` SET NULL + nullable : cohérent. `deliverable_id` RESTRICT + nullable : OK. |
| **4.3 Canevas** | Pas de transfert UUID ; reprise par `document_cell_key` ; blocage si incompatible | **Conforme** §6 | Cas feuille/adresse/nature/formule : **partiellement**. Bloqué si clé absente ou `decision_allowed` faux. **Non dit** : même clé, nature passée de LEAF à `STRUCTURAL_FORMULA` ; même clé, autre `excel_address` ; formule officielle changée. |
| **4.4 Concurrence** | lock + `expected_current_id` après lock ; UNIQUE seq ; un WORK courant ; rollback | **Conforme pour les décisions** (§5.3). **À ne pas confondre avec la génération WORK** | Voir §9.1 ci-dessous. |
| **4.5 Stockage** | `upload_root/…/templates/{id}/` ; pas l’image ; SHA ; inspecter le chemin en B | **Conforme** §8 | **Traversée de répertoires non mentionnée.** |
| **4.6 Graphe** | NULL, Decimal, ops, propagation, portes, pas de cache Excel | **Conforme en contrat** §9.1 | `IF` : formulation « non interprétable / 0 Excel ignoré » un peu floue. `H31=*10` mal classé (voir seed). |

---

## 4. Conformité R1–R15

| ID | Statut | Écart éventuel |
|----|--------|----------------|
| R1 table dédiée | OK | — |
| R2 pas de `CellResult` Excel | OK | — |
| R3 `cell_decision` moteur | OK | — |
| R4 template + cells | OK | — |
| R5 clés + regex par type | OK avec **trou I147** | `^A:[0-9]{3}:[C-H]$` exclut l’axe I (contrôle `ETAT A!I147`, T0). B ne peut pas seeder cette cellule sous la regex actuelle. |
| R6 portée campagne | OK | Tension avec l’exigence « décision attachée à la **version exacte** du document » : `deliverable_id` est optionnel (trace), pas la portée. **R6 l’emporte** — à laisser explicite pour ne pas réintroduire une FK obligatoire en B. |
| R7 WORK ≠ GENERATED | OK | — |
| R8 chemins distincts | OK | — |
| R9 deux UNIQUE | OK en intention | `UNIQUE(campaign_id, document_seq)` **sans** `WHERE` ni nullabilité : collision conceptuelle avec `GENERATED` (même table, aujourd’hui 0 ligne). |
| R10 graphe | OK | — |
| R11 concordance | OK | — |
| R12 30 % / 70 % | OK | — |
| R13 AVERTISSEMENT sans insert row | OK | Seed B : **ne pas** créer une feuille `AVERTISSEMENT` dans `template_cell` (ajout C). Non écrit clairement pour B. |
| R14 pas de fill `A_VALIDER` | OK | — |
| R15 `rbcm_05` après `rbcm_04` | OK | Politique `bea_digital_test` **absente**. |

---

## 5. Conformité Q1–Q12

| ID | Statut | Commentaire |
|----|--------|-------------|
| Q1 pas de fill 242 | OK | |
| Q2 INFO/FPN, file C inchangée, portes non fermées | OK principe | **O2** : inventaire nominatif toujours ouvert — B seed INFO/FPN « prévues » n’a pas la liste. |
| Q3 30/70 D09 | OK | |
| Q4 motif / justificatif | OK | |
| Q5 partiels grisés | OK | Phase E, pas B |
| Q6 `upload_root` | OK | O3 = 1ʳᵉ tâche de B, pas un préalable d’autorisation si B commence par l’inspection |
| Q7 SUPERSEDED métadonnées | OK | |
| Q8 `expected_current_id` | OK | Phase F |
| Q9 template à la 1re WORK | OK | B pose la FK nullable ; C/Q9 l’alimente |
| Q10 export technique | OK | |
| Q11 README / phase status | OK | Relu : L15 README et Alembic `T3_PHASE_STATUS` alignés `rbcm_04` |
| Q12 scratch | OK | Non supprimé |

---

## 6. Règles métier et réglementaires

| Règle | Tenue ? |
|-------|---------|
| D01 — pas de mapping ACTIVE / fill | Oui (R14). |
| D02 — pas d’ECART en cellule | Oui. |
| D06 — 67 non mappées ≠ 0 auto | Oui en principe ; table `unmapped` **vide en DEV** (audit) — B ne doit pas « réparer » ça par des zéros. |
| D09 — B/C et 30/70 provisoires | Oui. |
| D15 — bases D/C/SD | Oui, hors fill. |
| D16/D17 — H et ratios `H*` non métier | Oui, exemple H9 §9. |
| D22 — conflits | Mentionné, pas opérationnalisé (normal, hors B). |
| WORK ≠ document réglementaire validé | Oui, texte d’en-tête + pas de `VALIDATED`. |
| Saisie INFO/FPN ne ferme aucune porte | Oui Q2. |
| `calculated_value` moteur immuable | Oui R2 / tests 17. |

Aucune fonctionnalité documentaire **n’est écrite** comme fermant une porte. À préserver en B : le seed ne doit pas poser `AUTOMATIQUE` ni recopier des 0 d’octobre comme `CANVAS_NORM` (sauf G / 0,1 / 0,2 listés).

---

## 7. Critères 19–34 (numérotation **complément T0**)

Le modèle §13 a **réinitialisé** la numérotation (1–23). Correspondance ci-dessous. Aucun test exécuté.

| ID T0 complément | Attendu | Couvert modèle §13 | Décision | Préconditions | Ambiguïté |
|------------------|---------|--------------------|----------|---------------|-----------|
| 19 | 9 constantes absentes du WORK | 1 (D9) + partiel | 4.1, R12 | seed 9 formules | Les 8 autres constantes pas citées nommément dans §13 |
| 20 | 30 % et 70 % + D09 | 21 | R12 | E46/D46… | OK |
| 21 | G, 0,1, 0,2 conservés | 21 | CANVAS_NORM | | OK |
| 22 | E7:E25 couverture **vidées** | **absent** | T0 + OCTOBER_LEAF | | **À réintégrer** |
| 23 | INFO C6–C8 / C10–C20 vides ; C9 formule | **absent** | Q2 | | **À réintégrer** ; C9 `INFO:C9` vs formule structurelle |
| 24 | H9 pas `ZERO_CONFIRME` | 12 | 4.6 | D9 vide | OK |
| 25 | FPN C36 pas zéro métier | 12–13 | METIER_IF | | OK |
| 26 | L11 / I8 non OK | 14 | R11 | | OK |
| 27 | H28, C26, C16 non calculables | 13 | RATIO_DIV | | OK |
| 28 | AVERTISSEMENT, D9 reste D9 | 22 | R13 | | OK |
| 29 | POST `A:102:D` ⇏ `cell_result` | 19 | R2 | | Phase F |
| 30 | pas d’UPDATE `calculated_value` | 17 | R2 | | F |
| 31 | 2 WORK, 2 SHA, SUPERSEDED | 10–11 | R8 R9 | | C |
| 32 | `view` 403 ; motif vide 400 | 20 (403 seulement) | Q4 | | **400 motif manquant** |
| 33 | `BCM:102` et `A:102:D` coexistent | 19 | R5 | un run moteur | OK |
| 34 | SHA template `54e3b687…` | 2 | R4 | fichier source | OK |

Modèle **en plus** (hors 19–34) : 3 (template survit au rebuild), 4–6 FK/canevas, 7–8 concurrence, 15 portes, 16 mapping, 18 runner, 23 rollback génération.

---

## 8. Scénarios manquants

| Scénario | Couvert ? | Phase |
|----------|-----------|--------|
| Deux POST décision `expected_current_id=null` | Oui → 201 + 409 | F |
| Deux **générations WORK** simultanées | Oui modèle §7.3 → **w(n+1)**, un seul courant — **pas 409** | C |
| Échec pendant l’écriture fichier | Rollback SQL oui ; **fichier orphelin sur disque** non traité | C |
| Stockage indisponible | Non | B/C |
| SHA template ≠ fichier | « vérifié avant usage » ; pas de code d’erreur `TEMPLATE_SHA_MISMATCH` | B/C |
| Document WORK corrompu / SHA colonne ≠ disque | Non (download) | D |
| Reprise après kill process au milieu de B seed / C write | Seed **non idempotent** ; C rollback SQL seulement | B/C |
| Suppression utilisateur auteur | SET NULL oui | B DDL |
| DELETE template référencé | RESTRICT oui ; `ARCHIVED` vs DELETE non déroulé | B |
| Changement template, même clé, nature devenue non saisissable | Couvert (`decision_allowed` faux) | plus tard |
| Changement d’adresse Excel, même clé | Non explicite | plus tard |
| Téléchargement SUPERSEDED | Oui test 11 | D |
| Traversée `../` dans `stored_path` | **Non** | B |
| `document_seq` vs lignes `GENERATED` | **Non** | **B DDL** |
| Header B2/B3 écrits alors que `writable=false` | Génération §10.7 vs overlay §4.2 : **deux mécanismes**, pas fusionnés | C |

---

## 9. Contradictions et ambiguïtés

### 9.1 Ne pas appliquer le 409 aux générations WORK

Le scénario « deux requêtes `expected_current_id=null` → 201 puis 409 » est celui des **décisions** (`rbcm-doc-dec`).

Les **générations WORK** (`rbcm-work-gen`) : la seconde **réussit** en `document_seq+1` et l’ancienne passe `SUPERSEDED`. Un 409 ici serait une **régression** par rapport au modèle.

B ne code pas encore C, mais un développeur qui fige des CHECK/commentaires DDL en B ne doit pas coller `expected_current_id` sur `rbcm_deliverable`.

### 9.2 Même table `rbcm_deliverable` pour GENERATED et WORK

Aujourd’hui `excel_export` INSERT `kind=EXCEL`, `status=GENERATED`, **sans** `document_seq` / `template_id`.

Le modèle dit `document_seq integer ≥ 1` (lecture : NOT NULL) + `UNIQUE(campaign_id, document_seq)` + `template_id` FK RESTRICT.

Sans précision :

- soit tout livrable (y compris technique) **doit** avoir un seq → mélange des compteurs ;
- soit B pose NOT NULL et casse l’export technique dès la première génération post-migration (0 ligne aujourd’hui, donc la migration **passe**, le piège est **applicatif**).

**Correction documentaire recommandée (ne pas appliquer dans cette revue) :**  
`template_id` et `document_seq` **nullable** ; UNIQUE partiel `(campaign_id, document_seq) WHERE document_seq IS NOT NULL` ; seuls `WORK`/`SUPERSEDED` les renseignent.

### 9.3 Regex A et `I147`

Fichier : `T3_5_3_A_MODELE_DOCUMENTAIRE.md` §2.2.  
T0 : `I147` = `=+H147-H81` (contrôle actif/passif).  
Regex `A:…:[C-H]` → **pas de clé**.  
Correction recommandée : autoriser `I` pour A **uniquement** sur les contrôles (`A:427:I` ou clé `A:CTRL:I147`), documentée avant le seed B.

### 9.4 `H31` = `C39*10`

Classé « norme » dans T0 complément, pas dans la liste `RATIO_DIV` du modèle §4.1. Risque de seed `STRUCTURAL_FORMULA` vs norme. À ranger explicitement (`CANVAS_NORM` inadapté car c’est une **formule**, pas une valeur G).

### 9.5 `depends_on` au seed B ?

JSONB cité ; le graphe est C. Si B doit remplir 663 graphes, le parseur n’est pas spécifié.  
Recommandation : B stocke `formula_text` **obligatoire** pour les formules ; `depends_on` **optionnel** jusqu’à C.

### 9.6 Phases C–F

Le §15 du modèle n’a que le nom des lots. Pas de prérequis / livrables / interdictions / critères par phase (demandé au §7 du prompt de revue). **Pas bloquant pour le DDL B**, bloquant pour enchaîner C sans nouvelle fiche.

Il n’y a **plus** de « T3.5-3-A code ». Conforme.

### 9.7 Documents historiques

`T3_5_3_T0_COMPLEMENT.md` conserve l’alternative « réutiliser CellResult » comme **constat T0**. Le modèle A la **rejette**. Pas une contradiction opérationnelle si B ne lit que le modèle révisé + arbitrages.

---

## 10. Corrections documentaires nécessaires (à faire **avant** B, pas dans cette revue)

Fichier cible principal : `T3_5_3_A_MODELE_DOCUMENTAIRE.md`.

| # | Section | Correction recommandée |
|---|---------|------------------------|
| D1 | §7 | `template_id` et `document_seq` **nullable** ; UNIQUE partiel sur seq ; `GENERATED` sans seq ni template |
| D2 | §2.2 | Clé pour `ETAT A!I147` |
| D3 | §4.1 | Nature de `RCR:H31` (`*10`) |
| D4 | §12 / B | Inventaire seed : T0 cartographie + 663 formules ; **pas** de feuille AVERTISSEMENT ; `formula_text` source ; seed **idempotent** |
| D5 | §8 | `stored_path` = `upload_root` + segments UUID uniquement ; refus `..` |
| D6 | §12 | `bea_digital_test` : rbcm_05 via procédure test-db, pas un upgrade improvisé |
| D7 | §13 | Table de correspondance tests complément 19–34 ↔ modèle 1–23 ; réintroduire 22, 23, 32 (motif 400) |
| D8 | §5 vs §7.3 | Encadré : 409 = décisions ; 2ᵉ WORK concurrent = seq+1 |
| D9 | §15 | Mini-charte B : livrables (migration, copie SHA, seed counts), interdits (fill, runner, WORK utilisateur) |

Ces points sont **documentaires**. Cette revue **ne les a pas appliqués**.

---

## 11. Risques résiduels

| Risque | Gravité pour **B** |
|--------|---------------------|
| Improviser NULL/NOT NULL sur `document_seq` | **Haute** si B démarre maintenant |
| Seed incomplet (I147, H31, INFO) | Haute pour un « seed vérifié » |
| `bea_digital_test` sans rbcm puis tests B | Moyenne |
| Traversée de chemin | Moyenne (copie template) |
| Image Docker ≠ working tree | Déjà connu T3.5-2 ; B = service `migrate`, pas rebuild imposé |
| O2 liste INFO/FPN | B peut seeder toutes les LEAF INFO d’après T0 (C6–C20) en `OCTOBER_LEAF` / C9 formule — **décision de seed** à figer |
| Portes Dxx | Non fermées ; OK |
| Orphan files C | Hors B |

O1–O6 des arbitrages restent ouverts. **O4** (autorisation écrite B) n’est pas donnée par cette revue.

---

## 12. Verdict

# `VALIDABLE SOUS RÉSERVE`

**Pas** `VALIDABLE POUR AUTORISATION B` : le DDL livrable et le contrat de seed laisseraient B inventer des colonnes et un inventaire.

**Pas** `NON VALIDABLE` : aucune contradiction majeure sur D9, les namespaces, les FK utilisateurs, les portes, R14, le faux zéro.

**T3.5-3-B n’est pas autorisée.** Après intégration des réserves D1–D9 (lot documentaire distinct), une nouvelle décision utilisateur pourra autoriser B.

---

## 13. Confirmation d’arrêt

- Rapport : `docs/comptabilite/reporting-bcm-sm/T3_5_3_A_REVUE_FINALE.md`
- Documents de conception **non corrigés** (consigne revue)
- Pas de `rbcm_05`, pas de seed, pas de WORK, pas de touche base hors `SELECT`
- Pas de commit
- HEAD `091b57c` ; working tree T3.5-1/2 intact

**STOP. Attendre la décision de l’utilisateur.**

---

## 14. Addendum (ne modifie pas le verdict de cette revue)

Date : 16/11/2026. Lot suivant : `T3_5_3_A_LEVEE_RESERVES_D1_D9.md`.

Le verdict historique de **cette** revue reste `VALIDABLE SOUS RÉSERVE`. Les corrections D1–D9 y sont listées comme **à faire** ; elles ont été intégrées dans un lot documentaire distinct. Ce paragraphe n’autorise pas T3.5-3-B.
