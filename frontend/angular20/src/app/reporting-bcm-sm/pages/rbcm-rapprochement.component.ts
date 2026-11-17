import { JsonPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  OnInit,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';
import { DetailDrawerComponent } from '../../contrats-echeances/shared/detail-drawer.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { RbcmBarsComponent } from '../rbcm-charts';
import { RbcmCampaignPickerComponent } from '../rbcm-campaign-picker.component';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmPagerComponent } from '../rbcm-pager.component';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import {
  RBCM_API,
  RbcmChartSlice,
  RbcmReconcile,
  RbcmReconcileIssue,
  RbcmReconcileIssueList,
} from '../rbcm.models';

/** Contrôles internes BAL DET (ex-rapprochement DET/COND, T3.4-A2). */
@Component({
  selector: 'bea-rbcm-rapprochement',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    MatIconModule,
    JsonPipe,
    DetailDrawerComponent,
    RbcmStylesComponent,
    RbcmCampaignPickerComponent,
    RbcmBarsComponent,
    RbcmPagerComponent,
  ],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>Contrôles BAL DET</h1>
          <p class="bea-rbcm-sub">
            Cohérence interne de la balance détaillée (source unique). Aucune correction automatique des lignes.
          </p>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !ctx.selectedId()" (click)="run()">
            <mat-icon>fact_check</mat-icon> Lancer
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy() || !ctx.selectedId()" (click)="exportCsv()">
            <mat-icon>download</mat-icon> Export CSV
          </button>
        </div>
      </header>
      <bea-rbcm-campaign-picker />

      @if (!ctx.selectedId()) {
        <section class="bea-mg__panel">
          <div class="bea-rbcm-empty"><mat-icon>info</mat-icon><p>Sélectionnez une SM.</p></div>
        </section>
      } @else if (loadingSummary()) {
        <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
      } @else if (data(); as r) {
        @if (!r.ready) {
          <section class="bea-mg__panel">
            <div class="bea-rbcm-empty">
              <mat-icon>pending</mat-icon>
              <div>
                <strong>Contrôles non disponibles</strong>
                <p>Importez et confirmez la BAL DET, puis lancez les contrôles internes.</p>
              </div>
            </div>
          </section>
        } @else {
          <div class="bea-fx-kpis">
            <div class="bea-fx-kpi"><p>NCG</p><strong>{{ r.summary?.['ncg_count'] ?? r.summary?.['ncg_det'] }}</strong></div>
            <div class="bea-fx-kpi"><p>Lignes</p><strong>{{ r.summary?.['row_count'] ?? '—' }}</strong></div>
            <div class="bea-fx-kpi"><p>Σ classes 1–8</p><strong>{{ r.summary?.['classes_1_8_signed_det'] ?? '—' }}</strong></div>
            <div class="bea-fx-kpi" data-tone="warn"><p>Anomalies</p><strong>{{ issuesTotal() }}</strong></div>
          </div>
          @if (r.summary?.['historical_t1_note']; as note) {
            <p class="bea-rbcm-hint" style="margin-bottom:1rem">{{ note }}</p>
          }
          <div class="bea-rbcm-grid">
            <section class="bea-mg__panel bea-rbcm-span4">
              <div class="bea-mg__panel-top"><div><h2>Répartition</h2></div></div>
              <bea-rbcm-bars [parts]="anomalyBars()" vide="Aucune anomalie" />
            </section>
            <section class="bea-mg__panel bea-rbcm-span8">
              <div class="bea-mg__panel-top">
                <div>
                  <h2>Anomalies</h2>
                  <p class="bea-rbcm-sub">{{ issuesTotal() }} au total · pagination backend</p>
                </div>
              </div>

              <div class="bea-rbcm-filters">
                <label class="bea-mg__field bea-mg__field--grow">
                  <mat-icon>search</mat-icon>
                  <input type="search" placeholder="NCG, code, message…" [ngModel]="search" (ngModelChange)="onSearch($event)" />
                </label>
                <label class="bea-mg__field">
                  <mat-icon>priority_high</mat-icon>
                  <select [ngModel]="severity" (ngModelChange)="severity = $event; page.set(1); loadIssues()" aria-label="Gravité">
                    <option value="">Toutes gravités</option>
                    <option value="BLOCKING">Bloquant</option>
                    <option value="WARNING">Avertissement</option>
                    <option value="INFO">Info</option>
                  </select>
                </label>
                <label class="bea-mg__field">
                  <mat-icon>label</mat-icon>
                  <input placeholder="Type / code" [ngModel]="code" (ngModelChange)="onCode($event)" />
                </label>
                <label class="bea-mg__field">
                  <mat-icon>flag</mat-icon>
                  <select [ngModel]="resolvedFilter" (ngModelChange)="resolvedFilter = $event; page.set(1); loadIssues()" aria-label="Statut">
                    <option value="">Tous statuts</option>
                    <option value="false">Ouvertes</option>
                    <option value="true">Résolues</option>
                  </select>
                </label>
                <label class="bea-mg__field">
                  <mat-icon>sort</mat-icon>
                  <select [ngModel]="sort" (ngModelChange)="sort = $event; loadIssues()" aria-label="Tri">
                    <option value="severity">Gravité</option>
                    <option value="code">Code</option>
                    <option value="ncg">NCG</option>
                    <option value="created_at">Date</option>
                  </select>
                </label>
                <label class="bea-mg__field">
                  <mat-icon>view_list</mat-icon>
                  <select [ngModel]="pageSize" (ngModelChange)="pageSize = +$event; page.set(1); loadIssues()">
                    <option [ngValue]="10">10 / page</option>
                    <option [ngValue]="25">25 / page</option>
                    <option [ngValue]="50">50 / page</option>
                    <option [ngValue]="100">100 / page</option>
                  </select>
                </label>
              </div>

              @if (loadingIssues()) {
                <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement des anomalies…</p></div>
              } @else {
                <div class="bea-mg__table-wrap">
                  <table class="bea-mg__table">
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Réf. NCG</th>
                        <th>Gravité</th>
                        <th>Statut</th>
                        <th>Message</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      @for (i of issues(); track i.id) {
                        <tr class="bea-rbcm-row" (click)="open(i)">
                          <td>{{ i.code }}</td>
                          <td>{{ i.ncg || '—' }}</td>
                          <td>
                            <span class="bea-ct-badge" [attr.data-tone]="sevTone(i.severity)">{{ i.severity }}</span>
                          </td>
                          <td>{{ i.resolved ? 'Résolue' : 'Ouverte' }}</td>
                          <td class="bea-rbcm-ellipsis" [title]="i.message">{{ i.message }}</td>
                          <td>
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="$event.stopPropagation(); open(i)">
                              Détail
                            </button>
                          </td>
                        </tr>
                      } @empty {
                        <tr><td colspan="6">Aucune anomalie pour ces filtres.</td></tr>
                      }
                    </tbody>
                  </table>
                </div>
                <bea-rbcm-pager
                  [page]="page()"
                  [pageSize]="pageSize"
                  [total]="issuesTotal()"
                  label="Pagination des anomalies"
                  noun="anomalies"
                  (go)="go($event)"
                />
              }
            </section>
          </div>
        }
      }

      @if (issue(); as iss) {
        <bea-detail-drawer [titre]="iss.code" kicker="Contrôle" [sousTitre]="iss.ncg || '—'" (fermer)="issue.set(null)">
          <dl class="bea-rbcm-dl">
            <div><dt>Description</dt><dd>{{ iss.message }}</dd></div>
            <div><dt>Gravité</dt><dd>{{ iss.severity }}</dd></div>
            <div><dt>Statut</dt><dd>{{ iss.resolved ? 'Résolue' : 'Ouverte' }}</dd></div>
            <div><dt>Référence</dt><dd>{{ iss.ncg || '—' }}</dd></div>
            <div><dt>Date</dt><dd>{{ iss.created_at }}</dd></div>
          </dl>
          <h3>Données / résultat</h3>
          <pre class="bea-rbcm-pre">{{ iss.details | json }}</pre>
          <p class="bea-rbcm-hint">Aucune action corrective automatique n’est proposée (lecture seule).</p>
        </bea-detail-drawer>
      }
    </div>
  `,
})
export class RbcmRapprochementComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly ctx = inject(RbcmContextService);

  readonly loadingSummary = signal(false);
  readonly loadingIssues = signal(false);
  readonly busy = signal(false);
  readonly data = signal<RbcmReconcile | null>(null);
  readonly issues = signal<RbcmReconcileIssue[]>([]);
  readonly issuesTotal = signal(0);
  readonly page = signal(1);
  readonly issue = signal<RbcmReconcileIssue | null>(null);

  search = '';
  code = '';
  severity = '';
  resolvedFilter = '';
  sort = 'severity';
  pageSize = 25;

  private readonly search$ = new Subject<string>();
  private readonly code$ = new Subject<string>();
  private readonly subs = [
    this.search$.pipe(debounceTime(300), distinctUntilChanged()).subscribe((q) => {
      this.search = q;
      this.page.set(1);
      this.loadIssues();
    }),
    this.code$.pipe(debounceTime(300), distinctUntilChanged()).subscribe((q) => {
      this.code = q;
      this.page.set(1);
      this.loadIssues();
    }),
  ];

  constructor() {
    effect(() => {
      if (this.ctx.selectedId()) {
        this.loadSummary();
      } else {
        this.data.set(null);
        this.issues.set([]);
        this.issuesTotal.set(0);
      }
    });
  }

  ngOnInit(): void {
    this.ctx.loadCampaigns();
  }

  ngOnDestroy(): void {
    for (const s of this.subs) s.unsubscribe();
  }

  onSearch(q: string): void {
    this.search$.next(q ?? '');
  }
  onCode(q: string): void {
    this.code$.next(q ?? '');
  }

  sevTone(sev: string): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (sev === 'BLOCKING') return 'danger';
    if (sev === 'WARNING') return 'warn';
    return 'info';
  }

  anomalyBars(): RbcmChartSlice[] {
    const by: Record<string, number> = {};
    for (const i of this.issues()) by[i.code] = (by[i.code] || 0) + 1;
    return Object.entries(by).map(([label, value]) => ({ label, value }));
  }

  loadSummary(): void {
    const id = this.ctx.selectedId();
    if (!id) return;
    this.loadingSummary.set(true);
    this.api.get<RbcmReconcile>(`${RBCM_API}/campaigns/${id}/reconcile`).subscribe({
      next: (r) => {
        this.data.set(r);
        this.loadingSummary.set(false);
        this.page.set(1);
        this.loadIssues();
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Contrôles indisponibles');
          this.loadingSummary.set(false);
        }),
    });
  }

  loadIssues(): void {
    const id = this.ctx.selectedId();
    if (!id || !this.data()?.ready) {
      this.issues.set([]);
      this.issuesTotal.set(0);
      return;
    }
    this.loadingIssues.set(true);
    const params: Record<string, string | number | boolean> = {
      page: this.page(),
      page_size: this.pageSize,
      sort: this.sort,
    };
    if (this.search) params['search'] = this.search;
    if (this.severity) params['severity'] = this.severity;
    if (this.code) params['code'] = this.code;
    if (this.resolvedFilter === 'true') params['resolved'] = true;
    if (this.resolvedFilter === 'false') params['resolved'] = false;
    this.api.get<RbcmReconcileIssueList>(`${RBCM_API}/campaigns/${id}/reconcile/issues`, params).subscribe({
      next: (r) => {
        this.issues.set(r.items);
        this.issuesTotal.set(r.total);
        this.loadingIssues.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Anomalies indisponibles');
          this.loadingIssues.set(false);
        }),
    });
  }

  go(p: number): void {
    this.page.set(p);
    this.loadIssues();
  }

  run(): void {
    const id = this.ctx.selectedId();
    if (!id) return;
    this.feedback
      .run(() => this.api.post<Record<string, unknown>>(`${RBCM_API}/campaigns/${id}/reconcile`, {}), {
        busy: this.busy,
        loading: 'Contrôles…',
        success: { title: 'Contrôles exécutés' },
        errorTitle: 'Contrôles impossibles',
      })
      .subscribe({ next: () => this.loadSummary() });
  }

  open(i: RbcmReconcileIssue): void {
    this.issue.set(i);
  }

  exportCsv(): void {
    const id = this.ctx.selectedId();
    if (!id) return;
    this.feedback
      .run(() => this.api.download(`${RBCM_API}/campaigns/${id}/reconcile/export`), {
        busy: this.busy,
        loading: 'Export…',
        success: { title: 'CSV prêt' },
        errorTitle: 'Export impossible',
      })
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `rbcm_controles_${id}.csv`;
          a.click();
          URL.revokeObjectURL(url);
        },
      });
  }
}
