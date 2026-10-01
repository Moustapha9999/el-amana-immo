import { HttpErrorResponse, HttpEvent, HttpInterceptorFn, HttpRequest, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, Subject, finalize, share, tap } from 'rxjs';
import { ApiErrorInfo, describeApiError } from './api-error';
import { FeedbackService } from './feedback.service';
import { IdempotencyScope } from './idempotency';

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const RECENT_MS = 5000;
const LOADING_DELAY_MS = 700;
/** Appels techniques : jamais d'indicateur « en cours ». */
const SILENT = [/\/auth\//, /\/notifications/, /\/health/];

/** Mémoire courte des derniers résultats HTTP (référence support, erreurs par champ, succès). */
@Injectable({ providedIn: 'root' })
export class HttpOutcomeTracker {
  private lastError: { info: ApiErrorInfo; at: number } | null = null;
  private lastMutationOkAt = 0;
  /** Émis à chaque écriture confirmée par le backend. */
  readonly mutationSuccess$ = new Subject<void>();

  noteError(info: ApiErrorInfo): void {
    this.lastError = { info, at: Date.now() };
  }

  noteMutationSuccess(): void {
    this.lastMutationOkAt = Date.now();
    this.mutationSuccess$.next();
  }

  /** Erreur HTTP toute récente (consommée une seule fois). */
  takeError(): ApiErrorInfo | null {
    const last = this.lastError;
    this.lastError = null;
    return last && Date.now() - last.at < RECENT_MS ? last.info : null;
  }

  /** Une écriture vient d'être confirmée par le backend (navigation post-enregistrement). */
  mutationJustSucceeded(withinMs = 2500): boolean {
    return Date.now() - this.lastMutationOkAt < withinMs;
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
 * - mémorise l'erreur normalisée (référence support, champs) pour les messages d'écran.
 */
export const httpFeedbackInterceptor: HttpInterceptorFn = (req, next) => {
  const tracker = inject(HttpOutcomeTracker);
  const mutating = MUTATING.has(req.method);

  const observe = (source: Observable<HttpEvent<unknown>>) =>
    source.pipe(
      tap({
        next: (event) => {
          if (mutating && event instanceof HttpResponse) tracker.noteMutationSuccess();
        },
        error: (err: unknown) => {
          if (err instanceof HttpErrorResponse) tracker.noteError(describeApiError(err));
        },
      }),
    );

  if (!mutating) return observe(next(req));

  const key = dedupKey(req);
  const existing = inflight.get(key);
  if (existing) return existing;

  const silent = SILENT.some((re) => re.test(req.url)) || inject(IdempotencyScope).managed > 0;
  const feedback = inject(FeedbackService);
  let handle: ReturnType<FeedbackService['loading']> | null = null;
  const timer = silent ? null : setTimeout(() => (handle = feedback.loading('Opération en cours…')), LOADING_DELAY_MS);

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
