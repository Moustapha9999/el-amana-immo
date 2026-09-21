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

- `GET /api/v1/mg/achats/bons/{id}/pdf`
- `GET /api/v1/mg/notes-frais/notes/{id}/pdf`
- `GET /api/v1/mg/stock/demandes/{id}/pdf`

## GED

Upload via `POST /api/v1/ged/documents` (`espace_code=moyens-generaux`,
`module_code` + `entity` + `entity_id`). Panneau UI :

| Module | Entités GED |
|--------|--------------|
| `achats-appro` | `bon_commande` |
| `notes-frais` | `note_frais` |
| `stock-fournitures` | `demande_fourniture`, `inventaire`, `article` |
| `contrats-echeances` | `contrat` |

Téléchargement : `GET /api/v1/ged/documents/{id}/download` (panneau GED + Archives MG).

Les documents apparaissent dans Archives MG (`/archives-mg/registre`, filtre module + lien fiche).

Permissions `ged.read` / `ged.write` (incluses dans les rôles `*.admin` MG).
