# Moteur de classification LBC/FT — CDC 1.0

Date : 08/10/2026. Migrations `20261008_clientele_06` et `07` **uniquement**
sur `bea_digital_clientele_test` / `bea_digital_recette`. Base réelle
`bea_digital` inchangée. **Aucune classification massive. Aucune valeur ACTIVE.**

## Noms des sources

| Code interne (base, API) | Nom affiché |
| --- | --- |
| `MATRICE_V1`, `niveau_matrice`, `SOURCE_V1` | **Matrice des risques LBC/FT BEA** |
| `SCORING_V4`, `niveau_v4`, `SOURCE_V4` | **Fiche de scoring** |

Les codes restent stables (historique, migrations). Les textes renvoyés par
l’API passent par `app/data/clientele_sources.py` ; le front utilise
`SOURCES_LBC` / `STATUTS_REGLE` (`clientele.models.ts`).

## Écrans

- **Classification** : sous-onglets Clients classés, Simulation (sans
  écriture, retenue vs proposée), Référentiel maître, Critères, Divergences
  (arbitrage + historique), Réexamens, Versions (`?onglet=`).
- **Fiche client** : évaluer avec le moteur (score, critères, motif, date de
  référence), enregistrer le résultat du moteur, décision manuelle motivée
  (forçage si permission), historique complet.
- **Importer** (`/clientele/imports?source=`) :
  - `orion` — État des comptes ORION (assistant existant) ;
  - `situation` — classeur Situation des comptes PP & PM : reprise de la
    classe de risque (source `EXCEL_CONFORMITE`) ;
  - `liste` — import hebdomadaire : voir « Lots » ci-dessous.
  Lot et lignes en base (`clientele_classif_lots`, `_lot_lignes`) ; seul le
  fichier brut est temporaire (7 jours, pour recartographier). API
  `/api/v1/clientele/lots/...`. Une racine absente n’est jamais créée.

## Décision de conception

```text
MATRICE DES RISQUES LBC/FT BEA  +  FICHE DE SCORING
        ↓
RÉFÉRENTIEL UNIQUE BEA DIGITAL (LOT 1)
        ↓
MOTEUR SCORE  (additif, une seule mécanique)
```

- **SCORE uniquement.** Pas de moteur concurrent `MAX_NIVEAU`.
- **INTERDIT** = blocage métier (`BLOCKING`), distinct de ÉLEVÉ = 100 000.
  Le score reste calculable ; le dossier est signalé bloquant.
- Une donnée absente n’est **jamais** FAIBLE.
- Un conflit V1/V4 n’est **jamais** fusionné silencieusement : identifié,
  documenté, exclu de la somme jusqu’à arbitrage.
- Classification permanente du client ≠ évaluation d’une opération.

## Seuils (CDC §4 — défaut Excel C39 corrigé)

| Score | Niveau |
|-------|--------|
| 0 critère évalué | NON CLASSÉ |
| score < 10 000 | FAIBLE |
| 10 000 ≤ score < 100 000 | MOYEN |
| score ≥ 100 000 | ÉLEVÉ |
| critère INTERDIT V1 | INTERDIT (blocage) |

Échelle de référence : FAIBLE = 100, MOYEN = 10 000, ÉLEVÉ = 100 000.

## Quatre familles

CLIENT · GÉOGRAPHIE · PRODUIT/SERVICE/OPÉRATION · CANAL

Le score client permanent additionne Client + géographie client.
Produit / canal / provenance / destination n’entrent dans le score
permanent que lorsqu’une source opérationnelle validée existe (aujourd’hui
`NON_DISPONIBLE`).

## Référentiel maître (LOT 1)

Chaque ligne : **Dimension → Critère → Valeur → Score V1 → Niveau V1 →
Score V4 → Niveau V4 → Score retenu → Niveau retenu → Source → Version →
Conflit → Statut → actif=false**.

- Géographie et 119 sous-secteurs : **V1** est le référentiel métier.
  V4 est un contrôle, jamais un remplacement silencieux.
- Canaux supplémentaires (DIGITAL, APPLICATION, WEB, INTERMEDIAIRE, AUTRE) :
  prévus techniquement, **aucun score inventé** (`A_CONFIGURER`).
- PM privée / SARL : **A_ARBITRER** (V1 MOYEN vs V4 100).

