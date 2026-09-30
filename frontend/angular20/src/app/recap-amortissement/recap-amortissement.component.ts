import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { PaginationComponent } from '../shared/pagination.component';
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

function matchesText(haystack: unknown, needle: string): boolean {
  if (needle === '') {
    return true;
  }
  return String(haystack ?? '')
    .toLowerCase()
    .includes(needle);
}

@Component({
  selector: 'app-recap-amortissement',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MontantPipe,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
    PaginationComponent,
  ],
  templateUrl: './recap-amortissement.component.html',
  styleUrl: './recap-amortissement.component.css',
})
export class RecapAmortissementComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<RecapResponse | null>(null);
  readonly loading = signal(false);
  readonly detailPage = signal(1);
  readonly detailPageSize = 50;
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  private lastAnnee: number | null = null;

  /** Filtres locaux appliqués sur les données déjà chargées. */
  readonly localSearch = signal('');
  readonly localCompte = signal('');

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
    search: [''],
    compte: [''],
  });

  readonly compteOptions = computed(() => {
    const lignes = this.data()?.lignes ?? [];
    return lignes.map((l) => ({
      value: l.compte_immobilisation,
      label: `${l.compte_immobilisation} — ${l.intitule}`,
    }));
  });

  readonly filteredLignes = computed(() => {
    const lignes = this.data()?.lignes ?? [];
    const q = this.localSearch().trim().toLowerCase();
    const compte = this.localCompte().trim();
    return lignes.filter((row) => {
      if (compte && row.compte_immobilisation !== compte) {
        return false;
      }
      if (!q) {
        return true;
      }
      return (
        matchesText(row.compte_immobilisation, q) ||
        matchesText(row.intitule, q) ||
        matchesText(row.compte_amortissement, q) ||
        matchesText(row.valeur_brute, q) ||
        matchesText(row.amorts_cumules_n1, q) ||
        matchesText(row.cessions_annee, q) ||
        matchesText(row.dotations_annee, q) ||
        matchesText(row.amorts_cumules_n, q) ||
        matchesText(row.vnc, q)
      );
    });
  });

  readonly filteredTotaux = computed<RecapLigne | null>(() => {
    const d = this.data();
    if (!d || (!this.localSearch().trim() && !this.localCompte().trim())) {
      return d?.totaux ?? null;
    }
    const lignes = this.filteredLignes();
    const sum = (pick: (l: RecapLigne) => number) =>
      lignes.reduce((acc, l) => acc + (Number(pick(l)) || 0), 0);
    return {
      ...d.totaux,
      valeur_brute: sum((l) => l.valeur_brute),
      amorts_cumules_n1: sum((l) => l.amorts_cumules_n1),
      cessions_annee: sum((l) => l.cessions_annee),
      dotations_annee: sum((l) => l.dotations_annee),
      amorts_cumules_n: sum((l) => l.amorts_cumules_n),
      vnc: sum((l) => l.vnc),
    };
  });

  readonly filteredDetails = computed(() => {
    const details = this.data()?.details ?? [];
    const q = this.localSearch().trim().toLowerCase();
    const compte = this.localCompte().trim();
    return details.filter((row) => {
      if (compte && row.compte_immobilisation !== compte) {
        return false;
      }
      if (!q) {
        return true;
      }
      return (
        matchesText(row.code_inventaire, q) ||
        matchesText(row.designation, q) ||
        matchesText(row.compte_immobilisation, q) ||
        matchesText(row.valeur_brute, q) ||
        matchesText(row.dotations_annee, q) ||
        matchesText(row.amorts_cumules_n, q) ||
        matchesText(row.vnc, q)
      );
    });
  });

  readonly pagedDetails = computed<RecapDetail[]>(() => {
    const details = this.filteredDetails();
    const start = (this.detailPage() - 1) * this.detailPageSize;
    return details.slice(start, start + this.detailPageSize);
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
        this.lastAnnee = annee;
        this.data.set(res);
        this.detailPage.set(1);
        this.applyLocalFilters();
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

  applyLocalFilters(): void {
    const f = this.filterForm.getRawValue();
    this.localSearch.set(f.search);
    this.localCompte.set(f.compte);
    this.detailPage.set(1);
  }

  resetFilters(): void {
    const annee = this.filterForm.controls.annee.value;
    this.filterForm.reset({ annee, search: '', compte: '' });
    this.applyLocalFilters();
  }

  export(format: 'xlsx' | 'pdf'): void {
    const annee = this.lastAnnee;
    if (!annee) {
      return;
    }
    const params: Record<string, string> = { annee: String(annee), format, vue: 'synthese' };
    const search = this.localSearch().trim();
    if (search) {
      params['search'] = search;
    }
    const compte = this.localCompte().trim();
    if (compte) {
      params['compte'] = compte;
    }
    this.exporting.set(format);
    this.api
      .download('/reporting/recap-amortissement/export', params)
      .subscribe({
        next: (blob) => {
          this.exporting.set(null);
          const ext = format === 'pdf' ? 'pdf' : 'xlsx';
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `recap-amortissement-${annee}.${ext}`;
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
