# Opérationnalisation Moyens Généraux

## Catalogue seed verrouillé

Espace `moyens-generaux` et modules MG sont dans `SEED_LOCKED_*` : ils sont
(ré)insérés s’ils manquent, même après bootstrap (comme Immobilisations).

Sync manuelle :

```powershell
cd backend
$env:DATABASE_URL="postgresql+asyncpg://...@127.0.0.1:5432/bea_digital"
.\.venv\Scripts\python.exe scripts\sync_catalogue_mg.py
```

Ou simplement se reconnecter (Login 1 appelle `ensure_catalogue`).

## Rôles Login 2

Exemples : `stock-fournitures.admin`, `achats-appro.acheteur`, `notes-frais.valideur`.

Attribuer via CORE ADMIN → utilisateurs / rôles. Un `is_superuser` voit tout.

## PDF

- `GET /api/v1/mg/achats/bons/{id}/pdf?signataire_1=…&signataire_2=…`
  - Mini-page front « Préparer le Bon de Commande » avant téléchargement
  - Nom fichier : `Bon-Commande-00XXXX.pdf`
  - Signataires dynamiques (défaut : Chef Sce Moyens Généraux / Directrice des Ressources)
  - Totaux HT / TVA / TTC (taux `tva_defaut` dans paramètres achats)
- `GET /api/v1/mg/notes-frais/notes/{id}/pdf`
- `GET /api/v1/mg/stock/demandes/{id}/pdf`

## Paramètres achats (CRUD)

UI `/achats-appro/parametres` — API `GET|POST /mg/achats/parametres`,
`PATCH|DELETE /mg/achats/parametres/{cle}`.

Clés utiles : `tva_defaut`, `prefix_bc`, `devise_defaut`, `alerte_jours`, …

Permission : `mg.purchase.create` (écriture) / `mg.purchase.view` (lecture).

Attribuer les rôles Login 2 via **CORE ADMIN** (`achats-appro.acheteur`,
`.valideur`, `.admin`, `.lecteur`) — le catalogue se resynchronise au Login 1.

## GED

Upload via `POST /api/v1/ged/documents` (`espace_code=moyens-generaux`,
`module_code` + `entity` + `entity_id`). Panneau UI :

| Module | Entités GED |
|--------|--------------|
| `achats-appro` | `bon_commande`, `achat_demande`, `achat_facture`, `fournisseur` |
| `notes-frais` | `note_frais` |
| `stock-fournitures` | `demande_fourniture`, `inventaire`, `article` |
| `contrats-echeances` | `contrat` |

Téléchargement : `GET /api/v1/ged/documents/{id}/download` (panneau GED + Archives MG).

Les documents apparaissent dans Archives MG (`/archives-mg/registre`, filtre module + lien fiche).

Permissions `ged.read` / `ged.write` (incluses dans les rôles `*.admin` MG).
