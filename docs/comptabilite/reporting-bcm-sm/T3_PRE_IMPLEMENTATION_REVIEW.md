# T3 — Revue pré-implémentation (décision de démarrage)

**Module :** Reporting BCM SM (Comptabilité) — distinct du BCM Clientèle  
**Date de revue :** 16/11/2026  
**Nature :** analyse et restitution uniquement — **aucune implémentation**, aucune migration, aucune modification applicative  
**Décision attendue :** validation explicite utilisateur avant tout code T3  

---

## 1. État Git

| Élément | Valeur |
|---------|--------|
| Branche | `chore/audit-nettoyage-pre-deploiement` |
| Commit courant | `091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32` |
| Message HEAD | `docs(deploiement): aligner transmission srvsuividep et porte de release` |
| Working tree | **propre hors documentation** : uniquement `?? docs/comptabilite/` (non suivi) |
| Modifications applicatives depuis la dernière mission | **Aucune** (`backend/`, `frontend/`, migrations, config, DB) |
| Dossier cible | `docs/comptabilite/reporting-bcm-sm/` — présent (6 fichiers `.md` + ce livrable) |

Les quatre documents demandés sont présents et complets :

1. `T2_FINAL_VALIDATION.md`
2. `T2_OPEN_DECISIONS.md`
3. `T3_IMPLEMENTATION_PLAN.md`
4. `T3_ACCEPTANCE_CRITERIA.md`

Aucun fichier applicatif n’a été modifié dans cette mission.

---

## 2. Synthèse des quatre documents

### 2.1 `T2_FINAL_VALIDATION.md`

- T2 **VALIDÉ (conception)** le 16/11/2026 sur la même branche / commit.
- Corrections A–I intégrées (soldes, décisions append-only, ECART par campagne, Excel Python=vérité, workflow 3 rôles, `Numeric(18,2)`, imports, mapping `A_VALIDER`, paramètres).
- Points validés : module `reporting-bcm-sm`, espace `comptabilite`, préfixe `rbcm_`, API `/api/v1/reporting-bcm-sm/`, UI `/reporting-bcm-sm/...`, réutilisation CORE, distinction BCM Clientèle, socle T3 séparé des phases imports/moteur.
- Ouverts : D01, D02, D04, D05, D09, D15 (+ suite), LibreOffice/PDF, alignement Alembic sur DB **dev**, matrice compte×cellule absente.
- Risques : mapping prématuré, ECART en dur, confusion Clientèle, stockage `release-source`, multi-heads Alembic.
- **T3 prêt à démarrer après validation explicite** — cette validation T2 **ne commence pas** le code.

### 2.2 `T2_OPEN_DECISIONS.md`

Inventaire des décisions ouvertes avec échéances B-T3 / B-T4 / B-PROD / FUTUR.  
Bloquants déclarés pour T3 dans ce fichier : **P1**, **P2**, **ALEMBIC** (avant `upgrade`).  
Hypothèses non validées métier : `Numeric(18,2)`, SD/SC par règle (D15), réouverture = nouvelle `campaign_version` (P2).

### 2.3 `T3_IMPLEMENTATION_PLAN.md`

Socle uniquement : catalogue, hub `/comptabilite`, routes Angular, Login 2, permissions, page d’accueil, CRUD campagne minimal, audit, tests, migration additive éventuelle.  
Exclus : imports, rapprochement, mapping, paramètres, moteur, Excel, workflow 3 niveaux complet, PDF.  
Unicité proposée sous réserve P2. Tip Alembic fichiers : `20261105_mg_stock_mvt_ref_uq`.

### 2.4 `T3_ACCEPTANCE_CRITERIA.md`

Critères C1–C15 + tests fonctionnels, sécurité, concurrence, audit.  
T3 accepté si C1–C15 OK et aucun hors-périmètre ; puis seulement ouverture T4.

*(Restitution intégrale des quatre documents : annexes A–D en fin de ce fichier et dans la réponse de mission.)*

---

## 3. Décisions ouvertes — analyse structurée et classement A–E

Légende de classement (mission) :

- **A** — Bloquante avant démarrage T3 (empêche réellement le socle)  
- **B** — Non bloquante pour le socle T3  
- **C** — Bloquante avant T4 (imports / rapprochements / paramètres)  
- **D** — Bloquante avant moteur de calcul  
- **E** — Bloquante avant livraison réglementaire  

### 3.1 Fiches décision

#### P1 — Code module `reporting-bcm-sm` vs `reporting-compta`

| Champ | Contenu |
|-------|---------|
| Statut | Ouverte (docs T0–T2 utilisent déjà `reporting-bcm-sm`) |
| Responsable | Produit / Comptabilité |
| Conséquence technique | Catalogue, `MODULES_WITH_METIER_SHELL`, routes, perms, prefix API/UI, seed rôles |
| Conséquence métier | Identité du module dans le hub Comptabilité |
| Risque si ouvert | Renommage après seed = dette forte (perms, grants, URLs, audit) |
| À résoudre avant | Première entrée catalogue / première PR T3 qui fige le code |
| **Catégorie** | **A (confirmation nominale)** — mais le **socle peut démarrer sous le code provisoire déjà figé dans T2** dès confirmation écrite Produit. Sans confirmation, ne pas seed en prod/recette. |

**Justification :** ce n’est pas un blocage d’architecture (le plan T3 est déjà cohérent autour de `reporting-bcm-sm`) ; c’est un **verrou produit** avant d’écrire le code irréversible. Classé A pour la décision formelle, pas pour l’incertitude technique.

