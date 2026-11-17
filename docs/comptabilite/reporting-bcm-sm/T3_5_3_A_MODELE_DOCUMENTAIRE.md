# T3.5-3-A — Modèle documentaire cible (révisé)

Conception consolidée après revue, **puis gelée D1–D9** (`T3_5_3_A_LEVEE_RESERVES_D1_D9.md`). **Non implémentée.**  
Ce document n’est **pas** une validation Comptabilité / DSI de la SM, **ni** une autorisation de T3.5-3-B.

Prérequis : `T3_5_3_A_AUDIT_ETAT_REEL.md`, `T3_5_3_T0_COMPLEMENT.md`, `T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md`, `T3_5_3_A_REVUE_FINALE.md`.

Aucune table ci-dessous n’existe en base. Migration future **additive** `rbcm_05` après `rbcm_04` — **T3.5-3-B**, autorisation distincte. Pas maintenant.

---

## 1. Principes retenus (R1–R15)

1. Trois axes de version **distincts** : SM (`campaign_version`) ≠ canevas (`rbcm_template.version`) ≠ fichier WORK (`document_seq`).
2. Clé métier `BCM:102` **jamais** stockée comme coordonnée Excel (R2, R5).
3. Clé document `A:102:D` **jamais** dans `rbcm_cell_result.cell_ref` (R2).
4. Décisions documentaires dans **`rbcm_document_decision`**, pas `rbcm_cell_decision` (R1, R3, R6).
5. `calculated_value` moteur **immuable** après INSERT.
6. Fichiers WORK immuables : nouvel enregistrement, nouveau path, nouveau SHA (R8, R9).
7. Formules officielles **intactes** dans Excel ; vérité d’affichage = graphe Python Decimal (R10).
8. Vide ou `0` Excel de formule ≠ zéro métier (R10, R11).
9. Aucun fill des 242 `A_VALIDER` (R14). `engine/runner.py` hors graphe.

```
BEA-SM-10-2026.xlsx (dépôt, lecture seule, SHA figé)
        │ copie applicative persistante
        ▼
 rbcm_template 1..n  +  rbcm_template_cell
        │ FK à la 1re génération WORK (Q9)
        ▼
 rbcm_campaign.template_version_id
        │
 rbcm_document_decision  (append-only, portée campagne)
        │ overlay
        ▼
 rbcm_deliverable  kind=EXCEL status=WORK | SUPERSEDED | GENERATED
```

---

## 2. Séparation des clés (R5)

### 2.1 Espace moteur (inchangé)

`BCM:102`, `BCM:234 / 235`, `ECART`, `ETAT_B_PROVISOIRE`, `ETAT_C_PROVISOIRE` → `rbcm_cell_result` / mapping.  
`varchar(32)`. Max observé en DEV : 17.

### 2.2 Espace documentaire

| Feuille officielle | Motif | Exemple | Cellule Excel |
|--------------------|-------|---------|----------------|
| ETAT A (axes métier) | `A:{code}:{axe}` axe ∈ C–H | `A:102:D` | `ETAT A!D9` |
| ETAT A (contrôle) | `A:CTRL:{adresse}` | `A:CTRL:I147` | `ETAT A!I147` |
| ETAT B | `B:{code}:{axe}` axe ∈ C–I, L | `B:207:E` | `ETAT B!E46` |
| ETAT C | `C:{code}:{axe}` axe ∈ C–F, I | `C:103:F` | `ETAT C!F8` |
| CALCUL FPN | `FPN:{adresse}` | `FPN:C39` | `CALCUL FPN!C39` |
| RATIO COUVERTURE DE RISQUE | `RCR:{adresse}` | `RCR:H31` | `RATIO COUVERTURE DE RISQUE!H31` |
| RATIO DE LIQUIDITE | `LIQ:{adresse}` | `LIQ:C26` | `RATIO DE LIQUIDITE!C26` |
| RATIO FP ET AI | `FPAI:{adresse}` | `FPAI:C16` | `RATIO FP ET AI!C16` |
| informations à fournir | `INFO:{adresse}` | `INFO:C9` | `informations à fournir!C9` |

**D2 — contrôle `ETAT A!I147` (figé)**

| Élément | Valeur |
|---------|--------|
| Clé | **`A:CTRL:I147`** |
| Excel | `ETAT A!I147` |
| Formule officielle | `=+H147-H81` |
| Nature | `STRUCTURAL_FORMULA` |
| `writable` | false |
| `decision_allowed` | false |
| Rôle | Contrôle passif − actif (ligne 147 code 427 / ligne 81 total actif) |

Trois espaces **jamais** interchangeables :

| Clé | Couche | Sens |
|-----|--------|------|
| `BCM:102` | moteur | scalaire mapping / `cell_result` |
| `A:102:D` | document | axe D (MRU résidents) du code 102 |
| `A:CTRL:I147` | document | contrôle I147, **pas** un axe du code 427 |

`A:427:I` est **interdit** : la colonne I d’ETAT A n’est pas un axe métier C–H. Aucune autre clé `A:CTRL:…` n’est inventée ; T0 n’en documente qu’une.

Validation **par type** (CHECK SQL ou équivalent applicatif, les deux à l’implémentation) :

| Préfixe | Regex |
|---------|-------|
| A axes | `^A:[0-9]{3}:[C-H]$` |
| A contrôle | `^A:CTRL:I147$` |
| B | `^B:[0-9]{3}:([C-H]|I|L)$` |
| C | `^C:[0-9]{3}:([C-F]|I)$` |
| HEADER A/B/C | `^(A\|B\|C):HDR:[A-Z]{1,3}[0-9]{1,4}$` |
| STRUCT A/B/C sans code BCM | `^(A\|B\|C):STRUCT:[A-Z]{1,3}[0-9]{1,4}$` |
| FPN, RCR, LIQ, FPAI, INFO | `^(FPN\|RCR\|LIQ\|FPAI\|INFO):[A-Z]{1,3}[0-9]{1,4}$` |

**Convention T3.5-3-C (R-B1, autorisée 16/11/2026)** : les formules A/B/C **sans** code BCM ne sont **pas** des HEADER. Exemples gelés : `C:STRUCT:F44`, `C:STRUCT:F46`, `C:STRUCT:F48` (`=SUM(Cxx:Exx)` sur ETAT C).  
`A:HDR:` / `B:HDR:` / `C:HDR:` = uniquement nature `HEADER` (A1, A2, B2, B3, A3).

