import { Component, inject, OnInit, signal } from '@angular/core';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';

interface UserRow {
  id: string;
  email: string;
  full_name: string;
  is_superuser: boolean;
  roles: { code: string; label: string }[];
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-utilisateurs',
  imports: [MatTableModule],
  templateUrl: './utilisateurs.component.html',
})
export class UtilisateursComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<UserRow[]>([]);
  readonly error = signal<string | null>(null);
  readonly columns = ['full_name', 'email', 'roles', 'superuser'];

  ngOnInit(): void {
    this.api.get<Paginated<UserRow>>('/users', { page: 1, size: 100 }).subscribe({
      next: (res) => {
        this.error.set(null);
        this.rows.set(res.items);
      },
      error: (err) => {
        this.error.set(err.error?.detail ?? 'Accès réservé aux administrateurs.');
      },
    });
  }

  rolesLabel(row: UserRow): string {
    return row.roles.map((r) => r.label).join(', ') || '—';
  }
}
