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

interface ReevalRow {
  id: string;
  immobilisation_id: string;
  date_reevaluation: string;
  ancienne_valeur: string;
  nouvelle_valeur: string;
  justificatif: string | null;
  code_inventaire: string | null;
  designation: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-reevaluations',
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
  templateUrl: './reevaluations.component.html',
  styleUrl: './reevaluations.component.css',
})
export class ReevaluationsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly montant = formatMontant;

  readonly rows = signal<ReevalRow[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = 50;
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  readonly columns = ['date', 'code', 'designation', 'ancienne', 'nouvelle', 'ecart', 'justificatif', 'actions'];

  readonly filterForm = this.fb.nonNullable.group({
    date_debut: [''],
    date_fin: [''],
    search: [''],
  });

  readonly kpi = computed(() => {
    let hausses = 0;
    let baisses = 0;
    for (const row of this.rows()) {
      const ecart = (Number(row.nouvelle_valeur) || 0) - (Number(row.ancienne_valeur) || 0);
      if (ecart > 0) {
        hausses += ecart;
      } else if (ecart < 0) {
        baisses += Math.abs(ecart);
      }
    }
    return { hausses, baisses };
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
    this.api.get<Paginated<ReevalRow>>('/reevaluations', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        void this.dialogs.error('Impossible de charger les réévaluations').subscribe();
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
    this.api.download('/reporting/reevaluations/export', params).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        this.saveBlob(blob, `reevaluations-el-amana.${format === 'pdf' ? 'pdf' : 'xlsx'}`);
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

  ecartValue(row: ReevalRow): number {
    return (Number(row.nouvelle_valeur) || 0) - (Number(row.ancienne_valeur) || 0);
  }

  ecartKind(row: ReevalRow): 'up' | 'down' | 'neutre' {
    const e = this.ecartValue(row);
    if (e > 0) {
      return 'up';
    }
    if (e < 0) {
      return 'down';
    }
    return 'neutre';
  }

  ecartLabel(row: ReevalRow): string {
    const e = this.ecartValue(row);
    const abs = formatMontant(Math.abs(e));
    if (e > 0) {
      return `+${abs}`;
    }
    if (e < 0) {
      return `-${abs}`;
    }
    return '0,00';
  }
}
