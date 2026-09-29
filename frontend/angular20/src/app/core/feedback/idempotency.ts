import { HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Porte la clé d'idempotence de l'action en cours jusqu'à l'intercepteur HTTP.
 * La requête est construite de façon synchrone à la souscription : la clé n'est
 * visible que pendant ce laps de temps.
 */
@Injectable({ providedIn: 'root' })
export class IdempotencyScope {
  current: string | null = null;
  /** > 0 pendant la construction d'une requête lancée par `FeedbackService.run` (feedback déjà géré). */
  managed = 0;

  newKey(): string {
    const rand =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
    return `bea-${rand}`;
  }

  wrap<T>(key: string | null, action: () => Observable<T>): Observable<T> {
    return new Observable<T>((subscriber) => {
      const previous = this.current;
      this.current = key;
      this.managed++;
      try {
        return action().subscribe(subscriber);
      } finally {
        this.current = previous;
        this.managed--;
      }
    });
  }
}

export const idempotencyInterceptor: HttpInterceptorFn = (req, next) => {
  const key = inject(IdempotencyScope).current;
  if (key && MUTATING.has(req.method) && !req.headers.has('Idempotency-Key')) {
    return next(req.clone({ setHeaders: { 'Idempotency-Key': key } }));
  }
  return next(req);
};
