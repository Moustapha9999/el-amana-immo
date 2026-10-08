# Roadmap — Indicateurs communs, Reporting interne, Déclaration BCM

Date : 08/10/2026. Base réelle **non migrée**. Copie de test : `bea_digital_clientele_test`.

**Clé métier inchangée** : `racine_client` = CLIENT ORION = 6 chiffres texte (`000001`).
Comptage clients = `COUNT(DISTINCT racine_client)`. Comptage comptes = `COUNT(compte)` / `COUNT(rib)`.

---

## 1. Verdict : ce que vous pouvez prendre tel quel

Les phases **déjà livrées** (0 → 6 dans le dépôt) **ne se refont pas**. Elles sont le socle.

| # dépôt | Sujet | État | Action |
|---------|--------|------|--------|
| 0 | Audit | Fait | Prendre |
| 1 | Base CLIENT / COMPTE / RIB | Fait (`clientele_01`) | Prendre |
| 2 | Import ORION | Fait (`clientele_02`) | Prendre |
| 3 | Situation PP / PM (vue, pas une copie) | Fait | Prendre |
| 4 | Rapprochement d’imports (snapshots) | Fait (`clientele_03`) | Prendre |
| 5 | Classification configurable + historique | Fait | Prendre |
| 6 | Filtrage & alertes | Fait | Prendre |
| 7 | Moteur d’indicateurs + reporting | Fait | Prendre |
| 9 | EER branché sur la racine ORION | Fait | Prendre |
| 10 | Déclaration BCM | Fait (`clientele_04`) | Prendre |
| — | Module EER existant | Fait | Branché, non réécrit |

**Ne pas exécuter** les anciens prompts « Phase 7 reporting interne (28 rapports isolés) » ni « Phase 8 reporting BCM PDF ». Ils produiraient deux calculs divergents.

---

## 2. Ce qui change (obligatoire)

| # | Changement | Pourquoi |
|---|------------|----------|
| 1 | **Moteur d’indicateurs commun** avant tout écran de rapport | Reporting interne et Déclaration BCM doivent afficher le **même** chiffre |
| 2 | Reporting interne = **analyse / pilotage** (périodes libres) | Plus un sac de 28 requêtes indépendantes |
| 3 | BCM = **Déclaration mensuelle officielle** (pas un export) | Préparation + contrôle + drill-down + snapshot |
| 4 | **EER avant BCM** (intégration racine) | Tableau 1 « mis à jour ce mois » = EER de la période |
| 5 | Classification **à une date** (`historique`) | BCM juin ≠ classification d’octobre |
| 6 | Semaine / année = **simulation**, jamais « déclaration BCM » | Officiel = mensuel seulement |
| 7 | Champs sans définition = **À CONFIGURER**, pas de chiffre silencieux | Tableau 2 ligne 4, Tableau 3 entier, mapping INTERDIT, Actif/inactif |

**Inchangé** : Auth, RBAC, GED, agences, VNC immo, URLs `/api/v1/...`, routes `/clientele/...`, pas de 2ᵉ base, tests sur copie uniquement.

---

## 3. Ordre d’exécution désormais

```text
0–6    FAIT (référentiel + import + situation + historique + classif + alertes)
   ↓
7      Moteur d'indicateurs commun          ← FAIT
   ↓
8      Reporting interne (écran KPI)        ← FAIT (enrichissements PDF plus tard)
   ↓
9      EER branché sur la racine            ← FAIT (lookup 6 chiffres, préremplissage ORION, pas d'écrasement)
   ↓
10     Déclaration BCM (mensuelle, snapshot)  ← FAIT
   ↓
11     Dashboard Conformité consolidé
   ↓
12     Sécurité / RLS / perf / index
   ↓
13     Tests finaux puis production (backup → Alembic copie → jamais tester en prod)
```

Dashboard global (ancien « phase 10 ») **après** BCM : les KPI cliquables réutilisent le même moteur.

---

## 4. État réel du code vs besoins BCM

### Déjà utilisable

| Besoin BCM | Déjà en base |
|------------|----------------|
| Stock clients à une date d’import | `premiere_extraction` / `date_extraction` ; pas de suppression |
| PP / PM (heuristique) | Vue `clientele_situation.profil_derive` (PP / PM / NON_IDENTIFIE) |
| Risque actuel | `clientele_classifications` |
| Risque à une date | `clientele_classif_historique.created_at` + `nouvelle_classe` |
| Comptes / RIB / agence / OUVERT-FERME | `clientele_comptes` |
| Comparaison M / M-1 | Snapshots `clientele_import_*` + rapprochements |
| Alertes | `clientele_alertes` + événements |
| EER du mois | `eer_dossiers.date_eer`, `valide_le`, `statut`, `racine_client` (nullable, 40 car., **sans FK**) |

### Trous (ne pas inventer)

