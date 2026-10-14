# Module Gestion des réclamations (`reclamations`)

Espace **Audit, Contrôle & Conformité** → domaine **Management & Qualité**.
Code `reclamations`, URLs front `/reclamations/...`, API `/api/v1/reclamations/...`,
statut CORE `actif`.

## Décisions métier validées

| Sujet | Décision |
|-------|----------|
| Pilotage | Service Réclamations central (unité `est_service_reclamations`, une seule active) |
| Clôture | Service Réclamations central uniquement (403 `CLOTURE_RESERVEE_SR` sinon), après retour jugé suffisant du service concerné (ou traitement interne SR) et enregistrement de la réponse envoyée au client (409 `REPONSE_NON_ENVOYEE` sinon). La preuve d’envoi est facultative (à valider) |
| Délais | Règles configurables par type ou motif, **aucune règle initiale** : aucune échéance n’est calculée tant qu’un administrateur n’a pas créé de règle. Aucun délai n’est présenté comme réglementaire avant validation Conformité (`statut_validation`) |
| Unités | Liste réelle des entités BEA (reprise du module Formation) + création de directions, départements, services, agences, cellules dans le module. La table org `departements` (vide) n’est pas utilisée |
| Données | Aucune donnée fictive : seuls les canaux, canaux de réponse et une proposition de types et de motifs (marquée « Proposition initiale — nomenclature à valider par la banque ») sont insérés. L’option « Autre » (saisie libre) existe à chaque niveau motif / sous-motif |
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

## Pipeline, statuts et transitions (migration `20261014_reclamations_02`)

Pipeline en 4 étapes : **Réception → Affectation → Traitement → Clôture**.

| Statut | Étape | Transitions possibles |
|---|---|---|
| À qualifier | Réception | Qualifier → À affecter ; Transmettre → En traitement ; Traiter au SR → À clôturer ; Rejeter ; Annuler |
| À affecter | Affectation | Transmettre au service → En traitement ; Traiter au SR ; Rejeter ; Annuler |
| Réouverte | Affectation | idem « À affecter » |
| En traitement | Traitement | Retour du service → Retour reçu |
| Retour reçu | Clôture | Examiner : suffisant → À clôturer ; insuffisant (commentaire obligatoire) → nouvelle fiche, En traitement |
| À clôturer | Clôture | Enregistrer la réponse envoyée ; Clôturer (SR central, réponse enregistrée) → Clôturée |
| Clôturée / Rejetée | Clôture | Rouvrir (motif) → Réouverte ; Archiver |
| Annulée | Clôture | Archiver |

Terminaux : Clôturée, Rejetée, Annulée. Retirés de l’interface : la page « Réponse client »
(brouillon / validation), la page « Audit », l’action « Demander une information » et la
suspension. Les traces historiques (événements, audit, anciennes réponses) sont conservées ;
les anciens codes de statut / d’étape restent lisibles dans l’historique.

Reprise des dossiers existants : RECUE / RECUE_SR → À qualifier ; A_QUALIFIER → À affecter ;
AFFECTEE / EN_TRAITEMENT → En traitement ; RETOUR_RECU → Retour reçu ; REPONSE_* → À clôturer ;
REFUSEE → Rejetée ; ATTENTE_INFO / SUSPENDUE → statut d’avant la suspension. Un événement
`MIGRATION_CIRCUIT` trace chaque reprise. Sauvegarde préalable : `pg_dump` hors dépôt.

## Opérations concernées

Table `reclamation_operations` (1-N) : référence (obligatoire, unique par dossier sans tenir
compte de la casse), montant en MRU (> 0, 2 décimales), ordre. L’ancienne opération unique
(`operation_reference` / `montant_conteste`) est reprise comme première ligne. Liste, pipeline,
fiche et export affichent le nombre d’opérations et le montant total. Les indicateurs comptent
des **dossiers** ; les montants sont sommés par opération, chaque opération une seule fois.

## Formulaire d’enregistrement

