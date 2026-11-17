# T3.2 — Audit et seed des correspondances comptables

**Date :** 16/11/2026  
**Branche :** `feat/reporting-bcm-sm-t3`  
**Environnement :** DEV local (`bea_digital` via `bea_internal`) — **pas de production**  
**Statut seed :** effectué — **242 règles `A_VALIDER`**, **0 `ACTIVE`**

---

## 1. Sources utilisées

| Source | Fichier | Rôle | Utilisé pour le seed ? |
|--------|---------|------|-------------------------|
| Correspondance SCD | `Correspondance_BAL_SM_BEA_10-2026_1==SCD.xlsx` | Source primaire compte → Code BCM / rubrique État A | **Oui** (onglet `Correspondance`) |
| Contrôle SCD | même classeur, onglet `Contrôle` | Rapprochement BAL↔SM par clé (43 codes) | Audit seulement |
| BAL (classeur SCD) | onglet `BAL` | Soldes NCG de référence | Non (imports séparés) |
| Maquette RC | `Copie de Maquette SM-RC-MF.xlsx` (onglet `RC`) | Comparative / divergences D01 | **Non** (pas de matrice règle exploitable pour seed) |
| Analyse Claude | `Analyse_metier_SM_matrice.docx` | Travail métier T1 (115 / 67) | **Non** — non parsable ici ; matrice Excel Claude **absente** du dépôt |
| Canevas | `BEA-SM-10-2026.xlsx` | Livrable réglementaire | Non (hors seed mapping) |
| Code dépôt | `backend/app/services/reporting_bcm_sm/mapping_seed.py` | Parse + dry-run + seed idempotent | Oui |

**Empreinte fichier seed :**  
`sha256=1d903cebc316511e49f91a49c9466e3d62bf864c5f885b771d1f8de844156d57`

---

## 2. Comparaison 115 / 242

| Notion | Valeur | Explication |
|--------|--------|-------------|
| Lignes Excel SCD (données) | **242** | Une ligne = un couple (compte, code BCM, base, sens) |
| Règles métier uniques (clé business) | **242** | Aucun doublon exact sur (cellule, match, pattern, base, signe, exclusions) |
| Codes BCM / cellules uniques | **43** | Aligné avec l’onglet `Contrôle` (43 clés) |
| Comptes distincts (`pattern`) | **228** | 14 « extras » dus aux multi-cellules / conflit de base |
| Référence T1 « 115 règles » | **115** | **Non reproductible** depuis le seul fichier Correspondance |
| Référence T1 « 67 non mappées » | **67** | Liste non présente dans Correspondance ; **non seedée** (reste décision D06 / MATRICE) |

### Différence lignes Excel vs règles métier

- **Ligne Excel** = enregistrement brut du tableau SCD (compte + montants d’illustration + base + sens + code BCM).
- **Règle métier** = ce que le moteur doit appliquer : `cell_ref` + `match_type` + `pattern` + `amount_basis` + `sign_multiplier` (+ exclusions).
- Ici, après normalisation, **1 ligne Excel = 1 règle métier** (pas de collapse).

### Pourquoi pas 115 ?

Le chiffre **115** vient du dossier T1/T2 (analyse Claude / matrice compte×cellule).  
Dans le fichier SCD disponible :

- 242 mappings compte→BCM,
- seulement **43** codes BCM.

Donc **115 ≠ 242** et **115 ≠ 43**. Sans la matrice Claude (`Matrice_SM_cellule_regle_source.xlsx`, décision MATRICE ouverte), on **ne force pas** un filtre artificiel à 115.  
**Choix T3.2 :** seed des **242** règles SCD, toutes `A_VALIDER`, en attendant arbitrage D01 / MATRICE.

---

## 3. Analyse structurelle

### Exact vs préfixe

| Type | Nombre |
|------|--------|
| `EXACT` | **242** |
| `PREFIX` | **0** dans le fichier SCD |

Les préfixes évoqués en D01 (`913*`, etc.) **ne sont pas** matérialisés comme tels dans Correspondance (comptes exacts uniquement).

### Exclusions

Aucune exclusion JSON dans la source SCD → `exclusions = []` / `NULL`.

### Multi-cellules (même compte → plusieurs BCM)

**13 comptes** (ex. `120000` → `BCM:109` et `BCM:304` ; `218000` → `BCM:206` et `BCM:335`).  
Marqués `divergence_group=MULTI_CELL` au seed — liés à **D22** (conflits multi-cellules).

