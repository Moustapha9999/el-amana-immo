import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface AgenceOption {
  id: string;
  code: string;
  libelle: string;
}

interface CategorieOption {
  id: string;
  code: string;
  famille?: string;
  sous_famille?: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

interface VentilationLigne {
  immobilisation_id: string;
  code_inventaire: string;
  designation: string;
  date_acquisition: string | null;
  valeur_brute: number;
  taux: number | null;
  amortissement_cumule: number;
  dotation_periode: number;
  vnc: number;
  agence_id: string | null;
  agence_code: string | null;
  agence_libelle: string;
}

interface VentilationGroupe {
  agence_id: string | null;
  agence_code: string | null;
  agence_libelle: string;
  total_dotations: number;
  nb_immobilisations: number;
  lignes: VentilationLigne[];
}

interface VentilationResponse {
  annee: number;
  periodicite: string;
  periode_index: number | null;
  periode_label: string;
  date_arrete: string;
  agence_filtre_id: string | null;
  categorie_filtre_id: string | null;
  total_compte_68: number;
  nb_immobilisations: number;
  total_dotations: number;
  groupes: VentilationGroupe[];
  exercices_disponibles: number[];
}

@Component({
  selector: 'app-amortissements-agence',
  imports: [FormsModule, ReactiveFormsModule, MontantPipe, MatButtonModule, MatIconModule],
  templateUrl: './amortissements-agence.component.html',
  styleUrl: './amortissements-agence.component.css',
})
export class AmortissementsAgenceComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<VentilationResponse | null>(null);
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  readonly agences = signal<AgenceOption[]>([]);
  readonly categories = signal<CategorieOption[]>([]);
  readonly exercices = signal<number[]>([new Date().getFullYear()]);

  readonly trimestres = [
    { value: 1, label: 'T1 — 31/03' },
    { value: 2, label: 'T2 — 30/06' },
    { value: 3, label: 'T3 — 30/09' },
    { value: 4, label: 'T4 — 31/12' },
  ];

  readonly mois = Array.from({ length: 12 }, (_, i) => ({
    value: i + 1,
    label: new Date(2026, i, 1).toLocaleString('fr-FR', { month: 'long' }),
  }));

  readonly filterForm = this.fb.nonNullable.group({
    agence_id: [''],
    annee: [new Date().getFullYear()],
    periodicite: ['trimestriel' as 'mensuel' | 'trimestriel' | 'annuel'],
    periode_index: [2],
    categorie_id: [''],
  });

  readonly vueGlobale = computed(() => !this.data()?.agence_filtre_id);

  readonly flatLignes = computed(() => {
    const groupes = this.data()?.groupes ?? [];
    return groupes.flatMap((g) => g.lignes);
  });

  readonly totauxGlobaux = computed(() => this.sumLignes(this.flatLignes()));

  sumLignes(lignes: VentilationLigne[]): {
    nb: number;
    valeur_brute: number;
    amortissement_cumule: number;
    dotation_periode: number;
    vnc: number;
  } {
    return lignes.reduce(
      (acc, row) => {
        acc.nb += 1;
        acc.valeur_brute += Number(row.valeur_brute) || 0;
        acc.amortissement_cumule += Number(row.amortissement_cumule) || 0;
        acc.dotation_periode += Number(row.dotation_periode) || 0;
        acc.vnc += Number(row.vnc) || 0;
        return acc;
      },
      {
        nb: 0,
        valeur_brute: 0,
        amortissement_cumule: 0,
        dotation_periode: 0,
        vnc: 0,
      },
    );
  }

  ngOnInit(): void {
    this.loadReferentiels();
    this.load();
  }

  loadReferentiels(): void {
    this.api.get<Paginated<AgenceOption>>('/agences', { page: 1, size: 100 }).subscribe({
      next: (res) => this.agences.set(res.items ?? []),
      error: () => this.agences.set([]),
    });
    this.api.get<Paginated<CategorieOption>>('/categories', { page: 1, size: 100 }).subscribe({
      next: (res) => this.categories.set(res.items ?? []),
      error: () => this.categories.set([]),
    });
  }

  onPeriodiciteChange(): void {
    const p = this.filterForm.controls.periodicite.value;
    if (p === 'trimestriel') {
      this.filterForm.controls.periode_index.setValue(2);
    } else if (p === 'mensuel') {
      this.filterForm.controls.periode_index.setValue(new Date().getMonth() + 1);
    }
  }

  queryParams(): Record<string, string> {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = {
      annee: String(f.annee),
      periodicite: f.periodicite,
    };
    if (f.periodicite !== 'annuel') {
      params['periode_index'] = String(f.periode_index);
    }
    if (f.agence_id) {
      params['agence_id'] = f.agence_id;
    }
    if (f.categorie_id) {
      params['categorie_id'] = f.categorie_id;
    }
    return params;
  }

  load(): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee || annee < 2000 || annee > 2100) {
      void this.dialogs.error('Exercice invalide').subscribe();
      return;
    }
    this.loading.set(true);
    this.api
      .get<VentilationResponse>('/reporting/amortissements-agence', this.queryParams())
      .subscribe({
        next: (res) => {
          this.data.set(res);
          if (res.exercices_disponibles?.length) {
            this.exercices.set(res.exercices_disponibles);
          }
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          void this.dialogs
            .error(err.error?.detail ?? 'Impossible de charger le rapport')
            .subscribe();
        },
      });
  }

  resetFilters(): void {
    this.filterForm.reset({
      agence_id: '',
      annee: new Date().getFullYear(),
      periodicite: 'trimestriel',
      periode_index: 2,
      categorie_id: '',
    });
    this.load();
  }

  formatDate(iso: string | null): string {
    if (!iso) {
      return '—';
    }
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      return iso;
    }
    return d.toLocaleDateString('fr-FR');
  }

  categorieLabel(c: CategorieOption): string {
    const parts = [c.code, c.famille, c.sous_famille].filter(Boolean);
    return parts.join(' — ');
  }

  export(format: 'xlsx' | 'pdf'): void {
    this.exporting.set(format);
    this.api
      .download('/reporting/amortissements-agence/export', {
        ...this.queryParams(),
        format,
      })
      .subscribe({
        next: (blob) => {
          this.exporting.set(null);
          const annee = this.filterForm.controls.annee.value;
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `amortissements-agence-${annee}.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
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