API : `GET /api/v1/clientele/classification/valeurs`

## Moteur

`backend/app/services/clientele/scoring.py`

1. Charger les données client (racine 6 chiffres).
2. Évaluer chaque critère (EVALUE / NON_DISPONIBLE / NON_APPLICABLE / A_VERIFIER).
3. Exclure de la somme : `A_ARBITRER`, `A_CONFIGURER`, `A_VERIFIER`, poids 0.
4. Additionner les scores des critères retenus, par famille.
5. Appliquer les seuils CDC.
6. Si un critère INTERDIT V1 matche → niveau final INTERDIT (score conservé).
7. Générer le motif à partir des règles réellement utilisées.
8. Enregistrer le snapshot (`clientele_classif_evaluations`) **sans écraser**
   la classification retenue.

## Ce que le moteur ne fait pas

- Inventer un niveau quand Matrice et V4 divergent.
- Traiter une donnée absente comme Faible.
- Classer FAIBLE s’il n’y a aucun critère évalué.
- Activer les valeurs du référentiel maître.
- Écrire une classification de production depuis `POST /classification/evaluer`.
- Charger 119 secteurs + 247 pays comme règles ACTIVE de production.

## Livrables

- `backend/app/data/clientele_classif_referentiel.json` : extraction brute.
- `backend/app/data/clientele_classif_matrice.py` : catalogue des critères.
- `backend/app/data/clientele_classif_valeurs.py` : référentiel maître LOT 1.
- `backend/app/services/clientele/scoring.py` : moteur SCORE.
- Tables : `clientele_classif_dimensions`, `_valeurs`, `_pays`, `_secteurs`,
  `_formes`, `_divergences`, `_evaluations`.
- API : `GET .../matrice`, `/valeurs`, `/divergences`, `POST /evaluer`, `/backtest`.

## Directive du 10/10/2026 — décision de classification (migration `20261010_clientele_08`)

Moteur `1.2.0-cdc`, règles `CLASSIFICATION-2026.02`. Appliquée le 10/10/2026
sur la base unique `bea_digital`.

**Base unique (10/10/2026)** : l’ancienne `bea_digital` (sous-ensemble) a été
supprimée, `bea_digital_recette` renommée `bea_digital` (27 lignes d’audit
propres à l’ancienne base recopiées), bases `bea_digital_clientele_test` et
`bea_digital_eer_test` supprimées, `docker-compose.recette.yml` retiré.
Sauvegardes : `backups/*_20261010_avant_fusion.dump`. Les tests sur base
(`test_clientele_decision_db.py`) s’exécutent sur une copie jetable
`*_test` créée pour l’occasion puis supprimée ; sinon ils sont ignorés.

### Critère « Entreprise à ouverture récente » (`ENTREPRISE_RECENTE`)

| Ancienneté (date de référence − date d’ouverture) | Poids |
|---|---|
| ≤ 366 jours | 10 000 (MOYEN) |
| > 366 jours | 100 (FAIBLE) |

- Personnes morales uniquement (PM publique : **pas** de cas particulier).
  PP → `NON_APPLICABLE` (ou `A_VERIFIER` si une date / un « Oui » est fourni).
- **Date d’ouverture**, par priorité : saisie analyste sur la ligne du lot
  (`SAISIE`) > colonne « Date ouverture » du fichier (`FICHIER`) > date de
  création PM de l’EER (`EER`). **Jamais** la `DATOUV` d’un compte ORION.
  Aucune date n’est inventée.
- **Date de référence** : date d’extraction ORION du client
  (`EXTRACTION_ORION`), sinon date du calcul (`DATE_CALCUL`). Conservée dans
  l’évaluation et dans la classification.
- **Colonne « Entreprise ouverture récente »** (Oui / Non) :
  - avec une date : comparée au calcul ; contradiction → `A_VERIFIER`
    (exclu de la somme, signalé dans les anomalies du lot) ;
  - sans date : déclaratif analyste KYC (Oui = 10 000, Non = 100, source
    `DECLARATIF_KYC`) ;
  - valeur illisible, date invalide ou future → `A_VERIFIER`.
- **Interaction avec le score cumulé** : +10 000 suffit à porter un client
  au moins en MOYEN (10 000 ≤ score), jamais seul en ÉLEVÉ (< 100 000).
  Ex. : 200 (autres critères) + 10 000 = 10 200 → MOYEN ; 200 + 100 = 300 →
  FAIBLE. Aucun autre poids ni seuil modifié.

