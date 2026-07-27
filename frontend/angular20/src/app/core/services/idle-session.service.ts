import { Injectable, inject, OnDestroy } from '@angular/core';
import { AuthService } from './auth.service';

/** Déconnexion automatique après 2 minutes sans activité utilisateur. */
const IDLE_MS = 5 * 60 * 1000;

const ACTIVITY_EVENTS: (keyof WindowEventMap)[] = [
  'mousemove',
  'mousedown',
  'keydown',
  'touchstart',
  'scroll',
  'click',
  'wheel',
];

@Injectable({ providedIn: 'root' })
export class IdleSessionService implements OnDestroy {
  private readonly auth = inject(AuthService);

  private timer: ReturnType<typeof setTimeout> | null = null;
  private started = false;
  private readonly onActivity = (): void => this.resetTimer();

  start(): void {
    if (this.started || !this.auth.isAuthenticated()) {
      return;
    }
    this.started = true;
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, this.onActivity, { passive: true });
    }
    document.addEventListener('visibilitychange', this.onActivity);
    this.resetTimer();
  }

  stop(): void {
    if (!this.started) {
      return;
    }
    this.started = false;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    for (const event of ACTIVITY_EVENTS) {
      window.removeEventListener(event, this.onActivity);
    }
    document.removeEventListener('visibilitychange', this.onActivity);
  }

  private resetTimer(): void {
    if (!this.started) {
      return;
    }
    if (this.timer) {
      clearTimeout(this.timer);
    }
    this.timer = setTimeout(() => this.handleIdle(), IDLE_MS);
  }

  private handleIdle(): void {
    this.stop();
    if (this.auth.isAuthenticated()) {
      this.auth.logout({ reason: 'idle' });
    }
  }

  ngOnDestroy(): void {
    this.stop();
  }
}
