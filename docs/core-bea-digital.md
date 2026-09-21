# CORE BEA DIGITAL — commun à tous les départements

Le CORE n’est pas le module Immobilisations. C’est ce que **Crédit, RH, IT,
Achats, Moyens Généraux** réutiliseront sans recopier l’auth, l’audit ou les fichiers.

ORION reste le core banking. BEA DIGITAL reste la plateforme interne
(Excel, contrôles, workflows, reporting, GED).

## Chaîne (figée)

```text
Utilisateur
    → Département / espace autorisé ?
    → Module autorisé ?
    → Permission autorisée ?
    → ACCÈS
```

Login 1 ouvre la plateforme. Login 2 ouvre un module, seulement si Login 1
est encore valide. Détail auth : [socle-bea-digital.md](socle-bea-digital.md).

## Cartographie A–J

| | Brique | Table / service | Notes |
|---|--------|-----------------|-------|
| A | Utilisateurs | `users` | Email unique, bcrypt, `is_active`, soft-delete |
| B | Rôles | `roles` + `user_roles` | Immo = codes courts legacy (`comptable`, …). Nouveaux modules = `{module}.{profil}` (`credit.admin`). Helpers : `module_role_code` / `role_module_code` |
| C | Permissions | `permissions` + `role_permissions` | `{module}.{action}` ; `{module}.admin` couvre `{module}.*` |
| D | Départements | `plateforme_espaces` | Comptabilité, Moyens Généraux, Crédit, RH, … **≠** `departements` (org immo / centres de coût). Catalogue : [catalogue-modules-futurs.md](catalogue-modules-futurs.md) · MG : [moyens-generaux/README.md](moyens-generaux/README.md) |
| E | Modules | `plateforme_modules` | Actifs : `immobilisations`, `stock-fournitures` (+ stubs bientôt) |
| F | Accès | `user_espace_acces`, `user_module_acces` | User → département, User → module |
| G | Audit | `audit_logs` | Qui, quoi, quand, espace, module, action, session |
| H | Notifications | `notifications` | Filtrables par `espace_code` / `module_code`. Enum Postgres historique immo ; nouveaux modules → `event_type` libre + `categorie` (`notification_taxonomy`) |
| I | Sessions | `auth_sessions` | `kind=platform` (BEA DIGITAL) et `kind=module` |
| J | GED | `ged_documents` | Lecture CORE ADMIN + API métier `/api/v1/ged/*`. `pieces_jointes` / `archive_*` restent immo |

CORE ADMIN (pilotage Login 1) : [core-admin.md](core-admin.md).

## APIs CORE (hors lock Immobilisations)

Ces URLs restent `/api/v1/...` (pas de préfixe `/comptabilite/`).

| Besoin | Route | Session |
|--------|-------|---------|
| Login 1 / 2, `/auth/me` | `/api/v1/auth/*` | selon la route |
| Catalogue + manifeste CORE | `/api/v1/plateforme/*` | Login 1 |
| Dashboard CORE ADMIN | `/api/v1/plateforme/admin/dashboard` | Login 1 + `core.admin.access` |
| Utilisateurs CORE ADMIN | `/api/v1/plateforme/admin/users*` | Login 1 + `core.admin.users` |
| Départements CORE ADMIN | `/api/v1/plateforme/admin/departments*` | Login 1 + `core.admin.departments` |
| Modules CORE ADMIN | `/api/v1/plateforme/admin/modules*` | Login 1 + `core.admin.modules` |
| Rôles CORE ADMIN | `/api/v1/plateforme/admin/roles*` | Login 1 + `core.admin.roles` |
| Permissions CORE ADMIN | `/api/v1/plateforme/admin/permissions*` | Login 1 + `core.admin.permissions` |
| Matrice d’accès | `/api/v1/plateforme/admin/matrix` | Login 1 + `core.admin.roles` |
| Sessions CORE ADMIN | `/api/v1/plateforme/admin/sessions*` | Login 1 + `core.admin.sessions` |
| Audit CORE ADMIN | `/api/v1/plateforme/admin/audit` | Login 1 + `core.admin.audit` |
| Activité / Alertes / Notif / GED / Settings | `/api/v1/plateforme/admin/{activity,alerts,notifications,ged,settings/*}` | Login 1 + audit / security / settings |
| Utilisateurs / rôles / grants | `/api/v1/users` | Login 1 **ou** Login 2 (rôle `administrateur`) |
| Notifications | `/api/v1/notifications` | Login 1 ou Login 2 |
| Audit (écran immo actuel) | `/api/v1/audit` | Login 2 immo, auditeur / admin |

Le métier immo (`/immobilisations`, `/amortissements`, écritures, …) exige
toujours Login 2 `immobilisations`.

## GED (lecture CORE ADMIN + upload métier)

- Table `ged_documents` : fichier + `espace_code` + `module_code` + `entity` / `entity_id`.
- Lecture CORE ADMIN : `GET /api/v1/plateforme/admin/ged` (`core.admin.settings`).
- API métier : `/api/v1/ged/documents`
  - `POST` upload (`ged.write`) — multipart : `file`, `espace_code`, `module_code`, `entity`, `entity_id`
  - `GET` liste / `GET …/download` (`ged.read`)
  - `DELETE` soft-delete (`ged.write`)
- Stockage : `storage/ged/{module}/{entity}/{id}/` (volume compose `./storage/ged`).
- Les pièces comptables immo (`pieces_jointes`) et les archives Excel/PDF
  **ne migrent pas** dans cette table. Les modules futurs (Crédit, RH, …)
  écrivent ici via `GedService`.
- Schéma idempotent : `scripts/supabase/01_upgrade.sql` (cible docker ou Supabase).

## Ce que le CORE n’est pas

- Le référentiel org `directions` / `departements` / `centres_cout` / `agences`
  (utilisé par le parc immo).
- Le moteur VNC / `amortissement_engine.py`.
- Un second front ou une seconde base.
