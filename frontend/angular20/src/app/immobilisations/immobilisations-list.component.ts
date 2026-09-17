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
import {
  NATURE_IMMO_OFFICIELLE,
  STATUT_IMMOBILISATION_LABELS,
  statutLabel,
} from './immobilisation.constants';

interface ImmobilisationRow {
  id: string;
  code_inventaire: string;
  designation: string;
  valeur_brute: string;
  statut: string;
  categorie?: { famille: string } | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-immobilisations-list',
  imports: [
    ReactiveFormsModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MontantPipe,
    RouterLink,
    PaginationComponent,
  ],
  templateUrl: './immobilisations-list.component.html',
  styleUrl: './immobilisations-list.component.css',
})
export class ImmobilisationsListComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<ImmobilisationRow[]>([]);
  readonly loading = signal(true);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly displayedColumns = ['code', 'designation', 'famille', 'valeur', 'statut', 'actions'];
  readonly statutLabel = statutLabel;

  readonly statutOptions = Object.entries(STATUT_IMMOBILISATION_LABELS)
    .filter(([code]) => !['cession', 'rebut'].includes(code))
    .map(([value, label]) => ({ value, label }));

  readonly typeOptions = NATURE_IMMO_OFFICIELLE.map((n) => ({
    value: n.libelle,
    label: `${n.libelle} (${n.compte})`,
  }));

  readonly filterForm = this.fb.nonNullable.group({
    search: [''],
    statut: [''],
    famille: [''],
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.pageSize,
    };
    if (f.search.trim()) {
      params['search'] = f.search.trim();
    }
    if (f.statut) {
      params['statuts'] = f.statut;
    }
    if (f.famille) {
      params['famille'] = f.famille;
    }
    this.loading.set(true);
    this.api.get<Paginated<ImmobilisationRow>>('/immobilisations', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: () => {
        this.rows.set([]);
        this.total.set(0);
        this.loading.set(false);
        void this.dialogs.error('Chargement impossible').subscribe();
      },
    });
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  resetFilters(): void {
    this.filterForm.reset({ search: '', statut: '', famille: '' });
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  export(format: 'xlsx' | 'pdf'): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = { format };
    if (f.search.trim()) {
      params['search'] = f.search.trim();
    }
    if (f.statut) {
      params['statuts'] = f.statut;
    }
    if (f.famille) {
      params['famille'] = f.famille;
    }
    this.exporting.set(format);
    this.api.download('/reporting/immobilisations/export', params).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `immobilisations-bea-digital.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      error: () => {
        this.exporting.set(null);
        void this.dialogs.error('Export impossible').subscribe();
      },
    });
  }

  remove(row: ImmobilisationRow): void {
    this.dialogs
      .confirmAction(
        'suppression',
        `Voulez-vous vraiment supprimer l'immobilisation « ${row.code_inventaire} » ?`,
      )
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.api.delete<{ message: string }>(`/immobilisations/${row.id}`).subscribe({
          next: () => {
            this.dialogs
              .successAction('suppression', `« ${row.code_inventaire} » a été supprimée.`)
              .subscribe(() => {
                if (this.rows().length === 1 && this.page() > 1) {
                  this.page.update((p) => p - 1);
                }
                this.load();
              });
          },
          error: (err) => {
            void this.dialogs.error(err.error?.detail ?? 'Suppression impossible').subscribe();
          },
        });
      });
  }
}