Colonne `varchar(32)`. Interdit : `SHEET!ADDR` comme clé.  
`A:102:H` ≠ `BCM:102`. APIs disjointes.

---

## 3. `rbcm_template`

Une ligne = un fichier + un SHA. Immuable (`sha256`, `stored_path` jamais UPDATÉs).

| Colonne | Type | Null | FK |
|---------|------|------|-----|
| `id` | UUID PK | non | |
| `template_code` | varchar(32) | non | |
| `version` | integer ≥ 1 | non | |
| `filename` | varchar(255) | non | |
| `sha256` | char(64) | non | UNIQUE |
| `stored_path` | varchar(500) | non | copie applicative |
| `status` | varchar(16) | non | `CURRENT` / `SUPERSEDED` / `ARCHIVED` |
| `created_at` | timestamptz | non | |
| `created_by_id` | UUID | **oui** | `users` **ON DELETE SET NULL** |
| `metadata` | JSONB | oui | |

`UNIQUE (template_code, version)`. Index unique partiel : une ligne `CURRENT` par `template_code`.

`campaign.template_version_id` → `rbcm_template.id` **ON DELETE RESTRICT**, posé à la **première génération WORK** (Q9). Nullable avant.

Chaque `rbcm_deliverable` WORK porte son propre `template_id` : traçabilité du canevas **par fichier**, indépendamment d’un changement ultérieur sur la SM.

---

## 4. `rbcm_template_cell`

| Colonne | Type | Null |
|---------|------|------|
| `id` | UUID PK | non |
| `template_id` | UUID FK **RESTRICT** | non |
| `sheet_name` | varchar(64) | non |
| `excel_address` | varchar(8) | non |
| `document_cell_key` | varchar(32) | non |
| `bcm_code` | varchar(16) | oui |
| `axis` | varchar(4) | oui |
| `nature` | varchar(32) | non |
| `formula_text` | text | oui |
| `writable` | boolean | non |
| `completeness_group` | varchar(32) | oui |
| `metadata` | JSONB | oui (`depends_on`, libellé) |

`UNIQUE (template_id, sheet_name, excel_address)`  
`UNIQUE (template_id, document_cell_key)`

`writable` décrit le **canevas officiel**, pas le WORK. **Ne pas le modifier** pour « rendre D9 saisissable ». Voir §4.2.

### 4.1 Natures

| Nature | Exemple | `writable` (officiel) |
|--------|---------|----------------------|
| `HEADER` | A1, B2, B3 | false |
| `SEPARATOR` | lignes « …… » | false |
| `CANVAS_NORM` | G7=1, H29=0.1, LIQ C27=0.2 | false |
| `CANVAS_SCALE_FORMULA` | `RCR:H31` = `C39*10` ; `LIQ:D20` = `H116/2` ; `FPN:F33` = `C39*10/100` | **false** |
| `OCTOBER_LEAF` | 0 / valeur d’octobre saisie | true si LEAF métier |
| `OCTOBER_CONSTANT_FORMULA` | `ETAT A!D9` = `=588160767-F9` | **false** |
| `LEAF` | case saisie | true |
| `STRUCTURAL_FORMULA` | `SUM`, `+`, copie inter-feuille, **`A:CTRL:I147`** | false |
| `D09_PCT` / `D09_REMAINDER` | E46, D46 | false |
| `CONCORDANCE_IF` | B L11, C I8 | false |
| `METIER_IF` | FPN C27/C36 | false |
| `RATIO_DIV` | H28, C26, C16 (dénominateur **variable**) | false |

Pas de nature `TOTAL` distincte.

**D3 — `RCR:H31` (figé)**

| Élément | Valeur |
|---------|--------|
| Clé | `RCR:H31` |
| Excel | `RATIO COUVERTURE DE RISQUE!H31` |
| Formule officielle **conservée** | `='CALCUL FPN'!C39*10` |
| Nature | **`CANVAS_SCALE_FORMULA`** |
| `writable` / `decision_allowed` | false / false |

Ce n’est **pas** `CANVAS_NORM` (valeur figée type G=1 / 0,1 / 0,2).  
Ce n’est **pas** `RATIO_DIV` (pas une division à dénominateur métier).  
Ce n’est **pas** une constante d’octobre.

Graphe Decimal :

| État de `FPN:C39` | `RCR:H31` |
|-------------------|-----------|
| `NULL` / `NON_RENSEIGNE` | `NULL`, statut `FORMULE_NON_INTERPRETABLE` — **jamais 0** |
| `FORMULE_PARTIELLE` | `FORMULE_PARTIELLE` — **jamais** `FORMULE_COMPLETE` |
| valeur Decimal close, portes fermées | `C39 × 10` (Decimal) |
| porte D16/D17/D09 ouverte en amont | porte prioritaire, non métier |

Aval : `RCR:H30` (`H31+H32`), `RCR:H33` (`H31-H32`) héritent de la même propagation.

Même nature, formules T0 déjà documentées (pas inventées) :

| Clé | Formule | Coefficient |
|-----|---------|-------------|
| `RCR:H31` | `='CALCUL FPN'!C39*10` | ×10 |
| `LIQ:D20` | `=+'ETAT A'!H116/2` | ×½ |
| `FPN:F33` | `=C39*10/100` | ×10 % |

**Neuf constantes historiques** (`OCTOBER_CONSTANT_FORMULA`, même contrat que D9) :

| Excel | Code | Clé | Formule (`formula_text` conservé) |
|-------|------|-----|-----------------------------------|
| D9 | 102 | `A:102:D` | `=588160767-F9` |
| D21 | 114 | `A:114:D` | `=150000000-150000000` |
| D38 | 131 | `A:131:D` | `=3972024483-C38-2873218-5` |
| D75 | 234 | `A:234:D` | `=53348003-C75` |
| D76 | 235 | `A:235:D` | `=77770480-C76` |
| D106 | 322 | `A:322:D` | `=331024347.65-F106` |
| D112 | 328 | `A:328:D` | `=737956675-D111` |
| D123 | 403 | `A:403:D` | `=463722024+296461984-21` |
| D167 | 516 | `A:516:D` | `=5874268360-G167` |

