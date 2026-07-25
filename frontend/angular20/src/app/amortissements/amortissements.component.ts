import { MontantPipe } from '../shared/montant.pipe';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import {
  NATURE_IMMO_OFFICIELLE,
  statutLabel,
} from '../immobilisations/immobilisation.constants';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface ImmoRow {
  id: string;
  code_inventaire: string;
  designation: string;
  statut: string;
  valeur_brute: string;
  categorie?: { amortissable: boolean; famille: string } | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

const DEFAULT_STATUTS = 'en_service,suspendue,en_cours';

@Component({
  selector: 'app-amortissements',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MontantPipe,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    PaginationComponent,
  ],
  templateUrl: './amortissements.component.html',
  styleUrl: './amortissements.component.css',
})
export class AmortissementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<ImmoRow[]>([]);
  readonly loading = signal(true);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly statutLabel = statutLabel;
  readonly columns = ['code', 'designation', 'type', 'statut', 'valeur', 'actions'];

  readonly statutOptions = [
    { value: '', label: 'Tous (périmètre amort.)' },
    { value: 'en_service', label: 'En service' },
    { value: 'suspendue', label: 'Suspendue' },
    { value: 'en_cours', label: 'En cours' },
  ];

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
      amortissable: 'true',
      statuts: f.statut || DEFAULT_STATUTS,
    };
    if (f.search.trim()) {
      params['search'] = f.search.trim();
    }
    if (f.famille) {
      params['famille'] = f.famille;
    }
    this.loading.set(true);
    this.api.get<Paginated<ImmoRow>>('/immobilisations', params).subscribe({
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

  remove(row: ImmoRow): void {
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
