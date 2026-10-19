# Déclaration mensuelle BCM — correspondance des champs, règles et contrôles

Date : 19/10/2026. Grille `2026.10.bcm.3`. Modèle de référence : « Déclaration mensuelle - BEA - août - 2026 »
(non versionné : chiffres réels). Les explications entre parenthèses du modèle sont traduites en règles de calcul
ci-dessous ; aucun chiffre du modèle n’est repris dans le code.

Code : `backend/app/services/clientele/bcm_calcul.py` (une ligne par client, puis agrégation pure),
`backend/app/services/clientele/declaration.py` (assemblage, contrôles, cycle de vie, snapshot),
`backend/app/data/clientele_bcm_regles.py` (règles et valeurs par défaut),
`backend/app/services/clientele/declaration_modele.py` (export au format du modèle).

---

## 1. Principes

- Clé client = `racine_client` (6 chiffres). Chaque cellule = `COUNT(DISTINCT racine)` ; un client n’est compté
  qu’une fois par cellule (contrôle `unicite.clients`, bloquant).
- **Entrée en relation** d’un client = date d’ouverture minimale de ses comptes ORION (`clientele_comptes`).
  La date d’import dans BEA DIGITAL n’est jamais utilisée. Une fiche sans compte ORION n’est pas déclarée.
- Jours civils au fuseau `Africa/Nouakchott`. Bornes incluses.
- **Une donnée absente ne devient jamais zéro** : la cellule est « Non calculable » avec sa raison.
  Un zéro n’est affiché que si la population est réellement vide alors que la source couvre la période.
- Le classement des clients n’est jamais modifié pour la déclaration (INTERDIT inclus).
- À chaque calcul, la déclaration fige : les règles appliquées (valeur + statut + origine), les données d’entrée
  par client (date d’entrée, compte ouvert, catégorie, gel, risque aux deux dates, dernière mise à jour),
  les exceptions, les contrôles, la date et l’auteur. Le détail des populations et l’export relisent ce snapshot :
  ils reproduisent exactement les chiffres affichés. Une déclaration `VALIDEE` ne se recalcule plus.
- Aucune transmission à la BCM ni à l’UMEF.

## 2. Dates de référence

| Repère | Définition |
|---|---|
| Mois de déclaration | 1er jour → dernier jour du mois choisi |
| Fin du mois précédent | dernier jour du mois précédant le mois de déclaration |
| Fenêtre « cinq dernières années » | règle `maj.fenetre` : `CALENDAIRE` = 1er janvier de Y-5 → fin du mois (défaut) ; `GLISSANTE` = 12 × n mois finissant à la fin du mois |
| Validation officielle | seulement pour un mois calendaire clos |

## 3. Règles de calcul

Statut `CONFIRMEE` = arbitrage ou définition communiquée. Statut `A_VALIDER` = appliquée, signalée dans les
contrôles (`regles.a_valider`) et dans chaque cellule concernée (`regles_a_valider`). Une décision de la
Conformité (écran « Règles de calcul » de la déclaration, permission `clientele.bcm.valider`, motif obligatoire)
remplace la valeur et/ou le statut ; les décisions sont append-only (trigger) et auditées (`bcm.regle.decider`).

| Code | Règle par défaut | Statut | Origine |
|---|---|---|---|
| `stock.date_entree` | premier compte ORION | Confirmée | arbitrage du 19/10/2026 |
| `stock.perimetre` | tous les clients entrés à la date, comptes fermés inclus | Confirmée | arbitrage du 19/10/2026 |
| `actif.valeurs_gel` | `ACTIF` | À valider | définition « compte ouvert et gel actif » |
| `actif.agregation` | au moins un compte ORION ouvert **et** statut de gel client actif | À valider | proposition (le gel n’est connu qu’au niveau client) |
| `eer.source` | premier compte ORION ouvert dans le mois ; module EER en contrôle croisé | Confirmée | arbitrage du 19/10/2026 |
| `maj.fenetre` | calendaire, 5 ans | À valider | cahier des charges |
| `maj.evenements` | classement validé, mise à jour de données validée, date de mise à jour KYC | À valider | cahier des charges §1.2 |
| `interdit.rattachement` | hors colonnes (décompte séparé, inclus dans le total) | À valider | le modèle n’a pas de colonne Interdit |
| `forme.correspondance` | table explicite catégorie ORION → PP / PM / CJ (CJ vide) | À valider | proposition |
| `forme.repli_profil` | non | À valider | option |
| `risque.date_reference` | dernière entrée de l’historique de classification à la date | Confirmée | cahier des charges §6 |

Statut actif d’un client (jamais confondu avec l’état d’un compte) :

| Compte ORION ouvert | Statut de gel (fichier hebdomadaire KYC) | Résultat |
|---|---|---|
| non | quelconque | INACTIF |
| oui | vide / inconnu | INDÉTERMINÉ (ni actif ni inactif) |
| oui | dans `actif.valeurs_gel` | ACTIF |
| oui | autre (Inactif, Cloturé…) | INACTIF |

Correspondance des formes juridiques (`forme.correspondance`, valeur par défaut) :