WORK : les neuf cellules sont **vidées**. `writable` template reste false. Saisie via `decision_allowed`. `2873218` ≠ activation D02.

### 4.2 Saisissabilité dérivée (correction 4.1)

Contradiction levée : `writable` reste false sur une formule historique ; le WORK peut quand même recevoir une décision.

**Contrat `decision_allowed` (dérivé, pas une colonne template) :**

```
decision_allowed(cell) =
    (cell.writable = true)
    OR (cell.nature = 'OCTOBER_CONSTANT_FORMULA')
```

| Couche | `ETAT A!D9` / `A:102:D` |
|--------|-------------------------|
| Canevas officiel | nature `OCTOBER_CONSTANT_FORMULA` ; `writable=false` ; `formula_text='=588160767-F9'` |
| Fichier source dépôt | **inchangé** |
| Génération WORK | cellule **vidée** (ni formule, ni `588160767`) |
| Décision documentaire | **autorisée** via `decision_allowed` |
| UI | « À compléter » tant que pas de décision ; jamais 0,00 auto |

Règles :

- ne jamais UPDATER `template_cell.writable` ;
- ne jamais réécrire la constante historique dans le WORK ;
- overlay WORK : écrire `decided_value` seulement si `decision_allowed` ;
- formules structurelles, normes, IF, 30 % : `decision_allowed = false`.

`OCTOBER_LEAF` : déjà `writable=true` quand c’est une feuille métier ; vidée à la génération ; saisie via `writable`.

**HEADER B2/B3** : `writable=false`, `decision_allowed=false`. La génération WORK **écrit** l’arrêté et la banque de la SM comme **overlay de génération** (pas une décision documentaire). Les deux mécanismes ne se fusionnent pas.

**Changement de canevas — cas supplémentaires (4.3)** : même `document_cell_key` mais nature devenue non saisissable (LEAF → `STRUCTURAL_FORMULA`) → reprise bloquée. Même clé, `excel_address` différente → jointure par clé logique toujours, l’adresse T2 est celle du nouveau template. Formule officielle changée → la décision historique reste sur l’ancien `template_cell_id` ; l’overlay T2 n’applique la valeur que si `decision_allowed(T2)`.

---

## 5. `rbcm_document_decision` (R1, R6)

Portée **campagne**. Overlay sur chaque nouveau WORK.

| Colonne | Null | FK |
|---------|------|-----|
| `id` UUID PK | non | |
| `campaign_id` | non | campagne **RESTRICT** |
| `template_cell_id` | non | `rbcm_template_cell` **RESTRICT** — cellule du canevas **d’origine** |
| `document_cell_key` | non | dénormalisé |
| `deliverable_id` | oui | livrable **RESTRICT** si non null (trace, pas portée) |
| `calculation_run_id` | oui | run **SET NULL** (T3.5-3 : toujours NULL) |
| `calculated_value` | oui | snapshot documentaire ; **pas** un UPDATE moteur |
| `decided_value` | oui | |
| `decision_type` | non | |
| `reason` | **non** | motif obligatoire, y compris `ZERO_CONFIRME` (Q4) |
| `justificatif_ref` | oui | obligatoire app si `ZERO_MANUEL` ou `VALEUR_DECIDEE` (Q4) |
| `decided_by_id` | **oui** | `users` **ON DELETE SET NULL** |
| `decided_at` | non | |
| `supersedes_decision_id` | oui | self **ON DELETE RESTRICT** |

### 5.1 Politique FK (correction 4.2)

`NOT NULL` et `ON DELETE SET NULL` sont **incompatibles**. Contrat retenu :

| Référence | Nullabilité | ON DELETE | Motif |
|-----------|-------------|-----------|--------|
| `decided_by_id` | **nullable** | SET NULL | un utilisateur retiré du référentiel ne doit pas faire échouer l’historique ; NULL = auteur plus dans CORE |
| `supersedes_decision_id` | nullable | **RESTRICT** | interdiction de supprimer une décision encore référencée |
| `template_cell_id` | NOT NULL | **RESTRICT** | la cellule d’origine reste |
| `campaign_id` | NOT NULL | **RESTRICT** | |
| `deliverable_id` | nullable | **RESTRICT** | un WORK cité ne se supprime pas |
| `created_by_id` template / deliverable | nullable | SET NULL | même logique utilisateur |

Aucune API DELETE sur `rbcm_document_decision`. Chaîne `supersedes_decision_id` append-only. Trigger optionnel plus tard : `RAISE` sur DELETE.

### 5.2 Types

| Type | `decided_value` | Justificatif | Motif |
|------|-----------------|--------------|-------|
| `ZERO_CONFIRME` | 0 | non | **oui** |
| `ZERO_MANUEL` | 0 | **oui** | oui |
| `VALEUR_DECIDEE` | montant | **oui** | oui |
| `RETRAIT` | NULL | non | oui |

### 5.3 Courant et concurrence (correction 4.4, Q8)

Courant = dernière décision par `(campaign_id, document_cell_key)` selon `decided_at`, sous lock.

`expected_current_id` : obligatoire dans le POST (JSON `null` autorisé).

Vérification **après** `pg_advisory_xact_lock(campagne, 'rbcm-doc-dec')` :

| Croyance client | Courant réel | Résultat |
|-----------------|--------------|----------|
| `null` | aucune décision | **201** — première décision |
| `null` | une décision existe | **409 `DOC_DECISION_CONFLICT`** |
| UUID | id ≠ courant (y compris courant NULL après RETRAIT) | **409** |
| UUID | id = courant | **201** — supersede |

Scénario obligatoire :

1. Deux clients lisent une cellule sans décision → `expected_current_id = null`.
2. Premier POST `null` → 201.
3. Second POST `null` → **409**. Aucune seconde courante.

Index : `(campaign_id, document_cell_key, decided_at DESC)`, `(supersedes_decision_id)`.

### 5.4 Interdits

- UPDATE `rbcm_cell_result.calculated_value`
- INSERT documentaire dans `cell_result` / `cell_decision`
- Décision si `decision_allowed = false`
- Décision sans motif
- Promotion d’un 0 Excel de formule en `ZERO_CONFIRME`
- Transfert silencieux d’une décision vers un autre `template_cell_id`

---

## 6. Changement de canevas (correction 4.3)

