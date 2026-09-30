import { DatePipe } from '@angular/common';
import { MontantPipe, QuantitePipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { formatTauxPercent } from '../shared/amortissement-rate.util';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface CompteNatureLigne {
  immobilisation_id: string;
  code_inventaire: string;
  date_acquisition: string | null;
  quantite: number;
  designation: string;
  valeur_acquisition: number;
  taux: number | null;
  amorts_cumules_n1: number;
  dotations_annee: number;
  amorts_cumules_n: number;
  vnc: number;
  agence_code: string | null;
  agence_libelle: string | null;
}

interface CompteNatureGroupe {
  compte_immobilisation: string;
  intitule: string;
  lignes: CompteNatureLigne[];
  totaux: CompteNatureLigne;
}

interface CompteOption {
  numero: string;
  libelle: string;
}

interface ComptesParNatureResponse {
  annee: number;
  date_arrete: string;
  groupes: CompteNatureGroupe[];
  totaux: CompteNatureLigne;
  compte_filtre: string | null;
  comptes_disponibles: CompteOption[];
}

@Component({
  selector: 'app-comptes',
  imports: [ReactiveFormsModule, MontantPipe, QuantitePipe, DatePipe, MatButtonModule, MatIconModule, RouterLink, PaginationComponent],
  templateUrl: './comptes.component.html',
  styleUrl: './comptes.component.css',
})
export class ComptesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<ComptesParNatureResponse | null>(null);
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  readonly formatTaux = formatTauxPercent;

  /* Pagination indépendante par groupe de compte (les données arrivent en bloc). */
  readonly groupPageSize = 50;
  private readonly groupPages = signal<Record<string, number>>({});

  readonly filterForm = this.fb.nonNullable.group({
    annee: [new Date().getFullYear()],
    compte: [''],
    search: [''],
  });

  /** Recherche locale appliquée après chargement. */
  readonly localSearch = signal('');

  readonly comptesOptions = computed(() => this.data()?.comptes_disponibles ?? []);
  readonly singleCompte = computed(() => !!this.data()?.compte_filtre);
  readonly hasLignes = computed(() =>
    this.filteredGroupes().some((g) => g.lignes.length > 0),
  );

  readonly filteredGroupes = computed(() => {
    const groupes = this.data()?.groupes ?? [];
    const q = this.localSearch().trim().toLowerCase();
    if (!q) {
      return groupes;
    }
    return groupes
      .map((g) => {
        const lignes = g.lignes.filter((row) => this.ligneMatches(row, q));
        return { ...g, lignes, totaux: this.sumLignes(lignes, g.totaux) };
      })
      .filter((g) => g.lignes.length > 0);
  });

  readonly filteredTotaux = computed(() => {
    const d = this.data();
    if (!d || !this.localSearch().trim()) {
      return d?.totaux ?? null;
    }
    return this.sumLignes(
      this.filteredGroupes().flatMap((g) => g.lignes),
      d.totaux,
    );
  });

  private lastQuery: Record<string, string> = {};

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee || annee < 2000 || annee > 2100) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    const compte = (this.filterForm.controls.compte.value || '').trim();
    const query: Record<string, string> = { annee: String(annee) };
    if (compte) {
      query['compte'] = compte;
    }
    this.loading.set(true);
    this.api.get<ComptesParNatureResponse>('/reporting/comptes-par-nature', query).subscribe({
      next: (res) => {
        this.lastQuery = query;
        this.data.set(res);
        this.groupPages.set({});
        this.applyLocalSearch();
        this.loading.set(false);
      },
      error: (err: { error?: { detail?: unknown } }) => {
        this.loading.set(false);
        const detail = err.error?.detail;
        void this.dialogs
          .error(typeof detail === 'string' ? detail : 'Impossible de charger les comptes')
          .subscribe();
      },
    });
  }

  applyLocalSearch(): void {
    this.localSearch.set(this.filterForm.controls.search.value);
    this.groupPages.set({});
  }

  resetFilters(): void {
    const annee = this.filterForm.controls.annee.value;
    this.filterForm.reset({ annee, compte: '', search: '' });
    this.applyLocalSearch();
    this.load();
  }

  agenceLabel(row: CompteNatureLigne): string {
    return row.agence_libelle || row.agence_code || '—';
  }

  private sumLignes(lignes: CompteNatureLigne[], base: CompteNatureLigne): CompteNatureLigne {
    const sum = (pick: (l: CompteNatureLigne) => number) =>
      lignes.reduce((acc, l) => acc + (Number(pick(l)) || 0), 0);
    return {
      ...base,
      quantite: sum((l) => l.quantite),
      valeur_acquisition: sum((l) => l.valeur_acquisition),
      amorts_cumules_n1: sum((l) => l.amorts_cumules_n1),
      dotations_annee: sum((l) => l.dotations_annee),
      amorts_cumules_n: sum((l) => l.amorts_cumules_n),
      vnc: sum((l) => l.vnc),
    };
  }

  private ligneMatches(row: CompteNatureLigne, q: string): boolean {
    const fields = [
      row.code_inventaire,
      row.designation,
      row.date_acquisition,
      row.quantite,
      row.valeur_acquisition,
      row.taux,
      row.amorts_cumules_n1,
      row.dotations_annee,
      row.amorts_cumules_n,
      row.vnc,
      row.agence_code,
      row.agence_libelle,
    ];
    return fields.some((f) => String(f ?? '').toLowerCase().includes(q));
  }

  pageFor(compte: string): number {
    return this.groupPages()[compte] ?? 1;
  }

  setGroupPage(compte: string, page: number): void {
    this.groupPages.update((pages) => ({ ...pages, [compte]: page }));
  }

  pagedLignes(groupe: CompteNatureGroupe): CompteNatureLigne[] {
    const start = (this.pageFor(groupe.compte_immobilisation) - 1) * this.groupPageSize;
    return groupe.lignes.slice(start, start + this.groupPageSize);
  }

  export(format: 'xlsx' | 'pdf'): void {
    const annee = this.lastQuery['annee'];
    if (!annee) {
      return;
    }
    const compte = this.lastQuery['compte'] ?? '';
    const params: Record<string, string> = { ...this.lastQuery, format };
    const search = this.localSearch().trim();
    if (search) {
      params['search'] = search;
    }
    this.exporting.set(format);
    this.api.download('/reporting/comptes-par-nature/export', params).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        const suffix = compte ? `-${compte}` : '';
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `comptes-par-nature-${annee}${suffix}.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
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
