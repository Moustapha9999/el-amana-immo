import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { PaginationComponent } from '../shared/pagination.component';

interface Agence {
  id: string;
  libelle: string;
}
interface Article {
  id: string;
  code: string;
  designation: string;
}
interface Demande {
  id: string;
  reference: string;
  date_demande: string;
  agence_id: string;
  agence_libelle_snapshot: string | null;
  departement: string | null;
  demandeur_nom: string | null;
  fonction: string | null;
  statut: string;
  observation: string | null;
  lignes: {
    id: string;
    designation: string;
    quantite_demandee: number;
    quantite_accordee: number | null;
  }[];
}
interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

@Component({
  selector: 'bea-stock-demandes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, DatePipe, MgGedPanelComponent, PaginationComponent],
  template: `
    <section class="bea-mg">
      @if (mode() === 'list') {
        <header class="bea-mg__head">
          <div>
            <p class="bea-stock-page__kicker">Workflow</p>
            <h1>Demandes de fournitures</h1>
          </div>
          <div class="bea-mg__actions">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
              <mat-icon>table_view</mat-icon> Excel
            </button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" title="PDF">
              <mat-icon>picture_as_pdf</mat-icon> PDF
            </button>
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/stock-fournitures/demandes/nouvelle">
              <mat-icon>add</mat-icon> Nouvelle demande
            </a>
          </div>
        </header>

        <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="applyFilters()">
          <label class="bea-mg__field bea-mg__field--grow">
            <mat-icon>search</mat-icon>
            <input formControlName="q" placeholder="Rechercher par réf., agence ou demandeur…" (input)="onSearchInput()" />
          </label>
          <label class="bea-mg__field">
            <mat-icon>flag</mat-icon>
            <select formControlName="statut" (change)="applyFilters()">
              <option value="">Tous les statuts</option>
              <option value="BROUILLON">Brouillon</option>
              <option value="SOUMIS">Soumis</option>
              <option value="VISA_AGENCE">Visa agence</option>
              <option value="PREPARATION">Préparation</option>
              <option value="SERVIE">Servie</option>
              <option value="ARCHIVEE">Archivée</option>
              <option value="REJETEE">Rejetée</option>
              <option value="ANNULEE">Annulée</option>
            </select>
          </label>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary">
            <mat-icon>filter_list</mat-icon> Filtrer
          </button>
        </form>

        @if (erreur()) {
          <p class="bea-stock-page__error">{{ erreur() }}</p>
        }
        @if (msg()) {
          <p class="bea-stock-page__ok">{{ msg() }}</p>
        }

        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Liste des demandes</h2>
            <span class="bea-mg__count">{{ total() }} résultat(s)</span>
          </div>
          <div style="overflow-x:auto">
            <table class="bea-mg__table">
              <thead>
                <tr>
                  <th>Réf</th>
                  <th>Date</th>
                  <th>Agence</th>
                  <th>Demandeur</th>
                  <th>Statut</th>
                  <th class="bea-mg__th-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                @for (d of filtered(); track d.id; let i = $index) {
                  <tr [style.--i]="i">
                    <td><code class="bea-mg__code">{{ d.reference }}</code></td>
                    <td>{{ d.date_demande | date: 'shortDate' }}</td>
                    <td>{{ d.agence_libelle_snapshot || '—' }}</td>
                    <td>{{ d.demandeur_nom || '—' }}</td>
                    <td>
                      <span class="bea-stock-badge" [attr.data-statut]="d.statut">{{ statutLabel(d.statut) }}</span>
                    </td>
                    <td class="bea-mg__actions-cell">
                      <button
                        type="button"
                        class="bea-mg__icon-btn"
                        title="Voir"
                        (click)="goDetail(d.id)"
                      >
                        <mat-icon>visibility</mat-icon>
                      </button>
                      @if (d.statut === 'BROUILLON') {
                        <button
                          type="button"
                          class="bea-mg__icon-btn"
                          title="Éditer"
                          (click)="goDetail(d.id)"
                        >
                          <mat-icon>edit</mat-icon>
                        </button>
                      }
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="6">
                      <div class="bea-mg__empty">
                        <mat-icon>assignment</mat-icon>
                        <p>Aucune demande pour ces critères.</p>
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
              label="demande(s)"
              (pageChange)="goToPage($event)"
            />
          }
        </div>
      }

      @if (mode() === 'create') {
        <header class="bea-mg__head">
          <div>
            <p class="bea-stock-page__kicker">Création</p>
            <h1>Nouvelle demande</h1>
          </div>
          <div class="bea-mg__actions">
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/demandes">
              <mat-icon>arrow_back</mat-icon> Retour liste
            </a>
          </div>
        </header>

        @if (erreur()) {
          <p class="bea-stock-page__error">{{ erreur() }}</p>
        }

        <form class="bea-mg__panel" [formGroup]="form" (ngSubmit)="create()">
          <div class="bea-mg__panel-top">
            <h2>Expression de besoin</h2>
            <span class="bea-mg__count">Brouillon</span>
          </div>
          <div class="bea-mg__modal-body">
            <div class="bea-stock-fiche__banner" style="margin:0 0 1rem;border-radius:0.75rem">
              <img src="/brand/icon-bea-white.png" width="48" height="48" alt="" />
              <div>
                <strong>Banque El Amana</strong>
                <span>Service Moyens Généraux — Expression de besoin</span>
              </div>
            </div>
            <div class="bea-mg__grid">
              <label>
                Agence
                <select formControlName="agence_id">
                  @for (a of agences(); track a.id) {
                    <option [value]="a.id">{{ a.libelle }}</option>
                  }
                </select>
              </label>
              <label>
                Département
                <input formControlName="departement" />
              </label>
              <label class="bea-mg__span2">
                Fonction
                <input formControlName="fonction" />
              </label>
            </div>

            <div style="margin-top:1rem;overflow-x:auto">
              <table class="bea-mg__table" formArrayName="lignes">
                <thead>
                  <tr>
                    <th>Désignation</th>
                    <th>Qté demandée</th>
                    <th class="bea-mg__th-actions"></th>
                  </tr>
                </thead>
                <tbody>
                  @for (ctrl of lignes.controls; track $index; let i = $index) {
                    <tr [formGroupName]="i">
                      <td><input formControlName="designation" list="articles-list" /></td>
                      <td>
                        <input type="number" formControlName="quantite_demandee" min="0.001" step="0.001" />
                      </td>
                      <td class="bea-mg__actions-cell">
                        <button
                          type="button"
                          class="bea-mg__icon-btn bea-mg__icon-btn--danger"
                          title="Retirer la ligne"
                          (click)="removeLigne(i)"
                        >
                          <mat-icon>remove</mat-icon>
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <datalist id="articles-list">
              @for (a of articles(); track a.id) {
                <option [value]="a.designation"></option>
              }
            </datalist>
          </div>
          <footer class="bea-mg__modal-foot" style="padding-bottom:1.15rem">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="addLigne()">
              <mat-icon>add</mat-icon> Ligne
            </button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || saving()">
              Enregistrer brouillon
            </button>
          </footer>
        </form>
      }

      @if (mode() === 'detail' && current(); as d) {
        <header class="bea-mg__head">
          <div>
            <p class="bea-stock-page__kicker">Détail</p>
            <h1>{{ d.reference }}</h1>
          </div>
          <div class="bea-mg__actions">
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/demandes">
              <mat-icon>arrow_back</mat-icon> Retour liste
            </a>
          </div>
        </header>

        @if (erreur()) {
          <p class="bea-stock-page__error">{{ erreur() }}</p>
        }
        @if (msg()) {
          <p class="bea-stock-page__ok">{{ msg() }}</p>
        }

        <article class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Fiche demande</h2>
            <span class="bea-stock-badge" [attr.data-statut]="d.statut">{{ statutLabel(d.statut) }}</span>
          </div>
          <div class="bea-mg__modal-body">
            <div class="bea-stock-fiche__banner" style="margin:0 0 1rem;border-radius:0.75rem">
              <img src="/brand/icon-bea-white.png" width="48" height="48" alt="" />
              <div>
                <strong>{{ d.reference }}</strong>
                <span>{{ d.agence_libelle_snapshot }} — {{ statutLabel(d.statut) }}</span>
              </div>
            </div>
            <div class="bea-mg__grid">
              <label>
                Demandeur
                <input [value]="d.demandeur_nom || '—'" readonly />
              </label>
              <label>
                Date
                <input [value]="d.date_demande" readonly />
              </label>
              <label>
                Département
                <input [value]="d.departement || '—'" readonly />
              </label>
              <label>
                Fonction
                <input [value]="d.fonction || '—'" readonly />
              </label>
            </div>

            <div style="margin-top:1rem;overflow-x:auto">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th>Désignation</th>
                    <th>Qté demandée</th>
                    <th>Qté accordée</th>
                  </tr>
                </thead>
                <tbody>
                  @for (l of d.lignes; track l.id) {
                    <tr>
                      <td>{{ l.designation }}</td>
                      <td>{{ l.quantite_demandee }}</td>
                      <td>{{ l.quantite_accordee ?? '—' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>

            <div class="bea-stock-fiche__visas" style="margin-top:1rem">
              <div>Visa Agence concernée</div>
              <div>Visa Sce Moyens Généraux</div>
            </div>

            <bea-mg-ged moduleCode="stock-fournitures" entity="demande_fourniture" [entityId]="d.id" />
          </div>
          <footer class="bea-mg__modal-foot" style="flex-wrap:wrap;padding-bottom:1.15rem">
            @if (d.statut === 'BROUILLON') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('soumettre')">
                Soumettre
              </button>
            }
            @if (d.statut === 'SOUMIS') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('visa_agence')">
                Visa agence
              </button>
            }
            @if (d.statut === 'VISA_AGENCE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('visa_mg')">
                Visa MG → préparation
              </button>
            }
            @if (d.statut === 'PREPARATION' || d.statut === 'ACCORDEE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('servir')">
                Servir (sortie stock)
              </button>
            }
            @if (d.statut === 'SERVIE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="transition('archiver')">
                Archiver
              </button>
            }
            @if (
              d.statut !== 'ARCHIVEE' &&
              d.statut !== 'CLOTUREE' &&
              d.statut !== 'ANNULEE' &&
              d.statut !== 'REJETEE' &&
              d.statut !== 'SERVIE'
            ) {
              <button type="button" class="bea-mg__btn bea-mg__btn--danger" (click)="transition('rejeter')">
                Rejeter
              </button>
            }
          </footer>
        </article>
      }
    </section>
  `,
})
export class StockDemandesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly mode = signal<'list' | 'create' | 'detail'>('list');
  readonly demandes = signal<Demande[]>([]);
  readonly current = signal<Demande | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly articles = signal<Article[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly saving = signal(false);
  readonly erreur = signal('');
  readonly msg = signal('');

  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  readonly filters = this.fb.nonNullable.group({
    q: '',
    statut: '',
  });

  readonly form = this.fb.nonNullable.group({
    agence_id: ['', Validators.required],
    departement: [''],
    fonction: [''],
    lignes: this.fb.array([this.newLigne()]),
  });

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/stock/agences').subscribe((a) => {
      this.agences.set(a);
      if (a[0]) this.form.patchValue({ agence_id: a[0].id });
    });
    this.api
      .get<Paginated<Article>>('/mg/stock/articles', { page: 1, size: 500 })
      .subscribe((res) => this.articles.set(res.items));

    this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (this.router.url.endsWith('/nouvelle')) {
        this.mode.set('create');
        this.erreur.set('');
        return;
      }
      if (id) {
        this.mode.set('detail');
        this.loadOne(id);
        return;
      }
      this.mode.set('list');
      this.loadList();
    });
  }

  statutLabel(s: string): string {
    const map: Record<string, string> = {
      BROUILLON: 'Brouillon',
      SOUMIS: 'Soumis',
      VISA_AGENCE: 'Visa agence',
      PREPARATION: 'Préparation',
      ACCORDEE: 'Préparation',
      SERVIE: 'Servie',
      ARCHIVEE: 'Archivée',
      CLOTUREE: 'Archivée',
      REJETEE: 'Rejetée',
      ANNULEE: 'Annulée',
    };
    return map[s] || s;
  }

  filtered(): Demande[] {
    const q = (this.filters.value.q || '').trim().toLowerCase();
    if (!q) return this.demandes();
    return this.demandes().filter(
      (d) =>
        d.reference.toLowerCase().includes(q) ||
        (d.agence_libelle_snapshot || '').toLowerCase().includes(q) ||
        (d.demandeur_nom || '').toLowerCase().includes(q),
    );
  }

  onSearchInput(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.demandes.set([...this.demandes()]), 200);
  }

  goDetail(id: string): void {
    void this.router.navigate(['/stock-fournitures/demandes', id]);
  }

  newLigne() {
    return this.fb.nonNullable.group({
      designation: ['', Validators.required],
      quantite_demandee: [1, Validators.required],
      article_id: [null as string | null],
    });
  }

  addLigne(): void {
    this.lignes.push(this.newLigne());
  }

  removeLigne(i: number): void {
    if (this.lignes.length > 1) this.lignes.removeAt(i);
  }

  filterParams(): Record<string, string> {
    const v = this.filters.getRawValue();
    const params: Record<string, string> = {};
    if (v.statut) params['statut'] = v.statut;
    return params;
  }

  applyFilters(): void {
    this.page.set(1);
    this.loadList();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.loadList();
  }

  loadList(): void {
    this.erreur.set('');
    const params: Record<string, string | number> = {
      ...this.filterParams(),
      page: this.page(),
      size: this.pageSize,
    };
    this.api.get<Paginated<Demande>>('/mg/stock/demandes', params).subscribe({
      next: (res) => {
        this.demandes.set(res.items);
        this.total.set(res.total);
      },
      error: () => {
        this.demandes.set([]);
        this.total.set(0);
        this.erreur.set('Chargement des demandes impossible');
      },
    });
  }

  loadOne(id: string): void {
    this.erreur.set('');
    this.api.get<Demande>(`/mg/stock/demandes/${id}`).subscribe({
      next: (d) => this.current.set(d),
      error: () => this.erreur.set('Demande introuvable'),
    });
  }

  create(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.erreur.set('');
    const raw = this.form.getRawValue();
    const lignes = raw.lignes.map((l) => {
      const match = this.articles().find((a) => a.designation === l.designation);
      return {
        designation: l.designation,
        quantite_demandee: l.quantite_demandee,
        article_id: match?.id ?? null,
      };
    });
    this.api
      .post<Demande>('/mg/stock/demandes', {
        agence_id: raw.agence_id,
        departement: raw.departement || null,
        fonction: raw.fonction || null,
        lignes,
      })
      .subscribe({
        next: (d) => {
          this.saving.set(false);
          this.msg.set('Demande créée.');
          void this.router.navigate(['/stock-fournitures/demandes', d.id]);
        },
        error: (err) => {
          this.erreur.set(err?.error?.detail || 'Création refusée');
          this.saving.set(false);
        },
      });
  }

  transition(action: string): void {
    const d = this.current();
    if (!d) return;
    this.erreur.set('');
    this.api.post<Demande>(`/mg/stock/demandes/${d.id}/transition`, { action }).subscribe({
      next: (updated) => {
        this.current.set(updated);
        this.msg.set('Étape enregistrée.');
      },
      error: (err) => this.erreur.set(err?.error?.detail || 'Transition refusée'),
    });
  }

  exportFile(format: 'xlsx' | 'pdf'): void {
    const params = { ...this.filterParams(), format };
    this.api.download('/mg/stock/demandes/export', params).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `demandes-stock.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible (permission export ?)`),
    });
  }
}
