import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { PageHeaderComponent } from '../shared/page-header.component';

interface DashboardKpi {
  nombre_immobilisations: number;
  valeur_brute_totale: number;
  vnc_totale: number;
  dotation_periode: number;
  annee_reference: number;
}
interface ChartPoint {
  label: string;
  value: number;
  key: string;
}
interface DashboardFiltresActifs {
  statut: string | null;
  famille: string | null;
  mois: number | null;
}
interface DashboardCharts {
  par_statut: ChartPoint[];
  par_famille: ChartPoint[];
  dotations_mensuelles: ChartPoint[];
  evolution_vnc: ChartPoint[];
  composition: { valeur_brute: number; cumul_amortissement: number; vnc: number };
  filtres_actifs: DashboardFiltresActifs;
}
interface BarRow extends ChartPoint {
  pct: number;
}
interface DonutSegment {
  label: string;
  value: number;
  key: string;
  pct: number;
  color: string;
  dash: string;
  offset: number;
}
interface LinePoint {
  label: string;
  value: number;
  key: string;
  x: number;
  y: number;
}
interface ChartFilter {
  statut?: string;
  famille?: string;
  mois?: number;
}

/** Palette BEA (bleus institutionnels) */
const CHART_COLORS = ['#2874a6', '#3498db', '#1a5278', '#5dade2', '#21618c', '#154360', '#7fb3d5', '#94a3b8'];