| Catégorie juridique ORION | Colonne |
|---|---|
| PERSONNE PHYSIQUE | PP |
| SOCIETE COMMERCIALE ; AUT PERS MORALE IMMAT. AU RCS ; PERS MORALE SOUMIS DROIT ADMIN ; PERS.MOR. PUB SOUMIS DROIT COMM ; ORGANISME PRIVE SPECIALISE ; PERSONNE MORALE DROIT ETRANGER | PM |
| *(aucune)* | CJ |
| GROUPEMENT DE DROIT PRIVE ; GRPT DROIT PRI N/DOTE PERS. MOR. ; toute catégorie absente de la table | exception « non rattachée » |
| vide | exception « catégorie vide » |

Niveau de risque → colonne : FAIBLE → faible, MOYEN → moyen, ELEVE → élevé ; INTERDIT → hors colonnes (ou élevé
si `interdit.rattachement = ELEVE`, déclaration uniquement) ; pas d’historique à la date → non classé ;
valeur inconnue → invalide.

## 4. Correspondance champ par champ

Population commune « entré à D » = clients dont le premier compte ORION est ouvert au plus tard à D.

| Champ BCM | Définition métier (modèle) | Source BEA DIGITAL | Filtres | Date de référence | Agrégation / dédoublonnage | Exceptions | Statut |
|---|---|---|---|---|---|---|---|
| T1 l.1 « fin du mois précédent » | clients jusqu’au mois précédent, actifs + inactifs | `clientele_clients` ⋈ `clientele_comptes` | entré à la fin du mois précédent | fin du mois précédent | COUNT DISTINCT racine | sans compte ORION : hors déclaration | Prêt sous réserve |
| T1 l.2 « nombre cible » | clients actifs jusqu’au mois de déclaration | + `clientele_comptes.etat_compte`, `clientele_kyc.statut_gel` | entré à la fin du mois **et** ACTIF | fin du mois (statut de compte = état ORION actuel) | idem | gel inconnu → **cellule non calculable** | Prêt sous réserve, non calculable tant que le gel n’est pas chargé |
| T1 l.3 « mis à jour dans le mois » | EER du mois de déclaration | `clientele_comptes` (min date_ouverture) ; contrôle : `eer_dossiers` (VALIDE / CLOTURE / ARCHIVE, `date_eer` dans le mois) | premier compte ouvert dans le mois | mois | idem | écarts avec le module EER listés (`eer.croise`) | Prêt |
| T1 l.4 « mis à jour sur cinq ans » | clients actifs à partir de 5 ans avant l’année courante | `clientele_journal` (classement, `MAJ_DONNEES`), `clientele_classif_historique` (MANUEL), `clientele_kyc.date_maj_client` | entré à la fin du mois **et** ≥ 1 événement dans la fenêtre | fenêtre `maj.fenetre` | idem | historique ne couvrant pas le début de la fenêtre → **non calculable** | Prêt sous réserve |
| T1A colonnes PP / PM / CJ | forme juridique | `clientele_clients.categorie_juridique` | `forme.correspondance` | — | une colonne par client | vide / non rattachée : hors colonnes, dans le total | Prêt sous réserve |
| T1B colonnes élevé / moyen / faible | degré de risque | `clientele_classif_historique` | niveau à la date | l.1 : fin du mois précédent ; l.2–4 : fin du mois | une colonne par client | INTERDIT / non classé / invalide hors colonnes ; pas d’historique à la date → **non calculable** | Prêt sous réserve |
| T1 TOTAL | somme des clients de la ligne | — | — | — | COUNT DISTINCT racine (jamais la somme des colonnes) | — | Prêt |
| T2 (5 lignes) | opérations inhabituelles | **source absente** | — | — | — | — | Source absente |
| T3 (5 lignes) | opérations suspectes | **source absente** | — | — | — | — | Source absente |
| T4 élevé / moyen / faible | clients actifs / inactifs jusqu’au mois inclus, par niveau | `clientele_classif_historique` | entré à la fin du mois | fin du mois | une colonne par client | INTERDIT / non classés / invalides hors colonnes ; pas d’historique → **non calculable** | Prêt sous réserve |
| T4 total | total des clients à la fin du mois | `clientele_clients` ⋈ `clientele_comptes` | entré à la fin du mois | fin du mois | COUNT DISTINCT racine | — | Prêt |
| T4 ratio | % du niveau | — | — | — | nombre / total × 100, arrondi à 2 décimales ; total nul → non calculable | — | Prêt |

## 5. Contrôles

