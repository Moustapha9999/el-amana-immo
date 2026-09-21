import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { PaginationComponent } from '../shared/pagination.component';

interface Article {
  id: string;
  code: string;
  designation: string;
  stock_actuel: number;
  stock_min: number;
  stock_max: number | null;
  niveau: string | null;
  uom: string;
  famille_id?: string;
  emplacement?: string | null;
  agence_id?: string | null;
}

interface Mouvement {
  id: string;
  reference: string;
  date_mouvement: string;
  type_mouvement: string;
  article_id: string;
  quantite: number;
  agence_id: string | null;
  departement: string | null;
  motif: string | null;
  observation: string | null;
  initiateur_nom?: string | null;
  article_code?: string | null;
  article_designation?: string | null;
  stock_disponible?: number | null;
}

interface BcLigneReception {
  id: string;
  description: string;
  quantite: number;
  quantite_recue: number;
  article_id: string | null;
  uom: string;
}

interface BonReception {
  id: string;
  reference: string;
  date_bc: string;
  fournisseur_raison_sociale: string | null;
  statut: string;
  lignes: BcLigneReception[];
}

interface Famille {
  id: string;
  code: string;
  libelle: string;
  sort_order?: number;
  is_active?: boolean;
}

interface Agence {
  id: string;
  libelle: string;
}

interface Alerte {
  article_id: string;
  code: string;
  designation: string;
  stock_actuel: number;
  stock_min: number;
  niveau: string;
  agence_id?: string | null;
}

interface Parametre {
  id: string;
  cle: string;
  valeur: string;
  libelle: string | null;
}

interface InventaireLigne {
  id: string;
  article_id: string;
  stock_theorique: number;
  stock_physique: number | null;
  ecart: number | null;
  observation: string | null;
  article_code?: string | null;
  article_designation?: string | null;
}

interface Inventaire {
  id: string;
  reference: string;
  libelle: string;
  date_debut: string;
  date_fin: string | null;
  statut: string;
  observation: string | null;
  agence_id?: string | null;
  lignes: InventaireLigne[];
}

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/* ───────────────── État du stock ───────────────── */

@Component({
  selector: 'bea-stock-etat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DecimalPipe, MatIconModule, ReactiveFormsModule, PaginationComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Stock</p>
          <h1>État du stock</h1>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
            <mat-icon>table_view</mat-icon> Excel
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" title="PDF">
            <mat-icon>picture_as_pdf</mat-icon> PDF
          </button>
          <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/stock-fournitures/alertes">
            <mat-icon>warning_amber</mat-icon> Voir alertes
          </a>
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="applyFilters()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Rechercher par code ou désignation…" (input)="onSearchInput()" />
        </label>
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary">
          <mat-icon>filter_list</mat-icon> Filtrer
        </button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Quantités temps réel</h2>
          <span class="bea-mg__count">{{ total() }} article(s)</span>
        </div>
        <table class="bea-mg__table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Désignation</th>
              <th>Famille</th>
              <th>Stock dispo.</th>
              <th>Min</th>
              <th>Max</th>
              <th>Emplacement</th>
              <th>Niveau</th>
              <th class="bea-mg__th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (a of articles(); track a.id) {
              <tr>
                <td><code class="bea-mg__code">{{ a.code }}</code></td>
                <td>{{ a.designation }}</td>
                <td>{{ familleLabel(a.famille_id) }}</td>
                <td>{{ a.stock_actuel | number: '1.0-3' }} {{ a.uom }}</td>
                <td>{{ a.stock_min | number: '1.0-3' }}</td>
                <td>{{ a.stock_max != null ? (a.stock_max | number: '1.0-3') : '—' }}</td>
                <td>{{ a.emplacement || '—' }}</td>
                <td>
                  <span class="bea-stock-badge" [attr.data-niveau]="a.niveau">{{ a.niveau || '—' }}</span>
                </td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="openDetail(a)">
                    <mat-icon>visibility</mat-icon>
                  </button>
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="9" class="bea-mg__empty">
                  <mat-icon>inventory_2</mat-icon>
                  <p>Aucun article actif.</p>
                </td>
              </tr>
            }
          </tbody>
        </table>
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

      @if (detail(); as d) {
        <div class="bea-mg__backdrop" (click)="closeDetail()" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true" aria-label="Détail article">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Consultation</p>
              <h2>{{ d.code }}</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeDetail()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="bea-mg__modal-body">
            <p><strong>{{ d.designation }}</strong></p>
            <p>Stock actuel : {{ d.stock_actuel | number: '1.0-3' }} {{ d.uom }}</p>
            <p>Stock minimum : {{ d.stock_min | number: '1.0-3' }}</p>
            <p>
              Niveau :
              <span class="bea-stock-badge" [attr.data-niveau]="d.niveau">{{ d.niveau || '—' }}</span>
            </p>
            @if (d.emplacement) {
              <p>Emplacement : {{ d.emplacement }}</p>
            }
          </div>
          <footer class="bea-mg__modal-foot">
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/alertes" (click)="closeDetail()">
              Voir alertes
            </a>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="closeDetail()">Fermer</button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class StockEtatComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  readonly articles = signal<Article[]>([]);
  readonly familles = signal<Famille[]>([]);
  readonly detail = signal<Article | null>(null);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly erreur = signal('');

  readonly filters = this.fb.nonNullable.group({ q: '' });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.detail()) this.closeDetail();
  }

  ngOnInit(): void {
    this.api.get<Famille[]>('/mg/stock/familles').subscribe({ next: (f) => this.familles.set(f) });
    this.load();
  }

  familleLabel(id?: string): string {
    if (!id) return '—';
    return this.familles().find((f) => f.id === id)?.libelle || '—';
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
    const q = this.filters.getRawValue().q.trim();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.pageSize,
    };
    if (q) params['q'] = q;
    this.api.get<Paginated<Article>>('/mg/stock/articles', params).subscribe({
      next: (res) => {
        this.articles.set(res.items);
        this.total.set(res.total);
      },
      error: () => {
        this.articles.set([]);
        this.total.set(0);
        this.erreur.set('Impossible de charger le stock.');
      },
    });
  }

  openDetail(a: Article): void {
    this.detail.set(a);
  }

  closeDetail(): void {
    this.detail.set(null);
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    const q = this.filters.getRawValue().q.trim();
    const params: Record<string, string> = { format };
    if (q) params['q'] = q;
    this.api.download('/mg/stock/articles/export', params).subscribe({
      next: (blob) => downloadBlob(blob, `etat-stock.${format}`),
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible (permission export ?)`),
    });
  }
}

/* ───────────────── Alertes ───────────────── */

@Component({
  selector: 'bea-stock-alertes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DecimalPipe, MatIconModule, ReactiveFormsModule],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Alertes</p>
          <h1>Alertes stock</h1>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
            <mat-icon>table_view</mat-icon> Excel
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" title="PDF">
            <mat-icon>picture_as_pdf</mat-icon> PDF
          </button>
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/stock">
            <mat-icon>inventory_2</mat-icon> État du stock
          </a>
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="$event.preventDefault()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Filtrer les alertes…" (input)="onSearchInput()" />
        </label>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Ruptures et seuils</h2>
          <span class="bea-mg__count">{{ filtered().length }} alerte(s)</span>
        </div>
        <table class="bea-mg__table">
          <thead>
            <tr>
              <th>Niveau</th>
              <th>Code</th>
              <th>Désignation</th>
              <th>Stock</th>
              <th>Minimum</th>
              <th class="bea-mg__th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (a of filtered(); track a.article_id) {
              <tr>
                <td>
                  <span class="bea-stock-badge" [attr.data-niveau]="a.niveau">{{ a.niveau }}</span>
                </td>
                <td><code class="bea-mg__code">{{ a.code }}</code></td>
                <td>{{ a.designation }}</td>
                <td>{{ a.stock_actuel | number: '1.0-3' }}</td>
                <td>{{ a.stock_min | number: '1.0-3' }}</td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="openDetail(a)">
                    <mat-icon>visibility</mat-icon>
                  </button>
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="6" class="bea-mg__empty">
                  <mat-icon>check_circle</mat-icon>
                  <p>Aucune alerte pour les critères actuels.</p>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      @if (detail(); as d) {
        <div class="bea-mg__backdrop" (click)="closeDetail()" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true" aria-label="Détail alerte">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Alerte</p>
              <h2>{{ d.code }}</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeDetail()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="bea-mg__modal-body">
            <p><strong>{{ d.designation }}</strong></p>
            <p>
              Niveau :
              <span class="bea-stock-badge" [attr.data-niveau]="d.niveau">{{ d.niveau }}</span>
            </p>
            <p>Stock actuel : {{ d.stock_actuel | number: '1.0-3' }}</p>
            <p>Stock minimum : {{ d.stock_min | number: '1.0-3' }}</p>
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="closeDetail()">Fermer</button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class StockAlertesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly alertes = signal<Alerte[]>([]);
  readonly detail = signal<Alerte | null>(null);
  readonly erreur = signal('');
  readonly q = signal('');

  readonly filters = this.fb.nonNullable.group({ q: '' });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    if (!term) return this.alertes();
    return this.alertes().filter(
      (a) => a.code.toLowerCase().includes(term) || a.designation.toLowerCase().includes(term),
    );
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.detail()) this.closeDetail();
  }

  ngOnInit(): void {
    this.load();
  }

  onSearchInput(): void {
    this.q.set(this.filters.getRawValue().q);
  }

  load(): void {
    this.erreur.set('');
    this.api.get<Alerte[]>('/mg/stock/alertes').subscribe({
      next: (rows) => this.alertes.set(rows),
      error: () => this.erreur.set('Impossible de charger les alertes.'),
    });
  }

  openDetail(a: Alerte): void {
    this.detail.set(a);
  }

  closeDetail(): void {
    this.detail.set(null);
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    this.api.download('/mg/stock/alertes/export', { format }).subscribe({
      next: (blob) => downloadBlob(blob, `alertes-stock.${format}`),
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible (permission export ?)`),
    });
  }
}

