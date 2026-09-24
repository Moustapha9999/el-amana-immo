import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { formatMontant, formatQuantite } from '../shared/montant.pipe';

interface Col {
  key: string;
  label: string;
  kind: string;
}
interface CatalogItem {
  key: string;
  label: string;
  description: string;
  icon: string;
  group: string;
  filters: string[];
  columns: Col[];
}
interface Preview {
  report_key: string;
  label: string;
  total: number;
  page: number;
  size: number;
  columns: Col[];
  rows: Record<string, unknown>[];
  totals: Record<string, number>;
  filters_label: string;
  empty_message: string;
}
interface Agence {
  id: string;
  libelle: string;
}
interface Famille {
  id: string;
  libelle: string;
}

@Component({
  selector: 'bea-stock-rapport-viewer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting</p>
          <h1>{{ meta()?.label || preview()?.label || 'Rapport' }}</h1>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/rapports">
            <mat-icon>arrow_back</mat-icon> Catalogue
          </a>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" [disabled]="exporting()">
            <mat-icon>table_view</mat-icon> Excel
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" [disabled]="exporting()">
            <mat-icon>picture_as_pdf</mat-icon> PDF
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('csv')" [disabled]="exporting()">
            <mat-icon>description</mat-icon> CSV
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="print()">
            <mat-icon>print</mat-icon> Imprimer
          </button>
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="applyFilters()">
        @if (isCustom()) {
          <label class="bea-mg__field">
            <mat-icon>category</mat-icon>
            <select formControlName="dataset" (change)="onDatasetChange()">
              @for (d of datasets(); track d.key) {
                <option [value]="d.key">{{ d.label }}</option>
              }
            </select>
          </label>
        }
        @if (hasFilter('q')) {
          <label class="bea-mg__field bea-mg__field--grow">
            <mat-icon>search</mat-icon>
            <input formControlName="q" placeholder="Rechercher…" />
          </label>
        }
        @if (hasFilter('annee')) {
          <label class="bea-mg__field">
            <input type="number" formControlName="annee" placeholder="Année" />
          </label>
        }
        @if (hasFilter('mois')) {
          <label class="bea-mg__field">
            <select formControlName="mois">
              <option value="">Tous les mois</option>
              @for (m of months; track m) {
                <option [value]="m">{{ m }}</option>
              }
            </select>
          </label>
        }
        @if (hasFilter('agence_id')) {
          <label class="bea-mg__field">
            <select formControlName="agence_id">
              <option value="">Toutes agences</option>
              @for (a of agences(); track a.id) {
                <option [value]="a.id">{{ a.libelle }}</option>
              }
            </select>
          </label>
        }
        @if (hasFilter('famille_id')) {
          <label class="bea-mg__field">
            <select formControlName="famille_id">
              <option value="">Toutes familles</option>
              @for (f of familles(); track f.id) {
                <option [value]="f.id">{{ f.libelle }}</option>
              }
            </select>
          </label>
        }
        @if (hasFilter('departement')) {
          <label class="bea-mg__field">
            <input formControlName="departement" placeholder="Service / direction" />
          </label>
        }
        @if (hasFilter('statut')) {
          <label class="bea-mg__field">
            <input formControlName="statut" placeholder="Statut" />
          </label>
        }
        @if (hasFilter('nature_ecart')) {
          <label class="bea-mg__field">
            <select formControlName="nature_ecart">
              <option value="">Toutes natures</option>
              <option value="CONFORME">Conforme</option>
              <option value="SURPLUS">Surplus</option>
              <option value="MANQUANT">Manquant</option>
            </select>
          </label>
        }
        @if (hasFilter('type')) {
          <label class="bea-mg__field">
            <select formControlName="type">
              <option value="">Tous types</option>
              <option value="ENTREE">Entrée</option>
              <option value="SORTIE">Sortie</option>
              <option value="AJUSTEMENT">Ajustement</option>
            </select>
          </label>
        }
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary">
          <mat-icon>filter_list</mat-icon> Filtrer
        </button>
      </form>

      @if (isCustom() && datasetColumns().length) {
        <div class="bea-mg__panel" style="margin-bottom:1rem">
          <div class="bea-mg__panel-top"><h2>Colonnes</h2></div>
          <div style="display:flex;flex-wrap:wrap;gap:0.5rem 1rem">
            @for (c of datasetColumns(); track c.key) {
              <label>
                <input
                  type="checkbox"
                  [checked]="customColumns().includes(c.key)"
                  (change)="toggleColumn(c.key, $any($event.target).checked)"
                />
                {{ c.label }}
              </label>
            }
          </div>
        </div>
      }

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (preview(); as p) {
        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>{{ p.label }}</h2>
            <span class="bea-mg__count">{{ p.total }} ligne(s) · {{ p.filters_label }}</span>
          </div>
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table">
              <thead>
                <tr>
                  @for (c of p.columns; track c.key) {
                    <th>{{ c.label }}</th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of p.rows; track rowId(row, $index); let i = $index) {
                  <tr [style.--i]="i">
                    @for (c of p.columns; track c.key) {
                      <td>{{ cell(row, c) }}</td>
                    }
                  </tr>
                } @empty {
                  <tr>
                    <td [attr.colspan]="p.columns.length">
                      <div class="bea-mg__empty">
                        <mat-icon>insights</mat-icon>
                        <p>{{ p.empty_message || 'Aucune donnée disponible.' }}</p>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="bea-mg__actions" style="margin-top:0.75rem">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="goPage(-1)">Précédent</button>
            <span>Page {{ p.page }} / {{ totalPages() }}</span>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="goPage(1)">Suivant</button>
          </div>
        </div>
      }
    </section>
  `,
})
export class StockRapportViewerComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);

  readonly months = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
  readonly reportKey = signal('');
  readonly meta = signal<CatalogItem | null>(null);
  readonly preview = signal<Preview | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly familles = signal<Famille[]>([]);
  readonly catalog = signal<CatalogItem[]>([]);
  readonly customColumns = signal<string[]>([]);
  readonly erreur = signal('');
  readonly loading = signal(false);
  readonly exporting = signal(false);
  readonly page = signal(1);
  readonly size = 50;

  readonly filters = this.fb.nonNullable.group({
    q: [''],
    annee: [String(new Date().getFullYear())],
    mois: [''],
    agence_id: [''],
    famille_id: [''],
    departement: [''],
    statut: [''],
    nature_ecart: [''],
    type: [''],
    motif: [''],
    dataset: ['etat_stock'],
  });

  readonly isCustom = computed(() => this.reportKey() === 'personnalise');
  readonly datasets = computed(() =>
    this.catalog().filter((c) => c.key !== 'personnalise' && c.columns?.length),
  );
  readonly datasetColumns = computed(() => {
    const ds = this.filters.controls.dataset.value;
    return this.catalog().find((c) => c.key === ds)?.columns ?? [];
  });
  readonly totalPages = computed(() => {
    const p = this.preview();
    if (!p || !p.size) return 1;
    return Math.max(1, Math.ceil(p.total / p.size));
  });

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/stock/agences').subscribe({ next: (a) => this.agences.set(a) });
    this.api.get<Famille[]>('/mg/stock/familles').subscribe({ next: (f) => this.familles.set(f) });
    this.api.get<CatalogItem[]>('/mg/stock/rapports/catalog').subscribe({
      next: (rows) => {
        this.catalog.set(rows);
        const key = this.route.snapshot.paramMap.get('key') || '';
        this.reportKey.set(key);
        const meta = rows.find((r) => r.key === key) ?? null;
        this.meta.set(meta);
        if (key === 'personnalise') {
          const first = rows.find((r) => r.group === 'objets');
          if (first) {
            this.filters.patchValue({ dataset: first.key });
            this.customColumns.set(first.columns.map((c) => c.key));
          }
        }
        this.load();
      },
      error: () => this.erreur.set('Catalogue indisponible.'),
    });
  }

  hasFilter(name: string): boolean {
    if (this.isCustom()) {
      const ds = this.catalog().find((c) => c.key === this.filters.controls.dataset.value);
      return (ds?.filters ?? []).includes(name);
    }
    return (this.meta()?.filters ?? []).includes(name);
  }

  onDatasetChange(): void {
    this.customColumns.set(this.datasetColumns().map((c) => c.key));
    this.page.set(1);
    this.load();
  }

  toggleColumn(key: string, checked: boolean): void {
    const cur = new Set(this.customColumns());
    if (checked) cur.add(key);
    else cur.delete(key);
    this.customColumns.set([...cur]);
  }

  filterParams(): Record<string, string> {
    const v = this.filters.getRawValue();
    const p: Record<string, string> = {
      page: String(this.page()),
      size: String(this.size),
    };
    for (const k of [
      'q',
      'annee',
      'mois',
      'agence_id',
      'famille_id',
      'departement',
      'statut',
      'nature_ecart',
      'type',
      'motif',
    ] as const) {
      if (v[k] && this.hasFilter(k)) p[k] = String(v[k]);
    }
    return p;
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  goPage(delta: number): void {
    const next = Math.min(Math.max(1, this.page() + delta), this.totalPages());
    if (next === this.page()) return;
    this.page.set(next);
    this.load();
  }

  load(): void {
    this.erreur.set('');
    this.loading.set(true);
    const key = this.reportKey();
    if (key === 'personnalise') {
      const v = this.filters.getRawValue();
      this.api
        .post<Preview>('/mg/stock/rapports/personnalise/preview', {
          dataset: v.dataset,
          columns: this.customColumns(),
          filters: this.filterParams(),
          page: this.page(),
          size: this.size,
        })
        .subscribe({
          next: (p) => {
            this.preview.set(p);
            this.loading.set(false);
          },
          error: (err) => {
            this.loading.set(false);
            this.erreur.set(err?.error?.detail || 'Aperçu indisponible.');
          },
        });
      return;
    }
    this.api.get<Preview>(`/mg/stock/rapports/${key}/preview`, this.filterParams()).subscribe({
      next: (p) => {
        this.preview.set(p);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(err?.error?.detail || 'Aperçu indisponible.');
      },
    });
  }

  exportFile(format: 'xlsx' | 'pdf' | 'csv'): void {
    this.exporting.set(true);
    const key = this.reportKey();
    const body = {
      format,
      scope: 'filtered',
      filters: this.filterParams(),
      columns: this.isCustom() ? this.customColumns() : null,
    };
    const path =
      key === 'personnalise'
        ? '/mg/stock/rapports/personnalise/export'
        : `/mg/stock/rapports/${key}/export`;
    const payload =
      key === 'personnalise'
        ? { ...body, dataset: this.filters.controls.dataset.value }
        : body;
    this.api.downloadPost(path, payload).subscribe({
      next: (blob) => {
        this.exporting.set(false);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `stock-${key}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => {
        this.exporting.set(false);
        this.erreur.set(`Export ${format.toUpperCase()} impossible.`);
      },
    });
  }

  print(): void {
    window.print();
  }

  rowId(row: Record<string, unknown>, index: number): string {
    return String(row['id'] ?? index);
  }

  cell(row: Record<string, unknown>, col: Col): string {
    const v = row[col.key];
    const num = v as number | string | null | undefined;
    if (col.kind === 'money') return formatMontant(num);
    if (col.kind === 'number') return formatQuantite(num);
    if (v == null || v === '') return '—';
    return String(v);
  }
}
