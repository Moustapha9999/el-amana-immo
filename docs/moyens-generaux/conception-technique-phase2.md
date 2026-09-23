# Conception technique — Moyens Généraux Phase 2

Modules CDC hors Stock : Achats, Notes de frais, Contrats, Archives.

## Achats & Approvisionnements (`achats-appro`)

| Élément | Valeur |
|---------|--------|
| Entry | `/achats-appro/dashboard` |
| API | `/api/v1/mg/achats/...` |
| Tables | `mg_bons_commande`, `mg_bc_lignes`, `mg_achat_demandes`, `mg_achat_consultations`, `mg_achat_devis`, `mg_achat_comparaisons`, `mg_achat_bl`, `mg_achat_receptions`, `mg_achat_factures`, `mg_achat_paiements`, `mg_achat_parametres` |
| Permissions | `mg.purchase.view\|create\|approve\|export\|receive\|invoice\|pay\|demande` |
| Rôles CORE | `achats-appro.lecteur\|acheteur\|valideur\|admin` (+ GED pour admin) |

Cycle : demande → consultation → devis → comparaison (choix humain) → bon de commande → BL → réception (lignes stockables via `MgStockService.record_achat_reception`) → facture (contrôle 3 voies) → suivi de paiement (aucun virement).

Workflow BC : `BROUILLON → SOUMIS → VISA_MG → VISA_DR → VALIDE` puis `ENVOYE` / `PARTIEL` / `RECU` (+ REJETEE / ANNULEE). Soft-delete BC ; édition hors `CLOTURE`.

PDF BC : signataires dynamiques (query `signataire_1` / `signataire_2`), fichier `Bon-Commande-00XXXX.pdf`, totaux HT/TVA/TTC (taux `tva_defaut`).

Référentiel `fournisseurs` (sélection) + snapshot figé sur le BC. Paramètres CRUD (`tva_defaut`, préfixes, devise…) dans `mg_achat_parametres` / UI `/achats-appro/parametres`.

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
