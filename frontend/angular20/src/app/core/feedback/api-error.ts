import { HttpErrorResponse } from '@angular/common/http';

/** Famille d'erreur : choisit l'affichage (champ, notification, reconnexion…). */
export type ApiErrorKind =
  | 'validation'
  | 'auth'
  | 'access'
  | 'not_found'
  | 'conflict'
  | 'rate_limit'
  | 'temporary'
  | 'server'
  | 'network'
  | 'business';

/** Erreur API normalisée (contrat backend `app/core/api_errors.py`). */
export interface ApiErrorInfo {
  status: number;
  code: string;
  title: string;
  message: string;
  /** Erreurs par champ : { fournisseur_id: 'Le fournisseur est obligatoire.' }. */
  fieldErrors: Record<string, string>;
  requestId: string | null;
  /** L'utilisateur peut raisonnablement réessayer (réseau, 5xx, 409 doublon en cours). */
  retryable: boolean;
  kind: ApiErrorKind;
  /**
   * Le serveur a pu exécuter l'opération sans que la réponse n'arrive (réseau coupé, 502, 504) :
   * vérifier le statut de l'opération avant de la relancer.
   */
  outcomeUnknown: boolean;
  /** Délai conseillé avant un nouvel essai (en-tête Retry-After, secondes). */
  retryAfter: number | null;
}

