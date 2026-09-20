# CORE ADMIN — centre de pilotage BEA DIGITAL

Interface d’administration centrale. **Login 1 uniquement.** Ce n’est pas
l’écran Utilisateurs du module Immobilisations.

Le détail métier (VNC, URLs `/dashboard`, `/immobilisations`, Login 2) ne
change pas. Voir [core-bea-digital.md](core-bea-digital.md) et
[socle-bea-digital.md](socle-bea-digital.md).

## Audit de l’existant (réutiliser)

| Brique | Tables | Usage |
|--------|--------|----------------|
| Utilisateurs | `users` | Compteurs dashboard |
| Rôles / permissions | `roles`, `permissions`, `user_roles`, `role_permissions` | Permission `core.admin.access` |
| Départements | `plateforme_espaces` | Compteur (≠ org `departements`) |
| Modules | `plateforme_modules` | Compteur + état « modules » |
| Accès | `user_espace_acces`, `user_module_acces` | Fiche utilisateur (Phase 2) |
| Sessions | `auth_sessions` | Sessions actives (non révoquées, non expirées) |
| Sécurité | `auth_login_attempts` | Alertes (échecs sur la fenêtre de lockout) |
| Audit | `audit_logs` | Actions du jour + activité récente |
| Notifications / GED | `notifications`, `ged_documents` | Écrans lecture CORE ADMIN |

**RLS** : non utilisée sur `public`. L’API FastAPI reste le gendarme.

**Pas de tables** `admin_users` / `admin_roles` / `admin_permissions`.

Le rôle immo `administrateur` **n’ouvre pas** CORE ADMIN.

## Architecture cible

```text
Login 1 (platform)
    → /accueil
    → /admin  si core.admin.access ou is_superuser
Login 2 (module immobilisations)
    → /dashboard … inchangé
```

- Route front : `/admin` (hors shell immo). Utilisateurs : `/admin/users`.
- API dashboard : `GET /api/v1/plateforme/admin/dashboard` (jeton platform).
  KPIs + graphiques (`activite_7j`, sessions, connexions, modules) + activité
  récente + état santé. Pas de librairie chart côté front plateforme.
- API utilisateurs : `/api/v1/plateforme/admin/users*` (`core.admin.users`).
- API départements : `/api/v1/plateforme/admin/departments*` (`core.admin.departments`).
- API modules : `/api/v1/plateforme/admin/modules*` (`core.admin.modules`).
- API rôles : `/api/v1/plateforme/admin/roles*` (`core.admin.roles`).
- API permissions : `/api/v1/plateforme/admin/permissions*` (`core.admin.permissions`).
- API matrice : `/api/v1/plateforme/admin/matrix` (`core.admin.roles`).
- API sessions : `/api/v1/plateforme/admin/sessions*` (`core.admin.sessions`).
- API audit : `/api/v1/plateforme/admin/audit` (`core.admin.audit`).
- Permission d’entrée : `core.admin.access`. Superuser : `*`.

### Permissions CORE ADMIN (catalogue)

`core.admin.access`, `core.admin.users`, `core.admin.roles`,
`core.admin.permissions`, `core.admin.departments`, `core.admin.modules`,
`core.admin.sessions`, `core.admin.audit`, `core.admin.security`,
`core.admin.settings`.

Phase 1 : `core.admin.access` ouvre le shell. Phase 2 : `core.admin.users`
contrôle l’administration des comptes. Phase 3 : `core.admin.departments` et
`core.admin.modules`. Phase 4 : `core.admin.roles` et `core.admin.permissions`.
Phase 5 : matrice d’accès (même permission `core.admin.roles`).
Phase 6 : sessions (`core.admin.sessions`).
Phase 7 : audit (`core.admin.audit`).
Phases 8–10 : activité (`core.admin.audit`), alertes / sécurité
(`core.admin.security`), notifications / GED / général / maintenance
(`core.admin.settings`).
**Aucun n’est lié au rôle `administrateur` immo.**

### Ops (Backup / Recovery / Supervision) — voir [core-admin-ops.md](core-admin-ops.md)

Permissions supplémentaires : `core.admin.backup.*`, `core.admin.recovery.*`,
`core.admin.monitoring.view`, `core.admin.maintenance.view|manage`,
`core.admin.module_status.view|manage`, `core.admin.versions.view|manage`.

Routes UI : `/admin/backups`, `/admin/recovery`, `/admin/supervision`,
`/admin/module-states`, `/admin/versions`, `/admin/maintenance`.

Appliquer la migration : `.\scripts\apply-core-admin-ops.ps1` (crée un backup
local avant Alembic `20260918_core_admin_ops`).
## Phases

| Phase | Contenu |
|-------|---------|
| **1** | Shell + dashboard réel |
| **2** | Utilisateurs : liste, création, fiche, activer/désactiver, reset accès |
| **3** | Départements (`plateforme_espaces`) et modules (`plateforme_modules`) |
| **4** | Rôles / permissions |
| **5** | Matrice d’accès |
| **6** | Sessions (révocation) |
| **7** | Audit complet |
| **8** | Notifications + GED (lecture) |
| **9** | Paramètres (Général / Sécurité) |
| **10 (cette livraison)** | Activité, Alertes, Maintenance — menu CORE ADMIN complet |

## Phase 2 — Utilisateurs

Écran CORE ADMIN, **pas** `/utilisateurs` du module Immobilisations.

- Liste : synthèse (total, actifs, inactifs, superusers, 2FA, jamais
  connectés), recherche (nom, e-mail, téléphone, rôle, département, module)
  et filtres (statut, rôle, département, module, profil, 2FA, connexion).
- Actions de ligne : voir, éditer, désactiver / réactiver, supprimer
  (archivage `deleted_at`).
