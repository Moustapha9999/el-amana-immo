import { DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';
import { ApiService } from '../core/services/api.service';

interface EvolutionPoint {
  label: string;
  entrees: number;
  sorties: number;
}

interface Dash {
  articles_total: number;
  articles_actifs: number;
  articles_inactifs: number;
  stock_total_unites: number;
  entrees_mois: number;
  sorties_mois: number;
  articles_crees_mois: number;
  stock_faible: number;
  stock_epuise: number;
  demandes_en_attente: number;
  demandes_en_cours: number;
  demandes_validees: number;
  demandes_rejetees: number;
  inventaires_en_cours: number;
  inventaire_progression: number;
  mouvements_aujourd_hui: number;
  mouvements_mois: number;
  evolution: EvolutionPoint[];
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
  code: string;
  libelle: string;
}

type PeriodKey = '7j' | '30j' | '3m' | '12m';

const PERIODS: { value: PeriodKey; label: string }[] = [
  { value: '7j', label: '7 jours' },
  { value: '30j', label: '30 jours' },
  { value: '3m', label: '3 mois' },
  { value: '12m', label: '12 mois' },
];

@Component({
  selector: 'bea-stock-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, ReactiveFormsModule, DecimalPipe],
  template: `
    <section class="bea-stock-dash">
      <header class="bea-stock-dash__hero">
        <div class="bea-stock-dash__hero-copy">
          <h1>Tableau de bord</h1>
        </div>
        <div class="bea-stock-dash__hero-glow" aria-hidden="true"></div>
      </header>

      <form class="bea-mg__search bea-stock-dash__filters" [formGroup]="filters">
        <label class="bea-mg__field">
          <mat-icon>date_range</mat-icon>
          <select formControlName="period" aria-label="Période du graphique">
            @for (p of periods; track p.value) {
              <option [value]="p.value">{{ p.label }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>store</mat-icon>
          <select formControlName="agence_id" aria-label="Agence">
            <option value="">Toutes</option>
            @for (a of agences(); track a.id) {
              <option [value]="a.id">{{ a.libelle }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>category</mat-icon>
          <select formControlName="famille_id" aria-label="Catégorie">
            <option value="">Toutes</option>
            @for (f of familles(); track f.id) {
              <option [value]="f.id">{{ f.libelle }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>inventory</mat-icon>
          <select formControlName="statut_niveau" aria-label="Statut stock">
            <option value="empty">Tous</option>
            <option value="normal">Normal</option>
            <option value="faible">Faible</option>
            <option value="epuise">Rupture</option>
          </select>
        </label>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="resetFilters()">
          <mat-icon>restart_alt</mat-icon> Réinitialiser
        </button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      } @else if (loading()) {
        <div class="bea-stock-dash__skeleton" aria-busy="true">
          @for (_ of [1, 2, 3, 4, 5, 6, 7, 8]; track _) {
            <div class="bea-stock-dash__skel"></div>
          }
        </div>
      } @else if (data(); as d) {
        <div class="bea-stock-dash__kpis">
          <a class="bea-stock-dash__kpi" routerLink="/stock-fournitures/articles" style="--i:0">
            <span class="bea-stock-dash__kpi-icon" data-tone="navy">
              <mat-icon>inventory_2</mat-icon>
            </span>
            <span class="bea-stock-dash__kpi-meta">
              <span>Articles</span>
              <strong>{{ d.articles_actifs | number: '1.0-0' }}</strong>
              <em>+{{ d.articles_crees_mois | number: '1.0-0' }} ce mois</em>
            </span>
          </a>
          <a class="bea-stock-dash__kpi" routerLink="/stock-fournitures/articles" style="--i:1">
            <span class="bea-stock-dash__kpi-icon" data-tone="blue">
              <mat-icon>widgets</mat-icon>
            </span>
            <span class="bea-stock-dash__kpi-meta">
              <span>Stock total</span>
              <strong>{{ d.stock_total_unites | number: '1.0-2' }}</strong>
              <em>unités</em>
            </span>
          </a>
          <a class="bea-stock-dash__kpi" routerLink="/stock-fournitures/entrees" style="--i:2">
            <span class="bea-stock-dash__kpi-icon" data-tone="teal">
              <mat-icon>south</mat-icon>
            </span>
            <span class="bea-stock-dash__kpi-meta">
              <span>Entrées</span>
              <strong>{{ d.entrees_mois | number: '1.0-0' }}</strong>
              <em>ce mois</em>
            </span>
          </a>
          <a class="bea-stock-dash__kpi" routerLink="/stock-fournitures/sorties" style="--i:3">
            <span class="bea-stock-dash__kpi-icon" data-tone="navy">
              <mat-icon>north</mat-icon>
            </span>
            <span class="bea-stock-dash__kpi-meta">
              <span>Sorties</span>
              <strong>{{ d.sorties_mois | number: '1.0-0' }}</strong>
              <em>ce mois</em>
            </span>
          </a>
        </div>

        <div class="bea-stock-dash__kpis bea-stock-dash__kpis--row2">
          <a
            class="bea-stock-dash__kpi"
            routerLink="/stock-fournitures/alertes"
            style="--i:0"
            [attr.data-active]="d.stock_faible > 0 ? 'warn' : null"
          >
            <span class="bea-stock-dash__kpi-icon" data-tone="warn">
              <mat-icon>warning</mat-icon>
            </span>
            <span class="bea-stock-dash__kpi-meta">
              <span>Stock faible</span>
              <strong>{{ d.stock_faible | number: '1.0-0' }}</strong>
              <em>Attention</em>
            </span>
          </a>
          <a
            class="bea-stock-dash__kpi"
            routerLink="/stock-fournitures/alertes"
            style="--i:1"
            [attr.data-active]="d.stock_epuise > 0 ? 'danger' : null"
          >
            <span class="bea-stock-dash__kpi-icon" data-tone="danger">
              <mat-icon>remove_shopping_cart</mat-icon>
            </span>
            <span class="bea-stock-dash__kpi-meta">
              <span>Rupture</span>
              <strong>{{ d.stock_epuise | number: '1.0-0' }}</strong>
              <em>Épuisé</em>
            </span>
          </a>
          <a class="bea-stock-dash__kpi" routerLink="/stock-fournitures/demandes" style="--i:2">
            <span class="bea-stock-dash__kpi-icon" data-tone="blue">
              <mat-icon>assignment</mat-icon>
            </span>
            <span class="bea-stock-dash__kpi-meta">
              <span>Demandes en attente</span>
              <strong>{{ d.demandes_en_attente | number: '1.0-0' }}</strong>
              <em>À traiter</em>
            </span>
          </a>
          <a class="bea-stock-dash__kpi" routerLink="/stock-fournitures/inventaires" style="--i:3">
            <span class="bea-stock-dash__kpi-icon" data-tone="teal">
              <mat-icon>fact_check</mat-icon>
            </span>
            <span class="bea-stock-dash__kpi-meta">
              <span>Inventaire</span>
              <strong>{{ d.inventaire_progression | number: '1.0-1' }}%</strong>
              <em
                >Progression · {{ d.inventaires_en_cours | number: '1.0-0' }} en cours</em
              >
            </span>
          </a>
        </div>

        <section class="bea-stock-dash__panel bea-stock-dash__panel--chart" style="--i:0">
          <header class="bea-stock-dash__panel-head">
            <div>
              <h2>Mouvements de stock</h2>
              <p>Entrées et sorties sur la période sélectionnée</p>
            </div>
            <div class="bea-stock-dash__chips" role="group" aria-label="Période du graphique">
              @for (p of periods; track p.value) {
                <button
                  type="button"
                  class="bea-stock-dash__chip"
                  [attr.data-active]="filters.controls.period.value === p.value"
                  (click)="setPeriod(p.value)"
                >
                  {{ p.label }}
                </button>
              }
            </div>
          </header>

          <div class="bea-stock-dash__legend">
            <span><i data-tone="entrees"></i> Entrées</span>
            <span><i data-tone="sorties"></i> Sorties</span>
          </div>

          @if (lineChart(); as chart) {
            @if (chart.hasData) {
              <div class="bea-stock-dash__svg-wrap">
                <svg
                  class="bea-stock-dash__svg"
                  viewBox="0 0 100 56"
                  preserveAspectRatio="none"
                  role="img"
                  [attr.aria-label]="'Courbe des mouvements sur ' + periodLabel(filters.controls.period.value)"
                >
                  <defs>
                    <linearGradient id="beaDashEntreesFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#1a5278" stop-opacity="0.28" />
                      <stop offset="100%" stop-color="#1a5278" stop-opacity="0.02" />
                    </linearGradient>
                    <linearGradient id="beaDashSortiesFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#0f766e" stop-opacity="0.22" />
                      <stop offset="100%" stop-color="#0f766e" stop-opacity="0.02" />
                    </linearGradient>
                  </defs>
                  @for (g of chart.gridY; track g) {
                    <line
                      class="bea-stock-dash__grid"
                      [attr.x1]="chart.padX"
                      [attr.x2]="100 - chart.padX"
                      [attr.y1]="g"
                      [attr.y2]="g"
                    />
                  }
                  <polygon class="bea-stock-dash__area bea-stock-dash__area--entrees" [attr.points]="chart.areaEntrees" />
                  <polygon class="bea-stock-dash__area bea-stock-dash__area--sorties" [attr.points]="chart.areaSorties" />
                  <polyline
                    class="bea-stock-dash__line bea-stock-dash__line--entrees"
                    fill="none"
                    [attr.points]="chart.lineEntrees"
                  />
                  <polyline
                    class="bea-stock-dash__line bea-stock-dash__line--sorties"
                    fill="none"
                    [attr.points]="chart.lineSorties"
                  />
                  @for (dot of chart.dotsEntrees; track $index) {
                    <circle class="bea-stock-dash__dot bea-stock-dash__dot--entrees" [attr.cx]="dot.x" [attr.cy]="dot.y" r="1.1" />
                  }
                  @for (dot of chart.dotsSorties; track $index) {
                    <circle class="bea-stock-dash__dot bea-stock-dash__dot--sorties" [attr.cx]="dot.x" [attr.cy]="dot.y" r="1.1" />
                  }
                </svg>
                <div class="bea-stock-dash__xlabels">
                  @for (lab of chart.labels; track lab + $index) {
                    <span>{{ lab }}</span>
                  }
                </div>
              </div>
            } @else {
              <p class="bea-stock-panel__empty">Aucun mouvement sur cette période.</p>
            }
          }
        </section>

        <div class="bea-stock-dash__charts">
          <section class="bea-stock-dash__panel" style="--i:1">
            <header>
              <h2>Consommation par famille</h2>
              <p>Sorties cumulées</p>
            </header>
            <div class="bea-stock-bars">
              @for (row of d.conso_par_famille; track row.label; let i = $index) {
                <div class="bea-stock-bars__row" [style.--i]="i">
                  <span>{{ row.label }}</span>
                  <div class="bea-stock-bars__track">
                    <div
                      class="bea-stock-bars__fill bea-stock-dash__bar"
                      [style.--w.%]="barPct(row.value, maxFamille())"
                    ></div>
                  </div>
                  <strong>{{ row.value | number: '1.0-2' }}</strong>
                </div>
              } @empty {
                <p class="bea-stock-panel__empty">Aucune sortie enregistrée.</p>
              }
            </div>
          </section>

          <section class="bea-stock-dash__panel" style="--i:2">
            <header>
              <h2>Consommation par agence</h2>
              <p>Répartition géographique</p>
            </header>
            <div class="bea-stock-bars">
              @for (row of d.conso_par_agence; track row.label; let i = $index) {
                <div class="bea-stock-bars__row" [style.--i]="i">
                  <span>{{ row.label }}</span>
                  <div class="bea-stock-bars__track">
                    <div
                      class="bea-stock-bars__fill bea-stock-bars__fill--alt bea-stock-dash__bar"
                      [style.--w.%]="barPct(row.value, maxAgence())"
                    ></div>
                  </div>
                  <strong>{{ row.value | number: '1.0-2' }}</strong>
                </div>
              } @empty {
                <p class="bea-stock-panel__empty">Aucune donnée agence.</p>
              }
            </div>
          </section>
        </div>

        <nav class="bea-stock-dash__shortcuts" aria-label="Accès rapides">
          <a routerLink="/stock-fournitures/entrees">
            <mat-icon>south</mat-icon><span>Entrées</span>
          </a>
          <a routerLink="/stock-fournitures/sorties">
            <mat-icon>north</mat-icon><span>Sorties</span>
          </a>
          <a routerLink="/stock-fournitures/inventaires">
            <mat-icon>fact_check</mat-icon><span>Inventaire</span>
          </a>
          <a routerLink="/stock-fournitures/rapports">
            <mat-icon>assessment</mat-icon><span>Rapports</span>
          </a>
        </nav>
      }
    </section>
  `,
  styles: `
    :host {
      display: block;
    }

    .bea-stock-dash {
      max-width: 74rem;
    }

    .bea-stock-dash__hero {
      position: relative;
      overflow: hidden;
      border-radius: 1rem;
      padding: 1.25rem 1.5rem;
      margin-bottom: 1.15rem;
      background: linear-gradient(135deg, #0f172a 0%, #1a5278 55%, #2874a6 100%);
      color: #f8fafc;
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.18);
      animation: beaDashHeroIn 0.55s ease both;
    }

    .bea-stock-dash__hero h1 {
      margin: 0;
      font-size: clamp(1.45rem, 2.4vw, 1.85rem);
      font-weight: 700;
      letter-spacing: -0.02em;
    }

    .bea-stock-dash__hero-glow {
      position: absolute;
      right: -4rem;
      top: -3rem;
      width: 16rem;
      height: 16rem;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255, 255, 255, 0.22), transparent 68%);
      animation: beaDashPulse 4.5s ease-in-out infinite;
      pointer-events: none;
    }

    .bea-stock-dash__filters {
      animation: beaDashRise 0.45s ease both;
    }

    .bea-stock-dash__kpis {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 0.85rem;
      margin-bottom: 0.85rem;
    }

    .bea-stock-dash__kpis--row2 {
      margin-bottom: 1.15rem;
    }

    .bea-stock-dash__kpi {
      display: flex;
      gap: 0.75rem;
      align-items: center;
      text-decoration: none;
      color: inherit;
      background: #fff;
      border: 1px solid #dbe3ee;
      border-radius: 0.9rem;
      padding: 0.95rem 1rem;
      box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
      transition:
        transform 0.22s ease,
        box-shadow 0.22s ease,
        border-color 0.22s ease;
      animation: beaDashRise 0.5s ease both;
      animation-delay: calc(var(--i, 0) * 70ms);
    }

    .bea-stock-dash__kpi:hover {
      transform: translateY(-3px);
      border-color: #94a3b8;
      box-shadow: 0 10px 22px rgba(15, 23, 42, 0.1);
    }

    .bea-stock-dash__kpi[data-active='warn'] {
      border-color: #f59e0b;
      background: linear-gradient(180deg, #fffbeb, #fff);
    }

    .bea-stock-dash__kpi[data-active='danger'] {
      border-color: #ef4444;
      background: linear-gradient(180deg, #fef2f2, #fff);
      animation:
        beaDashRise 0.5s ease both,
        beaDashAlert 2.2s ease-in-out infinite;
      animation-delay: calc(var(--i, 0) * 70ms), 0.8s;
    }

    .bea-stock-dash__kpi-icon {
      flex: 0 0 auto;
      width: 2.4rem;
      height: 2.4rem;
      border-radius: 0.7rem;
      display: grid;
      place-items: center;
      background: #e2e8f0;
    }

    .bea-stock-dash__kpi-icon mat-icon {
      font-size: 1.2rem;
      width: 1.2rem;
      height: 1.2rem;
    }

    .bea-stock-dash__kpi-icon[data-tone='navy'] {
      background: #e8eef5;
      color: #1a5278;
    }
    .bea-stock-dash__kpi-icon[data-tone='warn'] {
      background: #fef3c7;
      color: #b45309;
    }
    .bea-stock-dash__kpi-icon[data-tone='danger'] {
      background: #fee2e2;
      color: #b91c1c;
    }
    .bea-stock-dash__kpi-icon[data-tone='blue'] {
      background: #dbeafe;
      color: #1d4ed8;
    }
    .bea-stock-dash__kpi-icon[data-tone='teal'] {
      background: #d1fae5;
      color: #047857;
    }

    .bea-stock-dash__kpi-meta span {
      display: block;
      font-size: 0.72rem;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .bea-stock-dash__kpi-meta strong {
      display: block;
      margin-top: 0.15rem;
      font-size: 1.45rem;
      line-height: 1.1;
      font-variant-numeric: tabular-nums;
      color: #0f172a;
    }

    .bea-stock-dash__kpi-meta em {
      display: block;
      margin-top: 0.2rem;
      font-style: normal;
      font-size: 0.72rem;
      color: #94a3b8;
    }

    .bea-stock-dash__kpi[data-active='warn'] strong {
      color: #b45309;
    }
    .bea-stock-dash__kpi[data-active='danger'] strong {
      color: #b91c1c;
    }

    .bea-stock-dash__shortcuts {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.25rem;
      margin-bottom: 0.5rem;
      animation: beaDashRise 0.55s ease both;
      animation-delay: 0.45s;
    }

    .bea-stock-dash__shortcuts a {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      text-decoration: none;
      color: #1a5278;
      background: #fff;
      border: 1px solid #cbd5e1;
      border-radius: 999px;
      padding: 0.4rem 0.9rem;
      font-size: 0.82rem;
      font-weight: 600;
      transition:
        background 0.2s ease,
        color 0.2s ease,
        transform 0.2s ease;
    }

    .bea-stock-dash__shortcuts a mat-icon {
      font-size: 1rem;
      width: 1rem;
      height: 1rem;
    }

    .bea-stock-dash__shortcuts a:hover {
      background: #1a5278;
      color: #fff;
      transform: translateY(-1px);
    }

    .bea-stock-dash__charts {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
      margin-bottom: 1rem;
    }

    .bea-stock-dash__panel {
      background: #fff;
      border: 1px solid #dbe3ee;
      border-radius: 1rem;
      padding: 1.1rem 1.15rem 1.2rem;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
      animation: beaDashRise 0.55s ease both;
      animation-delay: calc(0.25s + var(--i, 0) * 90ms);
    }

    .bea-stock-dash__panel--chart {
      margin-bottom: 1rem;
    }

    .bea-stock-dash__panel-head {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: 0.75rem;
      margin-bottom: 0.65rem;
    }

    .bea-stock-dash__panel header h2,
    .bea-stock-dash__panel-head h2 {
      margin: 0;
      font-size: 1.02rem;
      color: #0f172a;
    }

    .bea-stock-dash__panel header p,
    .bea-stock-dash__panel-head p {
      margin: 0.2rem 0 0;
      font-size: 0.78rem;
      color: #64748b;
    }

    .bea-stock-dash__chips {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
    }

    .bea-stock-dash__chip {
      border: 1px solid #cbd5e1;
      background: #f8fafc;
      color: #475569;
      border-radius: 999px;
      padding: 0.3rem 0.7rem;
      font: inherit;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      transition:
        background 0.18s ease,
        color 0.18s ease,
        border-color 0.18s ease;
    }

    .bea-stock-dash__chip[data-active='true'] {
      background: #1a5278;
      border-color: #1a5278;
      color: #fff;
    }

    .bea-stock-dash__chip:hover {
      border-color: #1a5278;
      color: #1a5278;
    }

    .bea-stock-dash__chip[data-active='true']:hover {
      color: #fff;
    }

    .bea-stock-dash__legend {
      display: flex;
      gap: 1rem;
      margin-bottom: 0.65rem;
      font-size: 0.78rem;
      color: #64748b;
    }

    .bea-stock-dash__legend span {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }

    .bea-stock-dash__legend i {
      width: 0.7rem;
      height: 0.7rem;
      border-radius: 999px;
      display: inline-block;
    }

    .bea-stock-dash__legend i[data-tone='entrees'] {
      background: #1a5278;
    }
    .bea-stock-dash__legend i[data-tone='sorties'] {
      background: #0f766e;
    }

    .bea-stock-dash__svg-wrap {
      width: 100%;
    }

    .bea-stock-dash__svg {
      display: block;
      width: 100%;
      height: 14rem;
      overflow: visible;
    }

    .bea-stock-dash__grid {
      stroke: #e2e8f0;
      stroke-width: 0.25;
    }

    .bea-stock-dash__area--entrees {
      fill: url(#beaDashEntreesFill);
    }
    .bea-stock-dash__area--sorties {
      fill: url(#beaDashSortiesFill);
    }

    .bea-stock-dash__line {
      stroke-width: 1.35;
      stroke-linecap: round;
      stroke-linejoin: round;
      vector-effect: non-scaling-stroke;
    }

    .bea-stock-dash__line--entrees {
      stroke: #1a5278;
    }
    .bea-stock-dash__line--sorties {
      stroke: #0f766e;
    }

    .bea-stock-dash__dot--entrees {
      fill: #1a5278;
    }
    .bea-stock-dash__dot--sorties {
      fill: #0f766e;
    }

    .bea-stock-dash__xlabels {
      display: flex;
      justify-content: space-between;
      gap: 0.25rem;
      margin-top: 0.35rem;
      font-size: 0.68rem;
      color: #94a3b8;
    }

    .bea-stock-dash__xlabels span {
      flex: 1;
      text-align: center;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .bea-stock-dash__bar {
      width: 0;
      animation: beaDashBarGrow 0.85s cubic-bezier(0.22, 1, 0.36, 1) forwards;
      animation-delay: calc(0.4s + var(--i, 0) * 60ms);
    }

    .bea-stock-dash__skeleton {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.85rem;
      margin-bottom: 1rem;
    }

    .bea-stock-dash__skel {
      height: 4.5rem;
      border-radius: 0.9rem;
      background: linear-gradient(90deg, #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%);
      background-size: 200% 100%;
      animation: beaDashShimmer 1.2s linear infinite;
    }

    @keyframes beaDashHeroIn {
      from {
        opacity: 0;
        transform: translateY(8px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @keyframes beaDashRise {
      from {
        opacity: 0;
        transform: translateY(12px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @keyframes beaDashPulse {
      0%,
      100% {
        transform: scale(1);
        opacity: 0.9;
      }
      50% {
        transform: scale(1.08);
        opacity: 1;
      }
    }

    @keyframes beaDashAlert {
      0%,
      100% {
        box-shadow: 0 4px 14px rgba(185, 28, 28, 0.08);
      }
      50% {
        box-shadow: 0 8px 22px rgba(185, 28, 28, 0.2);
      }
    }

    @keyframes beaDashBarGrow {
      from {
        width: 0;
      }
      to {
        width: var(--w, 0%);
      }
    }

    @keyframes beaDashShimmer {
      0% {
        background-position: 200% 0;
      }
      100% {
        background-position: -200% 0;
      }
    }

    @media (max-width: 1100px) {
      .bea-stock-dash__kpis {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 900px) {
      .bea-stock-dash__charts {
        grid-template-columns: 1fr;
      }
      .bea-stock-dash__skeleton {
        grid-template-columns: repeat(2, 1fr);
      }
    }

    @media (max-width: 560px) {
      .bea-stock-dash__kpis {
        grid-template-columns: 1fr;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .bea-stock-dash__hero,
      .bea-stock-dash__kpi,
      .bea-stock-dash__panel,
      .bea-stock-dash__shortcuts,
      .bea-stock-dash__filters,
      .bea-stock-dash__bar,
      .bea-stock-dash__hero-glow,
      .bea-stock-dash__skel {
        animation: none !important;
      }
      .bea-stock-dash__bar {
        width: var(--w, 0%);
      }
      .bea-stock-dash__kpi:hover,
      .bea-stock-dash__shortcuts a:hover {
        transform: none;
      }
    }
  `,
})
export class StockDashboardComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private sub?: Subscription;

  readonly periods = PERIODS;
  readonly data = signal<Dash | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly familles = signal<Famille[]>([]);
  readonly loading = signal(true);
  readonly erreur = signal('');

  readonly filters = this.fb.nonNullable.group({
    period: ['30j' as PeriodKey],
    agence_id: [''],
    famille_id: [''],
    statut_niveau: ['empty'],
  });

  readonly lineChart = computed(() => this.buildDualLine(this.data()?.evolution ?? []));

  periodLabel(period: string): string {
    return PERIODS.find((p) => p.value === period)?.label ?? period;
  }

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/stock/agences').subscribe({
      next: (rows) => this.agences.set(rows),
      error: () => this.agences.set([]),
    });
    this.api.get<Famille[]>('/mg/stock/familles').subscribe({
      next: (rows) => this.familles.set(rows),
      error: () => this.familles.set([]),
    });

    this.sub = this.filters.valueChanges
      .pipe(debounceTime(120), distinctUntilChanged((a, b) => JSON.stringify(a) === JSON.stringify(b)))
      .subscribe(() => this.load());

    this.load();
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  setPeriod(period: PeriodKey): void {
    if (this.filters.controls.period.value === period) {
      this.load();
      return;
    }
    this.filters.controls.period.setValue(period);
  }

  resetFilters(): void {
    this.filters.setValue({
      period: '30j',
      agence_id: '',
      famille_id: '',
      statut_niveau: 'empty',
    });
  }

  load(): void {
    this.loading.set(true);
    this.erreur.set('');
    const v = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      period: v.period,
      statut_niveau: v.statut_niveau || 'empty',
    };
    if (v.agence_id) {
      params['agence_id'] = v.agence_id;
    }
    if (v.famille_id) {
      params['famille_id'] = v.famille_id;
    }
    this.api.get<Dash>('/mg/stock/dashboard', params).subscribe({
      next: (d) => {
        this.data.set({
          ...d,
          evolution: Array.isArray(d.evolution) ? d.evolution : [],
          conso_par_famille: d.conso_par_famille ?? [],
          conso_par_agence: d.conso_par_agence ?? [],
          conso_par_mois: d.conso_par_mois ?? [],
        });
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

  barPct(value: number, max: number): number {
    return Math.min(100, Math.round((value / max) * 100));
  }

  private buildDualLine(points: EvolutionPoint[]): {
    hasData: boolean;
    padX: number;
    gridY: number[];
    labels: string[];
    lineEntrees: string;
    lineSorties: string;
    areaEntrees: string;
    areaSorties: string;
    dotsEntrees: { x: number; y: number }[];
    dotsSorties: { x: number; y: number }[];
  } {
    const padX = 3;
    const padY = 6;
    const height = 56;
    const empty = {
      hasData: false,
      padX,
      gridY: [padY, height / 2, height - padY],
      labels: [] as string[],
      lineEntrees: '',
      lineSorties: '',
      areaEntrees: '',
      areaSorties: '',
      dotsEntrees: [] as { x: number; y: number }[],
      dotsSorties: [] as { x: number; y: number }[],
    };
    if (!points.length) {
      return empty;
    }

    const values = points.flatMap((p) => [p.entrees || 0, p.sorties || 0]);
    const max = Math.max(...values, 0);
    const hasData = max > 0 || points.some((p) => (p.entrees || 0) + (p.sorties || 0) > 0);
    const range = max > 0 ? max : 1;
    const w = 100 - padX * 2;
    const h = height - padY * 2;
    const step = points.length > 1 ? w / (points.length - 1) : 0;

    const mapY = (v: number) => padY + h - (v / range) * h;
    const dotsEntrees = points.map((p, i) => ({
      x: padX + i * step,
      y: mapY(p.entrees || 0),
    }));
    const dotsSorties = points.map((p, i) => ({
      x: padX + i * step,
      y: mapY(p.sorties || 0),
    }));
    const baseline = height - padY;
    const lineEntrees = dotsEntrees.map((d) => `${d.x},${d.y}`).join(' ');
    const lineSorties = dotsSorties.map((d) => `${d.x},${d.y}`).join(' ');
    const areaEntrees =
      dotsEntrees.length > 0
        ? `${lineEntrees} ${dotsEntrees[dotsEntrees.length - 1].x},${baseline} ${dotsEntrees[0].x},${baseline}`
        : '';
    const areaSorties =
      dotsSorties.length > 0
        ? `${lineSorties} ${dotsSorties[dotsSorties.length - 1].x},${baseline} ${dotsSorties[0].x},${baseline}`
        : '';

    return {
      hasData: hasData || points.length > 0,
      padX,
      gridY: [padY, padY + h / 2, baseline],
      labels: points.map((p) => p.label),
      lineEntrees,
      lineSorties,
      areaEntrees,
      areaSorties,
      dotsEntrees,
      dotsSorties,
    };
  }
}