/** Miroir de `backend/app/core/error_catalog.py` + erreurs propres au navigateur. */
const CATALOG: Record<string, { title: string; message: string }> = {
  NETWORK_ERROR: {
    title: 'Serveur injoignable',
    message: 'Impossible de joindre le service. Vérifiez votre connexion et réessayez.',
  },
  MALFORMED_RESPONSE: {
    title: 'Réponse inattendue',
    message: 'Une erreur inattendue est survenue. Si le problème persiste, contactez le support.',
  },
  BAD_REQUEST: {
    title: 'Requête invalide',
    message: 'Certaines informations sont incorrectes. Vérifiez les champs indiqués, puis réessayez.',
  },
  BUSINESS_RULE_ERROR: { title: 'Opération impossible', message: 'L’opération n’a pas pu être effectuée.' },
  INVALID_VALUE: {
    title: 'Valeur non autorisée',
    message: 'Une valeur saisie n’est pas autorisée. Vérifiez les champs à liste de choix.',
  },
  VALIDATION_ERROR: {
    title: 'Champs à corriger',
    message: 'Certaines informations ne respectent pas le format attendu. Vérifiez les champs indiqués.',
  },
  PAYLOAD_TOO_LARGE: {
    title: 'Fichier trop volumineux',
    message: 'Le fichier ou la requête est trop volumineux. Choisissez un fichier plus petit.',
  },
  URI_TOO_LONG: {
    title: 'Recherche trop longue',
    message: 'La recherche ou le filtre est trop long. Réduisez les critères, puis réessayez.',
  },
  UNSUPPORTED_MEDIA_TYPE: { title: 'Format non pris en charge', message: 'Ce format de fichier n’est pas pris en charge.' },
  NOT_ACCEPTABLE: { title: 'Format indisponible', message: 'Ce format de réponse n’est pas disponible pour cette ressource.' },
  RANGE_NOT_SATISFIABLE: {
    title: 'Téléchargement impossible',
    message: 'La partie demandée du fichier n’est pas disponible. Relancez le téléchargement.',
  },
  HEADERS_TOO_LARGE: {
    title: 'Requête refusée',
    message: 'La requête n’a pas pu être traitée. Reconnectez-vous ; si le problème persiste, contactez le support.',
  },
  AUTH_REQUIRED: { title: 'Session expirée', message: 'Votre session a expiré. Reconnectez-vous pour continuer.' },
  UNAUTHENTICATED: { title: 'Session expirée', message: 'Votre session a expiré. Reconnectez-vous pour continuer.' },
  TOKEN_INVALID: { title: 'Session expirée', message: 'Votre session a expiré. Reconnectez-vous pour continuer.' },
  PLATFORM_SESSION_EXPIRED: { title: 'Session expirée', message: 'Votre session a expiré. Reconnectez-vous pour continuer.' },
  MODULE_SESSION_EXPIRED: {
    title: 'Session du module expirée',
    message: 'Votre session sur ce module a expiré. Reconnectez-vous au module pour continuer.',
  },
  MODULE_AUTH_REQUIRED: { title: 'Connexion au module requise', message: 'Connectez-vous au module pour continuer.' },
  SESSION_REVOKED: {
    title: 'Session révoquée',
    message: 'Votre session a été fermée (déconnexion ou révocation). Reconnectez-vous pour continuer.',
  },
  USER_NOT_FOUND: { title: 'Session expirée', message: 'Votre session a expiré. Reconnectez-vous pour continuer.' },
  AUTH_INVALID_CREDENTIALS: { title: 'Connexion refusée', message: 'Adresse e-mail ou mot de passe incorrect.' },
  TOTP_REQUIRED: {
    title: 'Code de vérification requis',
    message: 'Saisissez le code à 6 chiffres de votre application d’authentification.',
  },
  TOTP_INVALID: {
    title: 'Code de vérification incorrect',
    message: 'Le code de vérification est incorrect ou expiré. Saisissez le code affiché actuellement.',
  },
  LOGIN_LOCKED: {
    title: 'Connexion temporairement bloquée',
    message: 'Trop de tentatives de connexion. Patientez quelques minutes avant de réessayer.',
  },
  PASSWORD_CHANGE_REQUIRED: {
    title: 'Mot de passe à renouveler',
    message: 'Vous devez définir un nouveau mot de passe avant de continuer.',
  },
  MFA_REQUIRED: {
    title: 'Double authentification requise',
    message: 'Activez la double authentification sur votre compte pour accéder à cette fonctionnalité.',
  },
  FORBIDDEN: {
    title: 'Accès refusé',
    message: 'Vous ne disposez pas des autorisations nécessaires pour accéder à cette page ou effectuer cette opération.',
  },
  PERMISSION_DENIED: {
    title: 'Accès refusé',
    message: 'Vous ne disposez pas des autorisations nécessaires pour effectuer cette opération.',
  },
  MODULE_FORBIDDEN: { title: 'Module non autorisé', message: 'Vous n’avez pas accès à ce module.' },
  MODULE_UNAVAILABLE: { title: 'Module indisponible', message: 'Ce module est momentanément indisponible. Réessayez plus tard.' },
  NOT_FOUND: {
    title: 'Élément introuvable',
    message: 'Cette page ou cette ressource est introuvable ou n’est plus disponible.',
  },
  GONE: { title: 'Élément retiré', message: 'Cette ressource a été définitivement retirée.' },
  METHOD_NOT_ALLOWED: { title: 'Action indisponible', message: 'Cette action n’est pas disponible de cette manière.' },
  CONFLICT: {
    title: 'Conflit de données',
    message: 'Cette information a été modifiée par un autre utilisateur. Actualisez les données avant de réessayer.',
  },
  DUPLICATE: { title: 'Doublon', message: 'Cette donnée existe déjà.' },
  DUPLICATE_REQUEST: {
    title: 'Opération déjà en cours',
    message: 'Cette opération est déjà en cours de traitement. Patientez quelques instants.',
  },
  CONCURRENT_UPDATE: {
    title: 'Modification simultanée',
    message: 'Une autre opération modifiait les mêmes données au même moment. Actualisez puis réessayez.',
  },
  RESOURCE_LOCKED: {
    title: 'Élément en cours de modification',
    message: 'Cet élément est en cours de modification par une autre opération. Réessayez dans quelques instants.',
  },
  PRECONDITION_FAILED: {
    title: 'Données obsolètes',
    message: 'Les données affichées ne sont plus à jour. Actualisez la page avant de réessayer.',
  },
  REQUEST_TIMEOUT: {
    title: 'Délai dépassé',
    message: 'La demande a pris trop de temps. Vérifiez votre connexion, puis réessayez si nécessaire.',
  },
  RATE_LIMITED: {
    title: 'Trop de requêtes',
    message: 'Trop de tentatives ont été effectuées. Patientez quelques instants avant de réessayer.',
  },
  INTERNAL_ERROR: {
    title: 'Erreur inattendue',
    message:
      'Une erreur inattendue est survenue. Votre demande n’a pas pu être traitée normalement. ' +
      'Si le problème persiste, contactez le support avec la référence indiquée.',
  },
  NOT_IMPLEMENTED: { title: 'Fonctionnalité indisponible', message: 'Cette fonctionnalité n’est pas encore disponible.' },
  BAD_GATEWAY: {
    title: 'Service indisponible',
    message: 'Le service est temporairement indisponible. Réessayez dans quelques instants.',
  },
  SERVICE_UNAVAILABLE: {
    title: 'Service indisponible',
    message: 'Le service est temporairement indisponible. Réessayez dans quelques instants.',
  },
  DATABASE_ERROR: {
    title: 'Service indisponible',
    message: 'La base de données est momentanément indisponible. Réessayez dans quelques instants.',
  },
  DATABASE_BUSY: { title: 'Service très sollicité', message: 'Le service est très sollicité. Réessayez dans quelques instants.' },
  DATABASE_TIMEOUT: {
    title: 'Traitement trop long',
    message: 'Le traitement a pris trop de temps et a été interrompu. Affinez votre recherche ou réessayez plus tard.',
  },
  DEPENDENCY_UNAVAILABLE: {
    title: 'Service indisponible',
    message: 'Un service nécessaire à cette opération est momentanément indisponible. Réessayez dans quelques instants.',
  },
  GATEWAY_TIMEOUT: {
    title: 'Délai de réponse dépassé',
    message: 'Le service met trop de temps à répondre. Vérifiez le statut de votre opération avant de la relancer.',
  },
};

