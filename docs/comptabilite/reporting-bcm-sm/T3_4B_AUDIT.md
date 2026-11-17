# T3.4-B — Audit initial UI/UX (avant corrections)

**Date :** 16/11/2026 · Branche `feat/reporting-bcm-sm-t3`  
**Base métier :** T3.4-A2 (BAL DET source unique ; COND archives).

## Matrice des écrans

| Écran | Objectif | Attendu | Actuel | Manques | Priorité |
|-------|----------|---------|--------|---------|----------|
| Accueil | Pilotage | Zones claires, KPI réels, progression DET | Dense, KPI sémantique floue | Alignement filtres, labels FR | P1 |
| Campagnes | CRUD | Delete gated, archive, drawer | ⋮ Supprimer toujours visible | Gate delete-check | P0 |
| Nouvelle | Création | bea-mg fields | Inputs nus | Harmonisation | P1 |
| Fiche | Hub | Sections + export fichier | Export sans download | Wire download | P0 |
| Imports | DET seul | Analyse structurée | OK A2 + JSON brut | Preview structurée | P2 |
| BAL DET | Lecture | Filtres, pager, détail | OK basique | Debounce, lien imports | P2 |
| Contrôles | DET interne | Auth CSV, montants | Lien CSV nu | ApiService download | P0 |
| Paramètres | 8 fiches | Propose→confirm caisse | Apply direct | Propose preview | P1 |
| Mapping | Lecture | Pagination totale | Heuristique page | API total | P1 |
| Archives COND | Lecture | Bandeau | OK hors menu | Lien fiche si historique | P2 |

## Top-10 corrections T3.4-B

1. Gate delete/archive menu campagnes sur delete-check  
2. Download Excel après export  
3. CSV contrôles via ApiService  
4. Propose caisse_devises avant apply  
5. Harmoniser nouvelle campagne + params (`bea-mg__field`)  
6. Mapping pagination avec total  
7. Accueil KPI / labels FR  
8. Imports preview structurée  
9. Progression contrôles plus honnête  
10. Styles / animations / responsive partagés  

## Référence design

Composants `bea-mg` / `bea-fx` (Formation, Stock) — pas de nouveau design system.

---

**Note T3.4-C :** terminologie métier **SM / Situation Mensuelle** (plus de « Campagne » visible). Voir `T3_4C_REPORT.md`.
