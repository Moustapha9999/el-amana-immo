# Structure NCG & orientations SM — mécanisme livré (DEV)

Synthèse technique du mécanisme livré en phases 1–6 (novembre 2026).  
**Statut :** prêt pour validation métier Comptabilité sur DEV Docker. **Pas déployé.**

## Objectif

Comparer les BAL DET **par période métier**, détecter les NCG nouveaux / connus / absents / nuls / réapparus, et permettre à la Comptabilité d’orienter un NCG vers une cellule SM **sans activation automatique**.

## Composants

| Couche | Emplacement |
|--------|-------------|
| Catalogue central (89 règles) | `backend/app/services/reporting_bcm_sm/engine/rules_catalog.py` (`ALL_RULES`) |
| Structure / détection | `…/ncg_structure_service.py` |
| Orientations + fusion | `…/ncg_orientation_service.py` (`merge_active_orientations`) |
| Revue Comptabilité | `…/ncg_review_service.py` |
| Moteur | `…/engine/evaluate.py` + `…/engine/runner.py` (catalogue effectif = ALL_RULES ∪ orientations `VALIDE_ACTIF`) |
| Migration | `backend/alembic/versions/20261118_rbcm_06_ncg_orientation.py` |
| UI Structure | `/reporting-bcm-sm/imports` (panneau Structure NCG) |
| UI Revue | `/reporting-bcm-sm/ncg-revue` |

## Statuts d’orientation

`A_ORIENTER` → `EN_ATTENTE_VALIDATION` → `VALIDE_ACTIF` | `REJETE` | `DESACTIVE`

- Création / différé = jamais actif.
- Seul `VALIDE_ACTIF` entre dans le catalogue au calcul.
- Historique conservé (notes de correction, audit, pas de suppression).

## Permissions

- Proposition / correction / différé / soumission : `reporting-bcm-sm.mapping.propose`
- Validation / rejet / désactivation : `reporting-bcm-sm.mapping.validate`
- Séparation des rôles : le soumissionnaire ne peut pas valider sa propre orientation.

## Guides

- Utilisateur : [GUIDE_UTILISATEUR.md](GUIDE_UTILISATEUR.md)
- Test Comptabilité : [GUIDE_TEST_COMPTABILITE_NCG.md](GUIDE_TEST_COMPTABILITE_NCG.md)

## Cas réel octobre 2026

NCG **847000** (Moins-values cession) : détecté `nouveau`, orientation `A_ORIENTER` **sans cellule ni opération** jusqu’à décision Comptabilité.

## Invariants

- Ne pas créer de second catalogue / moteur.
- Ne pas modifier les 89 règles sans décision validée.
- Ne pas injecter d’écart de bilan dans une cellule.
- Ne pas recalculer les SM historiques pour activer une orientation (les orientations actives s’appliquent aux **prochains** calculs).
