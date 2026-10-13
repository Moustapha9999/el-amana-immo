# Vue 360° clientèle — `/clientele/filtrage`

Espace de supervision du module Clientèle : une vue synthétique pour décider, des indicateurs
cliquables pour enquêter, des dossiers détaillés pour agir.

## Principe de lecture seule

- Les résultats SCORE sont présentés **tels qu’enregistrés** (`clientele_classifications`,
  `clientele_classif_historique`, `clientele_classif_evaluations`). Aucun recalcul, aucun
  classement de masse, aucune correction de données depuis cet écran.
- Les contrôles de cohérence sont des **diagnostics** calculés à part (CTE SQL), jamais écrits et
  jamais affichés comme un motif du moteur.
- Le motif affiché est le premier champ enregistré non vide, dans l’ordre
  `motif_decision_manuelle`, `motif_moteur`, `motif_source`, `motif_risque`, `motif_classement`.
  Le champ d’origine est toujours indiqué. Un motif n’est jamais reconstitué.
- Une correspondance de filtrage reste **potentielle** tant qu’un agent habilité n’a pas pris une
  décision tracée. Aucun rapprochement ne fusionne des clients : un client = une racine ORION.

## Sections (paramètre d’URL `?vue=`)

| `vue` | Section |
|---|---|
| `synthese` (défaut) | Vue 360° : KPI, répartitions, contrôles, activité, historique |
| `profilage` | Profilage & classification : liste paginée des clients filtrés |
| `filtrage` | Filtrage réglementaire : catégories, dernier filtrage, codes ORION, correspondances |
| `listes` | Listes d’interdiction : listes, entrées paginées, ajout tracé |
| `alertes` | Centre d’alertes : file paginée, attribution, accès au dossier `/clientele/filtrage/:id` |
| `recherche` | Recherche transversale et fiche client 360° |
| `journal` | Historique & audit (profils de supervision) |

Tous les filtres sont portés par l’URL : un KPI ouvre la liste déjà filtrée et le lien est partageable.

## Unités et périodes

- **Client** : racine ORION distincte (`clientele_situation`). **Alerte** : ligne `clientele_alertes`.
  **Événement** : ligne d’historique ou d’audit. Ces unités ne s’additionnent jamais.
- **Stock** (clients, niveaux, alertes ouvertes) : à la date de consultation.
  **Flux** (alertes créées, décisions, classifications) : sur la période choisie, comparés à la
  période précédente de même durée, immédiatement antérieure.
- Périodes : aujourd’hui, 7 jours, 30 jours (défaut), trimestre en cours, année en cours,
  personnalisée (10 ans maximum). Fuseau Africa/Nouakchott = UTC+0 : jours UTC.
- États distincts à l’écran : chargement (`—`), erreur de chargement (message + référence de
  requête + Réessayer), zéro résultat (`0` / « zéro résultat »), donnée non définie (« Non défini »).

## Définitions des KPI

| KPI | Définition |
|---|---|
| Clients | Racines distinctes de la population filtrée ; PP + PM + non identifiés = total |
| Profil PP / PM | `profil_derive` de `clientele_situation` (heuristique ORION) |
| Niveau de risque | Niveau enregistré ; sans classification → « Non évalué », jamais Faible. Somme des niveaux = total clients |
| Classification enregistrée | Clients ayant une ligne `clientele_classifications` |
| Non profilé | Clients sans classification enregistrée |
| Bloqué (à arbitrer) | Non profilé dont la dernière évaluation est `A_ARBITRER` |
| Résultat à vérifier | Clients ayant au moins un contrôle de la famille COHÉRENCE en écart |
| Données incomplètes | Clients ayant au moins un contrôle de la famille DONNÉES en écart |
| Clients avec / sans correspondance | Clients ayant au moins une alerte (tous statuts) / aucune ; somme = total |
| Alertes ouvertes | Alertes `NOUVELLE`, `A_ANALYSER`, `EN_INVESTIGATION` des clients de la population |
| Non attribuées | Alertes ouvertes sans `assignee_id` |
| Ancienneté | Âge des alertes ouvertes : 0–7, 8–30, 31–90, > 90 jours |
| Priorité, délai cible | **Non défini** : aucune règle de priorité ni SLA dans le référentiel |
| Alertes créées / décisions | Alertes créées sur la période / événements de décision sur la période |
| Classifications enregistrées | Lignes d’historique de classification sur la période |
| Premières classifications | Lignes sans classe antérieure |
| Changements de classe | Lignes avec classe antérieure renseignée et différente |

