# T3.5-3 T0 — Complément d’audit (formules, faux zéro, modèles)

Branche : `feat/reporting-bcm-sm-t3` · HEAD Git inchangé `091b57c`  
**Audit uniquement. Aucun code métier. Aucune migration. Aucune modification Excel. Aucun commit / push / reset / rebuild.**  
T3.5-3-A **non commencé**. Mapping 242 `A_VALIDER` et ECART **non activés**.  
`engine/runner.py` **non modifié**. SM `11/2026` et `01/2026` **non touchées**.

Complète `T3_5_3_T0_AUDIT.md`. Ne le remplace pas.

Canevas relu : `BEA-SM-10-2026.xlsx`, SHA-256 `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658`, **663 formules**, 8 feuilles.

---

## 1. Vérification 1 — Formules historiques sur les huit feuilles

Toutes les formules ont été relues (openpyxl 3.1.5, formules non évaluées). L’audit T0 s’arrêtait aux 9 constantes d’ETAT A et aux 3 cellules `*30%` d’ETAT B. Ce complément classe **les 663**.

### 1.1 Règles de classement

| Nature | Définition | Décision |
|--------|------------|----------|
| `STRUCTURELLE` | `SUM`, somme `+` de cellules, copie `='feuille'!addr` | **conserver** |
| `CONSTANTE_HISTORIQUE` | Formule contenant un montant d’octobre (≥ 5 chiffres, hors code BCM) | **neutraliser** (vider la cellule à la génération ; **ne jamais** en faire une règle métier) |
| `METIER_D09` | `*30%` officiel d’ETAT B | **conserver_provisoire_D09** |
| `CONTROLE_CONCORDANCE` | `IF(...=...,TRUE,FALSE)` B/C | **conserver** la formule ; **ne pas** afficher VRAI comme contrôle OK tant que les sources sont incomplètes |
| `METIER_CONDITION` | `IF` de plafond FPN / gap liquidité | **conserver** ; résultat **non interprétable** si dépendances vides (renvoie 0) |
| `METIER_RATIO` | Division ou coefficient réglementaire du canevas (`/`, `*10`, `*10/100`, `/2`) | **conserver** ; statut UI obligatoire |

Les **quotités** `1`, `0,33`, `0,25`, le plancher `0,1` (couverture) et `0,2` (liquidité) sont des **valeurs** du canevas, pas des formules. Ce ne sont **pas** des montants d’octobre. Décision : **conserver_norme_canevas**.

### 1.2 Comptage

| Feuille | Formules | Structurelles | Const. hist. | 30 % D09 | Concordance IF | IF métier | Ratio / division |
|---------|---------:|--------------:|-------------:|---------:|---------------:|----------:|-----------------:|
| informations à fournir | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| ETAT A | 306 | 297 | **9** | 0 | 0 | 0 | 0 |
| ETAT B | 136 | 121 | 0 | **3** | **12** | 0 | 0 |
| ETAT C | 92 | 77 | 0 | 0 | **15** | 0 | 0 |
| CALCUL FPN | 30 | 27 | 0 | 0 | 0 | **2** | **1** |
| RATIO COUVERTURE DE RISQUE | 57 | 55 | 0 | 0 | 0 | 0 | **1** (+ `*10` norme) |
| RATIO DE LIQUIDITE | 31 | 28 | 0 | 0 | 0 | **2** | **2** |
| RATIO FP ET AI | 10 | 9 | 0 | 0 | 0 | 0 | **1** |
| **Total** | **663** | 615 | **9** | **3** | **27** | **4** | **5** (+1 `*10`) |

Aucune formule hors ETAT A n’incrusté un montant d’octobre. Les montants d’octobre hors formules (valeurs / zéros saisis) restent à **neutraliser** comme dans T0.

### 1.3 Formules à constante historique — never règles métier

Uniquement ETAT A. À **neutraliser** (cellule LEAF vide dans le WORK). Interdit de les recopier dans `rbcm_mapping_rule`, dans le runner, ou comme formule de template « officielle ».

| Feuille | Cellule | Code | Formule exacte | Constante(s) | Décision |
|---------|---------|------|----------------|--------------|----------|
| ETAT A | D9 | 102 | `=588160767-F9` | 588160767 | **neutraliser** |
| ETAT A | D21 | 114 | `=150000000-150000000` | 150000000, 150000000 | **neutraliser** (évalue toujours 0) |
| ETAT A | D38 | 131 | `=3972024483-C38-2873218-5` | 3972024483, 2873218, et `-5` | **neutraliser** — `2873218` ≠ activation D02 |
| ETAT A | D75 | 234 | `=53348003-C75` | 53348003 | **neutraliser** |
| ETAT A | D76 | 235 | `=77770480-C76` | 77770480 | **neutraliser** |
| ETAT A | D106 | 322 | `=331024347.65-F106` | 331024347.65 | **neutraliser** |
| ETAT A | D112 | 328 | `=737956675-D111` | 737956675 | **neutraliser** |
| ETAT A | D123 | 403 | `=463722024+296461984-21` | 463722024, 296461984, et `-21` | **neutraliser** |
| ETAT A | D167 | 516 | `=5874268360-G167` | 5874268360 | **neutraliser** |

**Confirmation demandée :** ces formules, et tout montant d’octobre lu comme `VALEUR` / `ZERO` saisi, **ne seront jamais** repris comme règles métier. T3.5-3-A doit les marquer `OCTOBER_CONSTANT_FORMULA` / `OCTOBER_LEAF` dans `rbcm_template_cell`, `writable=false` pour la formule incrustée (la cellule redevient une feuille saisie vide).

### 1.4 Formules 30 % d’ETAT B — dépendantes de D09, provisoires

Identification **explicite**, inchangée par rapport à T0, étendue aux compléments 70 % :

| Feuille | Cellule | Formule exacte | Nature | Décision |
|---------|---------|----------------|--------|----------|
| ETAT B | E46 | `=+('ETAT A'!C38+'ETAT A'!D38)*30%` | `METIER_D09` | **conserver_provisoire_D09** |
| ETAT B | E48 | `=+'ETAT A'!D40*30%` | `METIER_D09` | **conserver_provisoire_D09** |
| ETAT B | E49 | `=+'ETAT A'!D41*30%` | `METIER_D09` | **conserver_provisoire_D09** |
| ETAT B | D46 | `=+('ETAT A'!C38+'ETAT A'!D38)-E46` | complément 70 % | **conserver_provisoire_D09** (dépend de E46) |
| ETAT B | D48 | `=+'ETAT A'!D40-E48` | complément 70 % | **conserver_provisoire_D09** |
| ETAT B | D49 | `=+'ETAT A'!D41-E49` | complément 70 % | **conserver_provisoire_D09** |

Correction T0 : D46 / D48 / D49 n’étaient pas taguées D09. Ce sont des formules **structurelles d’apparence** mais **métier-provisoires** : 70 % = total A − 30 %. Tant que D09 n’est pas close, badge identique aux 30 %.

### 1.5 ETAT B — autres formules (hors 30 % / IF)

Tout le reste d’ETAT B est `SUM(C:H)`, totaux `+` de sous-lignes, ou **renvoi à ETAT A** :

| Cellule | Formule exacte | Décision |
|---------|----------------|----------|
| D12 | `=+'ETAT A'!D33` | conserver (copie A → B) |
| F31 | `=+'ETAT A'!D34` | conserver |
| E39 | `=+'ETAT A'!D35` | conserver |
| E43 | `=+'ETAT A'!D36` | conserver |
| D47 | `=+'ETAT A'!D39` | conserver |
| E27 | `=+'ETAT A'!D163-'ETAT B'!D27` | conserver ; **partiel** si D27 vide |
| C55:I55 | totaux généraux `+` / `SUM` | conserver |

Les feuilles C–H des codes B 101–216 sont presque toutes des **0 numériques d’octobre** (pas des formules) → **neutraliser** (LEAF vide), jamais recopier comme zéro métier.

### 1.6 ETAT C

Formules : totaux `SUM(C:E)` / `+` de maturités, copies depuis ETAT A ou ETAT B, 15 `IF` de concordance.

Copies inter-feuilles (conserver, résultat lié aux portes D09 / D16) :

| Cellule | Formule exacte |
|---------|----------------|
| D15 | `=+'ETAT B'!D12` |
| D17 | `=+'ETAT B'!F31` |
| D19 | `=+'ETAT B'!E39` |
| E20 | `=+'ETAT B'!E43` |
| E30 | `=+'ETAT A'!D97+'ETAT A'!G97` |
| E36 | `=+'ETAT A'!H110` |

Feuilles C/D/E des codes 101–220 : **0 d’octobre** à neutraliser.

### 1.7 Contrôles de concordance (`IF` TRUE/FALSE) — 27 formules

**ETAT B colonne L** (12) :

| Cellule | Formule exacte |
|---------|----------------|
| L11 | `=IF('ETAT A'!H33+'ETAT A'!C33=I11,TRUE,FALSE)` |
| L20 | `=IF('ETAT A'!H34+'ETAT A'!C34=I20,TRUE,FALSE)` |
| L36 | `=IF('ETAT A'!H35+'ETAT A'!C35=I36,TRUE,FALSE)` |
| L40 | `=IF('ETAT A'!H36+'ETAT A'!C36=I40,TRUE,FALSE)` |
| L44 | `=IF('ETAT A'!H37+'ETAT A'!C37=I44,TRUE,FALSE)` |
| L46 | `=IF('ETAT A'!H38+'ETAT A'!C38=I46,TRUE,FALSE)` |
| L47 | `=IF('ETAT A'!H39+'ETAT A'!C39=I47,TRUE,FALSE)` |
| L48 | `=IF('ETAT A'!H40+'ETAT A'!C40=I48,TRUE,FALSE)` |
| L49 | `=IF('ETAT A'!H41+'ETAT A'!C41=I49,TRUE,FALSE)` |
| L51 | `=IF('ETAT A'!H45+'ETAT A'!C45=I51,TRUE,FALSE)` |
| L52 | `=IF('ETAT A'!H70+'ETAT A'!C70=I52,TRUE,FALSE)` |
| L53 | `=IF('ETAT A'!H64+'ETAT A'!C64=I53,TRUE,FALSE)` |

**ETAT C colonne I** (15) :

| Cellule | Formule exacte |
|---------|----------------|
| I8 | `=IF('ETAT A'!H29=F8,TRUE,FALSE)` |
| I9 | `=IF('ETAT A'!H30=F9,TRUE,FALSE)` |
| I15 | `=IF('ETAT A'!H33=F15,TRUE,FALSE)` |
| I17 | `=IF('ETAT A'!H34=F17,TRUE,FALSE)` |
| I19 | `=IF('ETAT A'!H35=F19,TRUE,FALSE)` |
| I20 | `=IF('ETAT A'!H36=F20,TRUE,FALSE)` |
| I22 | `=IF('ETAT A'!H70=F22,TRUE,FALSE)` |
| I23 | `=IF('ETAT A'!H71=F23,TRUE,FALSE)` |
| I24 | `=IF('ETAT A'!H64=F24,TRUE,FALSE)` |
| I30 | `=IF('ETAT A'!H96=F30,TRUE,FALSE)` |
| I31 | `=IF('ETAT A'!H101=F31,TRUE,FALSE)` |
| I36 | `=IF('ETAT A'!H110=F36,TRUE,FALSE)` |
| I38 | `=IF('ETAT A'!H120=F38,TRUE,FALSE)` |
| I39 | `=IF('ETAT A'!H133=F39,TRUE,FALSE)` |
| I40 | `=IF(F40='ETAT A'!H134-'ETAT A'!H135,TRUE,FALSE)` |

Décision : **conserver** (mécanographie officielle). **Ne pas réécrire** en `IF(ISBLANK;…)` pour masquer le problème. En Excel, `0=0` → `TRUE` dès que les deux côtés sont vides. En BEA DIGITAL : statut `CONTROLE_NON_INTERPRETABLE` tant qu’une dépendance est `NON_RENSEIGNE`. Jamais un badge « concordance OK ».

### 1.8 CALCUL FPN (30 formules)

Copies depuis ETAT A et `informations à fournir`, plus :

