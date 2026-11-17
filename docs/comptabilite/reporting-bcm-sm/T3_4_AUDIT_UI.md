# T3.4-A — Audit UI/UX Reporting BCM SM

**Date :** 16/11/2026 · Branche `feat/reporting-bcm-sm-t3`

## Matrice des écrans

| Écran | Contenu attendu | Contenu actuel (T3.3) | Problèmes | Corrections T3.4 |
|-------|-----------------|------------------------|-----------|------------------|
| Accueil | Dashboard pilotage zones KPI / progression / graphiques / activité / actions | KPI + 4 graphiques + politiques + décisions mélangés | Surchargé, pas de campagne focus, pas d’activité récente structurée | Refonte 6 zones, sélecteur campagne, actions rapides |
| Campagnes | Liste + actions CRUD + drawer sections | Liste + drawer résumé/progression | Pas de menu actions, pas d’édition inline, suppression peu visible, pas de créateur | Menu ⋮, éligibilité suppression, archive, édition notes |
| Nouvelle | Formulaire complet | OK basique | Manque feedback dépendances | Affinage labels / confirmation |
| Fiche campagne | Hub sections + liens | Tout-en-un onglets lourds | Mélange imports/DET/params/reconcile | Hub léger + liens vers vues dédiées |
| Imports | Vue module DET/COND séparés | Uniquement dans fiche | Pas d’entrée nav | Page `/imports` + filtre campagne |
| BAL DET | Table paginée | Onglet fiche | Pas d’entrée nav | Page `/bal-det` |
| BAL COND | Table paginée | Absent | Manquant | Page `/bal-cond` + API |
| Rapprochement | Résumé / graphiques / écarts | Onglet fiche | Pas d’entrée nav | Page `/rapprochement` |
| Paramètres | 8 fiches + CRUD | Onglet fiche | Pas d’entrée nav | Page `/parametres` |
| Mapping | Stats + liste A_VALIDER | Table brute, texte 115 obsolète | Pas de stats, pas de drawer | Stats lifecycle, pagination, drawer lecture |

## Référence design

Formation (`fo-dashboard`) : kicker, KPI cliquables, grille panneaux, listes activité, empty states.

## Décisions UI

- Nav module = Accueil, Campagnes, Imports, BAL DET, BAL COND, Rapprochement, Paramètres, Correspondances.
- Contexte campagne sélectionnée (session) pour les vues données.
- Suppression : backend décide + message explicite des dépendances.
- Archive → `CLOTUREE` avec action `ARCHIVE` (conserve données).
- Aucune activation mapping.
