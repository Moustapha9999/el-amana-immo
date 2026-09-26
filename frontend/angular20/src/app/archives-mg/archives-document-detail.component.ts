import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ApiService } from '../core/services/api.service';

interface Doc {
  id: string;
  filename: string;
  title?: string | null;
  description?: string | null;
  reference?: string | null;
  doc_type?: string | null;
  module_code: string;
  espace_code: string;
  entity: string;
  entity_id: string;
  created_at: string | null;
  date_document?: string | null;
  mime_type?: string | null;
  size_bytes: number;
  version: number;
  version_comment?: string | null;
  parent_document_id?: string | null;
  ocr_status?: string | null;
  ocr_text?: string | null;
  ocr_error?: string | null;
  ocr_attempts?: number;
  security_level?: string | null;
  uploaded_by_id?: string | null;
}

interface AuditEvent {
  id: string;
  action: string;
  created_at: string | null;
  user_id?: string | null;
  after?: Record<string, unknown> | null;
}

type Tab = 'info' | 'ocr' | 'relations' | 'versions' | 'historique';

@Component({
  selector: 'bea-archives-document-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatIconModule, RouterLink],
  template: `
    <section class="bea-mg bea-doc-detail">
      <header class="bea-mg__head">
        <div>
          <a class="bea-doc-detail__back" routerLink="/archives-mg/documents">
            <mat-icon>arrow_back</mat-icon> Documents
          </a>
          <p class="bea-stock-page__kicker">Fiche documentaire</p>
          <h1>{{ doc()?.title || doc()?.filename || 'Document' }}</h1>
        </div>
        <div class="bea-mg__actions">
          @if (doc(); as d) {
            <span class="bea-ocr-badge" [attr.data-status]="d.ocr_status || 'pending'">
              {{ ocrLabel(d.ocr_status) }}
            </span>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="download()">
              <mat-icon>download</mat-icon> Télécharger
            </button>
            @if (d.ocr_status === 'failed') {
              <button type="button" class="bea-mg__btn" (click)="retryOcr()">
                <mat-icon>refresh</mat-icon> Relancer OCR
              </button>
            }
          }
        </div>
      </header>

      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (msg()) { <p class="bea-stock-page__ok">{{ msg() }}</p> }
      @if (loading()) { <p class="bea-stock-page__kicker">Chargement…</p> }

      @if (doc(); as d) {
        <div class="bea-doc-detail__layout">
          <div class="bea-mg__panel bea-doc-detail__preview">
            <div class="bea-mg__panel-top">
              <h2>Aperçu</h2>
              <div class="bea-doc-detail__zoom">
                <button type="button" class="bea-mg__icon-btn" (click)="zoomOut()" title="Zoom -"><mat-icon>zoom_out</mat-icon></button>
                <button type="button" class="bea-mg__icon-btn" (click)="zoomIn()" title="Zoom +"><mat-icon>zoom_in</mat-icon></button>
              </div>
            </div>
            @if (previewUrl()) {
              @if (isImage(d)) {
                <img [src]="previewUrl()" [style.transform]="'scale(' + zoom() + ')'" alt="Aperçu document" />
              } @else if (isPdf(d)) {
                <iframe [src]="safePreview()" title="Aperçu PDF" [style.transform]="'scale(' + zoom() + ')'"></iframe>
              } @else {
                <div class="bea-mg__empty">
                  <mat-icon>description</mat-icon>
                  <p>Aperçu non disponible pour ce type. Téléchargez le fichier.</p>
                </div>
              }
            } @else {
              <div class="bea-mg__empty"><p>Chargement de l'aperçu…</p></div>
            }
          </div>

          <div class="bea-mg__panel">
            <nav class="bea-doc-detail__tabs" role="tablist">
              @for (t of tabs; track t.id) {
                <button
                  type="button"
                  role="tab"
                  [attr.aria-selected]="tab() === t.id"
                  [class.active]="tab() === t.id"
                  (click)="tab.set(t.id)"
                >{{ t.label }}</button>
              }
            </nav>

            @if (tab() === 'info') {
              <dl class="bea-doc-detail__meta">
                <div><dt>Référence</dt><dd>{{ d.reference || '—' }}</dd></div>
                <div><dt>Type</dt><dd>{{ d.doc_type || d.entity }}</dd></div>
                <div><dt>Département</dt><dd>{{ d.espace_code }}</dd></div>
                <div><dt>Module</dt><dd>{{ d.module_code }}</dd></div>
                <div><dt>Date</dt><dd>{{ (d.date_document || d.created_at) ? ((d.date_document || d.created_at) | date: 'dd/MM/yyyy') : '—' }}</dd></div>
                <div><dt>Version</dt><dd>{{ d.version }}</dd></div>
                <div><dt>Sécurité</dt><dd>{{ d.security_level || 'internal' }}</dd></div>
                <div><dt>Taille</dt><dd>{{ sizeLabel(d.size_bytes) }}</dd></div>
                <div class="full"><dt>Description</dt><dd>{{ d.description || '—' }}</dd></div>
              </dl>
              <a
                class="bea-mg__btn"
                [routerLink]="['/archives-mg/dossiers', d.module_code, d.entity, d.entity_id]"
              >
                <mat-icon>account_tree</mat-icon> Ouvrir le dossier
              </a>
            }

            @if (tab() === 'ocr') {
              @if (d.ocr_status === 'done' && d.ocr_text) {
                <pre class="bea-doc-detail__ocr">{{ d.ocr_text }}</pre>
              } @else if (d.ocr_status === 'failed') {
                <p class="bea-stock-page__error">{{ d.ocr_error || 'OCR échoué' }}</p>
              } @else {
                <p class="bea-stock-page__kicker">OCR {{ ocrLabel(d.ocr_status).toLowerCase() }}…</p>
              }
            }

            @if (tab() === 'relations') {
              <ul class="bea-doc-detail__list">
                @for (r of relations(); track r.id) {
                  <li>
                    <a [routerLink]="['/archives-mg/documents', r.id]">{{ r.title || r.filename }}</a>
                    <small>{{ r.doc_type || r.entity }} · v{{ r.version }}</small>
                  </li>
                } @empty {
                  <li class="bea-mg__empty"><p>Aucun document lié sur cette opération.</p></li>
                }
              </ul>
            }

            @if (tab() === 'versions') {
              <ol class="bea-doc-detail__timeline">
                @for (v of versions(); track v.id) {
                  <li>
                    <strong>Version {{ v.version }}</strong>
                    <span>{{ v.created_at ? (v.created_at | date: 'dd/MM/yyyy HH:mm') : '' }}</span>
                    <p>{{ v.version_comment || v.filename }}</p>
                    <a [routerLink]="['/archives-mg/documents', v.id]">Voir</a>
                  </li>
                } @empty {
                  <li class="bea-mg__empty"><p>Une seule version.</p></li>
                }
              </ol>
              <label class="bea-mg__btn bea-mg__btn--primary" style="cursor:pointer;margin-top:0.75rem">
                <mat-icon>upload_file</mat-icon> Nouvelle version
                <input type="file" hidden (change)="onVersion($event)" />
              </label>
            }

            @if (tab() === 'historique') {
              <ol class="bea-doc-detail__timeline">
                @for (e of audit(); track e.id) {
                  <li>
                    <strong>{{ actionLabel(e.action) }}</strong>
                    <span>{{ e.created_at ? (e.created_at | date: 'dd/MM/yyyy HH:mm') : '' }}</span>
                  </li>
                } @empty {
                  <li class="bea-mg__empty"><p>Aucun événement d'audit.</p></li>
                }
              </ol>
            }
          </div>
        </div>
      }
    </section>
  `,
  styles: `
    .bea-doc-detail__back {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      color: #2874a6;
      text-decoration: none;
      font-size: 0.88rem;
      margin-bottom: 0.35rem;
    }
    .bea-doc-detail__layout {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 1rem;
      align-items: start;
    }
    .bea-doc-detail__preview {
      min-height: 28rem;
      overflow: auto;
    }
    .bea-doc-detail__preview img,
    .bea-doc-detail__preview iframe {
      width: 100%;
      min-height: 24rem;
      border: 0;
      transform-origin: top left;
      transition: transform 0.25s ease;
    }
    .bea-doc-detail__tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin-bottom: 1rem;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 0.5rem;
    }
    .bea-doc-detail__tabs button {
      border: 0;
      background: transparent;
      padding: 0.4rem 0.7rem;
      border-radius: 0.45rem;
      color: #64748b;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.85rem;
    }
    .bea-doc-detail__tabs button.active {
      background: #eff6ff;
      color: #1a5278;
    }
    .bea-doc-detail__meta {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
      margin: 0 0 1rem;
    }
    .bea-doc-detail__meta .full { grid-column: 1 / -1; }
    .bea-doc-detail__meta dt {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: #94a3b8;
    }
    .bea-doc-detail__meta dd {
      margin: 0.15rem 0 0;
      color: #0f172a;
      font-weight: 550;
    }
    .bea-doc-detail__ocr {
      white-space: pre-wrap;
      font-size: 0.85rem;
      background: #f8fafc;
      padding: 0.85rem;
      border-radius: 0.5rem;
      max-height: 28rem;
      overflow: auto;
    }
    .bea-doc-detail__list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.45rem;
    }
    .bea-doc-detail__list li {
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
      padding: 0.55rem 0.65rem;
      background: #f8fafc;
      border-radius: 0.5rem;
    }
    .bea-doc-detail__timeline {
      list-style: none;
      margin: 0;
      padding: 0;
      border-left: 2px solid #cbd5e1;
      display: grid;
      gap: 0.85rem;
    }
    .bea-doc-detail__timeline li {
      padding-left: 1rem;
      position: relative;
    }
    .bea-doc-detail__timeline li::before {
      content: '';
      width: 0.55rem;
      height: 0.55rem;
      border-radius: 50%;
      background: #2874a6;
      position: absolute;
      left: -0.4rem;
      top: 0.35rem;
    }
    .bea-doc-detail__timeline span {
      display: block;
      font-size: 0.78rem;
      color: #94a3b8;
    }
    .bea-ocr-badge {
      display: inline-block;
      font-size: 0.72rem;
      font-weight: 650;
      padding: 0.2rem 0.5rem;
      border-radius: 0.35rem;
      background: #e2e8f0;
      color: #475569;
    }
    .bea-ocr-badge[data-status='pending'] { background: #fef3c7; color: #92400e; }
    .bea-ocr-badge[data-status='processing'] { background: #dbeafe; color: #1e40af; }
    .bea-ocr-badge[data-status='done'] { background: #dcfce7; color: #166534; }
    .bea-ocr-badge[data-status='failed'] { background: #fee2e2; color: #991b1b; }
    @media (max-width: 960px) {
      .bea-doc-detail__layout { grid-template-columns: 1fr; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-doc-detail__preview img,
      .bea-doc-detail__preview iframe { transition: none; }
    }
  `,
})
export class ArchivesDocumentDetailComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly sanitizer = inject(DomSanitizer);

  readonly doc = signal<Doc | null>(null);
  readonly relations = signal<Doc[]>([]);
  readonly versions = signal<Doc[]>([]);
  readonly audit = signal<AuditEvent[]>([]);
  readonly tab = signal<Tab>('info');
  readonly loading = signal(true);
  readonly erreur = signal<string | null>(null);
  readonly msg = signal('');
  readonly previewUrl = signal<string | null>(null);
  readonly zoom = signal(1);

  readonly tabs: { id: Tab; label: string }[] = [
    { id: 'info', label: 'Informations' },
    { id: 'ocr', label: 'OCR' },
    { id: 'relations', label: 'Relations' },
    { id: 'versions', label: 'Versions' },
    { id: 'historique', label: 'Historique' },
  ];

  ngOnInit(): void {
    this.route.paramMap.subscribe((pm) => {
      const id = pm.get('id');
      if (id) this.load(id);
    });
  }

  safePreview(): SafeResourceUrl | null {
    const url = this.previewUrl();
    return url ? this.sanitizer.bypassSecurityTrustResourceUrl(url) : null;
  }

  ocrLabel(status: string | null | undefined): string {
    switch (status) {
      case 'processing':
        return 'OCR en cours';
      case 'done':
        return 'OCR terminé';
      case 'failed':
        return 'OCR échoué';
      default:
        return 'OCR en attente';
    }
  }

  actionLabel(action: string): string {
    const map: Record<string, string> = {
      document_ingest: 'Document créé',
      document_archive_operation: 'Archivé depuis opération',
      document_view: 'Consulté',
      document_download: 'Téléchargé',
      document_version_create: 'Nouvelle version',
      document_delete: 'Mis en corbeille',
      document_restore: 'Restauré',
      ocr_processing: 'OCR démarré',
      ocr_done: 'OCR terminé',
      ocr_failed: 'OCR échoué',
      ocr_retry: 'OCR relancé',
      archive_view: 'Consulté (archives)',
      archive_download: 'Téléchargé (archives)',
      archive_update: 'Métadonnées modifiées',
    };
    return map[action] || action;
  }

  sizeLabel(bytes: number | null): string {
    if (bytes == null) return '—';
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  }

  isImage(d: Doc): boolean {
    return (d.mime_type || '').startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(d.filename);
  }

  isPdf(d: Doc): boolean {
    return d.mime_type === 'application/pdf' || /\.pdf$/i.test(d.filename);
  }

  zoomIn(): void {
    this.zoom.update((z) => Math.min(2.5, z + 0.15));
  }

  zoomOut(): void {
    this.zoom.update((z) => Math.max(0.5, z - 0.15));
  }

  load(id: string): void {
    this.loading.set(true);
    this.erreur.set(null);
    this.api.get<Doc>(`/documents/${id}`).subscribe({
      next: (row) => {
        this.doc.set(row);
        this.loading.set(false);
        this.loadPreview(id);
        this.loadSide(id);
      },
      error: () => {
        // Fallback MG si accès via archives-mg uniquement
        this.api.get<Doc>(`/mg/archives/documents/${id}`).subscribe({
          next: (row) => {
            this.doc.set(row);
            this.loading.set(false);
            this.loadPreviewMg(id);
            this.loadSide(id);
          },
          error: () => {
            this.loading.set(false);
            this.erreur.set('Document introuvable ou accès refusé.');
          },
        });
      },
    });
  }

  private loadSide(id: string): void {
    this.api.get<Doc[]>(`/documents/${id}/relations`).subscribe({
      next: (rows) => this.relations.set(rows ?? []),
      error: () => this.relations.set([]),
    });
    this.api.get<Doc[]>(`/documents/${id}/versions`).subscribe({
      next: (rows) => this.versions.set(rows ?? []),
      error: () => this.versions.set([]),
    });
    this.api.get<AuditEvent[]>(`/documents/${id}/audit`).subscribe({
      next: (rows) => this.audit.set(rows ?? []),
      error: () => this.audit.set([]),
    });
  }

  private loadPreview(id: string): void {
    this.api.download(`/documents/${id}/download`).subscribe({
      next: (blob) => {
        const prev = this.previewUrl();
        if (prev) URL.revokeObjectURL(prev);
        this.previewUrl.set(URL.createObjectURL(blob));
      },
      error: () => this.loadPreviewMg(id),
    });
  }

  private loadPreviewMg(id: string): void {
    this.api.download(`/mg/archives/documents/${id}/download`).subscribe({
      next: (blob) => {
        const prev = this.previewUrl();
        if (prev) URL.revokeObjectURL(prev);
        this.previewUrl.set(URL.createObjectURL(blob));
      },
      error: () => this.previewUrl.set(null),
    });
  }

  download(): void {
    const d = this.doc();
    if (!d) return;
    this.api.download(`/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename || 'document';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => {
        this.api.download(`/mg/archives/documents/${d.id}/download`).subscribe({
          next: (blob) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = d.filename || 'document';
            a.click();
            URL.revokeObjectURL(url);
          },
          error: () => this.erreur.set('Téléchargement refusé.'),
        });
      },
    });
  }

  retryOcr(): void {
    const d = this.doc();
    if (!d) return;
    this.api.post<Doc>(`/documents/${d.id}/retry-ocr`, {}).subscribe({
      next: (row) => {
        this.doc.set(row);
        this.msg.set('OCR relancé.');
        this.loadSide(d.id);
      },
      error: () => this.erreur.set('Relance OCR refusée.'),
    });
  }

  onVersion(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    const d = this.doc();
    if (!file || !d) return;
    this.api
      .upload<Doc>(`/documents/${d.id}/versions`, file, {
        version_comment: `Version déposée — ${file.name}`,
      })
      .subscribe({
        next: (row) => {
          this.msg.set(`Version ${row.version} créée.`);
          this.load(d.id);
        },
        error: () => this.erreur.set('Création de version refusée.'),
      });
    input.value = '';
  }
}
