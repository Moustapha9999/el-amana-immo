import { DatePipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { formatMontant } from '../shared/montant.pipe';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface CessionRow {
  id: string;
  immobilisation_id: string;
  date_cession: string;
  prix_cession: string;
  vnc: string;
  plus_value: string;
  moins_value: string;
  reference: string | null;
  observations: string | null;
  libelle: string | null;
  code_inventaire: string | null;
  designation: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-cessions',
  standalone: true,
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
    PaginationComponent,
  ],
  templateUrl: './cessions.component.html',
  styleUrl: './cessions.component.css',
})
export class CessionsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly montant = formatMontant;

  readonly rows = signal<CessionRow[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = 50;
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  readonly columns = ['date', 'code', 'reference', 'designation', 'prix', 'vnc', 'resultat', 'actions'];

  readonly filterForm = this.fb.nonNullable.group({
    date_debut: [''],
    date_fin: [''],
    search: [''],
  });

  readonly kpi = computed(() => {
    const items = this.rows();
    let prix = 0;
    let plus = 0;
    let moins = 0;
    for (const row of items) {
      prix += Number(row.prix_cession) || 0;
      plus += Number(row.plus_value) || 0;
      moins += Number(row.moins_value) || 0;
    }
    return { prix, plus, moins };
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string | number> = { page: this.page(), size: this.pageSize };
    if (f.date_debut) {
      params['date_debut'] = f.date_debut;
    }
    if (f.date_fin) {
      params['date_fin'] = f.date_fin;
    }
    if (f.search.trim()) {
      params['search'] = f.search.trim();
    }
    this.loading.set(true);
    this.api.get<Paginated<CessionRow>>('/cessions', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        void this.dialogs.error('Impossible de charger les cessions').subscribe();
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
    this.filterForm.reset({ date_debut: '', date_fin: '', search: '' });
    this.page.set(1);
    this.load();
  }

  export(format: 'xlsx' | 'pdf'): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = { format };
    if (f.date_debut) {
      params['date_debut'] = f.date_debut;
    }
    if (f.date_fin) {
      params['date_fin'] = f.date_fin;
    }
    if (f.search.trim()) {
      params['search'] = f.search.trim();
    }
    this.exporting.set(format);
    this.api.download('/reporting/cessions/export', params).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        this.saveBlob(blob, `cessions-el-amana.${format === 'pdf' ? 'pdf' : 'xlsx'}`);
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

  resultatLabel(row: CessionRow): string {
    const plus = Number(row.plus_value) || 0;
    const moins = Number(row.moins_value) || 0;
    if (plus > 0) {
      return `+${formatMontant(plus)}`;
    }
    if (moins > 0) {
      return `-${formatMontant(moins)}`;
    }
    return '0,00';
  }

  resultatKind(row: CessionRow): 'plus' | 'moins' | 'neutre' {
    if ((Number(row.plus_value) || 0) > 0) {
      return 'plus';
    }
    if ((Number(row.moins_value) || 0) > 0) {
      return 'moins';
    }
    return 'neutre';
  }
}