### Politique de décision

- Le moteur **propose** (`score_calcule`, `niveau_propose`, `motif_moteur`).
- La classe du fichier est une donnée source (`classe_source_fichier`,
  `motif_source`), jamais confondue avec le calcul.
- Le niveau retenu (`niveau`) porte un `mode_decision` : `MOTEUR`, `FICHIER`
  ou `MANUEL` (+ `motif_decision_manuelle`).
- Seuls `EVALUE` et `BLOQUANT` sont admissibles : `NON_CLASSE`,
  `A_ARBITRER`… ne sont jamais enregistrés comme classification valide.
- Une décision manuelle n’est **jamais** remplacée par un import ou le
  moteur : un **réexamen** est ouvert (`clientele_classif_reexamens`, un seul
  ouvert par racine) et traité par un arbitre.
- **Forçage** (`clientele.classif.force`) : confirmation explicite + motif,
  tracé dans l’audit (`clientele.classif.forcage`).
- **INTERDIT bloquant** : un niveau inférieur n’est accepté que par forçage,
  tracé « levée de blocage » (`blocage_leve = true`,
  `clientele.classif.manuel.blocage_leve`).
- Traçabilité sur la classification **et** l’historique : lot, ligne source,
  évaluation, date de référence, date de MAJ métier, analyste KYC, versions
  moteur / règles, `force`, `blocage_leve`, auteur, date.

### Lots (import hebdomadaire)

Import → Mapping → Contrôles → Aperçu → Rapprochement → Évaluation →
Divergences → Enregistrement contrôlé → Historique → Export (SOURCE /
RESULTATS_MOTEUR / DECISIONS / ANOMALIES).

Format hebdomadaire réel (`File-uploade-par-semaine.xlsx`) : une feuille
`Feuil1`, 22 colonnes en ligne 3, consignes en ligne 4, **listes de
référence mélangées aux lignes suivantes, sans aucune racine client**.
Ces listes ne sont **jamais** importées comme des clients.

Modèle propre (téléchargeable `GET /lots/modele.xlsx`) :

| Feuille | Rôle |
|---|---|
| `CLIENTS` | Seule feuille à remplir. Une ligne par `RACINE CLIENT`. 22 colonnes source + `DATE_CREATION_ENTREPRISE` + `ENTREPRISE_OUVERTURE_RECENTE`. |
| `REFERENTIELS` / `SECTEURS_BCM` | Listes observées dans le fichier source. **Pas** le référentiel maître. |
| `NOTICE_IMPORT` | Dictionnaire : origine, format, obligatoire, règle. |
| `RESULTATS_MOTEUR` | Documentation des champs générés par BEA DIGITAL. Ne pas remplir. |

- Colonnes reconnues : les 22 du classeur + date de création entreprise /
  entreprise récente. **DATE EER n'est jamais** une date de création.
- Feuille `CLIENTS` prioritaire ; feuilles techniques ignorées.
- Contrôles : racine (6 chiffres, zéros conservés), inconnue (jamais
  créée), invalide, doublon, dates, NIF (9) / NNI (10) non tronqués,
  cohérence code/libellé/famille BCM, profil / sous-profil / catégorie,
  statuts observés (fermés / bloqués / clôturés / gelés **non assimilés**).
- Pas de COMPTE / RIB : aucun agrégat multi-comptes n'est déduit.
- Une donnée absente du fichier n'est pas absente de la base : le moteur
  lit encore ORION, EER, PPE, procurations, alertes, référentiels.
- Évaluation (≤ 2 000 racines) : même moteur que la fiche client (mêmes
  compléments : date saisie / fichier, déclaratif) ; évaluation photographiée
  avec `lot_id` + ligne.
- Divergence = classe du fichier ≠ niveau proposé admissible. Jamais écrite
  automatiquement ; traitement ligne par ligne (`POST /lots/{id}/divergences`,
  choix MOTEUR / FICHIER / AUTRE + motif → décision manuelle).
- Moteur non admissible (ex. NON CLASSÉ) : comparaison `NON_COMPARABLE` ;
  l’enregistrement « classe du fichier » reste possible (mode `FICHIER`) pour
  un lot `SITUATION` uniquement (voir contrôle ci-dessous pour `LISTE`).
