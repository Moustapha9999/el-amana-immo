import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';

export interface CoreAdminKpis {
  utilisateurs: number;
  utilisateurs_actifs: number;
  departements: number;
  modules: number;
  modules_actifs: number;
  sessions_actives: number;
  alertes_securite: number;
  actions_aujourd_hui: number;
  notifications_non_lues?: number;
  documents_ged?: number;
}

export interface CoreAdminChartPoint {
  label: string;
  key: string;
  value: number;
}

export interface CoreAdminDashboardCharts {
  activite_7j: CoreAdminChartPoint[];
  sessions: CoreAdminChartPoint[];
  connexions: CoreAdminChartPoint[];
  modules: CoreAdminChartPoint[];
}

export interface CoreAdminActivity {
  id: string;
  who: string;
  email?: string | null;
  action: string;
  entity: string;
  entity_id?: string | null;
  module?: string | null;
  espace?: string | null;
  created_at?: string | null;
}

export interface CoreAdminHealth {
  ok: boolean;
  label: string;
}

export interface CoreAdminDashboard {
  kpis: CoreAdminKpis;
  charts?: CoreAdminDashboardCharts;
  activite: CoreAdminActivity[];
  etat: Record<string, CoreAdminHealth>;
  fuseau: string;
  app_name?: string;
}

interface BarRow extends CoreAdminChartPoint {
  pct: number;
}

interface DonutSegment extends CoreAdminChartPoint {
  pct: number;
  color: string;
  dash: string;
  offset: number;
}

const CHART_COLORS = ['#1a5278', '#2874a6', '#3498db', '#5dade2', '#0f766e', '#b45309'];

