import { DatePipe } from '@angular/common';
import { QuantitePipe } from '../shared/montant.pipe';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  OnInit,
  computed,
  inject,
  input,
  signal,
  viewChild,
  viewChildren,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { PaginationComponent } from '../shared/pagination.component';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { FeedbackService } from '../core/feedback/feedback.service';
import {
  StockMouvementActions,
  StockMouvementEditComponent,
  StockMouvementRow,
  StockMouvementViewComponent,
} from './stock-mouvement-edit.component';
import { StockAlertesWatcherService } from './stock-alertes-watcher.service';
import { StockMotifsSortiePanelComponent } from './stock-motifs-sortie-panel.component';
import { StockSortieFormComponent } from './stock-sortie-form.component';
import { StockEntreeFormComponent } from './stock-entree-form.component';

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

interface Mouvement extends StockMouvementRow {
  departement: string | null;
  initiateur_nom?: string | null;
  stock_disponible?: number | null;
  destination_type?: 'DEPARTEMENT' | 'AGENCE' | null;
  destination_libelle?: string | null;
  demandeur_nom?: string | null;
  provenance_type?: string | null;
  provenance_libelle?: string | null;
  piece_reference?: string | null;
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

interface Parametre {
  id: string;
  cle: string;
  valeur: string;
  libelle: string | null;
}

interface PeriodeStock {
  id: string;
  libelle: string;
  annee: number;
  mois: number;
  statut: string;
  date_debut: string;
  date_fin: string;
  stock_initial?: number;
  entrees?: number;
  sorties?: number;
  ajustements?: number;
  stock_theorique?: number;
  articles?: number;
  cloture_message?: string | null;
}

interface SoldePeriode {
  article_code: string | null;
  article_designation: string | null;
  stock_initial: number;
  entrees: number;
  sorties: number;
  ajustements: number;
  stock_theorique: number;
  stock_final: number | null;
}

interface CloturePreview {
  periode?: { libelle?: string };
  articles: number;
  stock_final: number;
  articles_avec_ecarts: number;
  ajustements: number;
  periode_suivante: string;
  anomalies: string[];
  bloquant: boolean;
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
  imports: [RouterLink, QuantitePipe, MatIconModule, ReactiveFormsModule, PaginationComponent],
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


      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Quantités temps réel</h2>
          <span class="bea-mg__count">{{ total() }} article(s)</span>
        </div>
        <div class="bea-mg__table-scroll">
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
                <td>{{ a.stock_actuel | quantite }} {{ a.uom }}</td>
                <td>{{ a.stock_min | quantite }}</td>
                <td>{{ a.stock_max | quantite }}</td>
                <td>{{ a.emplacement || '—' }}</td>
                <td>
                  <span class="bea-stock-badge" [attr.data-niveau]="a.niveau">{{ a.niveau || '—' }}</span>
                </td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="openDetail(a)">
                    <mat-icon>visibility</mat-icon>
                  </button>
                  <a class="bea-mg__icon-btn" title="Modifier l’article (seuils, emplacement…)" [routerLink]="['/stock-fournitures/articles', a.id]">
                    <mat-icon>edit</mat-icon>
                  </a>                </td>
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