@Component({
  selector: 'app-dashboard',
  imports: [DecimalPipe, MontantPipe, MatIconModule, MatCardModule, MatButtonModule, PageHeaderComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly kpi = signal<DashboardKpi | null>(null);
  readonly charts = signal<DashboardCharts | null>(null);
  readonly loading = signal(false);
  readonly filter = signal<ChartFilter>({});
  readonly hasActiveFilters = computed(() => {
    const f = this.filter();
    return !!(f.statut || f.famille || f.mois);
  });
  readonly statutDonut = computed(() => this.buildDonut(this.charts()?.par_statut ?? []));
  readonly statutTotal = computed(() => this.statutDonut().reduce((s, seg) => s + seg.value, 0));
  /** Allocation type Meridian : répartition par famille */
  readonly familleDonut = computed(() => this.buildDonut(this.charts()?.par_famille ?? []));
  readonly familleBars = computed(() => this.buildBars(this.charts()?.par_famille ?? []));
  readonly dotationBars = computed(() => this.buildBars(this.charts()?.dotations_mensuelles ?? []));
  readonly vncLine = computed(() => this.buildLine(this.charts()?.evolution_vnc ?? []));
  readonly vncDeltaPct = computed(() => {
    const pts = this.charts()?.evolution_vnc ?? [];
    if (pts.length < 2) {
      return null;
    }
    const first = pts[0].value;
    const last = pts[pts.length - 1].value;
    if (!Number.isFinite(first) || first === 0) {
      return null;
    }
    return ((last - first) / Math.abs(first)) * 100;
  });
  readonly compositionBars = computed(() => {
    const c = this.charts()?.composition;
    if (!c) {
      return [];
    }
    const max = Math.max(c.valeur_brute, c.cumul_amortissement, c.vnc, 1);
    return [
      { label: 'Valeur brute', value: c.valeur_brute, pct: (c.valeur_brute / max) * 100, key: '' },
      { label: 'Amort. cumulé', value: c.cumul_amortissement, pct: (c.cumul_amortissement / max) * 100, key: '' },
      { label: 'VNC', value: c.vnc, pct: (c.vnc / max) * 100, key: '' },
    ];
  });
  ngOnInit(): void {
    this.loadDashboard();
  }
  loadDashboard(): void {
    const params = this.buildQueryParams();
    this.loading.set(true);
    let pending = 2;
    const done = () => {
      pending -= 1;
      if (pending <= 0) {
        this.loading.set(false);
      }
    };
    this.api.get<DashboardKpi>('/dashboard/kpi', params).subscribe({
      next: (data) => {
        this.kpi.set(data);
        done();
      },
      error: () => done(),
    });
    this.api.get<DashboardCharts>('/dashboard/charts', params).subscribe({
      next: (data) => {
        this.charts.set(data);
        done();
      },
      error: () => done(),
    });
  }
  resetFilters(): void {
    this.filter.set({});
    this.loadDashboard();
  }
  toggleStatut(key: string): void {
    this.filter.update((f) => ({
      ...f,
      statut: f.statut === key ? undefined : key,
    }));
    this.loadDashboard();
  }
  toggleFamille(key: string): void {
    this.filter.update((f) => ({
      ...f,
      famille: f.famille === key ? undefined : key,
    }));
    this.loadDashboard();
  }
  toggleMois(key: string): void {
    const n = Number(key);
    this.filter.update((f) => ({
      ...f,
      mois: f.mois === n ? undefined : n,
    }));
    this.loadDashboard();
  }
  isStatutSelected(key: string): boolean {
    return this.filter().statut === key;
  }
  isFamilleSelected(key: string): boolean {
    return this.filter().famille === key;
  }
  isMoisSelected(key: string): boolean {
    return this.filter().mois === Number(key);
  }
  chartExerciceLabel(): string {
    const k = this.kpi();
    return k != null ? String(k.annee_reference) : 'exercice';
  }
  statutFilterLabel(): string {
    const key = this.filter().statut;
    if (!key) {
      return '';
    }
    return this.statutDonut().find((s) => s.key === key)?.label ?? key;
  }
  moisFilterLabel(): string {
    const m = this.filter().mois;
    if (!m) {
      return '';
    }
    const pt = this.charts()?.dotations_mensuelles.find((p) => Number(p.key) === m);
    return pt?.label ?? String(m);
  }
  isDimmed(kind: 'statut' | 'famille' | 'mois', key: string): boolean {
    const f = this.filter();
    if (kind === 'statut' && f.statut && f.statut !== key) {
      return true;
    }
    if (kind === 'famille' && f.famille && f.famille !== key) {
      return true;
    }
    if (kind === 'mois' && f.mois && f.mois !== Number(key)) {
      return true;
    }
    return false;
  }
  private buildQueryParams(): Record<string, string | number> | undefined {
    const f = this.filter();
    const params: Record<string, string | number> = {};
    if (f.statut) {
      params['statut'] = f.statut;
    }
    if (f.famille) {
      params['famille'] = f.famille;
    }
    if (f.mois) {
      params['mois'] = f.mois;
    }
    return Object.keys(params).length ? params : undefined;
  }
  private buildBars(points: ChartPoint[]): BarRow[] {
    const max = Math.max(...points.map((p) => p.value), 1);
    return points.map((p) => ({ ...p, pct: (p.value / max) * 100 }));
  }
  private buildDonut(points: ChartPoint[]): DonutSegment[] {
    const total = points.reduce((s, p) => s + p.value, 0);
    if (total <= 0) {
      return [];
    }
    const circumference = 100;
    let offset = 0;
    return points.map((p, i) => {
      const pct = (p.value / total) * 100;
      const dash = `${pct} ${circumference - pct}`;
      const seg: DonutSegment = {
        label: p.label,
        value: p.value,
        key: p.key,
        pct,
        color: CHART_COLORS[i % CHART_COLORS.length],
        dash,
        offset: -offset,
      };
      offset += pct;
      return seg;
    });
  }
  private buildLine(points: ChartPoint[]): {
    polyline: string;
    area: string;
    dots: LinePoint[];
    min: number;
    max: number;
  } {
    if (!points.length) {
      return { polyline: '', area: '', dots: [], min: 0, max: 0 };
    }
    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    // Échelle min–max : rend la variation visible même quand les valeurs
    // sont grandes et proches (sinon la courbe paraît plate)
    const range = max - min;
    const padX = 4;
    const padY = 10;
    const w = 100 - padX * 2;
    const h = 100 - padY * 2;
    const step = points.length > 1 ? w / (points.length - 1) : 0;
    const dots: LinePoint[] = points.map((p, i) => {
      const x = padX + i * step;
      const ratio = range > 0 ? (p.value - min) / range : 0.5;
      const y = padY + h - ratio * h;
      return { label: p.label, value: p.value, key: p.key, x, y };
    });
    const polyline = dots.map((d) => `${d.x},${d.y}`).join(' ');
    const baseline = 100 - padY;
    const area = `${polyline} ${dots[dots.length - 1].x},${baseline} ${dots[0].x},${baseline}`;
    return { polyline, area, dots, min, max };
  }
}
