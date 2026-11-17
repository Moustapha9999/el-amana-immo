# T3.5-3-B — Revue finale de livraison (avant décision d’autorisation C)

Revue **technique en lecture seule**. Aucune migration, aucun seed, aucun pytest d’écriture, aucune restauration sur `bea_digital`.  
**T3.5-3-C n’est pas autorisée par ce document.** Seul l’utilisateur peut l’autoriser.

Date : 16/11/2026.

**Verdict : `B VALIDABLE SOUS RÉSERVE`**

La migration `rbcm_05` est additive, la base DEV locale est identifiée, le canevas officiel est copié et seedé avec SHA conforme, les campagnes BEA et le mapping T3.5-1/2 sont encore présents avec les mêmes identifiants.  
Trois points empêchent de clôturer B comme `VALIDÉE` sans réserve : (1) trois clés documentaires `C:HDR:F44/F46/F48` hors HEADER et hors regex gelée §2.2, non décrites ainsi dans le rapport B ; (2) plusieurs tests DOC-B sont des inspections de schéma, pas les actes décrits par le modèle ; (3) la conservation métier est établie par identifiants / compteurs / horodatage, pas par diff ligne à ligne avec le dump.

Aucun de ces points n’exige un rollback de `rbcm_05` ni un re-seed. Ils doivent être tranchés **avant** C, parce que le graphe WORK s’appuiera sur les clés.

---

## 1. Verdict

# `B VALIDABLE SOUS RÉSERVE`

Cela signifie uniquement que T3.5-3-B est **livrée sur DEV avec des réserves documentées**. Ce n’est **pas** une autorisation d’exécuter T3.5-3-C.

---

## 2. Tableau des vérifications

| # | Contrôle | Constat | Verdict |
|---|---------|---------|---------|
| 1 | Branche / HEAD | `feat/reporting-bcm-sm-t3` / `091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32` | OK |
| 2 | Commit / push | Working tree dirty (T3 non commité). HEAD inchangé. Aucun commit de B. | OK |
| 3 | Cible PG | Conteneur `bea-postgres` `172.18.0.2`, bind **`127.0.0.1:5432`**, volume `bea_postgres_data`. Backend `bea_app` → `postgres:5432/bea_digital` (clients `172.18.0.5` / `172.18.0.6`). | OK — locale |
| 4 | Production | Pas d’hôte public, pas de tunnel observé, production non interrogée. | OK |
| 5 | Alembic live | `bea_digital` = **`20261116_rbcm_05`**. `bea_digital_test` = `20261105_mg_stock_mvt_ref_uq`, **0** table `rbcm_*`. | OK |
| 6 | Migration additive | `down_revision = 20261116_rbcm_04`. `upgrade()` : CREATE / ADD COLUMN / FK / CHECK / index. Aucun DROP/TRUNCATE/DELETE métier. DROP uniquement dans `downgrade()` (non exécuté). | OK |
| 7 | D1 livrables | `template_id` / `document_seq` **nullable**. CHECK GENERATED ⇔ seq+template NULL ; WORK/SUPERSEDED ⇔ seq ≥ 1 et template NOT NULL. UNIQUE partiel `(campaign_id, document_seq) WHERE document_seq IS NOT NULL`. UNIQUE partiel un WORK EXCEL. 0 livrable existant. | OK |
| 8 | D2 / D3 seed | `A:CTRL:I147` formule `=+H147-H81`, `writable=false`. `RCR:H31` = `CANVAS_SCALE_FORMULA`, `='CALCUL FPN'!C39*10`. `INFO:C9` formule conservée. | OK |
| 9 | D4 inventaire | 8 feuilles, **663** formules (fichier **et** SQL), 9 constantes, pas d’`AVERTISSEMENT`, E18/E19 **absents** (17 cellules E mesurées). | OK |
| 10 | D5 stockage | Copie `{upload_root}/reporting-bcm-sm/templates/{uuid}/`. SHA source = SHA copie. `resolve()` + `relative_to`. Codes d’erreur nommés. | OK |
| 11 | D6 test-db | `bea_digital_test` **non** migrée. Pas d’improvisation. | OK |
| 12 | D9 / VALIDATED | CHECK template `CURRENT/SUPERSEDED/ARCHIVED`. CHECK livrable sans `VALIDATED`. `decision_allowed` **dérivé**, pas une colonne. | OK |
| 13 | Données T3.5-1/2 | IDs campagnes, owner, caisse, 242/0 mapping, 2 runs, 92 `cell_result` : alignés rapports A/T3.5-2. `updated_at` campagnes **antérieur** au seed. | OK sous R-B6 |
| 14 | Sauvegarde | Fichier présent, 9 110 083 o, SHA = rapport B, TOC 2235 / 2245 lignes, `dbname: bea_digital`, **20** tables `rbcm_*` (pas `rbcm_template`). Restauration isolée **non** faite. | OK sous R-B5 |
| 15 | Idempotence | 1 template CURRENT, UNIQUE `sha256`, 0 doublon de clé. 2ᵉ exécution **non relancée** ici. Code : lookup par SHA. | OK sous R-B7 |
| 16 | Périmètre C–F | Pas de générateur WORK, 0 livrable WORK, `runner.py` plus ancien que le seed, 0 mapping ACTIVE, pas de doc `T3_5_3_C*`. | OK |
| 17 | Clés hors modèle | `C:HDR:F44`, `C:HDR:F46`, `C:HDR:F48` (SUM structurels ETAT C, `bcm_code` NULL). | **Réserve R-B1** |
| 18 | Tests DOC-B | 10 fonctions présentes. Non ré-exécutées (écritures possibles). Couverture réelle partielle pour DOC-04/29/31/33. | **Réserve R-B4** |