1. Informations générales : référence (automatique), date de la réclamation, date de réception
   par la banque si différente, canal, point de réception, agence concernée, service concerné,
   priorité.
2. Appel téléphonique (canal téléphone uniquement).
3. Client : racine ORION (recherche), catégorie, nom, téléphone, e-mail, adresse.
4. Réclamation : type, motif, sous-motif (dépend du motif ; « Autre » ouvre un champ texte),
   objet, description.
5. Opérations concernées : lignes référence + montant, ajout / retrait, total en MRU.

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
`/reclamations/dossiers/:id?onglet=…` (Général, Traitement & clôture, Documents, Historique),
`/reclamations/circuit` (pipeline), `/reclamations/parametres?onglet=unites`.
`/reclamations/reponses` redirige vers la liste.

| API `/api/v1/reclamations` | Usage |
|---|---|
| `GET /config` | Accès, capacités, référentiels, unités, agences, libellés, paramètres |
| `GET/POST /referentiels`, `PATCH/DELETE /referentiels/{id}` | Nomenclature ; suppression seulement si jamais utilisé (dossiers, éléments rattachés, règles), sinon désactivation |
| `GET/POST /unites`, `PATCH /unites/{id}` | Directions, départements, services, agences, cellules ; hiérarchie sans cycle ; le service central ne se désactive pas |
| `GET/POST /unites/{id}/membres`, `PATCH …/membres/{mid}` | Rattachement des agents (`RESPONSABLE` / `AGENT`) |
| `GET /utilisateurs?q=`, `GET /clients/{racine}` | Recherche d’agents ; aperçu client ORION (racine, comptes) |
| `GET/POST /dossiers`, `GET/PATCH /dossiers/{id}` | Liste paginée côté serveur (filtres, tri), création, fiche, correction |
| `POST /dossiers/{id}/appels` | Appel téléphonique supplémentaire |
| `PUT /dossiers/{id}/operations` | Remplacement de la liste des opérations (révision, motif facultatif, tracé) |
| `GET /dossiers/{id}/chronologie` | Historique des événements |
| `GET/POST /dossiers/{id}/documents`, `POST …/{did}/retrait`, `GET …/{did}/fichier?apercu=` | Pièces GED |
| `POST /dossiers/{id}/qualifier`, `affecter`, `traiter-interne`, `retourner`, `evaluer`, `cloturer`, `refuser`, `annuler`, `rouvrir`, `archiver` | Actions du circuit (statut uniquement par ces routes) |
| `POST /dossiers/{id}/reponse` | Enregistrement de la réponse envoyée (contenu, canal, date d’envoi) |
| `GET/POST/PATCH /regles-delai`, `POST …/validation`, `GET/POST/DELETE /jours-feries` | Délais internes et calendrier |
| `GET /alertes`, `GET /tableau-de-bord`, `GET /circuit`, `GET /export` | Pilotage, kanban, Excel (5 000 lignes max) |

Règles appliquées :

- Référence `REC-AAAA-NNNNNN` attribuée par le serveur (compteur annuel verrouillé).
- Dates réelles saisies (première réception, réception SR) distinctes de l’heure de saisie ;
  pas de date future ; correction d’une date de réception = motif obligatoire, tracé.
- Statut initial : « À qualifier » (étape Réception). Si l’auteur est membre du SR, la date de
  réception SR est posée automatiquement. Le statut n’évolue ensuite que par les actions du circuit.
- Date de la réclamation obligatoire, ni future ni postérieure à la réception par la banque.
- Canal téléphone : section appel obligatoire (date-heure, numéro, vérification d’identité,
  rappel). La référence d’enregistrement d’appel n’est acceptée que si le paramètre
  `enregistrement_appels_autorise` vaut vrai (absent = refusé).
- Carte : seul un numéro masqué est accepté (au plus 10 chiffres, ex. `411111******1111`).
- Un agent hors périmètre global doit être membre d’une unité pour enregistrer ; il ne voit que
  ses dossiers et ceux de ses unités. Le point de réception corrige son dossier tant qu’il est
  « À qualifier ».