#### P2 — Une campagne active / période **ou** versions à chaque réouverture

| Champ | Contenu |
|-------|---------|
| Statut | Ouverte ; plan T3 propose `campaign_version` + unicité `(bank, year, month, version)` |
| Responsable | Comptabilité / Archi |
| Conséquence technique | Contrainte UNIQUE, service anti-doublon, C8/C7, tests concurrence |
| Conséquence métier | Historique des réouvertures, auditabilité des campagnes |
| Risque si ouvert | Schéma UNIQUE faux → migration corrective ; ou doublons métier |
| À résoudre avant | Migration `rbcm_campaign` et API POST création |
| **Catégorie** | **A pour la table campagne / API création** ; **B pour catalogue, routes, Login 2, accueil** |

#### D15 — Nature TOTDEB/TOTCRE

| Champ | Contenu |
|-------|---------|
| Statut | Ouverte |
| Responsable | DSI / Comptabilité |
| Conséquence technique | Toutes règles D/C du moteur |
| Conséquence métier | Exactitude des soldes / mouvements |
| Risque | Moteur faux sur toutes cellules D/C |
| À résoudre avant | Moteur (pas T3) |
| **Catégorie** | **D** |

#### D01 — Arbitrages mapping (comptes listés)

| Champ | Contenu |
|-------|---------|
| Statut | Ouverte ; mapping forcé `A_VALIDER` |
| Responsable | Comptabilité |
| Conséquence | Activation des 115 règles |
| Risque | Livrable réglementaire faux |
| **Catégorie** | **E** (activation mapping / T6) — **B** pour T3 |

#### D02 — Formaliser ECART / « selon le solde »

| Champ | Contenu |
|-------|---------|
| Statut | Ouverte ; ECART inactif sans D02 |
| Responsable | Comptabilité |
| **Catégorie** | **E** (activation ECART) — **B** pour T3 ; utile aussi en **D** si COD/D38 dans le moteur |

#### D04 — Sources des 8 paramètres

| **Catégorie** | **C** (params) puis **D** pour cellules mixtes |

#### D05 — Listes publics / projets

| **Catégorie** | **C** / **D** selon usage dans règles |

#### D06 — 67 rubriques sans règle

| **Catégorie** | **E** (gate BCM) — **B** pour T3 |

#### D08 — Provisions 290000 / 356000

| **Catégorie** | **E** / **D** — **B** pour T3 |

#### D09 — Fichier crédits / dépôts

| **Catégorie** | **C** (imports annexes) puis **E** pour B/C réels |

#### D10–D14 — Canevas / double comptage / FPN / circuit dépôt BCM

| **Catégorie** | **E** |

#### D16–D17 — Résidence / correspondants

| **Catégorie** | **E** |

#### D18–D22 — Liquidité, zéro, maturité, contrôles, conflit mapping

| **Catégorie** | **E** (et **D** pour ratios dans le moteur) |

#### REF-223 / REF-218 — Écarts historiques 2 873 223 / 2 873 218

| **Catégorie** | **B** — références documentaires, pas constantes à coder |

#### DSI-LO / DSI-PDF

| **Catégorie** | **B** pour T3–T5 ; **E** si PDF officiel exigé en V1 (docs : pas V1) |

#### DSI-SRV — Stockage hors `release-source` → `/srv`

| **Catégorie** | **C** (recommandé avant volumes T4) — **B** pour T3 (pas de gros fichiers) |

#### MATRICE — Matrice compte×cellule

| **Catégorie** | **D** / **E** (précision mapping T6) — **B** pour T3 |

#### SEPT — BAL + SM septembre (non-régression)

| **Catégorie** | **E** (recette) — **B** pour T3 |

#### ALEMBIC — `heads` / `current` sur DB **dev**

| Champ | Contenu |
|-------|---------|
| Statut | Contrôle fichiers dépôt OK (1 head) ; **current** sur DB dev **non vérifié** (interdit d’exécuter migration / pas de connexion imposée ici) |
| Responsable | Dev |
| Conséquence | Première migration `rbcm_*` |
| Risque | Branchement sur mauvaise head / drift DB |
| À résoudre avant | Premier `alembic upgrade` (pas avant rédaction du code modèle) |
| **Catégorie** | **A pour exécution migration** ; **B pour rédaction code hors DB** |

### 3.2 Synthèse des classements

| Catégorie | Décisions |
|-----------|-----------|
| **A** | P1 (confirmation code), P2 (unicité campagne pour schéma/API), ALEMBIC (avant `upgrade`) |
| **B** | REF-223, REF-218, DSI-LO, DSI-PDF (V1), D01/D06/D08 (pour le socle), MATRICE/SEPT (pour T3) |
| **C** | D04, D05, D09 (imports), DSI-SRV |
| **D** | D15, (D02/D04/D05/D08/D18–D22 pour parties moteur) |
| **E** | D01 (activation), D02 (activation ECART), D06, D08–D14, D16–D22, SEPT, PDF si exigé |

**Point clé :** toutes les décisions P1/P2 ne sont **pas** automatiquement bloquantes pour *tout* T3. Catalogue, hub, Login 2, routes, accueil et permissions peuvent avancer sans P2 ni D15. En revanche, **création campagne + contrainte UNIQUE + migration** dépendent de P2 (+ ALEMBIC pour l’upgrade).

---

## 4. Analyse spécifique `Numeric(18,2)`

### 4.1 Sources vérifiées

Fichiers réels (poste local) :

- `C:\Users\sallm\Downloads\BAL DET 31-10-2026.xlsx`
- `C:\Users\sallm\Downloads\BAL COND 31-10-2026.xlsx`

