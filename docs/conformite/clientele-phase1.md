# Base clientèle — Phase 1 : modèle CLIENT / COMPTE / RIB

Statut (08/10/2026) : migration `20261008_clientele_01` **appliquée uniquement sur la copie**
`bea_digital_clientele_test`. Base réelle `bea_digital` inchangée. Pas encore de module,
d'API ni d'écran (phases 2–3 : [clientele-phase2.md](clientele-phase2.md)).

## Règle

```text
CLIENT (racine ORION, 6 chiffres)  1 ──── N  COMPTE (11 chiffres)  ──── RIB (23 chiffres)
```

Une ligne de l'État Compte ORION = un compte. Toutes les lignes d'une même racine produisent
**un seul** client. Clients = `COUNT(*)` de `clientele_clients` ; comptes = `COUNT(*)` de
`clientele_comptes` ; jamais `COUNT(*)` sur l'extraction pour compter des clients.

## Sources analysées (racine du dépôt, non versionnées : données nominatives)

| Fichier | Contenu | Usage |
|---------|---------|-------|
| `Etat  Compte BEA (003).xlsx` | Extraction ORION, 27 colonnes, 59 903 lignes = 59 903 comptes | **Source de la phase 1** |
| `Copie de Situation des comptes PP et PM (maj 10.2026).xlsx` | Classeur Conformité, 1 ligne par client (47 359), profil retraité, classe de risque LBC-FT | Phase 3 (classification) |
| `Clonnes des 2  Files.xlsx` | Liste des colonnes des deux fichiers | Référence de mapping |
| `Risque LBC FT Client V4-2026.xlsx`, `Matrice des risques LBC FT BEA V1-7-5-25.xlsx` | Scoring et matrice de risque | Phase 3 |

## Constats sur les données réelles (État Compte)

| Constat | Valeur |
|---------|--------|
| Lignes / comptes / RIB distincts | 59 903 / 59 903 / 59 903 |
| Clients distincts (racines) | **42 913** (28 182 mono-compte, max 16 comptes) |
| Identifiants | tous en texte : RIB 23, COMPTE 11, CLIENT 6, agence 5 chiffres |
| RIB = `00007` + guichet + COMPTE + clé | 100 % ; guichet = `CODE_AGENCE_COMPTE` = `agences.code` (16 agences) |
| Racine dans le compte | 100 % : en tête (9 121, ex. `000001` → `00000100001`) **ou** précédée d'un `0` (50 782, ex. `000026` → `00000260007`) |
| Clé RIB invalide | 26 comptes (signalés, non bloquants) |
| Attributs identiques sur tous les comptes d'un client | nom, prénoms, naissance, nationalité, résident, agent économique, situations / catégorie juridiques, secteur, identifiant, RCS, conformité |
| Attributs propres au compte | agence (12 clients multi-agences), NCG, état, devise, liste d'interdiction |
| `RAISON_SOCIAL` | tronqué par ORION à 25 caractères |
| `IDENTIFIANT_LISTE`, `DATE_NAISSANCE` | parfois plusieurs valeurs (`,` ou `/`) : valeur brute conservée, NNI / NIF / date remplis seulement si valeur unique |
| `DATOUV`, `DDC` | numéros de série Excel ; `DDD` : date |

Le classeur « Situation » stocke aussi la racine **en entier** (colonne sans titre, zéros
perdus) : jamais utilisée comme clé.

## Tables

`clientele_clients` : `id` (UUID), `racine_client` **UNIQUE** `^[0-9]{6}$`, `raison_sociale`,
`prenoms`, `date_naissance` (+ `date_naissance_orion` brute), `nationalite`,
`statut_resident` (R/N), `agent_economique`, `situation_juridique`, `categorie_juridique`,
`secteur_activite`, `famille_secteur_activite`, `type_identifiant` (NNI/NIF),
`identifiant_orion`, `nni`, `nif`, `rcs`, `type_client` (codes EER, rempli par la
classification, jamais à l'import), provenance (`source`, `premiere_extraction`,
`date_extraction`), horodatage.

`clientele_comptes` : `id`, `compte` **UNIQUE** `^[0-9]{11}$`, `rib` **UNIQUE** `^[0-9]{23}$`,
CHECK `substr(rib, 11, 11) = compte`, `racine_client` **FK** → `clientele_clients.racine_client`
(RESTRICT en suppression et en modification), `agence_id` FK → `agences` (RESTRICT), `ncg`,
`rubrique_comptable`, `etat_compte` (OUVERT/FERME), `date_ouverture`, `ddc`, `ddd`, `devise`,
`conformite_compte` (CONFORME/NON_CONFORME), `liste_interdiction`, provenance, horodatage.

Index : racine (unique), raison sociale, NNI, NIF, type client ; comptes par racine et par
(agence, état).

Pas de FK depuis `eer_parties.racine_client` / `eer_dossiers.racine_client` : un dossier EER
peut précéder l'apparition du client dans ORION. Le lien reste logique.

## Consolidation (`backend/app/services/clientele/`)

- `consolidation.py` (sans base) : `lire_ligne` refuse un identifiant lu comme nombre, une
  longueur ou un format faux, un RIB qui ne contient pas le compte, un guichet différent de
  l'agence ; `consolider` regroupe par racine. Bloquant : données client différentes d'un compte
  à l'autre, compte ou RIB en double. Signalé : clé RIB invalide, racine absente du compte.
- `persistance.py` : `enregistrer(session, consolidation, date_extraction)`, tout ou rien
  (anomalie bloquante, agence inconnue, compte déjà rattaché à une autre racine → refus).
  Upsert idempotent ; un extrait plus ancien n'écrase pas un plus récent. Pas de commit.

## Tests

| Fichier | Contenu |
|---------|---------|
| `tests/test_clientele_consolidation.py` | Scénario obligatoire (1 client / 3 comptes / 3 RIB puis 2 clients / 4 comptes), zéros initiaux, racine numérique refusée, contrôles RIB, incohérences ; fichier réel si `CLIENTELE_ETAT_COMPTE` est défini |
| `tests/test_clientele_db.py` | Même scénario en base, réimport sans doublon, extrait ancien, changement de racine refusé, agence inconnue, CHECK / UNIQUE / FK / RESTRICT. Sauté sans la migration |

Résultat sur la copie : 28 tests verts. Chargement complet du fichier réel (transaction
annulée) : 42 913 clients, 59 903 comptes, 0 compte orphelin ; réimport = 0 création.
Durée d'écriture ≈ 55 s (insertion par lots de 1 000) — à optimiser en phase 2 (staging + `COPY`).

## Reste à faire

- Phase 2 : module (`plateforme_modules`, permissions, portée agence), table d'imports
  (empreinte SHA-256, rejets), traitement Celery, comptes disparus d'un extrait, scope de
  sauvegarde `module_backup_scopes.py`, écrans.
- Application sur la base réelle : après validation, sauvegarde puis `alembic upgrade head`.
