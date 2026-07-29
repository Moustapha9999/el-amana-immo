import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { sortCategoriesNatureImmo } from '../immobilisations/immobilisation.constants';
import {
  formatPeriodeAmortissement,
  formatTauxPercent,
} from '../shared/amortissement-rate.util';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

type Periodicite = 'mensuel' | 'trimestriel' | 'annuel';

interface Categorie {
  id: string;
  code: string;
  libelle: string;
  famille: string;
  amortissable: boolean;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

interface CalculLigne {
  immobilisation_id: string;
  code_inventaire: string;
  designation: string;
  statut: string;
  vnc_avant: string | number;
  dotation: string | number;
  vnc_apres: string | number;
  cumul_avant: string | number;
  cumul_apres: string | number;
  valeur_brute: string | number;
  nature: string | null;
  compte_dotation: string | null;
  compte_amortissement: string | null;
  taux: string | number | null;
  message: string | null;
}

interface PeriodeComptable {
  id: string;
  annee: number;
  trimestre: number;
  code: string;
  date_arrete: string;
  statut: 'en_attente' | 'ouverte' | 'calculee' | 'validee' | 'cloturee';
  total_dotation: string | number;
  nb_dotations: number;
}

interface CalculResponse {
  periodicite: string;
  annee: number;
  periode_index: number;
  periode: string;
  date_debut: string;
  date_arrete: string;
  date_ecriture: string;
  mode: string;
  periode_statut: string | null;
  nb_calcules: number;
  nb_ignores_vnc: number;
  nb_deja_comptabilises: number;
  nb_erreurs: number;
  total_dotations: string | number;
  lignes: CalculLigne[];
  ignores: CalculLigne[];
  deja_comptabilises: CalculLigne[];
  erreurs: CalculLigne[];
}

const MONTH_OPTIONS = [
  { value: 1, label: 'Janvier' },
  { value: 2, label: 'Février' },
  { value: 3, label: 'Mars' },
  { value: 4, label: 'Avril' },
  { value: 5, label: 'Mai' },
  { value: 6, label: 'Juin' },
  { value: 7, label: 'Juillet' },
  { value: 8, label: 'Août' },
  { value: 9, label: 'Septembre' },
  { value: 10, label: 'Octobre' },
  { value: 11, label: 'Novembre' },
  { value: 12, label: 'Décembre' },
];

const QUARTER_OPTIONS = [
  { value: 1, label: 'T1 — 31/03' },
  { value: 2, label: 'T2 — 30/06' },
  { value: 3, label: 'T3 — 30/09' },
  { value: 4, label: 'T4 — 31/12' },
];

function lastDayOfMonth(year: number, month: number): string {
  const d = new Date(year, month, 0);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function defaultDateEcriture(periodicite: Periodicite, annee: number, index: number): string {
  if (periodicite === 'mensuel') {
    return lastDayOfMonth(annee, index);
  }
  if (periodicite === 'trimestriel') {
    const endMonth = index * 3;
    return lastDayOfMonth(annee, endMonth);
  }
  return `${annee}-12-31`;
}

@Component({
  selector: 'app-calcul-amortissements',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MontantPipe,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
    PaginationComponent,
  ],
  templateUrl: './calcul-amortissements.component.html',
  styleUrl: './calcul-amortissements.component.css',
})
export class CalculAmortissementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly categories = signal<Categorie[]>([]);
  readonly periodes = signal<PeriodeComptable[]>([]);
  readonly loading = signal(false);
  readonly result = signal<CalculResponse | null>(null);
  readonly periodicite = signal<Periodicite>('trimestriel');
  readonly periodeIndex = signal(Math.ceil((new Date().getMonth() + 1) / 3));
  readonly page = signal(1);
  readonly pageSize = 50;
  readonly listFilter = signal({ search: '', statut: '' });
  readonly formatPeriode = formatPeriodeAmortissement;
  readonly formatTaux = formatTauxPercent;

  readonly form = this.fb.nonNullable.group({
    periodicite: ['trimestriel' as Periodicite],
    annee: [new Date().getFullYear()],
    periode_index: [Math.ceil((new Date().getMonth() + 1) / 3)],
    date_ecriture: [
      defaultDateEcriture(
        'trimestriel',
        new Date().getFullYear(),
        Math.ceil((new Date().getMonth() + 1) / 3),
      ),
    ],
    categorie_ids: [[] as string[]],
  });