Analyse exécutée en **Python `Decimal`** (pas `float`) via openpyxl `data_only=True`.

### 4.2 Résultats observés

| Métrique | BAL DET | BAL COND |
|----------|---------|----------|
| Valeurs numériques lues (D+C) | 110 384 | 474 |
| Non numériques | 0 | 0 |
| `|max|` observé | **3 979 355 213** (~10 chiffres) | **25 868 433 484** (~11 chiffres) |
| Échelle max (décimales) | **2** | **0** |
| Histogramme décimales | 0: 72 815 · 1: 12 694 · 2: 24 875 · ≥3: **0** | 0: 474 |
| Σ débits | 25 868 433 483,84 | 77 605 300 452 |
| Σ crédits | 25 865 560 250 | 77 596 680 798 |
| Capacité `Numeric(18,2)` (16 chiffres avant virgule) | **OK** | **OK** |

### 4.3 Agrégats et risque de dépassement

- Totaux de balance observés ~10¹⁰–10¹¹ ≪ 10¹⁶.
- Même agrégation multi-périodes ou multi-banques (ordre 10²–10³ campagnes) resterait largement sous la capacité pour des montants MRU de bilan.
- Risque de dépassement **faible** pour stockage des soldes importés et totaux de campagne.

### 4.4 Python `Decimal` / PostgreSQL / Excel

| Sujet | Constat |
|-------|---------|
| PostgreSQL `Numeric(18,2)` | Exact ; compatible SQLAlchemy `Numeric(18, 2)` + `Decimal` (convention déjà massivement utilisée : réclamations, MG, etc.) |
| Calculs Python | Utiliser `Decimal` de bout en bout ; `getcontext().prec` élevé pour intermédiaires ; **quantize** à 2 décimales **à la persistance / export réglementaire**, pas trop tôt |
| Résultats intermédiaires (ratios, proration) | Peuvent exiger **plus de 2 décimales en mémoire** ; ne pas forcer `Numeric(18,2)` sur des tables d’intermédiaires non encore conçues |
| Import Excel | Ne jamais passer par `float` ; `Decimal(str(cell))` ; cellules déjà à 0–2 décimales sur oct. 2026 |
| Export Excel | Format d’affichage fr-FR ≠ valeur stockée ; risque principal = arrondi d’affichage / conversion float côté openpyxl si mal géré |

### 4.5 Hypothèse devises

DET peut contenir des montants multi-devises côté métier ; l’échantillon oct. 2026 ne montre **aucune** précision > 2 décimales sur les colonnes débit/crédit lues. Si un jour le brut devise exige > 2 décimales, différencier colonnes (ex. montant_devise vs montant_mru).

### 4.6 Recommandation (sans modification de modèle maintenant)

1. **Conserver `Numeric(18,2)`** pour les **montants MRU persistés** (imports, cellules état, totaux campagne) — aligné dépôt + preuves BAL.  
2. **Différencier la précision de calcul** : Python `Decimal` haute précision pour intermédiaires du moteur ; quantification à 2 décimales aux frontières stockage / export.  
3. **Ne pas monter** à `(20,4)` etc. sans preuve devises — complexité inutile pour T3 (qui n’a **aucun montant**).  
4. Verrouiller formellement cette règle dans T4 avant tables de soldes.

---

## 5. Vérification de faisabilité technique (conventions dépôt)

Inspection code uniquement — **aucune migration lancée**.

### 5.1 Backend

| Point | Constat |
|-------|---------|
| `router.py` | Pattern établi : `include_router(..., dependencies=[Depends(require_module_access("…"))])` (ex. `reclamations`, `clientele`). T3 : même pattern pour `reporting-bcm-sm`. |
| Modèles | Nouveaux modules isolés (`models/reclamations.py`, etc.) + mixins timestamps ; préfixe tables métier. Faisable : `models/reporting_bcm_sm.py`, tables `rbcm_*`. |
| `deps.py` | `require_module_access(module_code)` exige session **Login 2** (`SESSION_KIND_MODULE`) ; `require_permission(*codes)` via `load_user_permission_codes`. |
| Permissions | Seed dans `FUNCTIONAL_PERMISSIONS` + `ROLE_PERMISSIONS` dans `plateforme_catalogue.py` (convention `{module}.{action}`). |
| `record_audit` | `backend/app/services/audit_helpers.py` — action/entity/entity_id + request_id via session ; à appeler sur POST campagne. |
| Erreurs | Convention `api_errors` / `auth_http_error` (codes `MODULE_AUTH_REQUIRED`, `PERMISSION_DENIED`) — plan T3 aligné. |

### 5.2 Catalogue et navigation

| Point | Constat |
|-------|---------|
| Catalogue | `PLATEFORME_MODULES` + perms ; espace `comptabilite` déjà `DEFAULT_ESPACE_CODE`. Module `reporting-bcm-sm` **absent** aujourd’hui (attendu). |
| Hub | Modules d’espace exposés via API plateforme ; carte hub dépend statut catalogue (`actif` / `bientot`). |
| Contrat front | `module-routing.contract.ts` : nouveaux modules = **prefixed** ; `MODULES_WITH_METIER_SHELL` doit inclure le code sinon Login 2 reste en « shell pending ». |
| BCM Clientèle | Permissions `clientele.bcm.*` séparées — ne pas réutiliser. |

### 5.3 Frontend

