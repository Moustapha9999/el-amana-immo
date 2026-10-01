import { DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  Input,
  OnChanges,
  SimpleChanges,
  computed,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

export interface ChartPoint {
  label: string;
  value: number;
  key?: string;
  queryParams?: Record<string, string>;
}

export interface OcrSlice {
  label: string;
  value: number;
  key: string;
  color: string;
}

const COLORS = ['#2874a6', '#3498db', '#1a5278', '#5dade2', '#21618c', '#154360', '#7fb3d5', '#94a3b8'];

@Component({
  selector: 'bea-archives-charts',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, RouterLink],
  template: `
    <div class="bea-arch-charts" [class.bea-arch-charts--ready]="ready()">
      <article class="bea-arch-charts__card">
        <header>
          <p class="bea-arch-charts__kicker">Évolution</p>
          <h3>Évolution documentaire</h3>
        </header>
        @if (monthSparse()) {
          <div class="bea-arch-charts__sparse">
            @for (p of monthNonZero(); track p.label) {
              <p class="bea-arch-charts__sparse-main">
                <span>{{ p.label }}</span>
                <strong>● {{ p.value | number }} document{{ p.value > 1 ? 's' : '' }}</strong>
              </p>
            }
            <p class="bea-arch-charts__empty">
              Pas encore assez de données pour afficher une évolution significative.
            </p>
            <div class="bea-arch-charts__mini-months">
              @for (d of monthLine().dots; track d.label) {
                <span [class.bea-arch-charts__mini--on]="d.value > 0">
                  <em>{{ shortMonth(d.label) }}</em>
                  <b>{{ d.value }}</b>
                </span>
              }
            </div>
          </div>
        } @else if (monthLine().dots.length) {
          <div class="bea-arch-charts__line">
            <svg viewBox="0 0 100 56" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <linearGradient id="archAreaFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#21618c" stop-opacity="0.28" />
                  <stop offset="100%" stop-color="#1a5278" stop-opacity="0.02" />
                </linearGradient>
              </defs>
              <polygon [attr.points]="monthLine().area" fill="url(#archAreaFill)" />
              <polyline [attr.points]="monthLine().line" fill="none" stroke="#21618c" stroke-width="1.2" />
              @for (d of monthLine().dots; track d.label) {
                <circle [attr.cx]="d.x" [attr.cy]="d.y" r="1.4" fill="#1a5278">
                  <title>{{ d.label }} : {{ d.value }}</title>
                </circle>
              }
            </svg>
            <div class="bea-arch-charts__xlabels">
              @for (d of monthLine().dots; track d.label) {
                <span>{{ shortMonth(d.label) }}</span>
              }
            </div>
          </div>
        } @else {
          <p class="bea-arch-charts__empty">Aucun document sur la période.</p>
        }
      </article>

      <article class="bea-arch-charts__card">
        <header>
          <p class="bea-arch-charts__kicker">Répartition</p>
          <h3>{{ moduleTitle }}</h3>
        </header>
        <div class="bea-arch-charts__bars">
          @for (b of moduleBars(); track b.label) {
            <a
              class="bea-arch-charts__bar-row"
              [routerLink]="listPath"
              [queryParams]="b.queryParams || {}"
            >
              <span class="bea-arch-charts__bar-label">{{ b.label }}</span>
              <span class="bea-arch-charts__bar-track">
                <span class="bea-arch-charts__bar-fill" [style.width.%]="b.pct"></span>
              </span>
              <strong>{{ b.value | number }}</strong>
            </a>
          } @empty {
            <p class="bea-arch-charts__empty">Aucune donnée.</p>
          }
        </div>
      </article>

      <article class="bea-arch-charts__card">
        <header>
          <p class="bea-arch-charts__kicker">Types</p>
          <h3>Documents par type</h3>
        </header>
        @if (typeDonut().length) {
          <div class="bea-arch-charts__donut-wrap">
            <svg viewBox="0 0 42 42" class="bea-arch-charts__donut" aria-hidden="true">
              @for (s of typeDonut(); track s.label) {
                <circle
                  cx="21"
                  cy="21"
                  r="15.9"
                  fill="transparent"
                  [attr.stroke]="s.color"
                  stroke-width="6"
                  [attr.stroke-dasharray]="s.dash"
                  [attr.stroke-dashoffset]="s.offset"
                >
                  <title>{{ s.label }} : {{ s.value }}</title>
                </circle>
              }
            </svg>
            <ul class="bea-arch-charts__legend">
              @for (s of typeDonut(); track s.label) {
                <li>
                  <a [routerLink]="listPath" [queryParams]="{ doc_type: s.key }">
                    <i [style.background]="s.color"></i>{{ s.label }}
                    <strong>{{ s.value | number }}</strong>
                  </a>
                </li>
              }
            </ul>
          </div>
        } @else {
          <p class="bea-arch-charts__empty">Aucun type renseigné.</p>
        }
      </article>

      <article class="bea-arch-charts__card">
        <header>
          <p class="bea-arch-charts__kicker">OCR</p>
          <h3>État du traitement</h3>
        </header>
        <div class="bea-arch-charts__ocr">
          @for (s of ocrSlices(); track s.key) {
            <a
              class="bea-arch-charts__ocr-item"
              [routerLink]="listPath"
              [queryParams]="{ ocr_status: s.key }"
            >
              <span class="bea-ocr-badge" [attr.data-status]="s.key">{{ s.label }}</span>
              <strong>{{ s.value | number }}</strong>
            </a>
          }
        </div>
      </article>
    </div>
  `,
  styles: `
    .bea-arch-charts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1rem;
      margin-top: 1rem;
      opacity: 0;
      transform: translateY(6px);
      transition: opacity 0.45s ease, transform 0.45s ease;
    }
    .bea-arch-charts--ready {
      opacity: 1;
      transform: none;
    }
    .bea-arch-charts__card {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 0.75rem;
      padding: 1rem 1.1rem;
      box-shadow: 0 1px 2px rgb(15 23 42 / 4%);
    }
    .bea-arch-charts__kicker {
      margin: 0;
      font-size: 0.72rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: #64748b;
    }
    .bea-arch-charts__card h3 {
      margin: 0.15rem 0 0.85rem;
      font-size: 1rem;
      color: #0f172a;
    }
    .bea-arch-charts__empty {
      margin: 0;
      color: #94a3b8;
      font-size: 0.88rem;
    }
    .bea-arch-charts__sparse {
      display: grid;
      gap: 0.65rem;
    }
    .bea-arch-charts__sparse-main {
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      font-size: 0.95rem;
      color: #0f172a;
    }
    .bea-arch-charts__sparse-main strong {
      color: #1a5278;
      font-weight: 650;
    }
    .bea-arch-charts__mini-months {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 0.35rem;
      margin-top: 0.25rem;
    }
    .bea-arch-charts__mini-months span {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.1rem;
      padding: 0.3rem 0.15rem;
      border-radius: 0.4rem;
      background: #f8fafc;
      font-size: 0.65rem;
      color: #94a3b8;
    }
    .bea-arch-charts__mini-months em {
      font-style: normal;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .bea-arch-charts__mini-months b {
      font-size: 0.78rem;
      font-weight: 650;
      color: #64748b;
    }
    .bea-arch-charts__mini--on {
      background: #eff6ff !important;
      color: #1e40af !important;
    }
    .bea-arch-charts__mini--on b {
      color: #1a5278 !important;
    }
    .bea-arch-charts__line svg {
      width: 100%;
      height: 140px;
      display: block;
    }
    .bea-arch-charts__xlabels {
      display: flex;
      justify-content: space-between;
      gap: 0.25rem;
      margin-top: 0.35rem;
      font-size: 0.68rem;
      color: #64748b;
    }
    .bea-arch-charts__bars {
      display: grid;
      gap: 0.55rem;
    }
    .bea-arch-charts__bar-row {
      display: grid;
      grid-template-columns: 7rem 1fr 2.5rem;
      gap: 0.5rem;
      align-items: center;
      text-decoration: none;
      color: inherit;
    }
    .bea-arch-charts__bar-label {
      font-size: 0.82rem;
      color: #334155;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bea-arch-charts__bar-track {
      height: 0.55rem;
      border-radius: 999px;
      background: #e2e8f0;
      overflow: hidden;
    }
    .bea-arch-charts__bar-fill {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #1a5278, #3498db);
      transition: width 0.55s ease;
    }
    .bea-arch-charts__donut-wrap {
      display: flex;
      gap: 1rem;
      align-items: center;
    }
    .bea-arch-charts__donut {
      width: 110px;
      height: 110px;
      transform: rotate(-90deg);
    }
    .bea-arch-charts__legend {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.35rem;
      flex: 1;
    }
    .bea-arch-charts__legend a {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      text-decoration: none;
      color: #334155;
      font-size: 0.82rem;
    }
    .bea-arch-charts__legend i {
      width: 0.65rem;
      height: 0.65rem;
      border-radius: 50%;
      display: inline-block;
    }
    .bea-arch-charts__legend strong {
      margin-left: auto;
    }
    .bea-arch-charts__ocr {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.55rem;
    }
    .bea-arch-charts__ocr-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.55rem 0.65rem;
      border-radius: 0.55rem;
      background: #f8fafc;
      text-decoration: none;
      color: inherit;
      transition: background 0.2s ease;
    }
    .bea-arch-charts__ocr-item:hover {
      background: #eff6ff;
    }
    .bea-ocr-badge {
      display: inline-block;
      font-size: 0.72rem;
      font-weight: 650;
      padding: 0.15rem 0.45rem;
      border-radius: 0.35rem;
      background: #e2e8f0;
      color: #475569;
    }
    .bea-ocr-badge[data-status='pending'] { background: #fef3c7; color: #92400e; }
    .bea-ocr-badge[data-status='processing'] { background: #dbeafe; color: #1e40af; }
    .bea-ocr-badge[data-status='done'] { background: #dcfce7; color: #166534; }
    .bea-ocr-badge[data-status='failed'] { background: #fee2e2; color: #991b1b; }
    @media (max-width: 960px) {
      .bea-arch-charts { grid-template-columns: 1fr; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-arch-charts,
      .bea-arch-charts__bar-fill {
        transition: none;
      }
    }
  `,
})
export class ArchivesChartsComponent implements OnChanges {
  @Input() months: ChartPoint[] = [];
  @Input() modules: ChartPoint[] = [];
  @Input() types: ChartPoint[] = [];
  @Input() ocr: OcrSlice[] = [];
  @Input() listPath = '/archives-mg/documents';
  @Input() moduleTitle = 'Documents par module';

