# Moteur central de demandes

Chaque département BEA DIGITAL a un module **Demandes**. Le moteur est unique ;
les tables restent `mg_employee_requests` / `mg_request_categories` (pas de
second référentiel).

## Circulation

```
Département source (Crédit, RH, IT, Comptabilité, MG)
        → Demande (source_espace_code)
        → Type (target_espace_code)
        → Inbox du département destinataire
```

Exemple : Crédit → Fournitures → Moyens Généraux → stock **ou** regroupement →
demande d’achat existante (`source_type = MG_EMPLOYEE_BATCH`).

## Modules

| Espace | Module | Vue |
|--------|--------|-----|
| Comptabilité | `demandes-comptabilite` | Demandeur |
| Crédit | `demandes-credit` | Demandeur |
| RH | `demandes-rh` | Demandeur |
| Informatique | `demandes-informatique` | Demandeur |
| Moyens Généraux | `demandes-mg` | Demandeur + traitant |

L’ancien Espace Employé (`employe` / `demandes-employes`) est retiré.

## API

- Demandeur : `/api/v1/me/requests` (Login 2 d’un module `demandes-*`)
- Traitant MG : `/api/v1/mg/requests`, `/api/v1/mg/batches`
- CORE ADMIN : `/api/v1/plateforme/admin/request-types`

## Permissions

Demandeur : `mg.request.mine.*` via `{module}.demandeur`.  
Traitant MG : `mg.request.*` / `mg.batch.*` via `demandes-mg.{lecteur,gestionnaire,valideur,admin}`.
