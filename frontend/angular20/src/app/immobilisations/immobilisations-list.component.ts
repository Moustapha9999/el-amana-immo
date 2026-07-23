import { DecimalPipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { PageHeaderComponent } from '../shared/page-header.component';
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
  page: number;
  size: number;
}

@Component({
  selector: 'app-immobilisations-list',
  imports: [MatTableModule, MatButtonModule, DecimalPipe, RouterLink, PageHeaderComponent],
  templateUrl: './immobilisations-list.component.html',
})
export class ImmobilisationsListComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<ImmobilisationRow[]>([]);
  readonly displayedColumns = ['code', 'designation', 'famille', 'valeur', 'statut', 'actions'];
  readonly statutLabel = statutLabel;

  ngOnInit(): void {
    this.api.get<Paginated<ImmobilisationRow>>('/immobilisations', { page: 1, size: 50 }).subscribe((res) => {
      this.rows.set(res.items);
    });
  }
}
