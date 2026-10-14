# Module Gestion des réclamations (`reclamations`)

Espace **Audit, Contrôle & Conformité** → domaine **Management & Qualité**.
Code `reclamations`, URLs front `/reclamations/...`, API `/api/v1/reclamations/...`,
statut CORE `actif`.

## Décisions métier validées

| Sujet | Décision |
|-------|----------|
| Pilotage | Service Réclamations central (unité `est_service_reclamations`, une seule active) |
| Clôture | Service Réclamations uniquement, après retour jugé suffisant du service concerné, réponse client envoyée et preuve d’envoi enregistrée |
| Délais | Règles configurables par type ou motif, **aucune règle initiale** : aucune échéance n’est calculée tant qu’un administrateur n’a pas créé de règle. Aucun délai n’est présenté comme réglementaire avant validation Conformité (`statut_validation`) |
| Unités | Liste réelle des entités BEA (reprise du module Formation) + création de directions, départements, services, agences, cellules dans le module. La table org `departements` (vide) n’est pas utilisée |
| Données | Aucune donnée fictive : seuls les canaux, canaux de réponse et une proposition de types (marquée « à valider ») sont insérés |
| Documents | GED (`ged_documents`, entité `reclamation`), plusieurs pièces par dossier, original jamais écrasé, retrait logique avec motif et audit. Aucun rôle du module ne reçoit `ged.*` |

## Modèle (migration `20261013_reclamations_01`)

| Table | Rôle |
|-------|------|
| `reclamation_referentiels` | Types, motifs (parent type), sous-motifs (parent motif), canaux de réception, canaux de réponse |
| `reclamation_unites` / `reclamation_unite_membres` | Unités organisationnelles du module et leurs membres (`RESPONSABLE` / `AGENT`) |
| `reclamations` | Dossier : référence `REC-AAAA-NNNNNN`, statut **et** étape séparés, client (racine ORION facultative), dates distinctes (première réception, réception SR, transmission, réception service, retour service, réponse client, clôture, réouverture), échéance figée, motifs de suspension / refus / annulation, `revision` |
| `reclamation_affectations` | Fiches de traitement (transmission → réception → retour → évaluation SR), renvois chaînés par `parent_id` |
| `reclamation_reponses` | Réponses client : brouillon → à valider → validée → envoyée (canal + date obligatoires) |
| `reclamation_documents` | Lien GED ↔ dossier, catégorie (original, pièce client, transmission, fiche, justificatif, retour, réponse, preuve d’envoi, autre) |
| `reclamation_appels` | Canal téléphone / centre d’appel : date-heure, numéro, agent, vérification d’identité, rappel ; référence d’enregistrement seulement si la banque l’autorise |
| `reclamation_evenements` | Chronologie **append-only** (trigger `trg_reclamation_evenements_immuable`) : rien n’est effacé |
| `reclamation_regles_delai` | Règles de délai (type / motif / priorité, jours calendaires ou ouvrés, point de départ, seuil d’alerte, délai service, neutralisation des suspensions, validation Conformité) |
| `reclamation_jours_feries`, `reclamation_parametres`, `reclamation_compteurs` | Calendrier, paramètres, numérotation annuelle verrouillée |

Contraintes base : cohérence chronologique des dates, unicité du service central actif,
unicité des codes et libellés de référentiel par parent.

## Statuts et étapes

Statuts (14) : Reçue initialement, Reçue par le SR, Ouverte / à qualifier, Affectée / transmise,
En cours de traitement, En attente d’information, Retour reçu — à vérifier, Réponse à préparer,
Réponse envoyée — à clôturer, Suspendue, Refusée / irrecevable, Clôturée, Réouverte,
Annulée / doublon. Terminaux : Clôturée, Refusée, Annulée.

Étapes (7) : Réception, Qualification, Affectation, Traitement, Retour, Réponse, Clôture.

Règles (phase 3) : suspension avec motif obligatoire ; réouverture qui conserve la clôture
précédente ; refus justifié par un profil autorisé ; renvoi au service avec motif et nouvelle
échéance ; aucune suppression d’historique.

## Droits

Permissions `reclamations.*` (31) contrôlées côté backend et sur les données.

| Rôle | Contenu |
|------|---------|
| `reclamations.point_reception` | Consultation de son périmètre, enregistrement, pièces |
| `reclamations.agent_traitement` | Traitement des fiches de son unité, pièces |
| `reclamations.responsable_service` | + gestion des affectations de son service, reporting |
| `reclamations.agent_sr` | Tout le périmètre, qualification, affectation, revue des retours, préparation / envoi des réponses, suspension |
| `reclamations.responsable_sr` | + validation des réponses, refus, annulation, clôture, réouverture, archivage, retrait de pièces, export, gestion des unités, audit |
| `reclamations.lecteur` | Consultation / audit sur tout le périmètre, exports |
| `reclamations.admin` | Toutes les permissions du module |

Périmètre (`services/reclamations/acces.py`) : `reclamations.scope.all` → tous les dossiers ;
sinon dossiers créés par l’utilisateur, reçus par une de ses unités ou affectés à une de ses
unités. Un dossier hors périmètre répond `404`.

## Enregistrement, fiche et pièces (phase 2)

