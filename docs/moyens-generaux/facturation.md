# Gestion des factures — Contrats & échéances

Sous-module de `contrats-echeances` (espace `moyens-generaux`). Factures des agences, sièges,
PDV Amanty, SOMELEC et autres fournisseurs : réception, contrôle, validation, paiements,
pièces justificatives, échéances, alertes, analyses et rapports.

## Réutilisation de l'existant (analyse des tables `mg_*`)

| Besoin | Table utilisée | Décision |
|--------|----------------|----------|
| Facture | `mg_achat_factures` | Registre unique. Colonne `origine` = `ACHAT` (module Achats, inchangé) ou `FACTURATION`. Achats filtre `origine = 'ACHAT'`. |
| Lignes | `mg_achat_facture_lignes` | Enrichie (unité, type de ligne). Lignes facultatives. |
| Paiements | `mg_achat_paiements` | Un ou plusieurs par facture. Annulation logique (`statut = ANNULE`, motif). |
| Historique | `mg_achat_evenements` | `entity_type` = `facture` / `point_facturation`. |
| Fournisseurs | `fournisseurs` (référentiel Achats) | Aucun doublon : la saisie des fournisseurs reste dans Achats. |
| Agences | `agences` | Référentiel commun. |
| Contrats | `mg_contrats` | Lien facultatif facture → contrat et point → contrat. |
| Paramètres | `mg_contrat_parametres` | Clés `factures.*`. |
| Documents | `ged_documents` (GED centrale) | Espace `moyens-generaux`, module `contrats-echeances`, entité `facture`. Pas de table de fichiers dédiée. |
| Point de facturation | `mg_points_facturation` | **Seule nouvelle table** : entité métier inexistante (site facturé identifié par sa référence fournisseur, code `PF-00001`). |

Migrations : `backend/alembic/versions/20261005_mg_facturation.py`, puis
`20261005_mg_points_telephone.py` (colonne `telephone` du site, facultative). `montant_ht` / `montant_tva`
deviennent facultatifs : aucun montant n'est inventé. Aucune statistique n'est stockée : tout est
recalculé à la volée.

## Cycle de vie

`BROUILLON → REÇUE → À CONTRÔLER → VALIDÉE → ARCHIVÉE`, exceptions `CONTESTÉE` et `ANNULÉE`
(motif obligatoire). Le statut de paiement (`À payer`, `Partiellement payée`, `Payée`) est calculé
à partir des paiements valides. Une facture validée ne peut plus changer de montant (la contester
d'abord). Suppression : brouillon ou reçue uniquement, et toujours logique. Un point déjà facturé
est désactivé, jamais supprimé.

## Alertes (calculées)

| Type | Règle | Paramètre |
|------|-------|-----------|
| Manquante | Point actif, mensuel, sans facture pour un mois échu depuis le début du suivi | `factures.delai_reception_jours` |
| Échéance proche | Échéance dans N jours, non soldée | `factures.alerte_echeance_jours` |
| Retard | Échéance dépassée, non soldée | — |
| Hausse | Montant ≥ +X % de la moyenne des 6 dernières factures du point | `factures.seuil_hausse_pct` |
| Doublon | Plusieurs factures pour un même point et une même période | — |

## Import Excel SOMELEC

`Points de facturation → Importer` : aperçu, contrôle des doublons (fichier + base), choix
nom / type / agence / inclusion par ligne, puis création des **seuls points nouveaux**. Aucun montant
n'est importé (les montants présents dans le fichier sont signalés puis ignorés).

## Accès

| Élément | Valeur |
|---------|--------|
| Front | `/contrats-echeances/factures` (vue 360°), `/factures/liste`, `/points`, `/paiements`, `/echeances`, `/alertes`, `/analyses`, `/rapports`, `/parametres` |
| Ouverture directe | `/contrats-echeances/factures/liste?facture=<id>`, `/contrats-echeances/factures/points?point=<id>` |
| API | `/api/v1/mg/factures/...`, `/api/v1/mg/points-facturation/...` |
| Permissions | `mg.factures.{view,create,update,delete,validate,archive,export}`, `mg.factures.payment.{view,create,update,delete}`, `mg.factures.documents.{view,create,delete}`, `mg.factures.analytics.view`, `mg.factures.reports.export`, `mg.facturation.manage` |

Les droits sont contrôlés côté backend (le front masque seulement les actions). Un utilisateur
rattaché à une agence qui n'a ni droit de saisie, ni de modification, ni de validation, ni de
paramétrage ne voit que les factures et points de son agence.

## Listes, mini-pages et exports (contrats + factures)

Composants communs dans `frontend/angular20/src/app/contrats-echeances/shared/` :

| Fichier | Rôle |
|---------|------|
| `table-state.ts` | Tri, pagination (10/25/50/100) et composant `bea-pager`. |
| `detail-drawer.component.ts` | Mini-page latérale (`bea-detail-drawer`) : en-tête, KPI, onglets, chargement, erreur + Réessayer, `Échap`. Également la frise d'historique et l'indicateur J-30 / J-15 / J-7 / J-1 / J0 / J+1. |
| `impression.ts` | Impression d'un tableau (fenêtre paysage). |

Les tableaux défilent dans leur propre zone, avec un en-tête fixe. Le bouton « Voir » ouvre la mini-page :

- contrat : Résumé, Informations, Facturation, Échéances, Paiements, Renouvellements, Documents, Historique ;
- échéance ;
- paiement de contrat ;
- facture ;
- paiement de facture.

Une mini-page ouverte depuis une autre se superpose à elle, sans la fermer. Le lien direct est
`/contrats-echeances?voir=<id>`.

Formats de sortie : **PDF, Excel et Imprimer uniquement**. Le CSV est supprimé, et le backend
renvoie `FORMAT_INVALIDE` pour tout autre format. Les exports reprennent les filtres de l'écran :

| Écran | Rapport exporté |
|-------|-----------------|
| Registre | `registre` |
| Échéances | `echeancier` |
| Paiements | `reglements` |

L'audit `contrats.export` enregistre les filtres appliqués.

Les indicateurs du registre sont calculés par le backend (`/mg/contrats/dashboard`) :

- montant annuel : montant TTC ramené à 365 jours de la durée du contrat ;
- montant mensuel ;
- nombre de contrats à renouveler ;
- nombre de contrats qui expirent bientôt.

Un paiement ne peut jamais dépasser le reste dû, que ce soit sur une échéance ou sur une facture. Le
récapitulatif « déjà payé / ce paiement / reste après » est affiché avant validation.

Renouvellements : **aucune nouvelle table**. Une période est déduite :

- des avenants `RECONDUCTION` ;
- du lien `contrat_precedent_id`.

Le statut (À préparer, En cours, Renouvelé, Refusé, Annulé) découle du statut du contrat renouvelé.
Une échéance « Reportée » correspond à un report tracé : la date change et le motif est inscrit dans
le commentaire.

## Limites de cette phase

- Pas de table PDV dédiée : un PDV Amanty est un point de facturation de type `PDV`.
- Pas de table d'échéances séparée : l'échéance est portée par la facture.
- Pas de notifications sortantes pour les alertes de factures (consultation dans l'écran Alertes et la vue 360°).
