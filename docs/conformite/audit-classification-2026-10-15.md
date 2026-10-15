# Audit de la classification LBC/FT — état avant paramétrage (15/10/2026)

Audit **en lecture seule** : aucune donnée, règle, classification, évaluation ni
historique modifié ; moteur non relancé ; classement de masse toujours verrouillé.
Les impacts sont chiffrés à partir des évaluations déjà photographiées.

- Script : `backend/scripts/audit_classification.py` (connexion
  `app.db.lecture_seule`, feuille « Contrôles » : 8 contrôles OK).
- Classeur détaillé (CONFIDENTIEL, données clients) :
  `backend/storage/rapports/audit-classification-20261015-093337.xlsx` — hors
  Git, hors image Docker, conservation 90 jours.
- Relancer : `docker compose exec -w /app -e PYTHONPATH=/app backend python
  scripts/audit_classification.py --matrice <Matrice.xlsx> --fiche <V4.xlsx>`.

Ce document ne contient que des agrégats. Toute liste nominative est dans le classeur.

## 1. État avant modification

| Élément | Valeur vérifiée en base |
|---|---|
| Clients (racines) / comptes | 42 912 / 59 902 |
| Classés | 42 250 (moteur 42 247, manuel 3) |
| Non classés | 662 |
| Réexamens | 2 (1 ouvert, 1 traité le 15/10/2026) |
| Divergences Matrice / Fiche à arbitrer | 115 (+ 1 « alignée », 1 « source invalide ») |
| Valeurs du référentiel maître à arbitrer | 5 (+ 5 canaux « à configurer ») |
| Valeurs du référentiel maître actives | 0 |
| Classement de masse | verrouillé (aucune référence de PV) |

Écarts avec l'état annoncé : **1 seul réexamen ouvert** (l'autre a été traité le
15/10 à 08:40 par « Administrateur Système »).

Anomalies transverses :

- **Deux versions du moteur coexistent** dans les classements retenus :
  40 912 sous `1.2.0-cdc`, 1 338 sous `1.3.0-cdc` (version du code). Les
  classements 1.2.0 n'ont pas été recalculés (règle : rien sans action explicite).
- **Deux décisions manuelles motivées « TEST1 »** (12/10/2026, Administrateur
  Système) sur des clients réels, classés ÉLEVÉ. L'une a un réexamen ouvert.
  À revoir par la Conformité ; rien n'a été supprimé.
- Moteur à règles historique : version 1 ACTIVE sans aucune règle, version 2
  BROUILLON sans règle — non utilisées par le moteur SCORE.

Sources lues par le moteur SCORE : ORION État des comptes, référentiel versionné
`clientele_classif_referentiel.json` (extraction Matrice V1 + Fiche V4), lots
hebdomadaires, EER, alertes. **Les tables `clientele_classif_pays / _valeurs`
ne sont pas lues par le moteur** : il lit le JSON.

Données essentielles non disponibles pour **tous** les clients : PPE, filtrage
confirmé, pays de résidence. Les 24 dossiers EER ne sont rattachés à **aucune**
racine client : ni le pays de résidence, ni la date de création PM, ni la
procuration EER n'atteignent le moteur.

## 2. Date d'ouverture de l'entreprise

- Le moteur **n'utilise jamais** la date d'ouverture d'un compte bancaire
  (vérifié dans `_collecter`). Ordre des sources : date saisie sur une ligne de
  lot → colonne « Date ouverture » du fichier → date de création PM de l'EER.
- **Aucun champ « date RCCM »** dans ORION : seul le numéro RCCM (`rcs`) existe
  (2 859 PM sur 5 142).
- Situation : **5 142 PM sans aucune date utilisable** (donnée manquante), 1 957
  profils non identifiés (applicabilité à vérifier), 0 date disponible.
  Le critère est NON_DISPONIBLE (hors score) — conforme à la règle « donnée
  absente ≠ Faible ».
- Personnes physiques : critère NON_APPLICABLE (règle existante).