---

## 3. Preuves réelles consultées

### 3.1 Git

```
branche : feat/reporting-bcm-sm-t3
HEAD    : 091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32
sujet   : docs(deploiement): aligner transmission srvsuividep et porte de release
```

Working tree : 9 fichiers tracked T3.1 + untracked T3.5 (dont `20261116_rbcm_05_document_model.py`, `template_seed.py`, `template_storage.py`, `test_reporting_bcm_sm_t35_3_b.py`, docs B). Travaux T3.5-1/2 **présents**, non nettoyés.

`runner.py` LastWriteTime **16/11/2026 22:15:55**. `template_seed.py` **23:16:53**. `excel_export.py` **13:42:29**. B n’a pas retouché le moteur après 22:15.

### 3.2 Docker / connexion réelle

| Élément | Valeur observée |
|---------|-----------------|
| `bea-postgres` | `postgres:17-alpine`, IP `172.18.0.2`, ports `127.0.0.1:5432→5432`, volume `bea_postgres_data` |
| `bea-backend` | healthy, IP `172.18.0.5`, montage hôte `storage/uploads` → `/app/storage/uploads` |
| `pg_stat_activity` | `admin` (socket) ; `bea_app` depuis `172.18.0.5` et `172.18.0.6` |
| `DATABASE_URL` (redacté) | `postgresql+asyncpg://bea_app:***@postgres:5432/bea_digital` |
| `SKIP_MIGRATIONS` | `1` |
| `upload_dir` | défaut code `storage/uploads` → `upload_root()` `/app/storage/uploads` |

**Aucune connexion de production n’a été ouverte.** L’adresse IP du serveur bancaire n’a pas été contactée.

### 3.3 Alembic et tables

| Base | `alembic_version` | `rbcm_*` |
|------|-------------------|----------|
| `bea_digital` | `20261116_rbcm_05` | **23** (20 d’avant B + `rbcm_template`, `rbcm_template_cell`, `rbcm_document_decision`) |
| `bea_digital_test` | `20261105_mg_stock_mvt_ref_uq` | **0** |

Dump pré-B : 20 tables `rbcm_*`, **sans** `rbcm_template` / `_cell` / `_document_decision`. Cohérent avec un état `rbcm_04`.

### 3.4 Conservation métier (live vs rapports antérieurs)

Sources avant B : `T3_5_2_REPORT.md`, `T3_5_3_A_AUDIT_ETAT_REEL.md`. Live : `SELECT` 16/11/2026 23:29+ (cette revue).

