# Déclaration SIC (BCM) — correspondance des champs

Modèle : « SIC bcm.xlsx » (feuilles `pp`, `pm`, `ref`). Le fichier est déposé **manuellement** sur la
plateforme SIC de la BCM ; BEA DIGITAL prépare, contrôle, génère et trace. Aucune connexion ni
automatisation de la plateforme SIC.

Code : `backend/app/data/clientele_sic.py` (colonnes, règles), `services/clientele/sic_calcul.py` (lignes,
anomalies, Excel, contre-vérification), `services/clientele/sic.py` (cycle), `services/clientele/bcm_referentiel.py`
(référentiels). Migration `20261019_clientele_13`.

## Fichier PP (feuille `pp`, 10 colonnes, dans cet ordre)

| Colonne | Source | Règle | Absent / invalide |
|---|---|---|---|
| CodeClient | racine ORION | texte, 6 chiffres, zéros conservés | bloquant |
| StatutResidentiel | `statut_resident` ORION | règle `sic.residence` R→MR, N→ETR (nationalité jamais utilisée) | bloquant |
| NNI | `nni` ORION | texte tel quel | absent : bloquant ; hors format `sic.nni_format` : à corriger (exporté) |
| Prenom | `prenoms` ORION sans « [IDP] n° » | règle `sic.nom_prenom` | non découpable : bloquant |
| Nom | nom complet ORION moins le prénom final | jamais deviné | bloquant |
| Genre | dossier EER validé (`sexe`), sinon complément KYC | règle `sic.genre` M→H, F→F ; jamais déduit du prénom | bloquant ; divergence EER/KYC : à corriger |
| CodeCategorieSocioprofessionnelle | complément KYC | code 11xx de la version active du référentiel | bloquant |
| NumTel | EER (`telephone_1..3`), sinon complément KYC | espaces / points / tirets retirés, format `sic.telephone_format` | bloquant |
| DateEntreeEnRelation | premier compte ORION | format `sic.format_date` | bloquant |
| MoughataaAgence | agence du premier compte → table agences SIC | aucune valeur déduite | bloquant |

## Fichier PM (feuille `pm`, 6 colonnes)

| Colonne | Source | Absent / invalide |
|---|---|---|
| CodeClient | racine ORION | bloquant |
| NIF | `nif` ORION (le NNI n'est jamais substitué) | bloquant (`sic.nif_obligatoire`) |
| RaisonSociale | nom ORION | absent : bloquant ; 25 caractères : avertissement (troncature ORION possible) |
| CodeSecteurActivite | complément KYC, sinon correspondance secteur ORION → code BCM | générique (SANS, DIVERS, INCONNU, vide) ou non rattaché : bloquant ; correspondance « à valider » : à corriger |
| DateEntreeEnRelation | premier compte ORION | bloquant |
| MoughataaAgence | agence du premier compte → table agences SIC | bloquant |

## Contrôles communs

- Profil PP / PM de la vue Situation ; profil non identifié → bloquant (le client apparaît dans les deux
  rapports, jamais exclu en silence).
- Confusion PP / PM : catégorie juridique rattachée à l'autre forme dans la correspondance des formes de la
  déclaration mensuelle (`forme.correspondance`, inchangée) → bloquant. Construction juridique → à corriger.
- Doublon de racine → bloquant ; NNI / NIF partagé par plusieurs racines → à corriger.
- Comptes dans plusieurs agences → avertissement (agence du premier compte retenue).
- Clients ayant des comptes mais absents de la vue Situation (compte sans agence) → contrôle bloquant.

Gravités : **BLOQUANTE** (client exclu du fichier, listé), **A_CORRIGER** (exporté, à revoir),
**AVERTISSEMENT** (information). Chaque anomalie porte racine, champ, valeur observée, motif, action attendue.

## Cycle et traçabilité

BROUILLON → contrôle → **A_CORRIGER** / CONTROLEE → validation (`clientele.bcm.valider`, commentaire obligatoire
s'il reste des anomalies) → **VALIDEE_EXPORT** → génération (`clientele.bcm.prepare`) → **GENEREE** → saisie
manuelle du dépôt (`clientele.sic.depot` : date, résultat ACCEPTE / ACCEPTE_PARTIELLEMENT / REJETE /
EN_ATTENTE, commentaire) → **DEPOSEE**.

- Après validation, plus de recalcul ; une correction passe par une nouvelle déclaration (l'historique reste).
- La génération relit le fichier : feuille, en-têtes, ordre, types texte, nombre de lignes, doublons, codes
  autorisés, contenu identique aux lignes validées. Échec → fichier refusé.
- Le fichier, son SHA-256, la version du référentiel et les règles appliquées sont figés dans la déclaration.
- Audit : création, contrôle, validation, génération, téléchargement, rapport, dépôt, import / activation de
  référentiel, correspondances, compléments (téléphone masqué dans le journal).
- Aucune donnée client, classification, KYC existant ou compte n'est modifié par une déclaration.

## Référentiel BCM (feuille `ref`)

Import en version BROUILLON (SHA-256, anomalies : code non numérique, libellé / catégorie absents, doublon,
code 11xx hors catégorie PP). Activation motivée, refusée en cas de doublon ; la version active précédente est
archivée. Codes immuables (trigger), version non brouillon jamais supprimée, comparaison entre versions.
Usage : catégorie « Personne physique » / « Autre PP » → PP (CSP), sinon PM (secteurs).

## Points à valider (Conformité / BCM)

1. Périmètre (`sic.perimetre`, défaut : au moins un compte ouvert à la date — état ORION actuel, pas d'historique
   de fermeture).
2. Format de date accepté par SIC (`sic.format_date`, défaut texte jj/mm/aaaa ; le modèle indique
   mm/dd/yyyy hh:mm:ss).
3. Valeurs MoughataaAgence par agence (aucune moughataa dans la table agences).
4. Correspondances secteur ORION → code BCM.
5. Formats NNI (10 chiffres proposé) et téléphone (8 chiffres, +222 facultatif).
6. Découpage Nom / Prénom : sur la copie de test, 12 415 PP sur 35 813 se découpent avec la règle confirmée ;
   3 368 ont le prénom en tête du nom complet (option `PRENOM_EN_FIN_OU_EN_TETE`, à valider) ; 9 475 ont un
   champ prénoms identique au nom complet (préfixe « [IDM] ») ; 3 180 noms sont tronqués à 25 caractères.
7. 1 708 clients « PERSONNE PHYSIQUE » ont l'agent économique « AUTRES SOCIETES » (profil PM) : confusion
   signalée, à corriger dans ORION ou à arbitrer.
8. Ligne d'instructions du modèle (ligne 2) : non reproduite dans le fichier généré (en-tête + données).

Décisions de la déclaration mensuelle (rattachement INTERDIT, catégories juridiques, fenêtre de cinq ans,
sources des tableaux d'opérations) : inchangées et non résolues par le développement SIC.