| Cellule | Formule exacte | Nature | Décision |
|---------|----------------|--------|----------|
| C7 | `='ETAT A'!H143` | structurelle | conserver |
| C8 | `='ETAT A'!H141` | structurelle | conserver |
| C9 | `='ETAT A'!H142-'informations à fournir'!C13` | structurelle | conserver ; partiel si C13 vide |
| C10 | `=+'ETAT A'!D144+'ETAT A'!D145` | structurelle | conserver |
| C11 | `='informations à fournir'!C9` | structurelle | conserver |
| C12 | `=+'informations à fournir'!C14` | structurelle | conserver |
| C13 | `=SUM(C7:C12)` | structurelle | conserver |
| C14 | `=+'informations à fournir'!C15` | structurelle | conserver |
| C15 | `=+C14` | structurelle | conserver |
| C16 | `='ETAT A'!H77` | structurelle | conserver |
| C17 | `='ETAT A'!H79` | structurelle | conserver |
| C18 | `='ETAT A'!H78` | structurelle | conserver |
| C19 | `='informations à fournir'!C10` | structurelle | conserver |
| C20 | `='ETAT A'!H80` | structurelle | conserver |
| C21 | `='informations à fournir'!C11` | structurelle | conserver |
| C22 | `='informations à fournir'!C12` | structurelle | conserver |
| C23 | `='ETAT A'!H74` | structurelle | conserver |
| C24 | `=+'informations à fournir'!C16` | structurelle | conserver |
| C25 | `=+'informations à fournir'!C17` | structurelle | conserver |
| C26 | `=+'informations à fournir'!C18` | structurelle | conserver |
| C27 | `=IF(C33<C35,C35-C33,0)` | métier condition | conserver ; **faux zéro** si C33 et C35 vides (`0<0` faux → 0) |
| C28 | `=SUM(C16:C27)` | structurelle | conserver |
| C29 | `=+C13+C15-C28` | structurelle | conserver |
| C32 | `=+'informations à fournir'!C19` | structurelle | conserver |
| C33 | `=+C32` | structurelle | conserver |
| F33 | `=C39*10/100` | norme canevas 10 % | conserver_norme ; non interprétable si C39 incomplet |
| C34 | `=+'informations à fournir'!C20` | structurelle | conserver |
| C35 | `=+C34` | structurelle | conserver |
| C36 | `=IF(C33>=C35,C33-C35,0)` | métier condition | conserver ; **faux zéro** si les deux vides (`0>=0` vrai → 0) |
| C39 | `=+C29+C36` | structurelle | FPN ; non métier tant que annexes + A incomplets |

`informations à fournir` C6–C8 et C10–C20 = **0 numériques d’octobre** (seule C9 est une formule). Neutraliser. Ne pas les traiter comme zéros FPN confirmés.

### 1.9 RATIO COUVERTURE DE RISQUE (57 formules)

Motif répété lignes 7–17 et 20–25 : `D=renvoi ETAT A`, `F=D-E`, `H=G*F`. Puis :

| Cellule | Formule exacte | Décision |
|---------|----------------|----------|
| H26 | `=SUM(H20:H25,H7:H17)` | conserver |
| H27 | `='CALCUL FPN'!C39` | conserver |
| H28 | `=H27/H26` | conserver ; **`#DIV/0!`** si H26 vide |
| H31 | `='CALCUL FPN'!C39*10` | **conserver_norme_canevas** (exigence 10× FPN, pas un montant d’octobre) |
| H32 | `=+H26` | conserver |
| H33 | `=+H31-H32` | conserver |

Valeurs **non formules** à distinguer :

| Cellules | Contenu octobre | Décision |
|----------|-----------------|----------|
| G7:G17 | `1` | **conserver_norme_canevas** (pondération 100 %) |
| G20:G21 | `0.33` | **conserver_norme_canevas** |
| G22:G25 | `0.25` | **conserver_norme_canevas** |
| H29 | `0.1` | **conserver_norme_canevas** (plancher 10 %) |
| E7:E25 | `0` | **neutraliser** (provisions déduites = feuilles, pas une norme) |

Ne pas vider les quotités G / H29 : ce n’est pas de la donnée d’octobre.

### 1.10 RATIO DE LIQUIDITE (31 formules)

| Cellule | Formule exacte | Décision |
|---------|----------------|----------|
| D6 | `=SUM(D7:D13)` | conserver |
| D7 | `='ETAT A'!H8` | conserver |
| D8 | `='ETAT A'!H11` | conserver |
| D9 | `='ETAT A'!H57` | conserver |
| D10 | `='ETAT A'!H42` | conserver |
| D11 | `='ETAT A'!H44` | conserver |
| D13 | `=C48` | conserver (boucle avec C48) |
| D14 | `=SUM(D15:D24)` | conserver |
| D15 | `='ETAT A'!H85` | conserver |
| D16 | `=+'ETAT A'!H105` | conserver |
| D20 | `=+'ETAT A'!H116/2` | **conserver_norme** (moitié de A 116) ; 0 si A116 vide — **pas** `#DIV/0!` |
| D21 | `=+'ETAT A'!H119` | conserver |
| D22 | `=+'ETAT A'!H122` | conserver |
| D24 | `=C49` | conserver |
| C26 | `=D6/D14` | conserver ; **`#DIV/0!`** si D14 vide |
| C33:C38, C41:C46 | renvois A / C | conserver |
| C39 | `=SUM(C33:C38)` | conserver |
| C47 | `=SUM(C41:C46)` | conserver |
| C48 | `=IF(C39-C47>0,C39-C47,0)` | conserver ; **faux zéro** si les deux vides |
| C49 | `=IF(C47-C39>0,C47-C39,0)` | conserver ; idem |

Valeur `C27 = 0.2` : **conserver_norme_canevas** (seuil 20 %).  
`D12`, `D17`, `D18`, `D19`, `D23` = **0 d’octobre** → **neutraliser**.

### 1.11 RATIO FP ET AI (10 formules)

| Cellule | Formule exacte | Décision |
|---------|----------------|----------|
| C6 | `='CALCUL FPN'!C39` | conserver |
| C8 | `='ETAT A'!H59` | conserver |
| C9 | `='informations à fournir'!C12` | conserver |
| C10 | `=C8-C9` | conserver |
| C11 | `='ETAT A'!H65-'ETAT A'!H68` | conserver |
| C12 | `='ETAT A'!H68` | conserver |
| C13 | `=C11+C12` | conserver |
| C14 | `='ETAT A'!H41` | conserver |
| C15 | `=C14+C13+C10` | conserver |
| C16 | `=(C6/C15)*100` | conserver ; **`#DIV/0!`** si C15 vide |

### 1.12 informations à fournir

| Cellule | Formule exacte | Décision |
|---------|----------------|----------|
| C9 | `='ETAT A'!D146` | conserver |

Inventaire exhaustif adresse par adresse : **annexe A**.

---

## 2. Vérification 2 — Risque de faux zéro dans le classeur WORK

### 2.1 Comportement Excel après neutralisation

openpyxl n’évalue pas. Excel, lui, traite une **cellule vide comme 0** dans `SUM`, `+`, `-`, `*`. Conséquence d’un WORK fidèle (LEAF vidées, formules officielles conservées) :

1. Tout total `SUM` / `+` dont les feuilles sont vides **affiche `0`** (souvent `0,00` après format).
2. Les `IF` d’écart (`C33<C35`, `C39-C47>0`) **renvoient 0**.
3. L’`IF` inverse FPN `C33>=C35` **renvoie 0** aussi (`0>=0` est vrai, différence nulle).
4. Les 27 concordances **affichent TRUE**.
5. `H28`, `C26`, `C16` **affichent `#DIV/0!`**.
6. `*30%`, `*10`, `/2`, `*10/100` affichent **0** sans erreur.

Ce `0` Excel **n’est pas** un zéro métier. T0 §13 tests 6–7 (feuille `NON_RENSEIGNE` → « À compléter ») ne couvrent **que les LEAF**. Ils ne couvrent pas les totaux.

### 2.2 Formules qui affichent zéro lorsque les dépendances sont vides

Toutes les `STRUCTURELLE` (`SUM`, `+`, copie, `F=D-E`, `H=G*F`) dès que chaque opérande est vide ou déjà un faux zéro.

Cas **IF → 0** (pièges) :

| Cellule | Condition si deps vides | Résultat Excel |
|---------|-------------------------|----------------|
| FPN C27 | `0<0` faux | **0** |
| FPN C36 | `0>=0` vrai | **0** |
| LIQ C48 | `0>0` faux | **0** |
| LIQ C49 | `0>0` faux | **0** |
| B E46/E48/E49 | `0*30%` | **0** |
| RCR H31 | `0*10` | **0** |
| FPN F33 | `0*10/100` | **0** |
| LIQ D20 | `0/2` | **0** |

### 2.3 Résultats partiels

Dès qu’**une** feuille d’un `SUM` / `+` est renseignée et une autre non, Excel affiche un **sous-total**. Exemples :

- ETAT A `H9 = SUM(D9:G9)` si seul F9 (caisse devises) est saisi : H9 = F9, **sans** D/E/G.
- ETAT B `I11` si seule D12 (`='ETAT A'!D33`) est remplie : total B « crédits » = une colonne.
- FPN `C29 = C13+C15-C28` si C13 a le capital A et C28 est encore 0 (annexes vides) : FPN **trop élevé**.
- RCR `H7 = G7*F7` avec G7=1 conservé et F7 = D7 − 0 : si D7 (copie A) est rempli et E7 (provision) vide, H7 **surestime** le risque.

Un résultat partiel est plus dangereux qu’un 0 global : il **ressemble** à un montant réel.

### 2.4 Non interprétables tant que les portes Dxx sont ouvertes

| Porte | Cellules / feuilles dont le résultat n’est pas métier |
|-------|------------------------------------------------------|
| **D01** | Toute cellule que l’on serait tenté de remplir depuis `BCM:nnn` / `A_VALIDER`. Aucun `AUTOMATIQUE`. |
| **D02** | D38 et toute cellule où l’on écrirait `2873218`. ECART inactif. |
| **D06** | Rubrique sans règle : LEAF `NON_RENSEIGNE`, jamais 0 auto. Totaux qui n’agrègent que ces LEAF = non interprétables. |
| **D09** | **ETAT B et C entiers**, y compris 30 % / 70 %, copies A→B, B→C, concordances L/I. |
| **D15** | Toute valeur issue du mapping (hors périmètre de remplissage T3.5-3). |
| **D16 / D17** | Axes D/E/F/G d’ETAT A (résidents / non-résidents). Donc H = `SUM(D:G)` d’une ligne de détail, **et** tous les ratios qui lisent `ETAT A'!H*`. |
| **D22** | Cellule en conflit multi-propositions. |

Conséquence : **aucun ratio (H28, C26, C16), aucun FPN C39, aucun total B/C** n’est un résultat métier tant que ces portes ne sont pas closes. Même un graphe « toutes les LEAF de la formule ont une valeur » resterait `PROVISOIRE` si la valeur vient d’une ventilation non autorisée.

### 2.5 Stratégie (contraintes 1–6)

1. **Conserver les formules officielles structurelles** dans le xlsx WORK (y compris IF, 30 %, divisions, `*10`). Ne pas les réécrire.
2. **Ne pas transformer les non-renseignées en zéro** dans BEA DIGITAL ni dans le template seed : LEAF = `None` / `NON_RENSEIGNE`.
3. **Ne pas modifier les formules officielles** (`IF(ISBLANK)`, `IFERROR`, `N()`, `+0`) pour cacher les 0 Excel ou les `#DIV/0!`.
4. **Distinguer complet / partiel / non interprétable** par un **graphe de dépendances** côté Python (même graphe que `rbcm_template_cell.formula`), pas par la valeur Excel cachée.
5. **Afficher les statuts dans BEA DIGITAL** (colonne / pastille par cellule, bandeau par feuille, bandeau campagne).
6. **Avertissement visible dans le fichier Excel WORK** sans décaler les lignes officielles (une insertion de ligne **casserait** toutes les adresses).

Proposition opérationnelle :

| Couche | Comportement |
|--------|----------------|
| UI cellule LEAF vide | « À compléter », **jamais** `0,00` |
| UI cellule LEAF `ZERO_CONFIRME` / `ZERO_MANUEL` + motif | `0,00` + badge « zéro confirmé » |
| UI formule, toutes deps `COMPLETE` **et** portes Dxx de la cellule closes | montant (pipe `montant`) + badge « calculé » |
| UI formule, au moins une dep `NON_RENSEIGNE` | montant éventuel grisé **ou** em dash ; badge **« partiel / incomplet »** ; jamais « 0,00 » nu |
| UI formule ratio dénominateur vide | « Non calculable » (`#DIV/0!`) |
| UI concordance | « Non interprétable » tant que sources incomplètes ; jamais « OK » sur `TRUE` Excel à vide |
| Feuille B/C / ratios / FPN | bandeau feuille : « Hors validation réglementaire — portes D01/D09/D16… ouvertes » |
| Excel WORK | (a) **feuille ajoutée** `AVERTISSEMENT` en première position ; (b) **en-tête / pied de page** de chaque feuille officielle ; (c) `warnings` JSON du livrable. **Pas** d’insert row, **pas** d’overwrite de A1/A2 officiels |

Texte Excel proposé (en-tête) :

> VERSION DE TRAVAIL BEA DIGITAL — montants et totaux éventuellement incomplets — **ne constitue pas une validation réglementaire**.

### 2.6 Comment l’utilisateur distingue un zéro métier d’un zéro de formule incomplète