- Ré-import identique : signalé (empreinte SHA-256) ; niveaux identiques →
  `INCHANGE` (pas de nouvelle ligne d’historique) ; réexamen non dupliqué.
- Export = feuille `CLIENTS` uniquement, 22 colonnes du modèle (CODE AGENCE …
  Analyste KYC). Pas de colonnes moteur, pas de DATE_CREATION_ENTREPRISE.
- Historique des lots : voir, exporter, modifier (libellé / période), fermer,
  supprimer (motif obligatoire). La suppression retire le lot et ses lignes ;
  les classifications déjà écrites sur les fiches restent. Audit conservé.
- Fermer un lot = statut `FERME` (fichier brut retiré, lot et lignes conservés).

#### Contrôle fichier / moteur SCORE (liste de clients, règle du 13/10/2026)

Pour un lot `LISTE`, chaque ligne reconnue est comparée **dès l’analyse** au
niveau **enregistré** par le moteur SCORE (`clientele_classifications.niveau_propose`).
Le moteur n’est **pas** relancé ; aucun niveau n’est modifié par le contrôle.
Résultat conservé dans `clientele_classif_lot_lignes.decision_detail.controle`
(niveaux fichier brut / normalisé, niveau et score SCORE, version des règles,
classement en vigueur, horodatage). Pas de migration : colonnes existantes.

| Statut | Condition | Action |
|---|---|---|
| `CONFORME` | Niveau fichier = niveau SCORE | « Le niveau du fichier correspond au niveau du moteur SCORE. Aucune décision requise. » Aucun bouton. |
| `ECART` | Niveaux officiels différents | « Écart détecté » : deux options seulement (ci-dessous). |
| `DONNEE_MANQUANTE` | Niveau absent du fichier **ou** client sans niveau SCORE enregistré | « Comparaison impossible — donnée manquante ». Aucune décision automatique. |
| `NON_COMPARABLE` | Libellé hors correspondance officielle, ou niveau SCORE inattendu | Anomalie : vérification requise. Aucune décision possible. |

Correspondance officielle : **Faible, Moyen, Élevé, Interdit** uniquement,
comparés sans tenir compte de la casse, des accents ni du mot « risque »
(« Risque élevé » = `ELEVE`). Aucune autre équivalence n’est inventée :
`HAUT`, `FORT`, `BAS`, abréviations, chiffres → `NON_COMPARABLE`.

Décision sur un écart (`POST /lots/{id}/controle/decision`, `ligne`, `choix`,
`justification`, `forcer`, `confirmation` ; permission `clientele.classif.execute`) :

- **A — `MOTEUR`** « Conserver le classement du moteur SCORE » : décision de
  contrôle seule, commentaire facultatif. La classification enregistrée n’est
  pas modifiée (`effet = AUCUNE_MODIFICATION`).
- **B — `FICHIER`** « Retenir le niveau du fichier » : justification
  **obligatoire** ; circuit habituel `decider_manuel` (décision `MANUEL`,
  niveau SCORE calculé conservé dans `niveau_propose`, ligne d’historique).
  Si le moteur SCORE classe INTERDIT : forçage (`clientele.classif.force`,
  confirmation, audit `clientele.classif.forcage`).
- Re-contrôle au moment de la décision contre la classification **actuelle** :
  plus d’écart → `409 PAS_D_ECART`. Une seule décision par ligne
  (`409 DEJA_DECIDE`). Lot fermé ou `SITUATION` refusé.
- Trace : `decision_detail.decision_controle` (choix, niveau retenu, niveaux
  comparés, justification, effet, forçage, auteur, date) + audit
  `clientele.lot.controle.moteur|fichier` (avant / après).
- `decision` de la ligne : `CONSERVE_MOTEUR` / `RETENU_FICHIER`.
- Pour un lot `LISTE`, « Enregistrer la classe du fichier » en masse est
  refusé (`409 DECISION_PAR_LIGNE`). Lot `SITUATION` inchangé.
- Re-mapping refusé dès qu’un écart a été décidé (`409 CONTROLE_DECIDE`) :
  les décisions ne peuvent pas être effacées par une nouvelle analyse.
