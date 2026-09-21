import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../core/services/api.service';

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
  niveau: string | null;
}
interface Agence {
  id: string;
  libelle: string;
}

@Component({
  selector: 'bea-stock-articles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <h1>Articles</h1>
          <p>Référentiel par famille (économat, papeterie, pré-imprimé, GAB…).</p>
        </div>
      </header>

      <form class="bea-stock-toolbar" [formGroup]="filters" (ngSubmit)="load()">
        <input formControlName="q" placeholder="Recherche code / désignation" />
        <select formControlName="famille_id">
          <option value="">Toutes les familles</option>
          @for (f of familles(); track f.id) {
            <option [value]="f.id">{{ f.libelle }}</option>
          }
        </select>
        <label class="bea-stock-check">
          <input type="checkbox" formControlName="bas_stock" /> Bas stock
        </label>
        <button type="submit" class="bea-admin-btn">Filtrer</button>
      </form>

      <details class="bea-stock-panel" open>
        <summary>Nouvel article</summary>
        <form class="bea-stock-form" [formGroup]="create" (ngSubmit)="createArticle()">
          <label>Code <input formControlName="code" /></label>
          <label>Désignation <input formControlName="designation" /></label>
          <label>
            Famille
            <select formControlName="famille_id">
              @for (f of familles(); track f.id) {
                <option [value]="f.id">{{ f.libelle }}</option>
              }
            </select>
          </label>
          <label>UOM <input formControlName="uom" /></label>
          <label>Stock initial <input type="number" formControlName="stock_initial" /></label>
          <label>Stock min <input type="number" formControlName="stock_min" /></label>
          <label>
            Agence
            <select formControlName="agence_id">
              <option value="">—</option>
              @for (a of agences(); track a.id) {
                <option [value]="a.id">{{ a.libelle }}</option>
              }
            </select>
          </label>
          <button type="submit" class="bea-admin-btn" [disabled]="create.invalid || saving()">Créer</button>
        </form>
        @if (msg()) {
          <p class="bea-stock-page__ok">{{ msg() }}</p>
        }
        @if (erreur()) {
          <p class="bea-stock-page__error">{{ erreur() }}</p>
        }
      </details>

      <div class="bea-stock-panel">
        <table class="bea-stock-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Désignation</th>
              <th>Stock</th>
              <th>Min</th>
              <th>Niveau</th>
            </tr>
          </thead>
          <tbody>
            @for (a of articles(); track a.id) {
              <tr>
                <td>{{ a.code }}</td>
                <td>{{ a.designation }}</td>
                <td>{{ a.stock_actuel }} {{ a.uom }}</td>
                <td>{{ a.stock_min }}</td>
                <td>
                  <span class="bea-stock-pill" [attr.data-niveau]="a.niveau">{{ a.niveau }}</span>
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="5">Aucun article.</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
  `,
})
export class StockArticlesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly familles = signal<Famille[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly articles = signal<Article[]>([]);
  readonly saving = signal(false);
  readonly erreur = signal('');
  readonly msg = signal('');

  readonly filters = this.fb.nonNullable.group({
    q: '',
    famille_id: '',
    bas_stock: false,
  });

  readonly create = this.fb.nonNullable.group({
    code: ['', Validators.required],
    designation: ['', Validators.required],
    famille_id: ['', Validators.required],
    uom: ['U'],
    stock_initial: [0],
    stock_min: [0],
    agence_id: [''],
  });

  ngOnInit(): void {
    this.api.get<Famille[]>('/mg/stock/familles').subscribe((f) => {
      this.familles.set(f);
      if (f[0] && !this.create.value.famille_id) {
        this.create.patchValue({ famille_id: f[0].id });
      }
    });
    this.api.get<Agence[]>('/mg/stock/agences').subscribe((a) => this.agences.set(a));
    this.load();
  }

  load(): void {
    const v = this.filters.getRawValue();
    const params: Record<string, string> = {};
    if (v.q) params['q'] = v.q;
    if (v.famille_id) params['famille_id'] = v.famille_id;
    if (v.bas_stock) params['bas_stock'] = 'true';
    this.api.get<Article[]>('/mg/stock/articles', params).subscribe({
      next: (rows) => this.articles.set(rows),
      error: () => this.erreur.set('Chargement articles impossible'),
    });
  }

  createArticle(): void {
    if (this.create.invalid) return;
    this.saving.set(true);
    this.erreur.set('');
    const raw = this.create.getRawValue();
    const body = {
      ...raw,
      agence_id: raw.agence_id || null,
    };
    this.api.post<Article>('/mg/stock/articles', body).subscribe({
      next: () => {
        this.msg.set('Article créé.');
        this.saving.set(false);
        this.create.patchValue({ code: '', designation: '', stock_initial: 0 });
        this.load();
      },
      error: (err) => {
        this.erreur.set(err?.error?.detail || 'Création refusée');
        this.saving.set(false);
      },
    });
  }
}
