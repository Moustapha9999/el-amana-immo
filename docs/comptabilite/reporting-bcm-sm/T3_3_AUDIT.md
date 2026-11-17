# T3.3-A — Audit avant implémentation

**Date :** 16/11/2026  
**Branche :** `feat/reporting-bcm-sm-t3`  
**Commit de base (HEAD distant de départ) :** `091b57c`  
**Alembic DEV :** `20261116_rbcm_01`  
**Mapping DEV :** 242 × `A_VALIDER`, 0 `ACTIVE`

## Déjà présent (réutilisable)

| Couche | Contenu |
|--------|---------|
| Modèles | `rbcm_campaign`, imports, lignes DET, balance NCG, reconcile_issue, paramètres, mapping, calculs, contrôles, validation_event, deliverable |
| Services | campagnes (create/list/patch/reopen/transition), import (upload/analyze/confirm), paramètres (set/list), workflow, moteur, excel_export, mapping_seed |
| API | accueil, campaigns CRUD partiel, imports upload/confirm/list, parameters, mapping rules, calculate, controls, workflow, export |
| Front | accueil, liste campagnes, nouvelle, détail minimal, mapping |
| Charts | SVG maison Formation / Archives (pas de lib chart ajoutée) |
| Feedback | FeedbackService + UiDialogService |

## Bugs / écarts critiques

1. **Parser BAL DET incorrect** : code lit NCG en col 1 ; fichier réel = `NCG,COMPTE,LIBELLE,DEVISE,DEB,CRE` (indices 0–5). Devise ignorée.
2. **UI incomplète** : pas d’assistant d’import, pas de rapprochement, pas de page paramètres, pas de drawers, pas de dashboard KPI/graphiques, pagination front locale limitée.
3. **API** : pas de `page`/`search` unifiés, pas de listing paginé des lignes DET, pas d’endpoint dashboard stats, pas de validate/reject paramètres, pas de soft-delete campagne, reconcile basique sans API détail.
4. **GED** : fichiers stockés sous `upload_root()/reporting-bcm-sm/` — OK ; pas encore de lien `ged_documents` systématique.

## Décisions (pas de blocage structurel)

- P2 UNIQUE version déjà en place — conserver.
- Pas d’activation mapping / ECART en T3.3.
- Tolérance rapprochement : documentée, seuils configurables en code (défaut 1,00 MRU pour alerte « > 1 »).
- Migration additive seulement si label campagne / index pagination nécessaires.

## Plan d’implémentation T3.3

1. Corriger parsers DET/COND + enrichir analyse (devises, NCG, preview).  
2. API dashboard, lignes paginées, reconcile détaillée, params validate/history, archive campagne.  
3. UI complète (dashboard, wizard import, détail/drawer, params, rapprochement, charts SVG).  
4. Tests + rapport.