@Component({
  selector: 'bea-core-admin-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, DecimalPipe, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-dash__head--hero">
        <div>
          <p class="bea-admin-dash__eyebrow">{{ appName() }}</p>
          <h1>Dashboard</h1>
          <p>Vue d’ensemble — organisation, accès et supervision de la plateforme.</p>
        </div>
        <div class="bea-admin-dash__stamp">
          <span class="bea-admin-dash__stamp-label">Fuseau</span>
          <strong>{{ fuseau() }}</strong>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of kpiCards(k); track card.label; let i = $index) {
            @if (card.path) {
              <a
                class="bea-admin-kpi bea-admin-kpi--link"
                [attr.data-tone]="card.tone"
                [style.animation-delay]="i * 50 + 'ms'"
                [routerLink]="card.path"
              >
                <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="card.icon" /></span>
                <div class="bea-admin-kpi__copy">
                  <p class="bea-admin-kpi__label">{{ card.label }}</p>
                  <p class="bea-admin-kpi__value">{{ card.value }}</p>
                  @if (card.hint) {
                    <p class="bea-admin-kpi__hint">{{ card.hint }}</p>
                  }
                </div>
              </a>
            } @else {
              <article class="bea-admin-kpi" [attr.data-tone]="card.tone" [style.animation-delay]="i * 50 + 'ms'">
                <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="card.icon" /></span>
                <div class="bea-admin-kpi__copy">
                  <p class="bea-admin-kpi__label">{{ card.label }}</p>
                  <p class="bea-admin-kpi__value">{{ card.value }}</p>
                  @if (card.hint) {
                    <p class="bea-admin-kpi__hint">{{ card.hint }}</p>
                  }
                </div>
              </article>
            }
          }
        </div>
      } @else if (!erreur()) {
        <p class="bea-admin-dash__loading">Chargement des indicateurs…</p>
      }

      <div class="bea-admin-charts">
        <section class="bea-admin-panel bea-admin-chart">
          <div class="bea-admin-users__list-head">
            <h2>Activité — 7 derniers jours</h2>
            <a class="bea-admin-table__link" routerLink="/admin/activity">Détail</a>
          </div>
          @if (activiteBars().length === 0) {
            <p class="bea-admin-panel__empty">Pas encore d’historique sur la période.</p>
          } @else {
            <div class="bea-admin-bars" role="img" aria-label="Actions audit sur 7 jours">
              @for (bar of activiteBars(); track bar.key) {
                <div class="bea-admin-bars__col">
                  <span class="bea-admin-bars__value">{{ bar.value }}</span>
                  <div class="bea-admin-bars__track">
                    <div class="bea-admin-bars__fill" [style.height.%]="bar.pct"></div>
                  </div>
                  <span class="bea-admin-bars__label">{{ bar.label }}</span>
                </div>
              }
            </div>
            <p class="bea-admin-chart__foot">
              Total période · <strong>{{ fmt(activite7jTotal()) }}</strong> actions
            </p>
          }
        </section>

        <section class="bea-admin-panel bea-admin-chart">
          <div class="bea-admin-users__list-head">
            <h2>Sessions actives</h2>
            <a class="bea-admin-table__link" routerLink="/admin/sessions">Gérer</a>
          </div>
          @if (sessionsDonut().length === 0 || sessionsTotal() === 0) {
            <p class="bea-admin-panel__empty">Aucune session active.</p>
          } @else {
            <div class="bea-admin-donut">
              <svg viewBox="0 0 100 100" class="bea-admin-donut__svg" aria-hidden="true">
                @for (seg of sessionsDonut(); track seg.key) {
                  <circle
                    class="bea-admin-donut__ring"
                    cx="50"
                    cy="50"
                    r="36"
                    fill="none"
                    [attr.stroke]="seg.color"
                    stroke-width="12"
                    [attr.stroke-dasharray]="seg.dash"
                    [attr.stroke-dashoffset]="seg.offset"
                  />
                }
              </svg>
              <div class="bea-admin-donut__center">
                <strong>{{ fmt(sessionsTotal()) }}</strong>
                <span>actives</span>
              </div>
              <ul class="bea-admin-donut__legend">
                @for (seg of sessionsDonut(); track seg.key) {
                  <li>
                    <span class="bea-admin-donut__swatch" [style.background]="seg.color"></span>
                    <span>{{ seg.label }}</span>
                    <strong>{{ fmt(seg.value) }}</strong>
                  </li>
                }
              </ul>
            </div>
          }
        </section>

        <section class="bea-admin-panel bea-admin-chart">
          <div class="bea-admin-users__list-head">
            <h2>Connexions (fenêtre)</h2>
            <a class="bea-admin-table__link" routerLink="/admin/alerts">Alertes</a>
          </div>
          @if (connexionsDonut().length === 0 || connexionsTotal() === 0) {
            <p class="bea-admin-panel__empty">Aucune tentative récente.</p>
          } @else {
            <div class="bea-admin-donut">
              <svg viewBox="0 0 100 100" class="bea-admin-donut__svg" aria-hidden="true">
                @for (seg of connexionsDonut(); track seg.key) {
                  <circle
                    class="bea-admin-donut__ring"
                    cx="50"
                    cy="50"
                    r="36"
                    fill="none"
                    [attr.stroke]="seg.color"
                    stroke-width="12"
                    [attr.stroke-dasharray]="seg.dash"
                    [attr.stroke-dashoffset]="seg.offset"
                  />
                }
              </svg>
              <div class="bea-admin-donut__center">
                <strong>{{ fmt(connexionsTotal()) }}</strong>
                <span>tentatives</span>
              </div>
              <ul class="bea-admin-donut__legend">
                @for (seg of connexionsDonut(); track seg.key) {
                  <li>
                    <span class="bea-admin-donut__swatch" [style.background]="seg.color"></span>
                    <span>{{ seg.label }}</span>
                    <strong>{{ fmt(seg.value) }} · {{ seg.pct | number: '1.0-0' }}%</strong>
                  </li>
                }
              </ul>
            </div>
          }
        </section>

        <section class="bea-admin-panel bea-admin-chart">
          <div class="bea-admin-users__list-head">
            <h2>Modules catalogue</h2>
            <a class="bea-admin-table__link" routerLink="/admin/modules">Catalogue</a>
          </div>
          @if (moduleBars().length === 0) {
            <p class="bea-admin-panel__empty">Aucun module actif au catalogue.</p>
          } @else {
            <ul class="bea-admin-hbar">
              @for (row of moduleBars(); track row.key) {
                <li>
                  <div class="bea-admin-hbar__meta">
                    <span>{{ row.label }}</span>
                    <strong>{{ fmt(row.value) }}</strong>
                  </div>
                  <div class="bea-admin-hbar__track">
                    <div class="bea-admin-hbar__fill" [style.width.%]="row.pct" [attr.data-key]="row.key"></div>
                  </div>
                </li>
              }
            </ul>
          }
        </section>
      </div>

      <div class="bea-admin-shortcuts">
        <h2>Accès rapides</h2>
        <div class="bea-admin-shortcuts__grid">
          @for (item of raccourcis; track item.path) {
            <a class="bea-admin-shortcut" [routerLink]="item.path">
              <span class="bea-admin-shortcut__icon"><bea-admin-icon [name]="item.icon" /></span>
              <span class="bea-admin-shortcut__copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.hint }}</span>
              </span>
              <bea-admin-icon class="bea-admin-shortcut__chevron" name="chevron_right" />
            </a>
          }
        </div>
      </div>

      <div class="bea-admin-panels">
        <section class="bea-admin-panel bea-admin-panel--list">
          <div class="bea-admin-users__list-head">
            <h2>Activité récente</h2>
            <a class="bea-admin-table__link" routerLink="/admin/activity">Voir tout</a>
          </div>
          @if (activite().length === 0) {
            <p class="bea-admin-panel__empty">Aucune action journalisée pour le moment.</p>
          } @else {
            <div class="bea-admin-panel__scroll">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Qui</th>
                    <th>Action</th>
                    <th>Entité</th>
                    <th>Module</th>
                    <th>Quand</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of activite(); track row.id) {
                    <tr>
                      <td>{{ row.who }}</td>
                      <td>{{ row.action }}</td>
                      <td class="bea-admin-table__clip" [title]="entityLabel(row)">
                        {{ entityLabel(row) }}
                      </td>
                      <td>{{ row.module || '—' }}</td>
                      <td>
                        @if (row.created_at) {
                          {{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                        } @else {
                          —
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </section>

        <section class="bea-admin-panel bea-admin-panel--list">
          <h2>État de la plateforme</h2>
          <ul class="bea-admin-health bea-admin-panel__scroll">
            @for (item of etatList(); track item.key) {
              <li>
                <span
                  class="bea-admin-health__dot"
                  [class.bea-admin-health__dot--ok]="item.ok"
                  [class.bea-admin-health__dot--ko]="!item.ok"
                ></span>
                <span>{{ item.label }}</span>
                <strong>{{ item.ok ? 'OK' : 'KO' }}</strong>
              </li>
            }
          </ul>
          <p class="bea-admin-health__note">
            Contrôles locaux CORE · API · Auth · base · modules actifs.
          </p>
        </section>
      </div>
    </section>
  `,
})
export class CoreAdminDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly kpis = signal<CoreAdminKpis | null>(null);
  readonly charts = signal<CoreAdminDashboardCharts>({
    activite_7j: [],
    sessions: [],
    connexions: [],
    modules: [],
  });
  readonly activite = signal<CoreAdminActivity[]>([]);
  readonly etatList = signal<{ key: string; label: string; ok: boolean }[]>([]);
  readonly fuseau = signal('Africa/Nouakchott');
  readonly appName = signal('BEA DIGITAL');
  readonly erreur = signal<string | null>(null);

  readonly activiteBars = computed(() => this.buildBars(this.charts().activite_7j));
  readonly activite7jTotal = computed(() =>
    this.charts().activite_7j.reduce((sum, p) => sum + (p.value || 0), 0),
  );
  readonly sessionsDonut = computed(() =>
    this.buildDonut(this.charts().sessions, ['#1a5278', '#3498db']),
  );
  readonly sessionsTotal = computed(() =>
    this.charts().sessions.reduce((sum, p) => sum + (p.value || 0), 0),
  );
  readonly connexionsDonut = computed(() =>
    this.buildDonut(this.charts().connexions, ['#15803d', '#b45309']),
  );
  readonly connexionsTotal = computed(() =>
    this.charts().connexions.reduce((sum, p) => sum + (p.value || 0), 0),
  );
  readonly moduleBars = computed(() => this.buildBars(this.charts().modules));

  readonly raccourcis = [
    { label: 'Utilisateurs', hint: 'CRUD · mots de passe', path: '/admin/users', icon: 'group' },
    { label: 'Rôles & matrice', hint: 'Permissions effectives', path: '/admin/matrix', icon: 'grid_view' },
    { label: 'Sessions', hint: 'Révoquer un accès', path: '/admin/sessions', icon: 'devices' },
    { label: 'Audit', hint: 'Journal plateforme', path: '/admin/audit', icon: 'history' },
    { label: 'Alertes', hint: 'Échecs de connexion', path: '/admin/alerts', icon: 'warning' },
    { label: 'Notifications', hint: 'File transversale', path: '/admin/notifications', icon: 'notifications' },
    { label: 'GED', hint: 'Documents CORE', path: '/admin/ged', icon: 'folder' },
    { label: 'Sécurité', hint: 'Politique auth', path: '/admin/security', icon: 'security' },
  ];

  ngOnInit(): void {
    this.api.get<CoreAdminDashboard>('/plateforme/admin/dashboard').subscribe({
      next: (data) => {
        this.kpis.set(data.kpis);
        this.charts.set({
          activite_7j: data.charts?.activite_7j ?? [],
          sessions: data.charts?.sessions ?? [],
          connexions: data.charts?.connexions ?? [],
          modules: data.charts?.modules ?? [],
        });
        this.activite.set(data.activite ?? []);
        this.fuseau.set(data.fuseau || 'Africa/Nouakchott');
        this.appName.set(data.app_name || 'BEA DIGITAL');
        const order = ['core', 'api', 'auth', 'db', 'modules'];
        const entries = Object.entries(data.etat ?? {});
        entries.sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
        this.etatList.set(
          entries.map(([key, value]) => ({
            key,
            label: value.label,
            ok: value.ok,
          })),
        );
        this.erreur.set(null);
      },
      error: () => this.erreur.set('Impossible de charger le dashboard CORE ADMIN.'),
    });
  }

  kpiCards(
    k: CoreAdminKpis,
  ): { label: string; value: string; hint?: string; path?: string; icon: string; tone: string }[] {
    return [
      {
        label: 'Utilisateurs',
        value: this.fmt(k.utilisateurs),
        hint: `${this.fmt(k.utilisateurs_actifs)} actifs`,
        path: '/admin/users',
        icon: 'group',
        tone: 'users',
      },
      {
        label: 'Départements',
        value: this.fmt(k.departements),
        path: '/admin/departments',
        icon: 'domain',
        tone: 'org',
      },
      {
        label: 'Modules',
        value: this.fmt(k.modules),
        hint: `${this.fmt(k.modules_actifs)} actifs`,
        path: '/admin/modules',
        icon: 'apps',
        tone: 'modules',
      },
      {
        label: 'Sessions actives',
        value: this.fmt(k.sessions_actives),
        path: '/admin/sessions',
        icon: 'devices',
        tone: 'sessions',
      },
      {
        label: 'Alertes sécurité',
        value: this.fmt(k.alertes_securite),
        path: '/admin/alerts',
        icon: 'warning',
        tone: 'alert',
      },
      {
        label: "Actions aujourd'hui",
        value: this.fmt(k.actions_aujourd_hui),
        path: '/admin/activity',
        icon: 'bolt',
        tone: 'actions',
      },
      {
        label: 'Notifications',
        value: this.fmt(k.notifications_non_lues ?? 0),
        hint: 'non lues',
        path: '/admin/notifications',
        icon: 'notifications',
        tone: 'sessions',
      },
      {
        label: 'Documents GED',
        value: this.fmt(k.documents_ged ?? 0),
        path: '/admin/ged',
        icon: 'folder',
        tone: 'org',
      },
    ];
  }

  entityLabel(row: CoreAdminActivity): string {
    if (!row.entity_id) {
      return row.entity;
    }
    const id = row.entity_id.length > 10 ? `${row.entity_id.slice(0, 8)}…` : row.entity_id;
    return `${row.entity} · ${id}`;
  }

  fmt(n: number): string {
    return new Intl.NumberFormat('fr-FR').format(n);
  }

  private buildBars(points: CoreAdminChartPoint[]): BarRow[] {
    const max = Math.max(...points.map((p) => p.value), 1);
    return points.map((p) => ({
      ...p,
      pct: Math.max(4, (p.value / max) * 100),
    }));
  }

  private buildDonut(points: CoreAdminChartPoint[], colors = CHART_COLORS): DonutSegment[] {
    const usable = points.filter((p) => p.value > 0);
    const total = usable.reduce((sum, p) => sum + p.value, 0);
    if (total <= 0) {
      return [];
    }
    const circumference = 2 * Math.PI * 36;
    let offset = 0;
    return usable.map((p, i) => {
      const fraction = p.value / total;
      const len = fraction * circumference;
      const seg: DonutSegment = {
        ...p,
        pct: fraction * 100,
        color: colors[i % colors.length],
        dash: `${len} ${circumference - len}`,
        offset: circumference / 4 - offset,
      };
      offset += len;
      return seg;
    });
  }
}
