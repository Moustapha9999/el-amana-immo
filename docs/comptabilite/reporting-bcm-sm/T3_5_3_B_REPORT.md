# T3.5-3-B — Rapport de livraison

Migration additive `rbcm_05` + seed du canevas officiel.  
**DEV Docker local uniquement.** Pas de phase C. Pas de commit.

Date : 16/11/2026.  
Autorisation : écrite par l’utilisateur, ce lot.

**Verdict : livrable B accepté sur DEV** (critères §11 du prompt d’exécution).  
T3.5-3-C **n’est pas autorisée** par ce rapport.

---

## 1. Branche et HEAD

| Élément | Valeur |
|---------|--------|
| Branche | `feat/reporting-bcm-sm-t3` |
| HEAD | `091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32` (`091b57c`) |
| Checkout / reset / commit | **aucun** |

Travaux T3.5-1/2 **préservés** (working tree déjà dirty, non nettoyé).

---

## 2. Environnement Docker confirmé

| Conteneur | Image / rôle | Ports |
|-----------|--------------|-------|
| `bea-postgres` | `postgres:17-alpine` | `127.0.0.1:5432→5432` |
| `bea-backend` | `bea-digital-backend:latest` | interne 8000 |
| `bea-worker` | image locale | — |
| `bea-frontend` | `bea-digital-frontend:latest` | `80→8080` |
| `bea-redis` | `redis:7-alpine` | interne |
| `bea-pgadmin` | `dpage/pgadmin4:9.18` | `127.0.0.1:5050` |

Réseau : `bea_internal`. IP Postgres : `172.18.0.2`.  
Volume données : `bea_postgres_data` → `/var/lib/postgresql/data`.  
**Aucun** `docker compose down -v`, **aucun** rebuild d’image.

Migration appliquée par le service `migrate` avec **volume source** `backend:/app` (même procédé que rbcm_03/04).

---

## 3–5. Base locale — pas de production

Connexion **réelle** (pas la seule variable `DATABASE_URL`) :

| Source | `current_database` | utilisateur | `inet_server_addr` | port |
|--------|--------------------|-------------|--------------------|------|
| `docker exec bea-postgres psql` | `bea_digital` | `admin` | (socket local) | — |
| Python dans `bea-backend` | `bea_digital` | `bea_app` | **`172.18.0.2`** | **5432** |

Hôte Docker `postgres` (compose), bind hôte **`127.0.0.1:5432` uniquement**.  
Pas d’IP publique, pas de tunnel, pas d’hôte distant.

**Aucune connexion de production n’a été ouverte.** Production `v1.0.0` non interrogée.

Nom de la base métier : **`bea_digital`**.  
`bea_digital_test` : vue en lecture seule (`alembic_version` = `20261105_mg_stock_mvt_ref_uq`, 0 table `rbcm_*`) — **non migrée**.

---

## 6. Alembic avant / après

| Moment | `bea_digital` |
|--------|----------------|
| Avant | `20261116_rbcm_04` |
| Après | **`20261116_rbcm_05`** |

`bea_digital_test` inchangé.

---

## 7. Sauvegarde préalable

| Champ | Valeur |
|-------|--------|
| Fichier | `backups/t353b_pre_rbcm05_20261116_231452.dump` |
| Taille | 9 110 083 octets (non vide) |
| SHA-256 | `B6ABA65DAE89E8D060FAC8CAC562E7DA01E2AFE7BB6AAB016C5DA501C30279AA` |
| Format | pg_dump custom (`-Fc`), gzip |
| TOC | 2235 / listing `pg_restore -l` = 2245 lignes |
| dbname dans l’archive | `bea_digital` |
| pg_dump | 17.11 |

La sauvegarde n’a **pas** été validée sur le seul code retour : existence, taille, SHA et TOC ont été relus.

---

## 8. `upload_root` réel

| Contexte | Valeur |
|----------|--------|
| `settings.upload_dir` (backend) | `storage/uploads` |
| Dans le conteneur | `/app/storage/uploads` |
| Montage hôte | `C:\Users\sallm\bea-digital\storage\uploads` |
| Copie template | `{upload_root}/reporting-bcm-sm/templates/{uuid}/` |

