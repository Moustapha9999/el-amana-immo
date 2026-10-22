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
BROUILLON → SOUMIS → VISA_AGENCE → PREPARATION → SERVIE → ARCHIVEE
(+ REJETEE | ANNULEE)
```

- `visa_mg` : VISA_AGENCE → PREPARATION (quantités accordées, pas de sortie)
- `servir` : PREPARATION → SERVIE (sorties stock)
- `archiver` : SERVIE → ARCHIVEE

Compat ancienne : `ACCORDEE` ≈ PREPARATION ; `CLOTUREE` ≈ ARCHIVEE.
## Permissions

`mg.stock.view`, `mg.stock.create`, `mg.stock.entry`, `mg.stock.exit`, `mg.stock.adjust`, `mg.stock.inventory`, `mg.stock.approve`, `mg.stock.export`,
`mg.stock.alert.manage` (magasinier, valideur, admin), `mg.stock.alert.delete` (admin)

Rôles module : `stock-fournitures.lecteur`, `stock-fournitures.magasinier`, `stock-fournitures.valideur`, `stock-fournitures.admin`.

## Alertes de stock (`mg_stock_alertes`)

Service `app/services/mg_stock_alertes.py`, migration `20261022_mg_stock_alertes`.

- Seuil global `mg_stock_parametres.alerte_seuil_unites` (défaut **5**, « 5 unités ou moins ») ;
  `alerte_seuil_actif` = interrupteur (`0` / `non` désactive). `stock_min` par article reste
  utilisé par le tableau de bord, pas par les alertes.
- Évaluation sur le **stock réel** après chaque mouvement validé (`_appliquer_effet`,
  `_apply_mouvement`, suppression forcée / annulation) : jamais sur une saisie d’écran.
- **Épisode** : un seul épisode ouvert par article (index unique partiel
  `uq_mg_stock_alertes_episode_ouvert`). Franchissement 6 → 5 : ouverture + notification ;
  5 → 4 : mise à jour de la quantité, pas de notification ; → 0 : passage `RUPTURE` notifié
  une fois ; retour > seuil : `retour_normal_at`, statut `RESOLUE`, prochain franchissement
  = nouvel épisode.
- Périmètre = la ligne article (chaque agence / emplacement a sa propre ligne) : les stocks
  ne sont jamais additionnés.
- Contrôle initial / rattrapage idempotent : `POST /mg/stock/alertes/suivi/controle` et
  Celery beat `stock-controle-seuils` (7h00).
- Statuts : `NOUVELLE → EN_COURS → RESOLUE / CLOTUREE` ; `RESOLUE` refusé tant que le stock
  reste sous le seuil. Responsable = utilisateur actif titulaire d’un rôle `stock-fournitures.*`.
- Suppression **logique** avec motif obligatoire, auditée (`audit_logs`), sans effet sur le stock
  ni les mouvements ; une alerte supprimée n’est pas recréée tant que l’épisode reste ouvert.
- API : `GET /alertes/suivi`, `GET|PATCH|DELETE /alertes/suivi/{id}`,
  `POST /alertes/suivi/suppression` (masse), `GET /alertes/suivi/responsables`, `/alertes/export`.

## Département / service « Autre »

Sorties (`DEPARTEMENT`) et entrées (`RETOUR_DEPARTEMENT`) : option « Autre (préciser) » sur
Département et Service. L’API reçoit soit `departement_id` / `service_id`, soit
`departement_autre` / `service_autre` (libellé nettoyé, obligatoire, refusé s’il correspond
déjà à une entité : `DEPARTEMENT_EXISTANT` / `SERVICE_EXISTANT`). Stockage : texte dans
`departement` / `service_libelle` + drapeaux `departement_autre` / `service_autre` ;
`org_entite_id` reste NULL pour un département saisi. **Aucune entité n’est créée** dans
l’organigramme. Demandes : `bea-org-entite-libelle-select [autre]="true"`. Exports et rapports
signalent « (saisie « Autre ») ».

## Pagination

Listes `articles`, `mouvements`, `demandes` (et Archives `documents`) : réponse
`{ items, total, page, size }` (`page`/`size`, défaut 50, max 500).
Exports restent non paginés (plafond 500).

## Écrans

| Route | Contenu |
|-------|---------|
| `/stock-fournitures/dashboard` | KPI + charts conso / alertes stock bas (filtres agence/famille) |
| `/stock-fournitures/articles` | Référentiel articles / familles |
| `/stock-fournitures/articles/:id` | Fiche article (onglets Informations / Stock / Mouvements / Demandes / Documents) |
| `/stock-fournitures/stock` | État du stock temps réel |
| `/stock-fournitures/entrees` | Entrées de stock |
| `/stock-fournitures/sorties` | Sorties de stock |
| `/stock-fournitures/mouvements` / `journal` | Journal entrées/sorties |
| `/stock-fournitures/demandes` | Ancienne fiche de besoin — **retirée du menu** : les besoins passent par les demandes employés (`/demandes-mg`, bouton « Servir le stock »). Route et API conservées pour les anciens liens. |
| `/stock-fournitures/inventaires` | Campagnes d’inventaire (comptage / clôture) |
| `/stock-fournitures/alertes` | Stock faible / épuisé |
| `/stock-fournitures/rapports` | Conso mensuelle / annuelle / agence — JSON / CSV / Excel / PDF |
| `/stock-fournitures/parametres` | Familles + préfixes numérotation |

## Mapping fiche papier → UI

Expression de besoin : demandeur, tableau désignation / qty demandée / qty accordée, Visa Agence + Visa MG.