const CODE_BY_STATUS: Record<number, string> = {
  0: 'NETWORK_ERROR',
  400: 'BUSINESS_RULE_ERROR',
  401: 'AUTH_REQUIRED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  405: 'METHOD_NOT_ALLOWED',
  406: 'NOT_ACCEPTABLE',
  408: 'REQUEST_TIMEOUT',
  409: 'CONFLICT',
  410: 'GONE',
  412: 'PRECONDITION_FAILED',
  413: 'PAYLOAD_TOO_LARGE',
  414: 'URI_TOO_LONG',
  415: 'UNSUPPORTED_MEDIA_TYPE',
  416: 'RANGE_NOT_SATISFIABLE',
  422: 'VALIDATION_ERROR',
  429: 'RATE_LIMITED',
  431: 'HEADERS_TOO_LARGE',
  500: 'INTERNAL_ERROR',
  501: 'NOT_IMPLEMENTED',
  502: 'BAD_GATEWAY',
  503: 'SERVICE_UNAVAILABLE',
  504: 'GATEWAY_TIMEOUT',
};

/** Titre d'un code métier non catalogué (TRANSITION_INVALIDE, STOCK_INSUFFISANT…), selon le statut. */
const TITLE_BY_STATUS: Record<number, string> = {
  400: 'Opération impossible',
  401: 'Authentification requise',
  403: 'Accès refusé',
  404: 'Élément introuvable',
  409: 'Conflit de données',
  413: 'Fichier trop volumineux',
  415: 'Format non pris en charge',
  422: 'Champs à corriger',
  423: 'Élément verrouillé',
  429: 'Trop de requêtes',
};

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const requestMethods = new WeakMap<HttpErrorResponse, string>();

/** Mémorisé par `httpFeedbackInterceptor` : une lecture en échec n'a jamais de résultat incertain. */
export function rememberRequestMethod(err: HttpErrorResponse, method: string): void {
  requestMethods.set(err, method);
}

const RETRYABLE_CODES = new Set([
  'DUPLICATE_REQUEST',
  'RATE_LIMITED',
  'LOGIN_LOCKED',
  'CONCURRENT_UPDATE',
  'RESOURCE_LOCKED',
  'REQUEST_TIMEOUT',
]);

interface ApiErrorBody {
  code?: string;
  title?: string;
  message?: string;
  user_message?: string;
  errors?: Array<{ field?: string | null; message?: string }>;
  field_errors?: Record<string, string> | Array<{ field?: string | null; message?: string }> | null;
  request_id?: string;
  detail?: unknown;
}

function detailText(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const msg = (detail as { message?: unknown }).message;
    if (typeof msg === 'string' && msg.trim()) return msg;
  }
  return null;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/** Corps exploitable uniquement s'il s'agit d'un objet JSON (jamais une page HTML nginx ni un texte brut). */
function structuredBody(http: HttpErrorResponse | null): ApiErrorBody | null {
  const raw: unknown = http?.error;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw) || raw instanceof Blob || raw instanceof Error) {
    return null;
  }
  if (typeof ProgressEvent !== 'undefined' && raw instanceof ProgressEvent) return null;
  return raw as ApiErrorBody;
}