- Création / modification : identité, départements (`plateforme_espaces`),
  modules, rôles immo existants.
- Désactivation : `is_active=false` sans `deleted_at` (réversible).
- Réinitialisation d’accès : mot de passe + révocation des sessions.
- Fiche : permissions, sessions et activité en lecture seule.
- On ne peut pas désactiver ni supprimer son propre compte. Seul un
  superutilisateur attribue `is_superuser`.

## Phase 3 — Départements et modules

Écrans CORE ADMIN `/admin/departments` et `/admin/modules`.
**≠** tables org `departements` (centres de coût immo).

- Catalogue Python = **seed des lignes absentes** uniquement. Les saisies
  CORE ADMIN (libellé, statut, route) ne sont plus écrasées au login.
- **Suppressions** : hors `comptabilite` / `immobilisations`, un module ou
  département effacé en CORE ADMIN **ne revient pas** au refresh (le seed
  optionnel ne s’applique qu’à la 1ʳᵉ install).
- Départements : liste, KPI, création, fiche, édition, désactivation,
  suppression. Code unique (`credit`, `reporting-rh`).
- Modules : mêmes actions, rattachés à un département.
- Protections : `comptabilite` et `immobilisations` ne se désactivent ni
  ne se suppriment. Route `/comptabilite` et entrée `/dashboard` figées.
- Suppression refusée s’il reste des modules (département) ou des accès
  utilisateurs.
- **Effet plateforme immédiat** : un département créé avec route `/{code}`
  (défaut) et statut `actif` apparaît sur Accueil pour les utilisateurs
  grantés (ou superuser) → hub `EspaceHubComponent`. Modules `bientot` =
  vitrine ; `actif` = Login 2 (shell métier = Immobilisations seulement
  tant que les ateliers n’ont pas abouti).

## Phase 4 — Rôles et permissions

Écrans CORE ADMIN `/admin/roles` et `/admin/permissions`.
**≠** `/utilisateurs` du module Immobilisations (Login 2).

- Catalogue Python = seed des rôles / permissions **absents** uniquement.
  Libellés et `role_permissions` des rôles déjà créés ne sont plus
  réécrits au login. La matrice effective lit la base (plus le plancher
  `ROLE_PERMISSIONS` Python).
- Rôles : liste, KPI (total, système, personnalisés, avec utilisateurs),
  création, fiche, édition des grants, suppression.
- Permissions : mêmes actions, filtre par module. `{module}.admin` couvre
  `{module}.*`.
- Protections : codes `RBAC_ROLES` (consultation…administrateur) et
  `FUNCTIONAL_PERMISSIONS` non supprimables, code figé. Le rôle
  `administrateur` immo ne peut pas recevoir `core.admin.*`.
- Suppression refusée s’il reste des utilisateurs (rôle) ou des rôles
  (permission).

## Phase 5 — Matrice d’accès

Écran CORE ADMIN `/admin/matrix` (Accès). Vue croisée rôles × permissions.

- Lecture : `GET /api/v1/plateforme/admin/matrix` — grants depuis
  `role_permissions` (pas le plancher Python `ROLE_PERMISSIONS`).
- Édition : `PATCH /api/v1/plateforme/admin/matrix` — bascule d’une case
  (`role_id`, `permission_code`, `granted`). Permission `core.admin.roles`.
- Filtres : recherche + module. KPI : rôles, permissions, grants, modules.
- Protection inchangée : le rôle `administrateur` immo ne peut pas recevoir
  `core.admin.*` (cases désactivées côté UI + refus API).

## Phase 6 — Sessions

Écran CORE ADMIN `/admin/sessions`. Table `auth_sessions`.

- Liste : KPI (actives, platform, module, expirées, révoquées), recherche,
  filtres type / statut, pagination.
- Révocation : `POST /api/v1/plateforme/admin/sessions/{id}/revoke` — révoque
  aussi les sessions module enfants. Permission `core.admin.sessions`.
- Protections : session courante non révocable ; Login 2 ne peut pas appeler
  l’API (Login 1 uniquement).

## Phase 7 — Audit

Écran CORE ADMIN `/admin/audit`. Table `audit_logs` (lecture seule).
**≠** `/audit` du module Immobilisations (Login 2).

- Liste paginée avec KPI (aujourd’hui, connexions, mutations, CORE, total).
- Filtres : recherche, module, entité, action, période ; raccourcis KPI via
  `kind=aujourd_hui|logins|mutations|core`.
- Permission `core.admin.audit`. Lien vers la fiche utilisateur quand
  `user_id` est présent.

## Phases 8–10 — Menu restant

Écrans CORE ADMIN sans « Bientôt » :

| Écran | Route | Permission | Source |
|-------|-------|------------|--------|
| Activité | `/admin/activity` | `core.admin.audit` | `audit_logs` (fenêtre) |
| Alertes | `/admin/alerts` | `core.admin.security` | `auth_login_attempts` |
| Notifications | `/admin/notifications` | `core.admin.settings` | `notifications` |
| GED | `/admin/ged` | `core.admin.settings` | `ged_documents` (lecture) |
| Général | `/admin/general` | `core.admin.settings` | settings (sans secrets) |
| Sécurité | `/admin/security` | `core.admin.security` | centre de contrôle (état, lockout, MFA, rate limit, contrôle défensif) |
| Maintenance | `/admin/maintenance` | `core.admin.settings` | santé runtime |

GED reste réservée (pas d’upload métier depuis CORE ADMIN).

## Rollback

Retirer les routes `/admin`, les endpoints `/plateforme/admin/*` et les
permissions `core.admin.*` du catalogue. **Aucune** table métier à DROP. Le
module Immobilisations n’est pas touché.
