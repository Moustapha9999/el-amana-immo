# Base clientèle — Phases 2 et 3 : import ORION et Situation PP / PM

Statut (08/10/2026) : migration `20261008_clientele_02` **à n’appliquer que sur la copie**
`bea_digital_clientele_test`. Base réelle `bea_digital` inchangée.

## Règle inchangée

```text
CLIENT (racine ORION, 6 chiffres)  1 ──── N  COMPTE  ──── RIB
```

Une ligne de l’État Compte = un compte. Comptage clients = `COUNT(DISTINCT racine_client)`
(vue `clientele_situation` ou `COUNT(*)` de `clientele_clients`), jamais `COUNT(*)` sur
l’extraction. L’import **ne supprime jamais** un client déjà en base.

## Phase 2 — Import État des comptes

Workflow : upload → analyse / mapping → contrôles → aperçu → confirmation SQL → rapport.

| Étape | Détail |
|-------|--------|
| Mapping | Auto par synonymes d’en-têtes ; ajustable avant confirmation |
| Contrôles | Racine / compte / RIB, zéros initiaux, doublons, rattachement à un autre client, agence inconnue, colonnes manquantes / supplémentaires, valeurs d’état inconnues |
| Écriture | `INSERT … SELECT` depuis `clientele_import_lignes` (pas de suppression) |
| Historique | `clientele_imports` : fichier, SHA-256, utilisateur, dates, effectifs, créations, mises à jour, rejets, anomalies, statut |
| Staging | Lignes valides purgées après import ; anomalies conservées |

API : `/api/v1/clientele/imports…` (module `clientele`, permissions `clientele.import.*`).
Écran : `/clientele/imports`.

## Phase 3 — Situation PP / PM

**Pas de copie** de la clientèle : vue PostgreSQL `clientele_situation` (CLIENT + COMPTES +
`agences`). PP / PM = filtre sur `profil_derive`.

### Sources des colonnes métier

| Colonne Situation | Source | Commentaire |
|-------------------|--------|-------------|
| CODE AG | ORION | Agence du compte le plus ancien (`min DATOUV`). 12 clients multi-agences dans l’extrait 10/2026 |
| AGENCE_COMPTE | ORION + `agences` | Libellé |
| CLIENT | ORION | Racine, colonne CLIENT, 6 chiffres texte |
| NOM CLIENT | ORION | `RAISON_SOCIAL` |
| date ouv | ORION | `MIN(DATOUV)` |
| statut | **partiel** | `OUVERT` / `CLOTURE` selon les comptes. Actif / inactif du classeur **n’est pas** dans ORION (source future) |
| Profil ORION retraité | **dérivé, pas copié** | Heuristique agent économique puis catégorie juridique (~94 % d’accord avec le classeur). `NON_IDENTIFIE` sinon |
| Profil pointage stagiaire | **absent** | Source future : classeur Situation / classification |
| NIF / NNI | ORION | Identifiant unique selon `TYPE_IDENTIFIANT` |
| Statut résident | ORION | R / N |
| Secteur d’activité | ORION | Souvent vide dans le classeur Situation |
| Catégorie juridique | ORION | |
| Classe risque LBC FT | **absent** | Source future : classification |
| Motif de risque | **absent** | Source future : classification |
| Nationnalité | ORION | |
| Date MAJ | **absent** | `updated_at` est technique |

Recherche : racine, nom, compte, RIB, agence, état, type d’identifiant, profil.
Fiche client : identité, comptes / RIB / agences / états, agrégats, dernier import.

## Module

Code `clientele`, URLs `/clientele/...`, domaine Conformité & sécurité financière.
Rôles `clientele.lecteur` / `clientele.gestionnaire` / `clientele.admin`.
Permissions `clientele.view`, `import.view`, `import.execute`, `export`, `scope.all`, `admin`.
Phases 4–6 : [clientele-phase4.md](clientele-phase4.md).
