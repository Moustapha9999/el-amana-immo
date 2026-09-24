import { KeyValuePipe } from '@angular/common';
import { MontantPipe, QuantitePipe, formatMontant, formatQuantite } from '../shared/montant.pipe';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

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
  csv_enabled: boolean;
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
  kpis?: Record<string, number>;
  bons_par_statut?: { statut: string; count: number }[];
}

interface Agence {
  id: string;
  libelle: string;
}

@Component({
  selector: 'bea-achats-rapport-viewer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, MontantPipe, QuantitePipe, KeyValuePipe],
  templateUrl: './achats-rapport-viewer.component.html',
})
export class AchatsRapportViewerComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(FormBuilder);

  readonly reportKey = signal('');
  readonly meta = signal<CatalogItem | null>(null);
  readonly preview = signal<Preview | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly selected = signal<Set<string>>(new Set());
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly loading = signal(false);
  readonly exporting = signal(false);
  readonly page = signal(1);
  readonly size = signal(50);
  readonly customColumns = signal<string[]>([]);

  readonly filters = this.fb.nonNullable.group({
    q: [''],
    statut: [''],
    priorite: [''],
    type_achat: [''],
    type_fournisseur: [''],
    ville: [''],
    pays: [''],
    departement: [''],
    type: [''],
    agence_id: [''],
    fournisseur_id: [''],
    date_debut: [''],
    date_fin: [''],
    sort_by: [''],
    sort_dir: ['desc'],
    dataset: ['demandes'],
  });

  readonly isAnalyses = computed(() => this.reportKey() === 'analyses');
  readonly isCustom = computed(() => this.reportKey() === 'personnalise');
  readonly selectedCount = computed(() => this.selected().size);
  readonly allPageSelected = computed(() => {
    const rows = this.preview()?.rows ?? [];
    if (!rows.length) return false;
    const sel = this.selected();
    return rows.every((r) => sel.has(String(r['id'])));
  });
  readonly totalPages = computed(() => {
    const p = this.preview();
    if (!p || !p.size) return 1;
    return Math.max(1, Math.ceil(p.total / p.size));
  });

  readonly availableFilters = computed(() => {
    if (this.isCustom()) {
      const ds = this.filters.controls.dataset.value;
      const cat = this.catalogDatasets().find((c) => c.key === ds);
      return cat?.filters ?? [];
    }
    return this.meta()?.filters ?? [];
  });

  readonly catalogDatasets = signal<CatalogItem[]>([]);

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/achats/agences').subscribe({
      next: (a) => this.agences.set(a),
    });
    this.api.get<CatalogItem[]>('/mg/achats/rapports/catalog').subscribe({
      next: (rows) => {
        this.catalogDatasets.set(rows.filter((r) => r.group === 'objets' || r.group === 'pilotage'));
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
      error: () => this.erreur.set('Impossible de charger le catalogue.'),
    });
  }

  onDatasetChange(): void {
    const ds = this.filters.controls.dataset.value;
    const item = this.catalogDatasets().find((c) => c.key === ds);
    this.customColumns.set(item?.columns.map((c) => c.key) ?? []);
    this.page.set(1);
    this.selected.set(new Set());
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
    const allowed = new Set(this.availableFilters());
    const p: Record<string, string> = {
      page: String(this.page()),
      size: String(this.size()),
    };
    const maybe = [
      'q',
      'statut',
      'priorite',
      'type_achat',
      'type_fournisseur',
      'ville',
      'pays',
      'departement',
      'type',
      'agence_id',
      'fournisseur_id',
      'date_debut',
      'date_fin',
      'sort_by',
      'sort_dir',
    ] as const;
    for (const k of maybe) {
      const val = v[k];
      if (val && (allowed.has(k) || k === 'sort_by' || k === 'sort_dir')) {
        p[k] = val;
      }
    }
    // Always allow period on analyses
    if (this.isAnalyses()) {
      if (v.date_debut) p['date_debut'] = v.date_debut;
      if (v.date_fin) p['date_fin'] = v.date_fin;
      if (v.agence_id) p['agence_id'] = v.agence_id;
    }
    return p;
  }

  load(): void {
    this.erreur.set('');
    this.msg.set('');
    this.loading.set(true);
    const key = this.reportKey();

    if (key === 'personnalise') {
      const v = this.filters.getRawValue();
      this.api
        .post<Preview>('/mg/achats/rapports/personnalise/preview', {
          dataset: v.dataset,
          columns: this.customColumns(),
          filters: this.filterParams(),
          sort_by: v.sort_by || null,
          sort_dir: v.sort_dir || 'desc',
          page: this.page(),
          size: this.size(),
        })
        .subscribe({
          next: (p) => {
            this.preview.set(p);
            this.loading.set(false);
          },
          error: (err) => {
            this.loading.set(false);
            this.preview.set(null);
            this.erreur.set(this.apiDetail(err, 'Aperçu indisponible.'));
          },
        });
      return;
    }

    this.api
      .get<Preview>(`/mg/achats/rapports/${key}/preview`, this.filterParams())
      .subscribe({
        next: (p) => {
          this.preview.set(p);
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          this.preview.set(null);
          this.erreur.set(this.apiDetail(err, 'Aperçu indisponible.'));
        },
      });
  }

  applyFilters(): void {
    this.page.set(1);
    this.selected.set(new Set());
    this.load();
  }

  goPage(delta: number): void {
    const next = Math.min(Math.max(1, this.page() + delta), this.totalPages());
    if (next === this.page()) return;
    this.page.set(next);
    this.load();
  }

  toggleRow(id: string, checked: boolean): void {
    const next = new Set(this.selected());
    if (checked) next.add(id);
    else next.delete(id);
    this.selected.set(next);
  }

  toggleAllPage(checked: boolean): void {
    const next = new Set(this.selected());
    for (const r of this.preview()?.rows ?? []) {
      const id = String(r['id'] ?? '');
      if (!id) continue;
      if (checked) next.add(id);
      else next.delete(id);
    }
    this.selected.set(next);
  }

  formatKpi(key: string, value: unknown): string {
    if (String(key).startsWith('montant') || String(key).includes('ht') || String(key).includes('ttc')) {
      return formatMontant(value as number | string | null);
    }
    return formatQuantite(value as number | string | null);
  }

  cellValue(row: Record<string, unknown>, col: Col): string | number {
    const v = row[col.key];
    if (col.kind === 'bool') return v ? 'Oui' : 'Non';
    if (col.kind === 'money' || col.kind === 'number') {
      return v == null || v === '' ? 0 : (v as number);
    }
    if (v == null || v === '') return '—';
    return v as string | number;
  }

  rowId(row: Record<string, unknown>): string {
    return String(row['id'] ?? '');
  }

  export(format: 'pdf' | 'xlsx' | 'csv', scope: 'selection' | 'filtered'): void {
    this.erreur.set('');
    this.msg.set('');
    if (scope === 'selection' && this.selectedCount() === 0) {
      this.erreur.set('Sélectionnez au moins une ligne.');
      return;
    }
    const key = this.reportKey();
    const filters = this.filterParams();
    delete filters['page'];
    delete filters['size'];

    this.exporting.set(true);
    const body: Record<string, unknown> = {
      format,
      scope,
      ids: scope === 'selection' ? [...this.selected()] : [],
      filters,
    };

    const path =
      key === 'personnalise'
        ? '/mg/achats/rapports/personnalise/export'
        : `/mg/achats/rapports/${key}/export`;

    if (key === 'personnalise') {
      body['dataset'] = this.filters.controls.dataset.value;
      body['columns'] = this.customColumns();
      body['sort_by'] = this.filters.controls.sort_by.value || null;
      body['sort_dir'] = this.filters.controls.sort_dir.value || 'desc';
    }

    this.api.downloadPost(path, body).subscribe({
      next: (blob) => {
        this.exporting.set(false);
        if (blob.type?.includes('json')) {
          this.erreur.set('Export refusé (permissions ou aucun résultat).');
          return;
        }
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `achats-${key}-${scope}.${format === 'xlsx' ? 'xlsx' : format}`;
        a.click();
        URL.revokeObjectURL(url);
        this.msg.set(
          scope === 'selection'
            ? `Export ${format.toUpperCase()} de la sélection (${this.selectedCount()} ligne(s)).`
            : `Export ${format.toUpperCase()} de tous les résultats filtrés.`,
        );
      },
      error: (err) => {
        this.exporting.set(false);
        this.erreur.set(this.apiDetail(err, `Export ${format.toUpperCase()} impossible.`));
      },
    });
  }

  print(): void {
    window.print();
  }

  datasetColumns(): Col[] {
    const ds = this.filters.controls.dataset.value;
    return this.catalogDatasets().find((c) => c.key === ds)?.columns ?? [];
  }

  private apiDetail(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    return fallback;
  }
}
