# Catalogue des erreurs BEA DIGITAL

Source unique des **codes transversaux** (HTTP + auth + dépendances) :

- backend : `backend/app/core/error_catalog.py` (messages, titres, niveau de journal)
- frontend : `frontend/angular20/src/app/core/feedback/api-error.ts` (même codes, mêmes messages)
- format de réponse : `backend/app/core/api_errors.py`

Les codes **métier de module** (`TRANSITION_INVALIDE`, `STOCK_INSUFFISANT`,
`CONFLIT_REVISION`, …) restent levés avec leur message par
`AppError(message, code=...)` ou `HTTPException(detail={"code", "message"})`.
Ils ne sont pas recopiés ici : seul le titre est déduit du statut HTTP.

Le statut HTTP réel est **toujours** conservé. Jamais de conversion en `200 OK`.

## Contrat de réponse

```json
{
  "type": "about:blank",
  "title": "Conflit de données",
  "status": 409,
  "success": false,
  "code": "CONFLIT_REVISION",
  "message": "Cette fiche a été modifiée par un autre utilisateur.",
  "user_message": "Cette fiche a été modifiée par un autre utilisateur.",
  "errors": [],
  "request_id": "REQ-2026-10-26-ABC123",
  "detail": "Cette fiche a été modifiée par un autre utilisateur."
}
```

`detail` est conservé pour les écrans historiques (`err.error?.detail`).
`errors[]` porte les erreurs de champ (`field`, `code`, `message`).
Aucun trace, SQL, chemin, mot de passe, jeton ni message brut d'exception
n'est renvoyé. Le diagnostic reste dans `bea.access` / `bea.errors`,
corrélé par `request_id` (en-tête `X-Request-ID`).

## Affichage Angular

| Type | Affichage | Action utilisateur |
| --- | --- | --- |
| Champ (`VALIDATION_ERROR`, `errors[]`) | Sous le champ + toast si `FeedbackService.run` | Corriger, renvoyer |
| Auth (401, mot de passe à changer, MFA) | Formulaire de connexion / redirection existante | Se reconnecter, changer le mot de passe, activer le 2FA |
| Accès (403) | Notification ou écran d'accès déjà en place | Demander un droit ; ne pas relancer |
| Introuvable (404, 410) | Notification / page métier | Retour, actualiser |
| Conflit (409, 412) | Notification | Actualiser puis réessayer |
| Temporaire (408, 429, 502, 503) | Notification, bouton « Réessayer » | Attendre `Retry-After` si présent |
| Serveur (500, 501) | Notification + référence support | Contacter le support avec `request_id` |
| Réseau / 504 sur une écriture | Notification : vérifier le statut avant de relancer | Ne pas soumettre deux fois une opération financière |

Les codes 1xx, 2xx et 3xx ne sont pas des erreurs : aucun numéro HTTP n'est
affiché. Une redirection normale n'ouvre pas de toast.

## Codes transversaux

