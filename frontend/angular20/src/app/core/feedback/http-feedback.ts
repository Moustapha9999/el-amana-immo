import {
  HttpContextToken,
  HttpErrorResponse,
  HttpEvent,
  HttpInterceptorFn,
  HttpRequest,
  HttpResponse,
} from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, Subject, finalize, share, tap } from 'rxjs';
import { ApiErrorInfo, ApiErrorKind, describeApiError, rememberRequestMethod } from './api-error';
import { FeedbackService } from './feedback.service';
import { IdempotencyScope } from './idempotency';

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const RECENT_MS = 5000;
const LOADING_DELAY_MS = 700;
/** Délai laissé à l'écran pour afficher l'erreur lui-même avant la notification de secours. */
const FALLBACK_DELAY_MS = 600;
/** Une même erreur globale (famille + code) n'est notifiée qu'une fois sur cette durée. */
const FALLBACK_DEDUP_MS = 15000;
/** Appels techniques : jamais d'indicateur « en cours » ni de notification de secours. */
const SILENT = [/\/auth\//, /\/notifications/, /\/health/];
/** Erreurs sans contexte d'écran : notifiées si aucun écran ne les a affichées. */
const GLOBAL_KINDS = new Set<ApiErrorKind>(['network', 'temporary', 'server', 'rate_limit']);

/** `new HttpContext().set(SKIP_ERROR_TOAST, true)` : l'écran gère entièrement l'erreur de cette requête. */
export const SKIP_ERROR_TOAST = new HttpContextToken<boolean>(() => false);

interface NotedError {
  info: ApiErrorInfo;
  at: number;
  handled: boolean;
}

/** Mémoire courte des derniers résultats HTTP (référence support, erreurs par champ, succès). */
@Injectable({ providedIn: 'root' })
export class HttpOutcomeTracker {
  private readonly feedback = inject(FeedbackService);
  private lastError: NotedError | null = null;
  private lastMutationOkAt = 0;
  private readonly fallbackShownAt = new Map<string, number>();
  /** Émis à chaque écriture confirmée par le backend. */
  readonly mutationSuccess$ = new Subject<void>();

  noteError(info: ApiErrorInfo, options: { fallback?: boolean } = {}): void {
    const noted: NotedError = { info, at: Date.now(), handled: false };
    this.lastError = noted;
    if (options.fallback && GLOBAL_KINDS.has(info.kind)) {
      setTimeout(() => this.showFallback(noted), FALLBACK_DELAY_MS);
    }
  }

  noteMutationSuccess(): void {
    this.lastMutationOkAt = Date.now();
    this.mutationSuccess$.next();
  }

  /** Erreur HTTP toute récente (consommée une seule fois). */
  takeError(): ApiErrorInfo | null {
    const last = this.lastError;
    this.lastError = null;
    if (!last || Date.now() - last.at >= RECENT_MS) return null;
    last.handled = true;
    return last.info;
  }

  /** Une écriture vient d'être confirmée par le backend (navigation post-enregistrement). */
  mutationJustSucceeded(withinMs = 2500): boolean {
    return Date.now() - this.lastMutationOkAt < withinMs;
  }

  private showFallback(noted: NotedError): void {
    const { info } = noted;
    if (noted.handled || this.feedback.wasShown(info.requestId)) return;
    // L'écran a affiché une erreur depuis (y compris sans référence, ex. 502 nginx) : rien à ajouter.
    if (this.feedback.toasts().some((t) => (t.tone === 'error' || t.tone === 'warning') && t.createdAt >= noted.at)) {
      return;
    }
    // Hors ligne : le bandeau « Connexion perdue » de <bea-feedback-host> suffit.
    if (info.kind === 'network' && typeof navigator !== 'undefined' && navigator.onLine === false) return;
    const key = `${info.kind}:${info.code}`;
    const now = Date.now();
    if (now - (this.fallbackShownAt.get(key) ?? 0) < FALLBACK_DEDUP_MS) return;
    this.fallbackShownAt.set(key, now);
    noted.handled = true;
    const message = { title: info.title, message: info.message, requestId: info.requestId };
    if (info.kind === 'server') this.feedback.error(message);
    else this.feedback.warning(message);
  }
}

function dedupKey(req: HttpRequest<unknown>): string {
  let body = '';
  if (req.body instanceof FormData || req.body instanceof Blob) body = '[binary]';
  else if (req.body != null) {
    try {
      body = JSON.stringify(req.body);
    } catch {
      body = '[unserializable]';
    }
  }
  return `${req.method} ${req.urlWithParams} ${body}`;
}

const inflight = new Map<string, Observable<HttpEvent<unknown>>>();

/**
 * Intercepteur transversal (tous modules) :
 * - requête d'écriture identique déjà en cours → partagée (anti double clic / double soumission) ;
 * - écriture > 700 ms hors `FeedbackService.run` → indicateur « Opération en cours… » ;
 * - mémorise l'erreur normalisée (référence support, champs) pour les messages d'écran ;
 * - erreur globale (réseau, serveur, service indisponible, 429) qu'aucun écran n'a affichée
 *   → notification de secours unique, jamais le statut HTTP ni le corps brut.
 */
export const httpFeedbackInterceptor: HttpInterceptorFn = (req, next) => {
  const tracker = inject(HttpOutcomeTracker);
  const mutating = MUTATING.has(req.method);
  const silent = SILENT.some((re) => re.test(req.url));
  const managed = inject(IdempotencyScope).managed > 0;
  const fallback = !silent && !managed && !req.context.get(SKIP_ERROR_TOAST);

  const observe = (source: Observable<HttpEvent<unknown>>) =>
    source.pipe(
      tap({
        next: (event) => {
          if (mutating && event instanceof HttpResponse) tracker.noteMutationSuccess();
        },
        error: (err: unknown) => {
          if (err instanceof HttpErrorResponse) {
            rememberRequestMethod(err, req.method);
            tracker.noteError(describeApiError(err), { fallback });
          }
        },
      }),
    );

  if (!mutating) return observe(next(req));

  const key = dedupKey(req);
  const existing = inflight.get(key);
  if (existing) return existing;

  const feedback = inject(FeedbackService);
  let handle: ReturnType<FeedbackService['loading']> | null = null;
  const timer =
    silent || managed ? null : setTimeout(() => (handle = feedback.loading('Opération en cours…')), LOADING_DELAY_MS);

  const shared = observe(next(req)).pipe(
    finalize(() => {
      inflight.delete(key);
      if (timer) clearTimeout(timer);
      handle?.close();
    }),
    share(),
  );
  inflight.set(key, shared);
  return shared;
};
