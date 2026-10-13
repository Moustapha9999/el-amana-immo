# Module Gestion des réclamations (`reclamations`)

Espace **Audit, Contrôle & Conformité** → domaine **Management & Qualité**.
Code `reclamations`, URLs front `/reclamations/...`, API `/api/v1/reclamations/...`,
statut CORE `developpement` (l’ouverture reste une décision CORE ADMIN).

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

## Avancement

| Phase | Contenu | État |
|-------|---------|------|
| 1 | Schéma, catalogue CORE, profils, périmètre, `GET /config`, routes et navigation (écrans « en construction ») | fait |
| 2 | Référentiels, unités et membres, création, liste paginée, fiche à onglets, pièces GED | à faire |
| 3 | Moteur de workflow, espace service « À traiter », réponses client, clôture | à faire |
| 4 | Délais, alertes, notifications (job de fond) | à faire |
| 5 | Tableau de bord 360°, rapports PDF / Excel | à faire |
| 6 | Tests de bout en bout, finition | à faire |

## En attente de la Conformité / du métier

- Nomenclature des types, motifs et sous-motifs (les 9 types insérés sont une proposition).
- Délais par type / motif et leur caractère réglementaire.
- Autorisation d’enregistrer une référence d’enregistrement d’appel.
- Rattachements d’unités à vérifier : « MARKETING ET COMMUNICATION » a été créé comme service
  sous le département « MARKETING & COMMUNICATION » (libellés distincts dans la source Formation).