function kindOf(status: number, code: string, hasFields: boolean): ApiErrorKind {
  if (status === 0) return 'network';
  if (status >= 200 && status < 400) return 'server';
  if (status === 401) return 'auth';
  if (status === 403) return code === 'PASSWORD_CHANGE_REQUIRED' || code === 'MFA_REQUIRED' ? 'auth' : 'access';
  if (status === 404 || status === 410) return 'not_found';
  if (status === 409 || status === 412 || status === 423) return 'conflict';
  if (status === 429) return 'rate_limit';
  if (status === 422 || hasFields) return 'validation';
  if (status === 408 || status === 502 || status === 503 || status === 504) return 'temporary';
  if (status >= 500) return 'server';
  return 'business';
}

function parseRetryAfter(http: HttpErrorResponse | null): number | null {
  const raw = http?.headers?.get('Retry-After');
  if (!raw) return null;
  const seconds = Number(raw);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds);
  const date = Date.parse(raw);
  return Number.isNaN(date) ? null : Math.max(0, Math.ceil((date - Date.now()) / 1000));
}

function collectFieldErrors(payload: ApiErrorBody | null): Record<string, string> {
  const out: Record<string, string> = {};
  const add = (field: unknown, message: unknown) => {
    const f = text(field);
    const m = text(message);
    if (f && m && !out[f]) out[f] = m;
  };
  for (const e of Array.isArray(payload?.errors) ? payload.errors : []) add(e?.field, e?.message);
  const extra = payload?.field_errors;
  if (Array.isArray(extra)) extra.forEach((e) => add(e?.field, e?.message));
  else if (extra && typeof extra === 'object') Object.entries(extra).forEach(([f, m]) => add(f, m));
  return out;
}

function isMutation(http: HttpErrorResponse | null): boolean {
  const method = http ? requestMethods.get(http) : undefined;
  return method === undefined || MUTATING.has(method);
}

export function describeApiError(err: unknown, body?: ApiErrorBody | null): ApiErrorInfo {
  const http = err instanceof HttpErrorResponse ? err : null;
  const status = http ? http.status : -1;
  const payload: ApiErrorBody | null = body ?? structuredBody(http);
  const malformed = status >= 200 && status < 400;

  const explicitCode =
    text(payload?.code) ||
    (payload?.detail && typeof payload.detail === 'object' ? text((payload.detail as { code?: unknown }).code) : null);
  const code =
    (malformed ? 'MALFORMED_RESPONSE' : null) ||
    explicitCode ||
    CODE_BY_STATUS[status] ||
    (status >= 500 ? 'INTERNAL_ERROR' : status >= 400 ? 'BUSINESS_RULE_ERROR' : 'MALFORMED_RESPONSE');

  const fieldErrors = collectFieldErrors(payload);
  const known = CATALOG[code];

  // 4xx : message métier du backend. 5xx : jamais de détail technique, sauf message
  // volontaire d'un code explicite non catalogué (ex. MIGRATION_REQUISE).
  const backendMessage = malformed
    ? null
    : text(payload?.user_message) || text(payload?.message) || detailText(payload?.detail);
  let message: string;
  if (status >= 500) {
    message = known?.message ?? (explicitCode && backendMessage) ?? CATALOG['INTERNAL_ERROR'].message;
  } else {
    message = backendMessage ?? known?.message ?? CATALOG['BUSINESS_RULE_ERROR'].message;
  }

  const requestId = text(payload?.request_id) || http?.headers?.get('X-Request-ID') || null;
  const kind = kindOf(status, code, Object.keys(fieldErrors).length > 0);
  const title =
    known?.title ||
    text(payload?.title) ||
    TITLE_BY_STATUS[status] ||
    (status >= 500 ? CATALOG['INTERNAL_ERROR'].title : 'Échec de l’opération');

  return {
    status,
    code,
    title,
    message,
    fieldErrors,
    requestId,
    retryable: status === 0 || (status >= 500 && status !== 501) || RETRYABLE_CODES.has(code),
    kind,
    outcomeUnknown: (status === 0 || status === 502 || status === 504) && isMutation(http),
    retryAfter: parseRetryAfter(http),
  };
}

/** Variante qui sait lire un corps d'erreur Blob (téléchargements). */
export async function describeApiErrorAsync(err: unknown): Promise<ApiErrorInfo> {
  if (err instanceof HttpErrorResponse && err.error instanceof Blob) {
    try {
      const parsed = JSON.parse(await err.error.text()) as ApiErrorBody;
      return describeApiError(err, parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null);
    } catch {
      return describeApiError(err, null);
    }
  }
  return describeApiError(err);
}
