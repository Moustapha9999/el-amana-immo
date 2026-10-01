import { Injectable, WritableSignal, inject, signal } from '@angular/core';
import { Observable, EMPTY, from, of } from 'rxjs';
import { catchError, filter, finalize, switchMap, take, tap } from 'rxjs/operators';
import { UiDialogService } from '../../shared/ui-dialog/ui-dialog.service';
import { UiConfirmData, UiDialogAction, UiReasonData } from '../../shared/ui-dialog/ui-dialog.types';
import { ApiErrorInfo, describeApiErrorAsync } from './api-error';
import { IdempotencyScope } from './idempotency';

export type FeedbackTone = 'success' | 'error' | 'warning' | 'info' | 'loading';

export interface FeedbackDetail {
  label: string;
  value: string;
}

export interface FeedbackAction {
  label: string;
  run: () => void;
}

export interface FeedbackMessage {
  title: string;
  message?: string;
  /** Lignes clé/valeur : Référence, Statut… */
  details?: FeedbackDetail[];
  requestId?: string | null;
  action?: FeedbackAction;
  /** ms ; 0 = reste affiché jusqu'à fermeture. */
  duration?: number;
}

export interface FeedbackToast extends FeedbackMessage {
  id: number;
  tone: FeedbackTone;
  createdAt: number;
}

export interface FeedbackHandle {
  update(message: Partial<FeedbackMessage>): void;
  success(message: FeedbackMessage): void;
  error(message: FeedbackMessage): void;
  close(): void;
}

type Confirm =
  | { action: UiDialogAction; message: string; title?: string; hint?: string }
  | UiConfirmData;

export interface RunOptions<T> {
  /** Confirmation préalable (preset UiDialogAction ou données libres). */
  confirm?: Confirm;
  /** Libellé pendant l'appel : « Enregistrement… ». */
  loading?: string;
  /** Message de succès — affiché UNIQUEMENT après réponse positive du backend. */
  success: FeedbackMessage | ((result: T) => FeedbackMessage | null);
  /** Titre en cas d'échec : « Échec de l'enregistrement ». */
  errorTitle?: string;
  /** Complément affiché sous l'erreur (ex. « Vos données saisies ont été conservées. »). */
  errorHint?: string;
  /** Signal mis à true pendant l'opération (désactive le bouton). */
  busy?: WritableSignal<boolean>;
  /** Envoie un en-tête Idempotency-Key unique pour cette action (anti double création). */
  idempotent?: boolean;
  /** Affiche « Réessayer » sur les erreurs récupérables. Défaut : true. */
  retry?: boolean;
  /** Reçoit l'erreur normalisée (erreurs par champ pour le formulaire). */
  onError?: (error: ApiErrorInfo) => void;
}

export interface RunWithReasonOptions<T> extends Omit<RunOptions<T>, 'confirm'> {
  reason: UiReasonData;
}

const DEFAULT_DURATION: Record<FeedbackTone, number> = {
  success: 5000,
  info: 5000,
  warning: 8000,
  error: 0,
  loading: 0,
};

const MAX_TOASTS = 4;

/**
 * Système de feedback transversal BEA DIGITAL.
 * Affichage : `FeedbackHostComponent` (fixe, indépendant du scroll).
 * Confirmations : `UiDialogService` (MatDialog).
 */
@Injectable({ providedIn: 'root' })
export class FeedbackService {
  private readonly dialogs = inject(UiDialogService);
  private readonly idempotency = inject(IdempotencyScope);
  private readonly timers = new Map<number, ReturnType<typeof setTimeout>>();
  private seq = 0;

  readonly toasts = signal<FeedbackToast[]>([]);

  success(message: FeedbackMessage | string): number {
    return this.push('success', message);
  }

  error(message: FeedbackMessage | string): number {
    return this.push('error', message);
  }

  warning(message: FeedbackMessage | string): number {
    return this.push('warning', message);
  }

  info(message: FeedbackMessage | string): number {
    return this.push('info', message);
  }

  /** Message « en cours » ; le transformer ensuite en succès/erreur via le handle. */
  loading(title: string): FeedbackHandle {
    const id = this.push('loading', { title, duration: 0 });
    return {
      update: (m) => this.patch(id, m),
      success: (m) => this.replace(id, 'success', m),
      error: (m) => this.replace(id, 'error', m),
      close: () => this.close(id),
    };
  }

  /** Erreur API normalisée → toast d'erreur (avec référence support). */
  apiError(error: ApiErrorInfo, title?: string, action?: FeedbackAction, hint?: string): number {
    return this.error(this.errorMessage(error, title, action, hint));
  }

  close(id: number): void {
    const t = this.timers.get(id);
    if (t) clearTimeout(t);
    this.timers.delete(id);
    this.toasts.update((list) => list.filter((x) => x.id !== id));
  }

