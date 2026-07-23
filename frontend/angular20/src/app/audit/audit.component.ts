import { DatePipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { AUDIT_ENTITY_OPTIONS, auditEntityLabel } from './audit.constants';

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
  imports: [
    ReactiveFormsModule,
    DatePipe,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatTableModule,
  ],
  templateUrl: './audit.component.html',
})
export class AuditComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<AuditRow[]>([]);
  readonly total = signal(0);
  readonly error = signal<string | null>(null);
  readonly displayedColumns = ['created_at', 'user_email', 'action', 'entity', 'entity_id', 'ip_address'];
  readonly entityOptions = AUDIT_ENTITY_OPTIONS;
  readonly entityLabel = auditEntityLabel;

  readonly filterForm = this.fb.nonNullable.group({
    entity: [''],
    action: [''],
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = { page: '1', size: '100' };
    if (f.entity.trim()) {
      params['entity'] = f.entity.trim();
    }
    if (f.action.trim()) {
      params['action'] = f.action.trim();
    }
    this.api.get<Paginated<AuditRow>>('/audit', params).subscribe({
      next: (res) => {
        this.error.set(null);
        this.rows.set(res.items);
        this.total.set(res.total);
      },
      error: (err) => {
        this.rows.set([]);
        this.error.set(err.error?.detail ?? 'Accès audit refusé (rôle auditeur ou administrateur requis).');
      },
    });
  }

  exportExcel(): void {
    this.api.download('/reporting/audit/export').subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'audit-el-amana.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    });
  }
}