Une décision **reste** liée au `template_cell_id` d’origine. Aucune réécriture automatique vers une « cellule équivalente ».

Traçabilité :

| Objet | Canevas |
|-------|---------|
| `rbcm_deliverable.template_id` | canevas du **fichier** WORK |
| `rbcm_campaign.template_version_id` | canevas pour le **prochain** WORK |
| `rbcm_document_decision.template_cell_id` | cellule du canevas **au moment de la décision** |

Changement de `campaign.template_version_id` vers un template T2 :

1. Pour **chaque** décision courante (hors `RETRAIT`) : il existe dans T2 une cellule de même `document_cell_key` **et** `decision_allowed(T2) = true`.
2. Si une clé manque ou n’est plus saisissable → **blocage** (`TEMPLATE_INCOMPATIBLE`) ou reprise **manuelle** contrôlée. Pas de mapping approximatif.
3. Les décisions **ne sont pas** recopiées vers les UUID T2. L’overlay du prochain WORK joint par `document_cell_key` (clé logique), en refusant toute clé sans cellule T2.
4. Les WORK déjà générés restent téléchargeables avec leur `template_id` d’origine.

Tests : changement compatible (mêmes clés) ; clé absente de T2 → bloqué ; aucune UPDATE de `template_cell_id` sur les décisions existantes.

---

## 7. Documents WORK (R7, R8, R9) — D1 figé

Réutiliser `rbcm_deliverable`. L’API `excel_export` (statuts `GENERATED`) **reste**. Extensions `rbcm_05` **additives et nullable**.

| Colonne ajoutée | Null | Contrainte |
|-----------------|------|------------|
| `template_id` | **oui** | FK `rbcm_template.id` **ON DELETE RESTRICT** |
| `document_seq` | **oui** | si non null : entier ≥ 1 |
| `superseded_by_id` | oui | self FK **ON DELETE RESTRICT** |

Pas de `generation_kind` si `status` suffit. Pas de `VALIDATED` dans le CHECK T3.5-3.

### 7.1 Statuts

| Statut | Sens | `template_id` | `document_seq` |
|--------|------|---------------|----------------|
| `GENERATED` | export technique (`excel_export`) — **jamais** SM officielle (Q10) | **NULL** | **NULL** |
| `WORK` | document de travail **non validé** — **un seul** courant par SM | NOT NULL | NOT NULL ≥ 1 |
| `SUPERSEDED` | ancien WORK remplacé ; binaire intact | NOT NULL | NOT NULL ≥ 1 |

CHECK (à poser en `rbcm_05`) :

```sql
CHECK (
  (status = 'GENERATED' AND document_seq IS NULL AND template_id IS NULL)
  OR (status IN ('WORK', 'SUPERSEDED')
      AND document_seq IS NOT NULL AND document_seq >= 1
      AND template_id IS NOT NULL)
)
```

Les compteurs **techniques** (`excel_export`, nom `BCM_SM_YYYYMM_vN.xlsx`) et **documentaires** (`document_seq`) **ne se mélangent pas**.

### 7.2 Deux unicités distinctes (R9, D1)

| Contrainte | Rôle |
|------------|------|
| Index unique **partiel** `(campaign_id, document_seq) WHERE document_seq IS NOT NULL` | numéros WORK 1, 2, 3… **sans trou réutilisé** ; les `GENERATED` (seq NULL) n’y entrent pas |
| Index unique partiel `(campaign_id)` WHERE `kind='EXCEL' AND status='WORK'` | **un seul courant** |

**Interdit** : `UNIQUE (campaign_id, document_seq)` sans `WHERE` (casserait plusieurs `GENERATED` NULL ou forcerait un seq technique).

`superseded_by_id` : chaîne de remplacement. ON DELETE **RESTRICT**.

### 7.3 Génération WORK concurrente (D8 — distinct des décisions)

Verrou : `pg_advisory_xact_lock(campagne, 'rbcm-work-gen')` **avant** d’allouer `document_seq`.

**Ce n’est pas** le 409 des décisions. Aucun `expected_current_id` sur `rbcm_deliverable`.

Deux demandes simultanées de génération :

1. Sérialisées par le lock.
2. Première : `document_seq = n` (ou 1), HTTP succès, statut `WORK`.
3. Seconde : attend, relit `max(document_seq)` **committé**, crée `n+1`, HTTP succès.
4. La première ligne passe `SUPERSEDED` ; la seconde est le WORK courant.
5. Les **deux** binaires sont conservés (paths et SHA distincts).
6. **Pas** de 409 systématique pour la deuxième génération.

Dans **une** transaction, après lock :

1. `document_seq = COALESCE(max(seq) WHERE seq IS NOT NULL, 0) + 1`.
2. Écrire le binaire sur un **nouveau** path sous `…/work/` (jamais `…/exports/`, jamais le path d’un livrable existant).
3. INSERT `status=WORK`, `template_id`, `document_seq`.
4. Si un courant existait : UPDATE **uniquement** `status=SUPERSEDED` et `superseded_by_id` — jamais path / SHA / bytes.
5. Commit.

**Échec de la 2ᵉ génération** (IO, SHA, exception) :

- rollback SQL de **cette** génération seulement ;
- le premier WORK reste `WORK` et téléchargeable ;
- **aucun** écrasement de son fichier.

**Fichiers orphelins** (écrits sur disque puis rollback / kill) :

- ne jamais supprimer un fichier référencé en base ;
- supprimer uniquement le **nouveau** path non committé, dans le `except` / finally ;
- un orphelin non référencé n’est pas servi au téléchargement ;
- reprise : `document_seq` relit le max **committé** ; pas de réutilisation d’un seq d’INSERT annulé.

Stockage indisponible : pas d’INSERT WORK ; erreur `STORAGE_UNAVAILABLE` ; ancien courant inchangé.

Nom WORK :

```
SM_{bank}_{yyyy}_{mm}_c{campaign_version}_w{document_seq}_{sha16}.xlsx
```

Répertoires (séparés) :

- `{upload_root}/reporting-bcm-sm/templates/{template_id}/`
- `{upload_root}/reporting-bcm-sm/{campaign_id}/work/`
- `{upload_root}/reporting-bcm-sm/{campaign_id}/exports/`  ← `excel_export` inchangé

