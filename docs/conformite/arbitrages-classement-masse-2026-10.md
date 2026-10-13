# Arbitrages Conformité avant tout classement de masse — octobre 2026

Base réelle au 13/10/2026 : 42 913 clients (PP 35 813, PM 5 142, non
identifiés 1 958). Moteur `1.3.0-cdc`, règles `CLASSIFICATION-2026.02`.
Chiffres issus de la simulation en lecture seule du 13/10/2026 15:19
(`simulation-classification-20261013-151900.xlsx`, contrôles OK) et du rapport
« Test 2 » (`rapport-tache-5c1b55bb-20261013-151015.xlsx`, contrôles OK),
dans `backend/storage/rapports/` (confidentiel, accès restreint).

**Rien de ce qui suit n’est appliqué.** Le classement de masse est verrouillé
côté serveur jusqu’à validation (voir `clientele-moteur-scoring.md`, « Verrou
serveur »). Aucune restauration ni règle nouvelle sans accord écrit.

Scénarios simulés (classe actuelle → classe simulée, protections du moteur
réel : manuels et classes de fichier préservés, non admissibles non écrits) :

| Scénario | Baisses | Hausses |
|---|---|---|
| S0 règles actuelles (liste ORION hors score) | 5 465 | 0 |
| S1 liste comptée ÉLEVÉ, tous comptes (ancienne règle) | 0 | 1 337 |
| S2 liste comptée ÉLEVÉ, comptes ouverts seulement | 225 | 1 296 |
| S3 = S0 sans double comptage association / profil | 5 465 | 0 |
| S4 = S0 avec secteur en conflit au niveau Fiche | 6 048 | 0 |

---

## 1. Les 1 337 PM de « Test 2 »

- **Impact** : 1 337 PM passés d’ÉLEVÉ à FAIBLE (1 283) ou MOYEN (54) le
  13/10 entre 09:44 et 09:47. Seule cause : suspension de la liste ORION.
  Les 1 337 sont restaurables (classe inchangée depuis, aucun réexamen,
  classe précédente moteur 1.2.0 du 10/10 dans l’historique, aucune classe
  précédente manuelle). Les 2 décisions manuelles PM n’ont pas été touchées.
- **Règle actuelle** : liste hors score → ces PM restent FAIBLE / MOYEN.
- **Proposition** : restaurer la classe précédente tant que le sens des
  codes ORION n’est pas établi (principe de prudence) ; restauration par
  nouvelle écriture tracée (historique + audit, motif « Restauration
  Test 2 — PV … »), sans rien supprimer.
- **À valider** : Conformité — restaurer ou conserver. Aucun geste sans
  accord écrit.

## 2. Codes ORION et alertes en attente

- **Impact** : codes sur 7 288 clients (OI 5 255, DI 2 212, les deux 188 ;
  CI / OV / DV marginaux). 7 347 alertes LISTE_INTERDICTION au statut
  NOUVELLE, jamais traitées. En S0, les 5 465 baisses (5 402 PP, 63 non
  identifiés) sont toutes dues à la liste : OI 4 241, DI 1 127, DI+OI 83,
  autres 14 ; agences 00001 : 3 026, 08001 : 1 111, 00004 : 412.
- **Règle actuelle** : codes lus sur tous les comptes, statut SUSPENDU,
  hors score, cités dans le motif.
- **Proposition** : rester hors score tant que le sens n’est pas documenté ;
  afficher chaque code dans les alertes en attente avec le libellé « code
  ORION non documenté » (jamais « sanction ») ; désigner un responsable de
  traitement des 7 347 alertes. Une fois le sens connu : ÉLEVÉ (§19) ou
  INTERDIT (§5) selon le code.
- **À valider** : DSI / équipe ORION — définition de chaque code ;
  Conformité — traitement retenu par code et responsable des alertes.

## 3. Comptes fermés

- **Impact** : 277 clients n’ont un code que sur des comptes fermés ; si la
  liste revient dans le score, 225 changeraient de niveau selon que l’on
  compte ou non les comptes fermés (S1 vs S2). Aucun effet tant que la liste
  est hors score.
- **Règle actuelle** : tous les comptes, fermés compris ; statut compte
  signalé, jamais interprété.
