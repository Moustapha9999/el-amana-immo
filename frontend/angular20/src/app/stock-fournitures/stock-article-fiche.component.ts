import { DatePipe } from '@angular/common';
import { QuantitePipe } from '../shared/montant.pipe';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';

interface Famille {
  id: string;
  code: string;
  libelle: string;
}
interface Agence {
  id: string;
  libelle: string;
}
interface ArticleFiche {
  id: string;
  code: string;
  designation: string;
  famille_id: string;
  famille_libelle: string | null;
  uom: string;
  stock_actuel: number;
  stock_min: number;
  stock_max: number | null;
  agence_id: string | null;
  agence_libelle: string | null;
  emplacement: string | null;
  is_active: boolean;
  niveau: string | null;
  stock_initial: number;
  total_entrees: number;
  total_sorties: number;
  total_ajustements: number;
  total_inventaires: number;
}
interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}
interface Mouvement {
  id: string;
  reference: string;
  date_mouvement: string;
  type_mouvement: string;
  quantite: number;
  motif: string | null;
  initiateur_nom?: string | null;
}
interface Demande {
  id: string;
  reference: string;
  date_demande: string;
  statut: string;
  demandeur_nom: string | null;
  agence_libelle_snapshot: string | null;
}

type Tab = 'infos' | 'stock' | 'mouvements' | 'demandes' | 'documents';

