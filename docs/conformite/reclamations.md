# Module Gestion des réclamations (`reclamations`)

Espace **Audit, Contrôle & Conformité** → domaine **Management & Qualité**.
Code `reclamations`, URLs front `/reclamations/...`, API `/api/v1/reclamations/...`,
statut CORE `actif`.

## Décisions métier validées

| Sujet | Décision |
|-------|----------|
| Pilotage | Service Réclamations central (unité `est_service_reclamations`, une seule active) |
| Clôture | Service Réclamations central uniquement (403 `CLOTURE_RESERVEE_SR` sinon), après retour jugé suffisant du service concerné (ou traitement interne SR). Résultat choisi à la clôture. Plus d’action « Qualifier » ni « Enregistrer la réponse envoyée » dans l’interface : le type se renseigne à la saisie ou via « Corriger les données » ; la réponse au client et sa preuve se joignent en pièces jointes |
| Délais | Fonctionnalité « Délais & alertes » retirée (voir plus bas) : aucune échéance ni alerte |
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
| `reclamation_regles_delai` | Règles de délai (type / motif / priorité, jours calendaires ou ouvrés, point de départ, seuil d’alerte, délai service, neutralisation des suspensions, validation Conformité) — conservée en base, plus utilisée depuis la migration 07 |
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

Table `reclamation_operations` (1-N) : référence (obligatoire), montant en MRU (> 0, 2 décimales),
ordre. L’ancienne opération unique (`operation_reference` / `montant_conteste`) est reprise comme
première ligne. Liste, pipeline, fiche et export affichent le nombre d’opérations et le montant
total. Les indicateurs comptent des **dossiers** ; les montants sont sommés par opération, chaque
opération une seule fois.

### Dossier multi-comptes / multi-clients (migration `20261015_reclamations_09`)

Un dossier (numéro, motif général, responsable, statut global) → clients participants → comptes →
opérations.

- `reclamation_participants` : client **principal** (le client saisi sur le dossier) et clients
  **associés**. Statut `VERIFIE` (présent dans la base clientèle), `A_VERIFIER` (racine inconnue),
  `A_RENSEIGNER` (non fournie).
- `reclamation_comptes` : comptes du dossier, chacun rattaché à un participant ; `VERIFIE` ou
  `A_VERIFIER`. Un compte absent de la base est accepté, jamais considéré comme vérifié.
- `reclamation_operations` : + `participant_id`, `compte_id`, `date_operation`, `montant_conteste`
  (≤ montant ; vide = montant de l’opération), `motif_detail`, `import_id`, `ligne_import`.
- Client vide sur une ligne : titulaire du compte s’il est connu, sinon le client principal.
  Compte appartenant à un autre client que celui indiqué : refusé (`COMPTE_AUTRE_CLIENT`).
- Une même référence peut revenir (autre compte, date, montant) : simple avertissement. Seule une
  ligne strictement identique est refusée (`OPERATION_DOUBLON`).
- Plusieurs clients identifiés = cas exceptionnel : paramètre `regroupement_multi_clients_autorise`
  (activé par la migration ; désactivé → `REGROUPEMENT_NON_AUTORISE`) **et** justification
  obligatoire (`reclamations.justification_regroupement`, `JUSTIFICATION_REGROUPEMENT_OBLIGATOIRE`),
  contrôlés avant toute écriture.
- Sécurité : seuls le périmètre global, l’auteur et les membres des unités en charge (réception,
  service concerné, traitement) voient l’identité des clients associés et leurs comptes. Les autres
  accès au dossier voient ces clients masqués (`****12`, `••••3456`), ne peuvent pas modifier les
  opérations ni ouvrir les fichiers d’import.
- La fiche groupe les opérations par client puis par compte, avec sous-totaux (montant et contesté).

### Import Excel des opérations

Modèle unique (`GET /imports/modele`), une ligne par opération : Identifiant client, Référence du
compte, Référence de l’opération, Date de l’opération, Montant de l’opération, Montant contesté,
Motif détaillé (+ feuille « Consignes », sans donnée fictive). 2 000 lignes au plus.

