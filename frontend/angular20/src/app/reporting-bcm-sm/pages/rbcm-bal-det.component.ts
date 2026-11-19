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
import { RouterLink } from '@angular/router';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { MontantPipe } from '../../shared/montant.pipe';
import { RbcmCampaignPickerComponent } from '../rbcm-campaign-picker.component';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmPagerComponent } from '../rbcm-pager.component';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import { RBCM_API, RbcmDetLineList } from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-bal-det',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    MatIconModule,
    RouterLink,
    MontantPipe,
    RbcmStylesComponent,
    RbcmCampaignPickerComponent,
    RbcmPagerComponent,
  ],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>BAL DET</h1>
          <p class="bea-rbcm-sub">Balance détaillée — pagination serveur. Lecture seule (source unique).</p>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/imports">
            <mat-icon>upload_file</mat-icon> Imports
          </a>
        </div>
      </header>
      <bea-rbcm-campaign-picker />
      @if (!ctx.selectedId()) {
        <section class="bea-mg__panel"><div class="bea-rbcm-empty"><mat-icon>info</mat-icon><p>Sélectionnez une SM.</p></div></section>
      } @else {
        <div class="bea-rbcm-filters">
          <label class="bea-mg__field bea-mg__field--grow">
            <mat-icon>search</mat-icon>
            <input
              type="search"
              placeholder="Compte, NCG, libellé…"
              [ngModel]="search"
              (ngModelChange)="onSearch($event)"
            />
          </label>
          <label class="bea-mg__field">
            <mat-icon>tag</mat-icon>
            <input placeholder="NCG" [ngModel]="ncg" (ngModelChange)="onNcg($event)" />
          </label>
          <label class="bea-mg__field">
            <mat-icon>payments</mat-icon>
            <input placeholder="Devise" [ngModel]="devise" (ngModelChange)="onDevise($event)" />
          </label>
          <label class="bea-mg__field">
            <mat-icon>view_list</mat-icon>
            <select [ngModel]="pageSize" (ngModelChange)="pageSize = +$event; load(1)" aria-label="Lignes par page">
              <option [ngValue]="10">10 / page</option>
              <option [ngValue]="25">25 / page</option>
              <option [ngValue]="50">50 / page</option>
              <option [ngValue]="100">100 / page</option>
            </select>
          </label>
        </div>
        @if (loading()) {
          <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
        } @else if (data(); as L) {
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th class="bea-rbcm-num">#</th><th class="bea-rbcm-col-ncg">NCG</th><th class="bea-rbcm-col-code">Compte</th><th class="bea-rbcm-col-libelle">Libellé</th><th>Devise</th><th class="bea-rbcm-col-montant bea-rbcm-num">Débit</th><th class="bea-rbcm-col-montant bea-rbcm-num">Crédit</th></tr></thead>
              <tbody>
                @for (r of L.items; track r.id) {
                  <tr>
                    <td class="bea-rbcm-num">{{ r.line_no }}</td>
                    <td class="bea-rbcm-mono bea-rbcm-col-ncg">{{ r.ncg }}</td>
                    <td class="bea-rbcm-col-code">{{ r.compte }}</td>
                    <td class="bea-rbcm-col-libelle"><span class="bea-rbcm-ellipsis" [title]="r.libelle || ''">{{ r.libelle || '—' }}</span></td>
                    <td>{{ r.devise }}</td>
                    <td class="bea-rbcm-num bea-rbcm-col-montant">{{ r.debit | montant }}</td>
                    <td class="bea-rbcm-num bea-rbcm-col-montant">{{ r.credit | montant }}</td>
                  </tr>
                } @empty {
                  <tr><td colspan="7">Aucune ligne (import DET validé requis).</td></tr>
                }
              </tbody>
            </table>
          </div>
          <bea-rbcm-pager
            [page]="L.page"
            [pageSize]="L.page_size"
            [total]="L.total"
            label="Pagination BAL DET"
            noun="lignes"
            (go)="load($event)"
          />
        }
      }
    </div>
  `,
})
export class RbcmBalDetComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly ctx = inject(RbcmContextService);

  readonly loading = signal(false);
  readonly data = signal<RbcmDetLineList | null>(null);
  search = '';
  ncg = '';
  devise = '';
  page = 1;
  pageSize = 50;

  private readonly search$ = new Subject<string>();
  private readonly ncg$ = new Subject<string>();
  private readonly devise$ = new Subject<string>();
  private readonly subs = [
    this.search$.pipe(debounceTime(300), distinctUntilChanged()).subscribe((q) => {
      this.search = q;
      this.load(1);
    }),
    this.ncg$.pipe(debounceTime(300), distinctUntilChanged()).subscribe((q) => {
      this.ncg = q;
      this.load(1);
    }),
    this.devise$.pipe(debounceTime(300), distinctUntilChanged()).subscribe((q) => {
      this.devise = q;
      this.load(1);
    }),
  ];

  constructor() {
    effect(() => {
      const id = this.ctx.selectedId();
      if (id) this.load(1);
      else this.data.set(null);
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
  onNcg(q: string): void {
    this.ncg$.next(q ?? '');
  }
  onDevise(q: string): void {
    this.devise$.next(q ?? '');
  }

  load(page: number): void {
    const id = this.ctx.selectedId();
    if (!id) return;
    this.page = page;
    this.loading.set(true);
    const params: Record<string, string | number> = { page, page_size: this.pageSize };
    if (this.search) params['search'] = this.search;
    if (this.ncg) params['ncg'] = this.ncg;
    if (this.devise) params['devise'] = this.devise;
    this.api.get<RbcmDetLineList>(`${RBCM_API}/campaigns/${id}/det-lines`, params).subscribe({
      next: (r) => {
        this.data.set(r);
        this.loading.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'BAL DET indisponible');
          this.loading.set(false);
        }),
    });
  }
}