@Component({
  selector: 'bea-stock-article-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, QuantitePipe, DatePipe, MgGedPanelComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Fiche article</p>
          @if (fiche(); as a) {
            <h1>{{ a.code }} — {{ a.designation }}</h1>
          } @else {
            <h1>Article</h1>
          }
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/stock-fournitures/articles">
            <mat-icon>arrow_back</mat-icon> Liste
          </a>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
      @if (msg()) {
        <p class="bea-stock-page__ok">{{ msg() }}</p>
      }

      @if (fiche(); as a) {
        <div class="bea-mg__panel" style="margin-bottom:1rem">
          <div class="bea-mg__panel-top">
            <h2>{{ a.designation }}</h2>
            <span class="bea-stock-badge" [attr.data-niveau]="a.niveau">{{ a.niveau || '—' }}</span>
          </div>
          <div class="bea-mg__modal-body" style="padding-top:0">
            <div class="bea-mg__grid">
              <label>
                Code
                <input [value]="a.code" readonly />
              </label>
              <label>
                Famille
                <input [value]="a.famille_libelle || '—'" readonly />
              </label>
              <label>
                Stock actuel
                <input [value]="(a.stock_actuel | quantite) + ' ' + a.uom" readonly />
              </label>
              <label>
                Agence
                <input [value]="a.agence_libelle || '—'" readonly />
              </label>
            </div>
          </div>
        </div>

        <nav class="bea-fiche-tabs" aria-label="Onglets fiche article">
          @for (t of tabs; track t.id) {
            <button
              type="button"
              class="bea-fiche-tabs__btn"
              [class.bea-fiche-tabs__btn--on]="tab() === t.id"
              (click)="tab.set(t.id)"
            >
              <mat-icon>{{ t.icon }}</mat-icon>
              {{ t.label }}
            </button>
          }
        </nav>

        <div class="bea-mg__panel">
          @if (tab() === 'infos') {
            <div class="bea-mg__panel-top">
              <h2>Informations</h2>
            </div>
            <form class="bea-mg__modal-body" [formGroup]="form" (ngSubmit)="saveInfos()">
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">
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
                <label>
                  Stock min
                  <input type="number" formControlName="stock_min" min="0" step="0.001" />
                </label>
                <label>
                  Stock max
                  <input type="number" formControlName="stock_max" min="0" step="0.001" />
                </label>
                <label>
                  Agence
                  <select formControlName="agence_id">
                    <option value="">—</option>
                    @for (ag of agences(); track ag.id) {
                      <option [value]="ag.id">{{ ag.libelle }}</option>
                    }
                  </select>
                </label>
                <label>
                  Emplacement
                  <input formControlName="emplacement" />
                </label>
              </div>
              <footer class="bea-mg__modal-foot" style="padding:1rem 0 0">
                <button
                  type="submit"
                  class="bea-mg__btn bea-mg__btn--primary"
                  [disabled]="form.invalid || saving()"
                >
                  Enregistrer
                </button>
              </footer>
            </form>
          }

          @if (tab() === 'stock') {
            <div class="bea-mg__panel-top">
              <h2>Résumé stock</h2>
            </div>
            <div class="bea-mg__modal-body">
              <div class="bea-fiche-kpis">
                <div>
                  <span>Stock initial</span>
                  <strong>{{ a.stock_initial | quantite }}</strong>
                </div>
                <div>
                  <span>Σ Entrées</span>
                  <strong>{{ a.total_entrees | quantite }}</strong>
                </div>
                <div>
                  <span>Σ Sorties</span>
                  <strong>{{ a.total_sorties | quantite }}</strong>
                </div>
                <div>
                  <span>Σ Ajustements</span>
                  <strong>{{ a.total_ajustements | quantite }}</strong>
                </div>
                <div>
                  <span>Inventaires</span>
                  <strong>{{ a.total_inventaires }}</strong>
                </div>
                <div>
                  <span>Stock actuel</span>
                  <strong>{{ a.stock_actuel | quantite }} {{ a.uom }}</strong>
                </div>
              </div>
              <p class="bea-stock-page__kicker" style="margin-top:1rem">
                Min {{ a.stock_min | quantite }}
                @if (a.stock_max != null) {
                  — Max {{ a.stock_max | quantite }}
                }
              </p>
            </div>
          }

          @if (tab() === 'mouvements') {
            <div class="bea-mg__panel-top">
              <h2>Mouvements</h2>
              <span class="bea-mg__count">{{ mouvements().length }}</span>
            </div>
            <div class="bea-mg__table-scroll">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th>Réf</th>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Qté</th>
                    <th>Initiateur</th>
                    <th>Motif</th>
                  </tr>
                </thead>
                <tbody>
                  @for (m of mouvements(); track m.id) {
                    <tr>
                      <td><code class="bea-mg__code">{{ m.reference }}</code></td>
                      <td>{{ m.date_mouvement | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>
                        <span class="bea-stock-badge" [attr.data-type]="m.type_mouvement">{{ m.type_mouvement }}</span>
                      </td>
                      <td>{{ m.quantite | quantite }}</td>
                      <td>{{ m.initiateur_nom || '—' }}</td>
                      <td>{{ m.motif || '—' }}</td>
                    </tr>
                  } @empty {
                    <tr>
                      <td colspan="6">
                        <div class="bea-mg__empty">
                          <mat-icon>swap_horiz</mat-icon>
                          <p>Aucun mouvement pour cet article.</p>
                        </div>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }

          @if (tab() === 'demandes') {
            <div class="bea-mg__panel-top">
              <h2>Demandes liées</h2>
              <span class="bea-mg__count">{{ demandes().length }}</span>
            </div>
            <div class="bea-mg__table-scroll">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th>Réf</th>
                    <th>Date</th>
                    <th>Agence</th>
                    <th>Demandeur</th>
                    <th>Statut</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  @for (d of demandes(); track d.id) {
                    <tr>
                      <td><code class="bea-mg__code">{{ d.reference }}</code></td>
                      <td>{{ d.date_demande | date: 'shortDate' }}</td>
                      <td>{{ d.agence_libelle_snapshot || '—' }}</td>
                      <td>{{ d.demandeur_nom || '—' }}</td>
                      <td>
                        <span class="bea-stock-badge" [attr.data-statut]="d.statut">{{ d.statut }}</span>
                      </td>
                      <td>
                        <a class="bea-mg__icon-btn" [routerLink]="['/stock-fournitures/demandes', d.id]" title="Ouvrir">
                          <mat-icon>visibility</mat-icon>
                        </a>
                      </td>
                    </tr>
                  } @empty {
                    <tr>
                      <td colspan="6">
                        <div class="bea-mg__empty">
                          <mat-icon>assignment</mat-icon>
                          <p>Aucune demande liée à cet article.</p>
                        </div>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }

          @if (tab() === 'documents') {
            <div class="bea-mg__panel-top">
              <h2>Documents</h2>
            </div>
            <div class="bea-mg__modal-body">
              <bea-mg-ged moduleCode="stock-fournitures" entity="article" [entityId]="a.id" />
            </div>
          }
        </div>
      }
    </section>
  `,
  styles: `
    .bea-fiche-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin-bottom: 0.75rem;
    }
    .bea-fiche-tabs__btn {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      border: 1px solid #dbe3ee;
      background: #fff;
      color: #475569;
      border-radius: 999px;
      padding: 0.4rem 0.85rem;
      font: inherit;
      font-size: 0.84rem;
      font-weight: 600;
      cursor: pointer;
    }
    .bea-fiche-tabs__btn mat-icon {
      font-size: 1rem;
      width: 1rem;
      height: 1rem;
    }
    .bea-fiche-tabs__btn--on {
      background: #1a5278;
      border-color: #1a5278;
      color: #fff;
    }
    .bea-fiche-kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
      gap: 0.75rem;
    }
    .bea-fiche-kpis > div {
      padding: 0.85rem;
      border-radius: 0.75rem;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
    }
    .bea-fiche-kpis span {
      display: block;
      font-size: 0.75rem;
      color: #64748b;
      margin-bottom: 0.25rem;
    }
    .bea-fiche-kpis strong {
      font-size: 1.1rem;
      color: #0f172a;
    }
  `,
})
export class StockArticleFicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly fiche = signal<ArticleFiche | null>(null);
  readonly familles = signal<Famille[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly mouvements = signal<Mouvement[]>([]);
  readonly demandes = signal<Demande[]>([]);
  readonly tab = signal<Tab>('infos');
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly saving = signal(false);

  readonly tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'infos', label: 'Informations', icon: 'info' },
    { id: 'stock', label: 'Stock', icon: 'inventory_2' },
    { id: 'mouvements', label: 'Mouvements', icon: 'swap_horiz' },
    { id: 'demandes', label: 'Demandes', icon: 'assignment' },
    { id: 'documents', label: 'Documents', icon: 'attach_file' },
  ];

  readonly form = this.fb.nonNullable.group({
    designation: ['', Validators.required],
    famille_id: ['', Validators.required],
    uom: ['U', Validators.required],
    stock_min: [0, Validators.required],
    stock_max: [null as number | null],
    agence_id: [''],
    emplacement: [''],
  });

  ngOnInit(): void {
    this.api.get<Famille[]>('/mg/stock/familles').subscribe((f) => this.familles.set(f));
    this.api.get<Agence[]>('/mg/stock/agences').subscribe((a) => this.agences.set(a));
    this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (!id) {
        void this.router.navigateByUrl('/stock-fournitures/articles');
        return;
      }
      this.load(id);
    });
  }

  load(id: string): void {
    this.erreur.set('');
    this.api.get<ArticleFiche>(`/mg/stock/articles/${id}`).subscribe({
      next: (a) => {
        this.fiche.set(a);
        this.form.patchValue({
          designation: a.designation,
          famille_id: a.famille_id,
          uom: a.uom,
          stock_min: a.stock_min,
          stock_max: a.stock_max,
          agence_id: a.agence_id || '',
          emplacement: a.emplacement || '',
        });
        this.loadRelated(id);
      },
      error: () => this.erreur.set('Article introuvable.'),
    });
  }

  loadRelated(id: string): void {
    this.api
      .get<Paginated<Mouvement>>('/mg/stock/mouvements', { article_id: id, page: 1, size: 100 })
      .subscribe({
        next: (res) => this.mouvements.set(res.items),
        error: () => this.mouvements.set([]),
      });
    this.api
      .get<Paginated<Demande>>('/mg/stock/demandes', { article_id: id, page: 1, size: 100 })
      .subscribe({
        next: (res) => this.demandes.set(res.items),
        error: () => this.demandes.set([]),
      });
  }

  saveInfos(): void {
    const a = this.fiche();
    if (!a || this.form.invalid) return;
    this.saving.set(true);
    this.erreur.set('');
    const raw = this.form.getRawValue();
    const body: Record<string, unknown> = {
      designation: raw.designation,
      famille_id: raw.famille_id,
      uom: raw.uom,
      stock_min: raw.stock_min,
      stock_max: raw.stock_max,
      emplacement: raw.emplacement || null,
      agence_id: raw.agence_id || null,
    };
    this.api.patch<ArticleFiche>(`/mg/stock/articles/${a.id}`, body).subscribe({
      next: () => {
        this.saving.set(false);
        this.msg.set('Article mis à jour.');
        this.load(a.id);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(err?.error?.detail || 'Modification refusée.');
      },
    });
  }
}