1. `POST /dossiers/{id}/imports` (fichier `.xlsx` + mode `AJOUT` / `REMPLACEMENT`) : le fichier est
   conservé en GED (catégorie `IMPORT_OPERATIONS`, empreinte SHA-256), l’analyse est stockée dans
   `reclamation_imports` (lignes avec erreurs / avertissements, groupes client → compte, totaux du
   fichier et du dossier après import). **Rien n’est écrit au dossier.**
2. `POST /dossiers/{id}/imports/{iid}/confirmer` (révision + justification si multi-clients) :
   contrôles rejoués sur l’état courant ; refus tant qu’une ligne est en erreur (`IMPORT_ERREURS`).
3. `POST /dossiers/{id}/imports/{iid}/abandonner`. Une nouvelle analyse abandonne la précédente.

Chronologie : `IMPORT_ANALYSE`, `IMPORT_CONFIRME`, `IMPORT_ABANDONNE` ; audit
`reclamations.operations.import.*`.

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

Permissions `reclamations.*` (29) contrôlées côté backend et sur les données.

| Rôle | Contenu |
|------|---------|
| `reclamations.point_reception` | Consultation de son périmètre, enregistrement, pièces |
| `reclamations.agent_traitement` | Traitement des fiches de son unité, pièces |
| `reclamations.responsable_service` | + gestion des affectations de son service, reporting |
| `reclamations.agent_sr` | Tout le périmètre, qualification, affectation, revue des retours, envoi des réponses |
| `reclamations.responsable_sr` | + refus, annulation, clôture, réouverture, archivage, retrait de pièces, export, gestion des unités |
| `reclamations.lecteur` | Consultation sur tout le périmètre, exports |
| `reclamations.admin` | Toutes les permissions du module (dont `references.validate`, `delete`) |

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
| `POST /referentiels/{id}/validation` | Validation Conformité d’un type, motif ou sous-motif |
| `GET /tableau-de-bord`, `GET /comparaison`, `GET /circuit` | Tableau de bord, comparaison A/B, kanban |
| `GET /export`, `GET /export/comparaison` | PDF / Excel (liste : 5 000 lignes max) |

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
- **Suppression définitive, quel que soit le statut** (migration `20261015_reclamations_08`) :
  en cours, clôturé, rejeté, archivé ou déjà à la corbeille. `POST /dossiers/{id}/supprimer`
  exécute `DELETE FROM reclamations` dans une transaction ; fiches de traitement, réponses,
  opérations, appels, métadonnées des pièces et chronologie suivent par `ON DELETE CASCADE`.
  Les documents GED du dossier et ses notifications sont supprimés ; les fichiers sont effacés
  du disque après le commit. Un dossier qui citait le dossier supprimé (doublon, lien) perd
  seulement ce lien. Rien n’est écrit dans ORION.
- La chronologie reste en ajout seul pour un dossier existant (trigger
  `trg_reclamation_evenements_immuable`) ; ses lignes ne disparaissent qu’avec leur dossier.
- Permission `reclamations.delete` (rôle `reclamations.admin`, ou habilitation explicite via CORE
  ADMIN), contrôlée côté serveur avec le périmètre du dossier. Confirmation « Supprimer
  définitivement » côté interface. Trace conservée dans `audit_logs`
  (`reclamations.suppression_definitive` : référence, statut, client, opérations, pièces).
- Corbeille : seuls les dossiers mis à la corbeille avant cette règle y figurent ; ils se
  restaurent (motif obligatoire) ou se suppriment définitivement.

Tests : `test_reclamations_notes_suppression.py` (notes multiples sans écrasement, consultation
selon permissions, suppression définitive en base, refus sans permission, tout statut y compris
archivé, chronologie protégée, corbeille restaurée ou supprimée).

## Délais & alertes : retirés (migration `20261014_reclamations_07`)

La fonctionnalité « Délais & alertes » a été retirée du module à la demande du métier :

- plus de menu, de route `/reclamations/delais`, de page ni de lien Admin ;
- plus de règles de délai, d’échéance, de situation (« en retard », « échéance proche »), de
  calendrier de jours fériés ni d’alerte : routes `/regles-delai`, `/delais/appliquer`,
  `/jours-feries` et `/alertes` supprimées, tâche Celery quotidienne supprimée, aucune échéance
  calculée à l’enregistrement ni à la qualification ;
