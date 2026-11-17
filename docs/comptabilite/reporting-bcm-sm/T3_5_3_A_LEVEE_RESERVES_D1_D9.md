# T3.5-3-A — Levée des réserves D1–D9

Lot **documentaire uniquement**. Aucun code, aucune migration, aucun seed, aucun Excel.  
**T3.5-3-B n’est pas autorisée** par ce document. Seul l’utilisateur peut l’autoriser.

Date : 16/11/2026.  
Branche : `feat/reporting-bcm-sm-t3` · HEAD : `091b57c`.

Référence des réserves : `T3_5_3_A_REVUE_FINALE.md` (verdict historique `VALIDABLE SOUS RÉSERVE`, inchangé).  
Cible gelée : `T3_5_3_A_MODELE_DOCUMENTAIRE.md`.

**Verdict : `RÉSERVES LEVÉES — PRÊT POUR REVUE FINALE`**

---

## 1. Résumé exécutif

Les neuf réserves D1–D9 de la revue finale sont **intégrées** au modèle, aux arbitrages et aux index. Le DDL livrable, la clé I147, la nature H31, le contrat de seed, la sécurité des chemins, la stratégie des deux bases, la table `DOC-*` et la charte B sont désormais **figés**.

Ce lot **ne démarre pas** B, **ne crée pas** `rbcm_05`, **ne seed pas**.

O4 (autorisation écrite B) reste ouvert. O1 (portes), O3 (`upload_root` résolu), O5 (scratch), O6 (PDF/SRV) restent ouverts.

---

## 2. État Git

### 2.1 Initial (cette mission)

```
branche : feat/reporting-bcm-sm-t3
HEAD    : 091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32  (= 091b57c)
```

Working tree T3.5-1/2 **préservé** (9 tracked + untracked rbcm / docs / e2e). Aucun nettoyage.

### 2.2 Final

HEAD inchangé `091b57c`. Seuls des Markdown sous `docs/comptabilite/reporting-bcm-sm/` ont été écrits. Pas de commit.

---

## 3. Tableau D1–D9

| ID | Document / section | Correction effectuée | Décision désormais figée | Limite restante |
|----|--------------------|----------------------|--------------------------|-----------------|
| **D1** | Modèle §7, §11 ; arbitrages R9 / D1 | `template_id` et `document_seq` **nullable** ; CHECK statut ; UNIQUE **partiel** `WHERE document_seq IS NOT NULL` | `GENERATED` (excel_export) sans seq ni template ; WORK/SUPERSEDED les renseignent ; compteurs non mélangés | Compte actuel de lignes `GENERATED` en DEV = 0 (audit) ; à revérifier en B |
| **D2** | Modèle §2.2 ; R5 | Clé **`A:CTRL:I147`** ; regex `^A:CTRL:I147$` ; `A:427:I` interdit | Formule `=+H147-H81` conservée ; `STRUCTURAL_FORMULA` ; pas saisissable ; distinct de `BCM:102` et `A:102:D` | Aucune autre `A:CTRL` inventée |
| **D3** | Modèle §4.1, §9.1 | Nature **`CANVAS_SCALE_FORMULA`** pour `RCR:H31` | `='CALCUL FPN'!C39*10` conservée ; NULL/partiel → non complète ; pas `CANVAS_NORM` ni `RATIO_DIV` | `LIQ:D20` et `FPN:F33` classés de même (déjà T0, pas inventés) |
| **D4** | Modèle §12.3–12.5 | Inventaire seed + idempotence SHA | 8 feuilles, 663 formules, 9 constantes, INFO, E7:E25, I147, H31 ; **pas** AVERTISSEMENT ; rejeu sans doublon | Comptes LEAF « grille T0 » = **sortie du seed**, pas un entier inventé ; E18/E19 selon le fichier |
| **D5** | Modèle §8 | UUID interne, `resolve()`, refus `..` | Codes `TEMPLATE_NOT_FOUND`, `TEMPLATE_SHA_MISMATCH`, `TEMPLATE_PATH_UNSAFE`, `STORAGE_UNAVAILABLE`, `WORK_SHA_MISMATCH` | Chemin **résolu** Windows/Docker = O3, 1ʳᵉ tâche de B |
| **D6** | Modèle §12.2 | Stratégie deux bases | DEV : inspecter puis `rbcm_05` après `rbcm_04`. Test : **pas prête** ; test-db, jamais upgrade improvisé | Procédure test-db exacte à **exécuter** en B, pas ici |
| **D7** | Modèle §13 | Table `DOC-01`…`DOC-36` | T0-19–34 réintégrés (E7:E25, INFO, 403, 400 motif) | Tests **non exécutés** |
| **D8** | Modèle §5.3, §7.3–7.4 | Encadré 409 vs seq+1 | Décisions : 201/409. WORK : n puis n+1, rollback, orphelins, pas d’écrasement | Implémentation lock = C/F |
| **D9** | Modèle §15.1 | Charte B | Périmètre, interdits, livrables, arrêt sur prérequis | **N’autorise pas** l’exécution |

---

## 4. Documents modifiés

| Fichier | Action |
|---------|--------|
| `T3_5_3_A_MODELE_DOCUMENTAIRE.md` | D1–D9 intégrés (§2.2, §4.1, §7, §8, §9.1, §10, §11, §12, §13, §15) |
| `T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md` | R5/R9/Q2/Q6/Q8, §5 D1–D9, alternatives écartées |
| `T3_5_3_A_REVISION_DOCUMENTAIRE.md` | Addendum §11 |
| `T3_5_3_A_AUDIT_ETAT_REEL.md` | Addendum §11 (sans réécrire les constats) |
| `T3_5_3_A_REVUE_FINALE.md` | Addendum §14 (verdict historique conservé) |
| `README.md` | Index + statut |
| `T3_PHASE_STATUS.md` | A = conception + levée ; B non autorisé |
| `T3_5_3_A_LEVEE_RESERVES_D1_D9.md` | **Créé** (ce rapport) |

