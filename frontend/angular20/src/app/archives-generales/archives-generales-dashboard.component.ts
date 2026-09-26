import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { ArchivesChartsComponent, ChartPoint, OcrSlice } from '../archives-mg/archives-charts.component';

interface DashDoc {
  id: string;
  filename: string;
  title?: string | null;
  reference?: string | null;
  espace_code: string;
  module_code: string;
  created_at: string | null;
}

interface ActivityEvent {
  id: string;
  action: string;
  label: string;
  created_at: string | null;
  entity_id?: string | null;
  espace_code?: string | null;
  module_code?: string | null;
  after?: Record<string, unknown> | null;
}

interface EspaceRow {
  espace_code: string;
  label?: string;
  count: number;
  ocr_done?: number;
  ocr_en_cours?: number;
  a_verifier?: number;
}

interface Dashboard {
  total: number;
  ce_mois: number;
  cette_annee: number;
  ocr_done: number;
  ocr_pending: number;
  ocr_processing: number;
  ocr_failed: number;
  ocr_en_cours: number;
  corbeille: number;
  manquants: number;
  a_verifier: number;
  dossiers_actifs: number;
  departements_actifs: number;
  par_mois: { year: number; month: number; count: number; label?: string }[];
  par_espace: EspaceRow[];
  par_module: { module_code: string; label?: string; count: number }[];
  par_type: { type: string; count: number }[];
  par_agence: { agence_id: string; label?: string; count: number }[];
  activite_recente: ActivityEvent[];
  recents: DashDoc[];
  ocr: {
    pending: number;
    processing: number;
    done: number;
    failed: number;
    en_cours: number;
  };
}

