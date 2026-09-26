import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { PaginationComponent } from '../shared/pagination.component';

interface Doc {
  id: string;
  filename: string;
  title?: string | null;
  reference?: string | null;
  doc_type?: string | null;
  module_code: string;
  espace_code: string;
  entity: string;
  entity_id: string;
  created_at: string | null;
  size_bytes: number;
  ocr_status?: string | null;
  security_level?: string | null;
}

interface ListOut {
  items: Doc[];
  total: number;
  page: number;
  size: number;
  ocr_pending_hint?: boolean;
}

@Component({
  selector: 'bea-archives-generales',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, DatePipe, PaginationComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Archive Générale</p>
          <h1>Recherche documentaire</h1>
        </div>
        <span class="bea-mg__count">{{ total() }} résultat(s)</span>
      </header>

      <form class="bea-mg__search bea-ag__search" (ngSubmit)="$event.preventDefault(); search()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input [(ngModel)]="q" name="q" placeholder="Mot-clé, référence, nom…" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>apartment</mat-icon>
          <select [(ngModel)]="espaceFilter" name="espace">
            <option value="">Tous mes départements</option>
            <option value="moyens-generaux">Moyens Généraux</option>
            <option value="comptabilite">Comptabilité</option>
            <option value="rh">RH</option>
            <option value="credit">Crédit</option>
            <option value="informatique">Informatique</option>
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>folder</mat-icon>
          <input [(ngModel)]="moduleFilter" name="module" placeholder="Module…" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>category</mat-icon>
          <input [(ngModel)]="docType" name="docType" placeholder="Type…" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>event</mat-icon>
          <input type="date" [(ngModel)]="dateDebut" name="dateDebut" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>event</mat-icon>
          <input type="date" [(ngModel)]="dateFin" name="dateFin" />
        </label>
        <label class="bea-ag__ocr-check">
          <input type="checkbox" [(ngModel)]="searchOcr" name="searchOcr" />
          Rechercher dans le texte OCR
        </label>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="search()">
          <mat-icon>search</mat-icon> Rechercher
        </button>
      </form>

      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (ocrHint()) {
        <p class="bea-stock-page__kicker">
          Aucun résultat plein texte — des documents sont encore en traitement OCR.
        </p>
      }

      <div class="bea-mg__panel">
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Fichier</th>
                <th>Département</th>
                <th>Module</th>
                <th>Type</th>
                <th>OCR</th>
                <th>Date</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (d of docs(); track d.id; let i = $index) {
                <tr [style.--i]="i">
                  <td>{{ d.title || d.filename }}</td>
                  <td>{{ d.espace_code }}</td>
                  <td>{{ d.module_code }}</td>
                  <td>{{ d.doc_type || d.entity }}</td>
                  <td>
                    <span class="bea-ocr-badge" [attr.data-status]="d.ocr_status || 'pending'">
                      {{ ocrLabel(d.ocr_status) }}
                    </span>
                    @if (d.ocr_status === 'failed') {
                      <button type="button" class="bea-mg__icon-btn" title="Relancer OCR" (click)="retryOcr(d)">
                        <mat-icon>refresh</mat-icon>
                      </button>
                    }
                  </td>
                  <td>{{ d.created_at ? (d.created_at | date: 'dd/MM/yyyy') : '—' }}</td>
                  <td>
                    <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="download(d)">
                      <mat-icon>download</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7">
                    <div class="bea-mg__empty">
                      <mat-icon>manage_search</mat-icon>
                      <p>Aucun document dans votre périmètre.</p>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (total() > 0) {
          <app-pagination
            [page]="page()"
            [total]="total()"
            [pageSize]="pageSize"
            label="document(s)"
            (pageChange)="goToPage($event)"
          />
        }
      </div>
    </section>
  `,
  styles: `
    .bea-ag__search { flex-wrap: wrap; }
    .bea-ag__ocr-check {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.88rem;
      color: #334155;
      white-space: nowrap;
    }
    .bea-ocr-badge {
      display: inline-block;
      font-size: 0.72rem;
      font-weight: 650;
      padding: 0.15rem 0.45rem;
      border-radius: 0.35rem;
      background: #e2e8f0;
      color: #475569;
    }
    .bea-ocr-badge[data-status='pending'] { background: #fef3c7; color: #92400e; }
    .bea-ocr-badge[data-status='processing'] { background: #dbeafe; color: #1e40af; }
    .bea-ocr-badge[data-status='done'] { background: #dcfce7; color: #166534; }
    .bea-ocr-badge[data-status='failed'] { background: #fee2e2; color: #991b1b; }
  `,
})
export class ArchivesGeneralesComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly docs = signal<Doc[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly erreur = signal<string | null>(null);
  readonly ocrHint = signal(false);

  q = '';
  espaceFilter = '';
  moduleFilter = '';
  docType = '';
  dateDebut = '';
  dateFin = '';
  searchOcr = false;

  ngOnInit(): void {
    this.load();
  }

  ocrLabel(status: string | null | undefined): string {
    switch (status) {
      case 'processing':
        return 'En cours';
      case 'done':
        return 'Terminé';
      case 'failed':
        return 'Échec';
      default:
        return 'En attente';
    }
  }

  search(): void {
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  load(): void {
    this.erreur.set(null);
    const params: Record<string, string | number | boolean> = {
      page: this.page(),
      size: this.pageSize,
      search_ocr: this.searchOcr,
    };
    if (this.q.trim()) params['q'] = this.q.trim();
    if (this.espaceFilter) params['espace_code'] = this.espaceFilter;
    if (this.moduleFilter.trim()) params['module_code'] = this.moduleFilter.trim();
    if (this.docType.trim()) params['doc_type'] = this.docType.trim();
    if (this.dateDebut) params['date_debut'] = this.dateDebut;
    if (this.dateFin) params['date_fin'] = this.dateFin;

    this.api.get<ListOut>('/doc-archives/general', params).subscribe({
      next: (res) => {
        this.docs.set(res.items ?? []);
        this.total.set(res.total ?? 0);
        this.ocrHint.set(!!res.ocr_pending_hint && this.searchOcr);
      },
      error: () => {
        this.docs.set([]);
        this.total.set(0);
        this.erreur.set('Chargement Archive Générale impossible (permission archives.general.view ?).');
      },
    });
  }

  download(d: Doc): void {
    this.api.download(`/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename || 'document';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Téléchargement refusé.'),
    });
  }

  retryOcr(d: Doc): void {
    this.api.post(`/documents/${d.id}/retry-ocr`, {}).subscribe({
      next: () => this.load(),
      error: () => this.erreur.set('Relance OCR refusée.'),
    });
  }
}
