import { QuantitePipe } from '../shared/montant.pipe';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

interface CatalogItem {
  key: string;
  label: string;
  description: string;
  icon: string;
  group: string;
  csv_enabled: boolean;
}

interface Summary {
  nb_articles: number;
  nb_mouvements: number;
  nb_inventaires: number;
  nb_periodes: number;
}

@Component({
  selector: 'bea-stock-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, QuantitePipe],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting</p>
          <h1>Centre de reporting</h1>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (summary(); as s) {
        <div class="bea-stock-dash__kpis" style="margin-bottom:1rem">
          <div class="bea-mg__panel" style="padding:0.9rem 1rem">
            <span class="bea-stock-page__kicker">Articles</span>
            <strong style="display:block;font-size:1.35rem">{{ s.nb_articles | quantite }}</strong>
          </div>
          <div class="bea-mg__panel" style="padding:0.9rem 1rem">
            <span class="bea-stock-page__kicker">Mouvements</span>
            <strong style="display:block;font-size:1.35rem">{{ s.nb_mouvements | quantite }}</strong>
          </div>
          <div class="bea-mg__panel" style="padding:0.9rem 1rem">
            <span class="bea-stock-page__kicker">Inventaires</span>
            <strong style="display:block;font-size:1.35rem">{{ s.nb_inventaires | quantite }}</strong>
          </div>
          <div class="bea-mg__panel" style="padding:0.9rem 1rem">
            <span class="bea-stock-page__kicker">Périodes</span>
            <strong style="display:block;font-size:1.35rem">{{ s.nb_periodes | quantite }}</strong>
          </div>
        </div>
      }

      @for (grp of groups(); track grp.key) {
        <div class="bea-mg__panel" style="margin-bottom:1rem">
          <div class="bea-mg__panel-top">
            <h2>{{ grp.label }}</h2>
            <span class="bea-mg__count">{{ grp.items.length }}</span>
          </div>
          <div class="bea-stock-report-grid">
            @for (r of grp.items; track r.key; let i = $index) {
              <a class="bea-stock-report-card" [routerLink]="['/stock-fournitures/rapports', r.key]" [style.--i]="i">
                <span class="bea-stock-dash__kpi-icon" data-tone="navy"><mat-icon>{{ r.icon }}</mat-icon></span>
                <span>
                  <strong>{{ r.label }}</strong>
                  <em>{{ r.description }}</em>
                </span>
                <mat-icon>chevron_right</mat-icon>
              </a>
            }
          </div>
        </div>
      }
    </section>
  `,
  styles: `
    .bea-stock-report-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
      gap: 0.75rem;
    }
    .bea-stock-report-card {
      display: flex;
      align-items: center;
      gap: 0.7rem;
      padding: 0.85rem 1rem;
      border: 1px solid #dbe3ee;
      border-radius: 0.85rem;
      text-decoration: none;
      color: inherit;
      background: #fff;
      animation: beaRepIn 0.4s ease both;
      animation-delay: calc(var(--i, 0) * 40ms);
    }
    .bea-stock-report-card:hover {
      border-color: #1a5278;
    }
    .bea-stock-report-card strong {
      display: block;
      color: #0f172a;
    }
    .bea-stock-report-card em {
      display: block;
      font-style: normal;
      font-size: 0.78rem;
      color: #64748b;
    }
    .bea-stock-dash__kpis {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.75rem;
    }
    @keyframes beaRepIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: none; }
    }
    @media (max-width: 800px) {
      .bea-stock-dash__kpis { grid-template-columns: 1fr 1fr; }
    }
  `,
})
export class StockRapportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly catalog = signal<CatalogItem[]>([]);
  readonly summary = signal<Summary | null>(null);
  readonly erreur = signal('');

  readonly groups = computed(() => {
    const rows = this.catalog();
    return [
      { key: 'objets', label: 'États & journaux', items: rows.filter((r) => r.group === 'objets') },
      { key: 'pilotage', label: 'Pilotage', items: rows.filter((r) => r.group === 'pilotage') },
      { key: 'analyses', label: 'Analyses & personnalisation', items: rows.filter((r) => r.group === 'analyses') },
    ].filter((g) => g.items.length);
  });

  ngOnInit(): void {
    this.api.get<CatalogItem[]>('/mg/stock/rapports/catalog').subscribe({
      next: (rows) => this.catalog.set(rows),
      error: () => this.erreur.set('Catalogue de rapports indisponible.'),
    });
    this.api.get<Summary>('/mg/stock/rapports/summary').subscribe({
      next: (s) => this.summary.set(s),
      error: () => {
        /* export optionnel */
      },
    });
  }
}
