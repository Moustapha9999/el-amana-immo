import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RbcmChartSlice } from './rbcm.models';

export const RBCM_PALETTE = [
  '#1a5278',
  '#0f766e',
  '#c2410c',
  '#7c3aed',
  '#0891b2',
  '#b91c1c',
  '#64748b',
  '#ca8a04',
];

function echelle(max: number): number {
  if (max <= 5) return 5;
  const p = Math.pow(10, Math.floor(Math.log10(max)));
  const n = max / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

@Component({
  selector: 'bea-rbcm-bars',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (parts().length) {
      <svg class="bea-fx-chart bea-rbcm-chart" [attr.viewBox]="'0 0 ' + W + ' ' + H" role="img" [attr.aria-label]="titre()">
        @for (g of grille(); track g.y) {
          <line class="bea-fx-chart__grid" [attr.x1]="P" [attr.x2]="W - 8" [attr.y1]="g.y" [attr.y2]="g.y" />
          <text class="bea-fx-chart__axis" [attr.x]="P - 6" [attr.y]="g.y + 3" text-anchor="end">{{ g.label }}</text>
        }
        @for (b of barres(); track b.label) {
          <g>
            <title>{{ b.label }} : {{ b.value }}</title>
            <rect
              class="bea-fx-chart__bar bea-rbcm-bar"
              [attr.x]="b.x"
              [attr.y]="b.y"
              [attr.width]="b.w"
              [attr.height]="b.h"
              [attr.fill]="b.color"
              [style.animation-delay.ms]="b.i * 40"
            />
            <text class="bea-fx-chart__axis" [attr.x]="b.x + b.w / 2" [attr.y]="H - 10" text-anchor="middle">{{ b.short }}</text>
          </g>
        }
      </svg>
    } @else {
      <div class="bea-fo-empty bea-rbcm-empty"><mat-icon>insights</mat-icon>{{ vide() }}</div>
    }
  `,
  styles: `
    :host { display: block; }
    .bea-rbcm-bar {
      animation: bea-rbcm-rise 0.45s ease both;
      transform-origin: bottom;
    }
    @keyframes bea-rbcm-rise {
      from { opacity: 0; transform: scaleY(0.2); }
      to { opacity: 1; transform: scaleY(1); }
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-rbcm-bar { animation: none; }
    }
    .bea-rbcm-empty {
      display: flex; align-items: center; gap: 0.5rem; color: var(--bea-muted, #64748b);
      padding: 1.5rem; justify-content: center;
    }
  `,
})
export class RbcmBarsComponent {
  readonly parts = input<RbcmChartSlice[]>([]);
  readonly titre = input('Répartition');
  readonly vide = input('Aucune donnée');
  readonly W = 640;
  readonly H = 220;
  readonly P = 36;

  private readonly max = computed(() => echelle(Math.max(1, ...this.parts().map((p) => p.value))));

  readonly grille = computed(() => {
    const max = this.max();
    return [0, 0.5, 1].map((f) => ({
      y: 14 + (this.H - 42) * (1 - f),
      label: String(Math.round(max * f)),
    }));
  });

  readonly barres = computed(() => {
    const s = this.parts();
    const zone = this.W - this.P - 12;
    const pas = zone / Math.max(1, s.length);
    const w = Math.min(48, pas * 0.62);
    const hMax = this.H - 42;
    const base = 14 + hMax;
    const k = hMax / this.max();
    return s.map((p, i) => {
      const h = Math.max(0, p.value * k);
      return {
        i,
        label: p.label,
        short: p.label.length > 8 ? p.label.slice(0, 7) + '…' : p.label,
        value: p.value,
        x: this.P + i * pas + (pas - w) / 2,
        w,
        h,
        y: base - h,
        color: RBCM_PALETTE[i % RBCM_PALETTE.length],
      };
    });
  });
}

@Component({
  selector: 'bea-rbcm-donut',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (parts().length) {
      <div class="bea-fx-donut bea-rbcm-donut">
        <svg viewBox="0 0 120 120" role="img" [attr.aria-label]="titre()">
          <circle class="bea-fx-donut__track" cx="60" cy="60" r="46" />
          @for (s of segs(); track s.label) {
            <circle
              class="bea-fx-donut__seg bea-rbcm-seg"
              cx="60"
              cy="60"
              r="46"
              [attr.stroke]="s.color"
              [attr.stroke-dasharray]="s.dash"
              [attr.stroke-dashoffset]="s.offset"
              [style.animation-delay.ms]="s.i * 60"
            />
          }
          <text x="60" y="58" text-anchor="middle" class="bea-fx-donut__total">{{ centre() ?? total() }}</text>
          <text x="60" y="74" text-anchor="middle" class="bea-fx-donut__unit">{{ unite() }}</text>
        </svg>
        <ul class="bea-fx-donut__legend">
          @for (p of parts(); track p.label; let i = $index) {
            <li><i [style.background]="RBCM_PALETTE[i % RBCM_PALETTE.length]"></i>{{ p.label }} ({{ p.value }})</li>
          }
        </ul>
      </div>
    } @else {
      <div class="bea-fo-empty bea-rbcm-empty"><mat-icon>donut_large</mat-icon>{{ vide() }}</div>
    }
  `,
  styles: `
    :host { display: block; }
    .bea-rbcm-donut { display: flex; gap: 1rem; align-items: flex-start; flex-wrap: wrap; min-width: 0; }
    .bea-rbcm-donut svg { width: 140px; height: 140px; flex: 0 0 auto; }
    .bea-fx-donut__legend { flex: 1 1 8rem; min-width: 0; }
    .bea-fx-donut__legend li { overflow-wrap: anywhere; }
    .bea-rbcm-seg {
      fill: none; stroke-width: 14; transform: rotate(-90deg); transform-origin: 60px 60px;
      animation: bea-rbcm-draw 0.6s ease both;
    }
    @keyframes bea-rbcm-draw {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-rbcm-seg { animation: none; }
    }
    .bea-rbcm-empty {
      display: flex; align-items: center; gap: 0.5rem; color: var(--bea-muted, #64748b);
      padding: 1.5rem; justify-content: center;
    }
  `,
})
export class RbcmDonutComponent {
  readonly parts = input<RbcmChartSlice[]>([]);
  readonly titre = input('Répartition');
  readonly unite = input('');
  readonly centre = input<string | number | null>(null);
  readonly vide = input('Aucune donnée');
  readonly RBCM_PALETTE = RBCM_PALETTE;

  readonly total = computed(() => this.parts().reduce((a, p) => a + p.value, 0));

  readonly segs = computed(() => {
    const parts = this.parts();
    const sum = Math.max(1, this.total());
    const C = 2 * Math.PI * 46;
    let acc = 0;
    return parts.map((p, i) => {
      const len = (p.value / sum) * C;
      const offset = -acc;
      acc += len;
      return {
        i,
        label: p.label,
        color: RBCM_PALETTE[i % RBCM_PALETTE.length],
        dash: `${len} ${C - len}`,
        offset,
      };
    });
  });
}