- liste : plus de colonne « Échéance », ni de filtres « Situation du délai », « Calcul du délai »,
  « En retard » ; fiche : plus d’échéance, de règle ni d’échéance service ;
- tableau de bord et rapports : plus de KPI « En retard », « Échéance proche », « Sans délai », ni
  d’anneau « Respect des délais », ni de listes « Échéance proche » / « Dossiers en retard », ni de
  section « Durées de traitement, réouverture et services » ; la comparaison A/B n’a plus de ligne
  « Respect de l’échéance » ;
- permissions `reclamations.delais.manage` et `reclamations.delais.validate` supprimées du
  catalogue et de la base (attributions supprimées en cascade).

**Données conservées** : les tables `reclamation_regles_delai`, `reclamation_jours_feries` et les
colonnes d’échéance de `reclamations` / `reclamation_affectations` restent en base, inchangées,
mais ne sont plus lues ni alimentées. Les événements historiques `DELAI_CALCULE` restent lisibles
dans la chronologie.

## Indicateurs conservés (`services/reclamations/indicateurs.py`)

Calcul serveur, dans le périmètre de l’utilisateur, avec les filtres de la page (agence, y compris
« sans agence » = `client_agence_id=AUCUNE`). Seul le **délai moyen de clôture** (première
réception → clôture, dossiers clôturés de la période, durée négative exclue) est affiché comme KPI.
Les durées mesurées (prise en charge, traitement du service, réponse au client, clôture) et le
taux de réouverture restent utilisés par la comparaison A/B et par les filtres de liste
(`indicateur` + `kpi_debut` / `kpi_fin` / `kpi_unite_id`, même condition SQL que le calcul).

**KPI cliquables** du tableau de bord (`liens` fournis par le serveur) : total, ouvertes,
reçues 30 j, délai moyen de clôture, opérations et montant. L’agence choisie est conservée.

## Comparaison de deux périodes

`GET /comparaison?a_debut&a_fin&b_debut&b_fin` (+ filtres), A = référence, B = période
comparée. Indicateurs : reçues, clôturées, opérations, montant, taux de réouverture, quatre durées
moyennes. Écart = B − A ; variation = écart ÷ A × 100, **N/A si A = 0** ; appréciation favorable /
défavorable seulement si le sens est défini (clôturées : hausse favorable ; réouverture et durées :
baisse favorable ; volumes et montant : sens non défini). Dates obligatoires et cohérentes
(`PERIODE_INCOMPLETE`, `PERIODE_INVALIDE`), avertissement si les durées diffèrent ou si les
périodes se chevauchent.

## Exports

- `GET /export` (liste filtrée, PDF / Excel) : rappelle les filtres (agence, indicateur) en
  sous-titre.
- `GET /export/comparaison` (PDF / Excel : comparaison + méthode).

## Types, motifs et sous-motifs : proposé / validé

`reclamation_referentiels.statut_validation` (`PROPOSEE` par défaut, `VALIDEE`), `valide_par_id`,
`valide_le`. Validation par `reclamations.references.validate` (rôle admin seulement ; à
attribuer à la Conformité via CORE ADMIN ; créée et rattachée au rôle admin par la migration
`20261014_reclamations_06`) : `POST /referentiels/{id}/validation`. Un enfant ne se
valide pas avant son parent (`PARENT_NON_VALIDE`) ; un parent ne repasse pas en proposé si des
enfants sont validés (`ENFANTS_VALIDES`) ; modifier le libellé d’une valeur validée la remet en
proposé. Les valeurs proposées restent utilisables (signalées « proposé » à la saisie). Désactiver
n’efface rien : l’historique des dossiers conserve la valeur. Un sous-motif d’un autre motif est
refusé (`CLASSEMENT_INCOHERENT`).

**Nomenclature de la banque** (migration `20261015_reclamations_09`, source
`app/data/reclamations_nomenclature.py`) : 26 types (familles A à E, codes `T01` … `T26`) et leurs
motifs (`T01_M01` …). L’ancienne proposition est désactivée (réactivable), pas supprimée.

**Désactiver / supprimer** (Paramètres) :
- Désactiver masque la valeur **et ses descendants** de toutes les listes déroulantes (saisie,
  qualification, filtres) ; une valeur dont un parent est inactif est refusée (`REFERENTIEL_INACTIF`).
  Un dossier qui porte déjà la valeur la conserve (affichée « désactivé » en modification).
