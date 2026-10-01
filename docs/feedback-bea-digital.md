# Retour utilisateur transversal (feedback) — BEA DIGITAL

Système **unique** de messages, confirmations et erreurs pour tous les
départements et modules. Aucun module ne doit recréer son propre mécanisme.

Interdits : `alert()`, `confirm()`, `console` comme seul retour, messages HTML
posés en haut de page (`erreur`/`msg` + `bea-stock-page__error/__ok`),
succès affiché **avant** la réponse du backend.

## Frontend (`frontend/angular20/src/app/core/feedback/`)

| Élément | Rôle |
| --- | --- |
| `FeedbackService` | `success / error / warning / info / loading / apiError / close / clear / confirm`, et surtout `run()` / `runWithReason()` |
| `<bea-feedback-host>` | Monté une fois dans `app.ts`. Fixe en haut à droite (bas sur mobile), indépendant du scroll, `aria-live`, `role=alert` pour les erreurs, `prefers-reduced-motion` respecté |
| `describeApiError(Async)` | Normalise toute erreur HTTP → `ApiErrorInfo {status, code, title, message, fieldErrors, requestId, retryable}` ; un 5xx n’affiche jamais le détail technique |
| `idempotencyInterceptor` + `IdempotencyScope` | En-tête `Idempotency-Key` sur les mutations lancées avec `idempotent: true` (anti double soumission, réutilisé par « Réessayer ») |
| `httpFeedbackInterceptor` + `HttpOutcomeTracker` | Global (toutes les requêtes) : une mutation identique déjà en vol est **partagée** (anti double clic même sans `run()`), toast « Opération en cours… » après 700 ms hors `run()`, mémorise la dernière erreur (référence support, erreurs par champ) et le dernier succès de mutation |
| `unsavedChanges()` + `unsavedChangesGuard` | `readonly hasUnsavedChanges = unsavedChanges(() => this.form.dirty && !this.saving(), () => this.form)` dans le composant. Le guard est posé sur **toutes** les routes (`withUnsavedChangesGuard` dans `app.routes.ts`) ; `beforeunload` géré par un registre global ; formulaire remis *pristine* après un succès backend, pas de fausse alerte juste après « Enregistrer » |
| Réseau | Toast persistant « Connexion perdue » (`window:offline`), puis « Connexion rétablie » |
| `UiDialogService` (existant, étendu) | `confirmAction(action, message, title?, hint?)`, `confirmWithReason(...)` (motif obligatoire), presets `soumission, validation, rejet, annulation, archivage, suspension, reprise, renouvellement, expiration, suppression, depart…` |

### Patron d’une action métier

```ts
this.feedback
  .run(() => this.api.post<Contrat>(`/mg/contrats/${id}/transition`, { action: 'valider' }), {
    confirm: { action: 'validation', message: `Valider le contrat ${c.reference} ?`, hint: '…' },
    loading: 'Validation…',
    busy: this.actionEnCours,          // désactive les boutons, bloque le double clic
    idempotent: true,                  // créations / paiements / transitions
    errorTitle: 'Échec de la validation',
    errorHint: 'Vos données saisies ont été conservées.',
    onError: (e) => this.fieldErrors.set(e.fieldErrors),
    success: (res) => ({ title: 'Validation effectuée', details: [{ label: 'Référence', value: res.reference }] }),
  })
  .subscribe((res) => this.fiche.set(res));
```

Rejet / annulation : `runWithReason(action, { reason: { … required: true }, … })`
— le motif saisi est passé à `action(motif)`.

Règles :

- succès **uniquement** dans `success` (appelé après réponse 2xx) ;
- erreurs de chargement : `describeApiErrorAsync(err).then(i => feedback.apiError(i, 'Chargement impossible'))` ;
- formulaire : ne jamais `reset()` en cas d’erreur ; afficher `fieldErrors` sous les champs ;
- les erreurs restent affichées jusqu’à fermeture et montrent la **Référence support** (`request_id`).

## Backend (`backend/app/`)

| Élément | Rôle |
| --- | --- |
| `core/request_context.py` + `middleware/request_context.py` | `request_id` (`REQ-AAAA-MM-JJ-XXXXXX`, ou `X-Request-ID` entrant), en-tête de réponse, log d’accès JSON `bea.access` (jamais de mot de passe, token, secret ni corps de requête) |
| `core/api_errors.py` | Handlers globaux → `{success:false, code, message, user_message, errors[{field,code,message}], request_id, detail}` |
| `middleware/idempotency.py` | Redis : rejoue la réponse pour une même `Idempotency-Key` (`Idempotent-Replayed: true`), 409 `DUPLICATE_REQUEST` si en cours ; passe-plat si Redis indisponible |
| `models/audit.py` | `audit_logs.request_id` renseigné automatiquement (événement `before_insert`) ; recherche par `request_id` dans l’audit CORE ADMIN |

