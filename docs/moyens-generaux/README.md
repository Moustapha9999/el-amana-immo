# Moyens Généraux — BEA DIGITAL

Espace plateforme `moyens-generaux`. Modules actifs : Stock, Achats, Notes de frais, Contrats, Archives.

## Documents

| Document | Contenu |
|----------|---------|
| [cdc-fonctionnel-v1.md](cdc-fonctionnel-v1.md) | CDC fonctionnel (5 modules) |
| [conception-technique-phase2.md](conception-technique-phase2.md) | Achats, notes, contrats, archives |
| [operationnalisation.md](operationnalisation.md) | Seed verrouillé, rôles, PDF, GED |

## Accès

| Élément | Valeur |
|---------|--------|
| Hub espace | `/moyens-generaux` |
| Module Stock | `/stock-fournitures/...` |
| API | `/api/v1/mg/stock/...` |
| Permissions | `mg.stock.view\|create\|entry\|exit\|adjust\|inventory\|approve\|export` |

## Modules catalogue

| Code | Statut |
|------|--------|
| `stock-fournitures` | actif |
| `achats-appro` | actif |
| `notes-frais` | actif |
| `contrats-echeances` | actif |
| `archives-mg` | actif |

Ne pas confondre avec l’espace seedé historique `achats` / `demandes-achat`.
