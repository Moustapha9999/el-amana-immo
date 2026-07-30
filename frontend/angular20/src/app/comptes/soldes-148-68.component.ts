import { DatePipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import {
  sortCategoriesNatureImmo,
} from '../immobilisations/immobilisation.constants';
import { MontantPipe } from '../shared/montant.pipe';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface SoldeNatureLigne {
  nature_code: string;
  nature: string;
  compte_immobilisation: string;
  compte_amortissement: string | null;
  libelle_amortissement: string | null;
  solde_148: number;
  solde_148_n1: number;
  compte_dotation: string | null;
  libelle_dotation: string | null;
  solde_68: number;
  valeur_brute: number;
  vnc: number;
  nb_biens: number;
}

interface DetailLigne {
  immobilisation_id: string;
  date: string | null;
  reference: string;
  designation: string;
  categorie: string | null;
  valeur_brute: number;
  dotation: number;
  amortissement_cumule: number;
  amortissement_cumule_n1: number;
  vnc: number;
  agence_code: string | null;
  agence_libelle: string | null;
  exercice: number;
  compte_immobilisation: string | null;
  compte_amortissement: string | null;
  compte_dotation: string | null;
}

interface Soldes14868Response {
  famille_compte: string;
  compte_numero: string;
  compte_intitule: string;
  annee: number;
  date_arrete: string;
  date_debut: string | null;
  date_fin: string | null;
  periode_label: string;
  solde_total: number;
  nb_immobilisations: number;
  nb_mouvements: number;
  total_valeur_brute: number;
  total_dotation: number;
  total_amortissement_cumule: number;
  total_amortissement_cumule_n1: number;
  total_vnc: number;
  lignes: SoldeNatureLigne[];
  detail: DetailLigne[];
  exercices_disponibles: number[];
  total_148: number;
  total_148_n1: number;
  total_68: number;
  nb_biens: number;
}

interface AgenceOption {
  id: string;
  code: string;
  libelle: string;
}

interface CategorieOption {
  id: string;
  code: string;
  famille: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

type FamilleCompte = '142' | '148' | '68';

@Component({
  selector: 'app-soldes-148-68',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    MontantPipe,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
    PaginationComponent,
  ],
  templateUrl: './soldes-148-68.component.html',
  styleUrl: './soldes-148-68.component.css',
})
export class Soldes14868Component implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<Soldes14868Response | null>(null);
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  readonly agences = signal<AgenceOption[]>([]);
  readonly categories = signal<CategorieOption[]>([]);
  readonly page = signal(1);
  readonly pageSize = 50;
  readonly viewMode = signal<'detail' | 'synthese'>('detail');

  readonly familleOptions: { value: FamilleCompte; label: string; hint: string }[] = [
    { value: '142', label: '142 — Immobilisations', hint: 'Valeur brute' },
    { value: '148', label: '148 — Amortissements cumulés', hint: 'Cumul amort.' },
    { value: '68', label: '68 — Dotations', hint: 'Dotations exercice' },
  ];

  readonly filterForm = this.fb.nonNullable.group({
    famille_compte: ['148' as FamilleCompte],
    annee: [new Date().getFullYear()],
    agence_id: [''],
    categorie_id: [''],
    date_debut: [''],
    date_fin: [''],
    search: [''],
  });

  readonly natureColumns = [
    'nature',
    'compte_immo',
    'compte_148',
    'vb',
    'solde_148_n1',
    'solde_68',
    'solde_148',
    'compte_68',
    'vnc',
    'nb',
  ];

  readonly detailColumns = computed(() => {
    const famille = this.data()?.famille_compte ?? this.filterForm.controls.famille_compte.value;
    const base = ['date', 'reference', 'designation', 'categorie', 'vb'];
    if (famille === '68') {
      return [...base, 'dotation', 'vnc', 'agence', 'exercice'];
    }
    if (famille === '148') {
      return [...base, 'amt', 'vnc', 'agence', 'exercice'];
    }
    return [...base, 'amt', 'dotation', 'vnc', 'agence', 'exercice'];
  });

  readonly pagedDetail = computed(() => {
    const rows = this.data()?.detail ?? [];
    const start = (this.page() - 1) * this.pageSize;
    return rows.slice(start, start + this.pageSize);
  });

  readonly soldeLabel = computed(() => {
    const f = this.data()?.famille_compte ?? this.filterForm.controls.famille_compte.value;
    if (f === '142') return 'Solde total (valeur brute)';
    if (f === '68') return 'Solde total (dotations)';
    return 'Solde total (amort. cumulés)';
  });

  readonly exercices = computed(() => {
    const fromApi = this.data()?.exercices_disponibles ?? [];
    const current = Number(this.filterForm.controls.annee.value) || new Date().getFullYear();
    const set = new Set<number>([...fromApi, current, new Date().getFullYear()]);
    return Array.from(set).sort((a, b) => b - a);
  });

  ngOnInit(): void {
    this.loadLookups();
    this.load();
  }

  loadLookups(): void {
    this.api.get<Paginated<AgenceOption>>('/agences', { page: 1, size: 100 }).subscribe({
      next: (res) => this.agences.set(res.items ?? []),
      error: () => this.agences.set([]),
    });
    this.api.get<Paginated<CategorieOption>>('/categories', { page: 1, size: 100 }).subscribe({
      next: (res) => {
        const items = res.items ?? [];
        const official = sortCategoriesNatureImmo(items);
        const officialIds = new Set(official.map((c) => c.id));
        const rest = items.filter((c) => !officialIds.has(c.id));
        this.categories.set([...official, ...rest]);
      },
      error: () => this.categories.set([]),
    });
  }

  private filterParams(): Record<string, string> {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = {
      annee: String(f.annee),
      famille_compte: f.famille_compte,
    };
    if (f.agence_id) params['agence_id'] = f.agence_id;
    if (f.categorie_id) params['categorie_id'] = f.categorie_id;
    if (f.date_debut) params['date_debut'] = f.date_debut;
    if (f.date_fin) params['date_fin'] = f.date_fin;
    if (f.search.trim()) params['search'] = f.search.trim();
    return params;
  }

  load(): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee || annee < 2000 || annee > 2100) {
      void this.dialogs.error('Exercice invalide').subscribe();
      return;
    }
    this.loading.set(true);
    this.api.get<Soldes14868Response>('/reporting/soldes-148-68', this.filterParams()).subscribe({
      next: (res) => {
        this.data.set(res);
        this.page.set(1);
        this.loading.set(false);
      },
      error: (err: { error?: { detail?: unknown } }) => {
        this.loading.set(false);
        const detail = err.error?.detail;
        void this.dialogs
          .error(typeof detail === 'string' ? detail : 'Impossible de charger la consultation')
          .subscribe();
      },
    });
  }

  resetFilters(): void {
    this.filterForm.reset({
      famille_compte: '148',
      annee: new Date().getFullYear(),
      agence_id: '',
      categorie_id: '',
      date_debut: '',
      date_fin: '',
      search: '',
    });
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
  }

  setView(mode: 'detail' | 'synthese'): void {
    this.viewMode.set(mode);
  }

  export(format: 'xlsx' | 'pdf'): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee || annee < 2000 || annee > 2100) {
      void this.dialogs.error('Exercice invalide').subscribe();
      return;
    }
    const famille = this.filterForm.controls.famille_compte.value;
    const params = {
      ...this.filterParams(),
      format,
      vue: this.viewMode(),
    };
    this.exporting.set(format);
    this.api.download('/reporting/soldes-148-68/export', params).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `soldes-${famille}-${annee}.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      error: () => {
        this.exporting.set(null);
        void this.dialogs.error('Export impossible').subscribe();
      },
    });
  }

  categorieLabel(cat: CategorieOption): string {
    return `${cat.famille}${cat.code ? ` (${cat.code})` : ''}`;
  }
}