### Multi-comptes (même cellule → plusieurs comptes)

**22 cellules** composées (ex. `BCM:128` agrège 202000, 202200, 202400…).  
Comportement moteur prévu : **somme** des règles `ACTIVE` de même `cell_ref` (aujourd’hui aucune ACTIVE).

### Conflit base/signe (même cellule + même compte)

| Compte | Cellule | Variantes | Lignes |
|--------|---------|-----------|--------|
| `218200` | `BCM:403` | `(C, +1)` et `(D, −1)` | CORR-R58, CORR-R59 |

Les **deux** variantes sont conservées en `A_VALIDER` (pas de suppression) — arbitrage humain D01/D22.

### Lignes non exploitables

**0** ligne skippée (toutes les 242 lignes data ont un compte numérique et un code BCM).

### 67 rubriques non mappées

**Non présentes** dans Correspondance.  
Table `rbcm_unmapped_rubric` reste à **0** ligne.  
À alimenter ultérieurement depuis canevas / matrice Claude (D06) — **jamais zéro automatique**.

---

## 4. Contrôle du modèle de données

| Capacité | Couverture |
|----------|------------|
| Règles | `rbcm_mapping_rule` (cell, match, pattern, exclusions JSONB, basis, signe, lifecycle) |
| Versions | `rbcm_mapping_version` + `is_current` |
| Multi-règles / cellule | Oui (pas d’unicité cell seule) |
| Historique sources | `rbcm_mapping_rule_source` (payload JSON) |
| Statuts | `A_VALIDER` \| `ACTIVE` \| `REJECTED` \| `SUPERSEDED` |
| Idempotence seed | Empreinte `sha256=` dans `notes` de version → 2ᵉ run = `SKIPPED_IDEMPOTENT` |
| Non-écrasement ACTIVE | Nouvelle version seulement ; pas d’UPDATE des règles ACTIVE |

---

## 5. Dry-run (avant insertion)

```text
excel_rows              = 242
unique_business_rules   = 242
duplicate_groups        = 0
prefix_rules            = 0
unique_cells            = 43
multi_cell_comptes      = 13
multi_compte_cells      = 22
conflicts_base_sign     = 1 (218200 / BCM:403)
incomplete_count        = 0
lifecycle_forced        = A_VALIDER
```

Fichier candidats :  
[`T3_2_MAPPING_SEED_CANDIDATES.jsonl`](T3_2_MAPPING_SEED_CANDIDATES.jsonl)

---

## 6. Résultat du seed DEV

| Métrique | Valeur |
|----------|--------|
| Status 1ʳᵉ exécution | `INSERTED` |
| `version_id` | `3dcf843f-06fa-4ce9-bda0-93c6be85ec81` |
| Règles insérées | **242** |
| Toutes `A_VALIDER` | **Oui** |
| Règles `ACTIVE` | **0** |
| Sources liées | **242** |
| Versions mapping | **1** (`is_current=true`) |
| 2ᵉ exécution (même fichier) | **idempotente** (pas de 2ᵉ version ; toujours 242 règles) |

Commande utilisée (DEV, réseau `bea_internal`, code monté) :  
`python scripts/rbcm_seed_mapping.py --seed --file /data/Correspondance.xlsx`

---

## 7. Tests exécutés

```text
pytest backend/tests/test_reporting_bcm_sm.py → 8 passed
```

Couvre : catalogue, paramètres, Decimal/bases, parse 242/`A_VALIDER`, dry-run (43 cellules, conflit 218200), P2 UNIQUE, absence constante ECART.

---

## 8. Anomalies à traiter en validation métier (humain)

1. **D01 / MATRICE** — réconcilier 115 (Claude) vs 242 (SCD) vs 43 codes BCM.  
2. **D22** — 13 comptes multi-cellules + conflit `218200`.  
3. **D06** — 67 rubriques non mappées non encore listées en base.  
4. **Préfixes** — absents du SCD ; ne pas inventer `913*` sans source.  
5. **Aucune activation** tant que validation Comptabilité non faite.

---

## 9. État Git

- Branche : `feat/reporting-bcm-sm-t3`
- **Pas de commit / push** (demande respectée)
- Modifs locales : code T3 + docs `docs/comptabilite/reporting-bcm-sm/` + seed mapping

---

## 10. Interdictions respectées

- Pas de production  
- Pas d’activation automatique  
- Pas de validation métier des règles  
- Pas de suppression de lignes SCD sans justification (les 242 sont conservées)
