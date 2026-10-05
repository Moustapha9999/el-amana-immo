import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { formatMontant } from '../../shared/montant.pipe';

export interface SerieMois {
  label: string;
  montant: number;
  n1?: number;
}

const PALETTE = ['#1a5278', '#0f766e', '#c2410c', '#7c3aed', '#0891b2', '#b91c1c', '#64748b', '#ca8a04'];

function court(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} k`;
  return v.toLocaleString('fr-FR', { maximumFractionDigits: 0 });
}

/** Histogramme mensuel (année N et N-1 en option), SVG sans dépendance. */
@Component({
  selector: 'bea-fx-bars',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg class="bea-fx-chart" [attr.viewBox]="'0 0 ' + W + ' ' + H" role="img" [attr.aria-label]="titre()">
      @for (g of grille(); track g.y) {
        <line class="bea-fx-chart__grid" [attr.x1]="P" [attr.x2]="W - 8" [attr.y1]="g.y" [attr.y2]="g.y" />
        <text class="bea-fx-chart__axis" [attr.x]="P - 6" [attr.y]="g.y + 3" text-anchor="end">{{ g.label }}</text>
      }
      @for (b of barres(); track b.i) {
        <g class="bea-fx-chart__col" [class.is-active]="actif() === b.i + 1" (click)="choisir.emit(b.i + 1)">
          <title>{{ b.label }} : {{ b.titre }}</title>
          <rect class="bea-fx-chart__hit" [attr.x]="b.x - 4" [attr.y]="12" [attr.width]="b.w + 8" [attr.height]="H - 40" />
          @if (avecN1()) {
            <rect class="bea-fx-chart__bar bea-fx-chart__bar--n1" [attr.x]="b.x" [attr.y]="b.y1" [attr.width]="b.w / 2 - 1" [attr.height]="b.h1" [style.animation-delay.ms]="b.i * 35" />
            <rect class="bea-fx-chart__bar" [attr.x]="b.x + b.w / 2" [attr.y]="b.y" [attr.width]="b.w / 2 - 1" [attr.height]="b.h" [style.animation-delay.ms]="b.i * 35 + 60" />
          } @else {
            <rect class="bea-fx-chart__bar" [attr.x]="b.x" [attr.y]="b.y" [attr.width]="b.w" [attr.height]="b.h" [style.animation-delay.ms]="b.i * 35" />
          }
          <text class="bea-fx-chart__axis" [attr.x]="b.x + b.w / 2" [attr.y]="H - 12" text-anchor="middle">{{ b.label }}</text>
        </g>
      }
    </svg>
    @if (avecN1()) {
      <p class="bea-fx-chart__legend"><i class="is-n"></i> {{ legende()[0] }} <i class="is-n1"></i> {{ legende()[1] }}</p>
    }
  `,
})
export class FxBarsComponent {
  readonly series = input.required<SerieMois[]>();
  readonly avecN1 = input(false);
  readonly legende = input<[string, string]>(['Année N', 'Année N-1']);
  readonly actif = input<number | null>(null);
  readonly titre = input('Évolution mensuelle');
  readonly choisir = output<number>();

  readonly W = 640;
  readonly H = 220;
  readonly P = 46;

  private readonly max = computed(() =>
    Math.max(1, ...this.series().map((s) => Math.max(s.montant, this.avecN1() ? (s.n1 ?? 0) : 0))),
  );

  readonly grille = computed(() => {
    const max = this.max();
    return [0, 0.5, 1].map((f) => ({ y: 12 + (this.H - 40) * (1 - f), label: court(max * f) }));
  });

