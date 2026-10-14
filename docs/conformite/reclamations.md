# Module Gestion des réclamations (`reclamations`)

Espace **Audit, Contrôle & Conformité** → domaine **Management & Qualité**.
Code `reclamations`, URLs front `/reclamations/...`, API `/api/v1/reclamations/...`,
statut CORE `actif`.

## Décisions métier validées

| Sujet | Décision |
|-------|----------|
| Pilotage | Service Réclamations central (unité `est_service_reclamations`, une seule active) |
| Clôture | Service Réclamations central uniquement (403 `CLOTURE_RESERVEE_SR` sinon), après retour jugé suffisant du service concerné (ou traitement interne SR) et enregistrement de la réponse envoyée au client (409 `REPONSE_NON_ENVOYEE` sinon). La preuve d’envoi est facultative (à valider) |
| Délais | Règles configurables (voir « Délais & alertes »), **aucune règle initiale**. Seule une règle validée par la Conformité calcule une échéance ; sinon le dossier affiche « Délai non configuré » ou « En attente de validation » |
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
| `GET/POST/PATCH /regles-delai`, `POST …/validation`, `POST …/versions`, `GET …/historique`, `POST /delais/appliquer`, `GET/POST/DELETE /jours-feries` | Délais et calendrier |
| `POST /referentiels/{id}/validation` | Validation Conformité d’un type, motif ou sous-motif |
| `GET /alertes`, `GET /tableau-de-bord`, `GET /comparaison`, `GET /circuit` | Pilotage, comparaison A/B, kanban |
| `GET /export`, `GET /export/pilotage`, `GET /export/comparaison` | PDF / Excel (liste : 5 000 lignes max) |

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

## Délais & alertes (migration `20261014_reclamations_05`)

Aucune nouvelle table : `reclamation_regles_delai` et `reclamations` sont complétées.

**Règle de délai** : libellé, type, motif, **sous-motif**, priorité, durée, unité (jours
calendaires, jours ouvrés, **heures**), point de départ (première réception banque / réception
SR), **point d’arrivée** (clôture / réponse au client), seuil d’alerte et délai du service (dans
l’unité de la règle), **destinataires des alertes** (SR, service de traitement, gestionnaire ;
défaut SR + service), date d’effet, date de fin, statut de validation, commentaire / source,
actif. Une **nouvelle version** (`remplace_id`) porte une date d’effet postérieure ; à sa
validation, l’ancienne version est bornée à la veille. Une règle déjà appliquée à des dossiers
ne voit plus ses paramètres de calcul modifiés (409 `REGLE_UTILISEE`) : on crée une version.
Toute création ou modification d’un paramètre de calcul remet la règle « À valider ».

**Sélection** (`services/reclamations/echeances.py`, service unique) :

1. seules les règles **validées**, actives et en vigueur à la date de départ s’appliquent ;
2. spécificité : sous-motif 8 + motif 4 + type 2 + priorité 1 (règle générale = 0) ;
3. au meilleur score, des paramètres différents = **conflit** : aucune échéance (`CONFLIT`),
   jamais d’arbitrage silencieux ; la validation d’une règle en conflit est refusée
   (409 `REGLE_CONFLIT`) ;
4. sinon la date d’effet la plus récente l’emporte.

**État du calcul** (`reclamations.etat_delai`) : `CALCULE`, `NON_CONFIGURE` (« Délai non
configuré »), `EN_ATTENTE_VALIDATION` (une règle correspond mais n’est pas validée : aucune
échéance n’est inventée), `CONFLIT`, `SANS_DEPART` (départ « réception SR » pas encore connu ;
recalcul automatique quand la date arrive).

**Situation** : dans le délai, échéance proche (seuil d’alerte atteint), en retard, délai
respecté, délai dépassé (dossiers terminés : fin du délai comparée à l’échéance), non calculable.
**Suspendu : non implémenté** — le circuit actuel n’a pas de statut de suspension (retiré en
phase 3) ; `neutraliser_suspension` est conservé mais sans effet.

**Calendrier** : jours ouvrés = lundi → vendredi hors jours fériés saisis ; échéance en jours =
fin de journée (23:59:59) ; heures = heures calendaires (heures ouvrées : non implémenté).