| Signal | Zéro métier confirmé | Zéro (ou vide) de formule incomplète |
|--------|----------------------|--------------------------------------|
| Origine | Décision append-only `ZERO_CONFIRME` / `ZERO_MANUEL` **ou** moteur `AUTOMATIQUE` (interdit tant que D01) | Évaluation `SUM`/`IF`/`*30%` sur deps `NON_RENSEIGNE` |
| UI montant | `0,00` | « À compléter » sur la LEAF ; « Incomplet » / em dash sur la formule — **pas** `0,00` seul |
| Motif | obligatoire | sans objet |
| Excel | 0 saisi dans la LEAF (après décision → régénération) | formule intacte qui *peut* afficher 0 — l’en-tête WORK et la feuille `AVERTISSEMENT` le disent ; l’UI fait foi |
| Statut API | `ZERO_CONFIRME` / `ZERO_MANUEL` | `NON_RENSEIGNE` (LEAF) · `FORMULE_PARTIELLE` · `FORMULE_NON_INTERPRETABLE` · `CONTROLE_NON_INTERPRETABLE` |

Règle d’or : **un `0` Excel de formule n’est jamais promu `ZERO_CONFIRME`**. Seul un acte utilisateur (ou un calcul moteur D01, plus tard) crée un zéro métier.

Statuts documentaires **nouveaux** (à ne pas confondre avec `CELL_VALUE_STATUSES` moteur) :

`NON_RENSEIGNE` · `ZERO_CONFIRME` · `ZERO_MANUEL` · `VALEUR_DECIDEE` · `FORMULE_COMPLETE` · `FORMULE_PARTIELLE` · `FORMULE_NON_INTERPRETABLE` · `CONTROLE_NON_INTERPRETABLE` · `PROVISOIRE_D09` · `NORME_CANEVAS`

---

## 3. Vérification 3 — Compatibilité des modèles existants

Sources : `backend/app/models/reporting_bcm_sm.py`, `backend/alembic/versions/20261116_rbcm_01_fondations.py` (rbcm_02–04 n’altèrent pas ces cinq tables). **Aucune table `rbcm_template`.**

### 3.1 `RbcmCampaign`

| Élément | Réel |
|---------|------|
| UNIQUE | `(bank_code, period_year, period_month, campaign_version)` |
| Check | `period_month 1–12`, `campaign_version ≥ 1`, `status IN` BROUILLON…ROUVERTE |
| `template_version_id` | `UUID` **nullable, sans FK**, aucune table cible |
| `mapping_version_id` | UUID nullable, **sans FK** |
| Versionnement | `campaign_version` = version de **campagne** (reouverture), **pas** version de fichier WORK |
| Plusieurs WORK | **oui** au niveau campagne (pas de contrainte « un seul livrable ») |

Incompatibilité : T0 disait « brancher `template_version_id` ». Il **manque** `rbcm_template` **et** la FK. Additif nécessaire.

### 3.2 `RbcmCalculationRun`

| Élément | Réel |
|---------|------|
| UNIQUE campagne | **aucun** — N runs / campagne |
| `status` | `String(24)` défaut `RUNNING`, **pas de CHECK** |
| Fingerprints | imports, mapping, params, **template** (colonne déjà là, jamais alimentée par un SHA canevas) |
| FK | `campaign_id` RESTRICT, `started_by_id` SET NULL |

Réutilisable comme **journal de génération WORK** (run documentaire distinct du moteur) **à condition** de ne pas y coller des `RbcmCellResult` en `BCM:nnn` et `A:102:D` mélangés. T3.5-3 **ne doit pas** appeler `engine/runner.py`. Un run documentaire éventuel = nouveau `engine_version` documentaire, ou plutôt **pas de run moteur du tout** : le livrable pointe `run_id=NULL`.

### 3.3 `RbcmCellResult`

| Élément | Réel |
|---------|------|
| UNIQUE | `(run_id, cell_ref)` — **une valeur par clé moteur par run** |
| `cell_ref` | **`String(32)`** |
| Montants | `calculated_value`, `retained_value` `Numeric(18,2)` **nullable** |
| `value_status` | `String(32)` défaut `NON_RENSEIGNE` — liste applicative `CELL_VALUE_STATUSES`, **pas de CHECK SQL** |
| FK | `run_id` RESTRICT, `campaign_id` RESTRICT |
| UPDATE | le runner actuel **INSERT** seulement (nouveau run). Aucun service n’UPDATE `calculated_value` aujourd’hui |

**`A:102:D` tient dans 32 caractères** (7). `BCM:102` aussi (7).  
`RATIO COUVERTURE DE RISQUE!H28` = 30 caractères — **passe juste**. Ce n’est **pas** une raison d’utiliser cette adresse comme `cell_ref`.

**Collision de namespaces (point bloquant si réutilisation brute) :**

| Clé | Sens | Table actuelle |
|-----|------|----------------|
| `BCM:102` | scalaire moteur, 1 montant pour le code A 102 | `rbcm_cell_result` / mapping / unmapped |
| `A:102:D` | cellule document ETAT A, axe D (MRU résidents), ligne code 102 | **n’existe pas** |
| `B:102:C` | autre espace de codes (ETAT B reprend 101, 102, …) | **n’existe pas** |

Si l’on écrit `A:102:D` dans `rbcm_cell_result.cell_ref` **du même run** (ou si l’UI requête par `campaign_id` sans filtrer le namespace), on **mélange** vérité moteur et document. Un fill « coller `BCM:102` dans D et F » est exactement le risque T0.  
`UNIQUE(run_id, cell_ref)` **n’empêche pas** d’avoir les deux clés côte à côte. Il empêche seulement le doublon **identique**.

**Décision de ce complément :** `RbcmCellResult.cell_ref` **reste** l’espace moteur `BCM:nnn` / `ECART` / synthétiques. **Ne pas** y stocker `A:102:D`. T0 §9 (« réutiliser CellResult avec clé `A:102:D` ») est **incorrect**.

`calculated_value` : **jamais écrasé** par une correction documentaire. Les corrections = INSERT décision. Un nouveau run moteur (plus tard) crée de **nouvelles** lignes résultat. Append-only préservé.

### 3.4 `RbcmCellDecision`

| Élément | Réel |
|---------|------|
| UNIQUE courant | **aucun** — l’historique tient dans `supersedes_decision_id` |
| `cell_ref` | `String(32)` — **même colonne** que le moteur |
| `calculated_value` | copie **figée** au moment de la décision (nullable) |
| `decided_value` | `Numeric(18,2)` nullable |
| `decision_type` | `String(32)` **sans CHECK** |
| `reason` | `Text` **nullable** — T0 exige motif obligatoire → **contrôle applicatif**, pas DB |
| `document_id` | UUID **sans FK** vers `ged_documents` |
| `justificatif_ref` | **absent** (existe sur `rbcm_parameter_value`) |
| `calculation_run_id` | SET NULL — une décision documentaire **peut** vivre sans run moteur |

Réutiliser **le pattern** append-only (`supersedes_decision_id`, copie de `calculated_value`, pas d’UPDATE de fond) : **oui**.  
Réutiliser **la même colonne `cell_ref`** pour `A:102:D` et `BCM:102` : **non**, trop de code (export technique, traces mapping, unmapped) suppose `BCM:`.

Adaptations additives recommandées (l’une des deux, pas les deux) :

1. **Préférée** — table neuve `rbcm_document_decision` (mêmes colonnes métier + `document_cell_key` + `template_cell_id` + `justificatif_ref` NOT NULL côté app). `rbcm_cell_decision` reste moteur.
2. **Minimale** — colonnes `ref_namespace VARCHAR(16) NOT NULL DEFAULT 'ENGINE'` et `document_cell_key VARCHAR(32)` sur `rbcm_cell_decision` ; CHECK `namespace IN ('ENGINE','DOCUMENT')` ; index `(campaign_id, document_cell_key, created_at)`.

Dans les deux cas : **INSERT only**. `RbcmCellResult.calculated_value` **intact**.

### 3.5 `RbcmDeliverable`

| Élément | Réel |
|---------|------|
| UNIQUE | **aucun** — plusieurs fichiers / campagne **déjà possibles** |
| `kind` | `String(16)` (`EXCEL` \| `PDF`) **sans CHECK** |
| `status` | `String(24)` défaut **`GENERATED`**, **sans CHECK** |
| `run_id` | SET NULL |
| `warnings` | JSONB nullable — **déjà prévu** pour l’avertissement WORK |
| `stored_path` | `String(500)` |
| `sha256` | `String(64)` nullable |

**Pas de contrainte qui force l’écrasement.** Une nouvelle génération = **INSERT**. Le risque n’est pas SQL, c’est applicatif : si `generate_excel` **réécrit le même `stored_path`**, le binaire part. T0 test 11/18 : ancien fichier conservé, statut `SUPERSEDED`, SHA distinct.

Manques :

- valeurs `WORK` / `SUPERSEDED` (et `VALIDATED` réservé, non utilisé) non documentées dans un CHECK ;
- pas de `superseded_by_id` ;
- pas de pointeur `campaign.current_work_deliverable_id` — à défaut, « courant » = dernier `status='WORK'` non supersédé ;
- `kind` trop court si l’on invente `EXCEL_WORK` (inutile : `kind=EXCEL` + `status=WORK`).

### 3.6 Corrections append-only et `calculated_value`

Chaîne exigée :

```
RbcmCellResult.calculated_value   — immuable après INSERT
        │ copie au moment de la décision
        ▼
RbcmCellDecision.calculated_value — snapshot
RbcmCellDecision.decided_value    — valeur retenue (document)
        │ overlay à la régénération
        ▼
nouveau RbcmDeliverable WORK      — nouveau SHA, ancien SUPERSEDED
```

Aucun `UPDATE rbcm_cell_result SET calculated_value=…`.  
`retained_value` moteur : hors T3.5-3 (pas de fill mapping).

### 3.7 Tableau d’incompatibilités → adaptations

| Besoin T3.5-3 | Existant | Compatible ? | Adaptation additive |
|---------------|----------|--------------|---------------------|
| Template SHA / 8 feuilles | `template_version_id` orphelin | **non** | `rbcm_template` + `rbcm_template_cell` + FK |
| Clé `A:102:D` | `cell_ref` String(32) moteur | **non** (namespace) | clé documentaire **hors** `CellResult` |
| Graphes de formules | — | **non** | `formula_text` + `nature` enrichie sur `template_cell` |
| Plusieurs WORK | Deliverable sans UNIQUE | **oui** | + statuts WORK/SUPERSEDED + non-réécriture path |
| Motif obligatoire | `reason` nullable | partiel | CHECK app ; option `justificatif_ref` |
| Statut complet/partiel | `CELL_VALUE_STATUSES` moteur | **non** | statuts documentaires §2.6 |
| Banner Excel | `warnings` JSONB | partiel | feuille `AVERTISSEMENT` + header |
| GED | `document_id` sans FK | inchangé | T3.5-3 : texte seulement |

---

## 4. Corrections à apporter au plan T0 initial

| § T0 | Correction |
|------|------------|
| §4 inventaire formules | Était centré ETAT A. **Les 663** sont maintenant classées. B/C/FPN/ratios n’ont **pas** de constante d’octobre en formule. |
| §4.3 30 % | Étendre le badge D09 à **D46, D48, D49** (compléments 70 %). |
| §8.3 watermark | **Interdit d’insérer une ligne** sur les feuilles officielles. Feuille `AVERTISSEMENT` + en-tête/pied de page. |
| §8.4 UI = Python SUM/+ | Conservé, **plus** le graphe complet/partiel/`#DIV/0!` / concordance non interprétable. Ne pas afficher `0,00` pour une formule à deps vides. |
| §9 réutiliser `CellResult` avec `A:102:D` | **Retiré.** `CellResult` = moteur uniquement. Décisions documentaires = table neuve **ou** namespace séparé. |
| §9 `campaign_version` | Ne pas s’en servir pour versionner les WORK. |
| §12 natures `template_cell` | Enrichir : `OCTOBER_CONSTANT_FORMULA`, `OCTOBER_LEAF`, `D09_PCT`, `D09_REMAINDER`, `CONCORDANCE_IF`, `RATIO_DIV`, `METIER_IF`, `CANVAS_NORM`, `SEPARATOR`, `HEADER`, `TOTAL`, `LEAF`. |
| §13 tests 6–7 | Insuffisants. Voir §7 ci-dessous. |
| Décision T0 n°3 (garder 30 % dans le xlsx) | **Oui**, avec badge D09, y compris 70 %. |

Inchangé et réaffirmé : pas de fill `A_VALIDER` ; pas d’ECART ; pas de `runner.py` ; pas de `VALIDATED` ; SHA source figé.

---

## 5. Risques restants