| Code | HTTP | Signification | Cause probable | Message utilisateur | Journal |
| --- | ---: | --- | --- | --- | --- |
| `BAD_REQUEST` | 400 | Requête mal formée | Corps / en-tête illisible | Certaines informations sont incorrectes… | WARNING |
| `BUSINESS_RULE_ERROR` | 400 | Règle métier (défaut 400) | `AppError` ou `HTTPException` 400 sans code | L'opération n'a pas pu être effectuée. | WARNING |
| `INVALID_VALUE` | 400 | Valeur refusée (contrainte, liste) | FK, check, valeur hors liste | Une valeur saisie n'est pas autorisée… | WARNING |
| `VALIDATION_ERROR` | 422 | Schéma Pydantic | Champ manquant ou format | Certaines informations ne respectent pas le format attendu… | WARNING |
| `PAYLOAD_TOO_LARGE` | 413 | Corps trop grand | Fichier / import | Le fichier ou la requête est trop volumineux… | WARNING |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Type MIME refusé | Mauvais format de fichier | Ce format de fichier n'est pas pris en charge. | WARNING |
| `AUTH_REQUIRED` | 401 | Authentification absente (défaut) | Pas de Bearer | Votre session a expiré… | INFO |
| `UNAUTHENTICATED` | 401 | Pas de jeton | Appel API sans session | Votre session a expiré… | INFO |
| `TOKEN_INVALID` | 401 | Jeton illisible ou mauvais type | JWT corrompu | Votre session a expiré… | INFO |
| `PLATFORM_SESSION_EXPIRED` | 401 | Session Login 1 expirée / révoquée | Idle, logout, révocation admin | Votre session a expiré… | INFO |
| `MODULE_SESSION_EXPIRED` | 401 | Session Login 2 expirée | Idle module | Votre session sur ce module a expiré… | INFO |
| `MODULE_AUTH_REQUIRED` | 401 | Login 2 manquant | Token plateforme sur route module | Connectez-vous au module… | INFO |
| `SESSION_REVOKED` | 401 | Refresh révoqué (réemploi) | Vol de jeton / double onglet | Votre session a été fermée… | WARNING |
| `USER_NOT_FOUND` | 401 | Compte disparu / inactif après émission | Désactivation pendant la session | Votre session a expiré… (volontairement uniforme) | WARNING |
| `AUTH_INVALID_CREDENTIALS` | 401 | Échec Login 1 / Login 2 | E-mail, mot de passe ou compte inactif | Adresse e-mail ou mot de passe incorrect. | WARNING |
| `TOTP_REQUIRED` | 401 | 2FA activée, code absent | Compte avec TOTP | Saisissez le code à 6 chiffres… | INFO |
| `TOTP_INVALID` | 401 | Code 2FA faux ou périmé | Horloge / saisie | Le code de vérification est incorrect… | WARNING |
| `LOGIN_LOCKED` | 429 | Lockout compte (échecs répétés) | Politique `login_lockout_*` | Trop de tentatives de connexion… | WARNING |
| `PASSWORD_CHANGE_REQUIRED` | 403 | Mot de passe provisoire | Compte créé par un admin | Vous devez définir un nouveau mot de passe… | INFO |
| `MFA_REQUIRED` | 403 | 2FA obligatoire (CORE ADMIN) | Politique MFA | Activez la double authentification… | INFO |
| `FORBIDDEN` | 403 | Accès refusé (défaut) | Rôle / grant | Vous ne disposez pas des autorisations… | WARNING |
| `PERMISSION_DENIED` | 403 | Permission manquante | Action précise | Vous ne disposez pas des autorisations… | WARNING |
| `MODULE_FORBIDDEN` | 403 | Module non accordé | Grant espace / module | Vous n'avez pas accès à ce module. | WARNING |
| `MODULE_UNAVAILABLE` | 403 | Module en maintenance | Statut catalogue | Ce module est momentanément indisponible… | INFO |
| `NOT_FOUND` | 404 | Ressource absente (ou masquée) | Id inconnu, hors périmètre | Cette page ou cette ressource est introuvable… | INFO |
| `METHOD_NOT_ALLOWED` | 405 | Mauvaise méthode HTTP | Client / proxy | Cette action n'est pas disponible de cette manière. | WARNING |
| `CONFLICT` | 409 | État incompatible (défaut) | Concurrent, déjà traité | Cette information a été modifiée… | WARNING |
| `DUPLICATE` | 409 | Unicité PostgreSQL 23505 | Doublon métier | Cette donnée existe déjà. | WARNING |
| `DUPLICATE_REQUEST` | 409 | Idempotency-Key en cours | Double clic | Cette opération est déjà en cours… | INFO |
| `CONCURRENT_UPDATE` | 409 | Deadlock / sérialisation | Deux écritures simultanées | Une autre opération modifiait les mêmes données… | WARNING |
| `RESOURCE_LOCKED` | 409 | Verrou PostgreSQL (55P03) | `lock_timeout` / NOWAIT | Cet élément est en cours de modification… | WARNING |
| `PRECONDITION_FAILED` | 412 | Révision obsolète | ETag / révision | Les données affichées ne sont plus à jour… | WARNING |
| `RATE_LIMITED` | 429 | Fenêtre glissante par IP | Locust, bot, usage intense | Trop de tentatives ont été effectuées… | WARNING |
| `REQUEST_TIMEOUT` | 408 | Délai client | Réseau lent | La demande a pris trop de temps… | INFO |
| `INTERNAL_ERROR` | 500 | Exception non maîtrisée | Bug | Une erreur inattendue est survenue… + référence | ERROR |
| `NOT_IMPLEMENTED` | 501 | Fonction non livrée | Endpoint futur | Cette fonctionnalité n'est pas encore disponible. | WARNING |
| `BAD_GATEWAY` | 502 | Nginx / intermédiaire | Backend down | Le service est temporairement indisponible… | ERROR |
| `SERVICE_UNAVAILABLE` | 503 | Service dégradé (défaut) | `/health/ready` | Le service est temporairement indisponible… | ERROR |
| `DATABASE_ERROR` | 503 | PostgreSQL injoignable | Réseau, auth, shutdown | La base de données est momentanément indisponible… | ERROR |
| `DATABASE_BUSY` | 503 | Pool saturé / trop de connexions | Charge, `DB_POOL_*` | Le service est très sollicité… | ERROR |
| `DATABASE_TIMEOUT` | 503 | `statement_timeout` (57014) | Requête trop lourde | Le traitement a pris trop de temps… | ERROR |
| `DEPENDENCY_UNAVAILABLE` | 503 | Redis / service externe | Redis down | Un service nécessaire… est momentanément indisponible… | ERROR |
| `GATEWAY_TIMEOUT` | 504 | Délai proxy | Traitement > `proxy_read_timeout` | Vérifiez le statut de votre opération avant de la relancer. | ERROR |

