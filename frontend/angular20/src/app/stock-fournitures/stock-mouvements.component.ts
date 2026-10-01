import { DatePipe } from '@angular/common';
import { QuantitePipe } from '../shared/montant.pipe';
import { ChangeDetectionStrategy, Component, HostListener, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { PaginationComponent } from '../shared/pagination.component';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import {
  StockMouvementActions,
  StockMouvementEditComponent,
  StockMouvementRow,
  StockMouvementViewComponent,
} from './stock-mouvement-edit.component';
import { StockAlertesWatcherService } from './stock-alertes-watcher.service';

interface Article {
  id: string;
  code: string;
  designation: string;
}
interface Agence {
  id: string;
  libelle: string;
}
interface Mouvement extends StockMouvementRow {
  departement: string | null;
  initiateur_nom?: string | null;
  stock_disponible?: number | null;
}
interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

@Component({
  selector: 'bea-stock-mouvements',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    MatIconModule,
    DatePipe,
    QuantitePipe,
    PaginationComponent,
    StockMouvementEditComponent,
    StockMouvementViewComponent,
  ],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Stock &amp; fournitures</p>
          <h1>Journal des mouvements</h1>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
            <mat-icon>table_view</mat-icon> Excel
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" title="PDF">
            <mat-icon>picture_as_pdf</mat-icon> PDF
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openCreate()">
            <mat-icon>add</mat-icon> Nouveau mouvement
          </button>
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="applyFilters()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Rechercher par réf. ou motif…" (input)="onSearchInput()" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>swap_vert</mat-icon>
          <select formControlName="type_mouvement" (change)="applyFilters()">
            <option value="">Tous les types</option>
            <option value="ENTREE">Entrée</option>
            <option value="SORTIE">Sortie</option>
            <option value="AJUSTEMENT">Ajustement</option>
            <option value="INVENTAIRE">Inventaire</option>
          </select>
        </label>
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary">
          <mat-icon>filter_list</mat-icon> Filtrer
        </button>
      </form>


      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Mouvements</h2>
          <span class="bea-mg__count">{{ total() }} résultat(s)</span>
        </div>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Réf</th>
                <th>Date</th>
                <th>Type</th>
                <th>Article</th>
                <th>Initiateur</th>
                <th>Stock dispo.</th>
                <th>Qté</th>
                <th>Motif</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (m of filtered(); track m.id; let i = $index) {
                <tr [style.--i]="i">
                  <td><code class="bea-mg__code">{{ m.reference }}</code></td>
                  <td>{{ m.date_mouvement | date: 'dd/MM/yyyy HH:mm' }}</td>
                  <td>
                    <span class="bea-stock-badge" [attr.data-type]="m.type_mouvement">{{ typeLabel(m.type_mouvement) }}</span>
                  </td>
                  <td>{{ m.article_code || articleLabel(m.article_id) }}</td>
                  <td>{{ m.initiateur_nom || '—' }}</td>
                  <td>{{ m.stock_disponible | quantite }}</td>
                  <td>{{ m.quantite | quantite }}</td>
                  <td>{{ m.motif || '—' }}</td>
                  <td class="bea-mg__actions-cell">
                    <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="openView(m)">
                      <mat-icon>visibility</mat-icon>
                    </button>
                    <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editTarget.set(m)">
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button
                      type="button"
                      class="bea-mg__icon-btn bea-mg__icon-btn--danger"
                      [title]="m.quantite_modifiable ? 'Supprimer' : mouvementActions.peutSupprimer(m) ? 'Suppression administrateur (motif requis)' : 'Suppression impossible (période clôturée, inventaire ou mouvement de workflow)'"
                      [disabled]="!mouvementActions.peutSupprimer(m)"
                      (click)="supprimer(m)"
                    >
                      <mat-icon>delete</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="9">
                    <div class="bea-mg__empty">
                      <mat-icon>swap_horiz</mat-icon>
                      <p>Aucun mouvement pour ces critères.</p>
                    </div>
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
            label="mouvement(s)"
            (pageChange)="goToPage($event)"
          />
        }
      </div>

      @if (createOpen()) {
        <div class="bea-mg__backdrop" (click)="closeCreate()" role="presentation"></div>
        <div class="bea-mg__modal" role="dialog" aria-modal="true" aria-label="Nouveau mouvement">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Création</p>
              <h2>Nouveau mouvement</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeCreate()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <form [formGroup]="form" (ngSubmit)="submit()">
            <div class="bea-mg__modal-body">
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">
                  Article
                  <select formControlName="article_id">
                    @for (a of articles(); track a.id) {
                      <option [value]="a.id">{{ a.code }} — {{ a.designation }}</option>
                    }
                  </select>
                </label>
                <label>
                  Type
                  <select formControlName="type_mouvement">
                    <option value="ENTREE">Entrée</option>
                    <option value="SORTIE">Sortie</option>
                    <option value="AJUSTEMENT">Ajustement</option>
                    <option value="INVENTAIRE">Inventaire</option>
                  </select>
                </label>
                <label>
                  Quantité
                  <input type="number" formControlName="quantite" min="1" step="1" />
                </label>
                <label class="bea-mg__span2">
                  Motif
                  <input formControlName="motif" placeholder="Motif du mouvement…" />
                </label>
                <label class="bea-mg__span2">
                  Agence
                  <select formControlName="agence_id">
                    <option value="">—</option>
                    @for (a of agences(); track a.id) {
                      <option [value]="a.id">{{ a.libelle }}</option>
                    }
                  </select>
                </label>
              </div>
              @if (modalErreur()) {
                <p class="bea-stock-page__error">{{ modalErreur() }}</p>
              }
            </div>
            <footer class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closeCreate()">Annuler</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || saving()">
                Enregistrer
              </button>
            </footer>
          </form>
        </div>
      }

      @if (viewTarget(); as m) {
        <bea-stock-mouvement-view
          [mouvement]="m"
          [agence]="m.agence_id ? agenceLabel(m.agence_id) : null"
          [peutSupprimer]="mouvementActions.peutSupprimer(m)"
          (closed)="viewTarget.set(null)"
          (modifier)="viewTarget.set(null); editTarget.set(m)"
          (supprimer)="viewTarget.set(null); supprimer(m)"
        />
      }

      @if (editTarget(); as e) {
        <bea-stock-mouvement-edit
          [mouvement]="e"
          [agences]="agences()"
          (closed)="editTarget.set(null)"
          (saved)="editTarget.set(null); apresMutation()"
        />
      }
    </section>
  `,
})
export class StockMouvementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly articles = signal<Article[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly mouvements = signal<Mouvement[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly saving = signal(false);
  readonly erreur = feedbackSignal('error', '');
  readonly msg = feedbackSignal('success', '');
  readonly modalErreur = signal('');
  readonly createOpen = signal(false);
  readonly viewTarget = signal<Mouvement | null>(null);
  readonly editTarget = signal<Mouvement | null>(null);
  protected readonly mouvementActions = inject(StockMouvementActions);
  private readonly alertesWatcher = inject(StockAlertesWatcherService);

  private searchTimer: ReturnType<typeof setTimeout> | null = null;
  /** Filtres de la liste affichée, repris tels quels par l'export. */
  private filtresAffiches: Record<string, string> = {};

  readonly filters = this.fb.nonNullable.group({
    q: '',
    type_mouvement: '',
  });

  readonly form = this.fb.nonNullable.group({
    article_id: ['', Validators.required],
    type_mouvement: ['ENTREE', Validators.required],
    quantite: [1, [Validators.required, Validators.min(1)]],
    motif: [''],
    agence_id: [''],
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.viewTarget()) {
      this.viewTarget.set(null);
      return;
    }
    if (this.createOpen()) this.closeCreate();
  }

  ngOnInit(): void {
    this.api
      .get<Paginated<Article>>('/mg/stock/articles', { page: 1, size: 500 })
      .subscribe((res) => this.articles.set(res.items));
    this.api.get<Agence[]>('/mg/stock/agences').subscribe((a) => this.agences.set(a));
    this.load();
  }

  typeLabel(t: string): string {
    const map: Record<string, string> = {
      ENTREE: 'Entrée',
      SORTIE: 'Sortie',
      AJUSTEMENT: 'Ajustement',
      INVENTAIRE: 'Inventaire',
    };
    return map[t] || t;
  }

  articleLabel(id: string): string {
    const a = this.articles().find((x) => x.id === id);
    return a ? `${a.code} — ${a.designation}` : id;
  }

  agenceLabel(id: string | null): string {
    if (!id) return '—';
    return this.agences().find((a) => a.id === id)?.libelle || id;
  }

  filtered(): Mouvement[] {
    return this.mouvements();
  }

  filterParams(): Record<string, string> {
    const v = this.filters.getRawValue();
    const params: Record<string, string> = {};
    if (v.type_mouvement) params['type_mouvement'] = v.type_mouvement;
    if ((v.q || '').trim()) params['q'] = v.q.trim();
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
    const filtres = this.filterParams();
    const params: Record<string, string | number> = {
      ...filtres,
      page: this.page(),
      size: this.pageSize,
    };
    this.api.get<Paginated<Mouvement>>('/mg/stock/mouvements', params).subscribe({
      next: (res) => {
        this.filtresAffiches = filtres;
        this.mouvements.set(res.items);
        this.total.set(res.total);
      },
      error: () => {
        this.mouvements.set([]);
        this.total.set(0);
        this.erreur.set('Chargement des mouvements impossible');
      },
    });
  }

  openCreate(): void {
    this.modalErreur.set('');
    this.msg.set('');
    const first = this.articles()[0]?.id || '';
    this.form.reset({
      article_id: first,
      type_mouvement: 'ENTREE',
      quantite: 1,
      motif: '',
      agence_id: this.agences()[0]?.id || '',
    });
    this.createOpen.set(true);
  }

  closeCreate(): void {
    this.createOpen.set(false);
  }

  openView(m: Mouvement): void {
    this.viewTarget.set(m);
  }

  supprimer(m: Mouvement): void {
    this.mouvementActions.supprimer(m).subscribe(() => this.apresMutation());
  }

  apresMutation(): void {
    this.load();
    this.alertesWatcher.refresh(true);
  }

  submit(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.modalErreur.set('');
    const raw = this.form.getRawValue();
    const body = {
      article_id: raw.article_id,
      type_mouvement: raw.type_mouvement,
      quantite: raw.quantite,
      motif: raw.motif || null,
      agence_id: raw.agence_id || null,
    };
    this.api.post<Mouvement>('/mg/stock/mouvements', body).subscribe({
      next: () => {
        this.saving.set(false);
        this.msg.set('Mouvement enregistré.');
        this.closeCreate();
        this.apresMutation();
      },
      error: (err) => {
        this.modalErreur.set(err?.error?.detail || 'Mouvement refusé');
        this.saving.set(false);
      },
    });
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    const params = { ...this.filtresAffiches, format };
    this.api.download('/mg/stock/mouvements/export', params).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `mouvements-stock.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible (permission export ?)`),
    });
  }
}