| Point | Constat |
|-------|---------|
| Routes | `app.routes.ts` : `path: 'reclamations'`, `canActivate: [authGuard, moduleGuard('reclamations')]` — modèle à suivre. |
| Nav | `shell-nav.ts` : map par `moduleCode` + `navForModule`. |
| Standalone | Composants standalone Angular 20 — convention existante. |
| Feedback | `FeedbackService` / `UiDialogService` / `unsavedChangesGuard` (AGENTS.md + C14). |
| Core Admin | Login 1 ≠ Login 2 ; déconnexion module → `espacePath` (`/comptabilite`) — C5. |
| `espace-hub.guard` | Segments réservés (legacy root + modules) ; ajouter `reporting-bcm-sm` au contrat pour éviter collision hub. |

### 5.4 Base de données / Alembic

| Point | Constat |
|-------|---------|
| Heads **fichiers** dépôt | **1 head** : `20261105_mg_stock_mvt_ref_uq` ← `20261102_mg_stock_periodes_02` (103 révisions) |
| `alembic current` DB dev | **Non exécuté** dans cette mission (pas d’intervention DB) — reste un prérequis **avant upgrade** |
| Stratégie | Migration additive sous `backend/alembic/versions/` uniquement ; `retour_arriere` documenté ; **jamais** sur prod `v1.0.0` sans procédure séparée |
| Unicité campagne | Dépend **P2** ; plan propose UNIQUE + contrôle service + 409 métier |
| Concurrence | Pattern dépôt déjà vu (contrainte UNIQUE + verrou applicatif, ex. stock mouvements) — applicable T3 |

### 5.5 Verdict faisabilité

Le socle T3 est **techniquement réalisable** dans les conventions actuelles. Aucun obstacle d’architecture (auth, catalogue, Angular prefixed, Alembic mono-head fichiers). Les seuls freins sont **produit (P1/P2)** et **contrôle `current` avant upgrade**.

---

## 6. Revue des critères d’acceptation T3 (C1–C15)

| # | Testable en T3 ? | Test concret | Résultat attendu | Dépendances | Preuve |
|---|------------------|--------------|------------------|-------------|--------|
| C1 | Oui | GET module catalogue / admin | Module `reporting-bcm-sm`, espace `comptabilite`, `entry_path` | P1 figé | JSON / UI admin |
| C2 | Oui | Connexion user habilité → `/comptabilite` | Carte visible | Catalogue `actif` + grant | Capture / checklist UI |
| C3 | Oui | Accès URL métier sans Login 2 | Redirect `/modules/reporting-bcm-sm/acces` | Contrat + moduleGuard | Navigation |
| C4 | Oui | Naviguer accueil / campagnes / nouvelle / détail | Routes OK | Contrat + `app.routes` | Navigation |
| C5 | Oui | Déconnexion module | → `/comptabilite`, pas Login 1 | `espacePath` | Navigation |
| C6 | Oui | GET `/api/v1/reporting-bcm-sm/campaigns` + token module | 200 + liste | API + perm `.view` | HTTP |
| C7 | Oui* | POST campagne | 201 `BROUILLON` + audit | **P2** + perm `.prepare` | HTTP + `audit_logs` |
| C8 | Oui* | 2ᵉ POST même période ouverte | Erreur métier structurée (ex. 409) | **P2** | HTTP |
| C9 | Oui | User sans `.view` / `.prepare` | 403 | Catalogue perms | HTTP |
| C10 | Oui | Token Login 1 seul / sans session module | 401/403 | `require_module_access` | HTTP |
| C11 | Oui | Revue PR | Aucun import/mapping/moteur/Excel | Discipline lot | Diff |
| C12 | Oui | Revue PR | Pas de touche Clientèle BCM / amortissement_engine / MFA | Discipline | Diff |
| C13 | Oui | Revue PR | Migration sous `backend/alembic/versions/` | — | Diff |
| C14 | Oui | Actions UI (création) | FeedbackService, pas `alert` | Front | Revue + éventuel test e2e |
| C15 | Oui | CI / pytest ciblés | Vert | Env test | CI |

\*C7/C8 : réalisables en T3 **si** P2 tranché (ou règle provisoire explicitement acceptée).

### Points de vigilance demandés

| Exigence | Couverture T3 |
|----------|----------------|
| User autorisé accède | C1–C4, C6 |
| User non autorisé bloqué | C9–C10 |
| Perms back/front cohérentes | Catalogue + guards nav + `require_permission` |
| Pas 2 campagnes même période (règle retenue) | C8 + tests concurrence — **dépend P2** |
| Actions sensibles auditées | C7 + § audit |
| API directe protégée | C9–C10 |
| Transitions statut contrôlées | **Partiel T3** (statuts initiaux) ; workflow 3 niveaux = hors T3 |
| Erreurs remontées UI | C14 + `api_errors` |

### Hors T3 (étapes ultérieures)

Imports DET/COND, rapprochement, mapping, paramètres, moteur, Excel, workflow complet, PDF, contrôles D01–D22, non-régression septembre.

---

## 7. Périmètre T3-A — Socle indépendant des arbitrages métier ouverts

Implémentable **sans** D15/D01/D02/… et **sans** activer de règle métier réglementaire :

1. Confirmation écrite **P1** = `reporting-bcm-sm` (sinon rester en doc).  
2. Entrée catalogue (`espace_code=comptabilite`, `entry_path`, statut adapté).  
3. Permissions initiales (`view`, `prepare` + réservation des codes futurs sans UI).  
4. Rôle(s) de recette rattachement `view`/`prepare` (décision produit minimale).  
5. Contrat Angular : `MODULE_ROUTE_CONTRACTS`, `MODULES_WITH_METIER_SHELL`, segment hub.  
6. Routes `app.routes.ts` + `moduleGuard` + nav shell (accueil, campagnes placeholders).  
7. Page d’accueil module (sans moteur).  
8. Router API + endpoints lecture/création **si** règle unicité provisoire documentée **ou** après P2.  
9. Audit hooks sur actions sensibles livrées.  
10. Tests auth/perms/guards + C11–C14.  
11. **Pas** d’imports, mapping, params, Excel, PDF.

