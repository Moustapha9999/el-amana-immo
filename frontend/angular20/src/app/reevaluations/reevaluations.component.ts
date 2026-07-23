import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';

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
  imports: [RouterLink, DatePipe, DecimalPipe, MatTableModule, MatButtonModule],
  templateUrl: './reevaluations.component.html',
})
export class ReevaluationsComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<ReevalRow[]>([]);
  readonly columns = ['date', 'code', 'designation', 'ancienne', 'nouvelle', 'actions'];

  ngOnInit(): void {
    this.api.get<Paginated<ReevalRow>>('/reevaluations', { page: 1, size: 100 }).subscribe((r) => this.rows.set(r.items));
  }
}
