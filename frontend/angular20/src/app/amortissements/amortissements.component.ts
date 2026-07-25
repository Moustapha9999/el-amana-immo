import { MontantPipe } from '../shared/montant.pipe';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { statutLabel } from '../immobilisations/immobilisation.constants';
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

@Component({
  selector: 'app-amortissements',
  imports: [RouterLink, MontantPipe, MatTableModule, MatButtonModule],
  templateUrl: './amortissements.component.html',
  styleUrl: './amortissements.component.css',
})
export class AmortissementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);

  readonly rows = signal<ImmoRow[]>([]);
  readonly loading = signal(true);
  readonly statutLabel = statutLabel;
  readonly columns = ['code', 'designation', 'type', 'statut', 'valeur', 'actions'];

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<Paginated<ImmoRow>>('/immobilisations', { page: 1, size: 100 }).subscribe({
      next: (res) => {
        this.rows.set(
          res.items.filter(
            (i) => i.categorie?.amortissable && ['en_service', 'suspendue', 'en_cours'].includes(i.statut),
          ),
        );
        this.loading.set(false);
      },
      error: () => {
        this.rows.set([]);
        this.loading.set(false);
        void this.dialogs.error('Chargement impossible').subscribe();
      },
    });
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
              .subscribe(() => this.load());
          },
          error: (err) => {
            void this.dialogs.error(err.error?.detail ?? 'Suppression impossible').subscribe();
          },
        });
      });
  }
}
