import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';

type Periode = '24h' | '7j' | '30j';
type Categorie = 'serveur' | 'refus' | 'conflits' | 'validation';

interface ErrorEvent {
  id: string;
  created_at: string | null;
  request_id: string | null;
  method: string;
  route: string;
  status_code: number;
  code: string | null;
  message: string | null;
  exception_type: string | null;
  user_id: string | null;
  user_email: string | null;
  user_full_name: string | null;
  module_code: string | null;
  ip_address: string | null;
  duration_ms: number | null;
}

interface ErrorKpis {
  total: number;
  serveur: number;
  refus: number;
  conflits: number;
  validation: number;
}

interface ErrorPage {
  items: ErrorEvent[];
  total: number;
  page: number;
  size: number;
  periode: Periode;
  kpis: ErrorKpis;
  top_routes: { label: string; count: number }[];
  top_codes: { label: string; count: number }[];
}

const CODE_LABELS: Record<string, string> = {
  VALIDATION_ERROR: 'Champs invalides',
  FORBIDDEN: 'Accès refusé',
  MODULE_FORBIDDEN: 'Module non autorisé',
  CONFLICT: 'Conflit',
  DUPLICATE: 'Doublon',
  DUPLICATE_REQUEST: 'Double soumission',
  RATE_LIMITED: 'Trop de requêtes',
  DATABASE_ERROR: 'Base indisponible',
  INTERNAL_ERROR: 'Erreur interne',
  BUSINESS_RULE_ERROR: 'Règle métier',
};