- **Proposition** : ne retenir pour le score que les comptes ouverts (code le
  plus défavorable par code) ; codes des comptes fermés conservés en
  historique et en alerte.
- **À valider** : Conformité — exclusion des comptes fermés ; DSI — liste
  exacte des valeurs de statut compte (Ouvert, fermé, Bloqué) et statut gel
  (Actif, Inactif, Cloturé).

## 4. Matrice ou Fiche — « Divers Commerce Général »

- **Impact** : 594 clients portent ce secteur (ÉLEVÉ Matrice / FAIBLE
  Fiche). Appliquer la Fiche (S4) ajouterait 583 baisses (556 PM, 27 PP).
- **Règle actuelle** : la Matrice prime (CDC §13), conflit signalé dans le
  détail du critère et dans le motif.
- **Proposition** : maintenir la Matrice (ÉLEVÉ) jusqu’à décision formelle ;
  tout changement passe par une nouvelle version des règles, puis une
  simulation.
- **À valider** : Conformité — niveau du secteur et règle générale de
  priorité Matrice / Fiche.

## 5. Données nécessaires pour un dossier complet

- **Impact** : PPE, filtrage et pays de résidence absents pour 100 % des
  clients ; tous les admissibles seraient « provisoires » : 40 938 FAIBLE,
  888 ÉLEVÉ, 423 MOYEN, 2 INTERDIT.
- **Règle actuelle** : données essentielles PPE, FILTRAGE, RÉSIDENCE,
  NATIONALITÉ ; une donnée absente n’est pas comptée (≠ FAIBLE), complétude
  INCOMPLETE, le client reste classé.
- **Proposition** : afficher séparément niveau, complétude et alertes
  (ex. « FAIBLE — provisoire », liste des données manquantes) ; aucun niveau
  ne change.
- **À valider** : Conformité — liste des données essentielles et libellé
  « provisoire » ; DSI — source PPE, filtrage et référentiel pays.

## 6. Double comptage association / profil

- **Impact** : 273 clients comptés deux fois pour le même fait (association
  et profil « personne morale association ») ; le score baisse en S3 mais
  aucun niveau ne change. Risques identifiés sans cas aujourd’hui : liste
  ORION + filtrage confirmé, non-résidence + pays de résidence.
- **Règle actuelle** : les deux critères comptent.
- **Proposition** : ne compter que le plus élevé des deux ; règle de
  dédoublonnage documentée pour les deux autres paires.
- **À valider** : Conformité.

## 7. Non-résidents

- **Impact** : 297 clients ÉLEVÉ du fait de la non-résidence.
- **Règle actuelle** : non-résident = ÉLEVÉ, quel que soit le pays (pays
  absent des données).
- **Proposition** : conserver ÉLEVÉ tant que le pays est inconnu ; une fois
  le référentiel pays disponible, graduer selon le pays.
- **À valider** : Conformité — maintien de la règle ; DSI — pays de
  résidence dans l’extraction.

## 8. Format final du motif

- **Impact** : présentation seulement ; les classements déjà enregistrés
  gardent leur motif (pas de recalcul sans action explicite).
- **Règle actuelle** : niveau et score, critères ÉLEVÉ / MOYEN avec leurs
  points, nombre et total des FAIBLE, critères suspendus, données
  essentielles manquantes. Le champ « motif de risque » reprend aujourd’hui
  le texte du moteur.
- **Proposition** : format de l’exemple fourni, corrigé : score exact
  (ex. 014249 = **100 300**, pas 200 300) ; liste ORION sous « Hors score /
  alertes en attente », jamais sous « Critères déterminants » ; motif source
  vide quand le moteur décide ; justification humaine séparée, obligatoire,
  historisée (déjà en place).
- **À valider** : Conformité.

---

## Après validation

1. Appliquer les seules règles validées (nouvelle version des règles), tests
   sur copie `*_test`.
2. Relancer la simulation sur la base réelle : contrôles OK, impact conforme.
3. Restauration « Test 2 » si décidée : opération distincte, tracée.
4. Ouvrir le verrou (`CLIENTELE_CLASSEMENT_MASSE_ACTIF=1` +
   `CLIENTELE_CLASSEMENT_MASSE_VALIDATION=<PV>`), lancer d’abord une
   population réduite.