---

## 9–10. Migration additive

Fichier : `backend/alembic/versions/20261116_rbcm_05_document_model.py`  
`Revises: 20261116_rbcm_04`. DDL transactionnel. Pas de DROP de tables T3.5-1/2.

Créé :

- `rbcm_template` (PK UUID, UNIQUE sha256, UNIQUE (code, version), unique partiel `CURRENT`, FK `created_by_id` SET NULL)
- `rbcm_template_cell` (FK template RESTRICT, UNIQUE addr, UNIQUE document_cell_key, CHECK natures)
- `rbcm_document_decision` (`decided_by_id` nullable SET NULL, historiques RESTRICT, `reason` NOT NULL)
- Colonnes livrable **nullable** : `template_id`, `document_seq`, `superseded_by_id`
- CHECK D1 : `GENERATED` ⇔ seq et template NULL ; `WORK`/`SUPERSEDED` ⇔ seq ≥ 1 et template NOT NULL
- UNIQUE partiel `(campaign_id, document_seq) WHERE document_seq IS NOT NULL`
- UNIQUE partiel un seul `WORK` par campagne
- FK `rbcm_campaign.template_version_id` → `rbcm_template` RESTRICT (valeurs existantes toutes NULL)

JSONB : colonnes SQL `extra` (équivalent conception `metadata` — `metadata` est réservé SQLAlchemy).

Pas de statut `VALIDATED`.

---

## 11. Conservation des données antérieures

| Objet | Après rbcm_05 |
|-------|----------------|
| Campagnes BEA 01/2026 et 11/2026 | 2, `CALCULEE`, inchangées |
| Règles mapping | 242 `A_VALIDER`, **0** `ACTIVE` |
| `rbcm_control_run` | 2 |
| `rbcm_cell_result` | 92 (non mutés) |
| `rbcm_cell_decision` | 0 |
| `rbcm_deliverable` | 0 |

`engine/runner.py` **non modifié**.

---

## 12. Canevas source

| Propriété | Mesure |
|-----------|--------|
| Fichier | `BEA-SM-10-2026.xlsx` (racine dépôt) |
| Taille | 78 202 |
| SHA-256 | `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658` |
| Feuilles | 8, noms T0, **pas** `AVERTISSEMENT` |
| Formules | **663** |

---

## 13. Copie persistante

```
storage/uploads/reporting-bcm-sm/templates/342dee7d-cd82-4e1e-b468-6e1ddef1606b/BEA-SM-10-2026.xlsx
```

Taille 78 202. SHA copie = SHA source (contrôle avant et après).  
UUID interne. `Path.resolve()`. Traversée `..` refusée (`TEMPLATE_PATH_UNSAFE`).

---

## 14. Seed et idempotence

1ʳᵉ exécution : `created=true`, version 1, 1691 cellules, template_id `342dee7d-…`.  
2ᵉ exécution : **`idempotent=true`**, même id, 0 doublon.

| Contrôle | Résultat |
|----------|----------|
| Formules | 663 |
| `OCTOBER_CONSTANT_FORMULA` | 9 |
| `A:CTRL:I147` | 1, formule `=+H147-H81` |
| `RCR:H31` | `CANVAS_SCALE_FORMULA`, `='CALCUL FPN'!C39*10` |
| `CANVAS_SCALE_FORMULA` | 3 (H31, LIQ D20, FPN F33) |
| INFO leaves | 14 ; C9 formule `='ETAT A'!D146` |
| Couverture E | E7:E17 et E20:E25 (**17**) ; **E18/E19 absents du fichier** (non inventés) |
| D09 | 3 PCT + 3 remainder |
| CONCORDANCE_IF | 27 |
| `AVERTISSEMENT` | 0 ligne |
| HEADER | 40 (5 × 8 feuilles) |

Clés HEADER A/B/C : `A:HDR:{addr}` (convention seed, hors axes C–H).  
`depends_on` non peuplé (phase C).

