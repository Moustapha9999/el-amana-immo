# T3.5-1 — Fiche guidée et désignation du responsable SM

Branche : `feat/reporting-bcm-sm-t3` · HEAD de référence `091b57c`  
**Aucun commit / push / déploiement production.** DEV uniquement.

Référence métier : `T3_5_WORKFLOW_CONCEPTION.md`.  
Hors périmètre : T3.5-2 à T3.5-6, mapping ACTIVE, ECART, D01/D02, moteur, canevas Excel.

---

## 1. Décisions d’implémentation (minimales)

| Sujet | Choix |
|-------|--------|
| Créateur | `preparer_id` inchangé (audit historique) |
| Responsable | `reporting_owner_id` + `reporting_owner_set_at` |
| Historique | Table append-only `rbcm_reporting_owner_history` (jamais d’UPDATE) |
| Identifiants techniques | `rbcm_campaign`, `/campaigns`, `campaign_id` conservés |
| Vocabulaire UI | SM / Situation Mensuelle |
| Liste des responsables | Utilisateurs actifs avec `reporting-bcm-sm.prepare` **ou** `reporting-bcm-sm.admin` **ou** superuser, **et** habilitation Login 2 au module |
| Changement de responsable | Permission `reporting-bcm-sm.prepare` (couverte par `reporting-bcm-sm.admin`) ; motif obligatoire ; interdit si `APPROUVEE` / `CLOTUREE` |
| Unicité | P2 inchangé (`CAMPAIGN_OPEN_EXISTS`) |
| SM existantes | Backfill `reporting_owner_id = preparer_id` ; aucune suppression |
| Date d’arrêté | Si absente à la création : dernier jour du mois (aide comptable, pas un champ UI) |

SoD workflow (`preparer_id ≠ approver`) **non modifié** : T3.5-5 tranchera si la séparation doit porter sur le responsable plutôt que sur le créateur.

---

## 2. Migration et stratégie de sécurité

Fichier : `backend/alembic/versions/20261116_rbcm_02_reporting_owner.py`  
Révision : `20261116_rbcm_01` → `20261116_rbcm_02`

Opérations **additives** uniquement :

1. Colonnes `reporting_owner_id` (FK `users`, `ON DELETE SET NULL`) et `reporting_owner_set_at`.
2. Table `rbcm_reporting_owner_history` (FK campagne `RESTRICT`).
3. Backfill : responsable = créateur pour les SM déjà présentes.
4. Une ligne d’historique initiale par SM existante (`Désignation initiale (migration T3.5-1)`).

**Non fait :** `DELETE`, `DROP` de données métier, reset Git, `docker compose down -v`.

Appliquée en DEV :

```
Running upgrade 20261116_rbcm_01 -> 20261116_rbcm_02
alembic_version = 20261116_rbcm_02
```

---

## 3. API ajoutées ou adaptées

| Méthode | Chemin | Permission | Rôle |
|---------|--------|------------|------|
| `GET` | `/api/v1/reporting-bcm-sm/preparateurs` | `prepare` | Liste des responsables éligibles |
| `POST` | `/campaigns` | `prepare` | Accepte `reporting_owner_id` (défaut = créateur) |
| `GET` | `/campaigns`, `/campaigns/{id}` | `view` | Ajoute noms créateur / responsable |
| `POST` | `/campaigns/{id}/reporting-owner` | `prepare` | Changement + audit `rbcm.campaign.owner_change` |
| `GET` | `/campaigns/{id}/reporting-owner/history` | `view` | Historique chronologique |

Codes d’erreur nouveaux :

| Code | Sens |
|------|------|
| `OWNER_NOT_FOUND` | Utilisateur inexistant |
| `OWNER_INACTIVE` | Compte inactif |
| `OWNER_NOT_PREPARER` | Pas la permission `prepare` |
| `OWNER_REASON_REQUIRED` | Motif manquant |
| `OWNER_UNCHANGED` | Même responsable |
| `CAMPAIGN_LOCKED` | SM `APPROUVEE` / `CLOTUREE` |

Audit applicatif : création (créateur + responsable) et chaque changement (ancien / nouveau / motif).  
Événements workflow : `OWNER_ASSIGN`, `OWNER_CHANGE` (en plus de la table dédiée).

---

## 4. Comportement frontend

**Création** (`Nouvelle Situation Mensuelle`) :

- Mois, année, responsable (liste `GET /preparateurs`).
- Confirmation via `FeedbackService` avant `POST`.
- Le créateur connecté est proposé par défaut ; un autre préparateur peut être désigné.
- Banque `BEA` implicite ; plus de champs techniques (libellé, SHA, NCG).

**Fiche SM** :