@Component({
  selector: 'bea-archives-generales-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe, DecimalPipe, MatIconModule, ArchivesChartsComponent],
  template: `
    <section class="bea-mg bea-nf bea-ag-dash">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Archive Générale</p>
          <h1>État documentaire de la plateforme</h1>
        </div>
        <div class="bea-mg__actions bea-ag-dash__actions">
          <a class="bea-mg__btn" routerLink="/archives-generales/recherche"><mat-icon>search</mat-icon> Recherche</a>
          <a class="bea-mg__btn" routerLink="/archives-generales/numeriser"><mat-icon>upload_file</mat-icon> Importer</a>
          <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/archives-generales/rapports"><mat-icon>summarize</mat-icon> Rapports</a>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (d(); as dash) {
        <div class="bea-nf-kpi">
          <a class="bea-nf-kpi__card" routerLink="/archives-generales/documents">
            <p>Documents</p><strong>{{ dash.total | number }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-generales/documents">
            <p>Ce mois</p><strong>{{ dash.ce_mois | number }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-generales/documents">
            <p>Cette année</p><strong>{{ dash.cette_annee | number }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-generales/documents">
            <p>Départements</p><strong>{{ dash.departements_actifs | number }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-generales/documents" [queryParams]="{ ocr_status: 'done' }">
            <p>OCR terminés</p><strong>{{ ocr().done | number }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-generales/ocr">
            <p>OCR en cours</p><strong>{{ ocr().en_cours | number }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-generales/a-verifier">
            <p>À vérifier</p><strong>{{ dash.a_verifier | number }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-generales/manquants">
            <p>Manquants</p><strong>{{ dash.manquants | number }}</strong>
          </a>
        </div>

        <bea-archives-charts
          [months]="monthPoints()"
          [modules]="espacePoints()"
          [types]="typePoints()"
          [ocr]="ocrPoints()"
          listPath="/archives-generales/documents"
          moduleTitle="Documents par département"
        />

        <div class="bea-ag-dash__grid">
          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Documents par module</h2>
            </div>
            <div class="bea-ag-dash__bars">
              @for (m of modulePoints(); track m.key) {
                <a class="bea-ag-dash__bar" [routerLink]="'/archives-generales/documents'" [queryParams]="m.queryParams || {}">
                  <span>{{ m.label }}</span>
                  <span class="bea-ag-dash__track"><i [style.width.%]="modulePct(m.value)"></i></span>
                  <strong>{{ m.value | number }}</strong>
                </a>
              } @empty {
                <p class="bea-stock-page__kicker">Aucun module.</p>
              }
            </div>
          </div>

          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Documents par agence</h2>
            </div>
            <div class="bea-ag-dash__bars">
              @for (a of agencePoints(); track a.key) {
                <a class="bea-ag-dash__bar" [routerLink]="'/archives-generales/documents'" [queryParams]="a.queryParams || {}">
                  <span>{{ a.label }}</span>
                  <span class="bea-ag-dash__track"><i [style.width.%]="agencePct(a.value)"></i></span>
                  <strong>{{ a.value | number }}</strong>
                </a>
              } @empty {
                <p class="bea-stock-page__kicker">Aucune agence renseignée sur les documents.</p>
              }
            </div>
          </div>
        </div>

        <div class="bea-ag-dash__grid">
          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>État documentaire par département</h2>
            </div>
            <div class="bea-mg__table-scroll">
              <table class="bea-mg__table">
                <thead>
                  <tr><th>Département</th><th>Documents</th><th>OCR OK</th><th>OCR en cours</th><th>À vérifier</th></tr>
                </thead>
                <tbody>
                  @for (e of dash.par_espace; track e.espace_code) {
                    <tr>
                      <td>
                        <a routerLink="/archives-generales/documents" [queryParams]="{ espace_code: e.espace_code }">{{ e.label || e.espace_code }}</a>
                      </td>
                      <td>{{ e.count | number }}</td>
                      <td>{{ e.ocr_done ?? 0 | number }}</td>
                      <td>{{ e.ocr_en_cours ?? 0 | number }}</td>
                      <td>{{ e.a_verifier ?? 0 | number }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="5"><div class="bea-mg__empty"><p>Aucun département.</p></div></td></tr>
                  }
                </tbody>
              </table>
            </div>
          </div>

          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Contrôle documentaire</h2>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/archives-generales/manquants">Ouvrir</a>
            </div>
            <ul class="bea-ag-dash__ctrl">
              <li>
                <a routerLink="/archives-generales/manquants">
                  <mat-icon>warning</mat-icon>
                  <span>{{ dash.manquants | number }} documents manquants</span>
                </a>
              </li>
              <li>
                <a routerLink="/archives-generales/a-verifier">
                  <mat-icon>error</mat-icon>
                  <span>{{ dash.a_verifier | number }} documents à vérifier</span>
                </a>
              </li>
              <li>
                <a routerLink="/archives-generales/ocr">
                  <mat-icon>hourglass_top</mat-icon>
                  <span>{{ ocr().en_cours | number }} OCR en cours / attente</span>
                </a>
              </li>
              <li>
                <a routerLink="/archives-generales/a-verifier">
                  <mat-icon>document_scanner</mat-icon>
                  <span>{{ ocr().failed | number }} OCR en erreur</span>
                </a>
              </li>
              <li>
                <span class="bea-ag-dash__muted">
                  <mat-icon>folder</mat-icon>
                  {{ dash.dossiers_actifs | number }} dossiers actifs
                </span>
              </li>
            </ul>
          </div>
        </div>

        <div class="bea-ag-dash__grid">
          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Activité documentaire</h2>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/archives-generales/activite">Voir tout</a>
            </div>
            <ol class="bea-ag-dash__feed">
              @for (ev of dash.activite_recente; track ev.id) {
                <li>
                  <time>{{ ev.created_at ? (ev.created_at | date: 'HH:mm') : '—' }}</time>
                  <div>
                    <strong>{{ ev.label }}</strong>
                    <p>
                      {{ (ev.after?.['filename'] || ev.after?.['reference'] || ev.entity_id) || '—' }}
                      @if (ev.espace_code) {
                        <span>· {{ ev.espace_code }}</span>
                      }
                    </p>
                  </div>
                </li>
              } @empty {
                <li class="bea-mg__empty"><p>Aucune activité récente.</p></li>
              }
            </ol>
          </div>

          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Documents récents</h2>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/archives-generales/documents">Vue globale</a>
            </div>
            <div class="bea-mg__table-scroll">
              <table class="bea-mg__table">
                <thead>
                  <tr><th>Fichier</th><th>Département</th><th>Module</th><th>Date</th></tr>
                </thead>
                <tbody>
                  @for (r of dash.recents; track r.id) {
                    <tr>
                      <td>{{ r.title || r.filename }}</td>
                      <td>{{ r.espace_code }}</td>
                      <td>{{ r.module_code }}</td>
                      <td>{{ r.created_at ? (r.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="4"><div class="bea-mg__empty"><p>Aucun document.</p></div></td></tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        </div>
      } @else if (!erreur()) {
        <p class="bea-stock-page__kicker">Chargement…</p>
      }
    </section>
  `,
  styles: `
    .bea-ag-dash__actions { flex-wrap: wrap; }
    .bea-ag-dash__actions .bea-mg__btn {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }
    .bea-ag-dash__grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
      margin-top: 1rem;
    }
    .bea-ag-dash__bars { display: grid; gap: 0.5rem; }
    .bea-ag-dash__bar {
      display: grid;
      grid-template-columns: 8rem 1fr 2.5rem;
      gap: 0.45rem;
      align-items: center;
      text-decoration: none;
      color: inherit;
      font-size: 0.85rem;
    }
    .bea-ag-dash__track {
      height: 0.5rem;
      border-radius: 999px;
      background: #e2e8f0;
      overflow: hidden;
    }
    .bea-ag-dash__track i {
      display: block;
      height: 100%;
      background: linear-gradient(90deg, #1a5278, #3498db);
    }
    .bea-ag-dash__ctrl {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.55rem;
    }
    .bea-ag-dash__ctrl a,
    .bea-ag-dash__muted {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.55rem 0.65rem;
      border-radius: 0.5rem;
      background: #fff7ed;
      color: #9a3412;
      text-decoration: none;
      font-size: 0.9rem;
    }
    .bea-ag-dash__muted {
      background: #f8fafc;
      color: #475569;
    }
    .bea-ag-dash__feed {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.75rem;
    }
    .bea-ag-dash__feed li {
      display: grid;
      grid-template-columns: 3rem 1fr;
      gap: 0.65rem;
    }
    .bea-ag-dash__feed time {
      font-size: 0.78rem;
      color: #94a3b8;
      padding-top: 0.15rem;
    }
    .bea-ag-dash__feed strong { display: block; font-size: 0.9rem; color: #0f172a; }
    .bea-ag-dash__feed p { margin: 0.15rem 0 0; font-size: 0.82rem; color: #64748b; }
    @media (max-width: 960px) {
      .bea-ag-dash__grid { grid-template-columns: 1fr; }
    }
  `,
})
export class ArchivesGeneralesDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly d = signal<Dashboard | null>(null);
  readonly erreur = signal<string | null>(null);

  readonly ocr = computed(() => {
    const dash = this.d();
    if (!dash) {
      return { pending: 0, processing: 0, done: 0, failed: 0, en_cours: 0 };
    }
    const o = dash.ocr;
    if (o) {
      return {
        pending: o.pending,
        processing: o.processing,
        done: o.done,
        failed: o.failed,
        en_cours: o.en_cours ?? o.pending + o.processing,
      };
    }
    return {
      pending: dash.ocr_pending,
      processing: dash.ocr_processing,
      done: dash.ocr_done,
      failed: dash.ocr_failed,
      en_cours: dash.ocr_en_cours ?? dash.ocr_pending + dash.ocr_processing,
    };
  });

  readonly monthPoints = computed<ChartPoint[]>(() =>
    (this.d()?.par_mois ?? []).map((r) => ({
      label: r.label || `${String(r.month).padStart(2, '0')}/${r.year}`,
      value: r.count,
    })),
  );

  readonly espacePoints = computed<ChartPoint[]>(() =>
    (this.d()?.par_espace ?? []).map((r) => ({
      label: r.label || r.espace_code,
      value: r.count,
      key: r.espace_code,
      queryParams: { espace_code: r.espace_code },
    })),
  );

  readonly modulePoints = computed<ChartPoint[]>(() =>
    (this.d()?.par_module ?? []).map((r) => ({
      label: r.label || r.module_code,
      value: r.count,
      key: r.module_code,
      queryParams: { module_code: r.module_code },
    })),
  );

  readonly typePoints = computed<ChartPoint[]>(() =>
    (this.d()?.par_type ?? []).map((r) => ({
      label: r.type,
      value: r.count,
      key: r.type,
      queryParams: { doc_type: r.type },
    })),
  );

  readonly agencePoints = computed<ChartPoint[]>(() =>
    (this.d()?.par_agence ?? []).map((r) => ({
      label: r.label || r.agence_id,
      value: r.count,
      key: r.agence_id,
      queryParams: { agence_id: r.agence_id },
    })),
  );

  /** OCR block = exactement le même objet `ocr` que les KPI. */
  readonly ocrPoints = computed<OcrSlice[]>(() => {
    const o = this.ocr();
    return [
      { label: 'Terminés', value: o.done, key: 'done', color: '#166534' },
      { label: 'En attente', value: o.pending, key: 'pending', color: '#92400e' },
      { label: 'En cours', value: o.processing, key: 'processing', color: '#1e40af' },
      { label: 'Échec', value: o.failed, key: 'failed', color: '#991b1b' },
    ];
  });

  modulePct(value: number): number {
    const max = Math.max(...this.modulePoints().map((p) => p.value), 1);
    return (value / max) * 100;
  }

  agencePct(value: number): number {
    const max = Math.max(...this.agencePoints().map((p) => p.value), 1);
    return (value / max) * 100;
  }

  espaceLink(code: string): string {
    return '/archives-generales/documents';
  }

  ngOnInit(): void {
    this.api.get<Dashboard>('/doc-archives/general/dashboard').subscribe({
      next: (row) => this.d.set(row),
      error: () => this.erreur.set('Dashboard Archive Générale indisponible.'),
    });
  }
}
