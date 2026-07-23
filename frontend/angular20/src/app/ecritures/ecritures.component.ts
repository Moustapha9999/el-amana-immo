import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';

interface EcritureRow {
  id: string;
  journal_code: string;
  date_ecriture: string;
  libelle: string;
  compte_debit: string;
  compte_credit: string;
  montant: string;
  reference: string | null;
  generee_auto: boolean;
  validee: boolean;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-ecritures',
  imports: [
    ReactiveFormsModule,
    DatePipe,
    DecimalPipe,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatTableModule,
  ],
  templateUrl: './ecritures.component.html',
})
export class EcrituresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<EcritureRow[]>([]);
  readonly total = signal(0);
  readonly displayedColumns = [
    'date_ecriture',
    'journal_code',
    'libelle',
    'compte_debit',
    'compte_credit',
    'montant',
    'reference',
    'generee_auto',
  ];

  readonly filterForm = this.fb.nonNullable.group({
    date_debut: [''],
    date_fin: [''],
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = { page: '1', size: '100' };
    if (f.date_debut) {
      params['date_debut'] = f.date_debut;
    }
    if (f.date_fin) {
      params['date_fin'] = f.date_fin;
    }
    this.api.get<Paginated<EcritureRow>>('/ecritures', params).subscribe((res) => {
      this.rows.set(res.items);
      this.total.set(res.total);
    });
  }

  export(format: 'xlsx' | 'pdf'): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = { format };
    if (f.date_debut) {
      params['date_debut'] = f.date_debut;
    }
    if (f.date_fin) {
      params['date_fin'] = f.date_fin;
    }
    this.api.download('/reporting/ecritures/export', params).subscribe((blob) => {
      const ext = format === 'pdf' ? 'pdf' : 'xlsx';
      this.saveBlob(blob, `ecritures-el-amana.${ext}`);
    });
  }

  private saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}
