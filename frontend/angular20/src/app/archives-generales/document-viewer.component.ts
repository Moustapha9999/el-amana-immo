import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  inject,
  signal,
} from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ApiService } from '../core/services/api.service';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { iconePiece } from '../shared/pieces-jointes';

export interface GedDoc {
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
  ocr_status?: string | null;
  ocr_text?: string | null;
  ocr_error?: string | null;
  ocr_attempts?: number;
  security_level?: string | null;
  archived_at?: string | null;
  agence_id?: string | null;
  fournisseur_id?: string | null;
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
  selector: 'bea-document-viewer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, DecimalPipe, MatIconModule],
  template: `
    @if (documentId) {
      <div class="bea-viewer" role="dialog" aria-modal="true" aria-label="Document">
        <header class="bea-viewer__bar">
          <button type="button" class="bea-mg__btn" (click)="close()">
            <mat-icon>arrow_back</mat-icon> Fermer
          </button>
          <div class="bea-viewer__title">
            <p class="bea-stock-page__kicker">Document</p>
            <strong>{{ doc()?.reference || doc()?.title || doc()?.filename || '…' }}</strong>
          </div>
          <div class="bea-viewer__bar-actions">
            <button type="button" class="bea-mg__btn" (click)="download()" [disabled]="!doc()">
              <mat-icon>download</mat-icon> Télécharger
            </button>
            <button type="button" class="bea-mg__btn" (click)="printDoc()" [disabled]="!canPrint()">
              <mat-icon>print</mat-icon> Imprimer
            </button>
            <button type="button" class="bea-viewer__close" (click)="close()" title="Fermer" aria-label="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </div>
        </header>


        <div class="bea-viewer__body">
          <section class="bea-viewer__preview">
            <div class="bea-viewer__tools">
              <button type="button" class="bea-mg__icon-btn" (click)="zoomOut()" title="Zoom −"><mat-icon>zoom_out</mat-icon></button>
              <button type="button" class="bea-mg__icon-btn" (click)="zoomIn()" title="Zoom +"><mat-icon>zoom_in</mat-icon></button>
              @if (doc() && isImage(doc()!)) {
                <button type="button" class="bea-mg__icon-btn" (click)="rotate()" title="Rotation"><mat-icon>rotate_right</mat-icon></button>
              }
              <button type="button" class="bea-mg__icon-btn" (click)="fit()" title="Ajuster"><mat-icon>fit_screen</mat-icon></button>
            </div>
            @if (doc(); as d) {
              @if (previewStatus() === 'loading') {
                <div class="bea-viewer__sheet bea-mg__empty"><p>Chargement de l'aperçu…</p></div>
              } @else if (previewStatus() === 'file' && previewUrl()) {
                @if (isImage(d)) {
                  <img
                    [src]="previewUrl()"
                    [style.transform]="'scale(' + zoom() + ') rotate(' + rotation() + 'deg)'"
                    alt="Aperçu"
                  />
                } @else if (isPdf(d)) {
                  <iframe #pdfFrame [src]="safePreview()" title="Aperçu PDF"></iframe>
                }
              } @else if (previewStatus() === 'table') {
                <div class="bea-viewer__sheet" id="bea-viewer-sheet">
                  <p class="bea-viewer__sheet-title">{{ sheetTitle() }}</p>
                  <div class="bea-viewer__table-scroll">
                    <table>
                      @for (row of sheetRows(); track $index; let first = $first) {
                        <tr>
                          @for (cell of row; track $index) {
                            @if (first) {
                              <th>{{ cell }}</th>
                            } @else {
                              <td>{{ cell }}</td>
                            }
                          }
                        </tr>
                      } @empty {
                        <tr><td>Feuille vide.</td></tr>
                      }
                    </table>
                  </div>
                  @if (sheetTruncated()) {
                    <p class="bea-stock-page__kicker">Aperçu limité aux premières lignes. Téléchargez le fichier pour le voir en entier.</p>
                  }
                </div>
              } @else if (previewStatus() === 'text') {
                <div class="bea-viewer__sheet bea-viewer__doc" id="bea-viewer-sheet" [style.zoom]="zoom()">
                  <p class="bea-viewer__sheet-title">{{ sheetTitle() }}</p>
                  @for (row of sheetRows(); track $index) {
                    <p>{{ row[0] }}</p>
                  } @empty {
                    <p>Document vide.</p>
                  }
                  @if (sheetTruncated()) {
                    <p class="bea-stock-page__kicker">Aperçu limité. Téléchargez le fichier pour le voir en entier.</p>
                  }
                </div>
              } @else {
                <div class="bea-viewer__sheet bea-mg__empty">
                  <mat-icon>{{ iconeDoc(d) }}</mat-icon>
                  <p>Aperçu indisponible pour ce format. Téléchargez-le pour l'ouvrir.</p>
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="download()">Télécharger</button>
                </div>
              }
            }
          </section>

          <aside class="bea-viewer__side">
            <nav class="bea-viewer__tabs">
              @for (t of tabs; track t.id) {
                <button type="button" [class.active]="tab() === t.id" (click)="tab.set(t.id)">{{ t.label }}</button>
              }
            </nav>
            @if (doc(); as d) {
              @if (tab() === 'info') {
                <dl class="bea-viewer__meta">
                  <div><dt>Nom</dt><dd>{{ d.filename }}</dd></div>
                  <div><dt>Référence</dt><dd>{{ d.reference || '—' }}</dd></div>
                  <div><dt>Département</dt><dd>{{ d.espace_code }}</dd></div>
                  <div><dt>Module</dt><dd>{{ d.module_code }}</dd></div>
                  <div><dt>Type</dt><dd>{{ d.doc_type || d.entity }}</dd></div>
                  <div><dt>Source</dt><dd>{{ d.entity }} · {{ d.entity_id }}</dd></div>
                  <div><dt>OCR</dt><dd>{{ ocrLabel(d.ocr_status) }}</dd></div>
                  <div><dt>Taille</dt><dd>{{ d.size_bytes | number }} o</dd></div>
                  <div><dt>Date</dt><dd>{{ d.created_at ? (d.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</dd></div>
                  <div><dt>Version</dt><dd>{{ d.version }}</dd></div>
                </dl>
              }
              @if (tab() === 'ocr') {
                @if (d.ocr_text) {
                  <pre class="bea-viewer__ocr">{{ d.ocr_text }}</pre>
                } @else {
                  <p class="bea-stock-page__kicker">{{ ocrLabel(d.ocr_status) }} — texte non disponible.</p>
                  @if (d.ocr_error) {
                    <p class="bea-stock-page__error">{{ d.ocr_error }}</p>
                  }
                }
              }
              @if (tab() === 'relations') {
                @for (r of relations(); track r.id) {
                  <button type="button" class="bea-viewer__rel" (click)="openRelated.emit(r.id)">
                    <mat-icon>description</mat-icon>
                    <span>
                      <strong>{{ r.reference || r.title || r.filename }}</strong>
                      <em>{{ r.doc_type || r.entity }}</em>
                    </span>
                  </button>
                } @empty {
                  <p class="bea-stock-page__kicker">Aucun document lié sur ce processus.</p>
                }
              }
              @if (tab() === 'versions') {
                @for (v of versions(); track v.id) {
                  <button type="button" class="bea-viewer__rel" (click)="openRelated.emit(v.id)">
                    <mat-icon>history</mat-icon>
                    <span>
                      <strong>v{{ v.version }} — {{ v.filename }}</strong>
                      <em>{{ v.version_comment || (v.created_at | date: 'dd/MM/yyyy') }}</em>
                    </span>
                  </button>
                } @empty {
                  <p class="bea-stock-page__kicker">Version unique.</p>
                }
              }
              @if (tab() === 'historique') {
                <ol class="bea-viewer__feed">
                  @for (ev of audit(); track ev.id) {
                    <li>
                      <time>{{ ev.created_at ? (ev.created_at | date: 'dd/MM HH:mm') : '—' }}</time>
                      <span>{{ actionLabel(ev.action) }}</span>
                    </li>
                  } @empty {
                    <li>Aucun événement.</li>
                  }
                </ol>
              }
            }
          </aside>
        </div>
      </div>
    }
  `,
  styles: `
    .bea-viewer {
      position: fixed;
      inset: 0;
      z-index: 200;
      background: #0f172a;
      display: flex;
      flex-direction: column;
      animation: beaViewerIn 0.35s ease;
    }
    .bea-viewer__bar {
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.75rem 1rem;
      background: #fff;
      border-bottom: 1px solid #e2e8f0;
    }
    .bea-viewer__title { flex: 1; min-width: 0; }
    .bea-viewer__title strong {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bea-viewer__bar-actions { display: flex; gap: 0.4rem; align-items: center; }
    .bea-viewer__close {
      width: 2.25rem;
      height: 2.25rem;
      border: 0;
      border-radius: 999px;
      background: #fee2e2;
      color: #991b1b;
      display: grid;
      place-items: center;
      cursor: pointer;
    }
    .bea-viewer__preview {
      overflow: auto;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 1rem;
      gap: 0.75rem;
      background: #0f172a;
    }
    .bea-viewer__sheet {
      width: min(100%, 960px);
      max-height: calc(100vh - 10rem);
      overflow: auto;
      background: #fff;
      border-radius: 0.5rem;
      padding: 1rem;
      color: #0f172a;
    }
    .bea-viewer__sheet-title { margin: 0 0 0.6rem; font-weight: 650; }
    .bea-viewer__table-scroll { overflow: auto; }
    .bea-viewer__sheet table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    .bea-viewer__sheet th, .bea-viewer__sheet td {
      border: 1px solid #e2e8f0;
      padding: 0.35rem 0.45rem;
      text-align: left;
      white-space: nowrap;
    }
    .bea-viewer__sheet th { background: #f8fafc; }
    .bea-viewer__doc { max-width: 52rem; margin: 0 auto; line-height: 1.55; font-size: 0.9rem; white-space: pre-wrap; }
    .bea-viewer__doc p { margin: 0 0 0.55rem; }
    .bea-viewer__body {
      flex: 1;
      display: grid;
      grid-template-columns: 1fr 22rem;
      min-height: 0;
    }
    .bea-viewer__preview {
      overflow: auto;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 1rem;
      gap: 0.75rem;
    }
    .bea-viewer__tools {
      display: flex;
      gap: 0.35rem;
      background: #fff;
      border-radius: 0.5rem;
      padding: 0.25rem;
    }
    .bea-viewer__preview img,
    .bea-viewer__preview iframe {
      max-width: 100%;
      background: #fff;
      border-radius: 0.4rem;
      box-shadow: 0 8px 30px rgb(0 0 0 / 25%);
    }
    .bea-viewer__preview iframe {
      width: min(920px, 100%);
      height: calc(100vh - 9rem);
      border: 0;
    }
    .bea-viewer__preview img {
      transform-origin: center top;
      transition: transform 0.25s ease;
    }
    .bea-viewer__side {
      background: #fff;
      overflow: auto;
      border-left: 1px solid #e2e8f0;
      padding: 0.75rem;
    }
    .bea-viewer__tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem;
      margin-bottom: 0.75rem;
    }
    .bea-viewer__tabs button {
      border: 0;
      background: #f1f5f9;
      border-radius: 999px;
      padding: 0.3rem 0.65rem;
      font-size: 0.78rem;
      cursor: pointer;
    }
    .bea-viewer__tabs button.active {
      background: #1a5278;
      color: #fff;
    }
    .bea-viewer__meta { margin: 0; display: grid; gap: 0.55rem; }
    .bea-viewer__meta div { display: grid; gap: 0.1rem; }
    .bea-viewer__meta dt { font-size: 0.72rem; color: #64748b; text-transform: uppercase; }
    .bea-viewer__meta dd { margin: 0; font-size: 0.9rem; }
    .bea-viewer__ocr {
      white-space: pre-wrap;
      font-size: 0.8rem;
      background: #f8fafc;
      padding: 0.75rem;
      border-radius: 0.4rem;
    }
    .bea-viewer__rel {
      width: 100%;
      display: flex;
      gap: 0.5rem;
      text-align: left;
      border: 1px solid #e2e8f0;
      background: #fff;
      border-radius: 0.5rem;
      padding: 0.55rem;
      margin-bottom: 0.4rem;
      cursor: pointer;
    }
    .bea-viewer__rel strong, .bea-viewer__rel em { display: block; }
    .bea-viewer__rel em { font-style: normal; color: #64748b; font-size: 0.78rem; }
    .bea-viewer__feed {
      list-style: none;
      margin: 0;
      padding: 0 0.25rem 0 0;
      display: grid;
      gap: 0.55rem;
      max-height: calc(100dvh - 11rem);
      overflow-y: auto;
    }
    .bea-viewer__feed time { display: block; font-size: 0.75rem; color: #94a3b8; }
    @keyframes beaViewerIn {
      from { opacity: 0; transform: scale(0.985); }
      to { opacity: 1; transform: none; }
    }
    @media (max-width: 900px) {
      .bea-viewer__body { grid-template-columns: 1fr; }
      .bea-viewer__side { border-left: 0; border-top: 1px solid #e2e8f0; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-viewer, .bea-viewer__preview img { animation: none; transition: none; }
    }
  `,
})
export class DocumentViewerComponent implements OnChanges {
  private readonly api = inject(ApiService);
  private readonly sanitizer = inject(DomSanitizer);