      @if (detail(); as d) {
        <div class="bea-mg__backdrop" (click)="closeDetail()" role="presentation"></div>
        <div class="bea-mg__modal bea-stock-view" role="dialog" aria-modal="true" aria-labelledby="stock-view-title">
          <header class="bea-mg__modal-head">
            <div class="bea-stock-view__head">
              <span class="bea-stock-view__avatar"><mat-icon>inventory_2</mat-icon></span>
              <div>
                <p class="bea-stock-page__kicker">Consultation · <code>{{ d.code }}</code></p>
                <h2 id="stock-view-title">{{ d.designation }}</h2>
              </div>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closeDetail()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </header>
          <div class="bea-mg__modal-body bea-stock-view__body">
            <div class="bea-stock-view__kpis">
              <div class="bea-stock-view__kpi bea-stock-view__kpi--main" [attr.data-niveau]="d.niveau">
                <span>Stock actuel</span>
                <strong>{{ d.stock_actuel | quantite }} <small>{{ d.uom }}</small></strong>
                <span class="bea-stock-badge" [attr.data-niveau]="d.niveau">{{ d.niveau || '—' }}</span>
              </div>
              <div class="bea-stock-view__kpi">
                <span>Minimum</span>
                <strong>{{ d.stock_min | quantite }}</strong>
              </div>
              <div class="bea-stock-view__kpi">
                <span>Maximum</span>
                <strong>{{ d.stock_max != null ? (d.stock_max | quantite) : '—' }}</strong>
              </div>
            </div>

            <div class="bea-stock-view__gauge" [attr.data-niveau]="d.niveau">
              <div class="bea-stock-view__gauge-track">
                <i [style.width.%]="gaugePct(d)"></i>
                @if (minPct(d) !== null) {
                  <b [style.left.%]="minPct(d)" title="Seuil minimum"></b>
                }
              </div>
              <div class="bea-stock-view__gauge-legend">
                <span>0</span>
                <span>Seuil min. {{ d.stock_min | quantite }}</span>
                <span>{{ gaugeMax(d) | quantite }}</span>
              </div>
            </div>

            <dl class="bea-stock-view__infos">
              <div><dt><mat-icon>category</mat-icon> Famille</dt><dd>{{ familleLabel(d.famille_id) }}</dd></div>
              <div><dt><mat-icon>place</mat-icon> Emplacement</dt><dd>{{ d.emplacement || '—' }}</dd></div>
              <div><dt><mat-icon>straighten</mat-icon> Unité</dt><dd>{{ d.uom }}</dd></div>
            </dl>
          </div>
          <footer class="bea-mg__modal-foot bea-stock-view__foot">
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/alertes" (click)="closeDetail()">
              <mat-icon>warning_amber</mat-icon> Alertes
            </a>
            <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/stock-fournitures/articles', d.id]" (click)="closeDetail()">
              <mat-icon>edit</mat-icon> Ouvrir la fiche
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
  readonly erreur = feedbackSignal('error', '');

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

  gaugeMax(a: Article): number {
    const max = Number(a.stock_max) || 0;
    if (max > 0) return Math.max(max, Number(a.stock_actuel) || 0);
    return Math.max((Number(a.stock_min) || 0) * 2, Number(a.stock_actuel) || 0, 1);
  }

  gaugePct(a: Article): number {
    return Math.min(100, Math.round(((Number(a.stock_actuel) || 0) / this.gaugeMax(a)) * 100));
  }

  minPct(a: Article): number | null {
    const min = Number(a.stock_min) || 0;
    return min > 0 ? Math.min(100, Math.round((min / this.gaugeMax(a)) * 100)) : null;
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

/* ───────────────── Flux (entrées / sorties) ───────────────── */

@Component({
  selector: 'bea-stock-flux',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    QuantitePipe,
    DatePipe,
    MatIconModule,
    PaginationComponent,
    StockMouvementEditComponent,
    StockMouvementViewComponent,
    StockSortieFormComponent,
    StockEntreeFormComponent,
    RouterLink,
  ],
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
          } @else if (typeMouvement() === 'SORTIE') {
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/rapports/consommation_destinataires">
              <mat-icon>leaderboard</mat-icon> Consommation
            </a>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="typeMouvement() === 'SORTIE' ? sortieOpen.set(true) : entreeOpen.set(true)">
            <mat-icon>add</mat-icon>
            {{ typeMouvement() === 'SORTIE' ? 'Nouvelle sortie' : 'Nouvelle entrée' }}
          </button>
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="$event.preventDefault()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input
            formControlName="q"
            [placeholder]="typeMouvement() === 'SORTIE' ? 'Rechercher référence, article, motif, demandeur…' : 'Rechercher référence, article, fournisseur, n° de pièce…'"
            (input)="onSearchInput()"
          />
        </label>
        @if (typeMouvement() === 'SORTIE') {
          <label class="bea-mg__field">
            <mat-icon>alt_route</mat-icon>
            <select formControlName="destination_type" (change)="goToPage(1)" aria-label="Destination">
              <option value="">Toutes destinations</option>
              <option value="DEPARTEMENT">Département / Service</option>
              <option value="AGENCE">Agence</option>
            </select>
          </label>
        } @else {
          <label class="bea-mg__field">
            <mat-icon>input</mat-icon>
            <select formControlName="provenance_type" (change)="goToPage(1)" aria-label="Provenance">
              <option value="">Toutes provenances</option>
              <option value="FOURNISSEUR">Fournisseur</option>
              <option value="RETOUR_DEPARTEMENT">Retour département</option>
              <option value="RETOUR_AGENCE">Retour agence</option>
              <option value="AUTRE">Autre</option>
            </select>
          </label>
        }
      </form>


      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Historique</h2>
          <span class="bea-mg__count">{{ total() }} mouvement(s)</span>
        </div>
        <div class="bea-mg__table-scroll">
        <table class="bea-mg__table">
          <thead>
            <tr>
              <th>Réf.</th>
              <th>Date</th>
              <th>Article</th>
              <th>{{ typeMouvement() === 'SORTIE' ? 'Sorti par' : 'Reçu par' }}</th>
              @if (typeMouvement() === 'SORTIE') {
                <th>Destination</th>
                <th>Demandé par</th>
              } @else {
                <th>Provenance</th>
              }
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
                @if (typeMouvement() === 'SORTIE') {
                  <td>
                    @if (m.destination_type) {
                      <mat-icon style="font-size:1rem;width:1rem;height:1rem;vertical-align:-0.15rem;color:#64748b" [title]="m.destination_type === 'AGENCE' ? 'Agence' : 'Département / Service'">
                        {{ m.destination_type === 'AGENCE' ? 'storefront' : 'account_tree' }}
                      </mat-icon>
                    }
                    {{ m.destination_libelle || '—' }}
                  </td>
                  <td>{{ m.demandeur_nom || '—' }}</td>
                } @else {
                  <td>
                    {{ m.provenance_libelle || (m.source_type === 'achat_reception' ? 'Réception BC' : '—') }}
                    @if (m.piece_reference) { <small style="display:block;color:#64748b">{{ m.piece_reference }}</small> }
                  </td>
                }
                <td>{{ m.stock_disponible | quantite }}</td>
                <td>{{ m.quantite | quantite }}</td>
                <td>{{ m.motif || '—' }}</td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="openDetail(m)">
                    <mat-icon>visibility</mat-icon>
                  </button>
                  <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editTarget.set(m)">
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button
                    type="button"
                    class="bea-mg__icon-btn bea-mg__icon-btn--danger"
                    [title]="m.quantite_modifiable ? 'Supprimer' : mouvementActions.peutSupprimer(m) ? 'Suppression administrateur (motif requis)' : 'Suppression impossible (période clôturée ou mouvement de workflow)'"
                    [disabled]="!mouvementActions.peutSupprimer(m)"
                    (click)="supprimer(m)"
                  >
                    <mat-icon>delete</mat-icon>
                  </button>
                </td>
              </tr>
            } @empty {
              <tr>
                <td [attr.colspan]="typeMouvement() === 'SORTIE' ? 10 : 9" class="bea-mg__empty">
                  <mat-icon>swap_vert</mat-icon>
                  <p>Aucun mouvement.</p>
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

      @if (entreeOpen()) {
        <bea-stock-entree-form (closed)="entreeOpen.set(false)" (saved)="entreeOpen.set(false); apresMutation()" />
      }

      @if (sortieOpen()) {
        <bea-stock-sortie-form (closed)="sortieOpen.set(false)" (saved)="sortieOpen.set(false); apresMutation()" />
      }

      @if (detail(); as d) {
        <bea-stock-mouvement-view
          [mouvement]="d"
          [agence]="agenceLabel(d.agence_id)"
          [peutSupprimer]="mouvementActions.peutSupprimer(d)"
          (closed)="closeDetail()"
          (modifier)="closeDetail(); editTarget.set(d)"
          (supprimer)="closeDetail(); supprimer(d)"
        />
      }

      @if (editTarget(); as e) {
        <bea-stock-mouvement-edit
          [mouvement]="e"
          [agences]="agences()"
          (closed)="editTarget.set(null)"
          (saved)="onEdited()"
        />
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
              <div class="bea-mg__table-scroll" style="margin-top:1rem">
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
                        <td>{{ l.quantite | quantite }}</td>
                        <td>{{ l.quantite_recue | quantite }}</td>
                        <td>{{ resteLigne(l) | quantite }}</td>
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
                            step="1"
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
  protected readonly mouvementActions = inject(StockMouvementActions);
  private readonly alertesWatcher = inject(StockAlertesWatcherService);

  readonly articles = signal<Article[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly mouvements = signal<Mouvement[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly detail = signal<Mouvement | null>(null);
  readonly editTarget = signal<Mouvement | null>(null);
  readonly entreeOpen = signal(false);
  readonly sortieOpen = signal(false);
  private readonly sortieForm = viewChild(StockSortieFormComponent);
  private readonly entreeForm = viewChild(StockEntreeFormComponent);
  readonly hasUnsavedChanges = (): boolean =>
    (this.sortieForm()?.hasUnsavedChanges() ?? false) || (this.entreeForm()?.hasUnsavedChanges() ?? false);
  readonly receptionOpen = signal(false);
  readonly bonsReception = signal<BonReception[]>([]);
  readonly selectedBonId = signal('');
  readonly receptionAgenceId = signal('');
  readonly receptionMotif = signal('');
  readonly receptionQtyMap = signal<Record<string, number>>({});
  readonly receptionArticleMap = signal<Record<string, string>>({});
  readonly erreur = feedbackSignal('error', '');
  readonly ok = feedbackSignal('success', '');
  readonly modalErreur = signal('');
  readonly saving = signal(false);
  readonly q = signal('');

  readonly filters = this.fb.nonNullable.group({ q: '', destination_type: '', provenance_type: '' });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    const rows = this.mouvements();
    if (!term) return rows;
    return rows.filter((m) => {
      const art = this.articleLabel(m.article_id).toLowerCase();
      return (
        m.reference.toLowerCase().includes(term) ||
        (m.motif || '').toLowerCase().includes(term) ||
        (m.demandeur_nom || '').toLowerCase().includes(term) ||
        (m.destination_libelle || '').toLowerCase().includes(term) ||
        (m.provenance_libelle || '').toLowerCase().includes(term) ||
        (m.piece_reference || '').toLowerCase().includes(term) ||
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
    if (this.detail()) this.closeDetail();
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

  agenceLabel(id: string | null): string | null {
    if (!id) return null;
    return this.agences().find((a) => a.id === id)?.libelle ?? null;
  }

  onSearchInput(): void {
    this.q.set(this.filters.getRawValue().q);
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.reload();
  }

  private filtresServeur(): Record<string, string> {
    const params: Record<string, string> = { type_mouvement: this.typeMouvement() };
    const { destination_type, provenance_type } = this.filters.getRawValue();
    if (destination_type && this.typeMouvement() === 'SORTIE') params['destination_type'] = destination_type;
    if (provenance_type && this.typeMouvement() === 'ENTREE') params['provenance_type'] = provenance_type;
    return params;
  }

  reload(): void {
    this.api
      .get<Paginated<Mouvement>>('/mg/stock/mouvements', {
        ...this.filtresServeur(),
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

  openDetail(m: Mouvement): void {
    this.detail.set(m);
  }

  closeDetail(): void {
    this.detail.set(null);
  }

  onEdited(): void {
    this.editTarget.set(null);
    this.apresMutation();
  }

  supprimer(m: Mouvement): void {
    this.mouvementActions.supprimer(m).subscribe(() => this.apresMutation());
  }

  protected apresMutation(): void {
    this.reload();
    this.loadArticles();
    this.alertesWatcher.refresh(true);
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
        this.apresMutation();
      },
      error: (err) => {
        this.saving.set(false);
        this.modalErreur.set(err?.error?.detail || 'Réception refusée.');
      },
    });
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    const params: Record<string, string> = { ...this.filtresServeur(), format };
    if (this.q().trim()) params['q'] = this.q().trim();
    this.api
      .download('/mg/stock/mouvements/export', params)
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
export class StockEntreesComponent {
  private readonly flux = viewChild(StockFluxComponent);
  readonly hasUnsavedChanges = (): boolean => this.flux()?.hasUnsavedChanges() ?? false;
}

@Component({
  selector: 'bea-stock-sorties',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StockFluxComponent],
  template: `<bea-stock-flux typeMouvement="SORTIE" titre="Sorties de stock" />`,
})
export class StockSortiesComponent {
  private readonly flux = viewChild(StockFluxComponent);
  readonly hasUnsavedChanges = (): boolean => this.flux()?.hasUnsavedChanges() ?? false;
}

/* ───────────────── Paramètres ───────────────── */

@Component({
  selector: 'bea-stock-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, RouterLink, QuantitePipe, StockMotifsSortiePanelComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Paramètres</p>
          <h1>Référentiels &amp; numérotation</h1>
        </div>
      </header>


      <section class="bea-mg__panel" style="margin-bottom:1rem">
        <div class="bea-mg__panel-top">
          <h2>Périodes de stock</h2>
          <span class="bea-mg__count">{{ periodes().length }} période(s)</span>
        </div>
        @if (periodeActive(); as pa) {
          <div class="bea-stock-period-banner" [attr.data-statut]="pa.statut">
            <div class="bea-stock-period-banner__copy">
              <span class="bea-stock-period-banner__label">Période active</span>
              <strong>{{ pa.libelle }}</strong>
            </div>
            <span class="bea-stock-badge" [attr.data-niveau]="pa.statut === 'OUVERTE' ? 'normal' : 'epuise'">
              {{ pa.statut === 'OUVERTE' ? 'Ouverte' : 'Clôturée' }}
            </span>
          </div>
          @if (pa.cloture_message) {
            <a class="bea-stock-period-alert" routerLink="/stock-fournitures/inventaires">
              <mat-icon>event_busy</mat-icon>
              <span>{{ pa.cloture_message }}</span>
            </a>
          }
        }
        <div class="bea-mg__table-scroll">
        <table class="bea-mg__table">
          <thead>
            <tr>
              <th>Période</th>
              <th>Du</th>
              <th>Au</th>
              <th>Statut</th>
              <th class="bea-mg__th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (p of periodes(); track p.id) {
              <tr>
                <td>{{ p.libelle }}</td>
                <td>{{ p.date_debut }}</td>
                <td>{{ p.date_fin }}</td>
                <td>
                  <span class="bea-stock-badge" [attr.data-niveau]="p.statut === 'OUVERTE' ? 'normal' : 'epuise'">
                    {{ p.statut === 'OUVERTE' ? 'Ouverte' : 'Clôturée' }}
                  </span>
                </td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Voir les soldes" (click)="openPeriodeView(p)">
                    <mat-icon>visibility</mat-icon>
                  </button>
                  @if (p.statut === 'OUVERTE') {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openCloture(p)">
                      Clôturer
                    </button>
                  }
                  @if (p.statut === 'CLOTUREE') {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="openReopen(p)">
                      Réouvrir
                    </button>
                  }
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="5" class="bea-mg__empty">Aucune période (ouverte au premier accès).</td>
              </tr>
            }
          </tbody>
        </table>
        </div>
      </section>

      <div class="bea-mg__cards">
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Familles</h2>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openFamilleCreate()">
              <mat-icon>add</mat-icon> Nouvelle famille
            </button>
          </div>
          <div class="bea-mg__table-scroll">
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
          </div>
        </section>

        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Paramètres module</h2>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openParamCreate()">
              <mat-icon>add</mat-icon> Ajouter paramètre
            </button>
          </div>
          <div class="bea-mg__table-scroll">
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
          </div>
        </section>
      </div>

      <bea-stock-motifs-sortie-panel sens="SORTIE" />
      <bea-stock-motifs-sortie-panel sens="ENTREE" />

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

      @if (cloturePreview(); as prev) {
        <div class="bea-mg__backdrop" (click)="cloturePreview.set(null)" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Clôture mensuelle</p>
              <h2>{{ prev.periode?.libelle }}</h2>
            </div>
          </header>
          <div class="bea-mg__modal-body">
            <p>Articles : {{ prev.articles }}</p>
            <p>Stock final : {{ prev.stock_final | quantite }}</p>
            <p>Articles avec écarts : {{ prev.articles_avec_ecarts }}</p>
            <p>Ajustements : {{ prev.ajustements }}</p>
            <p>Période suivante : {{ prev.periode_suivante }}</p>
            @if (prev.anomalies.length) {
              <p class="bea-stock-page__error">{{ prev.anomalies.join(' ; ') }}</p>
            }
            @if (modalErreur()) {
              <p class="bea-stock-page__error">{{ modalErreur() }}</p>
            }
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="cloturePreview.set(null)">
              Annuler
            </button>
            <button
              type="button"
              class="bea-mg__btn bea-mg__btn--primary"
              [disabled]="saving() || prev.bloquant"
              (click)="confirmCloture()"
            >
              Confirmer la clôture
            </button>
          </footer>
        </div>
      }

      @if (viewTarget(); as vp) {
        <div class="bea-mg__backdrop" (click)="closePeriodeView()" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" aria-label="Soldes de période">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Contrôle période</p>
              <h2>{{ vp.libelle }}</h2>
            </div>
            <span class="bea-stock-badge" [attr.data-niveau]="vp.statut === 'OUVERTE' ? 'normal' : 'epuise'">
              {{ vp.statut === 'OUVERTE' ? 'Ouverte' : 'Clôturée' }}
            </span>
          </header>
          <div class="bea-mg__modal-body">
            <p class="bea-stock-period-banner__label" style="margin:0 0 0.65rem">
              Du {{ vp.date_debut }} au {{ vp.date_fin }} · {{ viewSoldes().length }} article(s)
            </p>
            @if (viewLoading()) {
              <p>Chargement des soldes…</p>
            } @else {
              <div class="bea-mg__table-scroll" style="max-height:min(22rem, 50vh);border:1px solid #eef2f7;border-radius:0.6rem">
                <table class="bea-mg__table">
                  <thead>
                    <tr>
                      <th>Article</th>
                      <th>Réf.</th>
                      <th>Initial</th>
                      <th>Entrées</th>
                      <th>Sorties</th>
                      <th>Théorique</th>
                      <th>Final</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (s of viewSoldes(); track s.article_code) {
                      <tr>
                        <td>{{ s.article_designation }}</td>
                        <td><code class="bea-mg__code">{{ s.article_code }}</code></td>
                        <td>{{ s.stock_initial | quantite }}</td>
                        <td>{{ s.entrees | quantite }}</td>
                        <td>{{ s.sorties | quantite }}</td>
                        <td>{{ s.stock_theorique | quantite }}</td>
                        <td><strong>{{ s.stock_final | quantite }}</strong></td>
                      </tr>
                    } @empty {
                      <tr>
                        <td colspan="7" class="bea-mg__empty">Aucun solde sur cette période.</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
            @if (vp.statut === 'OUVERTE') {
              <p style="margin:0.85rem 0 0;font-size:0.86rem;color:#334155">
                Période ouverte : corrigez les mouvements dans
                <a routerLink="/stock-fournitures/entrees">Entrées</a>,
                <a routerLink="/stock-fournitures/sorties">Sorties</a>
                ou le <a routerLink="/stock-fournitures/journal">journal</a>
                (dates de {{ vp.libelle }}).
              </p>
            }
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closePeriodeView()">Fermer</button>
            @if (vp.statut === 'CLOTUREE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openReopen(vp)">
                Réouvrir pour modifier
              </button>
            }
            @if (vp.statut === 'OUVERTE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openCloture(vp)">
                Clôturer
              </button>
            }
          </footer>
        </div>
      }

      @if (reopenTarget(); as rp) {
        <div class="bea-mg__backdrop" (click)="reopenTarget.set(null)" role="presentation"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true">
          <header class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Admin</p>
              <h2>Réouvrir {{ rp.libelle }}</h2>
            </div>
          </header>
          <form [formGroup]="reopenForm" (ngSubmit)="confirmReopen()">
            <div class="bea-mg__modal-body">
              @if (periodeActive(); as cur) {
                @if (cur.id !== rp.id) {
                  <p class="bea-stock-period-alert" style="margin:0 0 0.85rem">
                    <mat-icon>lock</mat-icon>
                    <span>{{ cur.libelle }} sera verrouillée (mouvements conservés). Vous pourrez y revenir ensuite.</span>
                  </p>
                }
              }
              <p style="margin:0 0 0.75rem;font-size:0.86rem;color:#334155">
                Après réouverture, consultez les soldes puis corrigez via Entrées / Sorties / Journal.
              </p>
              <label class="bea-mg__span2">
                Motif (obligatoire)
                <input formControlName="motif" placeholder="Contrôle / correction de saisie" />
              </label>
              @if (modalErreur()) {
                <p class="bea-stock-page__error">{{ modalErreur() }}</p>
              }
            </div>
            <footer class="bea-mg__modal-foot">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reopenTarget.set(null)">
                Annuler
              </button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="reopenForm.invalid || saving()">
                Réouvrir
              </button>
            </footer>
          </form>
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
  private readonly motifsPanels = viewChildren(StockMotifsSortiePanelComponent);
  readonly hasUnsavedChanges = (): boolean => this.motifsPanels().some((p) => p.hasUnsavedChanges());

  readonly familles = signal<Famille[]>([]);
  readonly parametres = signal<Parametre[]>([]);
  readonly periodes = signal<PeriodeStock[]>([]);
  readonly periodeActive = signal<PeriodeStock | null>(null);
  readonly viewTarget = signal<PeriodeStock | null>(null);
  readonly viewSoldes = signal<SoldePeriode[]>([]);
  readonly viewLoading = signal(false);
  readonly cloturePreview = signal<CloturePreview | null>(null);
  readonly clotureId = signal<string | null>(null);
  readonly reopenTarget = signal<PeriodeStock | null>(null);
  readonly erreur = feedbackSignal('error', '');
  readonly ok = feedbackSignal('success', '');
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

  readonly reopenForm = this.fb.nonNullable.group({
    motif: ['', Validators.required],
  });

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.reopenTarget()) {
      this.reopenTarget.set(null);
      return;
    }
    if (this.viewTarget()) {
      this.closePeriodeView();
      return;
    }
    if (this.cloturePreview()) {
      this.cloturePreview.set(null);
      return;
    }
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
    this.reloadPeriodes();
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

  reloadPeriodes(): void {
    this.api.get<PeriodeStock[]>('/mg/stock/periodes').subscribe({
      next: (rows) => this.periodes.set(rows),
      error: () => this.periodes.set([]),
    });
    this.api.get<PeriodeStock>('/mg/stock/periodes/active').subscribe({
      next: (p) => this.periodeActive.set(p),
      error: () => this.periodeActive.set(null),
    });
  }

  openCloture(p: PeriodeStock): void {
    this.modalErreur.set('');
    this.clotureId.set(p.id);
    this.api.get<CloturePreview>(`/mg/stock/periodes/${p.id}/preview-cloture`).subscribe({
      next: (prev) => this.cloturePreview.set(prev),
      error: (err) => this.erreur.set(err?.error?.detail || 'Prévisualisation clôture impossible.'),
    });
  }

  confirmCloture(): void {
    const id = this.clotureId();
    if (!id) return;
    this.saving.set(true);
    this.modalErreur.set('');
    this.api.post(`/mg/stock/periodes/${id}/cloturer`, {}).subscribe({
      next: () => {
        this.saving.set(false);
        this.cloturePreview.set(null);
        this.ok.set('Période clôturée — stock reporté sans entrée artificielle.');
        this.reloadPeriodes();
      },
      error: (err) => {
        this.saving.set(false);
        this.modalErreur.set(err?.error?.detail || 'Clôture refusée.');
      },
    });
  }

  openPeriodeView(p: PeriodeStock): void {
    this.viewTarget.set(p);
    this.viewSoldes.set([]);
    this.viewLoading.set(true);
    this.api
      .get<{ items: SoldePeriode[] }>(`/mg/stock/periodes/${p.id}/soldes`, { page: 1, size: 500 })
      .subscribe({
        next: (res) => {
          this.viewSoldes.set(res.items || []);
          this.viewLoading.set(false);
        },
        error: () => {
          this.viewSoldes.set([]);
          this.viewLoading.set(false);
          this.erreur.set('Impossible de charger les soldes de la période.');
        },
      });
  }

  closePeriodeView(): void {
    this.viewTarget.set(null);
    this.viewSoldes.set([]);
  }

  openReopen(p: PeriodeStock): void {
    this.modalErreur.set('');
    this.reopenForm.reset({ motif: '' });
    this.reopenTarget.set(p);
  }

  confirmReopen(): void {
    const p = this.reopenTarget();
    if (!p || this.reopenForm.invalid) return;
    this.saving.set(true);
    this.modalErreur.set('');
    this.api
      .post<{ libelle?: string; periode_verrouillee?: { libelle?: string; mouvements?: number } }>(
        `/mg/stock/periodes/${p.id}/rouvrir`,
        this.reopenForm.getRawValue(),
      )
      .subscribe({
        next: (res) => {
          this.saving.set(false);
          this.reopenTarget.set(null);
          const locked = res.periode_verrouillee;
          this.ok.set(
            locked?.libelle
              ? `${p.libelle} rouverte — ${locked.libelle} verrouillée (${locked.mouvements || 0} mvt conservés).`
              : `${p.libelle} rouverte. Vous pouvez corriger les mouvements.`,
          );
          this.reloadPeriodes();
          this.openPeriodeView({ ...p, statut: 'OUVERTE' });
        },
        error: (err) => {
          this.saving.set(false);
          this.modalErreur.set(err?.error?.detail || 'Réouverture refusée (permission / motif).');
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