- Supprimer (`DELETE /referentiels/{id}`) traite la valeur et ses descendants : effacement définitif
  de ce qui n’a jamais servi ; suppression **logique** (`supprime_le`, masquée partout y compris dans
  Paramètres) de ce qui est porté par un dossier, afin que l’historique garde son libellé. Réponse :
  nombre d’éléments effacés / masqués. Recréer le même libellé restaure la valeur.

## Permissions retirées

`reclamations.suspend`, `reclamations.response.prepare`, `reclamations.response.validate`,
`reclamations.audit.view` : retirées du catalogue et supprimées de `permissions` par la migration
05 (cascade sur les attributions ; la descente les réinsère). Traçabilité conservée : la
chronologie (`reclamation_evenements`, append-only) et `audit_logs` ne sont pas touchés ; le
journal reste lisible dans l’onglet Historique de chaque fiche. `reclamations.delais.manage` et
`reclamations.delais.validate` ont suivi (migration 07). Le module compte 27 permissions.

## Enregistrement des appels

Inchangé : `enregistrement_appels_autorise` absent = refusé. Seule une **référence** externe est
saisissable quand le paramètre est activé ; aucun fichier audio n’est stocké, aucun lien public.

## Marketing (vérification)

Deux unités actives, sans membre ni dossier : département « MARKETING & COMMUNICATION » (racine)
et service « MARKETING ET COMMUNICATION » rattaché à ce département. Ce rattachement reproduit
la source Formation (deux libellés distincts) : **rien n’a été déplacé**. Fusion ou renommage =
décision de la banque.

## Avancement

| Élément | Statut |
|---|---|
| Circuit, fiche, pièces, opérations, corbeille | implémenté et testé |
| Délais & alertes (règles, échéances, alertes, section durées / réouverture / services) | retiré (données conservées en base) |
| Délai moyen de clôture, filtre agence (dont « sans agence ») | implémenté et testé |
| KPI cliquables = listes exactes ; totaux opérations / montant de la liste | implémenté et testé |
| Comparaison A/B, export de la comparaison | implémenté et testé |
| Référentiels proposés / validés, compatibilité sous-motif | implémenté et testé |
| Retrait des 4 permissions | implémenté et testé |
| Nomenclature types / motifs (26 types, liste de la banque) | chargée ; validation Conformité à faire ; aucun sous-motif inséré |
| Désactivation / suppression des types et motifs (masqués des listes) | implémenté et testé |
| Dossier multi-comptes / multi-clients, masquage des clients associés | implémenté et testé |
| Import Excel des opérations (modèle, aperçu, confirmation) | implémenté et testé |
| Référence d’enregistrement d’appel | en attente de décision (désactivée) |
| Unités Marketing | en attente de décision (non déplacées) |
| État « suspendu » | non implémenté (pas de suspension dans le circuit) |
| Écrans front | vérifiés par build ; pas de tests automatisés front |

Tests : `test_reclamations_finalisation.py` (quatre durées avec dates présentes, absentes et
incohérentes ; réouvertures simple et multiple ; services et opérations multiples ; filtre agence ;
KPI = listes et absence des KPI d’échéance ; comparaison et exports ; permissions retirées, dont
`delais.*` ; référentiels ; Marketing ; appels ; périmètre) et `test_reclamations_circuit.py`
(aucune échéance calculée à la création) — transactions annulées.

## En attente de la Conformité / du métier

- Validation de la nomenclature (types, motifs, sous-motifs).
- Preuve d’envoi de la réponse : facultative pour clôturer.
- Canal « Papier » renommé « Dépôt physique (agence / siège) ».
- Date de réclamation connue sans heure : enregistrée comme date seule ; la réception par la
  banque, horodatée, reste le point de départ des durées mesurées.
- Autorisation d’enregistrer une référence d’enregistrement d’appel.
- Unités « MARKETING & COMMUNICATION » / « MARKETING ET COMMUNICATION » (voir ci-dessus).

Le module n’est **pas** déclaré validé par la Conformité tant que ces décisions ne sont pas prises.