/* ───────────────── Flux (entrées / sorties) ───────────────── */

@Component({
  selector: 'bea-stock-flux',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, DecimalPipe, DatePipe, MatIconModule, PaginationComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Mouvements</p>
          <h1>{{ titre() }}</h1>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
            <mat-icon>table_view</mat-icon> Excel
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" title="PDF">
            <mat-icon>picture_as_pdf</mat-icon> PDF
          </button>
          @if (typeMouvement() === 'ENTREE') {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="openReception()">
              <mat-icon>local_shipping</mat-icon> Réception BC
            </button>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openCreate()">
            <mat-icon>add</mat-icon>
            {{ typeMouvement() === 'SORTIE' ? 'Nouvelle sortie' : 'Nouvelle entrée' }}
          </button>
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="$event.preventDefault()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Rechercher référence ou motif…" (input)="onSearchInput()" />
        </label>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
      @if (ok()) {
        <p class="bea-stock-page__ok">{{ ok() }}</p>
      }

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Historique</h2>
          <span class="bea-mg__count">{{ total() }} mouvement(s)</span>
        </div>
        <table class="bea-mg__table">
          <thead>
            <tr>
              <th>Réf.</th>
              <th>Date</th>
              <th>Article</th>
              <th>Initiateur</th>
              <th>Stock dispo.</th>
              <th>{{ typeMouvement() === 'SORTIE' ? 'Qté sortie' : 'Qté entrée' }}</th>
              <th>Motif</th>
              <th class="bea-mg__th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (m of filtered(); track m.id) {
              <tr>
                <td><code class="bea-mg__code">{{ m.reference }}</code></td>
                <td>{{ m.date_mouvement | date: 'dd/MM/yyyy HH:mm' }}</td>
                <td>{{ m.article_code || articleLabel(m.article_id) }}</td>
                <td>{{ m.initiateur_nom || '—' }}</td>
                <td>{{ m.stock_disponible != null ? (m.stock_disponible | number: '1.0-3') : '—' }}</td>
                <td>{{ m.quantite | number: '1.0-3' }}</td>
                <td>{{ m.motif || '—' }}</td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="openDetail(m)">
                    <mat-icon>visibility</mat-icon>
                  </button>
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="8" class="bea-mg__empty">
                  <mat-icon>swap_vert</mat-icon>
                  <p>Aucun mouvement.</p>
                </td>
              </tr>
            }
          </tbody>
        </table>
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
        <div
          class="bea-mg__modal"
          role="dialog"
          aria-modal="true"
          [attr.aria-label]="typeMouvement() === 'SORTIE' ? 'Nouvelle sortie' : 'Nouvelle entrée'"
        >
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Saisie</p>
              <h2>{{ typeMouvement() === 'SORTIE' ? 'Nouvelle sortie' : 'Nouvelle entrée' }}</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeCreate()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <form [formGroup]="form" (ngSubmit)="save()">
            <div class="bea-mg__modal-body">
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">
                  Article
                  <select formControlName="article_id">
                    <option value="">—</option>
                    @for (a of articles(); track a.id) {
                      <option [value]="a.id">
                        {{ a.code }} — {{ a.designation }} ({{ a.stock_actuel }})
                      </option>
                    }
                  </select>
                </label>
                <label>
                  Quantité
                  <input type="number" formControlName="quantite" min="0.001" step="0.001" />
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
                <label class="bea-mg__span2">
                  Motif
                  <input formControlName="motif" placeholder="Motif du mouvement…" />
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

      @if (detail(); as d) {
        <div class="bea-mg__backdrop" (click)="closeDetail()" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true" aria-label="Détail mouvement">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Consultation</p>
              <h2>{{ d.reference }}</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeDetail()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="bea-mg__modal-body">
            <p>Date : {{ d.date_mouvement | date: 'dd/MM/yyyy HH:mm' }}</p>
            <p>Type : {{ d.type_mouvement }}</p>
            <p>Article : {{ d.article_code || articleLabel(d.article_id) }}</p>
            <p>Initiateur : {{ d.initiateur_nom || '—' }}</p>
            <p>
              Stock disponible :
              {{ d.stock_disponible != null ? (d.stock_disponible | number: '1.0-3') : '—' }}
            </p>
            <p>
              {{ d.type_mouvement === 'SORTIE' ? 'Quantité sortie' : 'Quantité entrée' }} :
              {{ d.quantite | number: '1.0-3' }}
            </p>
            <p>Motif : {{ d.motif || '—' }}</p>
            @if (d.observation) {
              <p>Observation : {{ d.observation }}</p>
            }
            <p class="bea-stock-page__kicker" style="margin-top:0.75rem">
              Les mouvements sont immuables — modification et suppression impossibles.
            </p>
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="closeDetail()">Fermer</button>
          </footer>
        </div>
      }

      @if (receptionOpen()) {
        <div class="bea-mg__backdrop" (click)="closeReception()" role="presentation"></div>
        <div class="bea-mg__modal" role="dialog" aria-modal="true" aria-label="Réception bon de commande">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Achats → Stock</p>
              <h2>Réception bon de commande</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeReception()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="bea-mg__modal-body">
            <div class="bea-mg__grid">
              <label class="bea-mg__span2">
                Bon de commande
                <select [value]="selectedBonId()" (change)="onBonSelect($event)">
                  <option value="">— Sélectionner —</option>
                  @for (b of bonsReception(); track b.id) {
                    <option [value]="b.id">
                      {{ b.reference }} — {{ b.fournisseur_raison_sociale || 'Fournisseur' }} ({{ b.statut }})
                    </option>
                  }
                </select>
              </label>
              <label class="bea-mg__span2">
                Agence (optionnel)
                <select [value]="receptionAgenceId()" (change)="receptionAgenceId.set($any($event.target).value)">
                  <option value="">— Article —</option>
                  @for (a of agences(); track a.id) {
                    <option [value]="a.id">{{ a.libelle }}</option>
                  }
                </select>
              </label>
              <label class="bea-mg__span2">
                Motif
                <input
                  [value]="receptionMotif()"
                  (input)="receptionMotif.set($any($event.target).value)"
                  placeholder="Réception BC…"
                />
              </label>
            </div>

            @if (selectedBon(); as bon) {
              <div style="margin-top:1rem;overflow-x:auto">
                <table class="bea-mg__table">
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th>Commandé</th>
                      <th>Déjà reçu</th>
                      <th>Reste</th>
                      <th>Article</th>
                      <th>Qté à recevoir</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (l of bon.lignes; track l.id) {
                      <tr>
                        <td>{{ l.description }}</td>
                        <td>{{ l.quantite | number: '1.0-3' }}</td>
                        <td>{{ l.quantite_recue | number: '1.0-3' }}</td>
                        <td>{{ resteLigne(l) | number: '1.0-3' }}</td>
                        <td>
                          <select
                            [value]="receptionArticleOf(l)"
                            (change)="setReceptionArticle(l.id, $any($event.target).value)"
                          >
                            <option value="">—</option>
                            @for (a of articles(); track a.id) {
                              <option [value]="a.id">{{ a.code }} — {{ a.designation }}</option>
                            }
                          </select>
                        </td>
                        <td>
                          <input
                            type="number"
                            min="0"
                            step="0.001"
                            [value]="receptionQtyOf(l.id)"
                            (input)="setReceptionQty(l.id, $any($event.target).value)"
                            [attr.max]="resteLigne(l)"
                          />
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else if (bonsReception().length === 0) {
              <p class="bea-stock-page__kicker" style="margin-top:1rem">
                Aucun BC validé ou partiel en attente de réception.
              </p>
            }
            @if (modalErreur()) {
              <p class="bea-stock-page__error">{{ modalErreur() }}</p>
            }
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closeReception()">Annuler</button>
            <button
              type="button"
              class="bea-mg__btn bea-mg__btn--primary"
              [disabled]="!selectedBonId() || saving()"
              (click)="submitReception()"
            >
              Enregistrer réception
            </button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class StockFluxComponent implements OnInit {
  /** ENTREE | SORTIE */
  readonly typeMouvement = input.required<string>();
  readonly titre = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly articles = signal<Article[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly mouvements = signal<Mouvement[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly detail = signal<Mouvement | null>(null);
  readonly createOpen = signal(false);
  readonly receptionOpen = signal(false);
  readonly bonsReception = signal<BonReception[]>([]);
  readonly selectedBonId = signal('');
  readonly receptionAgenceId = signal('');
  readonly receptionMotif = signal('');
  readonly receptionQtyMap = signal<Record<string, number>>({});
  readonly receptionArticleMap = signal<Record<string, string>>({});
  readonly erreur = signal('');
  readonly ok = signal('');
  readonly modalErreur = signal('');
  readonly saving = signal(false);
  readonly q = signal('');

  readonly filters = this.fb.nonNullable.group({ q: '' });

  readonly form = this.fb.nonNullable.group({
    article_id: ['', Validators.required],
    quantite: [1, [Validators.required, Validators.min(0.001)]],
    agence_id: [''],
    motif: [''],
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    const rows = this.mouvements();
    if (!term) return rows;
    return rows.filter((m) => {
      const art = this.articleLabel(m.article_id).toLowerCase();
      return (
        m.reference.toLowerCase().includes(term) ||
        (m.motif || '').toLowerCase().includes(term) ||
        art.includes(term)
      );
    });
  });

  readonly selectedBon = computed(() => {
    const id = this.selectedBonId();
    return this.bonsReception().find((b) => b.id === id) ?? null;
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.receptionOpen()) {
      this.closeReception();
      return;
    }
    if (this.detail()) {
      this.closeDetail();
      return;
    }
    if (this.createOpen()) this.closeCreate();
  }

  ngOnInit(): void {
    this.loadArticles();
    this.api.get<Agence[]>('/mg/stock/agences').subscribe({
      next: (rows) => this.agences.set(rows),
    });
    this.reload();
  }

  loadArticles(): void {
    this.api.get<Paginated<Article>>('/mg/stock/articles', { page: 1, size: 500 }).subscribe({
      next: (res) => this.articles.set(res.items),
    });
  }

  articleLabel(id: string): string {
    const a = this.articles().find((x) => x.id === id);
    return a ? `${a.code} — ${a.designation}` : id.slice(0, 8);
  }

  onSearchInput(): void {
    this.q.set(this.filters.getRawValue().q);
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.reload();
  }

  reload(): void {
    this.api
      .get<Paginated<Mouvement>>('/mg/stock/mouvements', {
        type_mouvement: this.typeMouvement(),
        page: this.page(),
        size: this.pageSize,
      })
      .subscribe({
        next: (res) => {
          this.mouvements.set(res.items);
          this.total.set(res.total);
        },
        error: () => {
          this.mouvements.set([]);
          this.total.set(0);
          this.erreur.set('Chargement impossible.');
        },
      });
  }

  openCreate(): void {
    this.modalErreur.set('');
    this.ok.set('');
    this.form.reset({ article_id: '', quantite: 1, agence_id: '', motif: '' });
    this.createOpen.set(true);
  }

  closeCreate(): void {
    this.createOpen.set(false);
  }

  openDetail(m: Mouvement): void {
    this.detail.set(m);
  }

  closeDetail(): void {
    this.detail.set(null);
  }

  resteLigne(l: BcLigneReception): number {
    return Math.max(0, Number(l.quantite) - Number(l.quantite_recue || 0));
  }

  receptionQtyOf(ligneId: string): string {
    const v = this.receptionQtyMap()[ligneId];
    return v == null ? '' : String(v);
  }

  receptionArticleOf(l: BcLigneReception): string {
    return this.receptionArticleMap()[l.id] || l.article_id || '';
  }

  openReception(): void {
    this.modalErreur.set('');
    this.ok.set('');
    this.selectedBonId.set('');
    this.receptionAgenceId.set('');
    this.receptionMotif.set('');
    this.receptionQtyMap.set({});
    this.receptionArticleMap.set({});
    this.receptionOpen.set(true);
    this.api.get<BonReception[]>('/mg/stock/receptions/bons').subscribe({
      next: (rows) => this.bonsReception.set(rows),
      error: () => this.modalErreur.set('Impossible de charger les bons à réceptionner.'),
    });
  }

  closeReception(): void {
    this.receptionOpen.set(false);
  }

  onBonSelect(ev: Event): void {
    const id = (ev.target as HTMLSelectElement).value;
    this.selectedBonId.set(id);
    const bon = this.bonsReception().find((b) => b.id === id);
    const qty: Record<string, number> = {};
    const art: Record<string, string> = {};
    if (bon) {
      for (const l of bon.lignes) {
        const reste = this.resteLigne(l);
        if (reste > 0) qty[l.id] = reste;
        if (l.article_id) art[l.id] = l.article_id;
      }
      this.receptionMotif.set(`Réception ${bon.reference}`);
    }
    this.receptionQtyMap.set(qty);
    this.receptionArticleMap.set(art);
  }

  setReceptionQty(ligneId: string, raw: string): void {
    const n = Number(raw);
    this.receptionQtyMap.update((m) => {
      const next = { ...m };
      if (!raw || Number.isNaN(n) || n <= 0) delete next[ligneId];
      else next[ligneId] = n;
      return next;
    });
  }

  setReceptionArticle(ligneId: string, articleId: string): void {
    this.receptionArticleMap.update((m) => {
      const next = { ...m };
      if (!articleId) delete next[ligneId];
      else next[ligneId] = articleId;
      return next;
    });
  }

  submitReception(): void {
    const bonId = this.selectedBonId();
    const bon = this.selectedBon();
    if (!bonId || !bon) return;
    const qtyMap = this.receptionQtyMap();
    const artMap = this.receptionArticleMap();
    const lignes: { ligne_id: string; quantite: number; article_id?: string }[] = [];
    for (const l of bon.lignes) {
      const q = qtyMap[l.id];
      if (!q || q <= 0) continue;
      const articleId = artMap[l.id] || l.article_id || '';
      if (!articleId) {
        this.modalErreur.set(`Article requis pour « ${l.description} ».`);
        return;
      }
      const row: { ligne_id: string; quantite: number; article_id?: string } = {
        ligne_id: l.id,
        quantite: q,
      };
      if (!l.article_id || artMap[l.id]) row.article_id = articleId;
      lignes.push(row);
    }
    if (!lignes.length) {
      this.modalErreur.set('Saisir au moins une quantité à recevoir.');
      return;
    }
    this.saving.set(true);
    this.modalErreur.set('');
    const body: Record<string, unknown> = {
      lignes,
      motif: this.receptionMotif() || null,
    };
    if (this.receptionAgenceId()) body['agence_id'] = this.receptionAgenceId();
    this.api.post<{ mouvements_count: number }>(`/mg/stock/receptions/bc/${bonId}`, body).subscribe({
      next: (res) => {
        this.saving.set(false);
        this.ok.set(`Réception enregistrée (${res.mouvements_count} entrée(s)).`);
        this.closeReception();
        this.reload();
        this.loadArticles();
      },
      error: (err) => {
        this.saving.set(false);
        this.modalErreur.set(err?.error?.detail || 'Réception refusée.');
      },
    });
  }

  save(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.modalErreur.set('');
    const v = this.form.getRawValue();
    const body: Record<string, unknown> = {
      article_id: v.article_id,
      quantite: v.quantite,
      type_mouvement: this.typeMouvement(),
      motif: v.motif || null,
    };
    if (v.agence_id) body['agence_id'] = v.agence_id;
    this.api.post('/mg/stock/mouvements', body).subscribe({
      next: () => {
        this.saving.set(false);
        this.ok.set('Mouvement enregistré.');
        this.closeCreate();
        this.reload();
        this.loadArticles();
      },
      error: (err) => {
        this.saving.set(false);
        this.modalErreur.set(err?.error?.detail || 'Enregistrement refusé (stock / permission).');
      },
    });
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    this.api
      .download('/mg/stock/mouvements/export', {
        format,
        type_mouvement: this.typeMouvement(),
      })
      .subscribe({
        next: (blob) =>
          downloadBlob(blob, `${this.typeMouvement().toLowerCase()}s-stock.${format}`),
        error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible (permission export ?)`),
      });
  }
}

@Component({
  selector: 'bea-stock-entrees',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StockFluxComponent],
  template: `<bea-stock-flux typeMouvement="ENTREE" titre="Entrées de stock" />`,
})
export class StockEntreesComponent {}

@Component({
  selector: 'bea-stock-sorties',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StockFluxComponent],
  template: `<bea-stock-flux typeMouvement="SORTIE" titre="Sorties de stock" />`,
})
export class StockSortiesComponent {}

/* ───────────────── Inventaires ───────────────── */

@Component({
  selector: 'bea-stock-inventaires',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, DecimalPipe, DatePipe, MatIconModule, MgGedPanelComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Inventaire</p>
          <h1>Campagnes d’inventaire</h1>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
            <mat-icon>table_view</mat-icon> Excel
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" title="PDF">
            <mat-icon>picture_as_pdf</mat-icon> PDF
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openCreate()">
            <mat-icon>add</mat-icon> Nouvelle campagne
          </button>
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="$event.preventDefault()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="Rechercher une campagne…" (input)="onSearchInput()" />
        </label>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
      @if (ok()) {
        <p class="bea-stock-page__ok">{{ ok() }}</p>
      }

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Liste des campagnes</h2>
          <span class="bea-mg__count">{{ filtered().length }} campagne(s)</span>
        </div>
        <table class="bea-mg__table">
          <thead>
            <tr>
              <th>Réf.</th>
              <th>Libellé</th>
              <th>Début</th>
              <th>Statut</th>
              <th class="bea-mg__th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (inv of filtered(); track inv.id) {
              <tr>
                <td><code class="bea-mg__code">{{ inv.reference }}</code></td>
                <td>{{ inv.libelle }}</td>
                <td>{{ inv.date_debut | date: 'dd/MM/yyyy' }}</td>
                <td><span class="bea-stock-badge">{{ inv.statut }}</span></td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="ouvrir(inv.id, false)">
                    <mat-icon>visibility</mat-icon>
                  </button>
                  @if (inv.statut !== 'CLOTURE') {
                    <button
                      type="button"
                      class="bea-mg__icon-btn bea-mg__icon-btn--warn"
                      title="Éditer saisie"
                      (click)="ouvrir(inv.id, true)"
                    >
                      <mat-icon>edit</mat-icon>
                    </button>
                  }
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="5" class="bea-mg__empty">
                  <mat-icon>fact_check</mat-icon>
                  <p>Aucune campagne.</p>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      @if (createOpen()) {
        <div class="bea-mg__backdrop" (click)="closeCreate()" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true" aria-label="Nouvelle campagne">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Création</p>
              <h2>Nouvelle campagne</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeCreate()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <form [formGroup]="createForm" (ngSubmit)="creer()">
            <div class="bea-mg__modal-body">
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">
                  Libellé
                  <input formControlName="libelle" placeholder="Inventaire trimestriel" />
                </label>
                <label class="bea-mg__span2">
                  Agence
                  <select formControlName="agence_id">
                    <option value="">Toutes</option>
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
              <button
                type="submit"
                class="bea-mg__btn bea-mg__btn--primary"
                [disabled]="createForm.invalid || saving()"
              >
                Créer
              </button>
            </footer>
          </form>
        </div>
      }

      @if (detail(); as d) {
        <div class="bea-mg__backdrop" (click)="closeDetail()" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" aria-label="Détail inventaire">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">{{ editMode() ? 'Saisie' : 'Consultation' }}</p>
              <h2>{{ d.reference }} — {{ d.libelle }}</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeDetail()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="bea-mg__modal-body">
            <p>
              Statut : <span class="bea-stock-badge">{{ d.statut }}</span>
              — Début : {{ d.date_debut | date: 'dd/MM/yyyy' }}
              @if (d.date_fin) {
                — Fin : {{ d.date_fin | date: 'dd/MM/yyyy' }}
              }
            </p>
            <table class="bea-mg__table">
              <thead>
                <tr>
                  <th>Article</th>
                  <th>Théorique</th>
                  <th>Physique</th>
                  <th>Écart</th>
                </tr>
              </thead>
              <tbody>
                @for (l of d.lignes; track l.id) {
                  <tr>
                    <td>{{ l.article_code }} — {{ l.article_designation }}</td>
                    <td>{{ l.stock_theorique | number: '1.0-3' }}</td>
                    <td>
                      @if (d.statut === 'CLOTURE' || !editMode()) {
                        {{ l.stock_physique != null ? (l.stock_physique | number: '1.0-3') : '—' }}
                      } @else {
                        <input
                          type="number"
                          min="0"
                          step="0.001"
                          [value]="physiqueValue(l.id)"
                          (change)="setPhysique(l.id, $event)"
                        />
                      }
                    </td>
                    <td>{{ l.ecart != null ? (l.ecart | number: '1.0-3') : '—' }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="4" class="bea-mg__empty">Aucune ligne.</td>
                  </tr>
                }
              </tbody>
            </table>

            <bea-mg-ged moduleCode="stock-fournitures" entity="inventaire" [entityId]="d.id" />
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closeDetail()">Fermer</button>
            @if (d.statut !== 'CLOTURE' && editMode()) {
              <button
                type="button"
                class="bea-mg__btn bea-mg__btn--ghost"
                (click)="sauverSaisie()"
                [disabled]="saving()"
              >
                Enregistrer saisie
              </button>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="cloturer()" [disabled]="saving()">
                Clôturer &amp; ajuster stock
              </button>
            }
            @if (d.statut !== 'CLOTURE' && !editMode()) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="editMode.set(true)">
                Éditer saisie
              </button>
            }
          </footer>
        </div>
      }
    </section>
  `,
})
export class StockInventairesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly agences = signal<Agence[]>([]);
  readonly inventaires = signal<Inventaire[]>([]);
  readonly detail = signal<Inventaire | null>(null);
  readonly physiqueMap = signal<Record<string, number | ''>>({});
  readonly createOpen = signal(false);
  readonly editMode = signal(false);
  readonly erreur = signal('');
  readonly ok = signal('');
  readonly modalErreur = signal('');
  readonly saving = signal(false);
  readonly q = signal('');

  readonly filters = this.fb.nonNullable.group({ q: '' });

  readonly createForm = this.fb.nonNullable.group({
    libelle: ['', Validators.required],
    agence_id: [''],
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    if (!term) return this.inventaires();
    return this.inventaires().filter(
      (i) =>
        i.reference.toLowerCase().includes(term) ||
        i.libelle.toLowerCase().includes(term) ||
        i.statut.toLowerCase().includes(term),
    );
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.detail()) {
      this.closeDetail();
      return;
    }
    if (this.createOpen()) this.closeCreate();
  }

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/stock/agences').subscribe({ next: (a) => this.agences.set(a) });
    this.reload();
  }

  onSearchInput(): void {
    this.q.set(this.filters.getRawValue().q);
  }

  reload(): void {
    this.api.get<Inventaire[]>('/mg/stock/inventaires').subscribe({
      next: (rows) => this.inventaires.set(rows),
      error: () => this.erreur.set('Chargement inventaires impossible.'),
    });
  }

  openCreate(): void {
    this.modalErreur.set('');
    this.createForm.reset({ libelle: '', agence_id: '' });
    this.createOpen.set(true);
  }

  closeCreate(): void {
    this.createOpen.set(false);
  }

  closeDetail(): void {
    this.detail.set(null);
    this.editMode.set(false);
  }

  creer(): void {
    if (this.createForm.invalid) return;
    this.saving.set(true);
    this.modalErreur.set('');
    this.erreur.set('');
    const v = this.createForm.getRawValue();
    const body: Record<string, unknown> = { libelle: v.libelle };
    if (v.agence_id) body['agence_id'] = v.agence_id;
    this.api.post<Inventaire>('/mg/stock/inventaires', body).subscribe({
      next: (inv) => {
        this.saving.set(false);
        this.ok.set(`Campagne ${inv.reference} créée.`);
        this.closeCreate();
        this.reload();
        this.ouvrir(inv.id, true);
      },
      error: (err) => {
        this.saving.set(false);
        this.modalErreur.set(err?.error?.detail || 'Création refusée.');
      },
    });
  }

  ouvrir(id: string, edit: boolean): void {
    this.editMode.set(edit);
    this.api.get<Inventaire>(`/mg/stock/inventaires/${id}`).subscribe({
      next: (inv) => {
        this.detail.set(inv);
        const map: Record<string, number | ''> = {};
        for (const l of inv.lignes) {
          map[l.id] = l.stock_physique != null ? Number(l.stock_physique) : '';
        }
        this.physiqueMap.set(map);
      },
      error: () => this.erreur.set('Ouverture impossible.'),
    });
  }

  physiqueValue(id: string): number | '' {
    const v = this.physiqueMap()[id];
    return v === undefined ? '' : v;
  }

  setPhysique(id: string, event: Event): void {
    const raw = (event.target as HTMLInputElement).value;
    const val = raw === '' ? '' : Number(raw);
    this.physiqueMap.update((m) => ({ ...m, [id]: val }));
  }

  private saisieBody(): { id: string; stock_physique: number }[] {
    const d = this.detail();
    if (!d) return [];
    return d.lignes
      .filter((l) => {
        const v = this.physiqueMap()[l.id];
        return typeof v === 'number' && !Number.isNaN(v);
      })
      .map((l) => ({ id: l.id, stock_physique: this.physiqueMap()[l.id] as number }));
  }

  sauverSaisie(): void {
    const d = this.detail();
    if (!d) return;
    this.saving.set(true);
    this.erreur.set('');
    this.api.patch<Inventaire>(`/mg/stock/inventaires/${d.id}/saisie`, this.saisieBody()).subscribe({
      next: (inv) => {
        this.saving.set(false);
        this.ok.set('Saisie enregistrée.');
        this.detail.set(inv);
        this.reload();
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(err?.error?.detail || 'Saisie refusée.');
      },
    });
  }

  cloturer(): void {
    const d = this.detail();
    if (!d) return;
    this.saving.set(true);
    this.erreur.set('');
    this.api.patch<Inventaire>(`/mg/stock/inventaires/${d.id}/saisie`, this.saisieBody()).subscribe({
      next: () => {
        this.api.post<Inventaire>(`/mg/stock/inventaires/${d.id}/cloturer`, {}).subscribe({
          next: (inv) => {
            this.saving.set(false);
            this.ok.set('Inventaire clôturé — stock ajusté.');
            this.detail.set(inv);
            this.editMode.set(false);
            this.reload();
          },
          error: (err) => {
            this.saving.set(false);
            this.erreur.set(err?.error?.detail || 'Clôture refusée.');
          },
        });
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(err?.error?.detail || 'Saisie préalable refusée.');
      },
    });
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    this.api.download('/mg/stock/inventaires/export', { format }).subscribe({
      next: (blob) => downloadBlob(blob, `inventaires-stock.${format}`),
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible (permission export ?)`),
    });
  }
}

/* ───────────────── Paramètres ───────────────── */

@Component({
  selector: 'bea-stock-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Paramètres</p>
          <h1>Référentiels &amp; numérotation</h1>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
      @if (ok()) {
        <p class="bea-stock-page__ok">{{ ok() }}</p>
      }

      <div class="bea-mg__cards">
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Familles</h2>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openFamilleCreate()">
              <mat-icon>add</mat-icon> Nouvelle famille
            </button>
          </div>
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Libellé</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (f of familles(); track f.id) {
                <tr>
                  <td><code class="bea-mg__code">{{ f.code }}</code></td>
                  <td>{{ f.libelle }}</td>
                  <td class="bea-mg__actions-cell">
                    <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="openFamilleView(f)">
                      <mat-icon>visibility</mat-icon>
                    </button>
                    <button type="button" class="bea-mg__icon-btn" title="Éditer" (click)="openFamilleEdit(f)">
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button
                      type="button"
                      class="bea-mg__icon-btn bea-mg__icon-btn--danger"
                      title="Désactiver"
                      (click)="confirmFamilleDelete(f)"
                    >
                      <mat-icon>block</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="3" class="bea-mg__empty">
                    <mat-icon>category</mat-icon>
                    <p>Aucune famille.</p>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </section>

        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Paramètres module</h2>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openParamCreate()">
              <mat-icon>add</mat-icon> Ajouter paramètre
            </button>
          </div>
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Clé</th>
                <th>Libellé</th>
                <th>Valeur</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (p of parametres(); track p.cle) {
                <tr>
                  <td><code class="bea-mg__code">{{ p.cle }}</code></td>
                  <td>{{ p.libelle || '—' }}</td>
                  <td>{{ p.valeur }}</td>
                  <td class="bea-mg__actions-cell">
                    <button type="button" class="bea-mg__icon-btn" title="Éditer" (click)="openParamEdit(p)">
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button
                      type="button"
                      class="bea-mg__icon-btn bea-mg__icon-btn--danger"
                      title="Supprimer"
                      (click)="confirmParamDelete(p)"
                    >
                      <mat-icon>delete</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="4" class="bea-mg__empty">
                    <mat-icon>tune</mat-icon>
                    <p>Aucun paramètre.</p>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </section>
      </div>

      @if (familleModal(); as mode) {
        <div class="bea-mg__backdrop" (click)="closeFamilleModal()" role="presentation"></div>
        <div
          class="bea-mg__modal bea-mg__modal--sm"
          role="dialog"
          aria-modal="true"
          [attr.aria-label]="mode === 'create' ? 'Nouvelle famille' : mode === 'edit' ? 'Modifier famille' : 'Voir famille'"
        >
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">
                {{ mode === 'create' ? 'Création' : mode === 'edit' ? 'Modification' : 'Consultation' }}
              </p>
              <h2>
                {{ mode === 'create' ? 'Nouvelle famille' : mode === 'edit' ? 'Modifier la famille' : 'Détail famille' }}
              </h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeFamilleModal()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          @if (mode === 'view' && familleTarget(); as f) {
            <div class="bea-mg__modal-body">
              <p>Code : <code class="bea-mg__code">{{ f.code }}</code></p>
              <p>Libellé : {{ f.libelle }}</p>
            </div>
            <footer class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closeFamilleModal()">Fermer</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openFamilleEdit(f)">Éditer</button>
            </footer>
          } @else {
            <form [formGroup]="familleForm" (ngSubmit)="saveFamille()">
              <div class="bea-mg__modal-body">
                <div class="bea-mg__grid">
                  <label>
                    Code
                    <input formControlName="code" [readonly]="mode === 'edit'" />
                  </label>
                  <label>
                    Libellé
                    <input formControlName="libelle" />
                  </label>
                </div>
                @if (modalErreur()) {
                  <p class="bea-stock-page__error">{{ modalErreur() }}</p>
                }
              </div>
              <footer class="bea-mg__modal-foot">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closeFamilleModal()">
                  Annuler
                </button>
                <button
                  type="submit"
                  class="bea-mg__btn bea-mg__btn--primary"
                  [disabled]="familleForm.invalid || saving()"
                >
                  {{ mode === 'edit' ? 'Enregistrer' : 'Créer' }}
                </button>
              </footer>
            </form>
          }
        </div>
      }

      @if (paramModal(); as mode) {
        <div class="bea-mg__backdrop" (click)="closeParamModal()" role="presentation"></div>
        <div
          class="bea-mg__modal bea-mg__modal--sm"
          role="dialog"
          aria-modal="true"
          [attr.aria-label]="mode === 'create' ? 'Nouveau paramètre' : 'Modifier paramètre'"
        >
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">{{ mode === 'create' ? 'Création' : 'Modification' }}</p>
              <h2>{{ mode === 'create' ? 'Ajouter un paramètre' : 'Modifier le paramètre' }}</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeParamModal()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <form [formGroup]="paramForm" (ngSubmit)="saveParam()">
            <div class="bea-mg__modal-body">
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">
                  Clé
                  <input formControlName="cle" [readonly]="mode === 'edit'" />
                </label>
                @if (mode === 'create') {
                  <label class="bea-mg__span2">
                    Libellé
                    <input formControlName="libelle" />
                  </label>
                }
                <label class="bea-mg__span2">
                  Valeur
                  <input formControlName="valeur" />
                </label>
              </div>
              @if (modalErreur()) {
                <p class="bea-stock-page__error">{{ modalErreur() }}</p>
              }
            </div>
            <footer class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closeParamModal()">Annuler</button>
              <button
                type="submit"
                class="bea-mg__btn bea-mg__btn--primary"
                [disabled]="paramForm.invalid || saving()"
              >
                {{ mode === 'edit' ? 'Sauver' : 'Créer' }}
              </button>
            </footer>
          </form>
        </div>
      }

      @if (familleDeleteTarget(); as f) {
        <div class="bea-mg__backdrop" (click)="familleDeleteTarget.set(null)" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true">
          <header class="bea-mg__modal-head">
            <div>
              <h2>Désactiver la famille ?</h2>
              <p>{{ f.code }} — {{ f.libelle }}</p>
            </div>
          </header>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="familleDeleteTarget.set(null)">
              Annuler
            </button>
            <button
              type="button"
              class="bea-mg__btn bea-mg__btn--danger"
              (click)="doFamilleDelete()"
              [disabled]="saving()"
            >
              Désactiver
            </button>
          </footer>
        </div>
      }

      @if (paramDeleteTarget(); as p) {
        <div class="bea-mg__backdrop" (click)="paramDeleteTarget.set(null)" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true">
          <header class="bea-mg__modal-head">
            <div>
              <h2>Supprimer le paramètre ?</h2>
              <p>{{ p.cle }}{{ p.libelle ? ' — ' + p.libelle : '' }}</p>
            </div>
          </header>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="paramDeleteTarget.set(null)">
              Annuler
            </button>
            <button
              type="button"
              class="bea-mg__btn bea-mg__btn--danger"
              (click)="doParamDelete()"
              [disabled]="saving()"
            >
              Supprimer
            </button>
          </footer>
        </div>
      }
    </section>
  `,
})
export class StockParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly familles = signal<Famille[]>([]);
  readonly parametres = signal<Parametre[]>([]);
  readonly erreur = signal('');
  readonly ok = signal('');
  readonly modalErreur = signal('');
  readonly saving = signal(false);

  readonly familleModal = signal<'create' | 'edit' | 'view' | null>(null);
  readonly familleTarget = signal<Famille | null>(null);
  readonly familleDeleteTarget = signal<Famille | null>(null);

  readonly paramModal = signal<'create' | 'edit' | null>(null);
  readonly paramDeleteTarget = signal<Parametre | null>(null);

  readonly familleForm = this.fb.nonNullable.group({
    code: ['', Validators.required],
    libelle: ['', Validators.required],
  });

  readonly paramForm = this.fb.nonNullable.group({
    cle: ['', Validators.required],
    libelle: [''],
    valeur: ['', Validators.required],
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.familleDeleteTarget()) {
      this.familleDeleteTarget.set(null);
      return;
    }
    if (this.paramDeleteTarget()) {
      this.paramDeleteTarget.set(null);
      return;
    }
    if (this.familleModal()) {
      this.closeFamilleModal();
      return;
    }
    if (this.paramModal()) this.closeParamModal();
  }

  ngOnInit(): void {
    this.reloadFamilles();
    this.reloadParametres();
  }

  reloadFamilles(): void {
    this.api.get<Famille[]>('/mg/stock/familles').subscribe({
      next: (rows) => this.familles.set(rows),
      error: () => this.erreur.set('Chargement familles impossible.'),
    });
  }

  reloadParametres(): void {
    this.api.get<Parametre[]>('/mg/stock/parametres').subscribe({
      next: (rows) => this.parametres.set(rows),
      error: () => {
        /* permission ou migration absente */
      },
    });
  }

  openFamilleCreate(): void {
    this.modalErreur.set('');
    this.familleTarget.set(null);
    this.familleForm.reset({ code: '', libelle: '' });
    this.familleForm.controls.code.enable();
    this.familleModal.set('create');
  }

  openFamilleView(f: Famille): void {
    this.familleTarget.set(f);
    this.familleModal.set('view');
  }

  openFamilleEdit(f: Famille): void {
    this.modalErreur.set('');
    this.familleTarget.set(f);
    this.familleForm.reset({ code: f.code, libelle: f.libelle });
    this.familleForm.controls.code.disable();
    this.familleModal.set('edit');
  }

  closeFamilleModal(): void {
    this.familleModal.set(null);
    this.familleTarget.set(null);
    this.familleForm.controls.code.enable();
  }

  saveFamille(): void {
    if (this.familleForm.invalid) return;
    this.saving.set(true);
    this.modalErreur.set('');
    const raw = this.familleForm.getRawValue();
    const mode = this.familleModal();
    const target = this.familleTarget();

    if (mode === 'edit' && target) {
      this.api.patch<Famille>(`/mg/stock/familles/${target.id}`, { libelle: raw.libelle }).subscribe({
        next: () => {
          this.saving.set(false);
          this.ok.set('Famille mise à jour.');
          this.closeFamilleModal();
          this.reloadFamilles();
        },
        error: (err) => {
          this.saving.set(false);
          this.modalErreur.set(err?.error?.detail || 'Modification refusée.');
        },
      });
      return;
    }

    this.api.post<Famille>('/mg/stock/familles', { code: raw.code, libelle: raw.libelle }).subscribe({
      next: () => {
        this.saving.set(false);
        this.ok.set('Famille créée.');
        this.closeFamilleModal();
        this.reloadFamilles();
      },
      error: (err) => {
        this.saving.set(false);
        this.modalErreur.set(err?.error?.detail || 'Création refusée.');
      },
    });
  }

  confirmFamilleDelete(f: Famille): void {
    this.familleDeleteTarget.set(f);
  }

  doFamilleDelete(): void {
    const f = this.familleDeleteTarget();
    if (!f) return;
    this.saving.set(true);
    this.api.delete<Famille>(`/mg/stock/familles/${f.id}`).subscribe({
      next: () => {
        this.saving.set(false);
        this.familleDeleteTarget.set(null);
        this.ok.set(`Famille ${f.code} désactivée.`);
        this.reloadFamilles();
      },
      error: (err) => {
        this.saving.set(false);
        this.familleDeleteTarget.set(null);
        this.erreur.set(err?.error?.detail || 'Désactivation refusée.');
      },
    });
  }

  openParamCreate(): void {
    this.modalErreur.set('');
    this.paramForm.reset({ cle: '', libelle: '', valeur: '' });
    this.paramForm.controls.cle.enable();
    this.paramModal.set('create');
  }

  openParamEdit(p: Parametre): void {
    this.modalErreur.set('');
    this.paramForm.reset({ cle: p.cle, libelle: p.libelle || '', valeur: p.valeur });
    this.paramForm.controls.cle.disable();
    this.paramModal.set('edit');
  }

  closeParamModal(): void {
    this.paramModal.set(null);
    this.paramForm.controls.cle.enable();
  }

  saveParam(): void {
    if (this.paramForm.invalid) return;
    this.saving.set(true);
    this.modalErreur.set('');
    const raw = this.paramForm.getRawValue();
    const mode = this.paramModal();

    if (mode === 'edit') {
      this.api.patch<Parametre>(`/mg/stock/parametres/${raw.cle}`, { valeur: raw.valeur }).subscribe({
        next: (row) => {
          this.saving.set(false);
          this.ok.set(`Paramètre ${raw.cle} mis à jour.`);
          this.parametres.update((rows) => rows.map((p) => (p.cle === raw.cle ? row : p)));
          this.closeParamModal();
        },
        error: (err) => {
          this.saving.set(false);
          this.modalErreur.set(err?.error?.detail || 'Mise à jour refusée.');
        },
      });
      return;
    }

    this.api
      .post<Parametre>('/mg/stock/parametres', {
        cle: raw.cle,
        valeur: raw.valeur,
        libelle: raw.libelle || null,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.ok.set('Paramètre créé.');
          this.closeParamModal();
          this.reloadParametres();
        },
        error: (err) => {
          this.saving.set(false);
          this.modalErreur.set(err?.error?.detail || 'Création refusée.');
        },
      });
  }

  confirmParamDelete(p: Parametre): void {
    this.paramDeleteTarget.set(p);
  }

  doParamDelete(): void {
    const p = this.paramDeleteTarget();
    if (!p) return;
    this.saving.set(true);
    this.api.delete(`/mg/stock/parametres/${p.cle}`).subscribe({
      next: () => {
        this.saving.set(false);
        this.paramDeleteTarget.set(null);
        this.ok.set(`Paramètre ${p.cle} supprimé.`);
        this.reloadParametres();
      },
      error: (err) => {
        this.saving.set(false);
        this.paramDeleteTarget.set(null);
        this.erreur.set(err?.error?.detail || 'Suppression refusée.');
      },
    });
  }
}