**Migration campagne :** soit différée en fin de T3-A après P2, soit livrée avec la règle provisoire du plan T3 **explicitement acceptée** comme hypothèse de travail.

---

## 8. Périmètre T3-B — Éléments conditionnels (ne pas développer avant validation)

| Élément | Décision requise |
|---------|------------------|
| Contrainte UNIQUE définitive + C8 « période ouverte » | **P2** |
| Réouverture / `campaign_version` / `reopened_from_id` comportement métier | **P2** |
| Exécution `alembic upgrade` sur DB dev/test | **ALEMBIC** (`current` vérifié) |
| Tout montant / colonne Numeric | T4 + reco §4 (pas T3) |
| Imports DET/COND, SHA, idempotence | T4 + DSI-SRV recommandé |
| Paramètres, listes, mapping actif | D04/D05/D01 |
| Moteur / soldes D/C | **D15** (+ D02 pour ECART) |
| Livrables réglementaires / PDF / septembre | E / DSI |

---

## 9. Risques et dépendances

| Risque | Niveau | Mitigation |
|--------|--------|------------|
| Coder campagne sans P2 | Élevé | T3-A sans UNIQUE métier, ou accepter hypothèse plan T3 par écrit |
| Seed module sous mauvais code (P1) | Élevé | Confirmation Produit avant merge catalogue |
| Drift Alembic DB vs fichiers | Moyen | `heads`/`current` sur **dev** avant upgrade ; fichiers déjà mono-head |
| Scope creep (imports/moteur dans T3) | Élevé | Gate C11 ; revue PR |
| Confusion BCM Clientèle | Moyen | Codes/perms/docs séparés |
| Feu vert calendaire sans P1/P2 | Élevé | Option 2 ci-dessous |

---

## 10. Recommandation finale

### OPTION 2 — T3 PEUT DÉMARRER PARTIELLEMENT

**Peut démarrer immédiatement (T3-A)** après validation explicite utilisateur :

- Catalogue, permissions, Login 2, hub Comptabilité, contrat de routes, shell, page d’accueil, navigation, garde-fous C11–C14, tests auth/perms.

**Mettre en attente (T3-B) jusqu’à arbitrage :**

- Schéma / API création campagne avec unicité métier définitive → **P2**  
- Exécution migration sur DB → contrôle **ALEMBIC current**  
- Confirmation nominale **P1** avant seed durable (le code `reporting-bcm-sm` est l’hypothèse de travail T2)

**Ne pas démarrer :** imports, rapprochements, paramètres, mapping, moteur, Excel, PDF, activation D01/D02.

**Numeric(18,2) :** conserver pour montants MRU futurs ; différencier précision des calculs intermédiaires Python ; **aucune** modification de modèle dans cette mission.

---

## 11. Interdictions respectées

- Aucun code backend/frontend applicatif  
- Aucune migration exécutée  
- Aucune modification DB / config / déploiement / production  
- Aucune activation de règle métier non approuvée  
- Documents historiques T2/T3 **non remplacés** (ce fichier est un livrable additionnel)

**Prochaine étape :** attendre validation explicite de l’utilisateur avant toute implémentation T3.

---

## Annexe A — Contenu intégral `T2_FINAL_VALIDATION.md`