- Filtres de lignes : `CONTROLE_A_DECIDER`, `CONTROLE_DECIDE`,
  `CONTROLE_CONFORME`, `CONTROLE_ECART`, `CONTROLE_DONNEE_MANQUANTE`,
  `CONTROLE_NON_COMPARABLE`. Compteurs `controle_*` dans les stats du lot.
- Les lots analysés avant cette règle n’ont pas de résultat de contrôle
  (colonne « — ») : ré-analyser le fichier (re-mapping) pour l’obtenir.

Anomalie relevée, non corrigée : `normaliser_niveau` (import) traduit encore
`HAUT`/`FORT` → `ELEVE` et `BAS` → `FAIBLE` sans base officielle. Le contrôle
ne s’appuie pas dessus ; à arbitrer par la Conformité.

Tests : `backend/tests/test_clientele_lot_controle.py` (cas identique,
libellé officiel écrit autrement, différent, manquant fichier / moteur,
non comparable ; décisions A / B, justification, forçage INTERDIT, permission,
moteur jamais relancé).

### Classement de masse (remplace « Appliquer règles ACTIVE »)

L’ancien bouton appelait le moteur à règles historique (`appliquer_moteur`,
version ACTIVE sans aucune règle → « Aucune règle active »). Il est remplacé
par « Classer avec le moteur SCORE » (`POST /classification/moteur-masse`) :

- périmètre : tous les clients, filtre **optionnel** profil (PP / PM /
  NON_IDENTIFIE) et / ou agence (`clientele_situation`) ;
- par paquets de 300 racines (curseur `apres`) enchaînés par le front ;
- résultats admissibles seulement ; classements MOTEUR mis à jour ;
  décisions manuelles **et** classes reprises d’un fichier jamais écrasées
  (réexamen ouvert si écart) ; chaque évaluation photographiée ; un audit
  `clientele.classif.moteur_masse` par paquet ;
- relance sans doublon (niveau identique = inchangé, réexamen non dupliqué).

#### Bouton « Classer » — tâche serveur suivie (migration `20261013_clientele_10`)

L’écran n’enchaîne plus les paquets côté navigateur. Le bouton « Classer »
ouvre le choix de population (**Tous les clients**, **PP uniquement**,
**PM uniquement**, agence optionnelle), avec les effectifs réels, puis lance
une tâche serveur (`clientele_classif_taches`) :

- `POST /classification/taches` (`population` = TOUS / PP / PM, motif
  obligatoire) → 202 ; 409 `TACHE_EN_COURS` si une tâche est déjà active ;
- `GET /classification/taches/{id}` interrogé toutes les 1,5 s : statut,
  traités / total, pourcentage, bilan (classés = écrits + inchangés,
  préservés manuel / fichier, non classés = non admissibles, erreurs) ;
- `GET /classification/taches/courante` : au rechargement de la page, la
  progression est retrouvée ; `GET /classification/taches/perimetre` :
  effectifs TOUS / PP / PM / non identifiés ;
- paquets de 100 racines, chacun validé (commit) ; une racine en erreur est
  isolée (savepoint) et comptée « en erreur » sans bloquer les autres ;
- tâche sans nouvelles depuis 2 min (redémarrage) → INTERROMPU ;
  `POST /classification/taches/{id}/reprendre` repart après la dernière
  racine traitée (`curseur`) ;
- même traitement que `moteur-masse` (`traiter_paquet_moteur`) : aucune
  règle ni aucun score modifié. Audits `clientele.classif.tache.lancer`,
  `.reprendre`, `.fin` + `clientele.classif.moteur_masse` par paquet.

Débit mesuré sur copie : ≈ 27 clients / s (PM : 5 142 en 3 min 10 s ;
base complète ≈ 27 min). « Tous les clients » inclut les profils non
identifiés (1 958 au 13/10/2026).

#### Verrou serveur du classement de masse (13/10/2026)

Tant que la Conformité n’a pas validé les règles (voir
`arbitrages-classement-masse-2026-10.md`), **tout classement de masse par le
moteur SCORE est refusé côté serveur** : 409 `CLASSEMENT_MASSE_SUSPENDU`.

