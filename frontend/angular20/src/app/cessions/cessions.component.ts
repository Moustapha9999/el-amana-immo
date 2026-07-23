import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';

interface CessionRow {
  id: string;
  immobilisation_id: string;
  date_cession: string;
  prix_cession: string;
  vnc: string;
  plus_value: string;
  moins_value: string;
  code_inventaire: string | null;
  designation: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-cessions',
  imports: [RouterLink, DatePipe, DecimalPipe, MatTableModule, MatButtonModule],
  templateUrl: './cessions.component.html',
})
export class CessionsComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<CessionRow[]>([]);
  readonly columns = ['date', 'code', 'designation', 'prix', 'vnc', 'plus', 'moins', 'actions'];

  ngOnInit(): void {
    this.api.get<Paginated<CessionRow>>('/cessions', { page: 1, size: 100 }).subscribe((res) => this.rows.set(res.items));
  }
}