| Trous | Impact BCM | Décision demandée à la Conformité |
|-------|------------|-----------------------------------|
| **Actif / inactif** : ORION ne le porte pas ; Situation = `OUVERT`/`CLOTURE` comptes | Tableau 1 « cible » (« clients **actifs** ») | Source métier, ou confirmer que « actifs + inactifs » = **tout le stock** |
| **Construction juridique** : 0 dans le fichier août 2026 | Colonne Tableau 1 | Liste de `categorie_juridique` / `type_client` à mapper (référentiel, pas du code) |
| **INTERDIT** (moteur interne) vs 3 niveaux BCM | Tableau 1B / 4 | Compter avec ÉLEVÉ ? Exclure ? Ligne hors BCM ? |
| EER « mis à jour » : quel statut ? | Tableau 1 ligne 3 | `VALIDE` ? `CLOTURE` ? `operation_type = MISE_A_JOUR` seulement, ou aussi `ENTREE_RELATION` ? |
| Racine EER `String(40)` sans FK | Jointure fragile | Phase 9 : valider 6 chiffres, lier au référentiel, ne pas fusionner `eer_parties` |
| Fenêtre « 5 ans » | Tableau 1 ligne 4 | Date de début paramétrée (ex. 01/01/N-5), pas un `5` magique |
| Tableau 2 L4 « opérations enregistrées » | Pas de définition | **À CONFIGURER** |
| Tableau 3 (5 lignes) | Pas de définition | **À CONFIGURER** |
| Alertes « déclarées » YTD | Tableau 2 L1 | Quels statuts ? (`CONFIRMEE` ? hors faux positifs ?) |

Proposition **à valider**, pas à coder comme vérité BCM :

> « Nombre à la fin du mois précédent » = clients dont `premiere_extraction <= dernier jour du mois précédent`  
> (`COUNT DISTINCT racine`). Cela équivaut à « tout le stock connu », donc actifs **et** inactifs si ces deux mots signifient « toute la population ».

« Nombre cible = clients actifs du mois » reste **À CONFIGURER** tant que Actif n’a pas de source.

---

## 5. Moteur d’indicateurs commun

Une seule implémentation : `backend/app/data/clientele_indicateurs.py` (catalogue) puis service SQL.

```text
DONNÉES (clients, comptes, classif historique, EER, alertes, snapshots)
        │
        ▼
 MOTEUR D'INDICATEURS  (code + période + filtres → valeur + population paginée)
        │
   ┌────┴────┐
   ▼         ▼
Reporting  Déclaration BCM
interne    (snapshot à la validation)
```

Chaque indicateur expose :

- `code`, libellé, définition métier, formule, source, type de période (`POINT`, `INTERVALLE`, `YTD`, `MOIS`)
- clé (`RACINE` ou `COMPTE`)
- `statut` : `PRET` ou `A_CONFIGURER`
- drill-down : liste paginée côté serveur (jamais 40 000 lignes dans Angular)

Filtres communs : période, agence, PP/PM/CJ, risque, résidence — appliqués **dans** le moteur.

---

## 6. Catalogue Déclaration BCM (modèle août 2026)

Période officielle d’une déclaration : `date_debut = 1er du mois`, `date_fin = dernier jour`, `fin_mois_precedent = date_fin - 1 mois`.

Version moteur figée dans le snapshot.

### Tableau 1A — Forme juridique

| Code | Ligne | Définition fournie | Période | Source | Statut |
|------|--------|-------------------|---------|--------|--------|
| `bcm.t1.stock_m1` | Fin mois précédent | Actifs + inactifs jusqu’au mois précédent | Point au `fin_mois_precedent` | Clientèle | **PRET sous réserve** (stock = connu à cette date) |
| `bcm.t1.cible` | Cible à mettre à jour | Clients **actifs** du mois de déclaration | Mois | Clientèle | **À CONFIGURER** (définition Actif) |
| `bcm.t1.maj_mois` | Mis à jour ce mois | EER du mois | Mois | EER | **PRET sous réserve** (statut EER à valider) |
| `bcm.t1.maj_5ans` | Mis à jour 5 dernières années | Clients actifs depuis 5 ans avant l’année | Paramètre d’année | Clientèle + EER | **À CONFIGURER** (fenêtre + Actif) |

Colonnes : PP, PM, construction juridique, TOTAL. CJ = mapping référentiel (aujourd’hui 0).

### Tableau 1B — Degré de risque

Mêmes 4 lignes, colonnes ÉLEVÉ / MOYEN / FAIBLE / TOTAL.  
Classification = **historique à la date de référence**, pas le niveau courant.  
INTERDIT : mapping **À CONFIGURER**.

### Tableau 2 — Opérations inhabituelles