## Regroupements de statuts d’alerte (affichage seulement)

| Groupe | Statuts du workflow |
|---|---|
| Correspondance potentielle à examiner | `NOUVELLE`, `A_ANALYSER` |
| En cours d’analyse | `EN_INVESTIGATION` |
| Correspondance confirmée | `CONFIRMEE` |
| Écartée après examen | `FAUX_POSITIF`, `REJETEE` |
| Clôturée | `CLOTUREE` |

Aucun statut n’a été créé.

## Contrôles (diagnostics)

Définitions dans `backend/app/services/clientele/vue360.py` (`ANOMALIES`), reprises à l’écran :

- **Profilage** : sans classification enregistrée ; évaluation bloquée (conflit de référentiel).
- **Cohérence** : plusieurs critères à 100 000 points ; niveau différent des seuils CDC
  (< 10 000 Faible, < 100 000 Moyen, ≥ 100 000 Élevé, INTERDIT exclu) ; Liste d’interdiction ORION
  comptée alors que le critère est SUSPENDU ; classe retenue ≠ dernière évaluation ; scores
  différents sous la même version de règles ; réexamen ouvert.
- **Données** : sans identifiant exploitable ; nationalité vide ; profil PP / PM non identifié.

Un contrôle en écart signale un point à vérifier. Il ne corrige rien et ne vaut pas décision.

## Permissions

| Action | Permission backend |
|---|---|
| Accès à l’espace, synthèse, listes, fiche 360° | `clientele.filtrage.view` |
| Niveaux, scores, motifs, contrôles de cohérence | `clientele.classif.view` (sinon masqués, filtres correspondants ignorés côté serveur) |
| Lancer le filtrage, ajouter une entrée de liste | `clientele.filtrage.execute` |
| Attribuer, commenter, décider une alerte | `clientele.filtrage.decide` |
| Journal d’audit | `clientele.admin`, `clientele.classif.admin` ou `clientele.filtrage.decide` |
| Export Excel | `clientele.export` |

## Audit

Actions tracées dans `audit_logs` (module `clientele`) : consultation de fiche
(`clientele.client.view`), attribution (`clientele.filtrage.attribution`, avant / après),
commentaire (`clientele.filtrage.commentaire`), décision (`clientele.filtrage.decision`, avant / après),
dépôt de justificatif (`clientele.filtrage.justificatif`),
filtrage (`clientele.filtrage.scan`), ajout d’entrée de liste (`clientele.filtrage.liste_entree`),
export (`clientele.vue360.export`). Confirmer, écarter ou clôturer une alerte exige une justification.
Le journal affiché n’expose pas les valeurs avant / après (données personnelles).

## API (`/api/v1/clientele`)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/vue360/synthese` | KPI et répartitions de la population filtrée |
| GET | `/vue360/clients` | Liste paginée (`page`, `taille`, `tri`) cohérente avec les KPI |
| GET | `/vue360/clients/{racine}` | Fiche 360° (lecture seule, consultation auditée) |
| GET | `/vue360/journal` | Journal d’audit paginé |
| GET | `/vue360/export.xlsx` | Export : synthèse (filtres, période, auteur, date, limites), contrôles, clients (50 000 lignes max) |
| GET | `/filtrage/alertes` | File d’alertes ; accepte les filtres de population de la vue 360° |
| GET | `/filtrage/agents` | Agents habilités à recevoir une alerte |
| POST | `/filtrage/alertes/{id}/attribuer` | Attribution tracée |
| POST | `/filtrage/alertes/{id}/commentaires` | Commentaire tracé |

Filtres communs : `periode`, `du`, `au`, `profil`, `agence`, `niveau`, `profilage`, `filtrage`,
`anomalie`, `coherence`, `completude`, `q`, `classe_periode`.

## Limites connues

- Pas d’export PDF de la vue 360° (Excel uniquement).
- Priorité et délai cible des alertes non définis : à fixer par la Conformité avant affichage.
- Aucun journal d’import des listes d’interdiction : la date de mise à jour d’une liste n’est pas prouvable.
- Codes du champ ORION « Liste d’interdiction » non documentés : affichés bruts.