| Risque | Gravité | Mitigation |
|--------|---------|------------|
| Excel affiche 0 / TRUE / sous-total alors que l’UI dit « incomplet » | Élevé | Feuille `AVERTISSEMENT` + header ; UI fait foi ; tests de non-promotion 0 formule → `ZERO_CONFIRME` |
| Coller `BCM:102` dans `A:102:D` (ou dans CellResult mixte) | Élevé | Namespace séparé ; T3.5-3 sans fill mapping |
| Vider G7:G25 / H29 / C27 (normes) en croyant « zéro d’octobre » | Élevé | Seed `CANVAS_NORM` ; tests de conservation `1` / `0.33` / `0.25` / `0.1` / `0.2` |
| Conserver E7:E25 = 0 couverture comme provisions réelles | Moyen | Neutraliser E* couverture |
| `reason` nullable en base | Moyen | Rejet API si motif vide |
| `generate_excel` actuel réécrit un Workbook technique | Moyen | Ne pas l’appeler pour WORK ; nouveau service (lot B) |
| `stored_path` identique entre deux WORK | Moyen | Nommer `{campaign}_{n}_{sha16}.xlsx` |
| String(32) trop juste si l’on stocke `SHEET!ADDR` long | Faible | Ne pas s’en servir ; clé courte `A:102:D` / `RCR:H28` |
| FPN C36 « 0 confirmé » visuel alors que annexes vides | Élevé | `FORMULE_NON_INTERPRETABLE` |
| Utilisateur ouvre xlsx, voit TRUE en colonne L, croit B=A | Élevé | Ne pas présenter L/I comme contrôle OK ; bandeau |

Aucun de ces risques n’est levé par le seul lot T3.5-3-A (cartographie). Ils conditionnent B–D.

---

## 6. Schéma cible recommandé

```
BEA-SM-10-2026.xlsx  (SHA figé, jamais muté)
        │ lecture
        ▼
 rbcm_template
   id, filename, sha256, stored_path, label, is_current
 rbcm_template_cell
   UNIQUE(template_id, sheet_name, excel_address)
   sheet_name, excel_address, bcm_code, axis,
   nature, formula_text, writable, completeness_group
        │
 campaign.template_version_id  ──FK──►  rbcm_template.id
        │
 corrections documentaires (append-only)
 rbcm_document_decision
   campaign_id, template_cell_id, document_cell_key,   -- ex. A:102:D
   calculated_snapshot NULL,                           -- pas de CellResult moteur
   decided_value, decision_type, reason NOT NULL app,
   justificatif_ref, created_by, created_at,
   supersedes_decision_id
        │
 génération WORK (lot B) — PAS runner.py, PAS CellResult
        ▼
 rbcm_deliverable
   kind=EXCEL, status=WORK, run_id NULL,
   sha256, stored_path unique, warnings JSONB
   précédent : status=SUPERSEDED, binaire conservé
        │
 GET document (lot C)
   jointure template_cell + décision courante + graphe deps
   → statut documentaire §2.6  (jamais CellResult.BCM:102)
```

Clés documentaires (toutes ≤ 32, **disjointes** de `BCM:`) :

| Feuille | Motif | Exemple vérifié |
|---------|-------|-----------------|
| ETAT A | `A:{code}:{axe}` axe ∈ C–H | `A:102:D` = ETAT A!D9 |
| ETAT B | `B:{code}:{axe}` | `B:207:E` = ETAT B!E46 (`*30%`) |
| ETAT C | `C:{code}:{axe}` | `C:103:F` |
| CALCUL FPN | `FPN:{addr}` | `FPN:C39` |
| RATIO COUVERTURE DE RISQUE | `RCR:{addr}` | `RCR:H28` |
| RATIO DE LIQUIDITE | `LIQ:{addr}` | `LIQ:C26` |
| RATIO FP ET AI | `FPAI:{addr}` | `FPAI:C16` |
| informations à fournir | `INFO:{addr}` | `INFO:C9` |

`BCM:102` **n’est jamais** une clé document. `A:102:H` (total) ≠ `BCM:102` (scalaire moteur).

Livrables WORK : N versions par campagne, aucune UNIQUE destructive, pas d’UPDATE du binaire, pas d’UPDATE de `calculated_value`.

---

## 7. Tests d’acceptation complémentaires

À ajouter aux 18 tests T0 §13 (banque jetable, jamais SM 11/2026 / 01/2026) :

19. Aucune des 9 formules à constante historique n’est présente dans le WORK généré (recherche des littéraux `588160767`, `2873218`, `5874268360`, …).
20. Les 3 formules `*30%` **et** D46/D48/D49 sont encore dans le xlsx ; l’API les expose `PROVISOIRE_D09`.
21. Pondérations G7:G25, `H29=0.1`, `C27=0.2` **conservées** (non vidées).
22. E7:E25 couverture **vidées** (0 d’octobre, pas une norme).
23. `informations à fournir` C6–C8 / C10–C20 **vides** ; C9 formule conservée.
24. GET document : `H9` (SUM vide) → statut `FORMULE_PARTIELLE` ou `FORMULE_NON_INTERPRETABLE`, **pas** `0,00` / `ZERO_CONFIRME`.
25. GET document : FPN C36 avec annexes vides → **pas** zéro métier.
26. GET document : B L11 / C I8 → `CONTROLE_NON_INTERPRETABLE`, jamais « OK ».
27. GET document : `RCR:H28`, `LIQ:C26`, `FPAI:C16` → `FORMULE_NON_INTERPRETABLE` (`#DIV/0!` / dénominateur vide).
28. Feuille Excel `AVERTISSEMENT` présente ; en-tête de chaque feuille officielle contient « ne constitue pas une validation réglementaire » ; **aucune ligne insérée** (D9 reste D9).
29. `POST` correction `A:102:D` n’écrit **aucune** ligne `rbcm_cell_result` avec `cell_ref` `A:102:D` ni `BCM:102`.
30. `POST` correction n’exécute **pas** `UPDATE` sur `rbcm_cell_result.calculated_value`.
31. Deux WORK : 2 lignes deliverable, 2 SHA, 2 fichiers ; le premier `SUPERSEDED` ; téléchargement des deux OK.
32. `view` ne peut pas générer ; motif vide → 400.
33. Clé `A:102:D` et `BCM:102` coexistantes en base (si un run moteur existe) **sans** collision UNIQUE et **sans** mélange dans GET document.
34. SHA template lu = `54e3b687…` ; fichier `BEA-SM-10-2026.xlsx` bit-identique.

---

## 8. Conclusion

**T3.5-3-A n’est pas démarré.**

| Lot | Statut après ce complément |
|-----|----------------------------|
| **T3.5-3-A** (copie template, SHA, `rbcm_template` / `_cell`, seed natures **enrichies**) | **Prêt après validation explicite** des corrections §4 et du schéma §6 |
| **T3.5-3-B** (fill WORK) | **Pas prêt** tant que faux-zéro §2.5 (banner sans insert row, statuts formule) n’est pas validé |
| **T3.5-3-C/D/E** | Bloqués par B + namespace documentaire ≠ `CellResult` |

Points encore à trancher par validation (pas par code) :

1. Accepter le **retrait** de la réutilisation de `RbcmCellResult` pour `A:102:D`.
2. Accepter feuille `AVERTISSEMENT` + header plutôt qu’une ligne insérée.
3. Accepter que les 30 % **et** 70 % restent dans le xlsx avec badge D09.
4. Emplacement binaire template (T0 décision 4, toujours ouverte).

**Attendre une validation explicite avant toute implémentation.**

---

## Annexe A — Inventaire exhaustif des 663 formules

Colonnes : cellule · formule exacte · nature · décision. Les 9 constantes historiques, les 6 cellules D09 (30 % + 70 %) et les 36 IF / divisions sont les seules à **neutraliser** ou à **statuer en UI**. Les 615 autres sont **conserver**.

### informations à fournir (1 formules)

| Cellule | Formule | Nature | Décision |
|---------|---------|--------|----------|
| C9 | ='ETAT A'!D146 | STRUCTURELLE | conserver |

### ETAT A (306 formules)

