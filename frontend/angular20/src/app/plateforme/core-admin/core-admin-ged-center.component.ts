import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DocumentViewerComponent } from '../../archives-generales/document-viewer.component';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { coreAdminOpsError } from './core-admin-ops.models';

interface HealthItem {
  code: string;
  label: string;
  status: string;
  detail: string;
}

interface Overview {
  stats: {
    total: number;
    ce_mois: number;
    cette_annee: number;
    corbeille: number;
    manquants: number;
    a_verifier: number;
    dossiers_actifs: number;
    ocr?: { pending: number; processing: number; done: number; failed: number };
    par_espace?: { code?: string; label?: string; total?: number }[];
    par_module?: { code?: string; label?: string; total?: number }[];
  };
  aujourd_hui: number;
  consultations_aujourd_hui: number;
  telechargements_aujourd_hui: number;
  health: HealthItem[];
  storage: {
    utilise_disque_octets: number | null;
    disponible_octets: number | null;
  };
  ocr_max_attempts: number;
}

interface DossierRow {
  espace_code: string;
  module_code: string;
  entity: string;
  entity_id: string;
  count: number;
  reference?: string | null;
}

interface OcrRow {
  id: string;
  filename: string;
  espace_code: string;
  module_code: string;
  ocr_status: string;
  ocr_attempts: number;
  ocr_error?: string | null;
  created_at?: string | null;
}

interface TrashRow {
  id: string;
  filename: string;
  espace_code: string;
  module_code: string;
  deleted_at?: string | null;
  deleted_by?: string | null;
  delete_reason?: string | null;
}

interface AuditRow {
  id: string;
  action: string;
  entity_id?: string | null;
  espace_code?: string | null;
  module_code?: string | null;
  created_at?: string | null;
}

interface MissingRow {
  code: string;
  label: string;
  module_code: string;
  source_type: string;
  source_id: string;
  reference?: string | null;
  detail?: string | null;
}

interface SearchRow {
  id: string;
  filename: string;
  title?: string | null;
  reference?: string | null;
  espace_code: string;
  module_code: string;
  doc_type?: string | null;
  ocr_status?: string | null;
}

const ESPACE: Record<string, string> = {
  'moyens-generaux': 'Moyens Généraux',
  comptabilite: 'Comptabilité',
  archives: 'Archives',
  rh: 'RH',
  credit: 'Crédit',
};
const MODULE: Record<string, string> = {
  'notes-frais': 'Notes de frais',
  'stock-fournitures': 'Stock & Fournitures',
  'achats-appro': 'Achats',
  'contrats-echeances': 'Contrats',
  'archives-mg': 'Archives MG',
  documents: 'Documents',
};
const ACTION: Record<string, string> = {
  archive_purge: 'Suppression définitive',
  archive_download: 'Téléchargement',
  archive_view: 'Consultation',
  archive_delete: 'Mise à la corbeille',
  archive_restore: 'Restauration',
  document_view: 'Consultation',
  document_download: 'Téléchargement',
  document_delete: 'Mise à la corbeille',
  document_restore: 'Restauration',
  document_ingest: 'Document ajouté',
  document_export: 'Export',
  document_metadata_update: 'Métadonnées modifiées',
  document_archive_operation: 'Opération d\'archive',
  document_version_create: 'Nouvelle version',
  ocr_done: 'OCR terminé',
  ocr_failed: 'OCR en échec',
  ocr_processing: 'OCR lancé',
  ocr_retry: 'OCR relancé',
};

export function espaceLabel(code: string | null | undefined): string {
  return ESPACE[code || ''] || code || '—';
}
export function moduleLabel(code: string | null | undefined): string {
  return MODULE[code || ''] || code || '—';
}
export function actionLabel(code: string): string {
  return ACTION[code] || code.replaceAll('_', ' ');
}

