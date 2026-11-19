import { ChangeDetectionStrategy, Component, OnInit, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { MontantPipe } from '../../shared/montant.pipe';
import { RbcmCampaignPickerComponent } from '../rbcm-campaign-picker.component';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmPagerComponent } from '../rbcm-pager.component';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import { RBCM_API, RbcmCondLineList } from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-bal-cond',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, MontantPipe, RbcmStylesComponent, RbcmCampaignPickerComponent, RbcmPagerComponent],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>BAL COND (archives)</h1>
          <p class="bea-rbcm-sub">
            Lecture historique uniquement — BAL COND n’est plus importée (T3.4-A2). Source active : BAL DET.
          </p>
        </div>
      </header>
      <section class="bea-mg__panel">
        <p class="bea-rbcm-hint">
          Les imports COND existants sont conservés pour audit. Le workflow normal n’accepte plus ce type de fichier.
        </p>
      </section>
      <bea-rbcm-campaign-picker />
      @if (!ctx.selectedId()) {
        <section class="bea-mg__panel"><div class="bea-rbcm-empty"><mat-icon>info</mat-icon><p>Sélectionnez une SM.</p></div></section>
      } @else {
        <div class="bea-rbcm-filters">
          <label class="bea-mg__field bea-mg__field--grow">
            <mat-icon>search</mat-icon>
            <input type="search" placeholder="NCG ou libellé…" [(ngModel)]="search" (ngModelChange)="load(1)" />
          </label>
          <label class="bea-mg__field">
            <mat-icon>tag</mat-icon>
            <input placeholder="NCG exact" [(ngModel)]="ncg" (ngModelChange)="load(1)" />
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
              <thead><tr><th class="bea-rbcm-col-ncg">NCG</th><th class="bea-rbcm-col-libelle">Libellé</th><th class="bea-rbcm-col-montant bea-rbcm-num">Tot. débit</th><th class="bea-rbcm-col-montant bea-rbcm-num">Tot. crédit</th><th class="bea-rbcm-col-montant bea-rbcm-num">VAR</th></tr></thead>
              <tbody>
                @for (r of L.items; track r.id) {
                  <tr>
                    <td class="bea-rbcm-mono bea-rbcm-col-ncg">{{ r.ncg }}</td>
                    <td class="bea-rbcm-col-libelle"><span class="bea-rbcm-ellipsis" [title]="r.libelle || ''">{{ r.libelle || '—' }}</span></td>
                    <td class="bea-rbcm-num bea-rbcm-col-montant">{{ r.tot_debit | montant }}</td>
                    <td class="bea-rbcm-num bea-rbcm-col-montant">{{ r.tot_credit | montant }}</td>
                    <td class="bea-rbcm-num bea-rbcm-col-montant">{{ r.var | montant }}</td>
                  </tr>
                } @empty {
                  <tr><td colspan="5">Aucun solde COND (import COND validé requis).</td></tr>
                }
              </tbody>
            </table>
          </div>
          <bea-rbcm-pager
            [page]="L.page"
            [pageSize]="L.page_size"
            [total]="L.total"
            label="Pagination BAL COND"
            noun="NCG"
            (go)="load($event)"
          />
        }
      }
    </div>
  `,
})
export class RbcmBalCondComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly ctx = inject(RbcmContextService);

  readonly loading = signal(false);
  readonly data = signal<RbcmCondLineList | null>(null);
  search = '';
  ncg = '';
  page = 1;
  pageSize = 50;

  constructor() {
    effect(() => {
      if (this.ctx.selectedId()) this.load(1);
      else this.data.set(null);
    });
  }

  ngOnInit(): void {
    this.ctx.loadCampaigns();
  }

  load(page: number): void {
    const id = this.ctx.selectedId();
    if (!id) return;
    this.page = page;
    this.loading.set(true);
    const params: Record<string, string | number> = { page, page_size: this.pageSize };
    if (this.search) params['search'] = this.search;
    if (this.ncg) params['ncg'] = this.ncg;
    this.api.get<RbcmCondLineList>(`${RBCM_API}/campaigns/${id}/cond-lines`, params).subscribe({
      next: (r) => {
        this.data.set(r);
        this.loading.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'BAL COND indisponible');
          this.loading.set(false);
        }),
    });
  }
}
