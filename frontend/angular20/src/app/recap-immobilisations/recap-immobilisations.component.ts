import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface RecapImmoLigne {
  compte: string;
  intitule: string;
  valeurs_ouverture: number;
  acquisitions: number;
  cessions: number;
  valeurs_cloture: number;
}

interface RecapImmoResponse {
  annee: number;
  annee_ouverture: number;
  date_ouverture: string;
  date_cloture: string;
  lignes: RecapImmoLigne[];
  totaux: RecapImmoLigne;
}

@Component({
  selector: 'app-recap-immobilisations',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MontantPipe,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
  ],
  templateUrl: './recap-immobilisations.component.html',
  styleUrl: './recap-immobilisations.component.css',
})
export class RecapImmobilisationsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<RecapImmoResponse | null>(null);
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  readonly localSearch = signal('');

  readonly filterForm = this.fb.nonNullable.group({
    annee: [new Date().getFullYear()],
    search: [''],
  });

  readonly columns = [
    'compte',
    'intitule',
    'ouverture',
    'acquisitions',
    'cessions',
    'cloture',
  ];

  readonly lignesFiltrees = computed(() => {
    const d = this.data();
    if (!d) {
      return [];
    }
    const q = this.localSearch().trim().toLowerCase();
    if (!q) {
      return d.lignes;
    }
    return d.lignes.filter(
      (l) =>
        l.compte.toLowerCase().includes(q) ||
        l.intitule.toLowerCase().includes(q) ||
        String(l.valeurs_ouverture).includes(q) ||
        String(l.acquisitions).includes(q) ||
        String(l.cessions).includes(q) ||
        String(l.valeurs_cloture).includes(q),
    );
  });

  ngOnInit(): void {
    this.filterForm.controls.search.valueChanges.subscribe((v) => this.localSearch.set(v));
    this.load();
  }

  applyLocalFilters(): void {
    this.localSearch.set(this.filterForm.controls.search.value);
  }

  resetFilters(): void {
    const annee = this.filterForm.controls.annee.value;
    this.filterForm.reset({ annee, search: '' });
    this.applyLocalFilters();
  }

  load(): void {
    const annee = this.filterForm.controls.annee.value;
    this.loading.set(true);
    this.api.get<RecapImmoResponse>('/reporting/recap-immobilisations', { annee }).subscribe({
      next: (res) => {
        this.data.set(res);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        const msg = err.error?.detail ?? 'Impossible de charger le tableau récapitulatif.';
        void this.dialogs.error(typeof msg === 'string' ? msg : 'Erreur').subscribe();
      },
    });
  }

  export(format: 'xlsx' | 'pdf'): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee) {
      return;
    }
    this.exporting.set(format);
    this.api
      .download('/reporting/recap-immobilisations/export', {
        annee: String(annee),
        format,
      })
      .subscribe({
        next: (blob) => {
          this.exporting.set(null);
          const ext = format === 'pdf' ? 'pdf' : 'xlsx';
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `recap-immobilisations-${annee}.${ext}`;
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
