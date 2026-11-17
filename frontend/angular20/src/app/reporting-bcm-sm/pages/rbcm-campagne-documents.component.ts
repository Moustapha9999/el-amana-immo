import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, effect, inject, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import {
  DOCUMENT_STATUS_LABELS,
  RBCM_API,
  RbcmDocument,
  RbcmDocumentDetail,
  RbcmDocumentList,
  documentWarningLines,
  formatDocumentKind,
  splitCampaignDocuments,
} from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-campagne-documents',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, DatePipe],
  template: `
    <section class="bea-mg__panel bea-rbcm-span12">
      <div class="bea-mg__panel-top">
        <div>
          <h2>Documents</h2>
          <p class="bea-rbcm-sub">Canevas officiel alimenté par la BAL DET — les totaux Excel sont conservés.</p>
        </div>
        <div class="bea-rbcm-quick">
          @if (canPrepare()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || loading()" (click)="generateWork()">
              <mat-icon>description</mat-icon> Générer le canevas
            </button>
          }
          <button type="button" class="bea-mg__icon-btn" aria-label="Actualiser" [disabled]="busy() || loading()" (click)="reload()">
            <mat-icon>refresh</mat-icon>
          </button>
        </div>
      </div>

      @if (loading()) {
        <div class="bea-rbcm-empty bea-rbcm-empty--compact">
          <mat-icon>hourglass_top</mat-icon>
          <p>Chargement des documents…</p>
        </div>
      } @else if (loadError()) {
        <div class="bea-rbcm-empty">
          <mat-icon>error_outline</mat-icon>
          <p>{{ loadError() }}</p>
        </div>
      } @else {
        @if (currentWork(); as work) {
          <article class="bea-rbcm-doc-card">
            <p class="bea-rbcm-doc-banner" role="status">DOCUMENT DE TRAVAIL — NON VALIDÉ</p>
            <header class="bea-rbcm-doc-head">
              <div>
                <p class="bea-rbcm-source__name">{{ work.filename }}</p>
                <p class="bea-rbcm-hint">{{ work.work_disclaimer || 'Document de travail non validé — ne constitue pas une validation réglementaire.' }}</p>
              </div>
              <span class="bea-ct-badge" data-tone="warn">{{ DOCUMENT_STATUS_LABELS['WORK'] }}</span>
            </header>
            <dl class="bea-rbcm-dl">
              <div><dt>Séquence</dt><dd>{{ work.document_seq ?? '—' }}</dd></div>
              <div><dt>Format</dt><dd>{{ formatDocumentKind(work) }}</dd></div>
              <div><dt>Généré le</dt><dd>{{ work.created_at ? (work.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</dd></div>
              <div><dt>Auteur</dt><dd>{{ work.created_by_name || '—' }}</dd></div>
            </dl>
            @if (workWarnings().length) {
              <div>
                <p class="bea-rbcm-sub">Pourquoi ce document est provisoire</p>
                <ul class="bea-rbcm-warn-list">
                  @for (line of workWarnings(); track line) {
                    <li>{{ line }}</li>
                  }
                </ul>
              </div>
            }
            <div class="bea-rbcm-quick">
              @if (canExport()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="download(work)">
                  <mat-icon>download</mat-icon> Télécharger Excel
                </button>
              } @else {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" disabled title="Permission reporting-bcm-sm.export requise">
                  <mat-icon>lock</mat-icon> Télécharger Excel
                </button>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="toggleDetail(work)">
                {{ selectedId() === work.id ? 'Masquer le détail' : 'Consulter le détail' }}
              </button>
            </div>
            @if (selectedId() === work.id && detail()?.id === work.id) {
              <details class="bea-rbcm-tech">
                <summary>Informations techniques</summary>
                <dl class="bea-rbcm-dl" style="margin-top:0.55rem">
                  <div><dt>Empreinte</dt><dd class="bea-rbcm-mono">{{ detail()?.sha256_available ? (detail()?.sha256 || '—') : 'Non disponible' }}</dd></div>
                  <div><dt>Nature</dt><dd>{{ detail()?.generation_kind === 'documentary' ? 'Documentaire (canevas)' : 'Export technique' }}</dd></div>
                </dl>
              </details>
            }
          </article>
        } @else {
          <div class="bea-rbcm-empty bea-rbcm-empty--compact">
            <mat-icon>description</mat-icon>
            <p>Aucun document de travail. Importez la BAL DET, lancez le calcul, puis générez le canevas.</p>
          </div>
        }

        <div class="bea-rbcm-doc-block">
          <h3>Historique</h3>
          @if (!superseded().length) {
            <p class="bea-rbcm-hint">Aucune ancienne version.</p>
          } @else {
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th>Séquence</th>
                    <th>Fichier</th>
                    <th>Format</th>
                    <th>Généré le</th>
                    <th>Auteur</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  @for (d of superseded(); track d.id) {
                    <tr>
                      <td>{{ d.document_seq ?? '—' }}</td>
                      <td>
                        <span class="bea-ct-badge" data-tone="info">{{ DOCUMENT_STATUS_LABELS['SUPERSEDED'] }}</span>
                        <span class="bea-rbcm-ellipsis" style="display:inline-block;margin-left:0.4rem;vertical-align:middle">{{ d.filename }}</span>
                      </td>
                      <td>{{ formatDocumentKind(d) }}</td>
                      <td>{{ d.created_at ? (d.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                      <td>{{ d.created_by_name || '—' }}</td>
                      <td>
                        <div class="bea-rbcm-quick">
                          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="toggleDetail(d)">Détail</button>
                          @if (canExport()) {
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="download(d)">
                              <mat-icon>download</mat-icon>
                            </button>
                          }
                        </div>
                      </td>
                    </tr>
                    @if (selectedId() === d.id && detail()?.id === d.id) {
                      <tr>
                        <td colspan="6">
                          <ul class="bea-rbcm-warn-list">
                            @for (line of selectedWarnings(); track line) {
                              <li>{{ line }}</li>
                            }
                          </ul>
                          @if (!selectedWarnings().length) {
                            <p class="bea-rbcm-hint">Ancienne version remplacée par le document de travail courant.</p>
                          }
                        </td>
                      </tr>
                    }
                  }
                </tbody>
              </table>
            </div>
          }
        </div>

        <div class="bea-rbcm-doc-block">
          <h3>Exports techniques</h3>
          <p class="bea-rbcm-hint">Fichiers GENERATED — distincts du canevas officiel, hors validation réglementaire.</p>
          @if (!generated().length) {
            <p class="bea-rbcm-hint">Aucun export technique.</p>
          } @else {
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th>Fichier</th>
                    <th>Format</th>
                    <th>Généré le</th>
                    <th>Auteur</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  @for (d of generated(); track d.id) {
                    <tr>
                      <td>
                        <span class="bea-ct-badge">{{ DOCUMENT_STATUS_LABELS['GENERATED'] }}</span>
                        <span class="bea-rbcm-ellipsis" style="display:inline-block;margin-left:0.4rem;vertical-align:middle">{{ d.filename }}</span>
                      </td>
                      <td>{{ formatDocumentKind(d) }}</td>
                      <td>{{ d.created_at ? (d.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                      <td>{{ d.created_by_name || '—' }}</td>
                      <td>
                        @if (canExport()) {
                          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="download(d)">
                            <mat-icon>download</mat-icon>
                          </button>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class RbcmCampagneDocumentsComponent implements OnInit {
  readonly campaignId = input.required<string>();
  readonly refreshNonce = input(0);

  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);

  readonly DOCUMENT_STATUS_LABELS = DOCUMENT_STATUS_LABELS;
  readonly formatDocumentKind = formatDocumentKind;

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly selectedId = signal<string | null>(null);
  readonly detail = signal<RbcmDocumentDetail | null>(null);
  readonly workWarnings = signal<string[]>([]);
  readonly selectedWarnings = signal<string[]>([]);

  readonly currentWork = signal<RbcmDocument | null>(null);
  readonly superseded = signal<RbcmDocument[]>([]);
  readonly generated = signal<RbcmDocument[]>([]);

  constructor() {
    effect(() => {
      const n = this.refreshNonce();
      if (n > 0) this.reload();
    });
  }

  ngOnInit(): void {
    this.reload();
  }

  canExport(): boolean {
    return this.hasPerm('reporting-bcm-sm.export', 'reporting-bcm-sm.admin');
  }

  canPrepare(): boolean {
    return this.hasPerm('reporting-bcm-sm.prepare', 'reporting-bcm-sm.admin');
  }

  generateWork(): void {
    const id = this.campaignId();
    if (!id || !this.canPrepare()) return;
    this.feedback
      .run(() => this.api.post(`${RBCM_API}/campaigns/${id}/documents/work`, {}), {
        busy: this.busy,
        loading: 'Génération du canevas…',
        success: { title: 'Canevas généré' },
        errorTitle: 'Génération impossible',
      })
      .subscribe({ next: () => this.reload() });
  }

  reload(): void {
    const id = this.campaignId();
    if (!id) return;
    this.loading.set(true);
    this.loadError.set(null);
    this.selectedId.set(null);
    this.detail.set(null);
    this.api.get<RbcmDocumentList>(`${RBCM_API}/campaigns/${id}/documents`).subscribe({
      next: (res) => {
        const rows = (res.items || []).filter((d) => d.status !== 'VALIDATED');
        const split = splitCampaignDocuments(rows);
        this.currentWork.set(split.work);
        this.superseded.set(split.superseded);
        this.generated.set(split.generated);
        this.loading.set(false);
        if (split.work) this.loadWorkWarnings(split.work);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((info) => {
          this.loadError.set(info.message);
          this.feedback.apiError(info, 'Documents indisponibles');
          this.loading.set(false);
        }),
    });
  }

  toggleDetail(d: RbcmDocument): void {
    if (this.selectedId() === d.id) {
      this.selectedId.set(null);
      return;
    }
    this.selectedId.set(d.id);
    this.api.get<RbcmDocumentDetail>(`${RBCM_API}/campaigns/${this.campaignId()}/documents/${d.id}`).subscribe({
      next: (det) => {
        this.detail.set(det);
        const lines = documentWarningLines(det.warnings);
        if (d.status === 'WORK') this.workWarnings.set(lines);
        else this.selectedWarnings.set(lines);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((info) => this.feedback.apiError(info, 'Détail indisponible')),
    });
  }

  download(d: RbcmDocument): void {
    if (!this.canExport()) return;
    this.feedback
      .run(
        () => this.api.download(`${RBCM_API}/campaigns/${this.campaignId()}/documents/${d.id}/download`),
        {
          busy: this.busy,
          loading: 'Téléchargement…',
          success: { title: 'Fichier prêt' },
          errorTitle: 'Téléchargement impossible',
        },
      )
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = d.filename || 'document-sm.xlsx';
          a.click();
          URL.revokeObjectURL(url);
        },
      });
  }

  private loadWorkWarnings(work: RbcmDocument): void {
    this.api.get<RbcmDocumentDetail>(`${RBCM_API}/campaigns/${this.campaignId()}/documents/${work.id}`).subscribe({
      next: (det) => this.workWarnings.set(documentWarningLines(det.warnings)),
      error: () => this.workWarnings.set(work.work_disclaimer ? [work.work_disclaimer] : []),
    });
  }

  private hasPerm(...codes: string[]): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const have = u.permission_codes ?? [];
    if (have.includes('*')) return true;
    return codes.some((c) => have.includes(c));
  }
}