Non modifiés : T0 audit/complément (historiques), Python, TypeScript, SQL, Excel, `runner.py`, bases, `_t353_t0_scratch/`.

---

## 5. Décisions techniques figées (rappel opératoire pour B)

1. **Livrable** : NULL pour `GENERATED` ; NOT NULL pour `WORK`/`SUPERSEDED` ; UNIQUE partiel sur seq.
2. **I147** : `A:CTRL:I147`.
3. **H31** : `CANVAS_SCALE_FORMULA`, formule officielle conservée.
4. **Seed** : identité `(BEA-SM, sha256)` ; SHA v1 = `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658` ; idempotent ; `formula_text` obligatoire ; `depends_on` optionnel.
5. **Chemins** : calculés, jamais pris dans la requête ; refus de traversée.
6. **Test DB** : ne pas supposer `rbcm_*` présents.
7. **Tests** : IDs `DOC-*` stables.
8. **Concurrence** : deux locks distincts (`rbcm-doc-dec` vs `rbcm-work-gen`).
9. **B** : migration + copie + seed seulement.

R1–R15 et Q1–Q12 **préservés**. Portes D01/D02/D06/D09/D15/D16-D17/D22 **non activées**. `A_VALIDER` non fillé. WORK ≠ document réglementaire validé.

R6 inchangé : décisions à **portée campagne** ; `deliverable_id` reste une trace optionnelle, pas une FK obligatoire.

---

## 6. Réconciliation des tests

Voir modèle §13. Correspondance T0 complément 19–34 :

| T0-C | ID stable | Réintégré ? |
|------|-----------|-------------|
| 19 | DOC-01 | oui (9 constantes) |
| 20 | DOC-22 | oui |
| 21 | DOC-23 | oui |
| 22 | DOC-24 | **oui** (E7:E25) |
| 23 | DOC-25 | **oui** (INFO C6–C20 / C9) |
| 24 | DOC-11 | oui |
| 25 | DOC-12 | oui |
| 26 | DOC-13 | oui |
| 27 | DOC-14 | oui |
| 28 | DOC-26 | oui |
| 29 | DOC-27 | oui |
| 30 | DOC-17 | oui |
| 31 | DOC-10 | oui |
| 32 | DOC-20 + DOC-21 | **oui** (403 et 400) |
| 33 | DOC-19 | oui |
| 34 | DOC-02 | oui |

Ancien modèle 1–23 : mappé, non abandonné. Ajouts : DOC-28…36 (rollback, template RESTRICT, SHA, path, stockage, excel_export, I147, H31, seed idempotent).

---

## 7. Feuille de route de finalisation (DEV)

| Étape | Contenu | Sortie |
|-------|---------|--------|
| **A** | Conception (ce lot) | Docs gelés D1–D9 |
| **B** | `rbcm_05` + seed | Schéma + canevas v1 en base DEV — **après autorisation** |
| **C** | WORK + graphe Decimal | Fichier officiel vidé / formules conservées |
| **D** | API GET / générer / download | Permissions Login 2 |
| **E** | UI | Badges, partiels grisés |
| **F** | Décisions + régénération | 201/409, motif 400, historique |
| **Recette DEV** | unitaires, PG, concurrence, API, Angular, Playwright, Excel, SHA, échecs | Parcours 1–11 du modèle §15.3 |
| **Validation réglementaire** | Distincte, après F | Hors `rbcm_05` |
| **Production** | Procédure de release séparée | **Hors périmètre** |

Parcours cible : création SM → responsable → import BAL DET → contrôles → saisies manquantes → calcul + WORK → corrections → régénération → validation distincte → téléchargement → traçabilité.

---

## 8. Risques résiduels

| Risque | Gravité | Traitement |
|--------|---------|------------|
| O4 non donné | — | B interdit tant que non écrit |
| Compte exact E7:E25 / LEAF grilles | Basse | Mesure fichier en tête de seed |
| `bea_digital_test` en retard | Moyenne | D6 : stop si base non identifiée |
| Image Docker ≠ working tree | Connue T3.5-2 | B via service `migrate` |
| Orphelins disque | C | Contrat §7.3 |
| O2 cellules FPN hors INFO | Basse | Hors seed tant que T0 ne les liste pas |
| Portes Dxx | — | Toujours ouvertes |

---

## 9. Contrôle final

| Contrôle | Résultat |
|----------|----------|
| Contradiction D1 vs excel_export | levée (nullable + UNIQUE partiel) |
| D1–D9 traitées | oui |
| R1–R15 préservées | oui |
| Q1–Q12 préservées | oui |
| Tests 19–34 réconciliés | oui (`DOC-*`) |
| Porte réglementaire activée | **non** |
| GENERATED vs WORK | distingués |
| Code / base / Excel | **non touchés** |
| `rbcm_05` créé | **non** |
| Commit | **non** |

---

## 10. Verdict

# `RÉSERVES LEVÉES — PRÊT POUR REVUE FINALE`

**T3.5-3-B n’est pas autorisée.**

Après revue de l’utilisateur, une **autorisation écrite distincte** (O4) sera nécessaire pour ouvrir B.

---

## 11. Arrêt

- Pas de `rbcm_05`
- Pas de seed
- Pas de changement de base
- Pas de phase C
- Pas de commit / push / reset
- Pas de déploiement

**STOP. Attendre la revue de l’utilisateur.**
