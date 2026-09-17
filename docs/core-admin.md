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
| Notifications / GED | `notifications`, `ged_documents` | Menus « Bientôt » |

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
- API utilisateurs : `/api/v1/plateforme/admin/users*` (`core.admin.users`).
- Permission d’entrée : `core.admin.access`. Superuser : `*`.

### Permissions CORE ADMIN (catalogue)

`core.admin.access`, `core.admin.users`, `core.admin.roles`,
`core.admin.permissions`, `core.admin.departments`, `core.admin.modules`,
`core.admin.sessions`, `core.admin.audit`, `core.admin.security`,
`core.admin.settings`.

Phase 1 : `core.admin.access` ouvre le shell. Phase 2 : `core.admin.users`
contrôle l’administration des comptes. Les autres codes restent réservés
(phases 3–10). **Aucun n’est lié au rôle `administrateur` immo.**

## Phases

| Phase | Contenu |
|-------|---------|
| **1** | Shell + dashboard réel |
| **2 (cette livraison)** | Utilisateurs : liste, création, fiche, activer/désactiver, reset accès |
| 3 | Départements / modules |
| 4 | Rôles / permissions |
| 5 | Matrice d’accès |
| 6 | Sessions (révocation) |
| 7 | Audit complet |
| 8 | Notifications |
| 9 | Paramètres |
| 10 | Supervision / maintenance |

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

## Rollback

Retirer les routes `/admin`, les endpoints `/plateforme/admin/*` et les
permissions `core.admin.*` du catalogue. **Aucune** table métier à DROP. Le
module Immobilisations n’est pas touché.
