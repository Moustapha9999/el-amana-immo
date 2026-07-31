import { Injectable, OnDestroy, computed, signal } from '@angular/core';

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** Horloge système (fuseau local) pour affichage barre supérieure. */
@Injectable({ providedIn: 'root' })
export class SystemClockService implements OnDestroy {
  private readonly nowSignal = signal(new Date());
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly dateDisplay = computed(() => {
    const d = this.nowSignal();
    return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
  });

  readonly timeDisplay = computed(() => {
    const d = this.nowSignal();
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  });

  constructor() {
    this.nowSignal.set(new Date());
    this.timer = setInterval(() => this.nowSignal.set(new Date()), 1000);
  }

  ngOnDestroy(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