  @Input() documentId: string | null = null;
  @Output() readonly closed = new EventEmitter<void>();
  @Output() readonly openRelated = new EventEmitter<string>();

  readonly doc = signal<GedDoc | null>(null);
  readonly relations = signal<GedDoc[]>([]);
  readonly versions = signal<GedDoc[]>([]);
  readonly audit = signal<AuditEvent[]>([]);
  readonly erreur = feedbackSignal('error', null);
  readonly tab = signal<Tab>('info');
  readonly zoom = signal(1);
  readonly rotation = signal(0);
  readonly previewUrl = signal<string | null>(null);
  readonly safePreview = signal<SafeResourceUrl | null>(null);
  readonly previewStatus = signal<'loading' | 'file' | 'table' | 'text' | 'empty'>('loading');
  readonly sheetTitle = signal('');
  readonly sheetRows = signal<string[][]>([]);
  readonly sheetTruncated = signal(false);

  readonly tabs: { id: Tab; label: string }[] = [
    { id: 'info', label: 'Informations' },
    { id: 'ocr', label: 'Texte OCR' },
    { id: 'relations', label: 'Documents liés' },
    { id: 'versions', label: 'Versions' },
    { id: 'historique', label: 'Historique' },
  ];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['documentId']) {
      this.load(this.documentId);
    }
  }

  close(): void {
    this.revoke();
    this.closed.emit();
  }

  zoomIn(): void {
    this.zoom.update((z) => Math.min(2.5, +(z + 0.15).toFixed(2)));
  }
  zoomOut(): void {
    this.zoom.update((z) => Math.max(0.4, +(z - 0.15).toFixed(2)));
  }
  rotate(): void {
    this.rotation.update((r) => (r + 90) % 360);
  }
  fit(): void {
    this.zoom.set(1);
    this.rotation.set(0);
  }

  iconeDoc(d: GedDoc): string {
    return iconePiece(d.filename);
  }

  isImage(d: GedDoc): boolean {
    const m = (d.mime_type || '').toLowerCase();
    const n = d.filename.toLowerCase();
    return m.startsWith('image/') || /\.(png|jpe?g|gif|webp)$/.test(n);
  }

  isPdf(d: GedDoc): boolean {
    const m = (d.mime_type || '').toLowerCase();
    return m.includes('pdf') || d.filename.toLowerCase().endsWith('.pdf');
  }

  ocrLabel(status: string | null | undefined): string {
    switch (status) {
      case 'processing':
        return 'En cours';
      case 'done':
        return 'Terminé';
      case 'failed':
        return 'À vérifier';
      default:
        return 'En attente';
    }
  }

  actionLabel(action: string): string {
    const map: Record<string, string> = {
      document_ingest: 'Document ajouté',
      document_view: 'Document consulté',
      document_download: 'Document téléchargé',
      document_metadata_update: 'Métadonnées modifiées',
      document_version_create: 'Nouvelle version',
      document_versions_list: 'Versions consultées',
      document_relations_view: 'Documents liés consultés',
      document_audit_view: 'Historique consulté',
      document_delete: 'Mis à la corbeille',
      document_restore: 'Restauré',
      ocr_retry: 'OCR relancé',
      ocr_done: 'OCR terminé',
      ocr_failed: 'OCR en échec',
    };
    return map[action] || action;
  }

  download(): void {
    const d = this.doc();
    if (!d) return;
    this.api.download(`/documents/${d.id}/download`).subscribe({
      next: (blob) => this.saveBlob(blob, d.filename),
      error: () => this.erreur.set('Téléchargement refusé.'),
    });
  }

  isSheet(d: GedDoc): boolean {
    const n = d.filename.toLowerCase();
    return /\.(xlsx|xlsm|xls|csv|docx)$/.test(n);
  }

  canPrint(): boolean {
    const status = this.previewStatus();
    return status === 'file' || status === 'table';
  }

  printDoc(): void {
    const d = this.doc();
    if (!d || !this.canPrint()) return;
    if (this.previewStatus() === 'file' && this.isPdf(d)) {
      const frame = document.querySelector('.bea-viewer__preview iframe') as HTMLIFrameElement | null;
      const win = frame?.contentWindow;
      if (win) {
        win.focus();
        win.print();
        return;
      }
    }
    if (this.previewStatus() === 'file' && this.isImage(d) && this.previewUrl()) {
      this.openPrint(`<img src="${this.previewUrl()}" style="max-width:100%" alt="">`);
      return;
    }
    if (this.previewStatus() === 'table') {
      const body = this.sheetRows()
        .map((row) => `<tr>${row.map((cell) => `<td>${this.escapeHtml(cell)}</td>`).join('')}</tr>`)
        .join('');
      this.openPrint(
        `<h1>${this.escapeHtml(this.sheetTitle() || d.filename)}</h1><table>${body}</table>`,
      );
    }
  }

  private openPrint(html: string): void {
    const popup = window.open('', '_blank');
    if (!popup) {
      this.erreur.set('Impression bloquée par le navigateur. Autorisez les fenêtres pour ce site.');
      return;
    }
    popup.document.write(`<!DOCTYPE html><html><head><title>Impression</title>
      <style>body{font-family:sans-serif;padding:1rem}table{border-collapse:collapse;width:100%}
      td,th{border:1px solid #ccc;padding:4px 6px;font-size:12px}</style></head><body>${html}
      <script>window.onload=function(){window.print()}<\/script></body></html>`);
    popup.document.close();
  }

  private escapeHtml(value: string): string {
    return value
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;');
  }

  private load(id: string | null): void {
    this.revoke();
    this.doc.set(null);
    this.relations.set([]);
    this.versions.set([]);
    this.audit.set([]);
    this.erreur.set(null);
    this.sheetRows.set([]);
    this.previewStatus.set('loading');
    this.tab.set('info');
    this.fit();
    if (!id) return;
    this.api.get<GedDoc>(`/documents/${id}`).subscribe({
      next: (row) => {
        this.doc.set(row);
        this.loadPreview(row);
      },
      error: () => this.erreur.set('Document inaccessible.'),
    });
    this.api.get<GedDoc[]>(`/documents/${id}/relations`).subscribe({
      next: (rows) => this.relations.set(rows ?? []),
      error: () => this.relations.set([]),
    });
    this.api.get<GedDoc[]>(`/documents/${id}/versions`).subscribe({
      next: (rows) => this.versions.set(rows ?? []),
      error: () => this.versions.set([]),
    });
    this.api.get<AuditEvent[]>(`/documents/${id}/audit`).subscribe({
      next: (rows) => this.audit.set(rows ?? []),
      error: () => this.audit.set([]),
    });
  }

  private loadPreview(d: GedDoc): void {
    this.previewStatus.set('loading');
    if (this.isImage(d) || this.isPdf(d)) {
      this.api.download(`/documents/${d.id}/download`).subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          this.previewUrl.set(url);
          this.safePreview.set(this.sanitizer.bypassSecurityTrustResourceUrl(url));
          this.previewStatus.set('file');
        },
        error: () => {
          this.previewStatus.set('empty');
          this.erreur.set('Aperçu indisponible.');
        },
      });
      return;
    }
    if (this.isSheet(d)) {
      this.api.get<{ kind: string; title: string; rows: string[][]; truncated: boolean }>(
        `/documents/${d.id}/preview`,
      ).subscribe({
        next: (res) => {
          if (res.kind !== 'table' && res.kind !== 'text') {
            this.previewStatus.set('empty');
            return;
          }
          this.sheetTitle.set(res.title || d.filename);
          this.sheetRows.set(res.rows ?? []);
          this.sheetTruncated.set(!!res.truncated);
          this.previewStatus.set(res.kind === 'text' ? 'text' : 'table');
        },
        error: () => {
          this.previewStatus.set('empty');
          this.erreur.set('Lecture du classeur impossible.');
        },
      });
      return;
    }
    this.previewStatus.set('empty');
  }

  private saveBlob(blob: Blob, name: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name || 'document';
    a.click();
    URL.revokeObjectURL(url);
  }

  private revoke(): void {
    const prev = this.previewUrl();
    if (prev) URL.revokeObjectURL(prev);
    this.previewUrl.set(null);
    this.safePreview.set(null);
  }
}
