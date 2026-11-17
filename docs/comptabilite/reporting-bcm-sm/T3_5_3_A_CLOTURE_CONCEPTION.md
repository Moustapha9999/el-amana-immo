# T3.5-3-A — Clôture de conception (avant décision d’ouverture B)

Revue documentaire ciblée. Aucun code, aucune migration, aucun seed.  
**Ce document n’autorise pas l’exécution de T3.5-3-B.**

Date : 16/11/2026.  
Référence : `T3_5_3_A_LEVEE_RESERVES_D1_D9.md`.  
Cible gelée : `T3_5_3_A_MODELE_DOCUMENTAIRE.md` + `T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md`.

**Verdict : `CONCEPTION CLÔTURÉE — B PEUT ÊTRE AUTORISÉE`**

Cela signifie uniquement que les **prérequis documentaires** sont réunis. Ce n’est **pas** une autorisation d’exécution. O4 reste à trancher par l’utilisateur.

---

## 1. Git

```
branche : feat/reporting-bcm-sm-t3
HEAD    : 091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32  (= 091b57c)
```

Working tree T3.5-1/2 préservé. Aucun `rbcm_05` dans le dépôt (recherche `*.py` : 0 occurrence). Aucun nettoyage.

---

## 2. Vérification D1–D9

| ID | Constat | Blocage B ? |
|----|---------|-------------|
| **D1** | Modèle §7 : `template_id` / `document_seq` **nullable** ; CHECK `GENERATED` → tous deux NULL ; UNIQUE **partiel** `WHERE document_seq IS NOT NULL` ; `excel_export` conservé, compteurs non mélangés | Non |
| **D2** | §2.2 : clé **`A:CTRL:I147`**, formule `=+H147-H81`, regex `^A:CTRL:I147$`, `A:427:I` interdit ; distinct de `BCM:102` et `A:102:D` | Non |
| **D3** | §4.1 : `RCR:H31` = **`CANVAS_SCALE_FORMULA`**, `='CALCUL FPN'!C39*10` ; pas `CANVAS_NORM` ni `RATIO_DIV` | Non |
| **D4** | §12 : 8 feuilles, 663 formules, 9 constantes, SHA `54e3b687…`, idempotence `(template_code, sha256)`, pas d’AVERTISSEMENT au seed | Non |
| **D5** | §8 : `{upload_root}/reporting-bcm-sm/templates/{uuid}/`, défaut déclaré `storage/uploads`, UUID interne, `resolve()`, refus `..`, codes d’erreur nommés | Non |
| **D6** | §12.2 : `bea_digital` = `rbcm_04` ; `bea_digital_test` **sans** `rbcm_*` ; inspecter puis stop si base non identifiée ; pas d’upgrade improvisé | Non |
| **D7** | §13 : **DOC-01 à DOC-36** tous présents, sans trou (voir §4) | Non |
| **D8** | §5.3 : décisions 201 puis 409. §7.3 : WORK sérialisé, seq n puis n+1, **pas** de 409 systématique, rollback, orphelins | Non |
| **D9** | §15.1 : nom, prérequis, périmètre, 9 livrables, interdictions, arrêt sur prérequis manquant. **N’autorise pas** l’exécution | Non |

Les limites restantes (compte LEAF mesuré au seed, `upload_root` résolu, préparation test-db) sont des **tâches de tête de B**, pas des trous de conception.

---

## 3. R1–R15, Q1–Q12, portes

Relu dans `T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md` :

- R1 à R15 : présents. R5 inclut `A:CTRL:I147`. R9 = UNIQUE **partiel** (D1). R14 = pas de fill `A_VALIDER`.
- Q1 à Q12 : présents. Q2 INFO nominatif. Q8 distingue 409 / seq+1. Q10 export technique distinct.

Portes D01, D02, D06, D09, D15, D16/D17, D22 : **ouvertes** (O1, DOC-15, interdictions B).  
242 `A_VALIDER` / 0 `ACTIVE` : inchangé (Q1, R14, DOC-16).  
Pas de statut `VALIDATED` dans `rbcm_05`. Validation réglementaire **après F**, hors génération / téléchargement WORK.

Aucun document vivant ne prétend que B est déjà autorisée (`README`, `T3_PHASE_STATUS`, arbitrages, levée, revue finale historique).

---

## 4. DOC-01 … DOC-36

Comptage modèle §13 : **36 lignes**, identifiants continus DOC-01 → DOC-36.

Couverture T0-19–34 : DOC-01, 22, 23, **24 (E7:E25)**, **25 (INFO)**, 11–14, 26, 27, 17, 10, **20 (403)** + **21 (400)**, 19, 02.

Tests B prévus par la charte : DOC-02, 03, 04, 09 partiel, 29–31, 33–36.

---

## 5. Découpage B–F

| Phase | Cohérent | Note |
|-------|----------|------|
| A | conception close | pas de « A code » |
| B | migration + seed | charte §15.1 ; non commencée |
| C | WORK + graphe | après B |
| D | API / download | après C |
| E | UI | après D |
| F | décisions | après D |

Pas de nouvelle sous-phase de conception proposée.

---

## 6. Non-blocages (à ne pas retravailler en conception)

| Point | Traitement |
|-------|------------|
| O3 chemin `upload_root` résolu | 1ʳᵉ tâche de B, charte §15.1 |
| O1 portes métier | inchangées, hors B |
| O5 scratch T0 | ne pas supprimer |
| O6 PDF/SRV | hors T3.5-3 |
| Texte historique R9 dans `T3_5_3_A_REVISION_DOCUMENTAIRE.md` §2 (UNIQUE sans `WHERE`) | **périmé** ; le modèle et les arbitrages l’ont corrigé. Non bloquant. Non corrigé ici (consigne : signaler d’abord). |
| Compte exact E18/E19 couverture | mesure fichier en tête de seed (D4) |

Aucun de ces points n’empêche d’**autoriser** B. Ils n’autorisent pas non plus de l’exécuter.

---

## 7. Blocages restants pour **l’exécution**

1. **O4** — autorisation écrite distincte de l’utilisateur : **absente**.
2. En tête de B, si l’inspection échoue : mauvaise `DATABASE_URL`, Alembic ≠ `rbcm_04` sur `bea_digital`, SHA source ≠ `54e3b687…`, `upload_root` illisible → **stop** (déjà dans la charte).

Pas d’autre blocage documentaire.

---

## 8. Verdict

# `CONCEPTION CLÔTURÉE — B PEUT ÊTRE AUTORISÉE`

Les prérequis documentaires de T3.5-3-B sont réunis.

**T3.5-3-B n’est pas commencée et n’est pas autorisée par cette clôture.**

Attendre une autorisation écrite distincte. Objectif ensuite : terminer le module sur DEV, recette complète, puis validation métier — production hors périmètre.

---

## 9. Arrêt

- Pas de `rbcm_05`
- Pas de seed
- Pas de modification de base
- Pas de commit
- Fichier créé : `docs/comptabilite/reporting-bcm-sm/T3_5_3_A_CLOTURE_CONCEPTION.md` uniquement

**STOP.**
