import { DatePipe } from '@angular/common';
import { MontantPipe } from '../shared/montant.pipe';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface EcritureRow {
  id: string;
  journal_code: string;
  date_ecriture: string;
  libelle: string;
  compte_debit: string;
  compte_credit: string;
  montant: string;
  reference: string | null;
  generee_auto: boolean;
  validee: boolean;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-ecritures',
  imports: [ReactiveFormsModule, RouterLink, DatePipe, MontantPipe, MatButtonModule, MatIconModule, MatTableModule, PaginationComponent],
  templateUrl: './ecritures.component.html',
  styleUrl: './ecritures.component.css',
})
export class EcrituresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly rows = signal<EcritureRow[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = 50;
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  private lastQuery: Record<string, string> = {};
  readonly displayedColumns = [
    'date_ecriture',
    'journal_code',
    'libelle',
    'compte_debit',
    'compte_credit',
    'montant',
    'reference',
    'generee_auto',
    'actions',
  ];

  readonly filterForm = this.fb.nonNullable.group({
    search: [''],
    journal_code: [''],
    date_debut: [''],
    date_fin: [''],
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const f = this.filterForm.getRawValue();
    const query: Record<string, string> = {};
    if (f.search.trim()) {
      query['search'] = f.search.trim();
    }
    if (f.journal_code.trim()) {
      query['journal_code'] = f.journal_code.trim();
    }
    if (f.date_debut) {
      query['date_debut'] = f.date_debut;
    }
    if (f.date_fin) {
      query['date_fin'] = f.date_fin;
    }
    const params: Record<string, string> = {
      ...query,
      page: String(this.page()),
      size: String(this.pageSize),
    };
    this.loading.set(true);
    this.api.get<Paginated<EcritureRow>>('/ecritures', params).subscribe({
      next: (res) => {
        this.lastQuery = query;
        this.rows.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        void this.dialogs.error('Impossible de charger les écritures').subscribe();
      },
    });
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  resetFilters(): void {
    this.filterForm.reset({ search: '', journal_code: '', date_debut: '', date_fin: '' });
    this.page.set(1);
    this.load();
  }

  export(format: 'xlsx' | 'pdf'): void {
    const params: Record<string, string> = { ...this.lastQuery, format };
    this.exporting.set(format);
    this.api.download('/reporting/ecritures/export', params).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        const ext = format === 'pdf' ? 'pdf' : 'xlsx';
        this.saveBlob(blob, `ecritures-bea-digital.${ext}`);
      },
      error: () => {
        this.exporting.set(null);
        void this.dialogs.error('Export impossible').subscribe();
      },
    });
  }

  private saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}