`run_id` NULL pour un WORK. Ne **pas** appeler `excel_export.generate_excel`.

### 7.4 Décisions concurrentes (rappel D8 — §5.3)

Deux POST `expected_current_id=null` : premier **201**, second **409 `DOC_DECISION_CONFLICT`** après lock `rbcm-doc-dec` et relecture. Mécanisme **distinct** de §7.3.

---

## 8. Stockage du template (correction 4.5, Q6, D5)

**Non retenu** comme stockage définitif : `backend/app/data/reporting_bcm_sm/templates/` (disparaît au rebuild d’image).

| Rôle | Emplacement |
|------|-------------|
| Source officielle | `BEA-SM-10-2026.xlsx` à la racine du dépôt — **lecture seule**, jamais cible d’écriture WORK, jamais mutée par le seed |
| Copie applicative | `{upload_root}/reporting-bcm-sm/templates/{id}/` + `stored_path` en base |
| WORK | `…/{campaign_id}/work/` — n’écrase **jamais** la copie template |
| Export technique | `…/{campaign_id}/exports/` |

`upload_root()` lit `settings.upload_dir` (défaut **déclaré** dans `app.core.config` : `"storage/uploads"`). Le chemin **résolu** (hôte Windows vs `/app/...` Docker) **n’est pas inventé ici**. **Première tâche de B** : l’inspecter (O3) et s’arrêter s’il est absent, non inscriptible, ou hors volume persistant.

### 8.1 Construction sûre du chemin (D5)

`stored_path` n’est **jamais** un champ saisi par l’API. Il est **calculé** côté serveur :

```
resolved_root = Path(upload_root).resolve()
template_id   = UUID généré par l’application (pas un segment client)
dest_dir      = (resolved_root / "reporting-bcm-sm" / "templates" / str(template_id)).resolve()
dest_file     = dest_dir / "BEA-SM-10-2026.xlsx"
```

Règles :

- `template_id` = UUID v4 interne ; refuser tout autre format.
- Refuser `..`, chemins absolus, lecteurs Windows, `\\`, et tout segment fourni par une requête.
- Après `resolve()`, `dest_file` **doit** commencer par `resolved_root` (sinon `TEMPLATE_PATH_UNSAFE`).
- Permissions : répertoire créé par l’application ; fichier copie en lecture pour les usages ultérieurs.
- SHA-256 de la copie **avant** INSERT `rbcm_template` et **avant chaque** génération WORK. Doit égaler `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658` pour la version 1.
- Un rebuild backend **ne doit pas** supprimer les templates déjà référencés. Volume uploads persistant.

### 8.2 Erreurs attendues

| Code | Condition | HTTP (phases C/D) |
|------|-----------|-------------------|
| `TEMPLATE_NOT_FOUND` | ligne absente, fichier manquant sur disque | 404 / 409 métier |
| `TEMPLATE_SHA_MISMATCH` | SHA fichier ≠ SHA colonne ou ≠ SHA officiel de la version | 409 |
| `TEMPLATE_PATH_UNSAFE` | résolution hors `upload_root` | 500 interne, jamais de copie |
| `STORAGE_UNAVAILABLE` | `upload_root` absent, non inscriptible, disque plein | 503 |
| `WORK_SHA_MISMATCH` | SHA colonne WORK ≠ bytes disque au download | 409, ne pas servir le binaire |

Le fichier source dépôt reste protégé : le seed **copie**, il n’ouvre pas en écriture le xlsx git.

---

## 9. Statuts d’affichage et graphe Decimal (correction 4.6, R10, R11)

Statuts **dérivés** au GET, non stockés en table cellule. Pas les statuts moteur.

| Statut | Condition |
|--------|-----------|
| `NON_RENSEIGNE` | LEAF / D9 neutralisée, sans décision |
| `ZERO_CONFIRME` / `ZERO_MANUEL` / `VALEUR_DECIDEE` | décision courante |
| `NORME_CANEVAS` | `CANVAS_NORM` |
| `PROVISOIRE_D09` | `D09_*` ou groupe B/C, porte D09 ouverte |
| `FORMULE_COMPLETE` | toutes deps **closes** et portes de la cellule fermées |
| `FORMULE_PARTIELLE` | au moins une dep valorisée et une incomplète |
| `FORMULE_NON_INTERPRETABLE` | deps vides, ou porte ouverte, ou dénominateur vide |
| `CONTROLE_NON_INTERPRETABLE` | concordance, source incomplète |

Montants partiels : **affichés grisés + badge** (Q5), jamais comme montants complets, jamais `0,00` nu.

Saisie INFO / annexes FPN (Q2) : LEAF documentaires autorisées ; **ne ferme pas** D04/D05/D09 ni aucune porte réglementaire.

### 9.1 Contrat du graphe Python (non développé ici)

Opérations : `SUM`, `+`, `-`, `*`, `/`, `IF`, références inter-feuilles. Decimal uniquement.

| Règle | Comportement |
|-------|----------------|
| Référence vide / `NON_RENSEIGNE` | **NULL**, jamais coercition en 0 |
| Division, dénominateur NULL ou 0 | `FORMULE_NON_INTERPRETABLE` (« Non calculable ») — pas 0 |
| `IF` métier, deps NULL | `FORMULE_NON_INTERPRETABLE` ; le 0 Excel (`0<0` / `0>=0`) **n’est pas** une valeur métier |
| Concordance, source incomplète | `CONTROLE_NON_INTERPRETABLE` — **jamais** OK sur TRUE Excel |
| Dépendance transitive | DAG complet ; une formule dont une dep est une **formule partielle** est **partielle ou non interprétable**, jamais `FORMULE_COMPLETE` |
| Cache Excel / openpyxl | **jamais** vérité métier |
| Porte ouverte | priorité sur le graphe : même deps « remplies », statut non métier (`PROVISOIRE_D09` / `FORMULE_NON_INTERPRETABLE`) |
| `*` / coefficient canevas (`RCR:H31`, `LIQ:D20`, `FPN:F33`) | même propagation NULL/partiel que `+` ; **jamais** classé `RATIO_DIV` |
| `A:CTRL:I147` (`H147-H81`) | `STRUCTURAL_FORMULA` ; incomplet si H147 ou H81 incomplet ; **pas** une saisie |

Portes (inchangées, non closes par une saisie documentaire) :

