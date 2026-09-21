import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

interface Dash {
  articles_total: number;
  stock_faible: number;
  stock_epuise: number;
  demandes_en_cours: number;
  mouvements_mois: number;
  conso_par_famille: { label: string; value: number }[];
  conso_par_agence: { label: string; value: number }[];
  conso_par_mois: { label: string; value: number }[];
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
  selector: 'bea-stock-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, ReactiveFormsModule],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>Tableau de bord stock</h1>
          <p>Quantités temps réel, alertes et consommation.</p>
        </div>
        <a class="bea-admin-btn" routerLink="/stock-fournitures/demandes/nouvelle">Nouvelle demande</a>
      </header>

      <form class="bea-stock-toolbar" [formGroup]="filtres" (ngSubmit)="load()">
        <label>
          Agence
          <select formControlName="agence_id">
            <option value="">Toutes</option>
            @for (a of agences(); track a.id) {
              <option [value]="a.id">{{ a.libelle }}</option>
            }
          </select>
        </label>
        <label>
          Famille
          <select formControlName="famille_id">
            <option value="">Toutes</option>
            @for (f of familles(); track f.id) {
              <option [value]="f.id">{{ f.libelle }}</option>
            }
          </select>
        </label>
        <button type="submit" class="bea-admin-btn">Filtrer</button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      } @else if (loading()) {
        <p>Chargement…</p>
      } @else if (data(); as d) {
        <div class="bea-stock-kpis">
          <a routerLink="/stock-fournitures/articles"><article><span>Articles</span><strong>{{ d.articles_total }}</strong></article></a>
          <a routerLink="/stock-fournitures/alertes"><article data-tone="warn"><span>Stock faible</span><strong>{{ d.stock_faible }}</strong></article></a>
          <a routerLink="/stock-fournitures/alertes"><article data-tone="danger"><span>Épuisé</span><strong>{{ d.stock_epuise }}</strong></article></a>
          <a routerLink="/stock-fournitures/demandes"><article><span>Demandes en cours</span><strong>{{ d.demandes_en_cours }}</strong></article></a>
          <a routerLink="/stock-fournitures/journal"><article><span>Sorties du mois</span><strong>{{ d.mouvements_mois }}</strong></article></a>
        </div>

        <div class="bea-stock-charts">
          <section class="bea-stock-panel">
            <h2>Consommation par famille</h2>
            <div class="bea-stock-bars">
              @for (row of d.conso_par_famille; track row.label) {
                <div class="bea-stock-bars__row">
                  <span>{{ row.label }}</span>
                  <div class="bea-stock-bars__track">
                    <div class="bea-stock-bars__fill" [style.width.%]="barPct(row.value, maxFamille())"></div>
                  </div>
                  <strong>{{ row.value }}</strong>
                </div>
              } @empty {
                <p class="bea-stock-panel__empty">Aucune sortie enregistrée.</p>
              }
            </div>
          </section>
          <section class="bea-stock-panel">
            <h2>Consommation par agence</h2>
            <div class="bea-stock-bars">
              @for (row of d.conso_par_agence; track row.label) {
                <div class="bea-stock-bars__row">
                  <span>{{ row.label }}</span>
                  <div class="bea-stock-bars__track">
                    <div class="bea-stock-bars__fill bea-stock-bars__fill--alt" [style.width.%]="barPct(row.value, maxAgence())"></div>
                  </div>
                  <strong>{{ row.value }}</strong>
                </div>
              } @empty {
                <p class="bea-stock-panel__empty">Aucune donnée agence.</p>
              }
            </div>
          </section>
          <section class="bea-stock-panel bea-stock-panel--wide">
            <h2>Consommation mensuelle</h2>
            <div class="bea-stock-month">
              @for (row of d.conso_par_mois; track row.label) {
                <div class="bea-stock-month__col">
                  <div class="bea-stock-month__bar" [style.height.%]="barPct(row.value, maxMois())"></div>
                  <span>{{ row.label }}</span>
                </div>
              } @empty {
                <p class="bea-stock-panel__empty">Pas encore de courbe mensuelle.</p>
              }
            </div>
          </section>
        </div>
      }
    </section>
  `,
  styles: `
    .bea-stock-kpis a {
      text-decoration: none;
      color: inherit;
    }
    .bea-stock-kpis a article {
      height: 100%;
      cursor: pointer;
      transition: transform 0.15s ease;
    }
    .bea-stock-kpis a:hover article {
      transform: translateY(-2px);
    }
  `,
})
export class StockDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<Dash | null>(null);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly agences = signal<Agence[]>([]);
  readonly familles = signal<Famille[]>([]);

  readonly filtres = this.fb.nonNullable.group({
    agence_id: [''],
    famille_id: [''],
  });

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/stock/agences').subscribe({ next: (a) => this.agences.set(a) });
    this.api.get<Famille[]>('/mg/stock/familles').subscribe({ next: (f) => this.familles.set(f) });
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.erreur.set('');
    const v = this.filtres.getRawValue();
    const params: Record<string, string> = {};
    if (v.agence_id) params['agence_id'] = v.agence_id;
    if (v.famille_id) params['famille_id'] = v.famille_id;
    this.api.get<Dash>('/mg/stock/dashboard', params).subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
      },
      error: () => {
        this.erreur.set('Impossible de charger le tableau de bord.');
        this.loading.set(false);
      },
    });
  }

  maxFamille(): number {
    return Math.max(1, ...(this.data()?.conso_par_famille.map((x) => x.value) ?? [1]));
  }
  maxAgence(): number {
    return Math.max(1, ...(this.data()?.conso_par_agence.map((x) => x.value) ?? [1]));
  }
  maxMois(): number {
    return Math.max(1, ...(this.data()?.conso_par_mois.map((x) => x.value) ?? [1]));
  }
  barPct(value: number, max: number): number {
    return Math.min(100, Math.round((value / max) * 100));
  }
}