Codes : `VALIDATION_ERROR` 422, `AUTH_REQUIRED` 401, `FORBIDDEN` 403,
`NOT_FOUND` 404, `CONFLICT`/`DUPLICATE`/`DUPLICATE_REQUEST` 409,
`RATE_LIMITED` 429, `DATABASE_ERROR` 503, `INTERNAL_ERROR` 500,
`BUSINESS_RULE_ERROR` (défaut).

`detail` est conservé pour compatibilité (`err.error?.detail` lu par les
écrans existants). Pour un code métier explicite :
`raise AppError("Transition impossible depuis …", code="TRANSITION_INVALIDE")`
(`detail` reste une chaîne, compatible avec les écrans existants). Pilote :
`mg_contrats_service.py` (`CONTRAT_DATES_INVALIDES`, `TRANSITION_INVALIDE`,
`MOTIF_OBLIGATOIRE`, `RENOUVELLEMENT_EXISTANT`, `REF_PAIEMENT_EXISTANTE`, …).
`HTTPException(detail={"code", "message"})` reste accepté.

Enveloppe succès : `success_body()` disponible pour les **nouveaux**
endpoints ; les endpoints existants renvoient toujours leur objet brut (le
front les lit tel quel — les envelopper casserait tous les écrans).

Santé : `/health` (liveness, healthchecks Docker) et `/health/ready`
(base + Redis, latence, 503 si dégradé, sans détail de connexion).

Migration : `20260929_audit_request_id` (colonne + index idempotents ; déjà
appliquée à la main sur la base Docker, `SKIP_MIGRATIONS=1`).

## Écrans existants : `feedbackSignal`

Les ~60 écrans qui affichaient `erreur` / `msg` / `ok` en haut de page
déclarent désormais :

```ts
readonly erreur = feedbackSignal('error', null);
readonly msg = feedbackSignal('success', '');
```

C’est un vrai signal Angular (le code `erreur.set(...)` / `erreur()` est
inchangé), mais chaque valeur non vide est affichée par `<bea-feedback-host>`.
Une erreur reprend la référence support de l’erreur HTTP qui vient d’arriver
(`HttpOutcomeTracker`), avec les erreurs par champ. Les paragraphes haut de
page ont été retirés.

Restent volontairement **en place** (contexte immédiat) : erreurs dans les
modales (`modalErreur`, `pdfErreur`, `paiementErreur`), formulaires Login 1 /
Login 2, statut OCR d’un document.

Le **nouveau** code utilise `FeedbackService.run()` (confirmation, chargement,
idempotence, erreurs par champ) — `feedbackSignal` est un pont pour l’existant.
Pilote complet : Contrats & Échéances (`contrats-list.component.ts`).

## Supervision CORE ADMIN

- **Erreurs API** (`/admin/erreurs`, permission `core.admin.audit`) : table
  `api_error_events` alimentée par `RequestContextMiddleware` pour les 403,
  409, 422, 429 et 5xx (pas 401/404, trop bruyants). KPIs (serveur, refus,
  conflits, validation), top routes / codes, filtre 24 h / 7 j / 30 j,
  recherche par référence `REQ-…`, lien vers l’audit de la même requête.
  Écriture en tâche de fond, hors transaction métier ; une panne n’affecte
  jamais la requête. Aucun corps de requête ni secret n’est stocké.
- **Journal d’audit** (`/admin/audit`) : colonne *Référence* (`request_id`),
  recherche par référence, `?search=REQ-…` en lien direct.
- Carte **Erreurs API (24 h)** sur le dashboard CORE ADMIN (masquée sans
  `core.admin.audit`).
- Tâches Celery (beat embarqué dans le worker, `celery worker -B`,
  `app/workers/tasks_supervision.py`) :
  - `purge_api_error_events` — chaque nuit 02:30 (Nouakchott), rétention
    `API_ERRORS_RETENTION_DAYS` (90 j par défaut) ;
  - `check_server_error_spike` — toutes les 5 min : si ≥
    `API_ERRORS_SPIKE_THRESHOLD` (10) erreurs 5xx en
    `API_ERRORS_SPIKE_WINDOW_MIN` (15) min, notification « Pic d’erreurs
    serveur » aux superutilisateurs et détenteurs de `core.admin.audit` ;
    au plus une alerte par heure.
- Lecture seule : les messages métier critiques ne sont pas éditables depuis
  CORE ADMIN.

## Migrations Alembic

Chaîne appliquée (base à `20260929_api_error_events`) :
`20260927_qty_granted` → `20260929_contrats_ref_paiement` →
`20260929_audit_request_id` → `20260929_api_error_events` (toutes
idempotentes). Commande :
`docker compose --env-file .env.docker exec backend alembic upgrade head`.