**Pas de recalcul silencieux** : l’échéance est figée (`echeance_initiale`) ; une nouvelle règle
validée ne touche aux dossiers ouverts sans délai que par l’action explicite
« Appliquer aux dossiers sans délai » (`POST /delais/appliquer`, événement `DELAI_CALCULE` + audit).

**Alertes** : le job quotidien notifie au changement de niveau seulement (`niveau_alerte` :
`PROCHE` puis `RETARD`, `alerte_notifiee_le`) — jamais deux fois le même niveau ; une
réouverture remet le niveau à zéro.

Écran `/reclamations/delais` : compteurs (retard, échéance proche, ouverts sans délai par état),
listes, règles (portée, spécificité, mesure, alerte, période, validation, état effectif —
appliquée, programmée, en attente, rejetée, inactive, expirée —, nombre de dossiers, conflits),
historique (versions + journal d’audit), nouvelle version, validation / rejet, jours fériés.

## Indicateurs de pilotage (`services/reclamations/indicateurs.py`)

Calcul serveur, dans le périmètre de l’utilisateur, avec les filtres de la page (agence, y compris
« sans agence » = `client_agence_id=AUCUNE`). La période s’applique à la date de l’**événement
mesuré** (fin du délai, clôture, réouverture, transmission, retour). Comptes en dossiers
distincts ; durées en heures calendaires (affichées en jours = heures ÷ 24).

| Délai | Mesure | Unité de compte |
|---|---|---|
| Prise en charge | première réception banque → réception SR | dossier |
| Traitement du service | transmission au service → retour au SR (`transmis_le` → `retour_le` ; la réception par le service n’est pas toujours saisie) | fiche de traitement (un renvoi = une fiche de plus) |
| Réponse au client | retour du service reçu par le SR → envoi de la réponse | dossier |
| Clôture | première réception → clôture | dossier clôturé |

Pour chaque délai : moyenne des **terminés** (fin dans la période, n affiché), **en cours**
(départ dans la période, fin absente, dossier ouvert ; âge moyen), **anomalies** (durée négative :
exclue de la moyenne, comptée et listée). Sans donnée : « N/A », jamais 0.

**Taux de réouverture** = dossiers clôturés pendant la période puis réouverts pendant la période
÷ dossiers clôturés pendant la période × 100 (N/A si aucun dossier clôturé). Compté depuis la
chronologie (un dossier réouvert n’a plus de date de clôture). Sont aussi affichés le nombre de
réouvertures et les dossiers réouverts plusieurs fois.

**Services** : affectés (flux, transmissions de la période), retournés (flux, retours de la
période, délai moyen transmission → retour), en cours (stock actuel, âge moyen), en retard
(stock dont l’échéance du service est dépassée).

**KPI cliquables** : chaque compte ouvre `/reclamations/dossiers` avec le filtre
`indicateur` (+ `kpi_debut`, `kpi_fin`, `kpi_unite_id`) construit avec **la même condition
SQL** que le calcul ; le total de la liste = le nombre affiché. Liens du tableau de bord
fournis par le serveur (`liens`) : total, ouvertes, retards, échéance proche, sans délai,
reçues 30 j, délai moyen de clôture, opérations et montant (la liste affiche alors le total des
opérations et du montant). L’agence choisie est conservée dans tous les liens.

## Comparaison de deux périodes

`GET /comparaison?a_debut&a_fin&b_debut&b_fin` (+ filtres), A = référence, B = période
comparée. Indicateurs : reçues, clôturées, opérations, montant, respect de l’échéance, taux de
réouverture, quatre délais moyens. Écart = B − A ; variation = écart ÷ A × 100, **N/A si A = 0** ;
appréciation favorable / défavorable seulement si le sens est défini (clôturées et respect :
hausse favorable ; réouverture et délais : baisse favorable ; volumes et montant : sens non
défini). Dates obligatoires et cohérentes (`PERIODE_INCOMPLETE`, `PERIODE_INVALIDE`),
avertissement si les durées diffèrent ou si les périodes se chevauchent. Disponible dans le
tableau de bord et les rapports ; valeurs cliquables vers la liste de chaque période.

## Exports

- `GET /export` (liste filtrée, PDF / Excel) : ajoute la colonne « Situation du délai » et
  rappelle les filtres (agence, indicateur) en sous-titre.
