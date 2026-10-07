import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { Groupe } from './formation.models';

export const FO_PALETTE = ['#1a5278', '#0f766e', '#c2410c', '#7c3aed', '#0891b2', '#b91c1c', '#64748b', '#ca8a04'];

function nb(v: number): string {
  return v.toLocaleString('fr-FR');
}

function echelle(max: number): number {
  if (max <= 5) return 5;
  const p = Math.pow(10, Math.floor(Math.log10(max)));
  const n = max / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

/** Histogramme empilé présents / absents / non saisis (par année ou par mois). */
@Component({
  selector: 'bea-fo-stack',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (series().length) {
      <svg class="bea-fx-chart" [attr.viewBox]="'0 0 ' + W + ' ' + H" role="img" [attr.aria-label]="titre()">
        @for (g of grille(); track g.y) {
          <line class="bea-fx-chart__grid" [attr.x1]="P" [attr.x2]="W - 8" [attr.y1]="g.y" [attr.y2]="g.y" />
          <text class="bea-fx-chart__axis" [attr.x]="P - 6" [attr.y]="g.y + 3" text-anchor="end">{{ g.label }}</text>
        }
        @for (b of barres(); track b.label) {
          <g class="bea-fx-chart__col" [class.is-active]="actif() === b.label" (click)="choisir.emit(b.label)">
            <title>{{ b.label }} — {{ b.f }} formation(s), {{ b.total }} participation(s) : {{ b.p }} présent(s), {{ b.a }} absent(s){{ b.n ? ', ' + b.n + ' non saisie(s)' : '' }}</title>
            <rect class="bea-fx-chart__hit" [attr.x]="b.x - 4" y="12" [attr.width]="b.w + 8" [attr.height]="H - 40" />
            @if (b.hn) { <rect class="bea-fx-chart__bar bea-fo-bar--n" [attr.x]="b.x" [attr.y]="b.yn" [attr.width]="b.w" [attr.height]="b.hn" [style.animation-delay.ms]="b.i * 40 + 80" /> }
            @if (b.ha) { <rect class="bea-fx-chart__bar bea-fo-bar--a" [attr.x]="b.x" [attr.y]="b.ya" [attr.width]="b.w" [attr.height]="b.ha" [style.animation-delay.ms]="b.i * 40 + 40" /> }
            @if (b.hp) { <rect class="bea-fx-chart__bar bea-fo-bar--p" [attr.x]="b.x" [attr.y]="b.yp" [attr.width]="b.w" [attr.height]="b.hp" [style.animation-delay.ms]="b.i * 40" /> }
            @if (b.total && valeurs()) {
              <text class="bea-fo-chart-val" [attr.x]="b.x + b.w / 2" [attr.y]="b.top - 4" text-anchor="middle">{{ b.total }}</text>
            }
            <text class="bea-fx-chart__axis" [attr.x]="b.x + b.w / 2" [attr.y]="H - 12" text-anchor="middle">{{ b.label }}</text>
          </g>
        }
      </svg>
      <p class="bea-fo-legend">
        <span><i style="background:#15803d"></i>Présents</span>
        <span><i style="background:#dc2626"></i>Absents</span>
        <span><i style="background:#cbd5e1"></i>Non saisis</span>
      </p>
    } @else {
      <div class="bea-fo-empty"><mat-icon>insights</mat-icon>Aucune donnée sur la période</div>
    }
  `,
  imports: [MatIconModule],
})
export class FoStackComponent {
  readonly series = input.required<Groupe[]>();
  readonly titre = input('Participations');
  readonly actif = input<string | null>(null);
  readonly valeurs = input(true);
  readonly choisir = output<string>();

  readonly W = 640;
  readonly H = 230;
  readonly P = 40;

  private readonly max = computed(() => echelle(Math.max(1, ...this.series().map((s) => s.participants))));

  readonly grille = computed(() => {
    const max = this.max();
    return [0, 0.25, 0.5, 0.75, 1].map((f) => ({ y: 14 + (this.H - 42) * (1 - f), label: nb(Math.round(max * f)) }));
  });

  readonly barres = computed(() => {
    const s = this.series();
    const zone = this.W - this.P - 12;
    const pas = zone / Math.max(1, s.length);
    const w = Math.min(46, pas * 0.6);
    const hMax = this.H - 42;
    const base = 14 + hMax;
    const k = hMax / this.max();
    return s.map((g, i) => {
      const n = Math.max(0, g.participants - g.presents - g.absents);
      const hp = g.presents * k;
      const ha = g.absents * k;
      const hn = n * k;
      const x = this.P + i * pas + (pas - w) / 2;
      return {
        i, label: g.libelle, f: g.formations, p: g.presents, a: g.absents, n, total: g.participants, x, w,
        hp, ha, hn, yp: base - hp, ya: base - hp - ha, yn: base - hp - ha - hn, top: base - hp - ha - hn,
      };
    });
  });
}

export interface PartFo {
  label: string;
  value: number;
  color?: string;
  cle?: string;
}

/** Anneau de répartition avec valeur centrale (pourcentage ou total). */
@Component({
  selector: 'bea-fo-donut',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-fx-donut">
      <svg viewBox="0 0 120 120" role="img" [attr.aria-label]="titre()">
        <circle class="bea-fx-donut__track" cx="60" cy="60" r="46" />
        @for (s of segments(); track s.label) {
          <circle class="bea-fx-donut__seg" cx="60" cy="60" r="46" [attr.stroke]="s.color"
            [attr.stroke-dasharray]="s.dash + ' ' + (C - s.dash)" [attr.stroke-dashoffset]="-s.offset"
            [style.animation-delay.ms]="s.i * 120" (click)="choisir.emit(s.cle ?? s.label)" style="cursor:pointer">
            <title>{{ s.label }} : {{ s.value }} ({{ s.pct }} %)</title>
          </circle>
        }
        <text x="60" y="58" text-anchor="middle" class="bea-fx-donut__total">{{ centre() ?? total() }}</text>
        <text x="60" y="74" text-anchor="middle" class="bea-fx-donut__unit">{{ unite() }}</text>
      </svg>
      <ul class="bea-fx-donut__legend">
        @for (s of tous(); track s.label) {
          <li><i [style.background]="s.color"></i>{{ s.label }} <strong>{{ s.value }}</strong></li>
        }
      </ul>
    </div>
  `,
})
export class FoDonutComponent {
  readonly parts = input.required<PartFo[]>();
  readonly unite = input('');
  readonly titre = input('Répartition');
  readonly centre = input<string | null>(null);
  readonly choisir = output<string>();
  readonly C = 2 * Math.PI * 46;

  readonly total = computed(() => this.parts().reduce((a, p) => a + p.value, 0));
  readonly tous = computed(() => this.parts().map((p, i) => ({ ...p, color: p.color ?? FO_PALETTE[i % FO_PALETTE.length] })));
  readonly segments = computed(() => {
    const total = this.total() || 1;
    let offset = 0;
    return this.tous()
      .filter((p) => p.value > 0)
      .map((p, i) => {
        const dash = (p.value / total) * this.C;
        const seg = { ...p, i, dash, offset, pct: Math.round((p.value * 1000) / total) / 10 };
        offset += dash;
        return seg;
      });
  });
}

/** Barres horizontales : présents / absents / non saisis par dimension, ou valeur simple. */
@Component({
  selector: 'bea-fo-hbars',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (lignes().length) {
      <ul class="bea-fo-hbars">
        @for (l of lignes(); track l.libelle; let i = $index) {
          <li [style.--i]="i" [class.is-click]="cliquable()" (click)="cliquable() && choisir.emit(l.libelle)">
            <span class="bea-fo-hbars__label" [title]="l.libelle">{{ l.libelle }}</span>
            <span class="bea-fo-hbars__track" [title]="l.titre">
              @if (mode() === 'presence') {
                <i class="is-p" [style.width.%]="l.wp"></i><i class="is-a" [style.width.%]="l.wa"></i><i class="is-n" [style.width.%]="l.wn"></i>
              } @else {
                <i class="is-v" [style.width.%]="l.wv"></i>
              }
            </span>
            <span class="bea-fo-hbars__value">{{ l.valeur }}@if (l.sous) {<small>{{ l.sous }}</small>}</span>
          </li>
        }
      </ul>
      @if (reste() > 0) {
        <p class="bea-fo-legend">+ {{ reste() }} autre(s) — voir le reporting détaillé</p>
      } @else if (mode() === 'presence') {
        <p class="bea-fo-legend">
          <span><i style="background:#15803d"></i>Présents</span>
          <span><i style="background:#f87171"></i>Absents</span>
          <span><i style="background:#cbd5e1"></i>Non saisis</span>
        </p>
      }
    } @else {
      <div class="bea-fo-empty"><mat-icon>bar_chart</mat-icon>Aucune donnée</div>
    }
  `,
  imports: [MatIconModule],
})
export class FoHBarsComponent {
  readonly groupes = input<Groupe[]>([]);
  readonly valeursSimples = input<{ libelle: string; valeur: number }[] | null>(null);
  readonly mode = input<'presence' | 'valeur'>('presence');
  readonly limite = input(8);
  readonly cliquable = input(false);
  readonly unite = input('');
  readonly choisir = output<string>();

  private readonly source = computed(() => {
    const simples = this.valeursSimples();
    if (simples) return simples.map((s) => ({ libelle: s.libelle, total: s.valeur, p: 0, a: 0, taux: null as number | null }));
    return this.groupes().map((g) => ({ libelle: g.libelle, total: g.participants, p: g.presents, a: g.absents, taux: g.taux }));
  });

  readonly reste = computed(() => Math.max(0, this.source().length - this.limite()));

  readonly lignes = computed(() => {
    const src = this.source().slice(0, this.limite());
    const max = Math.max(1, ...src.map((s) => s.total));
    return src.map((s) => {
      const n = Math.max(0, s.total - s.p - s.a);
      return {
        libelle: s.libelle,
        wp: (s.p / max) * 100,
        wa: (s.a / max) * 100,
        wn: (n / max) * 100,
        wv: (s.total / max) * 100,
        valeur: nb(s.total) + (this.unite() ? ` ${this.unite()}` : ''),
        sous: this.mode() === 'presence' && s.taux !== null ? `${s.taux.toLocaleString('fr-FR')} %` : '',
        titre: this.mode() === 'presence' ? `${s.p} présent(s), ${s.a} absent(s), ${n} non saisi(s)` : `${s.total}`,
      };
    });
  });
}

/** Jauge circulaire de couverture. */
@Component({
  selector: 'bea-fo-gauge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-fo-gauge">
      <svg viewBox="0 0 120 120" role="img" [attr.aria-label]="libelle()">
        <circle class="bea-fo-gauge__track" cx="60" cy="60" r="48" />
        <circle class="bea-fo-gauge__val" cx="60" cy="60" r="48" [attr.stroke]="couleur()"
          [attr.stroke-dasharray]="dash() + ' ' + C" [style.--fo-len]="C" />
        <text x="60" y="62" text-anchor="middle" class="bea-fo-gauge__pct">{{ texte() }}</text>
        <text x="60" y="77" text-anchor="middle" class="bea-fo-gauge__unit">{{ libelle() }}</text>
      </svg>
      <div class="bea-fo-gauge__txt"><ng-content /></div>
    </div>
  `,
})
export class FoGaugeComponent {
  readonly valeur = input<number | null>(null);
  readonly libelle = input('couverture');
  readonly C = 2 * Math.PI * 48;
  readonly dash = computed(() => (Math.min(100, Math.max(0, this.valeur() ?? 0)) / 100) * this.C);
  readonly texte = computed(() => (this.valeur() === null ? '—' : `${Math.round(this.valeur()!)} %`));
  readonly couleur = computed(() => {
    const v = this.valeur() ?? 0;
    return v >= 75 ? '#15803d' : v >= 50 ? '#0891b2' : v >= 25 ? '#c2410c' : '#b91c1c';
  });
}

/** Courbe mensuelle : participations (aire) et présents (ligne). */
@Component({
  selector: 'bea-fo-line',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg class="bea-fo-line" [attr.viewBox]="'0 0 ' + W + ' ' + H" role="img" aria-label="Évolution mensuelle">
      <defs>
        <linearGradient id="beaFoLineGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#1a5278" stop-opacity="0.28" />
          <stop offset="100%" stop-color="#1a5278" stop-opacity="0.02" />
        </linearGradient>
      </defs>
      @for (g of grille(); track g.y) {
        <line class="bea-fx-chart__grid" [attr.x1]="P" [attr.x2]="W - 10" [attr.y1]="g.y" [attr.y2]="g.y" />
        <text class="bea-fx-chart__axis" [attr.x]="P - 6" [attr.y]="g.y + 3" text-anchor="end">{{ g.label }}</text>
      }
      <path class="bea-fo-line__area" [attr.d]="aire()" />
      <path class="bea-fo-line__path" [attr.d]="ligne()" [style.--fo-len]="2000" />
      <path class="bea-fo-line__path bea-fo-line__path--p" [attr.d]="lignePresents()" stroke-dasharray="4 3" />
      @for (pt of points(); track pt.label; let i = $index) {
        <circle class="bea-fo-line__dot" [attr.cx]="pt.x" [attr.cy]="pt.y" r="3.5" [style.animation-delay.ms]="300 + i * 40"
          (click)="choisir.emit(pt.cle)">
          <title>{{ pt.label }} : {{ pt.v }} participation(s), {{ pt.p }} présent(s), {{ pt.f }} formation(s)</title>
        </circle>
        <text class="bea-fx-chart__axis" [attr.x]="pt.x" [attr.y]="H - 10" text-anchor="middle">{{ pt.label }}</text>
      }
    </svg>
    <p class="bea-fo-legend">
      <span><i style="background:#1a5278"></i>Participations</span>
      <span><i style="background:#15803d"></i>Présents</span>
    </p>
  `,
})
export class FoLineComponent {
  readonly series = input.required<Groupe[]>();
  readonly choisir = output<string>();
  readonly W = 640;
  readonly H = 210;
  readonly P = 36;

  private readonly max = computed(() => echelle(Math.max(1, ...this.series().map((s) => s.participants))));
  readonly grille = computed(() =>
    [0, 0.5, 1].map((f) => ({ y: 14 + (this.H - 40) * (1 - f), label: nb(Math.round(this.max() * f)) })),
  );
  readonly points = computed(() => {
    const s = this.series();
    const n = Math.max(1, s.length - 1);
    const zone = this.W - this.P - 24;
    const h = this.H - 40;
    return s.map((g, i) => ({
      label: g.libelle,
      cle: g.cle ?? g.libelle,
      v: g.participants,
      p: g.presents,
      f: g.formations,
      x: this.P + 8 + (i / n) * zone,
      y: 14 + h - (g.participants / this.max()) * h,
      yp: 14 + h - (g.presents / this.max()) * h,
    }));
  });
  readonly ligne = computed(() => this.points().map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '));
  readonly lignePresents = computed(() => this.points().map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.yp.toFixed(1)}`).join(' '));
  readonly aire = computed(() => {
    const pts = this.points();
    if (!pts.length) return '';
    const bas = this.H - 26;
    return `${this.ligne()} L${pts[pts.length - 1]!.x.toFixed(1)},${bas} L${pts[0]!.x.toFixed(1)},${bas} Z`;
  });
}
