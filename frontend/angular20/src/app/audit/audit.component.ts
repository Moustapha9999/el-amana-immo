import { DatePipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { AUDIT_ENTITY_OPTIONS, auditActionLabel, auditEntityLabel } from './audit.constants';

interface AuditRow {
  id: string;
  user_email: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  ip_address: string | null;
  created_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-audit',
  imports: [ReactiveFormsModule, DatePipe, MatButtonModule, MatIconModule, MatTableModule, PaginationComponent],
  templateUrl: './audit.component.html',
  styleUrl: './audit.component.css',
})
export class AuditComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly rows = signal<AuditRow[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = 50;
  readonly loading = signal(true);
  readonly exporting = signal(false);
  readonly error = signal<string | null>(null);
  readonly columns = ['created_at', 'user_email', 'action', 'entity', 'entity_id', 'ip_address'];
  readonly entityOptions = AUDIT_ENTITY_OPTIONS;

  readonly kpi = computed(() => {
    const items = this.rows();
    const logins = items.filter((r) => r.action === 'login').length;
    return {
      total: this.total(),
      logins,
      mutations: Math.max(0, items.length - logins),
    };
  });

  readonly filterForm = this.fb.nonNullable.group({
    search: '',
    entity: '',
    action: '',
    date_debut: '',
    date_fin: '',
  });

  ngOnInit(): void {
    this.load();
  }

  entityLabel = auditEntityLabel;
  actionLabel = auditActionLabel;

  actionKind(action: string): 'login' | 'create' | 'update' | 'delete' | 'other' {
    if (action === 'login') {
      return 'login';
    }
    if (action === 'create' || action === 'scan_inventaire') {
      return 'create';
    }
    if (action === 'update' || action === 'mettre_en_service' || action === 'transfert_agence') {
      return 'update';
    }
    if (action === 'delete') {
      return 'delete';
    }
    return 'other';
  }

  shortId(id: string | null): string {
    if (!id) {
      return '—';
    }
    return id.length > 12 ? `${id.slice(0, 8)}…` : id;
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.get<Paginated<AuditRow>>('/audit', this.filterParams()).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: (err) => {
        this.rows.set([]);
        this.total.set(0);
        this.loading.set(false);
        this.error.set(err.error?.detail ?? 'Accès réservé aux administrateurs et auditeurs.');
      },
    });
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  resetFilters(): void {
    this.filterForm.reset({
      search: '',
      entity: '',
      action: '',
      date_debut: '',
      date_fin: '',
    });
    this.page.set(1);
    this.load();
  }

  exportExcel(): void {
    this.exporting.set(true);
    const params = this.filterParams();
    delete params['page'];
    delete params['size'];
    this.api.download('/reporting/audit/export', params).subscribe({
      next: (blob) => {
        this.exporting.set(false);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'audit-bea-digital.xlsx';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => {
        this.exporting.set(false);
        void this.dialogs.error('Export impossible').subscribe();
      },
    });
  }

  private filterParams(): Record<string, string> {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = { page: String(this.page()), size: String(this.pageSize) };
    if (f.search.trim()) {
      params['search'] = f.search.trim();
    }
    if (f.entity.trim()) {
      params['entity'] = f.entity.trim();
    }
    if (f.action.trim()) {
      params['action'] = f.action.trim();
    }
    if (f.date_debut) {
      params['date_debut'] = f.date_debut;
    }
    if (f.date_fin) {
      params['date_fin'] = f.date_fin;
    }
    return params;
  }
}