| Chemin | Bloqué |
|---|---|
| `POST /classification/taches`, `/taches/{id}/reprendre` (bouton « Classer ») | oui |
| `POST /classification/moteur-masse` | oui |
| `traiter_paquet_moteur` (appel indirect, y compris tâche déjà en cours : passe INTERROMPU au paquet suivant) | oui |
| `appliquer_moteur` sans racine | oui |
| `POST /lots/{id}/classer` origine `MOTEUR` | oui |
| `POST /lots/{id}/classer` origine `FICHIER`, décisions ligne à ligne | non (classes Conformité / humaines) |
| Fiche client : `classification/moteur`, décision manuelle, réexamen | non |

Le classement **individuel** reste autorisé : permission
`clientele.classif.execute`, motif obligatoire, décision manuelle jamais
écrasée sans forçage (`clientele.classif.force` + confirmation + motif),
INTERDIT levé seulement par forçage, historique et audit.

`GET /classification/taches/autorisation` (lecture) renvoie l’état du verrou ;
le front désactive « Classer » et « Classer avec le moteur » (lot) et affiche
le motif.

**Réactivation** (après validation écrite de la Conformité) :

1. appliquer les règles validées (nouvelle version des règles si besoin), tests
   sur copie `*_test` ;
2. relancer la simulation (`scripts/simulation_classification.py simuler`) sur
   la base réelle : feuille « Contrôles » entièrement OK, impact conforme à la
   décision ;
3. renseigner **les deux** variables du backend (`.env.docker`) :
   `CLIENTELE_CLASSEMENT_MASSE_ACTIF=1` et
   `CLIENTELE_CLASSEMENT_MASSE_VALIDATION=<référence du PV>` — l’une sans
   l’autre laisse le verrou fermé ;
4. `docker compose up -d backend worker` ; vérifier
   `/classification/taches/autorisation` (`actif: true`) ;
5. lancer d’abord une population réduite (PM ou une agence) ; la référence
   du PV est inscrite dans chaque audit (`validation`).

Pour refermer : remettre `CLIENTELE_CLASSEMENT_MASSE_ACTIF=0` et redémarrer ;
une tâche en cours s’interrompt au paquet suivant (reprise possible après
réouverture).

#### Simulation et rapports (lecture seule)

`scripts/simulation_classification.py` (`simuler`, `rapport-tache <id>`)
utilise `app/db/lecture_seule.py`, trois verrous indépendants : connexion
PostgreSQL `default_transaction_read_only=on` ; seules les requêtes
SELECT / WITH / SHOW partent (un `SET … read_only = off` est refusé) ;
flush et commit SQLAlchemy refusés (`EcritureInterdite`), y compris par un
service appelé indirectement (`evaluer_racine(persister=True)`,
`ecrire_resultat_moteur`, audit).

Chaque classeur : « Lisez-moi » (avertissement CONFIDENTIEL, paramètres,
base sans identifiants, versions moteur / règles, empreinte SHA-256 du
script), feuilles de résultats, feuille « Contrôles » (totaux / matrices /
populations / agences / causes / détails) ; un écart → sortie code 2.
`journal.jsonl` trace chaque exécution sans donnée client (paramètres,
empreinte du classeur, contrôles, résumé, purges).

Protection : `backend/storage/rapports/` hors Git (`.gitignore`), hors image
Docker (`.dockerignore`), non servi par nginx ni par l’API ; ACL Windows
limitée à l’utilisateur, SYSTEM et Administrateurs (POSIX : 700 / 600).
Conservation 90 jours (`--conservation-jours`), purge à chaque exécution.
Transmission à la Conformité par canal interne protégé uniquement.

### Permissions

`clientele.classif.force` et `clientele.classif.arbitrer` : rôle
**Clientèle — Admin** uniquement (attribution individuelle possible via
CORE ADMIN). Capacités front : `classif_forcer`, `classif_arbitrer`.

### API ajoutée

`GET /lots`, `POST /lots/{id}/date-ouverture`, `POST /lots/{id}/divergences`,
`POST /clients/{racine}/classification/moteur`,
`GET /clients/{racine}/classification/historique`,
`GET /classification/reexamens`, `POST /classification/reexamens/{id}/traiter`,
`POST /classification/divergences/{id}/arbitrer`,
`GET /classification/divergences/{id}/historique`.
`POST /lots/analyse` accepte `periode_reference`.

### Tests

- `tests/test_clientele_entreprise_recente.py` : seuil 366 / 367 jours, date
  de référence, déclaratif, contradictions, PP, PM publique, lecture Excel.
