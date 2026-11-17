# T3.4 — Rapport UI/UX et complétude CRUD

**Date :** 16/11/2026  
**Branche :** `feat/reporting-bcm-sm-t3`  
**HEAD de base :** `091b57c` (aucun commit)  
**Prod :** intacte · Mapping : 242 `A_VALIDER` · ECART off

## 1. Audit

Voir `T3_4_AUDIT_UI.md` (matrice écrans).

## 2. Pages réorganisées

| Route | Fonction |
|-------|----------|
| `/accueil` | Dashboard 6 zones |
| `/campagnes` | Liste + menu ⋮ + drawer + delete-check |
| `/campagnes/nouvelle` | Création |
| `/campagnes/:id` | Hub fiche (liens métier, historique, archive/delete) |
| `/imports` | Imports DET/COND + wizard |
| `/bal-det` | Lignes DET paginées |
| `/bal-cond` | Soldes COND paginés |
| `/rapprochement` | Résumé / graphiques / écarts |
| `/parametres` | 8 paramètres + drawer historique |
| `/mapping` | Stats lifecycle + liste paginée (lecture) |

## 3. Composants créés / modifiés

- `rbcm-ui.component.ts`, `rbcm-context.service.ts`, `rbcm-campaign-picker.component.ts`
- Pages listées ci-dessus
- Backend : `delete-check`, `archive`, `/imports`, `cond-lines`, `mapping/summary`, dashboard enrichi

## 4. CRUD campagnes / suppression

| Opération | Comportement |
|-----------|--------------|
| Create | Formulaire + confirmation |
| Read | Liste, drawer, fiche |
| Update | Notes via motif |
| Delete | Uniquement si `delete-check.can_delete` ; sinon messages dépendances |
| Archive | → `CLOTUREE` (données conservées) |
| Reopen | Motif obligatoire, nouvelle version |

## 5. Mini-pages / drawers

Campagne, import, anomalie, paramètre, règle mapping.

## 6. Graphiques / animations

Donut + barres SVG ; fade cartes ; `prefers-reduced-motion`.

## 7. Pagination

Campagnes, imports, DET, COND, mapping — backend.

## 8. Tests

- Nav/routes T3.4 (spec front)
- Messages suppression documentés (pytest)
- Suite RBCM existante

## 9. Problèmes restants

- Import réel oct. 2026 non rejoué ici
- Lien GED natif non systématisé
- Pas de captures avant/après automatisées
- Validation métier mapping (D01) hors scope

## 10. Git

Branche `feat/reporting-bcm-sm-t3` — **pas de commit / push**.
