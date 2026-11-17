# T3.3 — Rapport final

**Date :** 16/11/2026  
**Branche :** `feat/reporting-bcm-sm-t3`  
**Commit de base :** `091b57c` (aucun commit T3.3 effectué — en attente d’autorisation)  
**Environnement :** DEV uniquement  
**Alembic :** `20261116_rbcm_01` (aucune migration additive requise pour T3.3)

---

## A. État initial

| Élément | Valeur |
|---------|--------|
| Branche | `feat/reporting-bcm-sm-t3` |
| HEAD de départ | `091b57c` |
| Alembic DEV | `20261116_rbcm_01` |
| Mapping | 242 × `A_VALIDER`, 0 `ACTIVE` |
| Campagnes DEV | 1 (déjà présente) |
| Production | non touchée |

## B. Audit (T3.3-A)

Voir `T3_3_AUDIT.md`.

**Critique corrigé :** parser BAL DET lisait mal les colonnes (`NCG` était en col. 1). Colonnes réelles : `NCG, COMPTE, LIBELLE, DEVISE, DEB, CRE`.

## C. Développement

### Backend

- `import_service.py` — parsers DET/COND, SHA-256, preview, confirm transactionnel, reconcile, pagination lignes DET
- `campaign_service.py` — search/pagination/sort, delete contrôlée, reopen avec motif, progress, history
- `parameter_service.py` — catalogue 8 codes, validate/reject SoD, historique, dérivation `caisse_devises`
- `dashboard_service.py` — KPIs réels
- `endpoints/reporting_bcm_sm.py` — CRUD étendu, imports, reconcile+export CSV, params, dashboard
- `schemas/reporting_bcm_sm.py` — schémas enrichis

### Frontend

- Accueil dashboard KPI + graphiques SVG (`rbcm-charts.ts`)
- Liste campagnes : filtres, debounce, pagination serveur, drawer détail
- Nouvelle campagne : banque, période, date ref, libellé, description
- Fiche campagne : onglets Imports / Lignes DET / Rapprochement / Paramètres / Historique / Actions
- Drawers import, anomalie, paramètre (réutilise `bea-detail-drawer`)
- Feedback + confirmations UiDialog / FeedbackService

### Non fait / partiel

- Lien GED `ged_documents` systématique (stockage uploads module conservé)
- Import réel des fichiers oct. 2026 (55k + 228) : prêt côté code, non exécuté ici faute de dépôt des fichiers dans le workspace
- Tests e2e Angular non ajoutés (spec nav existante conservée)
- Celery pour import long : non introduit (batch SQL 1000 lignes en sync)

## D. Imports et données

| Élément | État |
|---------|------|
| Lignes importées en DEV (cette phase) | 0 (pas d’exécution fichier métier) |
| Mapping | toujours 242 `A_VALIDER` |
| ECART | désactivé |
| Paramètres | aucun report N−1 ; dérivation caisse = proposition documentée (préfixe NCG `101` + EUR) |

## E. Base de données

- **Migration créée :** aucune (schéma `rbcm_*` T3.1 suffisant)
- **Alembic final :** `20261116_rbcm_01`
- Mapping inchangé : 0 ACTIVE

## F. Tests

```text
docker run … pytest tests/test_reporting_bcm_sm.py
13 passed, 1 skipped
```

- Skip : fichier Correspondance absent du conteneur
- Nouveaux tests : colonnes DET, headers, VAR COND, SHA-256, pas de reconduction N−1

## G. Interface

| Page | État |
|------|------|
| Accueil / dashboard | terminé (données API) |
| Campagnes + drawer | terminé |
| Nouvelle | terminé |
| Détail (imports, lignes, reconcile, params) | terminé |
| Mapping | existant (lecture seule) |
| Graphiques SVG | terminés |
| Animations `prefers-reduced-motion` | respectées |

## H. Décisions métier restantes

Toujours ouvertes : **D01, D02, D06, D09, D15, D16/D17, D22** (+ D04/D05 pour règles exactes de dérivation paramètres).

La dérivation `caisse_devises` est **provisoire** (NCG `101*` EUR) et exige validation métier.

## I. État Git

- Branche : `feat/reporting-bcm-sm-t3`
- **Aucun commit / push** (consigne respectée)
- Fichiers modifiés / non suivis : module RBCM backend+front + docs T3.3

## J. Conclusion

**Terminé :** campagnes CRUD/versions/reopen, imports preview/confirm/idempotence SHA, reconcile, 8 paramètres + historique + dérivation proposée, UI dashboard/drawers/pagination, tests unitaires parsers, mapping non activé.

**Partiel :** import réel des balances octobre, GED native, tests front e2e, Celery.

**Bloqué :** état réglementaire final (dépend D01/D02/… et mapping ACTIVE).

**Risques :** règle provisoire caisse_devises ; volume DET 55k à valider en perf sur DEV avec fichiers réels.

**T3.4 recommandé :** validation métier des 242 mappings (activation contrôlée), arbitrage D01/D02, import de référence octobre, raffinement dérivation paramètres, éventuel Celery + barre de progression import.