  clear(): void {
    this.timers.forEach((t) => clearTimeout(t));
    this.timers.clear();
    this.toasts.set([]);
  }

  confirm(confirm: Confirm): Observable<boolean> {
    return this.dialogs.confirm(this.toConfirmData(confirm));
  }

  /**
   * Cycle complet : confirmation → chargement → backend → succès/erreur.
   * N'émet le résultat que si le backend a confirmé l'opération.
   */
  run<T>(action: () => Observable<T>, options: RunOptions<T>): Observable<T> {
    const confirmed$ = options.confirm ? this.confirm(options.confirm) : of(true);
    return confirmed$.pipe(
      take(1),
      filter(Boolean),
      switchMap(() => this.execute(action, options)),
    );
  }

  /** Variante avec saisie d'un motif obligatoire (rejet, annulation…). */
  runWithReason<T>(action: (reason: string) => Observable<T>, options: RunWithReasonOptions<T>): Observable<T> {
    return this.dialogs.confirmWithReason(options.reason).pipe(
      take(1),
      filter((r): r is string => r !== null),
      switchMap((reason) => this.execute(() => action(reason), options)),
    );
  }

  private execute<T>(action: () => Observable<T>, options: RunOptions<T>, reuseKey?: string | null): Observable<T> {
    if (options.busy?.()) return EMPTY;
    options.busy?.set(true);
    const handle = options.loading ? this.loading(options.loading) : null;
    const key = options.idempotent ? reuseKey || this.idempotency.newKey() : null;
    const request$ = this.idempotency.wrap(key, action);

    return request$.pipe(
      take(1),
      tap((result) => {
        const msg = typeof options.success === 'function' ? options.success(result) : options.success;
        if (msg && handle) handle.success(msg);
        else if (msg) this.success(msg);
        else handle?.close();
      }),
      catchError((err: unknown) =>
        from(describeApiErrorAsync(err)).pipe(
          switchMap((info) => {
            options.onError?.(info);
            const canRetry = options.retry !== false && info.retryable;
            return new Observable<T>((subscriber) => {
              options.busy?.set(false);
              const retry = canRetry
                ? {
                    label: 'Réessayer',
                    run: () => {
                      this.execute(action, options, key).subscribe(subscriber);
                    },
                  }
                : undefined;
              const msg = this.errorMessage(info, options.errorTitle, retry, options.errorHint);
              if (handle) handle.error(msg);
              else this.error(msg);
              if (!canRetry) subscriber.complete();
            });
          }),
        ),
      ),
      finalize(() => options.busy?.set(false)),
    );
  }

  private errorMessage(error: ApiErrorInfo, title?: string, action?: FeedbackAction, hint?: string): FeedbackMessage {
    const fieldLines = Object.values(error.fieldErrors);
    return {
      title: title || error.title,
      message: [error.message, ...fieldLines.filter((l) => l !== error.message).slice(0, 3), hint]
        .filter(Boolean)
        .join('\n'),
      requestId: error.requestId,
      action,
      duration: 0,
    };
  }

  private toConfirmData(confirm: Confirm): UiConfirmData {
    if ('action' in confirm) {
      return this.dialogs.preset(confirm.action, confirm.message, confirm.title, confirm.hint);
    }
    return confirm;
  }

  private push(tone: FeedbackTone, input: FeedbackMessage | string): number {
    const message: FeedbackMessage = typeof input === 'string' ? { title: input } : input;
    const id = ++this.seq;
    const toast: FeedbackToast = { ...message, id, tone, createdAt: Date.now() };
    this.toasts.update((list) => {
      const next = [...list, toast];
      while (next.length > MAX_TOASTS) {
        const dropped = next.shift();
        if (dropped) this.clearTimer(dropped.id);
      }
      return next;
    });
    this.schedule(id, message.duration ?? DEFAULT_DURATION[tone]);
    return id;
  }

  private patch(id: number, message: Partial<FeedbackMessage>): void {
    this.toasts.update((list) => list.map((t) => (t.id === id ? { ...t, ...message } : t)));
  }

  private replace(id: number, tone: FeedbackTone, message: FeedbackMessage): void {
    const exists = this.toasts().some((t) => t.id === id);
    if (!exists) {
      this.push(tone, message);
      return;
    }
    this.toasts.update((list) =>
      list.map((t) =>
        t.id === id
          ? { id, tone, createdAt: Date.now(), title: message.title, message: message.message, details: message.details, requestId: message.requestId, action: message.action, duration: message.duration }
          : t,
      ),
    );
    this.schedule(id, message.duration ?? DEFAULT_DURATION[tone]);
  }

  private schedule(id: number, duration: number): void {
    this.clearTimer(id);
    if (duration > 0) {
      this.timers.set(id, setTimeout(() => this.close(id), duration));
    }
  }

  private clearTimer(id: number): void {
    const t = this.timers.get(id);
    if (t) clearTimeout(t);
    this.timers.delete(id);
  }
}