Codes HTTP enregistrés IANA **non utilisés** aujourd'hui (402, 407, 411, 417,
418, 421, 423 WebDAV, 424–428, 451, 505–511, etc.) : s'ils apparaissent
(proxy, futur module), le front retombe sur le message du statut
(`CODE_BY_STATUS`) ou sur « L'opération n'a pas pu être effectuée. »
Aucun de ces numéros n'est affiché à l'utilisateur.

## Authentification — réponses uniformes

- Compte inexistant, inactif ou mot de passe faux → **même** `AUTH_INVALID_CREDENTIALS`.
- `USER_NOT_FOUND` après émission d'un jeton reste un 401 au message de session
  (pas « utilisateur introuvable »).
- La vérification bcrypt d'un compte inconnu utilise un hash factice
  (`verify_password_async`) pour limiter l'énumération par le temps de réponse.

## Base de données et charge

| Symptôme | Code | Ce que ce n'est pas |
| --- | --- | --- |
| 429 massifs, latence ~20–140 ms | `RATE_LIMITED` | Saturation CPU / pool PostgreSQL |
| Pool SQLAlchemy épuisé | `DATABASE_BUSY` | Erreur métier |
| Deadlock / 40001 | `CONCURRENT_UPDATE` | « 500 interne » |
| Exception Python | `INTERNAL_ERROR` | À corriger, pas à relancer en boucle |

Pool (par processus uvicorn, défauts SQLAlchemy) : `DB_POOL_SIZE` (5),
`DB_MAX_OVERFLOW` (10), `DB_POOL_TIMEOUT` (30). En local, un seul worker
uvicorn : 15 connexions applicatives au plus, loin de `max_connections=100`.

Le rate limit est **par IP**. Derrière nginx, `TRUSTED_PROXIES=frontend` est
obligatoire pour distinguer les postes ; Locust depuis la machine hôte partage
souvent **une seule IP** → 20 login/min et 300 API/min pour *tous* les
utilisateurs virtuels. Ce n'est pas une panne de connexion PostgreSQL.

## Reprise des opérations sensibles

- Écriture + réseau perdu / 502 / 504 → `outcomeUnknown` côté front : pas de
  « Réessayer » automatique sans `Idempotency-Key`.
- `FeedbackService.run({ idempotent: true })` renvoie la même clé : le
  middleware Redis rejoue la réponse (`Idempotent-Replayed: true`) ou
  répond 409 `DUPLICATE_REQUEST`.
- Le front n'est jamais la seule barrière : permissions, lockout et
  idempotence restent côté serveur.
