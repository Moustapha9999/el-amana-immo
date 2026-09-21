import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, HostListener, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { PaginationComponent } from '../shared/pagination.component';

interface Famille {
  id: string;
  code: string;
  libelle: string;
}
interface Article {
  id: string;
  code: string;
  designation: string;
  famille_id: string;
  uom: string;
  stock_actuel: number;
  stock_min: number;
  stock_max: number | null;
  agence_id: string | null;
  emplacement: string | null;
  niveau: string | null;
}
interface Agence {
  id: string;
  libelle: string;
}
interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

@Component({
  selector: 'bea-stock-articles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, DecimalPipe, MgGedPanelComponent, RouterLink, PaginationComponent],
  template: `
    <section class="bea-art">
      <header class="bea-art__head">
        <div>
          <p class="bea-stock-page__kicker">Référentiel</p>
          <h1>Articles</h1>
        </div>
        <div class="bea-art__head-actions">
          <button type="button" class="bea-art__btn bea-art__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
            <mat-icon>table_view</mat-icon> Excel
          </button>
          <button type="button" class="bea-art__btn bea-art__btn--ghost" (click)="exportFile('pdf')" title="PDF">
            <mat-icon>picture_as_pdf</mat-icon> PDF
          </button>
          <button type="button" class="bea-art__btn bea-art__btn--primary" (click)="openCreate()">
            <mat-icon>add</mat-icon> Nouvel article
          </button>
        </div>
      </header>

      <form class="bea-art__search" [formGroup]="filters" (ngSubmit)="applyFilters()">
        <label class="bea-art__search-field bea-art__search-field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Rechercher par code ou désignation…" (input)="onSearchInput()" />
        </label>
        <label class="bea-art__search-field">
          <mat-icon>category</mat-icon>
          <select formControlName="famille_id" (change)="applyFilters()">
            <option value="">Toutes les familles</option>
            @for (f of familles(); track f.id) {
              <option [value]="f.id">{{ f.libelle }}</option>
            }
          </select>
        </label>
        <label class="bea-art__toggle" [class.bea-art__toggle--on]="filters.value.bas_stock">
          <input type="checkbox" formControlName="bas_stock" (change)="applyFilters()" />
          <span>Bas stock</span>
        </label>
        <button type="submit" class="bea-art__btn bea-art__btn--primary">
          <mat-icon>filter_list</mat-icon> Filtrer
        </button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
      @if (msg()) {
        <p class="bea-stock-page__ok">{{ msg() }}</p>
      }

      <div class="bea-art__panel">
        <div class="bea-art__panel-top">
          <h2>Liste des articles</h2>
          <span class="bea-art__count">{{ total() }} résultat(s)</span>
        </div>
        <div class="bea-art__table-wrap">
          <table class="bea-art__table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Désignation</th>
                <th>Famille</th>
                <th>Stock</th>
                <th>Min</th>
                <th>Niveau</th>
                <th class="bea-art__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (a of articles(); track a.id; let i = $index) {
                <tr [style.--i]="i">
                  <td><code class="bea-art__code">{{ a.code }}</code></td>
                  <td>{{ a.designation }}</td>
                  <td>{{ familleLabel(a.famille_id) }}</td>
                  <td class="bea-art__num">{{ a.stock_actuel | number:'1.0-3' }} {{ a.uom }}</td>
                  <td class="bea-art__num">{{ a.stock_min | number:'1.0-3' }}</td>
                  <td>
                    <span class="bea-stock-badge" [attr.data-niveau]="a.niveau">{{ a.niveau || '—' }}</span>
                  </td>
                  <td class="bea-art__actions">
                    <a
                      class="bea-art__icon-btn"
                      title="Voir fiche"
                      [routerLink]="['/stock-fournitures/articles', a.id]"
                    >
                      <mat-icon>visibility</mat-icon>
                    </a>
                    <button type="button" class="bea-art__icon-btn" title="Modifier" (click)="openEdit(a)">
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button type="button" class="bea-art__icon-btn bea-art__icon-btn--danger" title="Désactiver" (click)="confirmDelete(a)">
                      <mat-icon>delete</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr class="bea-art__empty">
                  <td colspan="7">
                    <mat-icon>inventory_2</mat-icon>
                    <p>Aucun article pour ces critères.</p>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (total() > 0) {
          <app-pagination
            [page]="page()"
            [total]="total()"
            [pageSize]="pageSize"
            label="article(s)"
            (pageChange)="goToPage($event)"
          />
        }
      </div>

      @if (modalOpen()) {
        <div class="bea-art__backdrop" (click)="closeModal()" role="presentation"></div>
        <div class="bea-art__modal" role="dialog" aria-modal="true" [attr.aria-label]="editingId() ? 'Modifier article' : 'Nouvel article'">
          <header class="bea-art__modal-head">
            <div>
              <p class="bea-stock-page__kicker">{{ editingId() ? 'Modification' : 'Création' }}</p>
              <h2>{{ editingId() ? 'Modifier l’article' : 'Nouvel article' }}</h2>
            </div>
            <button type="button" class="bea-art__icon-btn" (click)="closeModal()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <form class="bea-art__modal-form" [formGroup]="form" (ngSubmit)="save()">
            <div class="bea-art__grid">
              <label>
                Code
                <input formControlName="code" [readonly]="!!editingId()" />
              </label>
              <label class="bea-art__span2">
                Désignation
                <input formControlName="designation" />
              </label>
              <label>
                Famille
                <select formControlName="famille_id">
                  @for (f of familles(); track f.id) {
                    <option [value]="f.id">{{ f.libelle }}</option>
                  }
                </select>
              </label>
              <label>
                Unité (UOM)
                <input formControlName="uom" />
              </label>
              @if (!editingId()) {
                <label>
                  Stock initial
                  <input type="number" formControlName="stock_initial" min="0" step="0.001" />
                </label>
              }
              <label>
                Stock minimum
                <input type="number" formControlName="stock_min" min="0" step="0.001" />
              </label>
              <label>
                Agence
                <select formControlName="agence_id">
                  <option value="">—</option>
                  @for (a of agences(); track a.id) {
                    <option [value]="a.id">{{ a.libelle }}</option>
                  }
                </select>
              </label>
              <label>
                Emplacement
                <input formControlName="emplacement" placeholder="Rayon / casier…" />
              </label>
            </div>
            @if (editingId(); as aid) {
              <bea-mg-ged moduleCode="stock-fournitures" entity="article" [entityId]="aid" />
            }
            @if (modalErreur()) {
              <p class="bea-stock-page__error">{{ modalErreur() }}</p>
            }
            <footer class="bea-art__modal-foot">
              <button type="button" class="bea-art__btn bea-art__btn--ghost" (click)="closeModal()">Annuler</button>
              <button type="submit" class="bea-art__btn bea-art__btn--primary" [disabled]="form.invalid || saving()">
                {{ editingId() ? 'Enregistrer' : 'Créer' }}
              </button>
            </footer>
          </form>
        </div>
      }

      @if (deleteTarget(); as del) {
        <div class="bea-art__backdrop" (click)="deleteTarget.set(null)" role="presentation"></div>
        <div class="bea-art__modal bea-art__modal--sm" role="dialog" aria-modal="true">
          <header class="bea-art__modal-head">
            <div>
              <h2>Désactiver l’article ?</h2>
              <p>{{ del.code }} — {{ del.designation }}</p>
            </div>
          </header>
          <footer class="bea-art__modal-foot">
            <button type="button" class="bea-art__btn bea-art__btn--ghost" (click)="deleteTarget.set(null)">Annuler</button>
            <button type="button" class="bea-art__btn bea-art__btn--danger" (click)="doDelete()" [disabled]="saving()">
              Désactiver
            </button>
          </footer>
        </div>
      }
    </section>
  `,
  styles: `
    :host { display: block; }

    .bea-art { max-width: 74rem; animation: beaArtIn 0.4s ease both; }

    .bea-art__head {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      justify-content: space-between;
      align-items: flex-end;
      margin-bottom: 1.15rem;
    }
    .bea-art__head h1 {
      margin: 0.15rem 0 0;
      font-size: clamp(1.4rem, 2.2vw, 1.7rem);
      letter-spacing: -0.02em;
      color: #0f172a;
    }
    .bea-art__head-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .bea-art__btn {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      border: 1px solid transparent;
      border-radius: 0.55rem;
      padding: 0.5rem 0.9rem;
      font: inherit;
      font-size: 0.88rem;
      font-weight: 600;
      cursor: pointer;
      transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
    }
    .bea-art__btn mat-icon { font-size: 1.1rem; width: 1.1rem; height: 1.1rem; }
    .bea-art__btn--primary {
      background: #1a5278;
      color: #fff;
      box-shadow: 0 4px 12px rgba(26, 82, 120, 0.25);
    }
    .bea-art__btn--primary:hover { background: #154360; transform: translateY(-1px); }
    .bea-art__btn--ghost {
      background: #fff;
      border-color: #cbd5e1;
      color: #1a5278;
    }
    .bea-art__btn--ghost:hover { border-color: #1a5278; background: #f8fafc; }
    .bea-art__btn--danger {
      background: #b91c1c;
      color: #fff;
    }
    .bea-art__btn:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }

    .bea-art__search {
      display: flex;
      flex-wrap: wrap;
      gap: 0.65rem;
      align-items: stretch;
      margin-bottom: 1.15rem;
      padding: 0.85rem;
      background: #fff;
      border: 1px solid #dbe3ee;
      border-radius: 0.95rem;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
      animation: beaArtRise 0.45s ease both;
      animation-delay: 0.05s;
    }
    .bea-art__search-field {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.35rem 0.7rem;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 0.6rem;
      min-width: 11rem;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .bea-art__search-field:focus-within {
      border-color: #1a5278;
      box-shadow: 0 0 0 3px rgba(26, 82, 120, 0.12);
      background: #fff;
    }
    .bea-art__search-field--grow { flex: 1 1 16rem; }
    .bea-art__search-field mat-icon { color: #64748b; font-size: 1.15rem; width: 1.15rem; height: 1.15rem; }
    .bea-art__search-field input,
    .bea-art__search-field select {
      flex: 1;
      border: 0;
      background: transparent;
      font: inherit;
      font-size: 0.9rem;
      outline: none;
      min-width: 0;
      padding: 0.35rem 0;
    }

    .bea-art__toggle {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.45rem 0.85rem;
      border-radius: 999px;
      border: 1px solid #e2e8f0;
      background: #f8fafc;
      font-size: 0.82rem;
      color: #475569;
      cursor: pointer;
      user-select: none;
    }
    .bea-art__toggle--on {
      background: #fef3c7;
      border-color: #f59e0b;
      color: #92400e;
      font-weight: 600;
    }
    .bea-art__toggle input { accent-color: #1a5278; }

    .bea-art__panel {
      background: #fff;
      border: 1px solid #dbe3ee;
      border-radius: 1rem;
      overflow: hidden;
      box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
      animation: beaArtRise 0.5s ease both;
      animation-delay: 0.12s;
    }
    .bea-art__panel-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.95rem 1.15rem;
      border-bottom: 1px solid #eef2f7;
      background: linear-gradient(180deg, #f8fafc, #fff);
    }
    .bea-art__panel-top h2 {
      margin: 0;
      font-size: 1rem;
      color: #0f172a;
    }
    .bea-art__count {
      font-size: 0.78rem;
      color: #64748b;
      background: #eef2f7;
      padding: 0.25rem 0.6rem;
      border-radius: 999px;
    }

    .bea-art__table-wrap { overflow-x: auto; }
    .bea-art__table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }
    .bea-art__table th {
      text-align: left;
      padding: 0.7rem 1rem;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #64748b;
      background: #f8fafc;
      border-bottom: 1px solid #e2e8f0;
      white-space: nowrap;
    }
    .bea-art__table td {
      padding: 0.75rem 1rem;
      border-bottom: 1px solid #f1f5f9;
      color: #0f172a;
      vertical-align: middle;
    }
    .bea-art__table tbody tr {
      animation: beaArtRise 0.4s ease both;
      animation-delay: calc(0.15s + var(--i, 0) * 35ms);
      transition: background 0.15s ease;
    }
    .bea-art__table tbody tr:hover { background: #f8fafc; }

    .bea-art__code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.82rem;
      background: #eef2f7;
      padding: 0.15rem 0.4rem;
      border-radius: 0.3rem;
      color: #1a5278;
    }
    .bea-art__num { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .bea-art__th-actions,
    .bea-art__actions { text-align: right; white-space: nowrap; }

    .bea-art__icon-btn {
      display: inline-grid;
      place-items: center;
      width: 2rem;
      height: 2rem;
      margin-left: 0.2rem;
      border: 1px solid #e2e8f0;
      border-radius: 0.45rem;
      background: #fff;
      color: #475569;
      cursor: pointer;
      text-decoration: none;
      transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
    }
    .bea-art__icon-btn mat-icon { font-size: 1.05rem; width: 1.05rem; height: 1.05rem; }
    .bea-art__icon-btn:hover {
      color: #1a5278;
      border-color: #94a3b8;
      transform: translateY(-1px);
    }
    .bea-art__icon-btn--danger:hover {
      color: #b91c1c;
      border-color: #fca5a5;
      background: #fef2f2;
    }

    .bea-art__empty td {
      text-align: center;
      padding: 2.5rem 1rem;
      color: #64748b;
    }
    .bea-art__empty mat-icon {
      font-size: 2rem;
      width: 2rem;
      height: 2rem;
      opacity: 0.45;
    }
    .bea-art__empty p { margin: 0.4rem 0 0; }

    .bea-art__backdrop {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(2px);
      z-index: 40;
      animation: beaArtFade 0.2s ease both;
    }
    .bea-art__modal {
      position: fixed;
      z-index: 41;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: min(34rem, calc(100vw - 1.5rem));
      max-height: calc(100vh - 2rem);
      overflow: auto;
      background: #fff;
      border-radius: 1rem;
      box-shadow: 0 24px 48px rgba(15, 23, 42, 0.28);
      animation: beaArtModalIn 0.28s cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    .bea-art__modal--sm { width: min(26rem, calc(100vw - 1.5rem)); }
    .bea-art__modal-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      padding: 1.1rem 1.25rem 0.85rem;
      border-bottom: 1px solid #eef2f7;
    }
    .bea-art__modal-head h2 {
      margin: 0.1rem 0 0;
      font-size: 1.15rem;
      color: #0f172a;
    }
    .bea-art__modal-head p { margin: 0.35rem 0 0; color: #64748b; font-size: 0.88rem; }
    .bea-art__modal-form { padding: 1rem 1.25rem 1.15rem; }
    .bea-art__grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
    }
    .bea-art__span2 { grid-column: 1 / -1; }
    .bea-art__grid label {
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
      font-size: 0.78rem;
      color: #475569;
      font-weight: 600;
    }
    .bea-art__grid input,
    .bea-art__grid select {
      font: inherit;
      font-weight: 400;
      font-size: 0.9rem;
      padding: 0.5rem 0.65rem;
      border: 1px solid #cbd5e1;
      border-radius: 0.45rem;
      background: #fff;
    }
    .bea-art__grid input:focus,
    .bea-art__grid select:focus {
      outline: none;
      border-color: #1a5278;
      box-shadow: 0 0 0 3px rgba(26, 82, 120, 0.12);
    }
    .bea-art__grid input[readonly] {
      background: #f1f5f9;
      color: #64748b;
    }
    .bea-art__modal-foot {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
      margin-top: 1rem;
      padding: 0 1.25rem 1.15rem;
    }
    .bea-art__modal--sm .bea-art__modal-foot { padding-top: 0.5rem; }

    @keyframes beaArtIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes beaArtRise {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes beaArtFade {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes beaArtModalIn {
      from { opacity: 0; transform: translate(-50%, -46%) scale(0.96); }
      to { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    }

    @media (max-width: 640px) {
      .bea-art__grid { grid-template-columns: 1fr; }
      .bea-art__span2 { grid-column: auto; }
    }

    @media (prefers-reduced-motion: reduce) {
      .bea-art,
      .bea-art__search,
      .bea-art__panel,
      .bea-art__table tbody tr,
      .bea-art__backdrop,
      .bea-art__modal {
        animation: none !important;
      }
    }
  `,
})
export class StockArticlesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly familles = signal<Famille[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly articles = signal<Article[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly saving = signal(false);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly modalErreur = signal('');
  readonly modalOpen = signal(false);
  readonly editingId = signal<string | null>(null);
  readonly deleteTarget = signal<Article | null>(null);

  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  readonly filters = this.fb.nonNullable.group({
    q: '',
    famille_id: '',
    bas_stock: false,
  });

  readonly form = this.fb.nonNullable.group({
    code: ['', Validators.required],
    designation: ['', Validators.required],
    famille_id: ['', Validators.required],
    uom: ['U', Validators.required],
    stock_initial: [0],
    stock_min: [0],
    agence_id: [''],
    emplacement: [''],
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.deleteTarget()) {
      this.deleteTarget.set(null);
      return;
    }
    if (this.modalOpen()) this.closeModal();
  }

  ngOnInit(): void {
    this.api.get<Famille[]>('/mg/stock/familles').subscribe((f) => this.familles.set(f));
    this.api.get<Agence[]>('/mg/stock/agences').subscribe((a) => this.agences.set(a));
    this.load();
  }

  familleLabel(id: string): string {
    return this.familles().find((f) => f.id === id)?.libelle || '—';
  }

  filterParams(): Record<string, string> {
    const v = this.filters.getRawValue();
    const params: Record<string, string> = {};
    if (v.q) params['q'] = v.q;
    if (v.famille_id) params['famille_id'] = v.famille_id;
    if (v.bas_stock) params['bas_stock'] = 'true';
    return params;
  }

  onSearchInput(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.applyFilters(), 280);
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  load(): void {
    this.erreur.set('');
    const params: Record<string, string | number> = {
      ...this.filterParams(),
      page: this.page(),
      size: this.pageSize,
    };
    this.api.get<Paginated<Article>>('/mg/stock/articles', params).subscribe({
      next: (res) => {
        this.articles.set(res.items);
        this.total.set(res.total);
      },
      error: () => {
        this.articles.set([]);
        this.total.set(0);
        this.erreur.set('Chargement articles impossible');
      },
    });
  }

  openCreate(): void {
    this.editingId.set(null);
    this.modalErreur.set('');
    this.msg.set('');
    const firstFamille = this.familles()[0]?.id || '';
    this.form.reset({
      code: '',
      designation: '',
      famille_id: firstFamille,
      uom: 'U',
      stock_initial: 0,
      stock_min: 0,
      agence_id: '',
      emplacement: '',
    });
    this.form.controls.code.enable();
    this.modalOpen.set(true);
  }

  openEdit(a: Article): void {
    this.editingId.set(a.id);
    this.modalErreur.set('');
    this.msg.set('');
    this.form.reset({
      code: a.code,
      designation: a.designation,
      famille_id: a.famille_id,
      uom: a.uom,
      stock_initial: 0,
      stock_min: Number(a.stock_min),
      agence_id: a.agence_id || '',
      emplacement: a.emplacement || '',
    });
    this.form.controls.code.disable();
    this.modalOpen.set(true);
  }

  closeModal(): void {
    this.modalOpen.set(false);
    this.editingId.set(null);
    this.form.controls.code.enable();
  }

  save(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.modalErreur.set('');
    const raw = this.form.getRawValue();
    const id = this.editingId();

    if (id) {
      const body = {
        designation: raw.designation,
        famille_id: raw.famille_id,
        uom: raw.uom,
        stock_min: raw.stock_min,
        agence_id: raw.agence_id || null,
        emplacement: raw.emplacement || null,
      };
      this.api.patch<Article>(`/mg/stock/articles/${id}`, body).subscribe({
        next: () => {
          this.saving.set(false);
          this.msg.set('Article mis à jour.');
          this.closeModal();
          this.load();
        },
        error: (err) => {
          this.modalErreur.set(err?.error?.detail || 'Modification refusée');
          this.saving.set(false);
        },
      });
      return;
    }

    const body = {
      code: raw.code,
      designation: raw.designation,
      famille_id: raw.famille_id,
      uom: raw.uom,
      stock_initial: raw.stock_initial,
      stock_min: raw.stock_min,
      agence_id: raw.agence_id || null,
      emplacement: raw.emplacement || null,
    };
    this.api.post<Article>('/mg/stock/articles', body).subscribe({
      next: () => {
        this.saving.set(false);
        this.msg.set('Article créé.');
        this.closeModal();
        this.load();
      },
      error: (err) => {
        this.modalErreur.set(err?.error?.detail || 'Création refusée');
        this.saving.set(false);
      },
    });
  }

  confirmDelete(a: Article): void {
    this.deleteTarget.set(a);
  }

  doDelete(): void {
    const a = this.deleteTarget();
    if (!a) return;
    this.saving.set(true);
    this.api.delete<Article>(`/mg/stock/articles/${a.id}`).subscribe({
      next: () => {
        this.saving.set(false);
        this.deleteTarget.set(null);
        this.msg.set(`Article ${a.code} désactivé.`);
        this.load();
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(err?.error?.detail || 'Désactivation refusée');
        this.deleteTarget.set(null);
      },
    });
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    const params = { ...this.filterParams(), format };
    this.api.download('/mg/stock/articles/export', params).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `articles-stock.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible (permission export ?)`),
    });
  }
}