```markdown
# T2 — Validation finale

**Module :** Reporting BCM SM (Comptabilité) — distinct du BCM Clientèle  
**Date :** 16/11/2026  
**Branche de travail :** `chore/audit-nettoyage-pre-deploiement`  
**Commit de départ :** `091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32`  
**Working tree initial :** propre  

## Documents consultés

- Rapport T0 (audit dépôt, accepté)
- Rapport T1 (consolidation métier, accepté)
- Brief T2 + corrections A–I (finalisation)
- Code réel : `backend/app/models/` (mixins, `Numeric(18,2)` immo, `clientele_declarations_bcm`, `ged_documents`, imports `fichier_sha256`), `api/deps.py`, `plateforme_catalogue.py`, `module-routing.contract.ts`, `FeedbackService`
- Fichiers métier oct. 2026 (BAL DET/COND, canevas, Correspondance, Maquette) — analyses T1

## Corrections intégrées dans le dossier T2 révisé

| Point | Correction |
|-------|------------|
| **A. Soldes** | D/C/SD/SC/solde signé distingués ; pas de généralisation `MAX(...)` ; bases **configurables** par règle ; D15 ouverte |
| **B. Décisions** | `rbcm_cell_decision` strictement append-only ; `supersedes_decision_id` ; pas de `superseded_at` mutatif |
| **C. ECART** | Calculé **par campagne** ; 2 873 223 / 2 873 218 = références historiques, **pas** constantes codées ; inactif sans D02 |
| **D. Excel** | Moteur Python = vérité ; openpyxl écrit cellules saisie seulement ; pas de recalcul formules ; pas de PDF natif sans DSI |
| **E. Workflow** | Préparateur / Contrôleur / Approbateur ; anti auto-approbation ; Login 2 + permissions CORE uniquement |
| **F. Données** | Un seul champ de cycle de vie mapping (`lifecycle_status`) ; campagnes versionnées à la réouverture ; `Numeric(18,2)` aligné immo (justifié) ; FK `RESTRICT` sur historiques ; SHA-256 + idempotence |
| **G. Imports** | Période/type/empreinte/version ; streaming DET ; rapprochements persistés ; import validé non écrasé |
| **H. Mapping** | 115 × `A_VALIDER` ; 67 ≠ zéro auto ; 3 sources + divergences D01 visibles |
| **I. Paramètres** | 8 codes ; pas de reconduction ; historique + justification |

## Points validés (conception)

- Intégration native BEA DIGITAL, code module `reporting-bcm-sm`, espace `comptabilite`
- Préfixe tables `rbcm_`, API `/api/v1/reporting-bcm-sm/`, UI `/reporting-bcm-sm/...`
- Réutilisation CORE (auth, Login 2, MFA existant, audit, GED) — aucun parallèle
- Distinction explicite BCM Clientèle
- Socle T3 limité (catalogue, hub, campagnes, perms, audit) clairement séparé des phases imports/moteur

## Points non résolus (voir T2_OPEN_DECISIONS.md)

- D01, D02, D04, D05, D09, D15 (et suite) — métier / Conformité / DSI
- LibreOffice / PDF — DSI
- Alignement `alembic current` vs head dépôt sur la DB de **développement** — à vérifier avant 1ʳᵉ migration T3 (`revision: str =` dans les fichiers ; tip probable `20261105_mg_stock_mvt_ref_uq`)
- Matrice compte×cellule Excel Claude encore absente

## Risques résiduels

| Risque | Niveau | Mitigation |
|--------|--------|------------|
| Activer mapping avant arbitrage D01 | Élevé | Statut forcé `A_VALIDER` ; gate workflow |
| ECART codé en dur | Élevé | Stockage run/campagne calculé ; refs historiques documentées seulement |
| Confusion BCM Clientèle | Moyen | Docs + codes perms séparés |
| Stockage `release-source` en prod | Moyen | T3 n’écrit pas encore de gros volumes ; migration `/srv` avant T4 massif |
| Multi-heads Alembic non vérifié sur DB | Moyen | Contrôle `alembic heads` / `current` avant migration |

## Tests exécutés dans cette mission

Aucun test applicatif lancé (mission documentaire).  
Contrôles réalisés : lecture conventions code, inventaire docs, cohérence interne dossier T2 révisé.

## Décision

# T2 VALIDÉ (conception)

Le dossier T2 révisé est **cohérent** avec le code réel BEA DIGITAL et les décisions métier confirmées pour la conception.

**T3 est prêt à démarrer** après **validation explicite** de l’utilisateur.  
Cette mission **ne commence pas** l’implémentation T3 (pas de modification `backend/` / `frontend/` applicatifs).

Si des amendements métier contredisent les points A–I, repasser T2 en `NON VALIDÉ` avant code.
```

## Annexe B — Contenu intégral `T2_OPEN_DECISIONS.md`

```markdown
# T2 — Décisions ouvertes

Reporting BCM SM (Comptabilité). Ne pas confondre avec BCM Clientèle.

Légende échéance : **B-T3** bloquant avant code T3 · **B-T4** avant imports/moteur · **B-PROD** avant mise en production · **FUTUR** amélioration.

| ID | Sujet | Responsable | Impact | Échéance | Bloque |
|----|-------|-------------|--------|----------|--------|
| P1 | Confirmer code module `reporting-bcm-sm` (vs `reporting-compta`) | Produit / Comptabilité | Catalogue, routes, perms | **B-T3** | Oui T3 |
| P2 | Une campagne active / période **ou** versions à chaque réouverture | Comptabilité / Archi | Unicité `rbcm_campaign` | **B-T3** | Oui schéma T3 minimal |
| D15 | Nature TOTDEB/TOTCRE (soldes individuels vs mouvements) | DSI / Comptabilité | Toutes règles D/C | **B-T4** | Moteur |
| D01 | Arbitrages mapping (202300/202400, 218000, 402, 913*, 580/585, 590/590200, 426, 122000) | Comptabilité | 115 règles | **B-PROD** (T6) | Activation mapping |
| D02 | Formaliser ECART / « selon le solde » | Comptabilité | COD / D38 | **B-PROD** | Activation ECART |
| D04 | Sources des 8 paramètres | Comptabilité / DSI | Params | **B-T4+** | Cellules mixtes |
| D05 | Listes publics / projets | Comptabilité | 322/323/403 | **B-T4+** | Idem |
| D06 | Traitement des 67 rubriques sans règle | Comptabilité | Finalisation | **B-PROD** | Gate BCM |
| D08 | Provisions 290000 / 356000 | Comptabilité | 131 / ratios | **B-PROD** | |
| D09 | Fichier crédits / dépôts | Comptabilité / DSI | ETAT B/C | **B-PROD** non forfaitaire | B/C réels |
| D10–D14 | Canevas / double comptage / FPN / circuit dépôt BCM | Conformité / DSI | Livrable | **B-PROD** | |
| D16–D17 | Résidence / correspondants | Comptabilité / Conformité | Colonnes SM | **B-PROD** | |
| D18–D22 | Liquidité, zéro, maturité, contrôles, conflit mapping | Conformité / Comptabilité | Ratios / contrôles | **B-PROD** | |
| REF-223 | Écart classes 1–8 oct. = 2 873 223 (COND) | Comptabilité | ECART période | Documenté T1 | Réf. historique |
| REF-218 | 2 873 218 non prouvé | Comptabilité | Clarifier | **FUTUR** / ticket | Non bloquant conception |
| DSI-LO | LibreOffice headless pour recalcul Excel | DSI | Formules classeur | **FUTUR** | Pas V1 |
| DSI-PDF | Conversion PDF approuvée | DSI | Livrable PDF | **FUTUR** | Pas V1 |
| DSI-SRV | Migration stockage hors `release-source` → `/srv` | DSI / Exploit | Fichiers | **B-T4** recommandé | Avant volumes SM |
| MATRICE | `Matrice_SM_cellule_regle_source.xlsx` | Claude / Comptabilité | 115 règles compte×cellule | **B-T6** | Précision mapping |
| SEPT | BAL + SM septembre | Comptabilité | Non-régression | **B-PROD** | Recette |
| ALEMBIC | `alembic heads` / `current` sur DB **dev** | Dev | 1ʳᵉ migration | **B-T3** exécution | Avant `upgrade` |

## Hypothèses de conception (non validées métier)

- `Numeric(18, 2)` pour montants MRU (aligné immobilisations) — **à confirmer** si devises exigent plus de décimales en stockage brut DET.
- SD/SC « métier » définis **par règle** (pas `MAX` global) — valeurs exactes après D15.
- Réouverture = nouvelle `campaign_version` liée à `reopened_from_id` — **P2**.

Ces hypothèses ne doivent pas être présentées comme décisions métier validées.
```

