import { WritableSignal, inject, signal, untracked } from '@angular/core';
import { FeedbackService } from './feedback.service';
import { HttpOutcomeTracker } from './http-feedback';

type Tone = 'error' | 'success' | 'warning' | 'info';

/**
 * Signal de message d'écran relié au feedback transversal : chaque valeur non vide
 * est affichée par `<bea-feedback-host>` (toast fixe), jamais en haut de page.
 * Une erreur reprend la référence support et les erreurs par champ de l'erreur HTTP
 * qui vient d'arriver. Pont pour le code existant (`erreur.set(...)` / `msg.set(...)`) ;
 * le nouveau code utilise directement `FeedbackService.run()`.
 */
export function feedbackSignal(tone: Tone, initial: string): WritableSignal<string>;
export function feedbackSignal(tone: Tone, initial?: string | null): WritableSignal<string | null>;
export function feedbackSignal(tone: Tone, initial: string | null = null): WritableSignal<string | null> {
  const feedback = inject(FeedbackService);
  const tracker = inject(HttpOutcomeTracker);
  const state = signal<string | null>(initial);
  const rawSet = state.set.bind(state);

  state.set = (value: string | null) => {
    rawSet(value);
    const text = typeof value === 'string' ? value.trim() : '';
    if (!text) return;
    if (tone !== 'error') {
      feedback[tone]({ title: text });
      return;
    }
    const http = tracker.takeError();
    const fields = http ? Object.values(http.fieldErrors).filter((m) => m !== text).slice(0, 4) : [];
    feedback.error({
      title: text,
      message: fields.length ? fields.join('\n') : undefined,
      requestId: http?.requestId ?? null,
    });
  };
  state.update = (fn: (v: string | null) => string | null) => state.set(fn(untracked(state)));
  return state;
}
