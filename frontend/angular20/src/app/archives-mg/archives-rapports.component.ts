import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { feedbackSignal } from '../core/feedback/feedback-signal';

@Component({
  selector: 'bea-archives-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">{{ kicker }}</p>
          <h1>Rapports documentaires</h1>
        </div>
      </header>


      <form class="bea-mg__search" (ngSubmit)="$event.preventDefault()">
        <label class="bea-mg__field">
          <mat-icon>folder</mat-icon>
          <input [(ngModel)]="moduleCode" name="module" placeholder="Module…" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>category</mat-icon>
          <input [(ngModel)]="docType" name="docType" placeholder="Type…" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>manage_search</mat-icon>
          <select [(ngModel)]="ocrStatus" name="ocr">
            <option value="">Tous OCR</option>
            <option value="done">Terminé</option>
            <option value="pending">En attente</option>
            <option value="processing">En cours</option>
            <option value="failed">Échec</option>
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>event</mat-icon>
          <input type="date" [(ngModel)]="dateDebut" name="debut" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>event</mat-icon>
          <input type="date" [(ngModel)]="dateFin" name="fin" />
        </label>
      </form>

      <div class="bea-ag-exports" [class.bea-ag-exports--two]="mode === 'general'">
        @if (mode !== 'general') {
          <article>
            <mat-icon>text_snippet</mat-icon>
            <h2>CSV</h2>
            <p>Liste filtrée, ouvrable dans un tableur.</p>
            <button type="button" class="bea-ag-dl" (click)="exportFmt('csv')" [disabled]="busy()">
              <mat-icon>download</mat-icon> Télécharger
            </button>
          </article>
        }
        <article>
          <span class="bea-ag-exports__mark bea-ag-exports__mark--xls"><mat-icon>table_view</mat-icon></span>
          <h2>Excel</h2>
          <p>Classeur mis en forme, mêmes filtres et mêmes droits.</p>
          <button type="button" class="bea-ag-dl bea-ag-dl--xls" (click)="exportFmt('xlsx')" [disabled]="busy()">
            <mat-icon>download</mat-icon> Télécharger
          </button>
        </article>
        <article>
          <span class="bea-ag-exports__mark bea-ag-exports__mark--pdf"><mat-icon>picture_as_pdf</mat-icon></span>
          <h2>PDF</h2>
          <p>Rapport imprimable des documents correspondant aux filtres.</p>
          <button type="button" class="bea-ag-dl bea-ag-dl--pdf" (click)="exportFmt('pdf')" [disabled]="busy()">
            <mat-icon>download</mat-icon> Télécharger
          </button>
        </article>
      </div>
      <p class="bea-stock-page__kicker">Les exports respectent vos permissions et les filtres actifs.</p>
    </section>
  `,
  styles: `
    .bea-ag-exports { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.8rem; margin-top: 0.8rem; }
    .bea-ag-exports--two { grid-template-columns: repeat(2, minmax(0, 22rem)); }
    .bea-ag-exports article {
      background: #fff; border: 1px solid #e2e8f0; border-radius: 0.85rem; padding: 1.05rem 1.1rem 1rem;
      display: grid; gap: 0.35rem; justify-items: start;
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
    }
    .bea-ag-exports h2 { margin: 0.15rem 0 0; font-size: 1.05rem; }
    .bea-ag-exports p { margin: 0 0 0.45rem; color: #64748b; font-size: 0.84rem; }
    .bea-ag-exports__mark {
      width: 2.4rem; height: 2.4rem; border-radius: 0.65rem;
      display: grid; place-items: center;
    }
    .bea-ag-exports__mark--xls { background: #ecfdf5; color: #166534; }
    .bea-ag-exports__mark--pdf { background: #eff6ff; color: #1a5278; }
    .bea-ag-dl {
      display: inline-flex; align-items: center; gap: 0.4rem;
      margin-top: auto; border: 0; border-radius: 0.55rem;
      padding: 0.55rem 0.95rem; font: inherit; font-size: 0.88rem; font-weight: 650;
      color: #fff; background: #1a5278; cursor: pointer;
      box-shadow: 0 6px 14px rgba(26, 82, 120, 0.22);
      transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
    }
    .bea-ag-dl mat-icon { font-size: 1.05rem; width: 1.05rem; height: 1.05rem; color: inherit; }
    .bea-ag-dl:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(26, 82, 120, 0.28); }
    .bea-ag-dl--xls { background: #166534; box-shadow: 0 6px 14px rgba(22, 101, 52, 0.22); }
    .bea-ag-dl--xls:hover { background: #14532d; box-shadow: 0 8px 18px rgba(22, 101, 52, 0.28); }
    .bea-ag-dl--pdf { background: #1a5278; }
    .bea-ag-dl--pdf:hover { background: #154360; }
    .bea-ag-dl:disabled { opacity: 0.55; cursor: wait; transform: none; }
    @media (max-width: 900px) {
      .bea-ag-exports, .bea-ag-exports--two { grid-template-columns: 1fr; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-ag-dl, .bea-ag-dl:hover { transition: none; transform: none; }
    }
  `,
})
export class ArchivesRapportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);

  mode: 'mg' | 'general' = 'mg';
  kicker = 'Archives MG';

  moduleCode = '';
  docType = '';
  ocrStatus = '';
  dateDebut = '';
  dateFin = '';

  readonly busy = signal(false);
  readonly erreur = feedbackSignal('error', null);
  readonly msg = feedbackSignal('success', '');

  ngOnInit(): void {
    const mode = this.route.snapshot.data['archivesMode'] as 'mg' | 'general' | undefined;
    if (mode === 'general') {
      this.mode = 'general';
      this.kicker = 'Archive Générale';
    }
  }

  exportFmt(format: string): void {
    this.busy.set(true);
    this.erreur.set(null);
    const params: Record<string, string> = { format, report_key: 'documents' };
    if (this.moduleCode.trim()) params['module_code'] = this.moduleCode.trim();
    if (this.docType.trim()) params['doc_type'] = this.docType.trim();
    if (this.ocrStatus) params['ocr_status'] = this.ocrStatus;
    if (this.dateDebut) params['date_debut'] = this.dateDebut;
    if (this.dateFin) params['date_fin'] = this.dateFin;

    const path =
      this.mode === 'general'
        ? '/doc-archives/general/rapports/export'
        : '/mg/archives/rapports/export';

    this.api.download(path, params).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `documents.${format === 'xlsx' ? 'xlsx' : format}`;
        a.click();
        URL.revokeObjectURL(url);
        this.msg.set('Export téléchargé.');
        this.busy.set(false);
      },
      error: () => {
        this.erreur.set('Export refusé (permission export ?).');
        this.busy.set(false);
      },
    });
  }
}
