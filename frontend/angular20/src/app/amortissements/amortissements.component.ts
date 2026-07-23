import { DecimalPipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { statutLabel } from '../immobilisations/immobilisation.constants';

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
  imports: [RouterLink, DecimalPipe, MatTableModule, MatButtonModule],
  templateUrl: './amortissements.component.html',
})
export class AmortissementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<ImmoRow[]>([]);
  readonly statutLabel = statutLabel;
  readonly columns = ['code', 'designation', 'type', 'statut', 'valeur', 'actions'];

  ngOnInit(): void {
    this.api.get<Paginated<ImmoRow>>('/immobilisations', { page: 1, size: 100 }).subscribe((res) => {
      this.rows.set(
        res.items.filter(
          (i) => i.categorie?.amortissable && ['en_service', 'suspendue', 'en_cours'].includes(i.statut),
        ),
      );
    });
  }
}
