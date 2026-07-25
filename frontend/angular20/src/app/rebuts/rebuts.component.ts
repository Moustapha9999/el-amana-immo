import { DatePipe } from '@angular/common';
import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface RebutRow {
  id: string;
  immobilisation_id: string;
  date_rebut: string;
  vnc: string;
  motif: string | null;
  code_inventaire: string | null;
  designation: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-rebuts',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    MontantPipe,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
  ],
  templateUrl: './rebuts.component.html',
  styleUrl: './rebuts.component.css',
})
export class RebutsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly rows = signal<RebutRow[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly columns = ['date', 'code', 'designation', 'vnc', 'motif', 'actions'];

  readonly filterForm = this.fb.nonNullable.group({
    date_debut: [''],
    date_fin: [''],
    search: [''],
  });

  readonly kpi = computed(() => {
    let vnc = 0;
    for (const row of this.rows()) {
      vnc += Number(row.vnc) || 0;
    }
    return { vnc };
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string | number> = { page: 1, size: 100 };
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
    this.api.get<Paginated<RebutRow>>('/rebuts', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        void this.dialogs.error('Impossible de charger les rebuts').subscribe();
      },
    });
  }

  resetFilters(): void {
    this.filterForm.reset({ date_debut: '', date_fin: '', search: '' });
    this.load();
  }
}
