import { HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { describeApiError, rememberRequestMethod } from './api-error';

function http(
  status: number,
  body: unknown,
  extras: { headers?: Record<string, string>; method?: string } = {},
): HttpErrorResponse {
  const err = new HttpErrorResponse({
    status,
    statusText: 'Error',
    error: body,
    headers: new HttpHeaders(extras.headers ?? {}),
    url: '/api/v1/exemple',
  });
  if (extras.method) rememberRequestMethod(err, extras.method);
  return err;
}

describe('describeApiError', () => {
  it('lit le code métier et le message français du backend', () => {
    const info = describeApiError(
      http(409, {
        code: 'CONFLIT_REVISION',
        title: 'Conflit de données',
        message: 'Cette fiche a été modifiée par un autre utilisateur.',
        user_message: 'Cette fiche a été modifiée par un autre utilisateur.',
        request_id: 'REQ-2026-10-26-ABC123',
        errors: [],
      }),
    );
    expect(info.status).toBe(409);
    expect(info.code).toBe('CONFLIT_REVISION');
    expect(info.kind).toBe('conflict');
    expect(info.message).toContain('modifiée');
    expect(info.requestId).toBe('REQ-2026-10-26-ABC123');
    expect(info.title).toBe('Conflit de données');
  });

  it('place les erreurs de validation sous les champs', () => {
    const info = describeApiError(
      http(422, {
        code: 'VALIDATION_ERROR',
        message: 'Certains champs sont invalides.',
        errors: [
          { field: 'email', code: 'VALUE_ERROR', message: 'Adresse e-mail invalide.' },
          { field: 'nom', code: 'STRING_TOO_SHORT', message: 'Ce champ doit contenir au moins 2 caractère(s).' },
        ],
      }),
    );
    expect(info.kind).toBe('validation');
    expect(info.fieldErrors['email']).toBe('Adresse e-mail invalide.');
    expect(info.fieldErrors['nom']).toContain('2');
  });

  it('ne révèle jamais le détail technique d’un 500', () => {
    const info = describeApiError(
      http(500, {
        message: 'psycopg2.OperationalError: password=secret SELECT * FROM users',
        detail: 'traceback /app/secret.py',
      }),
    );
    expect(info.status).toBe(500);
    expect(info.code).toBe('INTERNAL_ERROR');
    expect(info.kind).toBe('server');
    expect(info.message.toLowerCase()).not.toContain('password');
    expect(info.message.toLowerCase()).not.toContain('traceback');
    expect(info.message.toLowerCase()).not.toContain('select');
    expect(info.message).toContain('inattendue');
  });

  it('ne montre ni le JSON brut ni le numéro HTTP pour un réseau coupé', () => {
    const info = describeApiError(http(0, new ProgressEvent('error')));
    expect(info.code).toBe('NETWORK_ERROR');
    expect(info.kind).toBe('network');
    expect(info.retryable).toBeTrue();
    expect(info.message).not.toContain('0');
    expect(info.message).not.toContain('{');
    expect(info.message).toContain('joindre');
  });

  it('signale un résultat incertain seulement pour une mutation (POST/PUT/PATCH/DELETE)', () => {
    const mutation = describeApiError(http(0, null, { method: 'POST' }));
    const lecture = describeApiError(http(0, null, { method: 'GET' }));
    expect(mutation.outcomeUnknown).toBeTrue();
    expect(lecture.outcomeUnknown).toBeFalse();
  });

  it('traite une page HTML nginx comme une erreur serveur, pas comme du JSON', () => {
    const info = describeApiError(http(502, '<html><title>502 Bad Gateway</title></html>'));
    expect(info.code).toBe('BAD_GATEWAY');
    expect(info.kind).toBe('temporary');
    expect(info.message).not.toContain('<html');
    expect(info.message).not.toContain('502');
    expect(info.retryable).toBeTrue();
  });

  it('distingue identifiants refusés et session expirée', () => {
    const login = describeApiError(http(401, { code: 'AUTH_INVALID_CREDENTIALS', message: 'Adresse e-mail ou mot de passe incorrect.' }));
    const session = describeApiError(http(401, { code: 'PLATFORM_SESSION_EXPIRED', message: 'Votre session a expiré. Reconnectez-vous pour continuer.' }));
    expect(login.kind).toBe('auth');
    expect(login.message).toContain('mot de passe');
    expect(session.message).toContain('session');
    expect(login.message).not.toBe(session.message);
  });

  it('lit Retry-After et marque 429 comme réessayable', () => {
    const info = describeApiError(http(429, { code: 'RATE_LIMITED', message: 'Trop de tentatives.' }, { headers: { 'Retry-After': '12' } }));
    expect(info.retryable).toBeTrue();
    expect(info.retryAfter).toBe(12);
    expect(info.kind).toBe('rate_limit');
  });

  it('ne relance pas automatiquement un 504 financier (résultat inconnu)', () => {
    const info = describeApiError(
      http(504, { code: 'GATEWAY_TIMEOUT', message: 'Le service met trop de temps à répondre.' }, { method: 'POST' }),
    );
    expect(info.outcomeUnknown).toBeTrue();
    expect(info.retryable).toBeTrue();
    expect(info.message.toLowerCase()).toContain('statut');
  });

  it('accepte le contrat historique detail.code', () => {
    const info = describeApiError(http(403, { detail: { code: 'MFA_REQUIRED', message: 'Activez la double authentification.' } }));
    expect(info.code).toBe('MFA_REQUIRED');
    expect(info.kind).toBe('auth');
  });
});