## Annexe C — Contenu intégral `T3_IMPLEMENTATION_PLAN.md`

```markdown
# T3 — Plan d’implémentation (socle)

**Prérequis :** T2 VALIDÉ + validation explicite utilisateur pour démarrer le code.  
**Cette mission ne code pas T3.**

## 1. Périmètre exact

### Inclus

1. Enregistrement module `reporting-bcm-sm` dans le catalogue (`espace_code=comptabilite`)
2. Carte / accès depuis hub `/comptabilite`
3. Contrat de routes Angular préfixées `/reporting-bcm-sm/...`
4. Navigation shell module
5. Permissions granulaires initiales + Login 2
6. Page d’accueil module
7. Liste / création / consultation campagnes (statuts initiaux)
8. API consultation + création campagnes
9. Audit des actions sensibles (création campagne, changements statut initiaux)
10. Tests associés
11. Migration Alembic **additive** tables campagne minimales (si validée dans le lot T3)

### Exclus (phases suivantes)

- Imports DET/COND, rapprochement, mapping, paramètres, moteur, Excel, workflow 3 niveaux complet, PDF

## 2. Architecture

| Couche | Cible |
|--------|--------|
| Module | `reporting-bcm-sm` |
| Hub | `/comptabilite` |
| UI | `/reporting-bcm-sm/accueil`, `/campagnes`, `/campagnes/:id` |
| API | `/api/v1/reporting-bcm-sm/campaigns` |
| Tables T3 mini | `rbcm_campaign` (+ éventuellement `rbcm_validation_event` si transitions) |
| Auth | `require_module_access("reporting-bcm-sm")` + `require_permission(...)` |

Ne pas coder dans `app/` ou `alembic/` racine.

## 3. Fichiers concernés (prévision)

### Backend

- `backend/app/data/plateforme_catalogue.py` — module + permissions
- `backend/app/models/reporting_bcm_sm.py` — modèle campagne
- `backend/app/schemas/reporting_bcm_sm.py`
- `backend/app/services/reporting_bcm_sm/campaign_service.py`
- `backend/app/api/v1/endpoints/reporting_bcm_sm.py`
- `backend/app/api/v1/router.py` — include_router
- `backend/alembic/versions/YYYYMMDD_rbcm_01_campaigns.py` — après contrôle heads
- `backend/tests/test_reporting_bcm_sm_campaigns.py` (nom à aligner)

### Frontend

- `frontend/angular20/src/app/plateforme/module-routing.contract.ts`
- `frontend/angular20/src/app/app.routes.ts`
- `frontend/angular20/src/app/layout/shell/shell-nav.ts`
- `frontend/angular20/src/app/plateforme/espace-hub.guard.ts` — segment réservé
- `frontend/angular20/src/app/reporting-bcm-sm/` — pages accueil, liste, détail, création
- Consommation catalogue via API plateforme existante (`/plateforme/modules/...`)

### Docs

- Mettre à jour ce dossier + éventuellement `docs/catalogue-modules-futurs.md` / index compta

## 4. Modèle campagne (T3 minimal)

Champs proposés (alignés T2 révisé) :

- `id` UUID PK  
- `period_year`, `period_month`  
- `closing_date` nullable  
- `bank_code` défaut `BEA`  
- `status` : au minimum `BROUILLON` (autres transitions limitées en T3)  
- `campaign_version` INT défaut 1  
- `reopened_from_id` UUID nullable FK self  
- `preparer_id` UUID FK users nullable  
- `created_at` / `updated_at`  

**Unicité proposée (sous réserve P2) :**  
`UNIQUE (bank_code, period_year, period_month, campaign_version)`  
avec règle métier : une seule version « ouverte » (non `CLOTUREE`) par période — à coder en service.

Montants : aucun en T3.  
FK users : `ON DELETE RESTRICT` ou SET NULL selon convention users du dépôt (vérifier avant migration).

## 5. API T3

| Méthode | Chemin | Permission | Comportement |
|---------|--------|------------|--------------|
| GET | `/reporting-bcm-sm/campaigns` | `.view` | Liste filtrée année/mois/statut |
| POST | `/reporting-bcm-sm/campaigns` | `.prepare` | Crée `BROUILLON` ; refuse doublon période ouverte |
| GET | `/reporting-bcm-sm/campaigns/{id}` | `.view` | Détail |
| PATCH | `/reporting-bcm-sm/campaigns/{id}` | `.prepare` | Champs non sensibles seulement (ex. closing_date) |

Erreurs : `api_errors`. Audit : `record_audit` sur POST et transitions.

## 6. Permissions initiales (catalogue)

Proposer au seed catalogue (noms exacts à figer en PR) :

- `reporting-bcm-sm.view`
- `reporting-bcm-sm.prepare`
- (réserver sans UI T3) `import`, `parameters.write`, `mapping.propose`, `mapping.validate`, `confirm`, `correct`, `control`, `approve`, `export`, `reopen`

Rattacher au moins `view` + `prepare` à un rôle Comptabilité de recette (décision produit).

## 7. Routes Angular T3

- `path: 'reporting-bcm-sm'`, `canActivate: [moduleGuard('reporting-bcm-sm')]`, children :
  - `''` → redirect `accueil`
  - `accueil`
  - `campagnes`
  - `campagnes/nouvelle`
  - `campagnes/:id`
- `entryPath`: `/reporting-bcm-sm/accueil`
- `espacePath`: `/comptabilite`
- FeedbackService / UiDialogService / unsavedChangesGuard / montant si formulaires

## 8. Tests T3

- API : auth module absente → 401/403 ; create OK ; doublon période → 409 métier  
- Permission `.prepare` requise pour POST  
- Audit écrit sur création  
- Front : garde module ; hub Comptabilité affiche la carte si catalogue actif  
- Migration : upgrade sur copie `bea_digital_test` uniquement (quand exécuté)

## 9. Critères d’acceptation

Voir [T3_ACCEPTANCE_CRITERIA.md](T3_ACCEPTANCE_CRITERIA.md).

## 10. Procédure de retour arrière (développement)

1. Revert commits de la branche feature T3  
2. Si migration appliquée sur **DB test uniquement** : `alembic downgrade` si `retour_arriere=compatible`, sinon restore dump test  
3. Ne jamais appliquer ni downgrader sur la prod `v1.0.0`  
4. Retirer module catalogue / grants de recette si seedés

## 11. Contrôles avant 1ʳᵉ migration

```text
# Sur environnement DEV uniquement
alembic -c backend/alembic.ini heads
alembic -c backend/alembic.ini current
# Une seule head attendue ; current aligné ou plan de merge documenté
```

Tip fichiers actuel (lecture) : `20261105_mg_stock_mvt_ref_uq` ← `20261102_mg_stock_periodes_02`.  
**À confirmer sur la base de développement réelle** avant génération de `rbcm_01`.
```