Impact si une date était fournie (PM aujourd'hui sans critère) :

| Hypothèse | Effet |
|---|---|
| Entreprise ancienne (+100) | aucun changement de niveau |
| Entreprise récente (+10 000) | jusqu'à **3 724 FAIBLE → MOYEN** (borne haute) |

Les 648 PM non classées restent « à arbitrer » tant que le conflit de forme
juridique (§ 8) n'est pas tranché.

## 3. Statut du compte / statut de gel

- **Statut du compte** : ORION `etat_compte` = OUVERT (57 342) / FERME (2 560).
- **Statut de gel** : **aucune source**. ORION État des comptes n'a pas ce
  champ ; le fichier hebdomadaire a une colonne « Statut Gel » sans compte ni
  RIB (aucune agrégation possible). Les 17 lignes du lot existant sont vides.
- Valeurs observées hors liste cible : « Bloqué » (statut compte) et
  « Cloturé » (statut gel) — ni Ouvert/Fermé ni Actif/Inactif : **à arbitrer**.
- Composition : 40 530 clients tous comptes ouverts, 2 273 tous fermés,
  **109 mixtes**, 14 731 multi-comptes.
- Agrégation existante (technique, non approuvée) : vue `clientele_situation`,
  client CLOTURE si tous ses comptes sont FERME, sinon OUVERT.
- Le moteur n'utilise ni l'un ni l'autre ; la liste d'interdiction ORION est lue
  sur **tous** les comptes, ouverts ou fermés.

Proposition (à valider) : statut compte client = « Ouvert » si au moins un
compte ouvert, « Fermé » si tous fermés ; statut de gel = « non disponible »
jusqu'à une source par compte ; les 109 mixtes listés pour contrôle.

## 4. Catégories juridiques

Inventaire (classeur, feuille 4) : 9 valeurs `categorie_juridique`, 38
`situation_juridique`, 45 valeurs du fichier hebdomadaire. Le moteur lit
`categorie_juridique`, sinon `situation_juridique`.

| Correspondance (clients × champ) | Occurrences |
|---|---|
| Exacte | 413 |
| Proposée (rapprochement partiel unique) | 791 |
| Ambiguë | 2 032 |
| Non reconnue | 51 766 |
| Vide | 30 822 |

Constats :

- Les libellés ORION (« SOCIETE COMMERCIALE », « PERSONNE PHYSIQUE »,
  « Société à responsabilité limité (SARL) »…) ne correspondent pas aux
  libellés des référentiels : **26 815 clients ont une forme juridique
  « à vérifier »** (hors score).
- **« GROUPEMENT DE DROIT PRIVE » (663 clients)** est rapproché automatiquement
  de « Groupement » (PM privée, conflit MOYEN/FAIBLE) par un rapprochement
  partiel. Or 254 d'entre eux sont des associations ou fondations selon
  `situation_juridique`, et 14 ont un profil PP. Rapprochement à valider.
- « SARL » (situation) est ambigu : plusieurs libellés candidats.
- Les 45 catégories du fichier hebdomadaire sont presque toutes exactes ; il
  s'agit d'une liste hétérogène (profils PP, formes, types PM).

Le classeur fournit la table de correspondance demandée (valeur source,
normalisée, cible, niveau associé, justification, statut de validation,
date). **Aucun niveau n'est attribué aux catégories non résolues.**
Question PM privée / SARL — Moyen ou Faible : **reste à arbitrer** (§ 8).

Proposition technique (non appliquée) : table `clientele_classif_formes_mapping`
versionnée (valeur source brute, clé normalisée, cible, statut
EXACTE/PROPOSEE/VALIDEE/REJETEE, auteur, date), lue par le moteur à la place
du rapprochement partiel implicite.

## 5. NNI / NIF

Stockage : `VARCHAR(40)`, chaînes, zéros initiaux préservés (2 162 NNI et
1 119 NIF conformes commencent par 0). Aucune contrainte en base ; l'import
hebdomadaire signale la longueur sans tronquer.

| Profil | Champ | Conforme | Non conforme | Vide |
|---|---|---|---|---|
| PP | NNI | 20 462 | **3 752** | 11 599 (obligatoire proposé) |
| PP | NIF | 6 | 0 | 35 807 |
| PM | NIF | 1 370 | **106** | 3 666 (obligatoire proposé) |
| PM | NNI | 248 | 51 | 4 843 |
| Non identifié | — | — | — | 1 957 |

Non conformes : surtout NNI de 16 chiffres (1 971 — probablement un autre
identifiant saisi dans le champ NNI), caractères non numériques (651),
séparateurs internes. 185 NNI seraient conformes après retrait des séparateurs
— **non appliqué**. Liste nominative : classeur, feuille 5.

Obligation par profil (PP : NNI ; PM : NIF) : **proposition à valider**.
Les contraintes ne doivent être activées qu'après correction des 3 909 valeurs
à la source (ORION), sinon les imports seraient rejetés.

## 6. Référentiel pays

Source : feuille « Zone géographique » de `Matrice des risques LBC FT BEA
V1-7-5-25.xlsx` (fichier de la Banque présent dans le dépôt). Aucune autre
liste n'a été utilisée. Statut : **« fourni par la Banque — validation
Conformité à confirmer »**.

- 247 lignes lues : FAIBLE 181, MOYEN 16, ÉLEVÉ 43, INTERDIT 7 (Iran, Israël,
  Corée du Nord, Myanmar, Fédération de Russie, Syrie, Yémen). Niveaux
  conservés tels quels.
- 0 doublon ; **18 noms probablement tronqués** à 20 caractères (« FRENCH
  SOUTHERN TERR », « SYRIAN ARAB REPUBLIC », « UNITED ARAB EMIRATES »…).
- **Codes ISO non renseignés** : aucune table ISO 3166-1 de référence dans le
  projet ; ils ne sont pas reconstitués de mémoire.
- Le référentiel du moteur (JSON) a **9 entrées issues de la seule Fiche, non
  fusionnées** avec la Matrice (Syrie, Russie, Corée du Nord/Sud, …) : un
  client rattaché à ces entrées n'a pas de niveau Matrice.

Rapprochement des nationalités ORION (64 valeurs) : 40 720 clients rapprochés
d'un pays de la Matrice, **12 rattachés à une entrée Fiche seule** (Syrie 8,
Corée du Sud 3, Russie 1 — Syrie et Russie sont INTERDIT dans la Matrice),
5 non rapprochés (« ETATS-UNIS AMERIQUE », « POLYNESIE FRANCAISE »,
« non concerné »), 2 175 vides. Pays de résidence EER : 3 valeurs, toutes
« Renseigné » (valeur de consigne), aucune rattachée à un client.

