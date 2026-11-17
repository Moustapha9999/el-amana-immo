# T3.5-3-D — Rapport de livraison

API documentaire : liste, détail et téléchargement des documents WORK.  
**DEV Docker local uniquement.** Pas de phase E/F. Pas de commit.

Date : 16/11/2026.  
Autorisation : écrite, ce lot, après acceptation de C (`T3_5_3_C_REPORT.md`).

**Verdict : livrable D déposé sur DEV** (charte modèle §15.2).  
T3.5-3-E **n’est pas autorisée** par ce rapport.

---

## 1. Branche et HEAD

| Élément | Valeur |
|---------|--------|
| Branche | `feat/reporting-bcm-sm-t3` |
| HEAD | `091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32` (`091b57c`) |
| Checkout / reset / commit | **aucun** |
| Push / déploiement | **aucun** |

---

## 2. Environnement

Inchangé vs C : `bea-postgres` `127.0.0.1:5432` / `172.18.0.2`, base **`bea_digital`**, Alembic **`20261116_rbcm_05`**.  
**Aucune migration D.** Production non contactée. Volumes Docker inchangés.

`upload_root` : `/app/storage/uploads` (montage `storage/uploads`).

`bea_digital_test` : **non créée, non migrée, non utilisée** (D6). Schéma `rbcm_*` toujours absent de cette base.

---

## 3. Endpoints créés

Préfixe module existant : `/api/v1/reporting-bcm-sm`.  
Login 2 : `require_module_access("reporting-bcm-sm")` inchangé sur le routeur.

| Méthode | Route | Permission | Rôle |
|---------|-------|------------|------|
| `GET` | `/campaigns/{campaign_id}/documents` | `reporting-bcm-sm.view` | Liste des livrables de la SM |
| `GET` | `/campaigns/{campaign_id}/documents/{deliverable_id}` | `reporting-bcm-sm.view` | Métadonnées + historique |
| `GET` | `/campaigns/{campaign_id}/documents/{deliverable_id}/download` | `reporting-bcm-sm.export` | Fichier XLSX existant |

L’export technique historique `POST /exports/excel` et `GET /exports/{id}/download` **n’est pas modifié** (hors périmètre D).

### 3.1 Liste

Retour : `{ items, total }`. Chaque item expose : `id`, `kind`, `format` (`xlsx`), `status`, `document_seq`, `filename`, `sha256`, `sha256_available`, `created_at`, `created_by_id`, `template_id`, `superseded_by_id`, `is_current_work`, `generation_kind`, `regulatory_validated`, `work_disclaimer`.

Statuts distingués : **`GENERATED`**, **`WORK`**, **`SUPERSEDED`**.  
`regulatory_validated` est **toujours `false`**. WORK n’est jamais présenté comme `VALIDATED`.

### 3.2 Détail

Même contrat public + `warnings` (clés `path` / `dir` / `stored` filtrées) + `history` (séquence documentaire de la SM).  
`work_disclaimer` explicite : document de travail **non validé**.  
**Aucun `stored_path`.**

### 3.3 Téléchargement

Sert le fichier **déjà généré**. Aucun appel à `generate_work`, aucun appel à `engine/runner.py`, aucun recalcul de SM.

Contrôles avant `FileResponse` :