- `tests/test_clientele_decision_db.py` : sur une base `*_test` uniquement
  (sinon ignoré), transaction annulée ; contrôles du lot, cohérence
  individuel / lot, divergences, manuel préservé, ré-import, forçage
  (403 / 422 / OK + audit), INTERDIT, saisie de date.
- `tests/test_clientele_verrou_masse.py` : verrou fermé par défaut, ACTIF
  sans référence = fermé, chaque chemin de masse refusé avant tout accès base,
  lots FICHIER non concernés. Les tests de masse ouvrent le verrou par la
  fixture `masse_autorisee`.
- `tests/test_lecture_seule_db.py` (`*_test`) : SQL brut, `SET` de
  contournement, accès asyncpg direct, rollback, flush / commit, appels
  indirects du moteur — compteurs de la base inchangés.
- `tests/test_simulation_scenarios.py` : scénarios S0–S4 et niveau retenu.

### Décisions du 13/10/2026 (moteur `1.3.0-cdc`)

- **Motif moteur complet** : niveau et score, puis **tous** les critères
  ÉLEVÉ / MOYEN avec leurs points (du plus fort au plus faible), le nombre et
  le total des critères FAIBLE, les critères suspendus (hors score) et les
  données essentielles non disponibles (PPE, filtrage, résidence,
  nationalité : non comptées, ≠ FAIBLE). Le client reste classé.
- **Conflit sectoriel** Matrice / Fiche (ex. « Divers Commerce Général »
  ÉLEVÉ / FAIBLE) : la Matrice prime (CDC §13), mais le conflit est
  **signalé** dans le détail du critère et dans le motif.
- **Liste d'interdiction** : voir ci-dessous (tous comptes, DI et OI suspendus).
- Les classements déjà enregistrés gardent leur ancien motif et leur ancien
  score : rien n'est recalculé sans action explicite. Un classement de masse
  relancé avec ces règles ferait baisser les ÉLEVÉ dus uniquement à la liste
  (≈ 6 800 au 12/10/2026) : à décider par la Conformité avant de le lancer.

### Points restant à arbitrer

- **Liste d'interdiction ORION** : codes `DI` **et** `OI` lus sur **tous les
  comptes** du client (dédoublonnés ; segments vides ignorés, une valeur faite
  uniquement de virgules vaut « vide »). Valeur visible, statut `SUSPENDU`,
  **hors score** jusqu'à confirmation du sens des codes et arbitrage
  ÉLEVÉ (§19) / INTERDIT (§5). Vide/Non reste Faible 100.
- Le moteur lit encore le référentiel versionné (JSON) : une divergence
  Matrice / Fiche arbitrée n’est appliquée au score qu’après publication
  d’une nouvelle version des règles.
- La colonne « Date ouverture » du fichier doit être la date d’ouverture de
  l’entreprise (RCCM), pas la `DATOUV` du compte : à confirmer avec le
  fournisseur de l’extraction.
- Enregistrement « classe du fichier » quand le moteur n’est pas admissible :
  autorisé et tracé (`NON_COMPARABLE`) ; à confirmer par la Conformité.
- **Statut compte / Statut Gel** : valeurs observées (Ouvert, fermé, Bloqué /
  Actif, Inactif, Cloturé). Sémantique et règle d’agrégation multi-comptes
  à confirmer — aujourd’hui signalées, jamais assimilées.
- **Catégorie juridique** : la liste source mélange profils PP, formes
  sociales et types PM. Mapping vers le référentiel maître à arbitrer.
- **NIF / NNI** : longueurs max 9 / 10 reprises du fichier source ; règle
  exacte (chiffres uniquement ?) à confirmer.
- **Pays** : aucune liste dans le classeur source. Nationalité / résidence
  restent du texte jusqu’au référentiel pays officiel.
- **Analystes KYC** observés (Fatimata Diallo, Fatimata Thiam,
  Mohamed Lemrabott, Abass N'gam, Non identifié) : à aligner sur les
  utilisateurs autorisés.
## Lots suivants (non activés)

LOT 2 Client · LOT 3 Géographie opérationnelle · LOT 4 Produit/opération ·
LOT 5 Canaux · LOT 6 snapshot/historique complet · LOT 7 administration
(versions, conflits, simulation) · LOT 8 reporting / BCM.