| Cellule | Formule | Nature | Décision |
|---------|---------|--------|----------|
| C8 | =+C9+C10 | STRUCTURELLE | conserver |
| D8 | =+D9+D10 | STRUCTURELLE | conserver |
| E8 | =+E9+E10 | STRUCTURELLE | conserver |
| F8 | =+F9+F10 | STRUCTURELLE | conserver |
| G8 | =+G9+G10 | STRUCTURELLE | conserver |
| H8 | =SUM(D8:G8) | STRUCTURELLE | conserver |
| D9 | =588160767-F9 | CONSTANTE_HISTORIQUE | neutraliser — constantes=588160767 |
| H9 | =SUM(D9:G9) | STRUCTURELLE | conserver |
| H10 | =SUM(D10:G10) | STRUCTURELLE | conserver |
| C11 | =+C12+C13 | STRUCTURELLE | conserver |
| D11 | =+D12+D13 | STRUCTURELLE | conserver |
| E11 | =+E12+E13 | STRUCTURELLE | conserver |
| F11 | =+F12+F13 | STRUCTURELLE | conserver |
| G11 | =+G12+G13 | STRUCTURELLE | conserver |
| H11 | =SUM(D11:G11) | STRUCTURELLE | conserver |
| H12 | =SUM(D12:G12) | STRUCTURELLE | conserver |
| H13 | =SUM(D13:G13) | STRUCTURELLE | conserver |
| C14 | =+C15+C20+C24++C28 | STRUCTURELLE | conserver |
| D14 | =+D15+D20+D24++D28 | STRUCTURELLE | conserver |
| E14 | =+E15+E20+E24++E28 | STRUCTURELLE | conserver |
| F14 | =+F15+F20+F24++F28 | STRUCTURELLE | conserver |
| G14 | =+G15+G20+G24++G28 | STRUCTURELLE | conserver |
| H14 | =SUM(D14:G14) | STRUCTURELLE | conserver |
| C15 | =+C16+C17+C18 | STRUCTURELLE | conserver |
| D15 | =+D16+D17+D18 | STRUCTURELLE | conserver |
| E15 | =+E16+E17+E18 | STRUCTURELLE | conserver |
| F15 | =+F16+F17+F18 | STRUCTURELLE | conserver |
| G15 | =+G16+G17+G18 | STRUCTURELLE | conserver |
| H15 | =SUM(D15:G15) | STRUCTURELLE | conserver |
| H16 | =SUM(D16:G16) | STRUCTURELLE | conserver |
| H17 | =SUM(D17:G17) | STRUCTURELLE | conserver |
| H18 | =SUM(D18:G18) | STRUCTURELLE | conserver |
| C20 | =+C21+C22 | STRUCTURELLE | conserver |
| D20 | =+D21+D22 | STRUCTURELLE | conserver |
| E20 | =+E21+E22 | STRUCTURELLE | conserver |
| F20 | =+F21+F22 | STRUCTURELLE | conserver |
| G20 | =+G21+G22 | STRUCTURELLE | conserver |
| H20 | =SUM(D20:G20) | STRUCTURELLE | conserver |
| D21 | =150000000-150000000 | CONSTANTE_HISTORIQUE | neutraliser — constantes=150000000,150000000 |
| H21 | =SUM(D21:G21) | STRUCTURELLE | conserver |
| H22 | =SUM(D22:G22) | STRUCTURELLE | conserver |
| C24 | =+C25+C26 | STRUCTURELLE | conserver |
| D24 | =+D25+D26 | STRUCTURELLE | conserver |
| E24 | =+E25+E26 | STRUCTURELLE | conserver |
| F24 | =+F25+F26 | STRUCTURELLE | conserver |
| G24 | =+G25+G26 | STRUCTURELLE | conserver |
| H24 | =SUM(D24:G24) | STRUCTURELLE | conserver |
| H25 | =SUM(D25:G25) | STRUCTURELLE | conserver |
| H26 | =SUM(D26:G26) | STRUCTURELLE | conserver |
| H28 | =SUM(D28:G28) | STRUCTURELLE | conserver |
| H29 | =SUM(D29:G29) | STRUCTURELLE | conserver |
| H30 | =SUM(D30:G30) | STRUCTURELLE | conserver |
| C32 | =+C33+C34+C35+C36+C37 | STRUCTURELLE | conserver |
| D32 | =+D33+D34+D35+D36+D37 | STRUCTURELLE | conserver |
| E32 | =+E33+E34+E35+E36+E37 | STRUCTURELLE | conserver |
| F32 | =+F33+F34+F35+F36+F37 | STRUCTURELLE | conserver |
| G32 | =+G33+G34+G35+G36+G37 | STRUCTURELLE | conserver |
| H32 | =SUM(D32:G32) | STRUCTURELLE | conserver |
| H33 | =SUM(D33:G33) | STRUCTURELLE | conserver |
| H34 | =SUM(D34:G34) | STRUCTURELLE | conserver |
| H35 | =SUM(D35:G35) | STRUCTURELLE | conserver |
| H36 | =SUM(D36:G36) | STRUCTURELLE | conserver |
| H37 | =SUM(D37:G37) | STRUCTURELLE | conserver |
| D38 | =3972024483-C38-2873218-5 | CONSTANTE_HISTORIQUE | neutraliser — constantes=3972024483,2873218 |
| H38 | =SUM(D38:G38) | STRUCTURELLE | conserver |
| H39 | =SUM(D39:G39) | STRUCTURELLE | conserver |
| H40 | =SUM(D40:G40) | STRUCTURELLE | conserver |
| H41 | =SUM(D41:G41) | STRUCTURELLE | conserver |
| H42 | =SUM(D42:G42) | STRUCTURELLE | conserver |
| H43 | =SUM(D43:G43) | STRUCTURELLE | conserver |
| C44 | =+C45+C46 | STRUCTURELLE | conserver |
| D44 | =+D45+D46 | STRUCTURELLE | conserver |
| E44 | =+E45+E46 | STRUCTURELLE | conserver |
| F44 | =+F45+F46 | STRUCTURELLE | conserver |
| G44 | =+G45+G46 | STRUCTURELLE | conserver |
| H44 | =SUM(D44:G44) | STRUCTURELLE | conserver |
| H45 | =SUM(D45:G45) | STRUCTURELLE | conserver |
| H46 | =SUM(D46:G46) | STRUCTURELLE | conserver |
| H47 | =SUM(D47:G47) | STRUCTURELLE | conserver |
| H48 | =SUM(D48:G48) | STRUCTURELLE | conserver |
| C50 | =SUM(C51:C54) | STRUCTURELLE | conserver |
| D50 | =SUM(D51:D54) | STRUCTURELLE | conserver |
| E50 | =SUM(E51:E54) | STRUCTURELLE | conserver |
| F50 | =SUM(F51:F54) | STRUCTURELLE | conserver |
| G50 | =SUM(G51:G54) | STRUCTURELLE | conserver |
| H50 | =SUM(D50:G50) | STRUCTURELLE | conserver |
| H51 | =SUM(D51:G51) | STRUCTURELLE | conserver |
| H52 | =SUM(D52:G52) | STRUCTURELLE | conserver |
| H53 | =SUM(D53:G53) | STRUCTURELLE | conserver |
| H54 | =SUM(D54:G54) | STRUCTURELLE | conserver |
| H55 | =SUM(D55:G55) | STRUCTURELLE | conserver |
| C56 | =+C57+C58 | STRUCTURELLE | conserver |
| D56 | =+D57+D58 | STRUCTURELLE | conserver |
| E56 | =+E57+E58 | STRUCTURELLE | conserver |
| F56 | =+F57+F58 | STRUCTURELLE | conserver |
| G56 | =+G57+G58 | STRUCTURELLE | conserver |
| H56 | =SUM(D56:G56) | STRUCTURELLE | conserver |
| H57 | =SUM(D57:G57) | STRUCTURELLE | conserver |
| H58 | =SUM(D58:G58) | STRUCTURELLE | conserver |
| C59 | =+C60+C61 | STRUCTURELLE | conserver |
| D59 | =+D60+D61 | STRUCTURELLE | conserver |
| E59 | =+E60+E61 | STRUCTURELLE | conserver |
| F59 | =+F60+F61 | STRUCTURELLE | conserver |
| G59 | =+G60+G61 | STRUCTURELLE | conserver |
| H59 | =SUM(D59:G59) | STRUCTURELLE | conserver |
| H60 | =SUM(D60:G60) | STRUCTURELLE | conserver |
| H61 | =SUM(D61:G61) | STRUCTURELLE | conserver |
| H62 | =SUM(D62:G62) | STRUCTURELLE | conserver |
| H64 | =SUM(D64:G64) | STRUCTURELLE | conserver |
| C65 | =+C66+C67+C68 | STRUCTURELLE | conserver |
| D65 | =+D66+D67+D68 | STRUCTURELLE | conserver |
| E65 | =+E66+E67+E68 | STRUCTURELLE | conserver |
| F65 | =+F66+F67+F68 | STRUCTURELLE | conserver |
| G65 | =+G66+G67+G68 | STRUCTURELLE | conserver |
| H65 | =SUM(D65:G65) | STRUCTURELLE | conserver |
| H66 | =SUM(D66:G66) | STRUCTURELLE | conserver |
| H67 | =SUM(D67:G67) | STRUCTURELLE | conserver |
| H68 | =SUM(D68:G68) | STRUCTURELLE | conserver |
| C69 | =+C70+C71+C72 | STRUCTURELLE | conserver |
| D69 | =+D70+D71+D72 | STRUCTURELLE | conserver |
| E69 | =+E70+E71+E72 | STRUCTURELLE | conserver |
| F69 | =+F70+F71+F72 | STRUCTURELLE | conserver |
| G69 | =+G70+G71+G72 | STRUCTURELLE | conserver |
| H69 | =SUM(D69:G69) | STRUCTURELLE | conserver |
| H70 | =SUM(D70:G70) | STRUCTURELLE | conserver |
| H71 | =SUM(D71:G71) | STRUCTURELLE | conserver |
| H72 | =SUM(D72:G72) | STRUCTURELLE | conserver |
| H73 | =SUM(D73:G73) | STRUCTURELLE | conserver |
| C74 | =+C75+C76 | STRUCTURELLE | conserver |
| D74 | =+D75+D76 | STRUCTURELLE | conserver |
| E74 | =+E75+E76 | STRUCTURELLE | conserver |
| F74 | =+F75+F76 | STRUCTURELLE | conserver |
| G74 | =+G75+G76 | STRUCTURELLE | conserver |
| H74 | =SUM(D74:G74) | STRUCTURELLE | conserver |
| D75 | =53348003-C75 | CONSTANTE_HISTORIQUE | neutraliser — constantes=53348003 |
| H75 | =SUM(D75:G75) | STRUCTURELLE | conserver |
| D76 | =77770480-C76 | CONSTANTE_HISTORIQUE | neutraliser — constantes=77770480 |
| H76 | =SUM(D76:G76) | STRUCTURELLE | conserver |
| H77 | =SUM(D77:G77) | STRUCTURELLE | conserver |
| H78 | =SUM(D78:G78) | STRUCTURELLE | conserver |
| H79 | =SUM(D79:G79) | STRUCTURELLE | conserver |
| H80 | =SUM(D80:G80) | STRUCTURELLE | conserver |
| C81 | =+C80+C79+C78+C77+C74+C73+C69+C65+C64+C62+C59+C56+C55+C50+C48+C47+C44+C43+C42+C41+C40+C39+C38+C32+C30+C29+C28+C14+C11+C8 | STRUCTURELLE | conserver |
| D81 | =+D80+D79+D78+D77+D74+D73+D69+D65+D64+D62+D59+D56+D55+D50+D48+D47+D44+D43+D42+D41+D40+D39+D38+D32+D30+D29+D28+D14+D11+D8 | STRUCTURELLE | conserver |
| E81 | =+E80+E79+E78+E77+E74+E73+E69+E65+E64+E62+E59+E56+E55+E50+E48+E47+E44+E43+E42+E41+E40+E39+E38+E32+E30+E29+E28+E14+E11+E8 | STRUCTURELLE | conserver |
| F81 | =+F80+F79+F78+F77+F74+F73+F69+F65+F64+F62+F59+F56+F55+F50+F48+F47+F44+F43+F42+F41+F40+F39+F38+F32+F30+F29+F28+F14+F11+F8 | STRUCTURELLE | conserver |
| G81 | =+G80+G79+G78+G77+G74+G73+G69+G65+G64+G62+G59+G56+G55+G50+G48+G47+G44+G43+G42+G41+G40+G39+G38+G32+G30+G29+G28+G14+G11+G8 | STRUCTURELLE | conserver |
| H81 | =SUM(D81:G81) | STRUCTURELLE | conserver |
| H85 | =SUM(D85:G85) | STRUCTURELLE | conserver |
| D86 | =+D87+D92+D96 | STRUCTURELLE | conserver |
| E86 | =+E87+E92+E96 | STRUCTURELLE | conserver |
| F86 | =+F87+F92+F96 | STRUCTURELLE | conserver |
| G86 | =+G87+G92+G96 | STRUCTURELLE | conserver |
| H86 | =SUM(D86:G86) | STRUCTURELLE | conserver |
| D87 | =+D88+D89+D90 | STRUCTURELLE | conserver |
| E87 | =+E88+E89+E90 | STRUCTURELLE | conserver |
| F87 | =+F88+F89+F90 | STRUCTURELLE | conserver |
| G87 | =+G88+G89+G90 | STRUCTURELLE | conserver |
| H87 | =SUM(D87:G87) | STRUCTURELLE | conserver |
| H88 | =SUM(D88:G88) | STRUCTURELLE | conserver |
| H89 | =SUM(D89:G89) | STRUCTURELLE | conserver |
| H90 | =SUM(D90:G90) | STRUCTURELLE | conserver |
| D92 | =+D93+D94 | STRUCTURELLE | conserver |
| E92 | =+E93+E94 | STRUCTURELLE | conserver |
| F92 | =+F93+F94 | STRUCTURELLE | conserver |
| G92 | =+G93+G94 | STRUCTURELLE | conserver |
| H92 | =SUM(D92:G92) | STRUCTURELLE | conserver |
| H93 | =SUM(D93:G93) | STRUCTURELLE | conserver |
| H94 | =SUM(D94:G94) | STRUCTURELLE | conserver |
| D96 | =+D97+D98 | STRUCTURELLE | conserver |
| E96 | =+E97+E98 | STRUCTURELLE | conserver |
| F96 | =+F97+F98 | STRUCTURELLE | conserver |
| G96 | =+G97+G98 | STRUCTURELLE | conserver |
| H96 | =SUM(D96:G96) | STRUCTURELLE | conserver |
| H97 | =SUM(D97:G97) | STRUCTURELLE | conserver |
| H98 | =SUM(D98:G98) | STRUCTURELLE | conserver |
| H100 | =SUM(D100:G100) | STRUCTURELLE | conserver |
| D101 | =+D102+D103 | STRUCTURELLE | conserver |
| E101 | =+E102+E103 | STRUCTURELLE | conserver |
| F101 | =+F102+F103 | STRUCTURELLE | conserver |
| G101 | =+G102+G103 | STRUCTURELLE | conserver |
| H101 | =SUM(D101:G101) | STRUCTURELLE | conserver |
| H102 | =SUM(D102:G102) | STRUCTURELLE | conserver |
| H103 | =SUM(D103:G103) | STRUCTURELLE | conserver |
| D104 | =+D105+D110+D115+D119 | STRUCTURELLE | conserver |
| E104 | =+E105+E110+E115+E119 | STRUCTURELLE | conserver |
| F104 | =+F105+F110+F115+F119 | STRUCTURELLE | conserver |
| G104 | =+G105+G110+G115+G119 | STRUCTURELLE | conserver |
| H104 | =SUM(D104:G104) | STRUCTURELLE | conserver |
| D105 | =+D106+D107+D108+D109 | STRUCTURELLE | conserver |
| E105 | =+E106+E107+E108+E109 | STRUCTURELLE | conserver |
| F105 | =+F106+F107+F108+F109 | STRUCTURELLE | conserver |
| G105 | =+G106+G107+G108+G109 | STRUCTURELLE | conserver |
| H105 | =SUM(D105:G105) | STRUCTURELLE | conserver |
| D106 | =331024347.65-F106 | CONSTANTE_HISTORIQUE | neutraliser — constantes=331024347.65 |
| H106 | =SUM(D106:G106) | STRUCTURELLE | conserver |
| H107 | =SUM(D107:G107) | STRUCTURELLE | conserver |
| H108 | =SUM(D108:G108) | STRUCTURELLE | conserver |
| H109 | =SUM(D109:G109) | STRUCTURELLE | conserver |
| D110 | =+D111+D112+D113+D114 | STRUCTURELLE | conserver |
| E110 | =+E111+E112+E113+E114 | STRUCTURELLE | conserver |
| F110 | =+F111+F112+F113+F114 | STRUCTURELLE | conserver |
| G110 | =+G111+G112+G113+G114 | STRUCTURELLE | conserver |
| H110 | =SUM(D110:G110) | STRUCTURELLE | conserver |
| H111 | =SUM(D111:G111) | STRUCTURELLE | conserver |
| D112 | =737956675-D111 | CONSTANTE_HISTORIQUE | neutraliser — constantes=737956675 |
| H112 | =SUM(D112:G112) | STRUCTURELLE | conserver |
| H113 | =SUM(D113:G113) | STRUCTURELLE | conserver |
| H114 | =SUM(D114:G114) | STRUCTURELLE | conserver |
| D115 | =+D116 | STRUCTURELLE | conserver |
| E115 | =+E116 | STRUCTURELLE | conserver |
| F115 | =+F116 | STRUCTURELLE | conserver |
| G115 | =+G116 | STRUCTURELLE | conserver |
| H115 | =SUM(D115:G115) | STRUCTURELLE | conserver |
| H116 | =SUM(D116:G116) | STRUCTURELLE | conserver |
| H119 | =SUM(D119:G119) | STRUCTURELLE | conserver |
| H120 | =SUM(D120:G120) | STRUCTURELLE | conserver |
| H121 | =SUM(D121:G121) | STRUCTURELLE | conserver |
| H122 | =SUM(D122:G122) | STRUCTURELLE | conserver |
| D123 | =463722024+296461984-21 | CONSTANTE_HISTORIQUE | neutraliser — constantes=463722024,296461984 |
| H123 | =SUM(D123:G123) | STRUCTURELLE | conserver |
| H124 | =SUM(D124:G124) | STRUCTURELLE | conserver |
| D126 | =+D127+D128+D129+D130 | STRUCTURELLE | conserver |
| E126 | =+E127+E128+E129+E130 | STRUCTURELLE | conserver |
| F126 | =+F127+F128+F129+F130 | STRUCTURELLE | conserver |
| G126 | =+G127+G128+G129+G130 | STRUCTURELLE | conserver |
| H126 | =SUM(D126:G126) | STRUCTURELLE | conserver |
| H127 | =SUM(D127:G127) | STRUCTURELLE | conserver |
| H128 | =SUM(D128:G128) | STRUCTURELLE | conserver |
| H129 | =SUM(D129:G129) | STRUCTURELLE | conserver |
| H130 | =SUM(D130:G130) | STRUCTURELLE | conserver |
| H131 | =SUM(D131:G131) | STRUCTURELLE | conserver |
| H132 | =SUM(D132:G132) | STRUCTURELLE | conserver |
| H133 | =SUM(D133:G133) | STRUCTURELLE | conserver |
| D134 | =+D135+D136+D137 | STRUCTURELLE | conserver |
| E134 | =+E135+E136+E137 | STRUCTURELLE | conserver |
| F134 | =+F135+F136+F137 | STRUCTURELLE | conserver |
| G134 | =+G135+G136+G137 | STRUCTURELLE | conserver |
| H134 | =SUM(D134:G134) | STRUCTURELLE | conserver |
| H135 | =SUM(D135:G135) | STRUCTURELLE | conserver |
| H136 | =SUM(D136:G136) | STRUCTURELLE | conserver |
| H137 | =SUM(D137:G137) | STRUCTURELLE | conserver |
| H138 | =SUM(D138:G138) | STRUCTURELLE | conserver |
| H139 | =SUM(D139:G139) | STRUCTURELLE | conserver |
| D140 | =+D141+D142 | STRUCTURELLE | conserver |
| E140 | =+E141+E142 | STRUCTURELLE | conserver |
| F140 | =+F141+F142 | STRUCTURELLE | conserver |
| G140 | =+G141+G142 | STRUCTURELLE | conserver |
| H140 | =SUM(D140:G140) | STRUCTURELLE | conserver |
| H141 | =SUM(D141:G141) | STRUCTURELLE | conserver |
| H142 | =SUM(D142:G142) | STRUCTURELLE | conserver |
| H143 | =SUM(D143:G143) | STRUCTURELLE | conserver |
| H144 | =SUM(D144:G144) | STRUCTURELLE | conserver |
| H145 | =SUM(D145:G145) | STRUCTURELLE | conserver |
| H146 | =SUM(D146:G146) | STRUCTURELLE | conserver |
| D147 | =+D146+D145+D144+D143+D140+D139+D138+D134+D133+D132+D131+D126+D124+D123+D122+D121+D120+D104+D101+D100+D86+D85 | STRUCTURELLE | conserver |
| E147 | =+E146+E145+E144+E143+E140+E139+E138+E134+E133+E132+E131+E126+E124+E123+E122+E121+E120+E104+E101+E100+E86+E85 | STRUCTURELLE | conserver |
| F147 | =+F146+F145+F144+F143+F140+F139+F138+F134+F133+F132+F131+F126+F124+F123+F122+F121+F120+F104+F101+F100+F86+F85 | STRUCTURELLE | conserver |
| G147 | =+G146+G145+G144+G143+G140+G139+G138+G134+G133+G132+G131+G126+G124+G123+G122+G121+G120+G104+G101+G100+G86+G85 | STRUCTURELLE | conserver |
| H147 | =SUM(D147:G147) | STRUCTURELLE | conserver |
| I147 | =+H147-H81 | STRUCTURELLE | conserver |
| D152 | =+D153+D154+D155+D156 | STRUCTURELLE | conserver |
| E152 | =+E153+E154+E155+E156 | STRUCTURELLE | conserver |
| F152 | =+F153+F154+F155+F156 | STRUCTURELLE | conserver |
| G152 | =+G153+G154+G155+G156 | STRUCTURELLE | conserver |
| H152 | =SUM(D152:G152) | STRUCTURELLE | conserver |
| H153 | =SUM(D153:G153) | STRUCTURELLE | conserver |
| H154 | =SUM(D154:G154) | STRUCTURELLE | conserver |
| H155 | =SUM(D155:G155) | STRUCTURELLE | conserver |
| H156 | =SUM(D156:G156) | STRUCTURELLE | conserver |
| D157 | =+D158+D159 | STRUCTURELLE | conserver |
| E157 | =+E158+E159 | STRUCTURELLE | conserver |
| F157 | =+F158+F159 | STRUCTURELLE | conserver |
| G157 | =+G158+G159 | STRUCTURELLE | conserver |
| H157 | =SUM(D157:G157) | STRUCTURELLE | conserver |
| H158 | =SUM(D158:G158) | STRUCTURELLE | conserver |
| H159 | =SUM(D159:G159) | STRUCTURELLE | conserver |
| D160 | =+D161+D162+D165+D168+D169 | STRUCTURELLE | conserver |
| E160 | =+E161+E162+E165+E168+E169 | STRUCTURELLE | conserver |
| F160 | =+F161+F162+F165+F168+F169 | STRUCTURELLE | conserver |
| G160 | =+G161+G162+G165+G168+G169 | STRUCTURELLE | conserver |
| H160 | =SUM(D160:G160) | STRUCTURELLE | conserver |
| H161 | =SUM(D161:G161) | STRUCTURELLE | conserver |
| D162 | =+D163+D164 | STRUCTURELLE | conserver |
| E162 | =+E163+E164 | STRUCTURELLE | conserver |
| F162 | =+F163+F164 | STRUCTURELLE | conserver |
| G162 | =+G163+G164 | STRUCTURELLE | conserver |
| H162 | =SUM(D162:G162) | STRUCTURELLE | conserver |
| H163 | =SUM(D163:G163) | STRUCTURELLE | conserver |
| H164 | =SUM(D164:G164) | STRUCTURELLE | conserver |
| D165 | =+D166+D167 | STRUCTURELLE | conserver |
| E165 | =+E166+E167 | STRUCTURELLE | conserver |
| F165 | =+F166+F167 | STRUCTURELLE | conserver |
| G165 | =+G166+G167 | STRUCTURELLE | conserver |
| H165 | =SUM(D165:G165) | STRUCTURELLE | conserver |
| H166 | =SUM(D166:G166) | STRUCTURELLE | conserver |
| D167 | =5874268360-G167 | CONSTANTE_HISTORIQUE | neutraliser — constantes=5874268360 |
| H167 | =SUM(D167:G167) | STRUCTURELLE | conserver |
| H168 | =SUM(D168:G168) | STRUCTURELLE | conserver |
| H169 | =SUM(D169:G169) | STRUCTURELLE | conserver |
| H170 | =SUM(D170:G170) | STRUCTURELLE | conserver |
| D171 | =+D160 | STRUCTURELLE | conserver |
| E171 | =+E160 | STRUCTURELLE | conserver |
| F171 | =+F160 | STRUCTURELLE | conserver |
| G171 | =+G160 | STRUCTURELLE | conserver |
| H171 | =SUM(D171:G171) | STRUCTURELLE | conserver |

