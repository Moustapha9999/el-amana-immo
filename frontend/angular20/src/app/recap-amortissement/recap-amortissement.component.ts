import { MontantPipe } from '../shared/montant.pipe';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface RecapLigne {
  compte_immobilisation: string;
  intitule: string;
  valeur_brute: number;
  compte_amortissement: string | null;
  amorts_cumules_n1: number;
  cessions_annee: number;
  dotations_annee: number;
  amorts_cumules_n: number;
  vnc: number;
}

interface RecapDetail {
  immobilisation_id: string;
  code_inventaire: string;
  designation: string;
  compte_immobilisation: string;
  valeur_brute: number;
  amorts_cumules_n1: number;
  cessions_annee: number;
  dotations_annee: number;
  amorts_cumules_n: number;
  vnc: number;
}

interface RecapResponse {
  annee: number;
  date_arrete: string;
  lignes: RecapLigne[];
  details: RecapDetail[];
  totaux: RecapLigne;
}

@Component({
  selector: 'app-recap-amortissement',
  imports: [ReactiveFormsModule, MontantPipe, MatButtonModule, MatIconModule, MatTableModule],
  templateUrl: './recap-amortissement.component.html',
  styleUrl: './recap-amortissement.component.css',
})
export class RecapAmortissementComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<RecapResponse | null>(null);
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | 'detail-xlsx' | 'detail-pdf' | null>(null);

  readonly columns = [
    'compte',
    'intitule',
    'vb',
    'compte_amort',
    'cumul_n1',
    'cessions',
    'dotations',
    'cumul_n',
    'vnc',
  ];

  readonly detailColumns = ['code', 'designation', 'compte', 'dotations', 'cumul_n', 'vnc'];

  readonly filterForm = this.fb.nonNullable.group({
    annee: [new Date().getFullYear()],
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee || annee < 2000 || annee > 2100) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    this.loading.set(true);
    this.api.get<RecapResponse>('/reporting/recap-amortissement', { annee }).subscribe({
      next: (res) => {
        this.data.set(res);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        void this.dialogs
          .error(err.error?.detail ?? 'Impossible de charger le récapitulatif')
          .subscribe();
      },
    });
  }

  export(format: 'xlsx' | 'pdf', vue: 'synthese' | 'detail' = 'synthese'): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee) {
      return;
    }
    const busyKey = vue === 'detail' ? (`detail-${format}` as const) : format;
    this.exporting.set(busyKey);
    this.api
      .download('/reporting/recap-amortissement/export', {
        annee: String(annee),
        format,
        vue,
      })
      .subscribe({
        next: (blob) => {
          this.exporting.set(null);
          const ext = format === 'pdf' ? 'pdf' : 'xlsx';
          const prefix =
            vue === 'detail' ? 'detail-dotations-amortissement' : 'recap-amortissement';
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `${prefix}-${annee}.${ext}`;
          a.click();
          URL.revokeObjectURL(a.href);
        },
        error: () => {
          this.exporting.set(null);
          void this.dialogs.error('Export impossible').subscribe();
        },
      });
  }
}