- `GET /export/pilotage` (PDF / Excel : synthèse, délais, services, réouverture, agences) —
  mêmes fonctions que l’écran.
- `GET /export/comparaison` (PDF / Excel : comparaison + méthode).

## Types, motifs et sous-motifs : proposé / validé

`reclamation_referentiels.statut_validation` (`PROPOSEE` par défaut, `VALIDEE`), `valide_par_id`,
`valide_le`. Validation par `reclamations.references.validate` (rôle admin seulement ; à
attribuer à la Conformité via CORE ADMIN) : `POST /referentiels/{id}/validation`. Un enfant ne se
valide pas avant son parent (`PARENT_NON_VALIDE`) ; un parent ne repasse pas en proposé si des
enfants sont validés (`ENFANTS_VALIDES`) ; modifier le libellé d’une valeur validée la remet en
proposé. Les valeurs proposées restent utilisables (signalées « proposé » à la saisie). Désactiver
n’efface rien : l’historique des dossiers conserve la valeur. Un sous-motif d’un autre motif est
refusé (`CLASSEMENT_INCOHERENT`), y compris dans les règles de délai.

## Permissions retirées

`reclamations.suspend`, `reclamations.response.prepare`, `reclamations.response.validate`,
`reclamations.audit.view` : retirées du catalogue et supprimées de `permissions` par la migration
05 (cascade sur les attributions ; la descente les réinsère). Traçabilité conservée : la
chronologie (`reclamation_evenements`, append-only) et `audit_logs` ne sont pas touchés ; le
journal reste lisible dans l’onglet Historique de chaque fiche. Le module compte 29 permissions.

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
| Règles de délai (CRUD, sous-motif, heures, arrivée, destinataires, versions, historique, conflits) | implémenté et testé |
| Service central de calcul, états et situations, jours ouvrés / fériés, alertes sans doublon | implémenté et testé |
| Quatre délais, réouverture, performance des services, filtre agence (dont « sans agence ») | implémenté et testé |
| KPI cliquables = listes exactes ; totaux opérations / montant de la liste | implémenté et testé |
| Comparaison A/B, exports pilotage et comparaison | implémenté et testé |
| Référentiels proposés / validés, compatibilité sous-motif | implémenté et testé |
| Retrait des 4 permissions | implémenté et testé |
| Durées des délais et leur caractère réglementaire | en attente de validation (Conformité) |
| Nomenclature types / motifs / sous-motifs | en attente de validation (aucune valeur validée ; aucun sous-motif inséré) |
| Référence d’enregistrement d’appel | en attente de décision (désactivée) |
| Unités Marketing | en attente de décision (non déplacées) |
| État « suspendu » | non implémenté (pas de suspension dans le circuit) |
| Heures ouvrées | non implémenté (heures calendaires) |
| Écrans front | vérifiés par build ; pas de tests automatisés front |

Tests : `test_reclamations_finalisation.py` (cycle de vie des règles et versions ; sélection,
spécificité, attente, conflit ; calendrier ; quatre délais avec dates présentes, absentes et
incohérentes ; alertes sans doublon ; réouvertures simple et multiple ; services et opérations
multiples ; filtre agence ; KPI = listes ; comparaison et exports ; permissions retirées ;
référentiels ; Marketing ; appels ; périmètre) en plus des fichiers précédents — transactions
annulées.

## En attente de la Conformité / du métier

- Durées de délai par type / motif / sous-motif et leur caractère réglementaire : aucune règle
  n’est créée par le module.
- Validation de la nomenclature (types, motifs, sous-motifs).
- Preuve d’envoi de la réponse : facultative pour clôturer.
- Canal « Papier » renommé « Dépôt physique (agence / siège) ».
- Date de réclamation connue sans heure : enregistrée comme date seule ; la réception par la
  banque, horodatée, reste le point de départ des délais.
- Autorisation d’enregistrer une référence d’enregistrement d’appel.
- Unités « MARKETING & COMMUNICATION » / « MARKETING ET COMMUNICATION » (voir ci-dessus).
- Besoin éventuel d’une suspension des délais et d’heures ouvrées.

Le module n’est **pas** déclaré validé par la Conformité tant que ces décisions ne sont pas prises.
