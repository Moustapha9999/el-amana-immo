import { HttpErrorResponse } from '@angular/common/http';

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
}

const TITLES: Record<string, string> = {
  NETWORK_ERROR: 'Serveur injoignable',
  AUTH_REQUIRED: 'Session expirée',
  FORBIDDEN: 'Accès refusé',
  NOT_FOUND: 'Élément introuvable',
  CONFLICT: 'Conflit de données',
  DUPLICATE: 'Doublon',
  DUPLICATE_REQUEST: 'Opération déjà en cours',
  INVALID_VALUE: 'Valeur non autorisée',
  VALIDATION_ERROR: 'Champs à corriger',
  RATE_LIMITED: 'Trop de tentatives',
  DATABASE_ERROR: 'Service indisponible',
  SERVICE_UNAVAILABLE: 'Service indisponible',
  INTERNAL_ERROR: 'Erreur inattendue',
};

const MESSAGES: Record<string, string> = {
  NETWORK_ERROR: 'Impossible de contacter le serveur. Vérifiez votre connexion puis réessayez.',
  AUTH_REQUIRED: 'Votre session a expiré. Reconnectez-vous ; vos données saisies sont conservées sur cette page.',
  FORBIDDEN: 'Vous n’avez pas les autorisations nécessaires pour effectuer cette action.',
  NOT_FOUND: 'L’élément demandé est introuvable ou a été supprimé.',
  CONFLICT: 'Cette donnée a été modifiée entre-temps. Actualisez la page pour voir la version actuelle.',
  DUPLICATE: 'Cette donnée existe déjà.',
  INVALID_VALUE: 'Une valeur saisie n’est pas autorisée. Vérifiez les champs à liste de choix.',
  VALIDATION_ERROR: 'Certains champs sont invalides. Veuillez les corriger.',
  INTERNAL_ERROR: 'Une erreur interne est survenue.',
};

const CODE_BY_STATUS: Record<number, string> = {
  0: 'NETWORK_ERROR',
  400: 'BUSINESS_RULE_ERROR',
  401: 'AUTH_REQUIRED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  409: 'CONFLICT',
  422: 'VALIDATION_ERROR',
  429: 'RATE_LIMITED',
  502: 'SERVICE_UNAVAILABLE',
  503: 'SERVICE_UNAVAILABLE',
  504: 'SERVICE_UNAVAILABLE',
};

interface ApiErrorBody {
  code?: string;
  message?: string;
  user_message?: string;
  errors?: Array<{ field?: string | null; message?: string }>;
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

export function describeApiError(err: unknown, body?: ApiErrorBody | null): ApiErrorInfo {
  const http = err instanceof HttpErrorResponse ? err : null;
  const status = http?.status ?? -1;
  const payload: ApiErrorBody | null =
    body ?? (http && http.error && typeof http.error === 'object' && !(http.error instanceof Blob) ? http.error : null);

  const code =
    payload?.code ||
    (payload?.detail && typeof payload.detail === 'object' && typeof (payload.detail as { code?: unknown }).code === 'string'
      ? ((payload.detail as { code: string }).code)
      : '') ||
    CODE_BY_STATUS[status] ||
    (status >= 500 ? 'INTERNAL_ERROR' : 'ERROR');

  const fieldErrors: Record<string, string> = {};
  for (const e of payload?.errors ?? []) {
    if (e?.field && e.message && !fieldErrors[e.field]) fieldErrors[e.field] = e.message;
  }

  // Les 5xx n'exposent jamais le détail technique ; le backend renvoie déjà un message neutre.
  const message =
    (status >= 500 ? null : payload?.user_message || payload?.message || detailText(payload?.detail)) ||
    MESSAGES[code] ||
    (status >= 500 ? MESSAGES['INTERNAL_ERROR'] : 'L’opération n’a pas pu être effectuée.');

  const requestId = payload?.request_id || http?.headers?.get('X-Request-ID') || null;

  return {
    status,
    code,
    title: TITLES[code] || 'Échec de l’opération',
    message,
    fieldErrors,
    requestId,
    retryable: status === 0 || status >= 500 || code === 'DUPLICATE_REQUEST' || code === 'RATE_LIMITED',
  };
}

/** Variante qui sait lire un corps d'erreur Blob (téléchargements). */
export async function describeApiErrorAsync(err: unknown): Promise<ApiErrorInfo> {
  if (err instanceof HttpErrorResponse && err.error instanceof Blob) {
    try {
      const parsed = JSON.parse(await err.error.text()) as ApiErrorBody;
      return describeApiError(err, parsed);
    } catch {
      return describeApiError(err, null);
    }
  }
  return describeApiError(err);
}