| Porte | Effet |
|-------|--------|
| D01 | pas de fill mapping |
| D02 | pas d’ECART dans une cellule |
| D06 | pas de 0 auto |
| D09 | B, C, 30 %, 70 %, concordances B/C |
| D15 | bases D/C/SD |
| D16/D17 | axes D–G et donc H et ratios `H*` |
| D22 | conflit multi-cellules |

Exemple : `A:102:H` = `SUM(D9:G9)`. Si D9 est `NON_RENSEIGNE` (formule octobre vidée, pas encore de décision) et F9 a une valeur, H9 = `FORMULE_PARTIELLE`. Si plus tard D9 a une décision mais D16 ouverte, H9 reste `FORMULE_NON_INTERPRETABLE`.

---

## 10. Génération Excel (R12, R13)

1. Copier la **copie applicative** template (SHA contrôlé), pas le xlsx dépôt.
2. Aucune insertion / suppression de ligne sur les 8 feuilles officielles.
3. Feuille `AVERTISSEMENT` en première position.
4. En-tête / pied :

   `VERSION DE TRAVAIL BEA DIGITAL — montants et totaux éventuellement incomplets — ne constitue pas une validation réglementaire`

5. Neutraliser `OCTOBER_CONSTANT_FORMULA` (les **neuf** cellules vidées, saisissables via `decision_allowed`) et `OCTOBER_LEAF` (dont INFO C6–C8 / C10–C20 et couverture E7:E25).
6. Conserver formules structurelles (dont `A:CTRL:I147`, `INFO:C9`), **30 % et 70 %** (badge D09), IF, ratios, `CANVAS_SCALE_FORMULA` (`RCR:H31`, …), normes G / 0,1 / 0,2.
7. B2/B3 = arrêté / banque de la SM.
8. Overlay des décisions courantes si `decision_allowed`.
9. `warnings` JSONB : `work`, `regulatory_validation=false`, SHA, portes ouvertes, `div_zero_possible`, `concordance_true_if_empty`.

---

## 11. Intégrité — schéma cible

```
rbcm_template 1───N rbcm_template_cell
       ▲
       │ RESTRICT
 rbcm_campaign.template_version_id   (nullable jusqu’à 1re WORK)
       │
       ├── N rbcm_document_decision
       │      decided_by_id SET NULL
       │      template_cell_id RESTRICT
       │      supersedes_decision_id RESTRICT
       │      deliverable_id nullable RESTRICT
       ├── N rbcm_calculation_run ── N rbcm_cell_result     moteur
       ├── N rbcm_cell_decision                             moteur, vide
       └── N rbcm_deliverable
              template_id nullable RESTRICT
              document_seq nullable
              UNIQUE partiel (campaign_id, document_seq) WHERE document_seq IS NOT NULL
              UNIQUE partiel status=WORK
              superseded_by_id RESTRICT
              GENERATED : seq NULL, template_id NULL
```

---

## 12. Contrat du seed et migration (D4, D6, R15) — T3.5-3-B uniquement

### 12.1 Migration `rbcm_05`

Révision visée : `20261116_rbcm_05_document_model` ← `20261116_rbcm_04`. Additive. Service Docker `migrate`.  
Pas de DROP, pas d’ALTER `cell_ref` moteur, pas de prod.

### 12.2 Bases — stratégie (D6)

État connu (SELECT 16/11/2026, à **revérifier** au démarrage de B) :

| Base | Alembic | `rbcm_*` |
|------|---------|----------|
| `bea_digital` (DEV) | `20261116_rbcm_04` | 20 tables |
| `bea_digital_test` | `20261105_mg_stock_mvt_ref_uq` | **0** |
| Production | non interrogée | — |

B **commence** par inspecter `DATABASE_URL` / settings, le nom de base réel, et `alembic_version`.  
**S’arrêter** si la cible n’est pas identifiée, si ce n’est pas `bea_digital` pour le migrate DEV, ou si le head n’est pas `rbcm_04`.

`bea_digital_test` n’est **pas** prête. Les tests PG de B ne s’improvisent pas par `alembic upgrade` sur une base non identifiée. Procédure :

1. Identifier la base de test (`scripts/test-db.ps1` / politique unique `bea_digital_test`).
2. Préparer une copie qui **enchaîne** rbcm_01→05 (ou un refresh documenté incluant cette chaîne).
3. Consigner la révision atteinte dans le rapport B.
4. Jamais de migrate « à l’aveugle » vers une URL inconnue.

### 12.3 Identité du canevas v1

| Champ | Valeur figée |
|-------|----------------|
| Fichier source | `BEA-SM-10-2026.xlsx` (racine dépôt) |
| SHA-256 | `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658` |
| Taille | 78 202 octets |
| `template_code` | `BEA-SM` |
| `version` | 1 pour ce SHA |
| Feuilles officielles | **8** (noms T0 exacts) |

**Pas** de feuille `AVERTISSEMENT` dans le template ni dans `rbcm_template_cell`. Elle est ajoutée **uniquement** à la génération WORK (phase C).

### 12.4 Inventaire à enregistrer (D4)

Source : fichier officiel + T0 + complément (annexe 663 formules). **Ne pas inventer** une cellule absente de ces sources.

**Toujours enregistrer :**

1. Les **663** cellules à formule (`formula_text` obligatoire, texte officiel intact).
2. Les **9** `OCTOBER_CONSTANT_FORMULA` (§4.1).
3. `A:CTRL:I147` (§2.2).
4. `RCR:H31`, `LIQ:D20`, `FPN:F33` en `CANVAS_SCALE_FORMULA`.
5. D09 : E46/E48/E49 `D09_PCT` ; D46/D48/D49 `D09_REMAINDER`.
6. 27 `CONCORDANCE_IF` (B L* / C I*).
7. `INFO:C6`, `C7`, `C8`, `C10`–`C20` : `OCTOBER_LEAF`, `writable=true` (14 cellules, 0 d’octobre).
8. `INFO:C9` : `STRUCTURAL_FORMULA`, `='ETAT A'!D146`, `writable=false`.
9. Couverture `E7:E25` : `OCTOBER_LEAF` (0 d’octobre, pas une norme). Compte exact = cellules numériques non formules lues dans le fichier ; le named range T0 est `E7:E17` + `E20:E25`. **Ne pas inventer** E18/E19 si le fichier n’a pas de valeur.
10. `CANVAS_NORM` : G7:G17=1, G20:G21=0.33, G22:G25=0.25, H29=0.1, LIQ C27=0.2.
11. HEADER par feuille : A1, A2, B2, B3, A3 (`writable=false`).
12. Autres LEAF d’octobre : **algorithme fichier**, grilles T0 — ETAT A C–H (VALEUR/ZERO/VIDE des lignes codes), ETAT B C–H non formules, ETAT C C–E non formules, LIQ D12/D17/D18/D19/D23. Compte = sortie du seed, pas un entier inventé ici.