  readonly barres = computed(() => {
    const s = this.series();
    const zone = this.W - this.P - 12;
    const pas = zone / Math.max(1, s.length);
    const w = Math.min(34, pas * 0.62);
    const hMax = this.H - 40;
    return s.map((m, i) => {
      const h = Math.round((m.montant / this.max()) * hMax);
      const h1 = Math.round(((m.n1 ?? 0) / this.max()) * hMax);
      return {
        i,
        label: m.label,
        titre: formatMontant(m.montant) + (this.avecN1() ? ` (N-1 : ${formatMontant(m.n1 ?? 0)})` : ''),
        x: this.P + i * pas + (pas - w) / 2,
        w,
        h: Math.max(m.montant > 0 ? 2 : 0, h),
        y: 12 + hMax - Math.max(m.montant > 0 ? 2 : 0, h),
        h1: Math.max((m.n1 ?? 0) > 0 ? 2 : 0, h1),
        y1: 12 + hMax - Math.max((m.n1 ?? 0) > 0 ? 2 : 0, h1),
      };
    });
  });
}

export interface PartDonut {
  label: string;
  value: number;
  tone?: string;
}

/** Anneau de répartition (statuts, types de points…). */
@Component({
  selector: 'bea-fx-donut',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-fx-donut">
      <svg viewBox="0 0 120 120" role="img" [attr.aria-label]="titre()">
        <circle class="bea-fx-donut__track" cx="60" cy="60" r="46" />
        @for (s of segments(); track s.label) {
          <circle class="bea-fx-donut__seg" cx="60" cy="60" r="46" [attr.stroke]="s.color"
            [attr.stroke-dasharray]="s.dash + ' ' + (C - s.dash)" [attr.stroke-dashoffset]="-s.offset">
            <title>{{ s.label }} : {{ s.value }}</title>
          </circle>
        }
        <text x="60" y="58" text-anchor="middle" class="bea-fx-donut__total">{{ total() }}</text>
        <text x="60" y="74" text-anchor="middle" class="bea-fx-donut__unit">{{ unite() }}</text>
      </svg>
      <ul class="bea-fx-donut__legend">
        @for (s of segments(); track s.label) {
          <li><i [style.background]="s.color"></i>{{ s.label }} <strong>{{ s.value }}</strong></li>
        }
      </ul>
    </div>
  `,
})
export class FxDonutComponent {
  readonly parts = input.required<PartDonut[]>();
  readonly unite = input('factures');
  readonly titre = input('Répartition');
  readonly C = 2 * Math.PI * 46;

  readonly total = computed(() => this.parts().reduce((a, p) => a + p.value, 0));
  readonly segments = computed(() => {
    const total = this.total() || 1;
    let offset = 0;
    return this.parts()
      .filter((p) => p.value > 0)
      .map((p, i) => {
        const dash = (p.value / total) * this.C;
        const seg = { ...p, dash, offset, color: p.tone ?? PALETTE[i % PALETTE.length] };
        offset += dash;
        return seg;
      });
  });
}

/** Mini-courbe 12 mois (fiches point / agence). */
@Component({
  selector: 'bea-fx-spark',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg class="bea-fx-spark" viewBox="0 0 240 56" preserveAspectRatio="none" role="img" aria-label="Tendance 12 mois">
      @if (n1Path()) { <path class="bea-fx-spark__n1" [attr.d]="n1Path()" /> }
      <path class="bea-fx-spark__area" [attr.d]="aire()" />
      <path class="bea-fx-spark__line" [attr.d]="ligne()" />
    </svg>
  `,
})
export class FxSparkComponent {
  readonly values = input.required<number[]>();
  readonly n1 = input<number[] | null>(null);

  private readonly max = computed(() => Math.max(1, ...this.values(), ...(this.n1() ?? [])));

  private points(vals: number[]): [number, number][] {
    const n = Math.max(1, vals.length - 1);
    return vals.map((v, i) => [(i / n) * 240, 52 - (v / this.max()) * 46]);
  }

  readonly ligne = computed(() => this.points(this.values()).map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' '));
  readonly aire = computed(() => `${this.ligne()} L240,56 L0,56 Z`);
  readonly n1Path = computed(() => {
    const v = this.n1();
    if (!v || !v.some((x) => x > 0)) return '';
    return this.points(v).map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  });
}
