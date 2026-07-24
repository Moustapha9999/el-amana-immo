import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface CessionRow {
  id: string;
  immobilisation_id: string;
  date_cession: string;
  prix_cession: string;
  vnc: string;
  plus_value: string;
  moins_value: string;
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
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    DecimalPipe,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
  ],
  templateUrl: './cessions.component.html',
  styleUrl: './cessions.component.css',
})
export class CessionsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly rows = signal<CessionRow[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly columns = ['date', 'code', 'designation', 'prix', 'vnc', 'resultat', 'actions'];

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

  resetFilters(): void {
    this.filterForm.reset({ date_debut: '', date_fin: '', search: '' });
    this.load();
  }

  resultatLabel(row: CessionRow): string {
    const plus = Number(row.plus_value) || 0;
    const moins = Number(row.moins_value) || 0;
    if (plus > 0) {
      return `+${plus.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    if (moins > 0) {
      return `-${moins.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