Écrans : `/reclamations/dossiers` (liste), `/reclamations/dossiers/nouvelle`,
`/reclamations/dossiers/:id?onglet=…` (Général, Réception, Traitement, Chronologie, Documents,
Réponse client, Délais, Audit), `/reclamations/parametres?onglet=unites`.

| API `/api/v1/reclamations` | Usage |
|---|---|
| `GET /config` | Accès, capacités, référentiels, unités, agences, libellés, paramètres |
| `GET/POST /referentiels`, `PATCH/DELETE /referentiels/{id}` | Nomenclature ; suppression seulement si jamais utilisé (dossiers, éléments rattachés, règles), sinon désactivation |
| `GET/POST /unites`, `PATCH /unites/{id}` | Directions, départements, services, agences, cellules ; hiérarchie sans cycle ; le service central ne se désactive pas |
| `GET/POST /unites/{id}/membres`, `PATCH …/membres/{mid}` | Rattachement des agents (`RESPONSABLE` / `AGENT`) |
| `GET /utilisateurs?q=`, `GET /clients/{racine}` | Recherche d’agents ; aperçu client ORION (racine, comptes) |
| `GET/POST /dossiers`, `GET/PATCH /dossiers/{id}` | Liste paginée côté serveur (filtres, tri), création, fiche, correction |
| `POST /dossiers/{id}/appels` | Appel téléphonique supplémentaire |
| `GET /dossiers/{id}/chronologie`, `GET /dossiers/{id}/audit` | Événements ; journal d’audit (`reclamations.audit.view`) |
| `GET/POST /dossiers/{id}/documents`, `POST …/{did}/retrait`, `GET …/{did}/fichier?apercu=` | Pièces GED |
| `POST /dossiers/{id}/recevoir-sr` … `/archiver` | Actions du circuit (statut uniquement par ces routes) |
| `POST /dossiers/{id}/reponse`, `…/soumettre`, `…/valider`, `…/renvoyer`, `…/envoyer` | Cycle de la réponse client |
| `GET/POST/PATCH /regles-delai`, `POST …/validation`, `GET/POST/DELETE /jours-feries` | Délais internes et calendrier |
| `GET /alertes`, `GET /tableau-de-bord`, `GET /circuit`, `GET /export` | Pilotage, kanban, Excel (5 000 lignes max) |

Règles appliquées :

- Référence `REC-AAAA-NNNNNN` attribuée par le serveur (compteur annuel verrouillé).
- Dates réelles saisies (première réception, réception SR) distinctes de l’heure de saisie ;
  pas de date future ; correction d’une date de réception = motif obligatoire, tracé.
- Statut initial : « Reçue initialement », ou « Reçue par le SR » si un membre du SR saisit
  la date de réception SR. Le statut n’évolue ensuite que par les actions du circuit (phase 3).
- Canal téléphone : section appel obligatoire (date-heure, numéro, vérification d’identité,
  rappel). La référence d’enregistrement d’appel n’est acceptée que si le paramètre
  `enregistrement_appels_autorise` vaut vrai (absent = refusé).
- Carte : seul un numéro masqué est accepté (au plus 10 chiffres, ex. `411111******1111`).
- Un agent hors périmètre global doit être membre d’une unité pour enregistrer ; il ne voit que
  ses dossiers et ceux de ses unités. Le point de réception corrige son dossier tant qu’il est
  « Reçu initialement ».
- Correction concurrente refusée (`revision`, 409 `CONFLIT_REVISION`).
- Pièces : GED cloisonnée (`MODULES_CLOISONNES`) — invisibles dans la recherche GED générale,
  niveau `restricted`, pas d’OCR. Chaque dépôt crée une pièce (jamais d’écrasement) ; aperçu et
  téléchargement audités ; retrait = corbeille GED + motif + événement ; l’original n’est
  retirable que par l’administration du module.

Tests : `backend/tests/test_reclamations_fondations.py`, `test_reclamations_dossiers.py`
(transactions annulées). Parcours navigateur réalisé sur une copie jetable de la base.

## Avancement

| Phase | Contenu | État |
|-------|---------|------|
| 1 | Schéma, catalogue CORE, profils, périmètre, `GET /config`, routes et navigation | fait |
| 2 | Référentiels, unités et membres, création, liste paginée, fiche à onglets, pièces GED | fait |
| 3 | Circuit (qualification → affectation → retour → réponse → clôture), actions sur la fiche | fait |
| 4 | Délais paramétrables, jours fériés, alertes, notifications in-app, job Celery quotidien | fait |
| 5 | Tableau de bord 360°, circuit kanban, rapports, export Excel | fait |
| 6 | Tests (`fondations`, `dossiers`, `circuit`), activation locale, images Docker | fait |

## En attente de la Conformité / du métier

- Nomenclature des types, motifs et sous-motifs (les 9 types insérés sont une proposition).
- Délais par type / motif et leur caractère réglementaire.
- Autorisation d’enregistrer une référence d’enregistrement d’appel.
- Rattachements d’unités à vérifier : « MARKETING ET COMMUNICATION » a été créé comme service
  sous le département « MARKETING & COMMUNICATION » (libellés distincts dans la source Formation).
