import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';

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
  imports: [RouterLink, DatePipe, DecimalPipe, MatTableModule, MatButtonModule],
  templateUrl: './rebuts.component.html',
})
export class RebutsComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<RebutRow[]>([]);
  readonly columns = ['date', 'code', 'designation', 'vnc', 'motif', 'actions'];

  ngOnInit(): void {
    this.api.get<Paginated<RebutRow>>('/rebuts', { page: 1, size: 100 }).subscribe((res) => this.rows.set(res.items));
  }
}