- Correction concurrente refusée (`revision`, 409 `CONFLIT_REVISION`).
- Pièces : GED cloisonnée (`MODULES_CLOISONNES`) — invisibles dans la recherche GED générale,
  niveau `restricted`, pas d’OCR. Chaque dépôt crée une pièce (jamais d’écrasement) ; aperçu et
  téléchargement audités ; retrait = corbeille GED + motif + événement ; l’original n’est
  retirable que par l’administration du module.

Tests : `backend/tests/test_reclamations_fondations.py`, `test_reclamations_dossiers.py`,
`test_reclamations_circuit.py` (scénarios 1 à 10 : création complète, motif « Autre »,
opérations multiples, rejets de validation, pipeline, clôture réservée au SR, clôture sans
réponse refusée, réouverture, KPI sans double comptage, reprise des données) — transactions annulées.

## Notes, pièces jointes et suppression (migration `20261014_reclamations_03`)

- **Notes et pièces jointes** (onglet de la fiche) : « Ajouter une note » propose *note scannée*
  (type `NOTE`, PDF ou image uniquement, titre obligatoire) ou *autre document* (courrier,
  justificatif, document de traitement, retour du service, autre…). Chaque ajout crée un nouveau
  document GED (jamais d’écrasement) : titre, date du document (pas dans le futur), type,
  commentaire, nom du fichier, date d’ajout et auteur conservés. Contrôles d’extension, de
  signature et antivirus ; stockage privé, accès uniquement via l’API authentifiée
  (`reclamations.document.view` / `.download`, périmètre du dossier).
- **Suppression = corbeille (suppression logique)**. La suppression définitive est impossible :
  l’historique est en ajout seul (trigger `trg_reclamation_evenements_immuable`) et relève de la
  conservation documentaire. Un dossier supprimé sort des listes, KPI, exports et alertes, devient
  non modifiable, et reste consultable et restaurable (avec motif) depuis la corbeille.
- Permission `reclamations.delete`, accordée au seul rôle `reclamations.admin` ; l’attribuer
  explicitement via CORE ADMIN pour un autre profil. Contrôle côté serveur, motif obligatoire,
  confirmation par saisie de la référence, révision vérifiée, événement + audit
  (`reclamations.suppression` / `reclamations.restauration`).
- **Non supprimables** : dossiers clôturés, rejetés, archivés, avec réponse envoyée, portant un
  document officiel (réponse au client, preuve d’envoi) ou référencés par un autre dossier.
- Opérations concernées : simples références, conservées avec leur association (rien n’est
  écrit dans ORION ni dans la comptabilité) ; pièces jointes et historique conservés.

Tests : `test_reclamations_notes_suppression.py` (notes multiples sans écrasement, consultation
selon permissions, suppression / restauration, refus sans permission, dossier clôturé ou
officiel, opérations jamais supprimées, cohérence des pièces).

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

- Nomenclature des types, motifs et sous-motifs (types et motifs insérés = proposition ; aucun
  sous-motif n’est inséré).
- Preuve d’envoi de la réponse : désormais facultative pour clôturer.
- Permissions devenues sans usage mais conservées au catalogue : `reclamations.suspend`,
  `reclamations.response.prepare`, `reclamations.response.validate`, `reclamations.audit.view`.
- Canal « Papier » renommé « Dépôt physique (agence / siège) ».
- Date de réclamation connue sans heure : enregistrée comme date seule ; la réception par la
  banque, horodatée, reste le point de départ des délais.
- Délais par type / motif et leur caractère réglementaire.
- Autorisation d’enregistrer une référence d’enregistrement d’appel.
- Rattachements d’unités à vérifier : « MARKETING ET COMMUNICATION » a été créé comme service
  sous le département « MARKETING & COMMUNICATION » (libellés distincts dans la source Formation).