@Component({
  selector: 'bea-core-admin-errors',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Erreurs API</h1>
          <p>
            Erreurs renvoyées aux utilisateurs (refus, conflits, validations, erreurs serveur), corrélées par
            <strong>référence support</strong> (<code>request_id</code>). Lecture seule.
          </p>
        </div>
        <div class="bea-admin-errors__periods" role="group" aria-label="Période">
          @for (p of periodes; track p.code) {
            <button
              type="button"
              class="bea-admin-btn bea-admin-btn--ghost"
              [class.bea-admin-btn--on]="periode() === p.code"
              [attr.aria-pressed]="periode() === p.code"
              (click)="setPeriode(p.code)"
            >
              {{ p.label }}
            </button>
          }
        </div>
      </header>

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of kpiCards(k); track card.key; let i = $index) {
            <button
              type="button"
              class="bea-admin-kpi bea-admin-kpi--link"
              [attr.data-tone]="card.tone"
              [class.bea-admin-kpi--on]="categorie() === card.key || (card.key === 'tous' && !categorie())"
              [style.animation-delay]="i * 60 + 'ms'"
              (click)="setCategorie(card.key)"
            >
              <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="card.icon" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">{{ card.label }}</p>
                <p class="bea-admin-kpi__value">{{ card.value }}</p>
              </div>
            </button>
          }
        </div>
      }

      @if (topRoutes().length || topCodes().length) {
        <div class="bea-admin-errors__tops">
          <div class="bea-admin-panel">
            <h2>Routes les plus touchées</h2>
            <ol class="bea-admin-errors__top">
              @for (t of topRoutes(); track t.label) {
                <li><code>{{ t.label }}</code><strong>{{ t.count }}</strong></li>
              }
            </ol>
          </div>
          <div class="bea-admin-panel">
            <h2>Codes les plus fréquents</h2>
            <ol class="bea-admin-errors__top">
              @for (t of topCodes(); track t.label) {
                <li><span>{{ codeLabel(t.label) }} <code>{{ t.label }}</code></span><strong>{{ t.count }}</strong></li>
              }
            </ol>
          </div>
        </div>
      }

      <form class="bea-admin-toolbar bea-admin-toolbar--users" [formGroup]="filters" (ngSubmit)="search()">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input type="search" formControlName="search" placeholder="Référence REQ-…, route, code, e-mail…" />
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="button" class="bea-admin-btn bea-admin-btn--refresh" (click)="reload()" [disabled]="loading()">
            <bea-admin-icon name="refresh" />
            Actualiser
          </button>
          <button type="submit" class="bea-admin-btn">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="resetFilters()">Réinitialiser</button>
        </div>
      </form>

      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement des erreurs…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-users__list">
          <div class="bea-admin-users__list-head">
            <h2>Journal des erreurs</h2>
            <p>{{ total() }} erreur(s).</p>
          </div>
          @if (rows().length === 0) {
            <p class="bea-admin-panel__empty">Aucune erreur enregistrée pour ces critères.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Quand</th>
                    <th>Statut</th>
                    <th>Erreur</th>
                    <th>Route</th>
                    <th>Utilisateur</th>
                    <th>Référence support</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        @if (row.created_at) {
                          {{ row.created_at | date: 'dd/MM/yyyy HH:mm:ss' : 'Africa/Nouakchott' }}
                        } @else {
                          —
                        }
                      </td>
                      <td>
                        <span class="bea-admin-errors__status" [attr.data-tone]="tone(row.status_code)">{{ row.status_code }}</span>
                      </td>
                      <td class="bea-admin-table__clip" [title]="row.message || ''">
                        <strong>{{ codeLabel(row.code) }}</strong>
                        @if (row.exception_type) { <code> · {{ row.exception_type }}</code> }
                        @if (row.message) { <div class="bea-admin-sessions__meta">{{ row.message }}</div> }
                      </td>
                      <td class="bea-admin-table__clip" [title]="row.method + ' ' + row.route">
                        <code>{{ row.method }} {{ row.route }}</code>
                        @if (row.module_code) { <div class="bea-admin-sessions__meta">Module {{ row.module_code }}</div> }
                      </td>
                      <td>
                        @if (row.user_id) {
                          <a class="bea-admin-table__link" [routerLink]="['/admin/users', row.user_id]">
                            {{ row.user_full_name || row.user_email || 'Utilisateur' }}
                          </a>
                        } @else {
                          Anonyme
                        }
                        @if (row.ip_address) { <div class="bea-admin-sessions__meta">{{ row.ip_address }}</div> }
                      </td>
                      <td>
                        @if (row.request_id) {
                          <code>{{ row.request_id }}</code>
                          <div class="bea-admin-errors__links">
                            <button type="button" class="bea-admin-table__link" (click)="copier(row.request_id)">Copier</button>
                            <a class="bea-admin-table__link" routerLink="/admin/audit" [queryParams]="{ search: row.request_id }">Audit</a>
                          </div>
                        } @else {
                          —
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="bea-admin-pager">
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} erreur(s)</span>
              <div>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="go(page() - 1)">
                  Précédent
                </button>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages()" (click)="go(page() + 1)">
                  Suivant
                </button>
              </div>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class CoreAdminErrorsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly feedback = inject(FeedbackService);

  readonly periodes: { code: Periode; label: string }[] = [
    { code: '24h', label: '24 h' },
    { code: '7j', label: '7 jours' },
    { code: '30j', label: '30 jours' },
  ];

  readonly loading = signal(true);
  readonly rows = signal<ErrorEvent[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = signal(25);
  readonly periode = signal<Periode>('24h');
  readonly categorie = signal<Categorie | null>(null);
  readonly kpis = signal<ErrorKpis | null>(null);
  readonly topRoutes = signal<{ label: string; count: number }[]>([]);
  readonly topCodes = signal<{ label: string; count: number }[]>([]);
  readonly filters = this.fb.nonNullable.group({ search: '' });
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size())));

  ngOnInit(): void {
    const search = this.route.snapshot.queryParamMap.get('search');
    if (search) this.filters.patchValue({ search });
    this.reload();
  }

  kpiCards(k: ErrorKpis) {
    return [
      { key: 'tous', label: 'Total', value: k.total, icon: 'report', tone: 'blue' },
      { key: 'serveur', label: 'Erreurs serveur', value: k.serveur, icon: 'error', tone: 'rose' },
      { key: 'refus', label: 'Accès refusés', value: k.refus, icon: 'block', tone: 'amber' },
      { key: 'conflits', label: 'Conflits / limites', value: k.conflits, icon: 'sync_problem', tone: 'teal' },
      { key: 'validation', label: 'Saisies invalides', value: k.validation, icon: 'rule', tone: 'green' },
    ] as const;
  }

  codeLabel(code: string | null): string {
    return code ? (CODE_LABELS[code] ?? code) : 'Erreur';
  }

  tone(status: number): string {
    if (status >= 500) return 'danger';
    if (status === 403) return 'warn';
    return 'info';
  }

  setPeriode(p: Periode): void {
    this.periode.set(p);
    this.page.set(1);
    this.reload();
  }

  setCategorie(key: string): void {
    this.categorie.set(key === 'tous' ? null : (key as Categorie));
    this.page.set(1);
    this.reload();
  }

  search(): void {
    this.page.set(1);
    this.reload();
  }

  resetFilters(): void {
    this.filters.reset({ search: '' });
    this.categorie.set(null);
    this.page.set(1);
    this.reload();
  }

  go(page: number): void {
    this.page.set(page);
    this.reload();
  }

  copier(ref: string): void {
    navigator.clipboard?.writeText(ref).then(
      () => this.feedback.success({ title: 'Référence copiée', message: ref, duration: 2500 }),
      () => this.feedback.warning({ title: 'Copie impossible', message: ref }),
    );
  }

  reload(): void {
    this.loading.set(true);
    const params: Record<string, string | number> = { page: this.page(), size: this.size(), periode: this.periode() };
    const cat = this.categorie();
    if (cat) params['categorie'] = cat;
    const term = this.filters.getRawValue().search.trim();
    if (term) params['search'] = term;
    this.api.get<ErrorPage>('/plateforme/admin/supervision/erreurs', params).subscribe({
      next: (data) => {
        this.rows.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.page.set(data.page ?? 1);
        this.kpis.set(data.kpis ?? null);
        this.topRoutes.set(data.top_routes ?? []);
        this.topCodes.set(data.top_codes ?? []);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, 'Chargement des erreurs impossible'));
      },
    });
  }
}