  private readonly tick = signal(0);
  readonly ready = signal(false);

  readonly monthLine = computed(() => this.buildLine(this.months));
  readonly monthNonZero = computed(() => this.months.filter((p) => p.value > 0));
  /** Moins de 2 mois non nuls → état intelligent (évite la « montagne » à 1 point). */
  readonly monthSparse = computed(
    () => this.months.length > 0 && this.monthNonZero().length < 2,
  );
  readonly moduleBars = computed(() => this.buildBars(this.modules));
  readonly typeDonut = computed(() => this.buildDonut(this.types));
  readonly ocrSlices = computed(() => this.ocr);

  ngOnChanges(changes: SimpleChanges): void {
    this.tick.update((n) => n + 1);
    this.ready.set(false);
    requestAnimationFrame(() => this.ready.set(true));
  }

  shortMonth(label: string): string {
    const m = label.match(/^(\d{1,2})\/(\d{2,4})$/);
    if (!m) return label.slice(0, 3);
    const names = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'];
    const idx = Math.max(1, Math.min(12, Number(m[1]))) - 1;
    return names[idx];
  }

  private buildLine(points: ChartPoint[]) {
    if (!points.length) return { line: '', area: '', dots: [] as { x: number; y: number; label: string; value: number }[] };
    const max = Math.max(...points.map((p) => p.value), 1);
    const n = points.length;
    const dots = points.map((p, i) => {
      const x = n === 1 ? 50 : (i / (n - 1)) * 100;
      const y = 50 - (p.value / max) * 44;
      return { x, y, label: p.label, value: p.value };
    });
    const line = dots.map((d) => `${d.x},${d.y}`).join(' ');
    const area = `0,56 ${line} 100,56`;
    return { line, area, dots };
  }

  private buildBars(points: ChartPoint[]) {
    const max = Math.max(...points.map((p) => p.value), 1);
    return points.map((p) => ({
      ...p,
      pct: (p.value / max) * 100,
    }));
  }

  private buildDonut(points: ChartPoint[]) {
    const total = points.reduce((s, p) => s + p.value, 0) || 1;
    const C = 2 * Math.PI * 15.9;
    let offset = 0;
    return points.map((p, i) => {
      const len = (p.value / total) * C;
      const seg = {
        label: p.label,
        value: p.value,
        key: p.key || p.label,
        color: COLORS[i % COLORS.length],
        dash: `${len} ${C - len}`,
        offset: -offset,
      };
      offset += len;
      return seg;
    });
  }
}
