import { DecimalPipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { statutLabel } from './immobilisation.constants';

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
  imports: [MatTableModule, MatButtonModule, MatIconModule, DecimalPipe, RouterLink],
  templateUrl: './immobilisations-list.component.html',
  styleUrl: './immobilisations-list.component.css',
})
export class ImmobilisationsListComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);

  readonly rows = signal<ImmobilisationRow[]>([]);
  readonly loading = signal(true);
  readonly displayedColumns = ['code', 'designation', 'famille', 'valeur', 'statut', 'actions'];
  readonly statutLabel = statutLabel;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<Paginated<ImmobilisationRow>>('/immobilisations', { page: 1, size: 50 }).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.rows.set([]);
        this.loading.set(false);
        void this.dialogs.error('Chargement impossible').subscribe();
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
              .subscribe(() => this.load());
          },
          error: (err) => {
            void this.dialogs.error(err.error?.detail ?? 'Suppression impossible').subscribe();
          },
        });
      });
  }
}