| Code | Ligne | Définition | Période | Statut |
|------|--------|------------|---------|--------|
| `bcm.t2.extraites` | Extraites du système | Alertes du 01/01 → fin mois déclaration | YTD | **PRET sous réserve** (statuts d’alerte) |
| `bcm.t2.analysees` | Analysées | En cours d’analyse + clôturées + déclarées | À préciser | **PRET sous réserve** (mapping statuts) |
| `bcm.t2.suivi` | Suivi continu | En cours d’analyse + en attente de réponse | À préciser | **PRET sous réserve** |
| `bcm.t2.enregistrees` | Enregistrées | *aucune* | — | **À CONFIGURER** — pas de chiffre |
| `bcm.t2.umef_mois` | Soupçons UMEF | Déclarations **du mois** (pas YTD) | Mois | **À CONFIGURER** (pas d’entité UMEF encore) |

### Tableau 3 — Opérations suspectes

Cinq lignes, **aucune formule**. Toutes **À CONFIGURER**. Pas de module « suspectes du personnel » aujourd’hui.

### Tableau 4 — Classification BC/FT

| Code | Ligne | Définition | Statut |
|------|--------|------------|--------|
| `bcm.t4.eleve` / `moyen` / `faible` | Stock fin **mois de déclaration** | Actifs/inactifs jusqu’au mois inclus | **PRET sous réserve** (même interprétation stock + classif à `date_fin`) |
| `bcm.t4.total` | Total | Somme | Contrôle : E+M+F = total |
| ratio | % | `categorie / total × 100`, 2 décimales | Calculé |

Contrôle documenté (août 2026) : `t4.total - t1.stock_m1` = 292 = `t1.maj_mois`. À vérifier si la Conformité **valide** cette identité (elle a tenu sur le fichier, ce n’est pas encore une règle figée).

Statuts déclaration : `BROUILLON → CALCULEE → A_CONTROLER → VALIDEE → CLOTUREE → ARCHIVEE`.  
Une `VALIDEE` **ne recalcule plus** : snapshot JSON des cellules + ids de population.

Export : Excel / PDF de **préparation**. Pas de format d’import plateforme BCM tant qu’il n’est pas fourni.

---

## 7. Reporting interne (révisé)

Consomme **uniquement** le moteur. Périodes : aujourd’hui, 7/10/30 j, mois courant / précédent, 3/6 mois, année, personnalisée.

Familles (drill-down paginé, export Excel/PDF) :

1. Clients (stock, PP, PM, CJ, nouveaux = `premiere_extraction` dans la période)
2. Comptes (ouverts / fermés, par agence)
3. Classification (FAIBLE / MOYEN / ELEVE / INTERDIT + transitions d’historique)
4. EER (quand phase 9 branchée)
5. Alertes / opérations
6. Anomalies d’import / rapprochement
7. Comparaisons (réutilise phase 4)

Les 28 « rapports » de l’ancien prompt deviennent des **vues** de ces indicateurs, pas 28 SQL copiés.

---

## 8. Phase 9 — EER sur la base clientèle

EER **existe**. On ne le réécrit pas. On le **branche** :

1. Saisie / recherche racine 6 chiffres → charger `clientele_clients` + comptes
2. Préremplir ; n’afficher que les champs à contrôler / compléter
3. Distinguer sources : ORION / KYC / conformité / manuel / calculé
4. Ne jamais écraser silencieusement une donnée ORION
5. « Client mis à jour » BCM = dossier EER de la période au statut validé par la Conformité

`eer_parties` reste le dossier déclaré KYC. Le référentiel reste le miroir ORION. La comparaison des deux **est** le contrôle.

---

## 9. Phases 11–13

- Index déjà présents sur racine, RIB, compte, agence+état. À compléter : `classif_historique (racine, created_at)`, `alertes (created_at, statut)`, `eer_dossiers (date_eer, statut, racine)` une fois normalisée.
- Pagination / agrégations SQL : règle du moteur. Interdiction de charger 40 k clients au front.
- RLS : rôle applicatif encore **superuser** (phase 0). RLS progressive **sans** casser FastAPI. Tests sur copie.
- Production : dump + `alembic` sur copie, jamais d’essai sur `bea_digital`.

---

## 10. Prochaine implémentation (une seule)

**Phase 9 — EER sur la racine — fait.** Lookup 6 chiffres (`GET /eer/clientele/{racine}`), préremplissage des champs vides (`source=ORION`, à confirmer), pas de FK, pas de fusion `eer_parties`. `MISE_A_JOUR` reste fermé en V1. Tests : `test_eer_clientele_pont.py`.

**Phase 10 — Déclaration BCM — fait.** Une déclaration par mois (`/clientele/declarations`), calcul via le moteur, cellules `A_CONFIGURER` sans chiffre, snapshot JSON à `VALIDEE` (plus de recalcul). Export Excel / PDF de préparation. Tests : `test_clientele_declaration_bcm.py`.

**Ensuite : phase 11 — Dashboard Conformité consolidé** (KPI cliquables, même moteur).

Questions bloquantes pour la Conformité (une page A4) : Actif ; construction juridique ; INTERDIT↔BCM ; statut EER « mis à jour » ; statuts d’alertes Tableau 2 ; UMEF ; Tableau 3 ; identité T4−T1 = EER du mois.