  readonly filterForm = this.fb.nonNullable.group({
    search: [''],
    statut: [''],
  });

  readonly canValiderPeriode = computed(() => {
    if (this.periodicite() !== 'trimestriel') {
      return false;
    }
    const index = this.periodeIndex();
    const current = this.periodes().find((p) => p.trimestre === index);
    if (!current || current.statut === 'validee' || current.statut === 'cloturee') {
      return false;
    }
    if (index === 1) {
      return true;
    }
    const previous = this.periodes().find((p) => p.trimestre === index - 1);
    return previous?.statut === 'validee' || previous?.statut === 'cloturee';
  });

  readonly periodOptions = computed(() => {
    const p = this.periodicite();
    if (p === 'mensuel') {
      return MONTH_OPTIONS;
    }
    if (p === 'trimestriel') {
      return QUARTER_OPTIONS;
    }
    return [{ value: 1, label: 'Exercice (31/12)' }];
  });

  readonly columns = [
    'code',
    'designation',
    'nature',
    'vb',
    'taux',
    'cumul_avant',
    'vnc_avant',
    'dotation',
    'cumul_apres',
    'vnc_apres',
    'compte_68',
    'compte_148',
    'statut',
  ];

  readonly statutOptions = [
    { value: '', label: 'Tous les statuts' },
    { value: 'calcule', label: 'Calculé' },
    { value: 'ignore_vnc', label: 'Ignoré (VNC = 0)' },
    { value: 'deja_comptabilise', label: 'Déjà comptabilisé' },
    { value: 'erreur', label: 'Erreur' },
  ];

  readonly allRows = computed(() => {
    const r = this.result();
    if (!r) {
      return [] as CalculLigne[];
    }
    return [...r.lignes, ...r.ignores, ...r.deja_comptabilises, ...r.erreurs];
  });