| Objet | Avant B (docs) | Live après B | Commentaire |
|-------|----------------|--------------|-------------|
| SM `01/2026` | `57b77c73-…` `CALCULEE` | **même UUID**, `CALCULEE`, owner `6b99bb89-…`, `template_version_id` NULL, `updated_at` 20:23:31Z | ID identique |
| SM `11/2026` | `a9c8832b-…` `CALCULEE` | **même UUID**, `CALCULEE`, owner `6b99bb89-…`, `updated_at` 19:23:00Z | ID identique |
| Mapping | 242 `A_VALIDER`, 0 `ACTIVE` | 242 / 0 | inchangé en compteur |
| `rbcm_control_run` | 2, `previous_run_id` NULL | 2 UUID `00ad5c5d-…` (11/2026) et `d9f1207d-…` (01/2026), `OK`, prev NULL | IDs + campagnes |
| `rbcm_cell_result` | 92, préfixes moteur | 92 : BCM 86, ECART 2, ETAT_B 2, ETAT_C 2, **0** `A:` | pas de mélange de clés |
| `rbcm_cell_decision` | 0 | 0 | |
| `rbcm_deliverable` | 0 | 0 | pas de WORK |
| `rbcm_document_decision` | n/a | 0 | |
| `rbcm_calculation_run` | 2 | 2 | |
| Owner history | (T3.5-1) | 2 | |
| Issues | 2 SUMMARY A/OK | 2 catégorie A, `OK` | |
| Imports | 11/2026 : 2 | 11/2026 : 2 ; 01/2026 : 1 | total 3 |
| `caisse_devises` 11/2026 | `0.00` `CALCULE` `BAL_DET_DERIVE` | identique, `justificatif_ref` NULL | |
| Seed template | absent | créé `23:18:13Z` **après** `updated_at` des SM | SM non retouchées par le seed |

**Non vérifiable ici** (R-B6) : hash / dump-diff de chaque ligne `rbcm_mapping_rule`, `rbcm_cell_result.calculated_value`, historiques de paramètres. Un `pg_restore -a -t …` vers stdout a été **refusé** par le garde-fou (ressemble à une restauration) ; il n’a **pas** été relancé.

### 3.5 Sauvegarde

| Champ | Observé | Rapport B |
|-------|---------|-----------|
| Chemin | `backups/t353b_pre_rbcm05_20261116_231452.dump` | identique |
| Taille | 9 110 083 | identique |
| SHA-256 | `B6ABA65DAE89E8D060FAC8CAC562E7DA01E2AFE7BB6AAB016C5DA501C30279AA` | identique |
| En-tête TOC | `Archive created at 2026-11-16 23:14:52 UTC`, `dbname: bea_digital`, `TOC Entries: 2235`, gzip, pg_dump 17.11 | identique |
| `pg_restore -l` | 2245 lignes | identique |

**Sauvegarde créée et vérifiée techniquement (existence, taille, SHA, TOC).**  
**Restauration réellement testée : non.**

### 3.6 Canevas et copie

| Contrôle | Source dépôt | Copie persistante | SQL seed |
|----------|--------------|-------------------|----------|
| SHA-256 | `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658` | identique | identique |
| Taille | 78 202 | 78 202 | — |
| Feuilles | 8, noms T0, pas `AVERTISSEMENT` | idem (openpyxl sur la copie) | 8 `sheet_name` distincts |
| Formules | **663** (openpyxl `data_only=False`) | 663 | 663 `formula_text IS NOT NULL` |
| E18 / E19 | `None` / `None` | idem | 0 ligne |
| Couverture E | 17 : E7–E17 + E20–E25 | idem | 17 `OCTOBER_LEAF` E* |

Chemin copie :

`storage/uploads/reporting-bcm-sm/templates/342dee7d-cd82-4e1e-b468-6e1ddef1606b/BEA-SM-10-2026.xlsx`

`stored_path` SQL : `/app/storage/uploads/reporting-bcm-sm/templates/342dee7d-cd82-4e1e-b468-6e1ddef1606b/BEA-SM-10-2026.xlsx`.

Formules lues **telles quelles** (pas d’évaluation openpyxl) : I147, H31, C9, neuf constantes dont `=588160767-F9` et `=3972024483-C38-2873218-5`.

### 3.7 DDL D1–D9 (base vivante)

Confirmé par `pg_constraint` / `pg_indexes` :

- UNIQUE partiel seq : `WHERE (document_seq IS NOT NULL)`
- UNIQUE partiel un WORK : `kind = 'EXCEL' AND status = 'WORK'`
- CHECK D1 GENERATED / WORK / SUPERSEDED
- FK template livrable **RESTRICT** ; campagne `template_version_id` **RESTRICT** ; `decided_by_id` **YES** + `ON DELETE SET NULL` ; `reason` NOT NULL ; `supersedes_decision_id` RESTRICT
- Pas de `VALIDATED` dans les CHECK template / livrable / nature
- JSONB colonne SQL **`extra`** (pas `metadata`)

---

## 4. Anomalies

### A1 — Clés `C:HDR:F44/F46/F48` (principale)

Trois formules structurelles ETAT C `=SUM(Cxx:Exx)`, `bcm_code` NULL, nature `STRUCTURAL_FORMULA`, clés **`C:HDR:F44`**, **`C:HDR:F46`**, **`C:HDR:F48`**.