**`depends_on` JSONB** : **optionnel** en B. `formula_text` **obligatoire** pour toute formule. Le graphe est phase C.

**Jamais :**

- fill / `ACTIVE` des 242 `A_VALIDER` ;
- zéro automatique des 67 non mappées ;
- feuille `AVERTISSEMENT` ;
- copie des constantes d’octobre comme `CANVAS_NORM` ;
- invocation de `runner.py`.

### 12.5 Idempotence

1. Identité = `(template_code, sha256)`. `sha256` UNIQUE.
2. Rejouer le seed sur le **même** SHA : aucune nouvelle ligne template, aucun doublon `template_cell` (UNIQUE sheet+address et UNIQUE document_cell_key). Succès idempotent.
3. SHA **différent** : **nouvelle** version (`version+1`), ancien `CURRENT` → `SUPERSEDED`. Jamais d’UPDATE de `sha256` / `stored_path` d’une ligne existante.
4. Échec partiel : une transaction ; rollback → reprise = rejeu complet. Pas de template CURRENT sans ses 663 formules.
5. Rapport de seed : comptes contrôlables (feuilles=8, formules=663, 9 constantes, 1 `A:CTRL:I147`, 1 `RCR:H31` scale, 14 INFO leaves, 1 INFO C9, D09=6, IF=27, SHA).

---

## 13. Tests d’acceptation — identifiants stables (D7)

Jeux jetables, jamais SM BEA 11/2026 / 01/2026. **Aucun test exécuté ici.**

Les numéros « modèle 1–23 » et « complément T0 19–34 » **coexistent** via l’ID `DOC-*`. Aucun critère n’est abandonné.

| ID | T0-C | Ancien modèle | Objectif | Préconditions | Action | Attendu | Phase |
|----|------|---------------|----------|---------------|--------|---------|-------|
| DOC-01 | 19 | 1 | 9 constantes absentes du WORK | seed 9 formules | générer WORK | littéraux `588160767`, `2873218`, `5874268360`, … absents ; D9 `decision_allowed`, `writable` template false | C |
| DOC-02 | 34 | 2 | SHA officiel | fichier dépôt | hasher | `54e3b687…` bit-identique | B |
| DOC-03 | — | 3 | copie hors image | template sous `upload_root` | simuler rebuild | fichier encore lisible | B |
| DOC-04 | — | 4 | FK auteur | décision existante | DELETE user | `decided_by_id` NULL, ligne conservée | B/F |
| DOC-05 | — | 5 | append-only | décision | DELETE décision | interdit (RESTRICT / pas d’API) | B/F |
| DOC-06 | — | 6 | canevas T2 | décisions T1 | changer template | pas de transfert UUID ; clé absente ou non saisissable → bloqué | C/F |
| DOC-07 | 32† | 7 | concurrence décisions | cellule sans décision | 2 POST `expected_current_id=null` | 201 puis 409 | F |
| DOC-08 | — | 8 | concurrence WORK | SM sans WORK / 1 WORK | 2 POST générer | seq n et n+1 ; un seul `WORK` ; **pas** 409 | C |
| DOC-09 | — | 9 | unique seq | 2 WORK | lire seq | distincts ; `GENERATED` sans seq | B/C |
| DOC-10 | 31 | 10–11 | versions | 2 générations | SHA/path/GET | 2 fichiers ; ancien SUPERSEDED téléchargeable | C/D |
| DOC-11 | 24 | 12 | H9 partiel | D9 vide, F9 valorisé | GET | pas `ZERO_CONFIRME` / pas `0,00` nu | C/D |
| DOC-12 | 25 | 12–13 | FPN C36 | annexes vides | GET | pas zéro métier | C/D |
| DOC-13 | 26 | 14 | concordance | sources vides | GET L11 / I8 | `CONTROLE_NON_INTERPRETABLE` | C/D |
| DOC-14 | 27 | 13 | ratios | dénominateur vide | GET H28, C26, C16 | `FORMULE_NON_INTERPRETABLE` | C/D |
| DOC-15 | — | 15 | portes | mapping A_VALIDER | GET / générer | D01/D02/D06/D09/D15/D16/D17/D22 visibles, non fermées | C–F |
| DOC-16 | — | 16 | mapping | après WORK | compter règles | 0 `ACTIVE`, 242 `A_VALIDER` | C |
| DOC-17 | 30 | 17 | immutabilité moteur | POST décision | SQL | pas d’UPDATE `calculated_value` | F |
| DOC-18 | — | 18 | runner | génération WORK | hash fichier | `runner.py` non invoqué | C |
| DOC-19 | 33 | 19 | namespaces | run moteur + document | GET | `BCM:102` et `A:102:D` coexistent | D/F |
| DOC-20 | 32 | 20 | permission `view` | rôle view seul | POST WORK / décision | **403** ; GET autorisé | D/F |
| DOC-21 | 32 | — | motif obligatoire | POST décision `reason` vide | POST | **400** | F |
| DOC-22 | 20 | 21 | D09 | seed | WORK + GET | 30 % et 70 % présents, `PROVISOIRE_D09` | C |
| DOC-23 | 21 | 21 | normes | seed | WORK | G, 0,1, 0,2 conservés | C |
| DOC-24 | 22 | — | couverture | seed | WORK | E7:E25 **vidées** | C |
| DOC-25 | 23 | — | INFO | seed | WORK | C6–C8 et C10–C20 vides ; C9 formule `='ETAT A'!D146` | C |
| DOC-26 | 28 | 22 | AVERTISSEMENT | génération | xlsx | feuille en 1re position ; **pas** dans le seed ; D9 reste D9 | C |
| DOC-27 | 29 | 19 | POST document | `A:102:D` | INSERT | 0 ligne `cell_result` `A:` ou `BCM:102` créée par ce POST | F |
| DOC-28 | — | 23 | rollback génération | IO/SHA échec | générer | ancien WORK encore courant ; fichier ancien intact | C |
| DOC-29 | — | — | DELETE template référencé | WORK existant | DELETE template | RESTRICT | B |
| DOC-30 | — | — | SHA template | copie altérée | générer / seed | `TEMPLATE_SHA_MISMATCH` | B/C |
| DOC-31 | — | — | chemin | segment `..` | copie | `TEMPLATE_PATH_UNSAFE`, aucune écriture | B |
| DOC-32 | — | — | stockage | `upload_root` down | générer | `STORAGE_UNAVAILABLE` ; pas d’INSERT WORK | C |
| DOC-33 | — | — | `excel_export` | après `rbcm_05` | export technique | `GENERATED` seq NULL, API inchangée | B |
| DOC-34 | — | — | I147 | seed + WORK | lire | `A:CTRL:I147` présent ; formule conservée | B/C |
| DOC-35 | — | — | H31 | seed + GET | graphe | nature `CANVAS_SCALE_FORMULA` ; C39 vide → non interprétable | B/C |
| DOC-36 | — | — | seed idempotent | 2× seed même SHA | SQL | 1 template, 0 doublon cellule | B |