1. La SM existe.
2. Le livrable appartient à **cette** SM (`DELIVERABLE_NOT_FOUND` 404 sinon).
3. Nom de fichier sûr (`Path.name`, refus de `..` `/` `\`).
4. Chemin résolu **sous** `upload_root` **et** sous `reporting-bcm-sm/{campaign_id}/`.
5. Refus des `..`, chemins hors racine, liens symboliques sortants (`TEMPLATE_PATH_UNSAFE` 500).
6. Fichier présent sur disque (`DELIVERABLE_FILE_MISSING` 404).
7. Si `sha256` colonne renseigné : SHA-256 du fichier = colonne (`WORK_SHA_MISMATCH` 409).

`SUPERSEDED` reste téléchargeable (historique DOC-10). WORK courant aussi.

---

## 4. Permissions appliquées

Catalogue CORE existant — **aucun code parallèle**.

| Opération | Permission backend | Couverture |
|-----------|-------------------|------------|
| Liste / détail | `reporting-bcm-sm.view` | aussi `{module}.admin` via `user_has_permission_codes` (OR) |
| Téléchargement | `reporting-bcm-sm.export` | idem (`reporting-bcm-sm.admin` couvre) |

- Vérifications **uniquement backend** (`require_permission` + Login 2).
- Le rôle frontend n’autorise rien.
- `view` seul : liste/détail 200, téléchargement **403**.
- Sans permission : liste et téléchargement **403**.
- Lecteur métier (view+export) : les trois opérations.

---

## 5. Intégrité et sécurité chemins

Service : `backend/app/services/reporting_bcm_sm/document_access.py`.

| Contrôle | Comportement |
|----------|----------------|
| Appartenance SM | `campaign_id` du livrable = `{campaign_id}` d’URL |
| Jail `upload_root` | `Path.resolve()` + `relative_to(upload_root)` |
| Jail campagne | `relative_to(.../reporting-bcm-sm/{campaign_id})` |
| Traversée | `..` dans `stored_path` ou nom de fichier → refus |
| Symlink | cible résolue hors répertoire de la SM → refus |
| SHA-256 | comparé à la colonne si disponible ; pas de régénération si mismatch |
| Réponse | jamais de chemin physique, jamais de contenu dans l’audit |

---

## 6. Événements d’audit

`record_audit` existant (`AuditService.log`). Module `reporting-bcm-sm`, espace `comptabilite`.  
Pas de contenu fichier, pas de `stored_path`, pas de secret.

| Action | Entité | Résultat |
|--------|--------|----------|
| `rbcm.document.list` | `rbcm_campaign` | `after.result=ok`, `count` |
| `rbcm.document.get` | `rbcm_deliverable` | `ok`, `campaign_id`, `status`, `document_seq` |
| `rbcm.document.download` | `rbcm_deliverable` | `ok`, `sha256`, `filename`, `status`, `document_seq` |
| `rbcm.document.download_denied` | `rbcm_deliverable` | `denied`, `code` ; **commit avant raise** pour survivre au rollback `get_db` |

Les 403 `PERMISSION_DENIED` (Depends, avant handler) ne créent pas de ligne documentaire — convention existante des autres routes du module.

---

## 7. Tests et résultats

Fichier : `backend/tests/test_reporting_bcm_sm_t35_3_d.py`.

**Dispositif isolé** (identique C) : `docker compose run --rm --no-deps --entrypoint pytest` avec overlay `backend:/app` + `storage/uploads` + canevas officiel en lecture. Base **`bea_digital` DEV**, banque jetable **`T353D`**, périodes 2099-05 / 2099-06. Cleanup `DELETE` T353D uniquement. **Pas** `bea_digital_test`.

Commande :

```text
docker compose --env-file .env.docker run --rm --no-deps --entrypoint pytest
  -v backend:/app -v storage/uploads:/app/storage/uploads
  -v BEA-SM-10-2026.xlsx:/workspace/BEA-SM-10-2026.xlsx:ro
  backend tests/test_reporting_bcm_sm_t35_3_d.py -q --tb=short
```

**Résultat : 4 passed** (16/11/2026, 19,89 s).

| # | Cas demandé | Couverture | Résultat |
|---|-------------|------------|----------|
| 1 | Liste des documents d’une SM | HTTP GET liste : WORK / SUPERSEDED / GENERATED | OK |
| 2 | Détail | HTTP GET détail + disclaimer + history | OK |
| 3 | Téléchargement WORK valide | 200, magic `PK`, SHA = colonne | OK |
| 4 | Refus sans permission | 403 sans perm ; 403 `view` seul sur download | OK |
| 5 | Document d’une autre SM | 404 `DELIVERABLE_NOT_FOUND` | OK |
| 6 | Fichier manquant | 404 `DELIVERABLE_FILE_MISSING` | OK |
| 7 | SHA-256 incorrect | 409 `WORK_SHA_MISMATCH` | OK |
| 8 | Traversée de chemin | unité (`..`, hors root, symlink) + GENERATED malveillant | OK |
| 9 | Document SUPERSEDED | téléchargement 200 | OK |
| 10 | Traçabilité | `list` / `get` / `download` / `download_denied` | OK |

Le GET download est patché pour **interdire** `generate_work` pendant l’appel. Le nombre de livrables n’augmente pas.

---

## 8. Conservation des données

Mesure **après** tests et cleanup T353D :

| Invariant | Valeur |
|-----------|--------|
| Alembic | `20261116_rbcm_05` |
| SM BEA 01/2026 et 11/2026 | 2, `CALCULEE`, `template_version_id` **NULL** |
| Mappings `A_VALIDER` | **242** |
| Mappings `ACTIVE` | **0** |
| `rbcm_cell_result` | **92** |
| `rbcm_control_run` | **2** |
| Livrables BEA | **0** |
| Reliquat T353D / T353C | **0** |
| Template SHA-256 | `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658` |
| Clés `C:STRUCT:F44/F46/F48` | présentes |
| `engine/runner.py` | **non modifié** |
| `docker compose down -v` | **non exécuté** |

Aucune régénération des WORK de test BEA (il n’y en a pas). Aucune suppression d’historique métier.

---

## 9. Fichiers créés ou modifiés (ce lot)

Créés :

- `backend/app/services/reporting_bcm_sm/document_access.py`
- `backend/tests/test_reporting_bcm_sm_t35_3_d.py`
- `docs/comptabilite/reporting-bcm-sm/T3_5_3_D_REPORT.md`

Modifiés :

- `backend/app/api/v1/endpoints/reporting_bcm_sm.py` (3 GET documentaires)
- `backend/app/schemas/reporting_bcm_sm.py` (`DocumentOut` / `DocumentDetailOut`)
- `docs/comptabilite/reporting-bcm-sm/README.md`
- `docs/comptabilite/reporting-bcm-sm/T3_PHASE_STATUS.md`

Non modifiés : `engine/runner.py`, `work_fill.py`, `document_graph.py`, `formula_parser.py`, `document_keys.py`, mapping, SM BEA, Excel officiel, `excel_export.py`, volumes Docker.

---

## 10. Réserves

| Point | Traitement |
|-------|------------|
| O1 portes métier | toujours ouvertes (D01/D02/D06/D09/D15/D16–D17/D22) |
| UI consultation | phase **E**, non commencée |
| API décisions / corrections | phase **F**, non commencée |
| `bea_digital_test` | toujours sans `rbcm_*` ; tests D sur T353D / `bea_digital` |
| Download technique `/exports/.../download` | inchangé (pas de SHA/jail D) — hors lot |
| 403 permission | pas d’audit documentaire (Depends) |
| PDF | toujours hors périmètre |

---

## 11. Commit / push

**Aucun commit. Aucun push. Aucun déploiement.**

---

## Arrêt

- Pas d’interface utilisateur (E)
- Pas d’API décisions (F)
- Pas d’activation mapping
- Portes métier ouvertes
- Production intacte
- `runner.py` intact

**STOP. Attendre l’examen utilisateur avant T3.5-3-E.**
