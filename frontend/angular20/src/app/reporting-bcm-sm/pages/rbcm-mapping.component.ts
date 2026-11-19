import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';
import { DetailDrawerComponent } from '../../contrats-echeances/shared/detail-drawer.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { RbcmDonutComponent } from '../rbcm-charts';
import { RbcmPagerComponent } from '../rbcm-pager.component';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import { RBCM_API, RbcmChartSlice, RbcmMappingSummary } from '../rbcm.models';

interface MappingRule {
  id: string;
  cell_ref: string;
  pattern: string;
  match_type: string;
  amount_basis: string;
  signed_balance_mode: string;
  lifecycle_status: string;
  provenance: string;
  notes: string | null;
  priority: number;
}

@Component({
  selector: 'bea-rbcm-mapping',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, DetailDrawerComponent, RbcmStylesComponent, RbcmDonutComponent, RbcmPagerComponent],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>Correspondances comptables</h1>
          <p class="bea-rbcm-sub">Consultation seule — aucune activation automatique (D01).</p>
        </div>
      </header>

      @if (summary(); as s) {
        <div class="bea-fx-kpis">
          <div class="bea-fx-kpi"><mat-icon>account_tree</mat-icon><p>Total règles</p><strong>{{ s.total }}</strong></div>
          <div class="bea-fx-kpi" data-tone="warn"><mat-icon>pending</mat-icon><p>À valider</p><strong>{{ s.a_valider }}</strong></div>
          <div class="bea-fx-kpi" data-tone="ok"><mat-icon>check_circle</mat-icon><p>Actives</p><strong>{{ s.active }}</strong></div>
          <div class="bea-fx-kpi"><mat-icon>block</mat-icon><p>Rejetées</p><strong>{{ s.rejected }}</strong></div>
        </div>
        <p class="bea-rbcm-hint">{{ s.activation_policy }}</p>
        <div class="bea-rbcm-grid">
          <section class="bea-mg__panel bea-rbcm-span4">
            <div class="bea-mg__panel-top"><div><h2>Répartition</h2></div></div>
            <bea-rbcm-donut [parts]="lifeParts()" [centre]="s.total" unite="règles" />
          </section>
          <section class="bea-mg__panel bea-rbcm-span8">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Règles</h2>
                <p class="bea-rbcm-sub">Lecture seule. Les filtres restent en place quand vous changez de page.</p>
              </div>
            </div>
            <div class="bea-rbcm-filters">
              <label class="bea-mg__field bea-mg__field--grow">
                <mat-icon>search</mat-icon>
                <input type="search" placeholder="Cellule, pattern, source…" [ngModel]="search()" (ngModelChange)="onSearch($event)" />
              </label>
              <label class="bea-mg__field">
                <mat-icon>flag</mat-icon>
                <select [ngModel]="life()" (ngModelChange)="life.set($event); page.set(1); loadRules()" aria-label="Cycle de vie">
                  <option value="">Tous les statuts</option>
                  <option value="A_VALIDER">À valider</option>
                  <option value="ACTIVE">Actives</option>
                  <option value="REJECTED">Rejetées</option>
                  <option value="SUPERSEDED">Remplacées</option>
                </select>
              </label>
              <label class="bea-mg__field">
                <mat-icon>rule</mat-icon>
                <select [ngModel]="matchType()" (ngModelChange)="matchType.set($event); page.set(1); loadRules()" aria-label="Type de correspondance">
                  <option value="">Tous les types</option>
                  <option value="EXACT">Exact</option>
                  <option value="PREFIX">Préfixe</option>
                </select>
              </label>
              <label class="bea-mg__field">
                <mat-icon>view_list</mat-icon>
                <select [ngModel]="pageSize()" (ngModelChange)="setPageSize(+$event)" aria-label="Lignes par page">
                  <option [ngValue]="10">10 / page</option>
                  <option [ngValue]="25">25 / page</option>
                  <option [ngValue]="50">50 / page</option>
                  <option [ngValue]="100">100 / page</option>
                </select>
              </label>
            </div>
            @if (loading()) {
              <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement des correspondances…</p></div>
            } @else {
              <div class="bea-mg__table-wrap bea-rbcm-table-scroll">
                <table class="bea-mg__table">
                  <thead>
                    <tr>
                      <th [attr.aria-sort]="ariaSort('cell_ref')">
                        <button type="button" class="bea-fx-sort" (click)="toggleSort('cell_ref')">Cellule <mat-icon>{{ sortIcon('cell_ref') }}</mat-icon></button>
                      </th>
                      <th [attr.aria-sort]="ariaSort('pattern')">
                        <button type="button" class="bea-fx-sort" (click)="toggleSort('pattern')">Pattern <mat-icon>{{ sortIcon('pattern') }}</mat-icon></button>
                      </th>
                      <th [attr.aria-sort]="ariaSort('amount_basis')">
                        <button type="button" class="bea-fx-sort" (click)="toggleSort('amount_basis')">Base <mat-icon>{{ sortIcon('amount_basis') }}</mat-icon></button>
                      </th>
                      <th [attr.aria-sort]="ariaSort('lifecycle_status')">
                        <button type="button" class="bea-fx-sort" (click)="toggleSort('lifecycle_status')">Statut <mat-icon>{{ sortIcon('lifecycle_status') }}</mat-icon></button>
                      </th>
                      <th [attr.aria-sort]="ariaSort('provenance')">
                        <button type="button" class="bea-fx-sort" (click)="toggleSort('provenance')">Source <mat-icon>{{ sortIcon('provenance') }}</mat-icon></button>
                      </th>
                      <th class="bea-rbcm-col-actions"></th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (r of rules(); track r.id) {
                      <tr class="bea-rbcm-row" (click)="open(r)">
                        <td class="bea-rbcm-col-code"><span class="bea-rbcm-mono">{{ r.cell_ref }}</span></td>
                        <td class="bea-rbcm-col-libelle"><span class="bea-rbcm-ellipsis" [title]="r.match_type + ' ' + r.pattern">{{ r.match_type }} {{ r.pattern }}</span></td>
                        <td>{{ r.amount_basis }}</td>
                        <td class="bea-rbcm-col-statut"><span class="bea-ct-badge">{{ r.lifecycle_status }}</span></td>
                        <td>{{ r.provenance }}</td>
                        <td class="bea-rbcm-col-actions">
                          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="$event.stopPropagation(); open(r)">Détail</button>
                        </td>
                      </tr>
                    } @empty {
                      <tr><td colspan="6">Aucune correspondance pour ces filtres.</td></tr>
                    }
                  </tbody>
                </table>
              </div>
              <bea-rbcm-pager
                [page]="page()"
                [pageSize]="pageSize()"
                [total]="total()"
                label="Pagination des correspondances"
                noun="correspondances"
                (go)="go($event)"
              />
            }
          </section>
        </div>
      }

      @if (drawer(); as r) {
        <bea-detail-drawer [titre]="r.cell_ref" kicker="Règle" [sousTitre]="r.lifecycle_status" (fermer)="drawer.set(null)">
          <p><strong>Pattern :</strong> {{ r.match_type }} {{ r.pattern }}</p>
          <p><strong>Base :</strong> {{ r.amount_basis }} · mode {{ r.signed_balance_mode }}</p>
          <p><strong>Priorité :</strong> {{ r.priority }}</p>
          <p><strong>Provenance :</strong> {{ r.provenance }}</p>
          <p><strong>Notes :</strong> {{ r.notes || '—' }}</p>
          <p class="bea-rbcm-hint">Activation interdite en T3.4 — décision métier D01 requise.</p>
        </bea-detail-drawer>
      }
    </div>
  `,
})
export class RbcmMappingComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly search$ = new Subject<string>();

  readonly loading = signal(true);
  readonly summary = signal<RbcmMappingSummary | null>(null);
  readonly rules = signal<MappingRule[]>([]);
  readonly drawer = signal<MappingRule | null>(null);
  readonly search = signal('');
  readonly life = signal('A_VALIDER');
  readonly matchType = signal('');
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = signal(50);
  readonly sortBy = signal('cell_ref');
  readonly sortOrder = signal<'asc' | 'desc'>('asc');

  ngOnInit(): void {
    this.search$.pipe(debounceTime(300), distinctUntilChanged()).subscribe(() => {
      this.page.set(1);
      this.loadRules();
    });
    this.api.get<RbcmMappingSummary>(`${RBCM_API}/mapping/summary`).subscribe({
      next: (s) => this.summary.set(s),
    });
    this.loadRules();
  }

  lifeParts(): RbcmChartSlice[] {
    const s = this.summary();
    if (!s) return [];
    return Object.entries(s.by_lifecycle).map(([label, value]) => ({ label, value }));
  }

  onSearch(v: string): void {
    this.search.set(v);
    this.search$.next(v);
  }

  setPageSize(size: number): void {
    this.pageSize.set(size);
    this.page.set(1);
    this.loadRules();
  }

  toggleSort(column: string): void {
    if (this.sortBy() === column) this.sortOrder.set(this.sortOrder() === 'asc' ? 'desc' : 'asc');
    else {
      this.sortBy.set(column);
      this.sortOrder.set('asc');
    }
    this.page.set(1);
    this.loadRules();
  }

  sortIcon(column: string): string {
    if (this.sortBy() !== column) return 'unfold_more';
    return this.sortOrder() === 'asc' ? 'arrow_upward' : 'arrow_downward';
  }

  ariaSort(column: string): 'ascending' | 'descending' | 'none' {
    if (this.sortBy() !== column) return 'none';
    return this.sortOrder() === 'asc' ? 'ascending' : 'descending';
  }

  go(p: number): void {
    const pages = Math.max(1, Math.ceil(this.total() / this.pageSize()));
    const next = Math.min(Math.max(1, p), pages);
    if (next === this.page()) return;
    this.page.set(next);
    this.loadRules();
  }

  loadRules(): void {
    this.loading.set(true);
    const params: Record<string, string | number> = {
      page: this.page(),
      page_size: this.pageSize(),
      sort_by: this.sortBy(),
      sort_order: this.sortOrder(),
    };
    if (this.life()) params['lifecycle_status'] = this.life();
    if (this.matchType()) params['match_type'] = this.matchType();
    if (this.search()) params['search'] = this.search();
    this.api
      .get<{ items: MappingRule[]; total: number; page: number; page_size: number }>(
        `${RBCM_API}/mapping/rules`,
        params,
      )
      .subscribe({
        next: (r) => {
          this.rules.set(r.items);
          this.total.set(r.total);
          this.loading.set(false);
        },
        error: (e) =>
          void describeApiErrorAsync(e).then((i) => {
            this.feedback.apiError(i, 'Correspondances indisponibles');
            this.loading.set(false);
          }),
      });
  }

  open(r: MappingRule): void {
    this.drawer.set(r);
  }
}