export function octets(value: number | null | undefined): string {
  if (value == null) return 'Non disponible';
  if (value < 1024) return `${value} o`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} Ko`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} Mo`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} Go`;
}

const scrollStyles = `
  .bea-ged-scroll { max-height: min(32rem, calc(100dvh - 18rem)); overflow: auto; }
  .bea-ged-card { border-bottom: 1px solid #e2e8f0; padding: 0.55rem 0; }
  .bea-ged-card p { margin: 0.15rem 0 0; color: #64748b; font-size: 0.84rem; }
  .bea-ged-disk { background: #fff; border: 1px solid var(--bea-line); border-radius: 0.85rem; padding: 1rem 1.1rem; margin-bottom: 1rem; }
  .bea-ged-disk__head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
  .bea-ged-disk h2, .bea-ged-disk p { margin: 0; }
  .bea-ged-disk p { margin-top: 0.55rem; color: #475569; font-size: 0.88rem; }
  .bea-ged-disk__note { color: #64748b; font-size: 0.8rem; }
  .bea-ged-meter { height: 0.7rem; border-radius: 999px; background: #e2e8f0; overflow: hidden; margin-top: 0.75rem; }
  .bea-ged-meter span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #1a5278, #2874a6); transition: width 0.5s ease; }
  .bea-ged-file { display: grid; grid-template-columns: auto 1fr auto; gap: 0.75rem; align-items: center; padding: 0.7rem 0; border-bottom: 1px solid #e2e8f0; }
  .bea-ged-file strong, .bea-ged-file small, .bea-ged-file em { display: block; }
  .bea-ged-file small, .bea-ged-file em { color: #64748b; font-style: normal; font-size: 0.8rem; }
  .bea-ged-empty { color: #64748b; }
  .bea-ged-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 0.85rem; }
  .bea-ged-miss { background: #fff; border: 1px solid #fed7aa; border-left: 4px solid #c2410c; border-radius: 0.85rem; padding: 0.95rem 1rem; display: flex; flex-direction: column; gap: 0.35rem; animation: bea-admin-rise 0.4s ease both; }
  .bea-ged-miss strong { font-size: 1.02rem; }
  .bea-ged-miss p { margin: 0; color: #475569; }
  .bea-ged-chip { display: inline-flex; align-items: center; width: fit-content; padding: 0.15rem 0.5rem; border-radius: 999px; background: #fff7ed; color: #9a3412; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; }
  .bea-ged-meta { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .bea-ged-meta span { background: #f1f5f9; color: #334155; border-radius: 999px; padding: 0.15rem 0.5rem; font-size: 0.75rem; }
  .bea-ged-miss a { margin-top: 0.35rem; align-self: flex-start; }
  .bea-ged-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 0.75rem; align-items: center; padding: 0.8rem 0.15rem; border-bottom: 1px solid #e2e8f0; }
  .bea-ged-row strong, .bea-ged-row small { display: block; }
  .bea-ged-row strong { overflow-wrap: anywhere; }
  .bea-ged-row small { color: #64748b; font-size: 0.8rem; }
  .bea-ged-actions { display: flex; gap: 0.35rem; flex-shrink: 0; }
  .bea-ged-icon { width: 2.1rem; height: 2.1rem; border-radius: 0.55rem; border: 1px solid var(--bea-line); background: #fff; color: #1a5278; display: grid; place-items: center; cursor: pointer; }
  .bea-ged-icon:hover { border-color: #1a5278; transform: translateY(-1px); }
  .bea-ged-icon--danger { color: #b91c1c; }
  .bea-ged-icon--danger:hover { border-color: #b91c1c; background: #fef2f2; }
  .bea-ged-doc { display: flex; align-items: center; gap: 0.5rem; font-weight: 650; }
  .bea-ged-modal { position: fixed; inset: 0; z-index: 80; background: rgb(15 23 42 / 0.45); display: grid; place-items: center; padding: 1rem; }
  .bea-ged-dialog { width: min(28rem, 100%); background: #fff; border-radius: 0.9rem; padding: 1.1rem 1.2rem; box-shadow: 0 24px 60px rgb(15 23 42 / 0.25); }
  .bea-ged-dialog h2 { margin: 0 0 0.4rem; font-size: 1.05rem; }
  .bea-ged-dialog p { margin: 0 0 0.8rem; color: #475569; }
  .bea-ged-dialog label { display: grid; gap: 0.3rem; font-size: 0.82rem; font-weight: 650; }
  .bea-ged-dialog input { min-height: 2.3rem; border: 1px solid #cbd5e1; border-radius: 0.45rem; padding: 0 0.6rem; font: inherit; }
  .bea-ged-dialog__actions { display: flex; justify-content: flex-end; gap: 0.45rem; margin-top: 0.85rem; }
  .bea-ged-time { display: grid; gap: 0; }
  .bea-ged-event { display: grid; grid-template-columns: 1.1rem 1fr; gap: 0.7rem; }
  .bea-ged-event__rail { position: relative; }
  .bea-ged-event__rail::before { content: ''; position: absolute; left: 0.38rem; top: 0.9rem; bottom: -0.2rem; width: 2px; background: #e2e8f0; }
  .bea-ged-event:last-child .bea-ged-event__rail::before { display: none; }
  .bea-ged-dot { width: 0.85rem; height: 0.85rem; border-radius: 50%; margin-top: 0.85rem; background: #1a5278; box-shadow: 0 0 0 3px #e8f1f8; }
  .bea-ged-event[data-tone='danger'] .bea-ged-dot { background: #b91c1c; box-shadow: 0 0 0 3px #fee2e2; }
  .bea-ged-event[data-tone='ok'] .bea-ged-dot { background: #15803d; box-shadow: 0 0 0 3px #dcfce7; }
  .bea-ged-event[data-tone='warn'] .bea-ged-dot { background: #c2410c; box-shadow: 0 0 0 3px #ffedd5; }
  .bea-ged-event article { background: #fff; border: 1px solid #e2e8f0; border-radius: 0.75rem; padding: 0.7rem 0.85rem; margin-bottom: 0.55rem; }
  .bea-ged-event strong { display: block; }
  .bea-ged-event p { margin: 0.2rem 0 0; color: #64748b; font-size: 0.82rem; }
  .bea-ged-settings { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: 0.85rem; }
  .bea-ged-set { background: #fff; border: 1px solid var(--bea-line); border-radius: 0.85rem; padding: 0.95rem 1rem; animation: bea-admin-rise 0.45s ease both; }
  .bea-ged-set h2 { display: flex; align-items: center; gap: 0.45rem; margin: 0 0 0.45rem; font-size: 0.98rem; }
  .bea-ged-set p, .bea-ged-set li { color: #475569; font-size: 0.86rem; }
  .bea-ged-set ul { margin: 0; padding-left: 1.05rem; }
  .bea-ged-set li + li { margin-top: 0.25rem; }
  .bea-ged-levels { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.45rem; }
  .bea-ged-levels span { border-radius: 999px; padding: 0.18rem 0.55rem; font-size: 0.75rem; font-weight: 700; }
  .bea-ged-levels span:nth-child(1) { background: #ecfdf5; color: #166534; }
  .bea-ged-levels span:nth-child(2) { background: #eff6ff; color: #1e40af; }
  .bea-ged-levels span:nth-child(3) { background: #fff7ed; color: #9a3412; }
  .bea-ged-levels span:nth-child(4) { background: #fef2f2; color: #991b1b; }
  @media (prefers-reduced-motion: reduce) {
    .bea-ged-miss, .bea-ged-set, .bea-ged-meter span, .bea-ged-icon { animation: none; transition: none; }
  }
`;

@Component({
  selector: 'bea-core-admin-ged-dash',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Dashboard GED</h1>
          <p>Chiffres lus dans la GED centrale. Un état n'est affiché qu'après un contrôle réel.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-admin-dash__error">{{ erreur() }}</p> }
      @if (data(); as d) {
        <div class="bea-admin-kpis">
          @for (card of cards(d); track card.label) {
            <a class="bea-admin-kpi" [attr.data-tone]="card.tone" [routerLink]="card.link">
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">{{ card.label }}</p>
                <p class="bea-admin-kpi__value">{{ card.value }}</p>
              </div>
            </a>
          }
        </div>
        <div class="bea-admin-panel">
          <h2>État du système documentaire</h2>
          <div class="bea-ged-health">
            @for (item of d.health; track item.code) {
              <article [attr.data-status]="item.status">
                <strong>{{ item.label }}</strong>
                <span>{{ item.status }}</span>
                <p>{{ item.detail }}</p>
              </article>
            }
          </div>
        </div>
      }
    </section>
  `,
  styles: `
    .bea-admin-kpi { text-decoration: none; color: inherit; }
    .bea-ged-health { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.7rem; }
    .bea-ged-health article { border: 1px solid #e2e8f0; border-radius: 0.7rem; padding: 0.75rem; }
    .bea-ged-health span { margin-left: 0.4rem; font-size: 0.72rem; font-weight: 700; }
    .bea-ged-health article[data-status='OK'] span { color: #166534; }
    .bea-ged-health article[data-status='ATTENTION'] span { color: #92400e; }
    .bea-ged-health article[data-status='ERREUR'] span { color: #991b1b; }
    .bea-ged-health article[data-status='NON DISPONIBLE'] span { color: #475569; }
    .bea-ged-health p { margin: 0.25rem 0 0; color: #64748b; font-size: 0.84rem; }
    @media (max-width: 900px) { .bea-ged-health { grid-template-columns: 1fr; } }
  `,
})
export class CoreAdminGedDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly data = signal<Overview | null>(null);
  readonly erreur = signal('');

  ngOnInit(): void {
    this.api.get<Overview>('/plateforme/admin/ged/overview').subscribe({
      next: (row) => this.data.set(row),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Dashboard GED indisponible.')),
    });
  }

  cards(d: Overview) {
    const ocr = d.stats.ocr;
    return [
      { label: 'Documents', value: d.stats.total, tone: 'blue', link: '/admin/ged/documents' },
      { label: 'Ce mois', value: d.stats.ce_mois, tone: 'teal', link: '/admin/ged/documents' },
      { label: 'Cette année', value: d.stats.cette_annee, tone: 'teal', link: '/admin/ged/documents' },
      { label: "Aujourd'hui", value: d.aujourd_hui, tone: 'blue', link: '/admin/ged/documents' },
      { label: 'Dossiers', value: d.stats.dossiers_actifs, tone: 'amber', link: '/admin/ged/dossiers' },
      { label: 'OCR terminés', value: ocr?.done ?? 0, tone: 'teal', link: '/admin/ged/ocr' },
      { label: 'OCR en attente + cours', value: (ocr?.pending ?? 0) + (ocr?.processing ?? 0), tone: 'amber', link: '/admin/ged/ocr' },
      { label: 'OCR en erreur', value: ocr?.failed ?? 0, tone: 'amber', link: '/admin/ged/ocr' },
      { label: 'Manquants', value: d.stats.manquants, tone: 'amber', link: '/admin/ged/manquants' },
      { label: 'À vérifier', value: d.stats.a_verifier, tone: 'amber', link: '/admin/ged/documents' },
      { label: 'Corbeille', value: d.stats.corbeille, tone: 'blue', link: '/admin/ged/corbeille' },
      { label: 'Consultations du jour', value: d.consultations_aujourd_hui, tone: 'teal', link: '/admin/ged/audit' },
      { label: 'Téléchargements du jour', value: d.telechargements_aujourd_hui, tone: 'teal', link: '/admin/ged/audit' },
      { label: 'Disque utilisé', value: octets(d.storage.utilise_disque_octets), tone: 'blue', link: '/admin/ged/stockage' },
      { label: 'Disque disponible', value: octets(d.storage.disponible_octets), tone: 'teal', link: '/admin/ged/stockage' },
    ];
  }
}

@Component({
  selector: 'bea-core-admin-ged-dossiers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head"><div><h1>Dossiers</h1><p>Même regroupement que les archives : espace, module, opération. Pas de seconde table.</p></div></header>
      @if (erreur()) { <p class="bea-admin-dash__error">{{ erreur() }}</p> }
      <div class="bea-admin-panel bea-ged-scroll">
        @for (d of rows(); track d.espace_code + d.entity_id) {
          <article class="bea-ged-card">
            <strong>{{ d.reference || d.entity }}</strong>
            <p>{{ d.espace_code }} · {{ d.module_code }} · {{ d.count }} document(s)</p>
          </article>
        } @empty { <p class="bea-admin-panel__empty">Aucun dossier.</p> }
      </div>
    </section>
  `,
  styles: scrollStyles,
})
export class CoreAdminGedDossiersComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<DossierRow[]>([]);
  readonly erreur = signal('');
  ngOnInit(): void {
    this.api.get<DossierRow[]>('/plateforme/admin/ged/dossiers').subscribe({
      next: (rows) => this.rows.set(rows ?? []),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Dossiers indisponibles.')),
    });
  }
}

@Component({
  selector: 'bea-core-admin-ged-ocr',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DocumentViewerComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>OCR</h1>
          <p>Maximum {{ maxAttempts() }} passages (1 essai + 2 relances automatiques). Aucun retry infini.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-admin-dash__error">{{ erreur() }}</p> }
      <div class="bea-admin-kpis">
        @for (k of counts(); track k.key) {
          <button type="button" class="bea-admin-kpi" (click)="load(k.key)">
            <div class="bea-admin-kpi__copy"><p class="bea-admin-kpi__label">{{ k.label }}</p><p class="bea-admin-kpi__value">{{ k.value }}</p></div>
          </button>
        }
      </div>
      <div class="bea-admin-panel bea-ged-scroll">
        <table class="bea-admin-table">
          <thead><tr><th>Document</th><th>Département</th><th>Module</th><th>Statut</th><th>Tentatives</th><th>Erreur</th><th></th></tr></thead>
          <tbody>
            @for (row of rows(); track row.id) {
              <tr>
                <td>{{ row.filename }}</td>
                <td>{{ row.espace_code }}</td>
                <td>{{ row.module_code }}</td>
                <td>{{ row.ocr_status }}</td>
                <td>{{ row.ocr_attempts }} / {{ maxAttempts() }}</td>
                <td>{{ row.ocr_error || '—' }}</td>
                <td>
                  <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="viewerId.set(row.id)">Voir</button>
                  @if (row.ocr_status !== 'done' && row.ocr_attempts < maxAttempts()) {
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="retry(row)">Relancer</button>
                  }
                </td>
              </tr>
            } @empty { <tr><td colspan="7">Aucun traitement OCR.</td></tr> }
          </tbody>
        </table>
      </div>
    </section>
    <bea-document-viewer [documentId]="viewerId()" (closed)="viewerId.set(null)" (openRelated)="viewerId.set($event)" />
  `,
  styles: scrollStyles,
})
export class CoreAdminGedOcrComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<OcrRow[]>([]);
  readonly maxAttempts = signal(3);
  readonly counts = signal<{ key: string; label: string; value: number }[]>([]);
  readonly erreur = signal('');
  readonly viewerId = signal<string | null>(null);

  ngOnInit(): void { this.load('pending'); }

  load(status: string): void {
    this.api.get<{ counts: Record<string, number>; max_attempts: number; items: OcrRow[] }>('/plateforme/admin/ged/ocr', { status, page: 1, size: 50 }).subscribe({
      next: (res) => {
        this.rows.set(res.items ?? []);
        this.maxAttempts.set(res.max_attempts || 3);
        const c = res.counts || {};
        this.counts.set([
          { key: 'pending', label: 'En attente', value: c['pending'] ?? 0 },
          { key: 'processing', label: 'En cours', value: c['processing'] ?? 0 },
          { key: 'done', label: 'Terminés', value: c['done'] ?? 0 },
          { key: 'failed', label: 'Échecs', value: c['failed'] ?? 0 },
        ]);
      },
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'OCR indisponible.')),
    });
  }

  retry(row: OcrRow): void {
    this.api.post(`/documents/${row.id}/retry-ocr`, {}).subscribe({
      next: () => this.load(row.ocr_status),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Relance refusée.')),
    });
  }
}

@Component({
  selector: 'bea-core-admin-ged-storage',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Stockage</h1>
          <p>Disque local de la GED. Le chemin interne n'est pas affiché.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-admin-dash__error">{{ erreur() }}</p> }
      @if (data(); as d) {
        <div class="bea-admin-kpis">
          <article class="bea-admin-kpi">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="dns" /></span>
            <div class="bea-admin-kpi__copy"><p class="bea-admin-kpi__label">Provider</p><p class="bea-admin-kpi__value">{{ d.provider }}</p></div>
          </article>
          <article class="bea-admin-kpi">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="description" /></span>
            <div class="bea-admin-kpi__copy"><p class="bea-admin-kpi__label">Documents actifs</p><p class="bea-admin-kpi__value">{{ d.documents }}</p></div>
          </article>
          <article class="bea-admin-kpi" data-tone="alert">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="delete" /></span>
            <div class="bea-admin-kpi__copy"><p class="bea-admin-kpi__label">Corbeille</p><p class="bea-admin-kpi__value">{{ d.corbeille }}</p></div>
          </article>
          <article class="bea-admin-kpi">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="data_usage" /></span>
            <div class="bea-admin-kpi__copy"><p class="bea-admin-kpi__label">Volume en base</p><p class="bea-admin-kpi__value">{{ size(d.taille_metadonnees_octets) }}</p></div>
          </article>
        </div>
        <article class="bea-ged-disk">
          <div class="bea-ged-disk__head">
            <h2>Occupation du disque serveur</h2>
            <strong>{{ usedLabel(d) }}</strong>
          </div>
          <div class="bea-ged-meter" aria-hidden="true"><span [style.width.%]="usedPct(d)"></span></div>
          <p>Disponible {{ size(d.disponible_octets) }} sur {{ size(d.capacite_octets) }}. Cette jauge mesure le disque, pas seulement les fichiers GED.</p>
          <p class="bea-ged-disk__note">{{ d.erreurs_detail }} Pas de bucket : le stockage objet n'est pas branché.</p>
        </article>
        <div class="bea-admin-panel">
          <h2>Fichiers actifs récents</h2>
          @if (!d.documents && d.corbeille) {
            <p class="bea-ged-empty">Aucun document actif. {{ d.corbeille }} fichier(s) sont dans la corbeille.</p>
          }
          <div class="bea-ged-scroll">
            @for (row of d.recents || []; track row.id) {
              <div class="bea-ged-file">
                <bea-admin-icon name="description" />
                <div>
                  <strong>{{ row.filename }}</strong>
                  <small>{{ dept(row.espace_code) }} · {{ mod(row.module_code) }} · {{ row.created_at | date: 'dd/MM/yyyy HH:mm' }}</small>
                </div>
                <em>{{ size(row.size_bytes) }}</em>
              </div>
            } @empty { <p class="bea-admin-panel__empty">Aucun fichier actif.</p> }
          </div>
        </div>
      }
    </section>
  `,
  styles: scrollStyles,
})
export class CoreAdminGedStorageComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly data = signal<StorageShape | null>(null);
  readonly erreur = signal('');
  readonly size = octets;
  readonly dept = espaceLabel;
  readonly mod = moduleLabel;

  ngOnInit(): void {
    this.api.get<StorageShape>('/plateforme/admin/ged/storage').subscribe({
      next: (row) => this.data.set(row),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Stockage indisponible.')),
    });
  }

  usedPct(d: StorageShape): number {
    if (!d.capacite_octets || d.disponible_octets == null) return 0;
    return Math.min(100, Math.max(0, ((d.capacite_octets - d.disponible_octets) / d.capacite_octets) * 100));
  }

  usedLabel(d: StorageShape): string {
    if (d.capacite_octets == null || d.disponible_octets == null) return 'Capacité non lue';
    return `${octets(d.capacite_octets - d.disponible_octets)} utilisés`;
  }
}

interface StorageShape {
  provider: string;
  bucket: string | null;
  documents: number;
  corbeille: number;
  taille_metadonnees_octets: number;
  capacite_octets: number | null;
  disponible_octets: number | null;
  erreurs_detail: string;
  recents?: { id: string; filename: string; size_bytes: number; espace_code: string; module_code?: string; created_at: string | null }[];
}

@Component({
  selector: 'bea-core-admin-ged-trash',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Corbeille GED</h1>
          <p>{{ rows().length }} document(s). La suppression définitive demande la phrase CONFIRMER et reste journalisée.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-admin-dash__error">{{ erreur() }}</p> }
      @if (msg()) { <p class="bea-admin-note">{{ msg() }}</p> }
      <div class="bea-admin-panel bea-ged-scroll">
        @for (row of rows(); track row.id) {
          <article class="bea-ged-row">
            <bea-admin-icon name="draft" />
            <div>
              <strong>{{ row.filename }}</strong>
              <small>{{ dept(row.espace_code) }} · {{ mod(row.module_code) }}</small>
              <small>{{ row.deleted_by || 'Auteur non renseigné' }} · {{ row.deleted_at | date: 'dd/MM/yyyy HH:mm' }} · {{ row.delete_reason || 'Sans motif' }}</small>
            </div>
            <div class="bea-ged-actions">
              <button type="button" class="bea-ged-icon" aria-label="Restaurer" (click)="restore(row)"><bea-admin-icon name="restore" /></button>
              <button type="button" class="bea-ged-icon bea-ged-icon--danger" aria-label="Supprimer définitivement" (click)="open(row)"><bea-admin-icon name="delete_forever" /></button>
            </div>
          </article>
        } @empty { <p class="bea-admin-panel__empty">La corbeille est vide.</p> }
      </div>
      @if (target(); as row) {
        <div class="bea-ged-modal" (click)="target.set(null)">
          <form class="bea-ged-dialog" (click)="$event.stopPropagation()" (ngSubmit)="purge(row)">
            <h2>Suppression définitive</h2>
            <p>{{ row.filename }} sera retiré de la GED et du disque. Cette action est journalisée.</p>
            <label>Tapez CONFIRMER<input [(ngModel)]="phrase" name="phrase" autocomplete="off" /></label>
            <div class="bea-ged-dialog__actions">
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="target.set(null)">Annuler</button>
              <button type="submit" class="bea-admin-btn" [disabled]="phrase !== 'CONFIRMER'">Supprimer</button>
            </div>
          </form>
        </div>
      }
    </section>
  `,
  styles: scrollStyles,
})
export class CoreAdminGedTrashComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<TrashRow[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly target = signal<TrashRow | null>(null);
  readonly dept = espaceLabel;
  readonly mod = moduleLabel;
  phrase = '';

  ngOnInit(): void { this.load(); }

  load(): void {
    this.api.get<{ items: TrashRow[] }>('/plateforme/admin/ged/trash', { page: 1, size: 50 }).subscribe({
      next: (res) => this.rows.set(res.items ?? []),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Corbeille indisponible.')),
    });
  }

  open(row: TrashRow): void {
    this.phrase = '';
    this.target.set(row);
  }

  restore(row: TrashRow): void {
    this.api.post(`/plateforme/admin/ged/documents/${row.id}/restore`, {}).subscribe({
      next: () => { this.msg.set('Document restauré.'); this.load(); },
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Restauration refusée.')),
    });
  }

  purge(row: TrashRow): void {
    this.api.post(`/plateforme/admin/ged/documents/${row.id}/purge`, { confirmation_phrase: this.phrase }).subscribe({
      next: () => { this.target.set(null); this.phrase = ''; this.msg.set('Document supprimé définitivement.'); this.load(); },
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Suppression définitive refusée.')),
    });
  }
}

@Component({
  selector: 'bea-core-admin-ged-missing',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Documents manquants</h1>
          <p>Règles branchées : opérations Moyens Généraux sans pièce dans la GED. Les autres départements ne sont pas inventés.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-admin-dash__error">{{ erreur() }}</p> }
      <div class="bea-admin-kpis">
        <article class="bea-admin-kpi" data-tone="alert">
          <span class="bea-admin-kpi__icon"><bea-admin-icon name="folder_off" /></span>
          <div class="bea-admin-kpi__copy">
            <p class="bea-admin-kpi__label">Pièces absentes</p>
            <p class="bea-admin-kpi__value">{{ rows().length }}</p>
          </div>
        </article>
      </div>
      <div class="bea-ged-grid">
        @for (row of rows(); track row.source_type + row.source_id) {
          <article class="bea-ged-miss">
            <span class="bea-ged-chip">Pièce absente</span>
            <strong>{{ row.reference || row.code }}</strong>
            <p>{{ row.label }}</p>
            <div class="bea-ged-meta">
              <span>{{ mod(row.module_code) }}</span>
              <span>{{ row.detail || 'Pièce attendue absente' }}</span>
            </div>
            <a class="bea-admin-btn" [routerLink]="['/archives-generales/numeriser']" [queryParams]="{ module_code: row.module_code, entity: row.source_type, entity_id: row.source_id, reference: row.reference || '' }">
              <bea-admin-icon name="upload_file" /> Ajouter
            </a>
          </article>
        } @empty { <p class="bea-admin-panel__empty">Aucun document manquant.</p> }
      </div>
    </section>
  `,
  styles: scrollStyles,
})
export class CoreAdminGedMissingComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<MissingRow[]>([]);
  readonly erreur = signal('');
  readonly mod = moduleLabel;
  ngOnInit(): void {
    this.api.get<MissingRow[]>('/plateforme/admin/ged/manquants').subscribe({
      next: (rows) => this.rows.set(rows ?? []),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Liste des manquants indisponible.')),
    });
  }
}

@Component({
  selector: 'bea-core-admin-ged-audit',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Audit documentaire</h1>
          <p>{{ rows().length }} événement(s) lus dans le journal unique. Aucun second journal n'est tenu.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-admin-dash__error">{{ erreur() }}</p> }
      <div class="bea-ged-scroll bea-ged-time">
        @for (row of rows(); track row.id) {
          <div class="bea-ged-event" [attr.data-tone]="tone(row.action)">
            <div class="bea-ged-event__rail"><span class="bea-ged-dot"></span></div>
            <article>
              <strong>{{ label(row.action) }}</strong>
              <p>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' }} · {{ dept(row.espace_code) }} · {{ mod(row.module_code) }}</p>
            </article>
          </div>
        } @empty { <p class="bea-admin-panel__empty">Aucun événement documentaire.</p> }
      </div>
    </section>
  `,
  styles: scrollStyles,
})
export class CoreAdminGedAuditComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<AuditRow[]>([]);
  readonly erreur = signal('');
  readonly label = actionLabel;
  readonly dept = espaceLabel;
  readonly mod = moduleLabel;

  tone(action: string): string {
    if (action.includes('purge') || action.includes('delete') || action.includes('failed')) return 'danger';
    if (action.includes('restore') || action.includes('done') || action.includes('ingest')) return 'ok';
    if (action.includes('retry') || action.includes('processing')) return 'warn';
    return 'info';
  }

  ngOnInit(): void {
    this.api.get<{ items: AuditRow[] }>('/plateforme/admin/ged/audit', { page: 1, size: 40 }).subscribe({
      next: (res) => this.rows.set(res.items ?? []),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Audit documentaire indisponible.')),
    });
  }
}

@Component({
  selector: 'bea-core-admin-ged-search',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DocumentViewerComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head"><div><h1>Recherche documentaire</h1><p>Plein texte PostgreSQL (nom, référence, texte OCR). Le périmètre reste celui du compte connecté.</p></div></header>
      <form class="bea-admin-toolbar" (ngSubmit)="run()">
        <label class="bea-admin-field bea-admin-toolbar__search"><span>Recherche</span><input [(ngModel)]="q" name="q" placeholder="Nom, référence, contenu OCR…" /></label>
        <button type="submit" class="bea-admin-btn">Rechercher</button>
      </form>
      @if (erreur()) { <p class="bea-admin-dash__error">{{ erreur() }}</p> }
      @if (!started()) {
        <p class="bea-admin-panel__empty">Saisissez un critère pour lancer la recherche.</p>
      } @else {
        <div class="bea-admin-panel bea-ged-scroll">
          @for (row of rows(); track row.id) {
            <article class="bea-ged-card">
              <strong>{{ row.reference || row.title || row.filename }}</strong>
              <p>{{ row.espace_code }} · {{ row.module_code }} · {{ row.doc_type || '—' }} · OCR {{ row.ocr_status || '—' }}</p>
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="viewerId.set(row.id)">Voir</button>
            </article>
          } @empty { <p class="bea-admin-panel__empty">Aucun document.</p> }
        </div>
      }
    </section>
    <bea-document-viewer [documentId]="viewerId()" (closed)="viewerId.set(null)" (openRelated)="viewerId.set($event)" />
  `,
  styles: scrollStyles,
})
export class CoreAdminGedSearchComponent {
  private readonly api = inject(ApiService);
  q = '';
  readonly started = signal(false);
  readonly rows = signal<SearchRow[]>([]);
  readonly erreur = signal('');
  readonly viewerId = signal<string | null>(null);

  run(): void {
    this.started.set(true);
    this.api.get<{ items: SearchRow[] }>('/doc-archives/general', { q: this.q, search_ocr: true, page: 1, size: 30 }).subscribe({
      next: (res) => this.rows.set(res.items ?? []),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Recherche refusée pour ce compte.')),
    });
  }
}

@Component({
  selector: 'bea-core-admin-ged-settings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Paramètres GED</h1>
          <p>Règles réellement appliquées par le service documentaire. Ces cartes décrivent le comportement en vigueur, elles ne sont pas un formulaire d'enregistrement.</p>
        </div>
      </header>
      <div class="bea-ged-settings">
        <article class="bea-ged-set">
          <h2><bea-admin-icon name="upload_file" /> Formats acceptés</h2>
          <p>L'import refuse tout autre type.</p>
          <ul>
            <li>PDF</li>
            <li>JPG, JPEG, PNG</li>
          </ul>
        </article>
        <article class="bea-ged-set">
          <h2><bea-admin-icon name="lock" /> Confidentialité</h2>
          <p>Chaque document porte un niveau. Le périmètre département est contrôlé côté serveur.</p>
          <div class="bea-ged-levels">
            <span>public</span>
            <span>internal</span>
            <span>confidential</span>
            <span>restricted</span>
          </div>
        </article>
        <article class="bea-ged-set">
          <h2><bea-admin-icon name="document_scanner" /> OCR</h2>
          <ul>
            <li>3 passages au maximum.</li>
            <li>La tâche s'arrête après deux relances automatiques.</li>
            <li>Une relance manuelle est refusée une fois ce plafond atteint.</li>
            <li>Le texte reconnu alimente la recherche plein texte.</li>
          </ul>
        </article>
        <article class="bea-ged-set">
          <h2><bea-admin-icon name="dns" /> Stockage</h2>
          <ul>
            <li>Disque local, pas de bucket.</li>
            <li>Le nom affiché n'est pas le chemin du fichier.</li>
            <li>Le chemin interne n'est pas renvoyé à l'écran.</li>
            <li>Aucun journal d'erreur storage n'est encore enregistré.</li>
          </ul>
        </article>
        <article class="bea-ged-set">
          <h2><bea-admin-icon name="account_tree" /> Architecture</h2>
          <ul>
            <li>Une seule table : ged_documents.</li>
            <li>Archive Générale, archives des départements et CORE ADMIN lisent cette table.</li>
            <li>Les dossiers sont des regroupements, pas une seconde table.</li>
            <li>Les pièces immobilisations restent hors de cette GED.</li>
          </ul>
        </article>
        <article class="bea-ged-set">
          <h2><bea-admin-icon name="delete" /> Corbeille</h2>
          <ul>
            <li>La suppression métier est une mise à la corbeille.</li>
            <li>La purge définitive exige la phrase CONFIRMER.</li>
            <li>La purge est refusée si le document n'est pas déjà en corbeille.</li>
            <li>Chaque purge est écrite dans le journal d'audit.</li>
          </ul>
        </article>
        <article class="bea-ged-set">
          <h2><bea-admin-icon name="manage_search" /> Recherche</h2>
          <ul>
            <li>Plein texte PostgreSQL, configuration française.</li>
            <li>Nom, référence et texte OCR sont cherchés ensemble.</li>
            <li>Pas de moteur de recherche séparé.</li>
          </ul>
        </article>
        <article class="bea-ged-set">
          <h2><bea-admin-icon name="admin_panel_settings" /> Accès</h2>
          <ul>
            <li>CORE ADMIN : permission de paramétrage de la plateforme.</li>
            <li>Lecture, écriture, téléchargement et export GED restent des droits distincts.</li>
            <li>Un compte sans le département du document ne le voit pas.</li>
          </ul>
        </article>
      </div>
    </section>
  `,
  styles: scrollStyles,
})
export class CoreAdminGedSettingsComponent {}