  readonly filteredRows = computed(() => {
    const f = this.listFilter();
    const q = f.search.trim().toLowerCase();
    return this.allRows().filter((row) => {
      if (f.statut && row.statut !== f.statut) {
        return false;
      }
      if (!q) {
        return true;
      }
      const hay = [
        row.code_inventaire,
        row.designation,
        row.nature ?? '',
        row.compte_dotation ?? '',
        row.compte_amortissement ?? '',
        row.message ?? '',
        this.statutLabel(row.statut),
      ]
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  });

  readonly pagedRows = computed(() => {
    const start = (this.page() - 1) * this.pageSize;
    return this.filteredRows().slice(start, start + this.pageSize);
  });

  ngOnInit(): void {
    this.loadPeriodes();
    this.api.get<Paginated<Categorie>>('/categories', { page: 1, size: 100 }).subscribe({
      next: (res) => {
        const amort = (res.items ?? []).filter((c) => c.amortissable);
        const sorted = sortCategoriesNatureImmo(amort);
        this.categories.set(sorted);
        this.form.controls.categorie_ids.setValue(sorted.map((c) => c.id));
      },
      error: () => this.categories.set([]),
    });

    this.form.controls.periodicite.valueChanges.subscribe((p) => {
      this.periodicite.set(p);
      let index = 1;
      if (p === 'mensuel') {
        index = new Date().getMonth() + 1;
      } else if (p === 'trimestriel') {
        index = Math.ceil((new Date().getMonth() + 1) / 3);
      }
      this.form.controls.periode_index.setValue(index);
      this.syncDateEcriture();
      this.result.set(null);
    });

    this.form.controls.annee.valueChanges.subscribe(() => {
      this.syncDateEcriture();
      this.loadPeriodes();
    });
    this.form.controls.periode_index.valueChanges.subscribe((index) => {
      this.periodeIndex.set(Number(index));
      this.syncDateEcriture();
    });
  }

  private loadPeriodes(): void {
    const annee = Number(this.form.controls.annee.value);
    if (!annee) {
      this.periodes.set([]);
      return;
    }
    this.api.get<PeriodeComptable[]>(`/exercices/${annee}/periodes`).subscribe({
      next: (rows) => this.periodes.set(rows),
      error: () => this.periodes.set([]),
    });
  }

  periodeStatutLabel(statut: PeriodeComptable['statut']): string {
    const labels: Record<PeriodeComptable['statut'], string> = {
      en_attente: 'En attente',
      ouverte: 'Ouverte',
      calculee: 'Calculée',
      validee: 'Validée',
      cloturee: 'Clôturée',
    };
    return labels[statut];
  }

  private syncDateEcriture(): void {
    const f = this.form.getRawValue();
    const annee = Number(f.annee);
    const index = Number(f.periode_index);
    if (!annee || !index) {
      return;
    }
    this.form.controls.date_ecriture.setValue(
      defaultDateEcriture(f.periodicite, annee, index),
      { emitEvent: false },
    );
  }

  applyListFilter(): void {
    this.listFilter.set(this.filterForm.getRawValue());
    this.page.set(1);
  }

  resetListFilter(): void {
    this.filterForm.reset({ search: '', statut: '' });
    this.listFilter.set({ search: '', statut: '' });
    this.page.set(1);
  }

  goToPage(page: number): void {
    this.page.set(page);
  }

  simuler(): void {
    this.run('simulation');
  }

  valider(): void {
    const r = this.result();
    if (!r) {
      void this.dialogs.error('Commencez par lancer une simulation.').subscribe();
      return;
    }
    if (!this.canValiderPeriode()) {
      void this.dialogs
        .error('Cette période ne peut pas encore être comptabilisée. Validez la période précédente.')
        .subscribe();
      return;
    }
    const dateEcr = this.form.controls.date_ecriture.value;
    const action =
      r.nb_calcules > 0
        ? `Comptabiliser ${r.nb_calcules} dotation(s)`
        : 'Valider la période sans dotation';
    this.dialogs
      .confirmAction(
        'comptabilisation',
        `${action} pour ${formatPeriodeAmortissement(r.periode)} ` +
          `au ${dateEcr} (total ${r.total_dotations}) ? Les écritures 681 → 148 seront générées.`,
      )
      .subscribe((ok) => {
        if (ok) {
          this.run('validation');
        }
      });
  }

  private run(mode: 'simulation' | 'validation'): void {
    const f = this.form.getRawValue();
    const annee = Number(f.annee);
    if (!annee || annee < 2000 || annee > 2100) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    if (!f.date_ecriture) {
      void this.dialogs.error('Date d’écriture obligatoire').subscribe();
      return;
    }
    const body = {
      periodicite: f.periodicite,
      annee,
      periode_index: Number(f.periode_index),
      mode,
      date_ecriture: f.date_ecriture,
      categorie_ids:
        f.categorie_ids.length === 0 || f.categorie_ids.length === this.categories().length
          ? null
          : f.categorie_ids,
    };
    this.loading.set(true);
    this.api.post<CalculResponse>('/amortissements/calculer', body).subscribe({
      next: (res) => {
        this.result.set(res);
        this.page.set(1);
        this.loading.set(false);
        if (mode === 'validation') {
          this.loadPeriodes();
          const statutMessage = res.periode_statut === 'validee'
            ? ' La période est validée ; la suivante est maintenant ouverte.'
            : ' La période reste calculée tant que toutes les catégories ne sont pas comptabilisées.';
          void this.dialogs
            .successAction(
              'comptabilisation',
              `${res.nb_calcules} dotation(s) comptabilisée(s) — total ${res.total_dotations}.${statutMessage}`,
            )
            .subscribe();
        }
      },
      error: (err: { error?: { detail?: unknown } }) => {
        this.loading.set(false);
        const detail = err.error?.detail;
        void this.dialogs
          .error(typeof detail === 'string' ? detail : 'Calcul impossible')
          .subscribe();
      },
    });
  }

  statutLabel(statut: string): string {
    switch (statut) {
      case 'calcule':
        return 'Calculé';
      case 'ignore_vnc':
        return 'Ignoré (VNC = 0)';
      case 'deja_comptabilise':
        return 'Déjà comptabilisé';
      case 'erreur':
        return 'Erreur';
      default:
        return statut;
    }
  }

  onCategorieToggle(id: string, checked: boolean): void {
    const ctrl = this.form.controls.categorie_ids;
    const current = [...ctrl.value];
    if (checked) {
      if (!current.includes(id)) {
        ctrl.setValue([...current, id]);
      }
    } else {
      ctrl.setValue(current.filter((x) => x !== id));
    }
  }

  isCategorieSelected(id: string): boolean {
    return this.form.controls.categorie_ids.value.includes(id);
  }

  selectAllCategories(): void {
    this.form.controls.categorie_ids.setValue(this.categories().map((c) => c.id));
  }

  clearCategories(): void {
    this.form.controls.categorie_ids.setValue([]);
  }
}
