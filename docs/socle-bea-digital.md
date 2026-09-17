# Socle figé — authentification et permissions BEA DIGITAL

Référence d’implémentation (backend canonique `backend/`). Les contrôles
d’accès se font **côté API**, pas uniquement dans Angular.

## Chaîne d’accès

```text
Utilisateur
    → Département (espace) autorisé ?
    → Module autorisé ?
    → Permission autorisée ?
    → ACCÈS
```

Login 1 n’ouvre que la plateforme. Login 2 n’ouvre qu’un module, et seulement
si Login 1 est encore valide.

## Login 1 — session BEA DIGITAL

```text
Login 1  →  session plateforme (kind=platform)  →  /accueil
```

| Élément | Règle figée |
|---------|-------------|
| Utilisateur | Table `users`, email unique, `is_active`, pas soft-deleted |
| Mot de passe | bcrypt, minimum 8 caractères ; comparaison insensible à la casse de l’email |
| Session | JWT access + refresh liés à `auth_sessions` (`kind=platform`) |
| Access | 15 minutes |
| Refresh | 1 jour ; rotation à chaque refresh |
| Déconnexion | `POST /api/v1/auth/logout` révoque la session **et** les sessions module enfants → écran Login 1 |
| Récupération | `POST /auth/forgot-password` + `POST /auth/reset-password` ; lien 15 min ; toutes les sessions révoquées après reset |
| Tentatives | Journal `auth_login_attempts` (`login_kind=platform`) |
| Blocage | 5 échecs / 15 min **par email** (Login 1) → HTTP 429 `LOGIN_LOCKED` |
| Rôles | portés par `user_roles` ; exposés dans `/auth/me` avec `espace_codes`, `module_codes`, `permission_codes` |
| 2FA | TOTP optionnel (code `TOTP_REQUIRED` si activé) |

Routes plateforme (`/auth/me`, `/plateforme/*`) exigent un jeton **platform**.
Un jeton module est refusé (`PLATFORM_SESSION_EXPIRED` / session BEA DIGITAL requise).

## Login 2 — session module

```text
Login 1 → Département → Module → Login 2 → session module (kind=module)
```

| Élément | Règle figée |
|---------|-------------|
| Prérequis | Session plateforme active + même email que Login 1 |
| Autorisation | Grant `user_espace_acces` **et** `user_module_acces` (superuser = tous) |
| Session | JWT liés à `auth_sessions` (`kind=module`, `module_code`, `parent_session_id`) |
| Access | 15 minutes |
| Refresh | 45 minutes ; refuse si le parent plateforme est révoqué / expiré |
| APIs métier | `require_module_access("immobilisations")` sur `/api/v1/...` immo |
| Tentatives | 5 échecs / 15 min par email + module → 429 |
| Front | `moduleGuard` → `/modules/immobilisations/acces` si pas de session module |

### Déconnexion module (obligatoire)

```text
Déconnexion module  →  révocation session module seulement  →  /comptabilite
```

**Interdit** : ramener au Login 1.

- API : `POST /api/v1/auth/modules/logout` (ne révoque pas la session plateforme)
- Front shell : `AuthService.logoutModule()` → `/comptabilite`
- Chrome Accueil : `logoutPlatform()` → Login 1 (c’est la déconnexion BEA DIGITAL)

## Matrice Immobilisations

| Profil | Rôle (`roles.code`) | Permissions |
|--------|---------------------|-------------|
| Consultation | `consultation` / `lecture_seule` | `immobilisations.read` |
| Création | `creation` | `read` + `create` |
| Modification | `modification` | `read` + `update` |
| Validation | `validation` | `read` + `validate` |
| Comptable (opérations) | `comptable` | read, create, update, cession, rebut, reevaluation, amortissement, reporting |
| Auditeur | `auditeur` | read, reporting |
| Administration | `administrateur` ou `is_superuser` | toutes les `immobilisations.*` |

`immobilisations.admin` (ou superuser) implique toutes les permissions `immobilisations.*`.

Le catalogue rôles / permissions est synchronisé au Login 1 (`ensure_catalogue`).

## Où c’est contrôlé

1. **Espace / module** — `PlateformeAccessService` + `require_module_access`
2. **Permission** — `require_permission("immobilisations.…")` sur les endpoints métier
3. **Front** — garde de route uniquement (ne pas s’y fier pour la sécurité)
