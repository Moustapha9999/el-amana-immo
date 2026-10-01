import { ChangeDetectionStrategy, Component, HostListener, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService, FeedbackToast } from './feedback.service';

const ICONS: Record<FeedbackToast['tone'], string> = {
  success: 'check_circle',
  error: 'error',
  warning: 'warning',
  info: 'info',
  loading: 'progress_activity',
};

/** Monté une seule fois dans `App` : zone fixe, visible quelle que soit la position de scroll. */
@Component({
  selector: 'bea-feedback-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <div class="bea-fb" aria-live="polite" aria-relevant="additions text">
      @for (t of feedback.toasts(); track t.id) {
        <section
          class="bea-fb__toast"
          [attr.data-tone]="t.tone"
          [attr.role]="t.tone === 'error' ? 'alert' : 'status'"
          [attr.aria-busy]="t.tone === 'loading'"
        >
          <span class="bea-fb__icon" aria-hidden="true">
            @if (t.tone === 'loading') {
              <span class="bea-fb__spinner"></span>
            } @else {
              <mat-icon>{{ icon(t) }}</mat-icon>
            }
          </span>
          <div class="bea-fb__content">
            <p class="bea-fb__title">{{ t.title }}</p>
            @if (t.message) { <p class="bea-fb__message">{{ t.message }}</p> }
            @if (t.details?.length) {
              <dl class="bea-fb__details">
                @for (d of t.details; track d.label) {
                  <div><dt>{{ d.label }}</dt><dd>{{ d.value }}</dd></div>
                }
              </dl>
            }
            @if (t.requestId) {
              <p class="bea-fb__ref">Référence support : <code>{{ t.requestId }}</code></p>
            }
            @if (t.action) {
              <button type="button" class="bea-fb__action" (click)="runAction(t)">{{ t.action.label }}</button>
            }
          </div>
          @if (t.tone !== 'loading') {
            <button type="button" class="bea-fb__close" aria-label="Fermer le message" (click)="feedback.close(t.id)">
              <mat-icon>close</mat-icon>
            </button>
          }
          @if (t.duration && t.tone !== 'loading') {
            <span class="bea-fb__timer" [style.animation-duration.ms]="t.duration"></span>
          }
        </section>
      }
    </div>
  `,
  styles: `
    :host {
      position: fixed;
      top: 1rem;
      right: 1rem;
      z-index: 1100;
      pointer-events: none;
    }
    .bea-fb {
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
      width: min(24rem, calc(100vw - 2rem));
    }
    .bea-fb__toast {
      position: relative;
      display: flex;
      align-items: flex-start;
      gap: 0.7rem;
      padding: 0.85rem 0.85rem 0.9rem 0.9rem;
      overflow: hidden;
      border: 1px solid #e2e8f0;
      border-left: 4px solid var(--fb-accent);
      border-radius: 0.8rem;
      background: #fff;
      box-shadow: 0 14px 32px rgba(15, 23, 42, 0.16);
      pointer-events: auto;
      animation: beaFbIn 0.38s cubic-bezier(0.22, 1, 0.36, 1) both;
      --fb-accent: #1a5278;
      --fb-soft: #e8f1f8;
    }
    .bea-fb__toast[data-tone='success'] { --fb-accent: #0f766e; --fb-soft: #e8f6ef; }
    .bea-fb__toast[data-tone='error'] { --fb-accent: #b91c1c; --fb-soft: #fef2f2; }
    .bea-fb__toast[data-tone='warning'] { --fb-accent: #c2410c; --fb-soft: #fff7ed; }
    .bea-fb__toast[data-tone='info'],
    .bea-fb__toast[data-tone='loading'] { --fb-accent: #1a5278; --fb-soft: #e8f1f8; }
    .bea-fb__icon {
      display: inline-grid;
      place-items: center;
      flex-shrink: 0;
      width: 2rem;
      height: 2rem;
      border-radius: 50%;
      background: var(--fb-soft);
      color: var(--fb-accent);
    }
    .bea-fb__icon mat-icon { font-size: 1.2rem; width: 1.2rem; height: 1.2rem; }
    .bea-fb__spinner {
      width: 1rem;
      height: 1rem;
      border: 2px solid rgba(26, 82, 120, 0.25);
      border-top-color: #1a5278;
      border-radius: 50%;
      animation: beaFbSpin 0.8s linear infinite;
    }
    .bea-fb__content { flex: 1; min-width: 0; }
    .bea-fb__title {
      margin: 0.15rem 0 0;
      font-size: 0.92rem;
      font-weight: 700;
      color: #0f172a;
    }
    .bea-fb__message {
      margin: 0.25rem 0 0;
      font-size: 0.85rem;
      line-height: 1.4;
      color: #475569;
      white-space: pre-line;
      overflow-wrap: anywhere;
    }
    .bea-fb__details {
      display: grid;
      gap: 0.15rem;
      margin: 0.45rem 0 0;
      padding: 0.45rem 0.55rem;
      border-radius: 0.5rem;
      background: #f8fafc;
      font-size: 0.8rem;
    }
    .bea-fb__details div { display: flex; gap: 0.4rem; }
    .bea-fb__details dt { color: #64748b; }
    .bea-fb__details dd { margin: 0; font-weight: 700; color: #0f172a; overflow-wrap: anywhere; }
    .bea-fb__ref {
      margin: 0.4rem 0 0;
      font-size: 0.75rem;
      color: #64748b;
    }
    .bea-fb__ref code {
      padding: 0.05rem 0.3rem;
      border-radius: 0.25rem;
      background: #f1f5f9;
      color: #334155;
      user-select: all;
    }
    .bea-fb__action {
      margin-top: 0.55rem;
      padding: 0.35rem 0.75rem;
      border: 1px solid var(--fb-accent);
      border-radius: 0.45rem;
      background: #fff;
      color: var(--fb-accent);
      font: inherit;
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
    }
    .bea-fb__action:hover { background: var(--fb-soft); }
    .bea-fb__close {
      display: inline-grid;
      place-items: center;
      flex-shrink: 0;
      width: 1.75rem;
      height: 1.75rem;
      padding: 0;
      border: 0;
      border-radius: 0.4rem;
      background: transparent;
      color: #94a3b8;
      cursor: pointer;
    }
    .bea-fb__close:hover,
    .bea-fb__close:focus-visible { background: #f1f5f9; color: #334155; outline: none; }
    .bea-fb__close mat-icon { font-size: 1.1rem; width: 1.1rem; height: 1.1rem; }
    .bea-fb__timer {
      position: absolute;
      left: 0;
      bottom: 0;
      height: 3px;
      width: 100%;
      background: var(--fb-accent);
      opacity: 0.35;
      transform-origin: left;
      animation: beaFbTimer linear forwards;
    }
    @keyframes beaFbIn {
      from { opacity: 0; transform: translateX(1.5rem) scale(0.98); }
      to { opacity: 1; transform: none; }
    }
    @keyframes beaFbSpin { to { transform: rotate(360deg); } }
    @keyframes beaFbTimer { from { transform: scaleX(1); } to { transform: scaleX(0); } }
    @media (max-width: 600px) {
      :host { top: auto; bottom: 0.75rem; right: 0.75rem; left: 0.75rem; }
      .bea-fb { width: 100%; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-fb__toast, .bea-fb__timer { animation: none; }
      .bea-fb__spinner { animation-duration: 2s; }
    }
  `,
})
export class FeedbackHostComponent {
  readonly feedback = inject(FeedbackService);
  private offlineToast: number | null = null;

  @HostListener('window:offline')
  onOffline(): void {
    if (this.offlineToast !== null) return;
    this.offlineToast = this.feedback.warning({
      title: 'Connexion perdue',
      message: 'Vos saisies restent sur la page. Enregistrez à nouveau une fois le réseau revenu.',
      duration: 0,
    });
  }

  @HostListener('window:online')
  onOnline(): void {
    if (this.offlineToast === null) return;
    this.feedback.close(this.offlineToast);
    this.offlineToast = null;
    this.feedback.success({ title: 'Connexion rétablie' });
  }

  icon(t: FeedbackToast): string {
    return ICONS[t.tone];
  }

  runAction(t: FeedbackToast): void {
    const action = t.action;
    this.feedback.close(t.id);
    action?.run();
  }
}