### ETAT B (136 formules)

| Cellule | Formule | Nature | Décision |
|---------|---------|--------|----------|
| C8 | =+C9+C10 | STRUCTURELLE | conserver |
| D8 | =+D9+D10 | STRUCTURELLE | conserver |
| E8 | =+E9+E10 | STRUCTURELLE | conserver |
| F8 | =+F9+F10 | STRUCTURELLE | conserver |
| G8 | =+G9+G10 | STRUCTURELLE | conserver |
| H8 | =+H9+H10 | STRUCTURELLE | conserver |
| I8 | =SUM(C8:H8) | STRUCTURELLE | conserver |
| I9 | =SUM(C9:H9) | STRUCTURELLE | conserver |
| I10 | =SUM(C10:H10) | STRUCTURELLE | conserver |
| C11 | =+C12+C13 | STRUCTURELLE | conserver |
| D11 | =+D12+D13 | STRUCTURELLE | conserver |
| E11 | =+E12+E13 | STRUCTURELLE | conserver |
| F11 | =+F12+F13 | STRUCTURELLE | conserver |
| G11 | =+G12+G13 | STRUCTURELLE | conserver |
| H11 | =+H12+H13 | STRUCTURELLE | conserver |
| I11 | =SUM(C11:H11) | STRUCTURELLE | conserver |
| L11 | =IF('ETAT A'!H33+'ETAT A'!C33=I11,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| D12 | =+'ETAT A'!D33 | STRUCTURELLE | conserver |
| I12 | =SUM(C12:H12) | STRUCTURELLE | conserver |
| I13 | =SUM(C13:H13) | STRUCTURELLE | conserver |
| C14 | =+C15 | STRUCTURELLE | conserver |
| D14 | =+D15 | STRUCTURELLE | conserver |
| E14 | =+E15 | STRUCTURELLE | conserver |
| F14 | =+F15 | STRUCTURELLE | conserver |
| G14 | =+G15 | STRUCTURELLE | conserver |
| H14 | =+H15 | STRUCTURELLE | conserver |
| I14 | =SUM(C14:H14) | STRUCTURELLE | conserver |
| C15 | =+C16+C17+C18+C19 | STRUCTURELLE | conserver |
| D15 | =+D16+D17+D18+D19 | STRUCTURELLE | conserver |
| E15 | =+E16+E17+E18+E19 | STRUCTURELLE | conserver |
| F15 | =+F16+F17+F18+F19 | STRUCTURELLE | conserver |
| G15 | =+G16+G17+G18+G19 | STRUCTURELLE | conserver |
| H15 | =+H16+H17+H18+H19 | STRUCTURELLE | conserver |
| I15 | =SUM(C15:H15) | STRUCTURELLE | conserver |
| I16 | =SUM(C16:H16) | STRUCTURELLE | conserver |
| I17 | =SUM(C17:H17) | STRUCTURELLE | conserver |
| I18 | =SUM(C18:H18) | STRUCTURELLE | conserver |
| I19 | =SUM(C19:H19) | STRUCTURELLE | conserver |
| C20 | =+C21+C22+C23+C29+C30 | STRUCTURELLE | conserver |
| D20 | =+D21+D22+D23+D29+D30 | STRUCTURELLE | conserver |
| E20 | =+E21+E22+E23+E29+E30 | STRUCTURELLE | conserver |
| F20 | =+F21+F22+F23+F29+F30 | STRUCTURELLE | conserver |
| G20 | =+G21+G22+G23+G29+G30 | STRUCTURELLE | conserver |
| H20 | =+H21+H22+H23+H29+H30 | STRUCTURELLE | conserver |
| I20 | =SUM(C20:H20) | STRUCTURELLE | conserver |
| L20 | =IF('ETAT A'!H34+'ETAT A'!C34=I20,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| I21 | =SUM(C21:H21) | STRUCTURELLE | conserver |
| I22 | =SUM(C22:H22) | STRUCTURELLE | conserver |
| C23 | =+C24+C25+C26+C27+C28 | STRUCTURELLE | conserver |
| D23 | =+D24+D25+D26+D27+D28 | STRUCTURELLE | conserver |
| E23 | =+E24+E25+E26+E27+E28 | STRUCTURELLE | conserver |
| F23 | =+F24+F25+F26+F27+F28 | STRUCTURELLE | conserver |
| G23 | =+G24+G25+G26+G27+G28 | STRUCTURELLE | conserver |
| H23 | =+H24+H25+H26+H27+H28 | STRUCTURELLE | conserver |
| I23 | =SUM(C23:H23) | STRUCTURELLE | conserver |
| I24 | =SUM(C24:H24) | STRUCTURELLE | conserver |
| I25 | =SUM(C25:H25) | STRUCTURELLE | conserver |
| I26 | =SUM(C26:H26) | STRUCTURELLE | conserver |
| E27 | =+'ETAT A'!D163-'ETAT B'!D27 | STRUCTURELLE | conserver |
| I27 | =SUM(C27:H27) | STRUCTURELLE | conserver |
| I28 | =SUM(C28:H28) | STRUCTURELLE | conserver |
| I29 | =SUM(C29:H29) | STRUCTURELLE | conserver |
| C30 | =+C31+C32 | STRUCTURELLE | conserver |
| D30 | =+D31+D32 | STRUCTURELLE | conserver |
| E30 | =+E31+E32 | STRUCTURELLE | conserver |
| F30 | =+F31+F32 | STRUCTURELLE | conserver |
| G30 | =+G31+G32 | STRUCTURELLE | conserver |
| H30 | =+H31+H32 | STRUCTURELLE | conserver |
| I30 | =SUM(C30:H30) | STRUCTURELLE | conserver |
| F31 | =+'ETAT A'!D34 | STRUCTURELLE | conserver |
| I31 | =SUM(C31:H31) | STRUCTURELLE | conserver |
| I32 | =SUM(C32:H32) | STRUCTURELLE | conserver |
| C33 | =+C34+C35 | STRUCTURELLE | conserver |
| D33 | =+D34+D35 | STRUCTURELLE | conserver |
| E33 | =+E34+E35 | STRUCTURELLE | conserver |
| F33 | =+F34+F35 | STRUCTURELLE | conserver |
| G33 | =+G34+G35 | STRUCTURELLE | conserver |
| H33 | =+H34+H35 | STRUCTURELLE | conserver |
| I33 | =SUM(C33:H33) | STRUCTURELLE | conserver |
| I34 | =SUM(C34:H34) | STRUCTURELLE | conserver |
| I35 | =SUM(C35:H35) | STRUCTURELLE | conserver |
| C36 | =+C37+C38+C39 | STRUCTURELLE | conserver |
| D36 | =+D37+D38+D39 | STRUCTURELLE | conserver |
| E36 | =+E37+E38+E39 | STRUCTURELLE | conserver |
| F36 | =+F37+F38+F39 | STRUCTURELLE | conserver |
| G36 | =+G37+G38+G39 | STRUCTURELLE | conserver |
| H36 | =+H37+H38+H39 | STRUCTURELLE | conserver |
| I36 | =SUM(C36:H36) | STRUCTURELLE | conserver |
| L36 | =IF('ETAT A'!H35+'ETAT A'!C35=I36,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| I37 | =SUM(C37:H37) | STRUCTURELLE | conserver |
| I38 | =SUM(C38:H38) | STRUCTURELLE | conserver |
| E39 | =+'ETAT A'!D35 | STRUCTURELLE | conserver |
| I39 | =SUM(C39:H39) | STRUCTURELLE | conserver |
| C40 | =+C41+C42+C43 | STRUCTURELLE | conserver |
| D40 | =+D41+D42+D43 | STRUCTURELLE | conserver |
| E40 | =+E41+E42+E43 | STRUCTURELLE | conserver |
| F40 | =+F41+F42+F43 | STRUCTURELLE | conserver |
| G40 | =+G41+G42+G43 | STRUCTURELLE | conserver |
| H40 | =+H41+H42+H43 | STRUCTURELLE | conserver |
| I40 | =SUM(C40:H40) | STRUCTURELLE | conserver |
| L40 | =IF('ETAT A'!H36+'ETAT A'!C36=I40,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| I41 | =SUM(C41:H41) | STRUCTURELLE | conserver |
| I42 | =SUM(C42:H42) | STRUCTURELLE | conserver |
| E43 | =+'ETAT A'!D36 | STRUCTURELLE | conserver |
| I43 | =SUM(C43:H43) | STRUCTURELLE | conserver |
| I44 | =SUM(C44:H44) | STRUCTURELLE | conserver |
| L44 | =IF('ETAT A'!H37+'ETAT A'!C37=I44,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| I45 | =SUM(C45:H45) | STRUCTURELLE | conserver |
| D46 | =+('ETAT A'!C38+'ETAT A'!D38)-E46 | STRUCTURELLE_INTERFEUILLE | conserver |
| E46 | =+('ETAT A'!C38+'ETAT A'!D38)*30% | METIER_D09 | conserver_provisoire_D09 — 30% |
| I46 | =SUM(C46:H46) | STRUCTURELLE | conserver |
| L46 | =IF('ETAT A'!H38+'ETAT A'!C38=I46,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| D47 | =+'ETAT A'!D39 | STRUCTURELLE | conserver |
| I47 | =SUM(C47:H47) | STRUCTURELLE | conserver |
| L47 | =IF('ETAT A'!H39+'ETAT A'!C39=I47,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| D48 | =+'ETAT A'!D40-E48 | STRUCTURELLE | conserver |
| E48 | =+'ETAT A'!D40*30% | METIER_D09 | conserver_provisoire_D09 — 30% |
| I48 | =SUM(C48:H48) | STRUCTURELLE | conserver |
| L48 | =IF('ETAT A'!H40+'ETAT A'!C40=I48,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| D49 | =+'ETAT A'!D41-E49 | STRUCTURELLE | conserver |
| E49 | =+'ETAT A'!D41*30% | METIER_D09 | conserver_provisoire_D09 — 30% |
| I49 | =SUM(C49:H49) | STRUCTURELLE | conserver |
| L49 | =IF('ETAT A'!H41+'ETAT A'!C41=I49,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| I51 | =SUM(C51:H51) | STRUCTURELLE | conserver |
| L51 | =IF('ETAT A'!H45+'ETAT A'!C45=I51,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| I52 | =SUM(C52:H52) | STRUCTURELLE | conserver |
| L52 | =IF('ETAT A'!H70+'ETAT A'!C70=I52,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| I53 | =SUM(C53:H53) | STRUCTURELLE | conserver |
| L53 | =IF('ETAT A'!H64+'ETAT A'!C64=I53,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| C55 | =+C53+C52+C51+C49+C48+C47+C46+C45+C44+C40+C36+C33+C20+C14+C11+C8 | STRUCTURELLE | conserver |
| D55 | =+D53+D52+D51+D49+D48+D47+D46+D45+D44+D40+D36+D33+D20+D14+D11+D8 | STRUCTURELLE | conserver |
| E55 | =+E53+E52+E51+E49+E48+E47+E46+E45+E44+E40+E36+E33+E20+E14+E11+E8 | STRUCTURELLE | conserver |
| F55 | =+F53+F52+F51+F49+F48+F47+F46+F45+F44+F40+F36+F33+F20+F14+F11+F8 | STRUCTURELLE | conserver |
| G55 | =+G53+G52+G51+G49+G48+G47+G46+G45+G44+G40+G36+G33+G20+G14+G11+G8 | STRUCTURELLE | conserver |
| H55 | =+H53+H52+H51+H49+H48+H47+H46+H45+H44+H40+H36+H33+H20+H14+H11+H8 | STRUCTURELLE | conserver |
| I55 | =SUM(C55:H55) | STRUCTURELLE | conserver |

### ETAT C (92 formules)

| Cellule | Formule | Nature | Décision |
|---------|---------|--------|----------|
| C6 | =+C7+C8 | STRUCTURELLE | conserver |
| D6 | =+D7+D8 | STRUCTURELLE | conserver |
| E6 | =+E7+E8 | STRUCTURELLE | conserver |
| F6 | =SUM(C6:E6) | STRUCTURELLE | conserver |
| F7 | =SUM(C7:E7) | STRUCTURELLE | conserver |
| F8 | =SUM(C8:E8) | STRUCTURELLE | conserver |
| I8 | =IF('ETAT A'!H29=F8,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| C9 | =+C10+C11+C12 | STRUCTURELLE | conserver |
| D9 | =+D10+D11+D12 | STRUCTURELLE | conserver |
| E9 | =+E10+E11+E12 | STRUCTURELLE | conserver |
| F9 | =SUM(C9:E9) | STRUCTURELLE | conserver |
| I9 | =IF('ETAT A'!H30=F9,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F10 | =SUM(C10:E10) | STRUCTURELLE | conserver |
| F11 | =SUM(C11:E11) | STRUCTURELLE | conserver |
| F12 | =SUM(C12:E12) | STRUCTURELLE | conserver |
| C13 | =+C14+C15+C16+C17+C18+C19+C20 | STRUCTURELLE | conserver |
| D13 | =+D14+D15+D16+D17+D18+D19+D20 | STRUCTURELLE | conserver |
| E13 | =+E14+E15+E16+E17+E18+E19+E20 | STRUCTURELLE | conserver |
| F13 | =SUM(C13:E13) | STRUCTURELLE | conserver |
| F14 | =SUM(C14:E14) | STRUCTURELLE | conserver |
| D15 | =+'ETAT B'!D12 | STRUCTURELLE | conserver |
| F15 | =SUM(C15:E15) | STRUCTURELLE | conserver |
| I15 | =IF('ETAT A'!H33=F15,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F16 | =SUM(C16:E16) | STRUCTURELLE | conserver |
| D17 | =+'ETAT B'!F31 | STRUCTURELLE | conserver |
| F17 | =SUM(C17:E17) | STRUCTURELLE | conserver |
| I17 | =IF('ETAT A'!H34=F17,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F18 | =SUM(C18:E18) | STRUCTURELLE | conserver |
| D19 | =+'ETAT B'!E39 | STRUCTURELLE | conserver |
| F19 | =SUM(C19:E19) | STRUCTURELLE | conserver |
| I19 | =IF('ETAT A'!H35=F19,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| E20 | =+'ETAT B'!E43 | STRUCTURELLE | conserver |
| F20 | =SUM(C20:E20) | STRUCTURELLE | conserver |
| I20 | =IF('ETAT A'!H36=F20,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| C21 | =+C22+C23 | STRUCTURELLE | conserver |
| F21 | =SUM(C21:E21) | STRUCTURELLE | conserver |
| F22 | =SUM(C22:E22) | STRUCTURELLE | conserver |
| I22 | =IF('ETAT A'!H70=F22,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F23 | =SUM(C23:E23) | STRUCTURELLE | conserver |
| I23 | =IF('ETAT A'!H71=F23,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F24 | =SUM(C24:E24) | STRUCTURELLE | conserver |
| I24 | =IF('ETAT A'!H64=F24,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| C25 | =+C24+C21+C13+C9+C6 | STRUCTURELLE | conserver |
| D25 | =+D24+D21+D13+D9+D6 | STRUCTURELLE | conserver |
| E25 | =+E24+E21+E13+E9+E6 | STRUCTURELLE | conserver |
| F25 | =SUM(C25:E25) | STRUCTURELLE | conserver |
| C28 | =+C29+C30 | STRUCTURELLE | conserver |
| D28 | =+D29+D30 | STRUCTURELLE | conserver |
| E28 | =+E29+E30 | STRUCTURELLE | conserver |
| F28 | =SUM(C28:E28) | STRUCTURELLE | conserver |
| F29 | =SUM(C29:E29) | STRUCTURELLE | conserver |
| E30 | =+'ETAT A'!D97+'ETAT A'!G97 | STRUCTURELLE | conserver |
| F30 | =SUM(C30:E30) | STRUCTURELLE | conserver |
| I30 | =IF('ETAT A'!H96=F30,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| C31 | =+C32+C33+C34 | STRUCTURELLE | conserver |
| D31 | =+D32+D33+D34 | STRUCTURELLE | conserver |
| E31 | =+E32+E33+E34 | STRUCTURELLE | conserver |
| F31 | =SUM(C31:E31) | STRUCTURELLE | conserver |
| I31 | =IF('ETAT A'!H101=F31,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F32 | =SUM(C32:E32) | STRUCTURELLE | conserver |
| F33 | =SUM(C33:E33) | STRUCTURELLE | conserver |
| F34 | =SUM(C34:E34) | STRUCTURELLE | conserver |
| C35 | =+C36 | STRUCTURELLE | conserver |
| D35 | =+D36 | STRUCTURELLE | conserver |
| E35 | =+E36 | STRUCTURELLE | conserver |
| F35 | =SUM(C35:E35) | STRUCTURELLE | conserver |
| E36 | =+'ETAT A'!H110 | STRUCTURELLE | conserver |
| F36 | =SUM(C36:E36) | STRUCTURELLE | conserver |
| I36 | =IF('ETAT A'!H110=F36,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F37 | =SUM(C37:E37) | STRUCTURELLE | conserver |
| F38 | =SUM(C38:E38) | STRUCTURELLE | conserver |
| I38 | =IF('ETAT A'!H120=F38,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F39 | =SUM(C39:E39) | STRUCTURELLE | conserver |
| I39 | =IF('ETAT A'!H133=F39,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| C40 | =+C41+C42 | STRUCTURELLE | conserver |
| D40 | =+D41+D42 | STRUCTURELLE | conserver |
| E40 | =+E41+E42 | STRUCTURELLE | conserver |
| F40 | =SUM(C40:E40) | STRUCTURELLE | conserver |
| I40 | =IF(F40='ETAT A'!H134-'ETAT A'!H135,TRUE,FALSE) | CONTROLE_CONCORDANCE | conserver_mais_statut_UI — IF TRUE/FALSE — 0=0 devient VRAI si sources vides |
| F41 | =SUM(C41:E41) | STRUCTURELLE | conserver |
| F42 | =SUM(C42:E42) | STRUCTURELLE | conserver |
| F43 | =SUM(C43:E43) | STRUCTURELLE | conserver |
| F44 | =SUM(C44:E44) | STRUCTURELLE | conserver |
| F45 | =SUM(C45:E45) | STRUCTURELLE | conserver |
| F46 | =SUM(C46:E46) | STRUCTURELLE | conserver |
| F47 | =SUM(C47:E47) | STRUCTURELLE | conserver |
| F48 | =SUM(C48:E48) | STRUCTURELLE | conserver |
| F49 | =SUM(C49:E49) | STRUCTURELLE | conserver |
| C50 | =+C40+C39+C38+C35+C36+C31+C28 | STRUCTURELLE | conserver |
| D50 | =+D40+D39+D38+D35+D36+D31+D28 | STRUCTURELLE | conserver |
| E50 | =+E40+E39+E38+E35+E36+E31+E28 | STRUCTURELLE | conserver |
| F50 | =SUM(C50:E50) | STRUCTURELLE | conserver |

### CALCUL FPN (30 formules)

| Cellule | Formule | Nature | Décision |
|---------|---------|--------|----------|
| C7 | ='ETAT A'!H143 | STRUCTURELLE | conserver |
| C8 | ='ETAT A'!H141 | STRUCTURELLE | conserver |
| C9 | ='ETAT A'!H142-'informations à fournir'!C13 | STRUCTURELLE | conserver |
| C10 | =+'ETAT A'!D144+'ETAT A'!D145 | STRUCTURELLE | conserver |
| C11 | ='informations à fournir'!C9 | STRUCTURELLE | conserver |
| C12 | =+'informations à fournir'!C14 | STRUCTURELLE | conserver |
| C13 | =SUM(C7:C12) | STRUCTURELLE | conserver |
| C14 | =+'informations à fournir'!C15 | STRUCTURELLE | conserver |
| C15 | =+C14 | STRUCTURELLE | conserver |
| C16 | ='ETAT A'!H77 | STRUCTURELLE | conserver |
| C17 | ='ETAT A'!H79 | STRUCTURELLE | conserver |
| C18 | ='ETAT A'!H78 | STRUCTURELLE | conserver |
| C19 | ='informations à fournir'!C10 | STRUCTURELLE | conserver |
| C20 | ='ETAT A'!H80 | STRUCTURELLE | conserver |
| C21 | ='informations à fournir'!C11 | STRUCTURELLE | conserver |
| C22 | ='informations à fournir'!C12 | STRUCTURELLE | conserver |
| C23 | ='ETAT A'!H74 | STRUCTURELLE | conserver |
| C24 | =+'informations à fournir'!C16 | STRUCTURELLE | conserver |
| C25 | =+'informations à fournir'!C17 | STRUCTURELLE | conserver |
| C26 | =+'informations à fournir'!C18 | STRUCTURELLE | conserver |
| C27 | =IF(C33<C35,C35-C33,0) | METIER_CONDITION | conserver_mais_statut_UI — IF |
| C28 | =SUM(C16:C27) | STRUCTURELLE | conserver |
| C29 | =+C13+C15-C28 | STRUCTURELLE | conserver |
| C32 | =+'informations à fournir'!C19 | STRUCTURELLE | conserver |
| C33 | =+C32 | STRUCTURELLE | conserver |
| F33 | =C39*10/100 | METIER_RATIO | conserver_mais_statut_UI — division — #DIV/0! ou ratio non interprétable si dénominateur vide |
| C34 | =+'informations à fournir'!C20 | STRUCTURELLE | conserver |
| C35 | =+C34 | STRUCTURELLE | conserver |
| C36 | =IF(C33>=C35,C33-C35,0) | METIER_CONDITION | conserver_mais_statut_UI — IF |
| C39 | =+C29+C36 | STRUCTURELLE | conserver |

### RATIO COUVERTURE DE RISQUE (57 formules)

| Cellule | Formule | Nature | Décision |
|---------|---------|--------|----------|
| D7 | ='ETAT A'!H32 | STRUCTURELLE | conserver |
| F7 | =D7-E7 | STRUCTURELLE | conserver |
| H7 | =G7*F7 | STRUCTURELLE | conserver |
| D8 | ='ETAT A'!H38 | STRUCTURELLE | conserver |
| F8 | =D8-E8 | STRUCTURELLE | conserver |
| H8 | =G8*F8 | STRUCTURELLE | conserver |
| D9 | ='ETAT A'!H39 | STRUCTURELLE | conserver |
| F9 | =D9-E9 | STRUCTURELLE | conserver |
| H9 | =G9*F9 | STRUCTURELLE | conserver |
| D10 | ='ETAT A'!H40 | STRUCTURELLE | conserver |
| F10 | =D10-E10 | STRUCTURELLE | conserver |
| H10 | =G10*F10 | STRUCTURELLE | conserver |
| D11 | ='ETAT A'!H41 | STRUCTURELLE | conserver |
| F11 | =D11-E11 | STRUCTURELLE | conserver |
| H11 | =G11*F11 | STRUCTURELLE | conserver |
| D12 | ='ETAT A'!H45 | STRUCTURELLE | conserver |
| F12 | =D12-E12 | STRUCTURELLE | conserver |
| H12 | =G12*F12 | STRUCTURELLE | conserver |
| D13 | ='ETAT A'!H69 | STRUCTURELLE | conserver |
| F13 | =D13-E13 | STRUCTURELLE | conserver |
| H13 | =G13*F13 | STRUCTURELLE | conserver |
| D14 | =+'informations à fournir'!B7 | STRUCTURELLE | conserver |
| F14 | =D14-E14 | STRUCTURELLE | conserver |
| H14 | =G14*F14 | STRUCTURELLE | conserver |
| D15 | =+'informations à fournir'!B8 | STRUCTURELLE | conserver |
| F15 | =D15-E15 | STRUCTURELLE | conserver |
| H15 | =G15*F15 | STRUCTURELLE | conserver |
| D16 | ='ETAT A'!H58 | STRUCTURELLE | conserver |
| F16 | =D16-E16 | STRUCTURELLE | conserver |
| H16 | =G16*F16 | STRUCTURELLE | conserver |
| D17 | ='ETAT A'!H166 | STRUCTURELLE | conserver |
| F17 | =D17-E17 | STRUCTURELLE | conserver |
| H17 | =G17*F17 | STRUCTURELLE | conserver |
| D20 | ='ETAT A'!H161 | STRUCTURELLE | conserver |
| F20 | =D20-E20 | STRUCTURELLE | conserver |
| H20 | =G20*F20 | STRUCTURELLE | conserver |
| D21 | ='ETAT A'!H163 | STRUCTURELLE | conserver |
| F21 | =D21-E21 | STRUCTURELLE | conserver |
| H21 | =G21*F21 | STRUCTURELLE | conserver |
| D22 | ='ETAT A'!H164 | STRUCTURELLE | conserver |
| F22 | =D22-E22 | STRUCTURELLE | conserver |
| H22 | =G22*F22 | STRUCTURELLE | conserver |
| D23 | ='ETAT A'!H167 | STRUCTURELLE | conserver |
| F23 | =D23-E23 | STRUCTURELLE | conserver |
| H23 | =G23*F23 | STRUCTURELLE | conserver |
| D24 | ='ETAT A'!H168 | STRUCTURELLE | conserver |
| F24 | =D24-E24 | STRUCTURELLE | conserver |
| H24 | =G24*F24 | STRUCTURELLE | conserver |
| D25 | ='ETAT A'!H169 | STRUCTURELLE | conserver |
| F25 | =D25-E25 | STRUCTURELLE | conserver |
| H25 | =G25*F25 | STRUCTURELLE | conserver |
| H26 | =SUM(H20:H25,H7:H17) | STRUCTURELLE | conserver |
| H27 | ='CALCUL FPN'!C39 | STRUCTURELLE | conserver |
| H28 | =H27/H26 | METIER_RATIO | conserver_mais_statut_UI — division — #DIV/0! ou ratio non interprétable si dénominateur vide |
| H31 | ='CALCUL FPN'!C39*10 | STRUCTURELLE_INTERFEUILLE | conserver |
| H32 | =+H26 | STRUCTURELLE | conserver |
| H33 | =+H31-H32 | STRUCTURELLE | conserver |

### RATIO DE LIQUIDITE (31 formules)

| Cellule | Formule | Nature | Décision |
|---------|---------|--------|----------|
| D6 | =SUM(D7:D13) | STRUCTURELLE | conserver |
| D7 | ='ETAT A'!H8 | STRUCTURELLE | conserver |
| D8 | ='ETAT A'!H11 | STRUCTURELLE | conserver |
| D9 | ='ETAT A'!H57 | STRUCTURELLE | conserver |
| D10 | ='ETAT A'!H42 | STRUCTURELLE | conserver |
| D11 | ='ETAT A'!H44 | STRUCTURELLE | conserver |
| D13 | =C48 | STRUCTURELLE | conserver |
| D14 | =SUM(D15:D24) | STRUCTURELLE | conserver |
| D15 | ='ETAT A'!H85 | STRUCTURELLE | conserver |
| D16 | =+'ETAT A'!H105 | STRUCTURELLE | conserver |
| D20 | =+'ETAT A'!H116/2 | METIER_RATIO | conserver_mais_statut_UI — division — #DIV/0! ou ratio non interprétable si dénominateur vide |
| D21 | =+'ETAT A'!H119 | STRUCTURELLE | conserver |
| D22 | =+'ETAT A'!H122 | STRUCTURELLE | conserver |
| D24 | =C49 | STRUCTURELLE | conserver |
| C26 | =D6/D14 | METIER_RATIO | conserver_mais_statut_UI — division — #DIV/0! ou ratio non interprétable si dénominateur vide |
| C33 | ='ETAT A'!H15 | STRUCTURELLE | conserver |
| C34 | ='ETAT A'!H20 | STRUCTURELLE | conserver |
| C35 | ='ETAT C'!C8 | STRUCTURELLE | conserver |
| C36 | ='ETAT A'!H29 | STRUCTURELLE | conserver |
| C37 | ='ETAT C'!C9 | STRUCTURELLE | conserver |
| C38 | ='ETAT A'!H43 | STRUCTURELLE | conserver |
| C39 | =SUM(C33:C38) | STRUCTURELLE | conserver |
| C41 | ='ETAT A'!H87 | STRUCTURELLE | conserver |
| C42 | ='ETAT A'!H92 | STRUCTURELLE | conserver |
| C43 | ='ETAT C'!C30 | STRUCTURELLE | conserver |
| C44 | ='ETAT A'!H100 | STRUCTURELLE | conserver |
| C45 | ='ETAT C'!C31 | STRUCTURELLE | conserver |
| C46 | ='ETAT A'!H121 | STRUCTURELLE | conserver |
| C47 | =SUM(C41:C46) | STRUCTURELLE | conserver |
| C48 | =IF(C39-C47>0,C39-C47,0) | METIER_CONDITION | conserver_mais_statut_UI — IF |
| C49 | =IF(C47-C39>0,C47-C39,0) | METIER_CONDITION | conserver_mais_statut_UI — IF |

### RATIO FP ET AI (10 formules)

| Cellule | Formule | Nature | Décision |
|---------|---------|--------|----------|
| C6 | ='CALCUL FPN'!C39 | STRUCTURELLE | conserver |
| C8 | ='ETAT A'!H59 | STRUCTURELLE | conserver |
| C9 | ='informations à fournir'!C12 | STRUCTURELLE | conserver |
| C10 | =C8-C9 | STRUCTURELLE | conserver |
| C11 | ='ETAT A'!H65-'ETAT A'!H68 | STRUCTURELLE | conserver |
| C12 | ='ETAT A'!H68 | STRUCTURELLE | conserver |
| C13 | =C11+C12 | STRUCTURELLE | conserver |
| C14 | ='ETAT A'!H41 | STRUCTURELLE | conserver |
| C15 | =C14+C13+C10 | STRUCTURELLE | conserver |
| C16 | `=(C6/C15)*100` | METIER_RATIO | conserver_mais_statut_UI — division — `#DIV/0!` ou ratio non interprétable si dénominateur vide |

---

## État Git (ce complément)

- Branche : `feat/reporting-bcm-sm-t3`
- HEAD : `091b57c` — **inchangé**
- Fichiers de ce lot : `docs/comptabilite/reporting-bcm-sm/T3_5_3_T0_COMPLEMENT.md` (créé), `docs/comptabilite/reporting-bcm-sm/README.md` (index)
- Scripts d’inspection jetables **détruits** après lecture
- **Aucun** code backend / frontend, **aucune** migration, **aucun** modèle, **aucune** donnée métier, **aucun** fichier Excel source modifié
- T3.5-3-A **non commencé**. Pas de commit.