- Période, créateur, responsable actuel, date de désignation, date de création.
- Parcours guidé 7 étapes ; après création l’étape courante est **BAL DET**.
- Bouton contextuel **Importer BAL DET** uniquement si la DET n’est pas encore confirmée et si la SM n’est pas figée.
- Historique des responsables (append-only).
- Changement de responsable : select + motif obligatoire (`runWithReason`).
- Mapping / calcul / export : relégués dans **Accès expert**.

**Liste** : colonne Responsable.

---

## 5. Permissions et Login 2

- Créer / désigner / changer : `reporting-bcm-sm.prepare` (Login 2 déjà exigé par le module).
- `reporting-bcm-sm.admin` couvre `prepare` (racine `{module}.admin`).
- Lecteur (`view`) : voit la fiche et l’historique, ne change pas le responsable, n’obtient pas l’annuaire des préparateurs.
- Un responsable non autorisé est refusé **backend** (`OWNER_NOT_PREPARER`), même si l’UI ne le propose pas.

---

## 6. Tests exécutés

```
backend/tests/test_reporting_bcm_sm.py
backend/tests/test_reporting_bcm_sm_t35_1.py
39 passed in 5.85s
```

Couverture T3.5-1 :

| Cas | Résultat |
|-----|----------|
| Création avec responsable ≠ créateur | OK |
| Responsable sans `prepare` refusé | OK (`OWNER_NOT_PREPARER`) |
| Admin module accepté comme responsable | OK |
| Motif obligatoire (schéma + service) | OK |
| Historique append-only (INSERT, pas d’UPDATE) | OK |
| Doublon de période ouverte (P2) | OK (`CAMPAIGN_OPEN_EXISTS`) |
| SM figée : changement interdit | OK |
| Même responsable : refusé | OK |
| Moteur / imports non touchés | OK (inspection source) |
| Migration additive + backfill | OK (inspection + DEV) |

Frontend : spec `currentGuidedStep` ajoutée dans `rbcm-nav.spec.ts` (build production Angular réussi).

---

## 7. Préservation des données DEV

Avant / après migration `rbcm_02` :

| SM | Statut | Imports | Résultat |
|----|--------|---------|----------|
| `11/2026` v1 (`a9c8832b-…`) | `CALCULEE` | 3 (inchangé) | Conservée |
| `01/2026` v1 | `CALCULEE` | — | Conservée |

Backfill : `reporting_owner_id = preparer_id` (`6b99bb89-…`) + une ligne d’historique initiale par SM.  
Aucune ligne d’import, de calcul ou de mapping n’a été modifiée.

---

## 8. Fichiers touchés (T3.5-1)

**Backend**

- `backend/app/models/reporting_bcm_sm.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/reporting_bcm_sm.py`
- `backend/app/services/reporting_bcm_sm/campaign_service.py`
- `backend/app/api/v1/endpoints/reporting_bcm_sm.py`
- `backend/alembic/versions/20261116_rbcm_02_reporting_owner.py`
- `backend/tests/test_reporting_bcm_sm_t35_1.py`

**Frontend**

- `frontend/angular20/src/app/reporting-bcm-sm/rbcm.models.ts`
- `frontend/angular20/src/app/reporting-bcm-sm/rbcm-ui.component.ts`
- `frontend/angular20/src/app/reporting-bcm-sm/pages/rbcm-campagne-nouvelle.component.ts`
- `frontend/angular20/src/app/reporting-bcm-sm/pages/rbcm-campagne-detail.component.ts`
- `frontend/angular20/src/app/reporting-bcm-sm/pages/rbcm-campagnes.component.ts`
- `frontend/angular20/src/app/reporting-bcm-sm/rbcm-nav.spec.ts`

**Docs**

- `docs/comptabilite/reporting-bcm-sm/T3_5_1_REPORT.md` (ce fichier)
- `docs/comptabilite/reporting-bcm-sm/README.md` (index)

Non modifiés : `engine/runner.py`, `import_service.py`, mapping, ECART, workflow D01/D02.

---

## 9. Limites et suite

1. **T3.5-2** (contrôles classés, file des manques, relance) n’est pas commencé — attendre validation de ce rapport.
2. Boutons Contrôler / Compléter / Préparer / Valider **volontairement absents** du parcours principal (lots suivants).
3. SoD d’approbation reste calée sur `preparer_id` (créateur), pas encore sur le responsable.
4. Réouverture : le responsable de la version source est recopié ; le créateur de la nouvelle version est l’utilisateur qui rouvre.
5. Build Angular : avertissement budget CSS `rbcm-ui` (8,35 ko / 8 ko) — cosmétique, déjà dans la zone des styles partagés.
6. Pas de Playwright Login 2 dans ce lot (flakiness connue T3.4-C).

---

## 10. État Git

- Branche dirty `feat/reporting-bcm-sm-t3`
- HEAD `091b57c`
- **Pas de commit, pas de push**
- Production v1.0.0 hors périmètre