† T0-32 couvre à la fois 403 `view` et 400 motif → DOC-20 + DOC-21.

---

## 14. Hors modèle

PDF · réimport Excel · statut `VALIDATED` en `rbcm_05` · fill `A_VALIDER` · ECART · table de dépendances normalisée · pointeur `current_work_deliverable_id` · T3.5-3-B **sans autorisation écrite**.

La **validation réglementaire** (étape 9 de la feuille de route) est une phase **postérieure à F**, distincte de la génération et du téléchargement WORK. Elle n’est pas un statut `VALIDATED` dans `rbcm_05`.

---

## 15. Découpage des phases (D9) — sans « A code »

Il n’existe **pas** de phase « T3.5-3-A code ».

### 15.1 Fiche T3.5-3-B (n’autorise pas l’exécution)

**Nom :** T3.5-3-B — Migration `rbcm_05` + seed du canevas officiel.

**Prérequis :** conception D1–D9 intégrée ; HEAD Git connu ; autorisation **écrite** utilisateur (O4) ; inspection `upload_root` et Alembic en tête de lot.

**Périmètre autorisable ultérieurement :**

- migration additive `rbcm_05` ;
- tables `rbcm_template`, `rbcm_template_cell`, `rbcm_document_decision` ;
- colonnes livrable nullable §7 ;
- FK et CHECK documentés ;
- copie persistante du template ;
- SHA-256 ;
- seed idempotent §12 ;
- contrôles d’intégrité et tests schéma/seed (DOC-02, 03, 04, 09 partiel, 29–31, 33–36).

**Interdictions de B :**

- aucune génération WORK utilisateur ;
- aucun nouveau moteur de calcul / graphe Decimal exécuté ;
- **aucune** modification de `engine/runner.py` ;
- aucun remplissage de document ;
- aucun changement de mapping `A_VALIDER` / `ACTIVE` ;
- aucune fermeture des portes D01, D02, D06, D09, D15, D16/D17, D22 ;
- aucune validation réglementaire ;
- aucune UI nouvelle ;
- aucun changement de production ;
- aucun `docker compose down -v` ;
- aucune modification du xlsx officiel.

**Livrables B :**

1. fichier migration `rbcm_05` ;
2. modèles SQLAlchemy alignés ;
3. copie persistante + SHA ;
4. seed idempotent ;
5. rapport de migration (base, révision avant/après) ;
6. rapport de seed (comptes) ;
7. contrôles d’intégrité (UNIQUE, SHA, 8 feuilles, 663 formules) ;
8. tests schéma/seed ;
9. procédure de rollback **documentaire et technique** : downgrade seulement si aucun WORK/décision ; **jamais** supprimer l’historique ni le xlsx dépôt.

**Arrêt :** tout prérequis non satisfait (mauvaise base, SHA source ≠ attendu, `upload_root` illisible) → **stop**, pas de seed partiel laissé CURRENT.

### 15.2 Phases C–F

| Phase | Périmètre | Prérequis | Livrables | Sortie | Interdictions |
|-------|-----------|-----------|-----------|--------|---------------|
| **C** | Génération WORK + graphe Decimal de complétude | B OK | service `work_fill`, overlay, AVERTISSEMENT, tests DOC-01, 08, 11–14, 22–26, 28, 32, 34–35 | un WORK générable, rollback sûr | runner, fill mapping, UI, décisions API |
| **D** | API GET / générer / télécharger | C | routes, permissions, download SUPERSEDED, SHA download | API stable | UI, validation réglementaire |
| **E** | UI documentaire | D | écran cellules, badges, partiels grisés (Q5) | parcours comptable visible | `alert()`, validation réglementaire |
| **F** | Décisions, corrections, régénération | D | POST décisions, 201/409, motif 400, overlay, historique | DOC-07, 17, 20, 21, 27 | UPDATE `calculated_value`, `VALIDATED` |

### 15.3 Feuille de route vers la fin du module (DEV)

Cible fonctionnelle :

1. Création d’une SM.
2. Désignation du responsable.
3. Import BAL DET.
4. Contrôles et conservation des runs (T3.5-2).
5. Saisie des informations manquantes (INFO / feuilles autorisées).
6. Calcul (moteur existant, **inchangé** en B) et génération du document WORK (C).
7. Consultation et correction des cellules autorisées (E/F).
8. Régénération avec historique des versions (C/F).
9. Validation distincte par une personne autorisée — **hors `rbcm_05`**, après F.
10. Téléchargement du document (WORK maintenant ; document validé plus tard).
11. Traçabilité complète.

Recette finale **DEV** (après F, avant toute discussion de déploiement) :

- unitaires, intégration PostgreSQL, concurrence (décisions **et** WORK), API/permissions, Angular, Playwright du parcours comptable, Excel généré, historiques et SHA, scénarios d’échec (stockage, SHA, rollback, orphelins).

**Production hors périmètre** jusqu’à procédure de release séparée.
