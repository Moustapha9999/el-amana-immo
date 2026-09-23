import { DecimalPipe } from '@angular/common';
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
  nb_demandes: number;
  nb_consultations: number;
  nb_devis: number;
  nb_comparaisons: number;
  nb_bons: number;
  nb_receptions: number;
  nb_factures: number;
  montant_bons: number;
  montant_factures: number;
  montant_paiements: number;
}

@Component({
  selector: 'bea-achats-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, DecimalPipe],
  templateUrl: './achats-rapports.component.html',
})
export class AchatsRapportsComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly catalog = signal<CatalogItem[]>([]);
  readonly summary = signal<Summary | null>(null);
  readonly erreur = signal('');
  readonly loading = signal(true);

  readonly objets = computed(() => this.catalog().filter((c) => c.group === 'objets'));
  readonly pilotage = computed(() => this.catalog().filter((c) => c.group === 'pilotage'));
  readonly analyses = computed(() => this.catalog().filter((c) => c.group === 'analyses'));

  ngOnInit(): void {
    this.api.get<CatalogItem[]>('/mg/achats/rapports/catalog').subscribe({
      next: (rows) => {
        this.catalog.set(rows);
        this.loading.set(false);
      },
      error: () => {
        this.erreur.set('Catalogue de rapports indisponible.');
        this.loading.set(false);
      },
    });
    this.api.get<Summary>('/mg/achats/rapports/summary').subscribe({
      next: (s) => this.summary.set(s),
      error: () => {
        /* export permission may be missing — hub still usable */
      },
    });
  }
}