| Code | Contrôle | Bloquant |
|---|---|---|
| `regles.a_valider` | règles appliquées non confirmées | non |
| `dates.reference` | dates appliquées | information |
| `unicite.clients` | une racine = une ligne | oui |
| `interdit.rattachement` | clients INTERDIT présents et règle non confirmée | **oui** |
| `classif.historique_m1` / `classif.historique_fin` | historique de classification couvrant la date | **oui** |
| `t1a.<ligne>.somme` / `t1b.<ligne>.somme` | colonnes = total ; écart expliqué par les exceptions | non |
| `t1.<ligne>.perimetre` | total T1A = total T1B | oui |
| `t4.identite` | total T4 = T1 l.1 + T1 l.3 | oui |
| `t4.somme` | élevé + moyen + faible = total ; écart = INTERDIT, non classés, invalides | non |
| `t4.ratios` | ratios recalculés | oui |
| `t4.non_classes` / `t4.invalides` | clients sans classement / classement invalide | non |
| `forme.exceptions` | catégories vides ou non rattachées (avec détail) | non |
| `actif.gel` | statut de gel connu | non (rend la ligne 2 non calculable) |
| `maj.couverture` | historique des mises à jour couvrant la fenêtre | non (rend la ligne 4 non calculable) |
| `eer.croise` | premières ouvertures ORION vs dossiers EER du mois | non |
| `perimetre.sans_compte` | fiches sans compte ORION exclues | non |
| `t2.source` / `t3.source` | source absente | non |

Chaque exception est consultable client par client (lien « voir les clients », endpoint
`GET /clientele/declarations/{id}/cellules/bcm.exc.<code>`), comme chaque cellule.

## 6. Comparaison avec le fichier d’août 2026 (copie de test, données du 19/10/2026)

| Champ | Modèle | BEA DIGITAL | Explication |
|---|---|---|---|
| T1 l.1 total | 40 118 | 42 431 | le modèle semble ne retenir que les clients ayant un compte ouvert (40 158 aujourd’hui) ; arbitrage du 19/10 = tous les clients entrés |
| T1 l.3 total | 292 | 292 | identique |
| T1 l.3 PP / PM | 260 / 32 | 247 / 24 (+ 21 en exception) | 17 catégories vides, 4 groupements non rattachés |
| T1 l.1 PP / PM | 34 426 / 5 692 | 23 964 / 2 398 | 15 378 catégories vides et 691 groupements hors colonnes |
| T1 l.2, l.4 | 589 / 7 602 | non calculables | aucun statut de gel chargé ; historique des mises à jour depuis le 12/10/2026 |
| T1B, T4 par risque | 680 / 1 045 / 38 685 | non calculables | historique de classification depuis le 10/10/2026 |
| T4 total | 40 410 | 42 723 | même écart de périmètre que T1 l.1 ; identité T4 = l.1 + l.3 respectée |
| T2, T3 | chiffrés | source absente | aucun registre |

## 7. Tableaux 2 et 3 — proposition de registre (non construit)

Aucune donnée de BEA DIGITAL ne correspond : `clientele_alertes` contient des correspondances de listes ORION,
pas des alertes transactionnelles ; aucun signalement interne, aucune analyse d’opération ni déclaration UMEF
n’est enregistré. T2 et T3 restent distincts.

Proposition à valider par la Conformité :

| Élément | Contenu |
|---|---|
| `bcm_operations` | une ligne par opération : origine (`ALERTE_SYSTEME` pour T2, `SIGNALEMENT_EMPLOYE` pour T3), référence, date de détection, racine client, montant, agence, auteur du signalement |
| `bcm_operation_etats` (append-only) | `EXTRAITE` / `RECUE` → `EN_ANALYSE` → `EN_ATTENTE_REPONSE` / `SUIVI_CONTINU` → `CLOTUREE` / `DECLAREE_UMEF`, avec date, utilisateur, motif |
| `bcm_declarations_umef` | référence UMEF, date d’envoi, opérations liées |
| Calcul | T2 l.1 = extraites du 01/01 à la fin du mois ; l.2 = entrées en analyse ; l.3 = en analyse ou en attente de réponse à la fin du mois ; l.5 = déclarations UMEF envoyées dans le mois ; T3 = même logique sur les signalements des employés, sur le mois |
| À définir | « opérations enregistrées à partir de ces processus » (T2 l.4 et T3 l.4) |

## 8. Questions ouvertes pour la Conformité

1. Confirmer `actif.valeurs_gel` et l’agrégation multi-comptes ; organiser le chargement du statut de gel.
2. Confirmer la fenêtre de cinq ans (calendaire ou glissante) et la liste des événements de mise à jour.
3. Décider du rattachement des clients INTERDIT (bloquant dès qu’il en existe).
4. Confirmer la table des formes juridiques ; statuer sur les groupements et sur le repli PP / PM du profil.
5. Périmètre « actifs + inactifs » : l’écart avec le modèle (≈ 2 300 clients sans compte ouvert) confirme
   que le fichier d’août ne retenait que les clients ayant un compte ouvert. L’arbitrage du 19/10 est à confirmer.
6. Tableaux 2 et 3 : valider le registre proposé.

## 9. Mise en service

- Migration additive `20261019_clientele_12` (table `clientele_bcm_regles` + trigger append-only).
  Appliquée sur la copie `bea_digital_clientele_test` uniquement. Base réelle : sauvegarde, puis
  `alembic upgrade head` (sans la table, les règles par défaut s’appliquent mais aucune décision ne peut être
  enregistrée).
- Les déclarations calculées avant cette version doivent être recalculées pour consulter les populations.
- Le reporting interne (`indicateurs.py`) utilise encore le stock « première extraction » : divergence connue
  avec la déclaration, à aligner séparément.