**Comportement actuel à connaître** : le moteur applique MOYEN forfaitaire à
toute nationalité étrangère (le niveau du pays n'est pas utilisé) ; seul le
pays de résidence utilise le niveau pays, et un pays INTERDIT y est déjà
traité comme **bloquant** (CDC §5, §17). Ce comportement n'a jamais été
déclenché (aucun pays de résidence alimenté). La conséquence métier de
« Interdit » (blocage, alerte, refus, validation manuelle) **reste à
arbitrer** ; « Interdit pays » est distinct des codes DI / OI ORION (non
disponibles, non inventés).

## 7. Conversion HAUT / FORT / BAS

- Emplacement unique : `backend/app/services/clientele/lots.py`,
  `normaliser_niveau()` (HAUT / FORT → ÉLEVÉ, BAS → FAIBLE). Le contrôle
  fichier / moteur (`CORRESPONDANCES_OFFICIELLES`) ne reconnaît déjà que
  Faible / Moyen / Élevé / Interdit.
- Valeur brute conservée (`classe_source_brut`).
- **0 ligne concernée** en base (17 lignes, toutes « Moyen ») ; 0
  classification issue d'une conversion.
- Proposition pour la Conformité : retirer les synonymes ; HAUT / FORT / BAS
  → « classe illisible », valeur brute conservée. Non appliqué.

## 8. Divergences et valeurs à arbitrer

Dossier complet (classeur, feuille 8) : identifiant, valeurs des deux sources,
règle moteur, clients concernés, impact, proposition, décision attendue, statut.

| Domaine | Nb | Règle moteur actuelle | Impact sur les classements |
|---|---|---|---|
| PAYS | 106 | Matrice retenue (résidence) | aucun aujourd'hui (résidence non alimentée) |
| FORME_JURIDIQUE (SARL, SA, SUARL…) | 1 | conflit exclu, évaluation « à arbitrer » | **662 non classés** |
| PROFIL PM privée | 1 | idem | 0 client en conflit sur ce critère |
| SECTEUR | 2 | Matrice retenue, conflit signalé | 13 clients (« Divers Commerce Général ») |
| PP_CATEGORIE, PPE_NON, SANCTIONS, SEUIL_SCORE | 5 | voir classeur | 0 aujourd'hui sauf seuils (tous) |

Pays : 82 FAIBLE / 6 ÉLEVÉ / 4 INTERDIT / 2 MOYEN présents dans la Matrice
seule (pas de conflit de niveau), 9 présents dans la Fiche seule, 3 INTERDIT
(Matrice) vs « Inacceptable » (Fiche).

Les 5 valeurs à arbitrer (profil PM privée ; SARL, SUARL, Groupement,
Professions libérales) portent toutes la même question : **MOYEN (Matrice) ou
FAIBLE (Fiche)**. Impact chiffré sur les 662 non classés :

| Décision | Résultat |
|---|---|
| Matrice (MOYEN, +10 000) | 269 ÉLEVÉ, 393 MOYEN |
| Fiche (FAIBLE, +100) | 269 ÉLEVÉ, 387 FAIBLE, 6 MOYEN |

(269 sont des associations / fondations : ÉLEVÉ quel que soit le choix.)

Aucune source n'a été rendue prioritaire ; aucune règle modifiée.

## 9. Classement de masse

Verrouillé côté serveur (`CLIENTELE_CLASSEMENT_MASSE_ACTIF` absent, aucune
référence de PV). Non modifié. Procédure de déverrouillage : voir
`clientele-moteur-scoring.md` § « Verrou serveur ».

## 10. Non classés et réexamens

- **662 non classés, cause unique** : conflit de référentiel non arbitré sur la
  forme juridique (PM privée « Groupement »). 648 PM, 14 PP (profil
  incohérent avec la catégorie « Groupement de droit privé »). Aucun cas de
  donnée manquante seule ni d'erreur de calcul. Ils seront classés dès
  l'arbitrage du § 8, **par une action explicite** (masse verrouillée).
- Réexamen ouvert (1) : moteur propose FAIBLE (score 200), décision manuelle
  ÉLEVÉ « TEST1 » conservée. À traiter par un arbitre via le workflow existant.
- Réexamen traité (1) : décision manuelle FAIBLE « Decision finale » (15/10).
- Aucune fermeture automatique ; décisions, auteurs et historique intacts.

## 11. Produit / opération et Canal

Critères PRODUIT, TYPE_OPERATION, PAYS_PROVENANCE / DESTINATION_FONDS, CANAL,
ORIGINE_FONDS : **NON_DISPONIBLE** (hors score). Aucune source opérations ni
canal dans BEA DIGITAL ; ORION État des comptes n'a pas le canal. Référentiel
Matrice : 14 produits, 2 canaux ; 5 canaux à configurer (DIGITAL,
APPLICATION, WEB, INTERMEDIAIRE, AUTRE). Données candidates non utilisées :
NCG / rubrique comptable des comptes, origine des fonds EER (non rattaché).
Sources, clés et propriétaires présumés : classeur, feuille 11.

## 12. Analystes KYC

Aucun identifiant stable dans le fichier hebdomadaire (noms ou prénoms seuls).

| Valeur | Rapprochement proposé |
|---|---|
| Fatimata Thiam | nom identique à un compte — à valider |
| Abass / Abass N'gam | compte « Abass Ngam » (similaire) — à valider |
| Fatimata | **2 candidats** (Diop, Thiam) — à arbitrer |
| Fatimata Diallo | aucun compte identique (« Fatimata Diop » similaire) |
| Mohamed Lemrabott, Mouhamed, Ba | aucun compte |
| Non identifié | valeur de consigne |

Aucun compte créé, aucun rôle attribué. Table à valider par le responsable KYC.

## Propositions de corrections (non appliquées)

1. Rattacher les dossiers EER aux racines clients (sans quoi pays de résidence,
   PPE, procuration et date de création restent indisponibles).
2. Fusionner les 9 entrées pays « Fiche seule » avec leur ligne Matrice
   (nouvelle version du référentiel, historique conservé) ; compléter les noms
   tronqués et les codes ISO depuis la norme officielle.
3. Table de correspondance des formes juridiques versionnée, validée ligne à
   ligne, remplaçant le rapprochement partiel implicite.
4. Contrôles NNI / NIF à l'import (signalement, jamais de troncature) puis
   contraintes après correction à la source.
5. Retrait des synonymes HAUT / FORT / BAS.
6. Paramètre explicite de la conséquence « pays Interdit » (en attente).
7. Après arbitrages : nouvelle version des règles, simulation lecture seule,
   sauvegarde vérifiée, classement contrôlé par lot, rapport avant / après.

## Décisions à obtenir de la Conformité

1. PM privée (profil, SARL, SUARL, Groupement, Professions libérales) :
   MOYEN ou FAIBLE — débloque les 662 non classés.
2. « GROUPEMENT DE DROIT PRIVE » ORION : groupement (PM privée) ou association
   selon la situation juridique ?
3. Validation de la table de correspondance des catégories juridiques.
4. Source de la date d'ouverture de l'entreprise (RCCM via lot, EER) et
   applicabilité aux profils non identifiés.
5. Règle d'agrégation multi-comptes ; correspondance de « Bloqué » et
   « Cloturé » ; source du statut de gel.
6. Obligation NNI / NIF par profil.
7. Validation du référentiel pays (247 lignes, niveaux de la Banque) et
   conséquence métier du niveau « Interdit ».
8. Nationalité : maintien du MOYEN forfaitaire ou application du niveau pays.
9. 106 divergences pays, 2 secteurs, catégories PP, PPE = Non, sanctions
   (ÉLEVÉ / INTERDIT), seuils de score.
10. HAUT / FORT / BAS : retrait des synonymes.
11. Les deux décisions manuelles « TEST1 » et le réexamen ouvert.
12. Sources et règles Produit / opération / Canal ; 5 canaux à configurer.
13. Table des analystes KYC (dont « Fatimata »).
14. Recalcul des 40 912 classements établis en moteur 1.2.0 (après validation).
15. PV de validation pour le déverrouillage du classement de masse.