T0 les connaît (`T3_5_3_T0_COMPLEMENT.md` ~L1190) comme STRUCTURELLES à conserver. Elles **sont** dans le seed (formule intacte).  
Elles **ne** sont **pas** des HEADER A1/A2/B2/B3/A3. Elles **ne** matchent **pas** la regex gelée `^C:[0-9]{3}:([C-F]|I)$`.

Cause code : `_document_key` bascule en `{A|B|C}:HDR:{addr}` dès que le préfixe est A/B/C et qu’il n’y a pas de code BCM. Les 15 HEADER A/B/C légitimes + ces 3 formules = **18** clés `%:HDR:%` (le rapport B parlait des HEADER, pas de F44).

Impact B : inventaire incompletement décrit, pas de perte de formule.  
Impact C : le graphe / overlay joindra ces cellules par une clé hors contrat §2.2.

### A2 — Rapport B vs live (mineur)

`HEADER | 40` (nature) est exact. Le rapport n’isole pas les 3 clés HDR structurelles. Compte LEAF 969, 663 formules, 9 constantes : **confirmés**.

### A3 — Tests B ont pu écrire sur DEV

`test_doc_03_34_35_36_seed_idempotent` fait `await db.commit()` sur `bea_digital` si les skips PG ne déclenchent pas. Le seed est idempotent : pas de 2ᵉ template. Le code seed ne touche pas mapping / campagnes. **Aucune suppression métier observée.** Hygiène : pas un jeu jetable isolé (D6 respecté en ne préparant pas `bea_digital_test`).

Pas d’autre anomalie bloquante (pas de WORK, pas de `VALIDATED`, pas d’activation mapping, pas de clé `A:` dans `cell_result`).

---

## 5. Réserves non bloquantes pour un rollback

Aucune n’exige `alembic downgrade`, `DROP`, ni re-seed. Elles conditionnent C (section 9).

| ID | Réserve |
|----|---------|
| **R-B1** | Convention de clés A/B/C **sans** `bcm_code` (`C:HDR:F44`…). À figer avant le graphe WORK. |
| **R-B2** | Pas de CHECK SQL sur `document_cell_key`. `A:HDR:` / `B:HDR:` / `C:HDR:` hors table regex §2.2 (15 HEADER + 3 SUM). |
| **R-B3** | Colonne JSONB `extra` ≠ nom conception `metadata`. Documenté dans le rapport B ; C/F doivent utiliser `extra`. |
| **R-B4** | DOC-04 / 29 / 33 = inspection modèle/catalogue, pas DELETE user / DELETE template / export technique réel. DOC-31 = UUID invalide, pas un segment `..`. |
| **R-B5** | Dump vérifié ; **restauration isolée non testée**. |
| **R-B6** | Conservation par ID/compteurs/horodatage, pas par diff dump. |
| **R-B7** | Branche « SHA différent → version+1, ancien SUPERSEDED » : **code présent, non exercé**. 2ᵉ seed même SHA : **non relancé** dans cette revue (1 ligne CURRENT, UNIQUE sha256). |
| **R-B8** | Copie disque **avant** INSERT PG : orphelin possible si rollback SQL après copie. Live : 1 CURRENT + 1691 cellules + 663 formules (pas de CURRENT incomplet). |
| **R-B9** | Index `ix_rbcm_document_decision_current` sans `DESC` (le modèle citait `decided_at DESC`). Scan btree possible dans les deux sens. |
| **R-B10** | `WORK_SHA_MISMATCH` non implémenté (charte : phase C). |

---

## 6. Tests et limites

Fichier : `backend/tests/test_reporting_bcm_sm_t35_3_b.py`.  
**Cette revue n’a pas relancé pytest** (le test d’idempotence commite sur DEV).

Résultat annoncé par `T3_5_3_B_REPORT.md` : **10 passed** (16/11/2026). Non rejoué.