## Annexe D — Contenu intégral `T3_ACCEPTANCE_CRITERIA.md`

```markdown
# T3 — Critères d’acceptation

Module `reporting-bcm-sm` — socle uniquement.

## 1. Critères vérifiables

| # | Critère | Preuve |
|---|---------|--------|
| C1 | Module présent au catalogue, `espace_code=comptabilite`, `entry_path` renseigné | API `/plateforme/modules/reporting-bcm-sm` ou admin catalogue |
| C2 | Carte visible sur hub `/comptabilite` pour utilisateur habilité | UI |
| C3 | Login 2 module obligatoire avant écrans métier | Redirection `/modules/reporting-bcm-sm/acces` |
| C4 | Routes `/reporting-bcm-sm/accueil`, `/campagnes`, création, détail | Navigation |
| C5 | Déconnexion module → `/comptabilite` (jamais Login 1) | Contrat routes |
| C6 | `GET /api/v1/reporting-bcm-sm/campaigns` liste | HTTP 200 + corps |
| C7 | `POST .../campaigns` crée `BROUILLON` | HTTP 201 + audit |
| C8 | Doublon période ouverte refusé | Erreur métier structurée |
| C9 | Sans permission `.view` / `.prepare` → refus | 403 |
| C10 | Sans session module → refus | 401/403 |
| C11 | Aucun import DET/COND / mapping / moteur / Excel dans le lot | Revue PR |
| C12 | Aucune touche BCM Clientèle / amortissement_engine / MFA | Diff |
| C13 | Migration uniquement sous `backend/alembic/versions/` | Diff |
| C14 | Feedback UI via FeedbackService (pas `alert`) | Revue front |
| C15 | Working tree / CI verte sur tests ajoutés | CI / pytest |

## 2. Tests fonctionnels

- Créer campagne octobre 2026 → visible en liste  
- Ouvrir détail → statut `BROUILLON`, période correcte  
- Tentative 2ᵉ campagne même période/version ouverte → échec  
- Utilisateur Lecteur : voit liste, ne crée pas  

## 3. Tests de sécurité / permissions

- Token plateforme seul (Login 1) sans Login 2 module → pas d’accès API métier  
- Permission `view` sans `prepare` → GET OK, POST KO  
- Pas d’endpoint T3 qui bypasse `require_permission`  

## 4. Tests de concurrence

- Deux POST simultanés même période : au plus une campagne créée (contrainte UNIQUE + gestion erreur)  
- Pas de corruption de ligne (pas de partial update hors transaction)  

## 5. Tests d’audit

- Création campagne → entrée `audit_logs` (action, entity, user, request_id)  
- Pas de secret / contenu fichier dans l’audit  

## 6. Validation finale T3

T3 accepté si **C1–C15** OK et aucun critère hors périmètre livré par erreur.

**Ensuite seulement :** ouverture T4 (imports) sur validation produit séparée.
```