---

## 15. Tests DOC exécutés (phase B)

Fichier : `backend/tests/test_reporting_bcm_sm_t35_3_b.py`  
Résultat : **10 passed**.

| ID | Résultat |
|----|----------|
| DOC-02 SHA officiel | OK |
| DOC-03 copie sous upload_root | OK (seed + fichier) |
| DOC-04 `decided_by_id` nullable SET NULL | OK |
| DOC-09 UNIQUE partiel seq | OK (pg_indexes) |
| DOC-29 template FK RESTRICT | OK |
| DOC-30 SHA mismatch / fichier absent | OK |
| DOC-31 `..` / UUID | OK |
| DOC-33 GENERATED sans seq, pas VALIDATED | OK |
| DOC-34 I147 | OK |
| DOC-35 H31 scale | OK |
| DOC-36 seed idempotent | OK |

---

## 16. Tests non exécutés

DOC-01, 05–08, 10–28, 32 : **phases C–F** (WORK, graphe, API, UI, décisions). Non prétendus réalisés.

`bea_digital_test` : pas de suite rbcm ; non préparée (D6).

---

## 17. Risques et réserves

| Point | Traitement |
|-------|------------|
| Image Docker ≠ working tree | migrate/pytest via volume `/app` ; pas de rebuild |
| Colonne SQL `extra` vs conception `metadata` | documenté ; pas de collision SQLAlchemy |
| `A:HDR:*` | clés HEADER A/B/C, pas des axes métier |
| Compte LEAF 969 | sortie fichier, pas un entier figé à l’avance |
| O1 portes | toujours ouvertes |
| WORK / graphe | hors B |

---

## 18. Restauration (incident)

Ne pas l’exécuter tant qu’aucun incident.

1. Arrêter d’écrire sur `bea_digital`.
2. Dump actuel de précaution (autre nom).
3. Restaurer `backups/t353b_pre_rbcm05_20261116_231452.dump` via `pg_restore` **dans une procédure contrôlée** (scripts `db-restore` — refuse l’écrasement d’un schéma non vide : suivre le runbook, ne pas improviser `DROP DATABASE`).
4. Vérifier `alembic_version` = `20261116_rbcm_04` si retour avant B.
5. La copie template sous `storage/uploads/.../templates/{uuid}/` peut rester (immuable) ; elle n’est plus référencée si la table est revenue en arrière.

**Interdit :** `alembic downgrade` en routine, `TRUNCATE`, `docker compose down -v`.

---

## 19. Fichiers créés ou modifiés (ce lot)

Créés :

- `backend/alembic/versions/20261116_rbcm_05_document_model.py`
- `backend/app/services/reporting_bcm_sm/template_storage.py`
- `backend/app/services/reporting_bcm_sm/template_seed.py`
- `backend/scripts/rbcm_seed_template.py`
- `backend/tests/test_reporting_bcm_sm_t35_3_b.py`
- `docs/comptabilite/reporting-bcm-sm/T3_5_3_B_REPORT.md`
- copie persistante sous `storage/uploads/reporting-bcm-sm/templates/342dee7d-…/`
- dump `backups/t353b_pre_rbcm05_20261116_231452.dump`

Modifiés :

- `backend/app/models/reporting_bcm_sm.py`
- `backend/app/models/__init__.py`
- `docs/comptabilite/reporting-bcm-sm/README.md`
- `docs/comptabilite/reporting-bcm-sm/T3_PHASE_STATUS.md`

Non modifiés : `engine/runner.py`, mapping, campagnes, Excel officiel git, rapports T0 / revue A historiques.

---

## 20. Commit / push

**Aucun commit. Aucun push.**

---

## Arrêt

- Pas de génération WORK
- Pas d’API documentaire nouvelle
- Pas d’UI
- Pas de décisions documentaires en base (0 ligne)
- Pas d’activation mapping
- Portes D01/D02/D06/D09/D15/D16-D17/D22 ouvertes
- Production intacte

**STOP. Attendre l’examen utilisateur avant T3.5-3-C.**