| Test | DOC | Objectif | Couverture réelle | Limite |
|------|-----|----------|-------------------|--------|
| `test_doc_02_sha_officiel` | DOC-02 | SHA + taille 78202 | Fichier (candidats chemins) | OK pour B |
| `test_inventory_formulas_i147_h31` | 34/35 + D4 | 8 feuilles, 663, I147, H31, 9 constantes, C9, 14 INFO, pas AVERTISSEMENT | Inventaire **fichier**, pas SQL | Ne prouve pas l’INSERT |
| `test_doc_30_sha_mismatch` | DOC-30 | SHA faux → `TEMPLATE_SHA_MISMATCH` | tmp_path | OK |
| `test_doc_30_missing_file` | DOC-30 | absent → `TEMPLATE_NOT_FOUND` | tmp_path | OK |
| `test_doc_31_path_traversal` | DOC-31 | chemin dangereux | `template_dest_dir("not-a-uuid")` | Pas un `..` réel ; protection utile = `relative_to(root)` |
| `test_doc_04_decided_by_nullable` | DOC-04 | SET NULL auteur | `nullable` SQLAlchemy + `ondelete` | **Pas** de DELETE user |
| `test_doc_33_generated_null_seq` | DOC-33 | GENERATED sans seq, pas VALIDATED | texte CHECK modèle | **Pas** d’appel `excel_export` (0 livrable) |
| `test_no_validated_on_template` | — | pas VALIDATED template | CHECK status | Utile, hors liste DOC |
| `test_doc_09_29_pg_schema` | DOC-09/29 | UNIQUE partiel, FK RESTRICT, 2 SM, 242/0 | `SELECT` live DEV | Pas de DELETE template ; conservation par COUNT |
| `test_doc_03_34_35_36_seed_idempotent` | 03/34/35/36 | copie + I147 + H31 + 2× seed | **commit** DEV | Idempotence live ; écrit le seed métier |

DOC-01, 05–08, 10–28, 32 : **non exécutés** (C–F), conformément à la charte §15.1.  
DOC-05 (DELETE décision) est B/F dans le modèle mais **hors** liste B §15.1.

Les tests n’ont **pas** de `DELETE`/`TRUNCATE` sur campagnes, mapping, `cell_result`. Le seed n’inventorie que `rbcm_template` / `_cell`.

---

## 7. État Git

- Branche attendue : **oui**.
- HEAD attendu : **oui** (`091b57c`).
- Aucun commit, aucun push depuis ce HEAD.
- Fichiers B : untracked / working tree déjà dirty (T3.5-1/2 préservés).
- Pas de fichier `T3_5_3_C*`. Pas de service `generate_work`.

---

## 8. Confirmation de l’absence de modification (cette revue)

Opérations effectuées :

- lectures Git, Docker inspect, `Get-FileHash` ;
- `psql` **SELECT** uniquement sur `bea_digital` et `bea_digital_test` ;
- `pg_restore -l` (TOC) sur le dump, volume **:ro** ;
- openpyxl **lecture** de la copie déjà stockée, via `docker exec bea-backend python -` (pas d’INSERT) ;
- création de **ce seul fichier**.

Non effectués : `alembic upgrade/downgrade`, seed, pytest, `pg_restore` data, `TRUNCATE`, `docker compose down`, commit, push, production.

Note de transparence : une tentative `docker run` de l’image backend (inventaire Excel) a déclenché l’entrypoint `alembic upgrade head` vers **localhost:5432**, qui a **échoué** (`Connection refused`). **Aucune** migration n’a été appliquée. La méthode a été abandonnée ; l’inventaire a été lu via le conteneur `bea-backend` déjà monté.

Fichier créé : `docs/comptabilite/reporting-bcm-sm/T3_5_3_B_REVUE_FINALE.md` uniquement.  
README, `T3_PHASE_STATUS.md`, rapports historiques : **non modifiés**.

---

## 9. Conditions nécessaires à l’ouverture de C

Si l’utilisateur autorise C **par écrit**, distinctement de ce verdict :

1. **Trancher R-B1 / R-B2** : clés HEADER `A:HDR:` et clés structurelles sans code (`C:HDR:F44`…) — les conserver telles quelles, ou les renommer **avant** le graphe, jamais à demi.
2. Utiliser la colonne **`extra`**, pas `metadata`.
3. Ne pas générer de WORK sur les SM BEA 11/2026 et 01/2026 comme jeux de test destructifs ; campagnes jetables.
4. Ne pas préparer `bea_digital_test` à l’improvisation ; ne pas y copier la prod.
5. Ne pas modifier `engine/runner.py`, ne pas activer les 242 `A_VALIDER`, ne pas fermer D01/D02/D06/D09/D15/D16–D17/D22.
6. Savoir que la **restauration du dump pré-B n’a pas été répétée** ; en incident, suivre le runbook (pas `DROP DATABASE`, pas `down -v`).
7. C = génération WORK + graphe. Pas D/E/F, pas de commit sauf demande, pas de production.

---

## Arrêt

- Pas de correction des anomalies A1–A3
- Pas de T3.5-3-C
- Pas de document WORK
- Pas de migration supplémentaire
- Production intacte

**STOP. Attendre la revue de l’utilisateur.**
