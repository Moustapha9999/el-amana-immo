# Conception technique — Moyens Généraux Phase 2

Modules CDC hors Stock : Achats, Notes de frais, Contrats, Archives.

## Achats & Approvisionnements (`achats-appro`)

| Élément | Valeur |
|---------|--------|
| Entry | `/achats-appro/bons` |
| API | `/api/v1/mg/achats/...` |
| Tables | `mg_bons_commande`, `mg_bc_lignes` |
| Permissions | `mg.purchase.view\|create\|approve\|export` |

Fiche papier : Bon de commande (fournisseur, lignes qty×PU, total HT, Visa Chef MG + Directrice Ressources).

Workflow : `BROUILLON → SOUMIS → VISA_MG → VISA_DR → VALIDE` (+ REJETEE / ANNULEE).

Référentiel `fournisseurs` (sélection) + snapshot figé sur le BC.

## Notes de frais (`notes-frais`)

| Élément | Valeur |
|---------|--------|
| Entry | `/notes-frais/notes` |
| API | `/api/v1/mg/notes-frais/...` |
| Tables | `mg_notes_frais`, `mg_note_frais_lignes` |
| Permissions | `mg.notes.view\|create\|approve\|export` |

Fiche papier : date / description / motif / montant MRU / mode règlement + visas MG / DR.

## Contrats & Échéances (`contrats-echeances`)

| Élément | Valeur |
|---------|--------|
| Entry | `/contrats-echeances/liste` |
| API | `/api/v1/mg/contrats/...` |
| Table | `mg_contrats` |
| Permissions | `mg.contrats.view\|create\|manage\|export` |

Alertes : `prochain_echeance` / `date_fin` dans la fenêtre `alerte_jours`.

## Archives MG (`archives-mg`)

| Élément | Valeur |
|---------|--------|
| Entry | `/archives-mg/registre` |
| API | `/api/v1/mg/archives/...` |
| Source | `ged_documents` (`espace_code=moyens-generaux`) |
| Permissions | `mg.archives.view\|export` |

Vue centralisée des pièces des modules MG (pas de suppression physique Phase 2).
