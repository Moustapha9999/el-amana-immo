import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { ArchivesChartsComponent, ChartPoint, OcrSlice } from './archives-charts.component';

interface DashDoc {
  id: string;
  filename: string;
  module_code: string;
  entity: string;
  created_at: string | null;
}

interface Dashboard {
  total: number;
  ce_mois: number;
  cette_annee: number;
  achats: number;
  stock: number;
  notes: number;
  contrats: number;
  manquants: number;
  corbeille: number;
  ocr_done: number;
  ocr_pending: number;
  ocr_processing: number;
  ocr_failed: number;
  par_mois: { year: number; month: number; count: number }[];
  par_module: { module_code: string; label: string; count: number }[];
  par_type: { type: string; count: number }[];
  recents: DashDoc[];
}

@Component({
  selector: 'bea-archives-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe, ArchivesChartsComponent],
  template: `
    <section class="bea-mg bea-nf">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>Archives — Tableau de bord</h1>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn" routerLink="/archives-mg/rapports">Rapports</a>
          <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/archives-mg/documents" [queryParams]="{}">Scanner / Importer</a>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (d(); as dash) {
        <div class="bea-nf-kpi">
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents">
            <p>Documents</p><strong>{{ dash.total }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ recent_days: 31 }">
            <p>Ce mois</p><strong>{{ dash.ce_mois }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ year: currentYear }">
            <p>Cette année</p><strong>{{ dash.cette_annee }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ ocr_status: 'done' }">
            <p>OCR terminés</p><strong>{{ dash.ocr_done }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ ocr_status: 'processing' }">
            <p>OCR en cours</p><strong>{{ dash.ocr_processing + dash.ocr_pending }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ ocr_status: 'failed' }">
            <p>OCR en erreur</p><strong>{{ dash.ocr_failed }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/manquants">
            <p>À vérifier</p><strong>{{ dash.manquants }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/corbeille">
            <p>Corbeille</p><strong>{{ dash.corbeille }}</strong>
          </a>
        </div>

        <bea-archives-charts
          [months]="monthPoints()"
          [modules]="modulePoints()"
          [types]="typePoints()"
          [ocr]="ocrPoints()"
          listPath="/archives-mg/documents"
        />

        <div class="bea-mg__panel" style="margin-top:1rem">
          <div class="bea-mg__panel-top">
            <h2>Documents récents</h2>
            <span class="bea-mg__count">{{ dash.recents.length }}</span>
          </div>
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table">
              <thead>
                <tr><th>Fichier</th><th>Module</th><th>Entité</th><th>Date</th></tr>
              </thead>
              <tbody>
                @for (r of dash.recents; track r.id) {
                  <tr>
                    <td>
                      <a [routerLink]="['/archives-mg/documents', r.id]">{{ r.filename }}</a>
                    </td>
                    <td>{{ r.module_code }}</td>
                    <td>{{ r.entity }}</td>
                    <td>{{ r.created_at ? (r.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                  </tr>
                } @empty {
                  <tr><td colspan="4"><div class="bea-mg__empty"><p>Aucun document archivé.</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      } @else if (!erreur()) {
        <p class="bea-stock-page__kicker">Chargement du tableau de bord…</p>
      }
    </section>
  `,
})
export class ArchivesDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly d = signal<Dashboard | null>(null);
  readonly erreur = signal<string | null>(null);
  readonly currentYear = new Date().getFullYear();

  readonly monthPoints = computed<ChartPoint[]>(() => {
    const rows = this.d()?.par_mois ?? [];
    return rows.map((r) => ({
      label: `${String(r.month).padStart(2, '0')}/${r.year}`,
      value: r.count,
      key: `${r.year}-${r.month}`,
    }));
  });

  readonly modulePoints = computed<ChartPoint[]>(() => {
    const rows = this.d()?.par_module ?? [];
    return rows.map((r) => ({
      label: r.label || r.module_code,
      value: r.count,
      key: r.module_code,
      queryParams: { module_code: r.module_code },
    }));
  });

  readonly typePoints = computed<ChartPoint[]>(() => {
    const rows = this.d()?.par_type ?? [];
    return rows.map((r) => ({
      label: r.type,
      value: r.count,
      key: r.type,
    }));
  });

  readonly ocrPoints = computed<OcrSlice[]>(() => {
    const dash = this.d();
    if (!dash) return [];
    return [
      { label: 'Terminés', value: dash.ocr_done, key: 'done', color: '#166534' },
      { label: 'En attente', value: dash.ocr_pending, key: 'pending', color: '#92400e' },
      { label: 'En cours', value: dash.ocr_processing, key: 'processing', color: '#1e40af' },
      { label: 'Échec', value: dash.ocr_failed, key: 'failed', color: '#991b1b' },
    ];
  });

  ngOnInit(): void {
    this.api.get<Dashboard>('/mg/archives/dashboard').subscribe({
      next: (row) => this.d.set(row),
      error: () => this.erreur.set('Tableau de bord archives indisponible.'),
    });
  }
}
