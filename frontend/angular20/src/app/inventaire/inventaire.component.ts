import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';

interface InventaireScanRow {
  id: string;
  code_scanne: string;
  valide: boolean;
  localisation: string | null;
  created_at: string;
  code_inventaire: string | null;
  designation: string | null;
  immobilisation_id: string | null;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-inventaire',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSnackBarModule,
    MatTableModule,
  ],
  templateUrl: './inventaire.component.html',
})
export class InventaireComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly snack = inject(MatSnackBar);

  readonly scans = signal<InventaireScanRow[]>([]);
  readonly scanning = signal(false);
  readonly displayedColumns = ['created_at', 'code_scanne', 'valide', 'designation', 'localisation'];

  readonly scanForm = this.fb.nonNullable.group({
    code_scanne: ['', Validators.required],
    localisation: [''],
  });

  ngOnInit(): void {
    this.loadScans();
  }

  loadScans(): void {
    this.api.get<Paginated<InventaireScanRow>>('/inventaire/scans', { page: 1, size: 50 }).subscribe((res) => {
      this.scans.set(res.items);
    });
  }

  submitScan(): void {
    if (this.scanForm.invalid) {
      this.scanForm.markAllAsTouched();
      return;
    }
    const raw = this.scanForm.getRawValue();
    this.scanning.set(true);
    this.api
      .post<InventaireScanRow>('/inventaire/scans', {
        code_scanne: raw.code_scanne.trim(),
        localisation: raw.localisation.trim() || null,
      })
      .subscribe({
        next: (row) => {
          this.scanning.set(false);
          this.scanForm.patchValue({ code_scanne: '', localisation: raw.localisation });
          this.loadScans();
          if (row.valide) {
            this.snack.open(`Actif trouvé : ${row.designation ?? row.code_inventaire}`, 'Fermer', {
              duration: 4000,
            });
          } else {
            this.snack.open('Code inconnu — scan enregistré comme non conforme', 'Fermer', { duration: 4000 });
          }
        },
        error: (err) => {
          this.scanning.set(false);
          const msg = err.error?.detail ?? 'Scan impossible';
          this.snack.open(typeof msg === 'string' ? msg : 'Erreur', 'Fermer', { duration: 5000 });
        },
      });
  }
}
