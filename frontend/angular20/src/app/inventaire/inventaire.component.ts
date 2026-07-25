import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

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
  imports: [ReactiveFormsModule, RouterLink, DatePipe, MatButtonModule, MatIconModule, MatTableModule],
  templateUrl: './inventaire.component.html',
  styleUrl: './inventaire.component.css',
})
export class InventaireComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly scans = signal<InventaireScanRow[]>([]);
  readonly scanning = signal(false);
  readonly loading = signal(false);
  readonly displayedColumns = ['created_at', 'code_scanne', 'valide', 'designation', 'localisation'];

  readonly scanForm = this.fb.nonNullable.group({
    code_scanne: ['', Validators.required],
    localisation: [''],
  });

  ngOnInit(): void {
    this.loadScans();
  }

  loadScans(): void {
    this.loading.set(true);
    this.api.get<Paginated<InventaireScanRow>>('/inventaire/scans', { page: 1, size: 50 }).subscribe({
      next: (res) => {
        this.scans.set(res.items);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  submitScan(): void {
    if (this.scanForm.invalid) {
      this.scanForm.markAllAsTouched();
      void this.dialogs.error('Code inventaire requis', 'Validation').subscribe();
      return;
    }
    const raw = this.scanForm.getRawValue();
    this.dialogs
      .confirmAction('enregistrement', `Enregistrer le scan « ${raw.code_scanne.trim()} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
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
                void this.dialogs
                  .successAction(
                    'validation',
                    `Actif trouvé : ${row.designation ?? row.code_inventaire}`,
                  )
                  .subscribe();
              } else {
                void this.dialogs
                  .error('Code inconnu — scan enregistré comme non conforme', 'Validation')
                  .subscribe();
              }
            },
            error: (err) => {
              this.scanning.set(false);
              const msg = err.error?.detail ?? 'Scan impossible';
              void this.dialogs.error(typeof msg === 'string' ? msg : 'Erreur').subscribe();
            },
          });
      });
  }
}
