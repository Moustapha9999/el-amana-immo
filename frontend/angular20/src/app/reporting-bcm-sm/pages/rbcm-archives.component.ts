import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { RbcmPagerComponent } from '../rbcm-pager.component';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import {
  IMPORT_STATUS_LABELS,
  RBCM_API,
  RbcmCampaign,
  RbcmCampaignList,
  RbcmImport,
  RbcmImportList,
  STATUS_LABELS,
  periodLabel,
  statusTone,
} from '../rbcm.models';
import { RbcmContextService } from '../rbcm-context.service';

type ArchiveTab = 'det' | 'sm';

@Component({
  selector: 'bea-rbcm-archives',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, RouterLink, RbcmPagerComponent, RbcmStylesComponent],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>Archives</h1>
          <p class="bea-rbcm-sub">
            BAL DET importées et Situations Mensuelles réglementairement validées — classées par mois et année.
          </p>
        </div>
      </header>

      <div class="bea-rbcm-quick" style="margin-bottom:1rem">
        <button
          type="button"
          class="bea-mg__btn"
          [class.bea-mg__btn--primary]="tab() === 'det'"
          [class.bea-mg__btn--ghost]="tab() !== 'det'"
          (click)="tab.set('det')"
        >
          <mat-icon>table_rows</mat-icon> Archives BAL DET
        </button>
        <button
          type="button"
          class="bea-mg__btn"
          [class.bea-mg__btn--primary]="tab() === 'sm'"
          [class.bea-mg__btn--ghost]="tab() !== 'sm'"
          (click)="tab.set('sm')"
        >
          <mat-icon>verified</mat-icon> Archives Situations Mensuelles
        </button>
      </div>

      @if (tab() === 'det') {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <div>
              <h2>BAL DET importées</h2>
              <p class="bea-rbcm-sub">Fichiers source par SM — le canevas de travail n’apparaît pas ici.</p>
            </div>
          </div>
          <div class="bea-rbcm-filters">
            <label class="bea-mg__field bea-mg__field--grow">
              <mat-icon>search</mat-icon>
              <input
                type="search"
                placeholder="Nom de fichier, NCG…"
                [ngModel]="detSearch"
                (ngModelChange)="detSearch = $event; loadDet(1)"
              />
            </label>
          </div>
          @if (detLoading()) {
            <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
          } @else {
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th class="bea-rbcm-col-period">Période</th>
                    <th class="bea-rbcm-col-libelle">Fichier</th>
                    <th class="bea-rbcm-col-statut">Statut</th>
                    <th class="bea-rbcm-col-date">Importé le</th>
                    <th class="bea-rbcm-col-montant bea-rbcm-num">Lignes</th>
                    <th class="bea-rbcm-col-actions"></th>
                  </tr>
                </thead>
                <tbody>
                  @for (imp of detItems(); track imp.id) {
                    <tr>
                      <td class="bea-rbcm-col-period">
                        <a [routerLink]="['/reporting-bcm-sm/campagnes', imp.campaign_id]">
                          {{ campaignLabel(imp.campaign_id) }}
                        </a>
                      </td>
                      <td class="bea-rbcm-col-libelle"><span class="bea-rbcm-ellipsis" [title]="imp.filename">{{ imp.filename }}</span></td>
                      <td class="bea-rbcm-col-statut">
                        <span class="bea-ct-badge" [attr.data-tone]="importTone(imp.status)">
                          {{ IMPORT_STATUS_LABELS[imp.status] || imp.status }}
                        </span>
                      </td>
                      <td class="bea-rbcm-col-date">{{ imp.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td class="bea-rbcm-num bea-rbcm-col-montant">{{ imp.row_count ?? '—' }}</td>
                      <td class="bea-rbcm-col-actions">
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="downloadDet(imp)">
                          <mat-icon>download</mat-icon> Télécharger
                        </button>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="6">Aucune BAL DET archivée.</td></tr>
                  }
                </tbody>
              </table>
            </div>
            <bea-rbcm-pager
              [page]="detPage()"
              [pageSize]="25"
              [total]="detTotal()"
              label="Pagination des BAL DET"
              noun="imports"
              (go)="loadDet($event)"
            />
          }
        </section>
      } @else {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <div>
              <h2>Situations Mensuelles validées</h2>
              <p class="bea-rbcm-sub">
                Uniquement les SM approuvées ou clôturées. Un canevas de travail n’est jamais un document réglementaire.
              </p>
            </div>
          </div>
          @if (smLoading()) {
            <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
          } @else {
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th class="bea-rbcm-col-period">Période</th>
                    <th class="bea-rbcm-col-statut">Statut réglementaire</th>
                    <th class="bea-rbcm-col-date">Validée le</th>
                    <th class="bea-rbcm-col-libelle">Responsable</th>
                    <th class="bea-rbcm-col-actions"></th>
                  </tr>
                </thead>
                <tbody>
                  @for (c of smItems(); track c.id) {
                    <tr>
                      <td class="bea-rbcm-col-period"><strong>{{ periodLabel(c) }}</strong></td>
                      <td class="bea-rbcm-col-statut">
                        <span class="bea-ct-badge" [attr.data-tone]="statusTone(c.status)">
                          {{ STATUS_LABELS[c.status] || c.status }}
                        </span>
                      </td>
                      <td class="bea-rbcm-col-date">{{ c.approved_at ? (c.approved_at | date: 'dd/MM/yyyy HH:mm') : (c.locked_at | date: 'dd/MM/yyyy HH:mm') }}</td>
                      <td class="bea-rbcm-col-libelle">{{ c.reporting_owner_name || c.preparer_name || '—' }}</td>
                      <td class="bea-rbcm-col-actions">
                        <div class="bea-rbcm-quick">
                          <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/reporting-bcm-sm/campagnes', c.id]">Fiche</a>
                          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="downloadFinal(c)">
                            <mat-icon>download</mat-icon> Document final
                          </button>
                        </div>
                      </td>
                    </tr>
                  } @empty {
                    <tr>
                      <td colspan="5">Aucune Situation Mensuelle réglementairement validée pour le moment.</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </section>
      }

      <p class="bea-rbcm-hint" style="margin-top:1rem">
        Les anciennes BAL COND restent consultables en lecture seule —
        <a routerLink="/reporting-bcm-sm/bal-cond">historique COND</a>.
      </p>
    </div>
  `,
})
export class RbcmArchivesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly ctx = inject(RbcmContextService);

  readonly IMPORT_STATUS_LABELS = IMPORT_STATUS_LABELS;
  readonly STATUS_LABELS = STATUS_LABELS;
  readonly periodLabel = periodLabel;
  readonly statusTone = statusTone;

  readonly tab = signal<ArchiveTab>('det');
  readonly detLoading = signal(true);
  readonly smLoading = signal(true);
  readonly busy = signal(false);
  readonly detItems = signal<RbcmImport[]>([]);
  readonly detTotal = signal(0);
  readonly detPage = signal(1);
  readonly smItems = signal<RbcmCampaign[]>([]);
  detSearch = '';

  ngOnInit(): void {
    this.ctx.loadCampaigns();
    this.loadDet(1);
    this.loadSm();
  }

  campaignLabel(id: string): string {
    const c = this.ctx.campaigns().find((x) => x.id === id);
    return c ? periodLabel(c) : id.slice(0, 8);
  }

  importTone(status: string): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (status === 'VALIDATED') return 'ok';
    if (status === 'ANALYZED') return 'warn';
    if (status === 'REJECTED') return 'danger';
    return 'info';
  }

  loadDet(page: number): void {
    this.detPage.set(page);
    this.detLoading.set(true);
    const params: Record<string, string | number> = {
      page,
      page_size: 25,
      file_type: 'BAL_DET',
    };
    if (this.detSearch) params['search'] = this.detSearch;
    this.api.get<RbcmImportList>(`${RBCM_API}/imports`, params).subscribe({
      next: (r) => {
        this.detItems.set(r.items);
        this.detTotal.set(r.total);
        this.detLoading.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Archives BAL DET indisponibles');
          this.detLoading.set(false);
        }),
    });
  }

  loadSm(): void {
    this.smLoading.set(true);
    this.api
      .get<RbcmCampaignList>(`${RBCM_API}/campaigns`, { page: 1, page_size: 100, sort_by: 'period', sort_order: 'desc' })
      .subscribe({
        next: (r) => {
          this.smItems.set(r.items.filter((c) => c.status === 'APPROUVEE' || c.status === 'CLOTUREE'));
          this.smLoading.set(false);
        },
        error: (e) =>
          void describeApiErrorAsync(e).then((i) => {
            this.feedback.apiError(i, 'Archives SM indisponibles');
            this.smLoading.set(false);
          }),
      });
  }

  downloadDet(imp: RbcmImport): void {
    this.feedback
      .run(() => this.api.download(`${RBCM_API}/campaigns/${imp.campaign_id}/imports/${imp.id}/download`), {
        busy: this.busy,
        loading: 'Téléchargement…',
        success: { title: 'Fichier BAL DET téléchargé' },
        errorTitle: 'Téléchargement impossible',
      })
      .subscribe();
  }

  downloadFinal(c: RbcmCampaign): void {
    this.feedback
      .run(() => this.api.download(`${RBCM_API}/campaigns/${c.id}/documents/final/download`), {
        busy: this.busy,
        loading: 'Téléchargement…',
        success: { title: 'Document final téléchargé' },
        errorTitle: 'Document final indisponible',
      })
      .subscribe();
  }
}
