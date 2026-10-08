# Base clientèle — Phases 4, 5 et 6

Statut (08/10/2026) : migration `20261008_clientele_03` **à n’appliquer que sur**
`bea_digital_clientele_test`. Base réelle `bea_digital` inchangée.

Règle inchangée : CLIENT = racine ORION (6 chiffres). Classification et alertes
portent sur la **racine**, pas sur le RIB.

## Phase 4 — Rapprochement d’imports

Chaque import confirmé est photographié (`clientele_import_clients` /
`clientele_import_comptes`) **avant** purge du staging. Le rapprochement compare
deux photographies, pas le stock vivant.

| Catégorie | Signification |
|-----------|----------------|
| Nouveaux | Présents dans B, absents de A |
| Modifiés | Même racine / même RIB, champ différent (agence, état, devise, catégorie, secteur, …) |
| Inchangés | Comptés en synthèse, non listés ligne à ligne |
| Absents de l’extraction | Présents dans A, absents de B — **ce n’est pas une suppression** |
| Anomalies | Ex. même RIB rattaché à une autre racine |
| Comptes fermés | `OUVERT` → `FERME` dans B (sous-ensemble des modifiés) |

Écran : `/clientele/rapprochements`. Exports Excel (onglets) et PDF (synthèse).

Les imports antérieurs à cette phase n’ont pas de snapshot : les réimporter pour les rapprocher.

## Phase 5 — Classification

Niveaux : `FAIBLE`, `MOYEN`, `ELEVE`, `INTERDIT`. Moteur **configurable**
(critères, poids, opérateurs, priorités, versions, dates d’effet).

La **matrice maître** (Matrice V1 + Scoring V4) est extraite et versionnée
([clientele-moteur-scoring.md](clientele-moteur-scoring.md)). Les poids V4 sont des
**propositions**. Les divergences restent `A_ARBITRER`. Version ACTIVE historique
toujours **sans règle métier validée**.

- Version 1 ACTIVE livrée **sans règle** : `POST /classification/appliquer` refuse tant qu’aucune règle n’est saisie (`clientele.classif.admin`).
- `POST /classification/evaluer` simule SCORE + MAX_NIVEAU **sans écrire** la classe retenue.
- INTERDIT proposé n’est pas auto-appliqué. Donnée absente ≠ Faible. 0 critère → NON CLASSÉ.
- Manuel et Excel contrôlé (modèle : `RACINE_CLIENT`, `NIVEAU`, motifs). La racine n’est **jamais** modifiable.
- Une saisie manuelle n’est pas écrasée par le moteur sans `forcer`.
- Historique complet (ancienne / nouvelle classe, motifs, source, utilisateur, version).

PPE, filtrage confirmé, etc. sont des **critères du catalogue**, sans source ORION tant que le métier n’a pas branché la donnée.

## Phase 6 — Filtrage et alertes

Sources : CLIENT (nom, prénoms, identifiants) + `LISTE_INTERDICTION` ORION + listes internes.

Une correspondance est **potentielle**. Workflow :

`NOUVELLE` → `A_ANALYSER` → `EN_INVESTIGATION` → `CONFIRMEE` | `FAUX_POSITIF` | `REJETEE` → `CLOTUREE`

Commentaire obligatoire pour les décisions. Justificatifs conservés. Un faux positif
est mémorisé (`clientele_filtrage_empreintes`) et **signalé** à une nouvelle occurrence
(nouvelle alerte, pas une confirmation automatique).

## Droits

| Permission | Lecteur | Gestionnaire | Admin |
|------------|---------|--------------|-------|
| `*.view` (rapprochement, classif, filtrage) | oui | oui | oui |
| execute / decide | | oui | oui |
| `classif.admin` (règles / versions) | | | oui |

## Tests

`backend/tests/test_clientele_phase456.py` : 000001×2 + 000002 puis extraction suivante
(nouveau client, compte ajouté, compte fermé, client absent de l’extraction mais
conservé) ; moteur configurable ; Excel ; workflow faux positif.
