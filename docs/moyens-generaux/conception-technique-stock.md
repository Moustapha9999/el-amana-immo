# Conception technique — Stock & Fournitures (Phase 1)

## Identifiants catalogue

| Élément | Code |
|---------|------|
| Espace | `moyens-generaux` |
| Module | `stock-fournitures` |
| Entry path | `/stock-fournitures/dashboard` |
| API | `/api/v1/mg/stock/...` |

## Tables (`mg_*`)

| Table | Rôle |
|-------|------|
| `mg_article_familles` | code, libelle (économat, papeterie, pre_imprime, conso_gab, …) |
| `mg_articles` | code unique, designation, famille_id, uom, stock_actuel, stock_min, stock_max, agence_id, emplacement, is_active |
| `mg_stock_mouvements` | type ENTREE/SORTIE/AJUSTEMENT/INVENTAIRE, article_id, quantite, agence_id, user_id, motif, source_type, source_id, date |
| `mg_demandes_fourniture` | reference, date, agence_id (+ snapshot), departement, demandeur_id, fonction, statut, visas |
| `mg_demande_fourniture_lignes` | demande_id, article_id nullable, designation, qty_demandee, qty_accordee |
| `mg_inventaires` / `mg_inventaire_lignes` | campagnes de comptage (théorique / physique / écart) |
| `mg_stock_parametres` | préfixes numérotation, flags alertes |

Stock temps réel : solde dénormalisé `mg_articles.stock_actuel` mis à jour dans la même transaction que chaque mouvement.

## Workflow demande

```text
BROUILLON → SOUMIS → VISA_AGENCE → VISA_MG → ACCORDEE
  → mouvements SORTIE (qty accordée) → CLOTUREE
(+ REJETEE | ANNULEE)
```

## Permissions

`mg.stock.view`, `mg.stock.create`, `mg.stock.entry`, `mg.stock.exit`, `mg.stock.adjust`, `mg.stock.inventory`, `mg.stock.approve`, `mg.stock.export`

Rôles module : `stock-fournitures.lecteur`, `stock-fournitures.magasinier`, `stock-fournitures.valideur`, `stock-fournitures.admin`.

## Écrans

| Route | Contenu |
|-------|---------|
| `/stock-fournitures/dashboard` | KPI + charts conso / alertes stock bas (filtres agence/famille) |
| `/stock-fournitures/articles` | Référentiel articles / familles |
| `/stock-fournitures/stock` | État du stock temps réel |
| `/stock-fournitures/entrees` | Entrées de stock |
| `/stock-fournitures/sorties` | Sorties de stock |
| `/stock-fournitures/mouvements` / `journal` | Journal entrées/sorties |
| `/stock-fournitures/demandes` | Expression de besoin (fiche digitalisée) |
| `/stock-fournitures/inventaires` | Campagnes d’inventaire (comptage / clôture) |
| `/stock-fournitures/alertes` | Stock faible / épuisé |
| `/stock-fournitures/rapports` | Conso mensuelle / annuelle / agence — JSON / CSV / Excel / PDF |
| `/stock-fournitures/parametres` | Familles + préfixes numérotation |

## Mapping fiche papier → UI

Expression de besoin : demandeur, tableau désignation / qty demandée / qty accordée, Visa Agence + Visa MG.
