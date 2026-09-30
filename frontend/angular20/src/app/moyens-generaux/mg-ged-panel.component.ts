import { ChangeDetectionStrategy, Component, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { FeedbackService } from '../core/feedback/feedback.service';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import {
  PIECES_ACCEPT,
  PIECES_FORMATS_LABEL,
  detacherReason,
  iconePiece,
  verifierPieceJointe,
} from '../shared/pieces-jointes';

interface GedDoc {
  id: string;
  filename: string;
  size_bytes: number;
  ocr_status?: string | null;
}

@Component({
  selector: 'bea-mg-ged',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <section
      class="bea-mg-ged"
      [class.bea-mg-ged--drag]="dragging()"
      (dragover)="onDragOver($event)"
      (dragleave)="onDragLeave($event)"
      (drop)="onDrop($event)"
    >
      <div class="bea-mg-ged__head">
        <h3>Pièces jointes (GED)</h3>
        @if (entityId) {
          <label class="bea-mg__btn bea-mg__btn--ghost bea-mg-ged__upload">
            <mat-icon>archive</mat-icon>
            Archiver
            <input type="file" [accept]="accept" hidden (change)="onFile($event)" />
          </label>
        }
      </div>
      @if (!entityId) {
        <p class="bea-stock-page__kicker">Enregistrer d’abord la fiche pour attacher des fichiers.</p>
      } @else {
        @if (uploading()) {
          <p class="bea-stock-page__kicker">Envoi en cours…</p>
        }
        <div class="bea-mg-ged__drop" aria-label="Zone de dépôt de fichier">
          <mat-icon>upload_file</mat-icon>
          <p>Glisser-déposer un fichier ({{ formats }}), ou utiliser Archiver.</p>
        </div>
        <ul class="bea-mg-ged__list">
          @for (d of docs(); track d.id) {
            <li>
              <mat-icon>{{ icone(d.filename) }}</mat-icon>
              <span>{{ d.filename }}</span>
              <small class="bea-ocr-badge" [attr.data-status]="d.ocr_status || 'pending'">
                {{ ocrLabel(d.ocr_status) }}
              </small>
              <small>{{ sizeLabel(d.size_bytes) }}</small>
              <button
                type="button"
                class="bea-mg-ged__dl"
                title="Télécharger"
                (click)="download(d)"
              >
                <mat-icon>download</mat-icon>
              </button>
              @if (peutDetacher()) {
                <button
                  type="button"
                  class="bea-mg-ged__dl bea-mg-ged__detach"
                  title="Détacher la pièce"
                  [attr.aria-label]="'Détacher ' + d.filename"
                  [disabled]="detaching() === d.id"
                  (click)="detacher(d)"
                >
                  <mat-icon>link_off</mat-icon>
                </button>
              }
            </li>
          } @empty {
            <li class="bea-mg-ged__empty">Aucun document.</li>
          }
        </ul>
      }
    </section>
  `,
  styles: `
    .bea-mg-ged {
      margin-top: 1rem;
      padding-top: 0.85rem;
      border-top: 1px solid #e2e8f0;
    }
    .bea-mg-ged--drag .bea-mg-ged__drop {
      border-color: #1a5278;
      background: #eff6ff;
    }
    .bea-mg-ged__drop {
      display: flex;
      align-items: center;
      gap: 0.55rem;
      margin-bottom: 0.65rem;
      padding: 0.75rem 0.85rem;
      border: 1px dashed #cbd5e1;
      border-radius: 0.55rem;
      color: #64748b;
      font-size: 0.85rem;
      transition: border-color 0.2s ease, background 0.2s ease;
    }
    .bea-mg-ged__drop mat-icon {
      color: #94a3b8;
    }
    .bea-mg-ged__drop p { margin: 0; }
    .bea-mg-ged__head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      margin-bottom: 0.65rem;
    }
    .bea-mg-ged__head h3 {
      margin: 0;
      font-size: 0.95rem;
      font-weight: 650;
      color: #0f172a;
    }
    .bea-mg-ged__upload {
      cursor: pointer;
      margin: 0;
    }
    .bea-mg-ged__list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.35rem;
    }
    .bea-mg-ged__list li {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.45rem 0.55rem;
      border-radius: 0.5rem;
      background: #f8fafc;
      font-size: 0.88rem;
      color: #334155;
    }
    .bea-mg-ged__list mat-icon {
      font-size: 1.1rem;
      width: 1.1rem;
      height: 1.1rem;
      color: #64748b;
    }
    .bea-mg-ged__list span {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bea-mg-ged__list small {
      color: #94a3b8;
      font-size: 0.75rem;
      white-space: nowrap;
    }
    .bea-ocr-badge {
      font-weight: 650;
      padding: 0.1rem 0.35rem;
      border-radius: 0.3rem;
      background: #e2e8f0;
      color: #475569 !important;
    }
    .bea-ocr-badge[data-status='pending'] { background: #fef3c7; color: #92400e !important; }
    .bea-ocr-badge[data-status='processing'] { background: #dbeafe; color: #1e40af !important; }
    .bea-ocr-badge[data-status='done'] { background: #dcfce7; color: #166534 !important; }
    .bea-ocr-badge[data-status='failed'] { background: #fee2e2; color: #991b1b !important; }
    .bea-mg-ged__dl {
      display: inline-grid;
      place-items: center;
      width: 1.75rem;
      height: 1.75rem;
      border: 1px solid #e2e8f0;
      border-radius: 0.4rem;
      background: #fff;
      color: #1a5278;
      cursor: pointer;
      padding: 0;
    }
    .bea-mg-ged__dl:hover {
      border-color: #1a5278;
      background: #f0f7fc;
    }
    .bea-mg-ged__detach { color: #b91c1c; }
    .bea-mg-ged__detach:hover:not(:disabled) { border-color: #b91c1c; background: #fef2f2; }
    .bea-mg-ged__detach:disabled { opacity: 0.5; cursor: wait; }
    .bea-mg-ged__dl mat-icon {
      font-size: 1rem;
      width: 1rem;
      height: 1rem;
      color: inherit;
    }
    .bea-mg-ged__empty {
      color: #94a3b8;
      background: transparent !important;
      padding-left: 0 !important;
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-mg-ged__drop { transition: none; }
    }
  `,
})
export class MgGedPanelComponent implements OnChanges {
  @Input({ required: true }) moduleCode!: string;
  @Input({ required: true }) entity!: string;
  @Input() entityId: string | null = null;
  @Input() espaceCode = 'moyens-generaux';
  @Input() docType = 'JUSTIFICATIF';
  @Input() reference: string | null = null;
  /** Fiche verrouillée (payée, clôturée…) : consultation seule. */
  @Input() lectureSeule = false;
  @Output() changed = new EventEmitter<void>();

  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  readonly detaching = signal<string | null>(null);
  readonly peutDetacher = () => !this.lectureSeule && this.auth.canWriteGed();
  readonly docs = signal<GedDoc[]>([]);
  readonly erreur = feedbackSignal('error', null);
  readonly msg = feedbackSignal('success', '');
  readonly dragging = signal(false);
  readonly uploading = signal(false);

  readonly accept = PIECES_ACCEPT;
  readonly formats = PIECES_FORMATS_LABEL;
  readonly icone = (nom: string) => iconePiece(nom);

  ngOnChanges(): void {
    this.reload();
  }

  ocrLabel(status: string | null | undefined): string {
    switch (status) {
      case 'processing':
        return 'OCR…';
      case 'done':
        return 'OCR ok';
      case 'failed':
        return 'OCR échec';
      default:
        return 'OCR…';
    }
  }

  sizeLabel(bytes: number): string {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  }

  onDragOver(ev: DragEvent): void {
    if (!this.entityId) return;
    ev.preventDefault();
    this.dragging.set(true);
  }

  onDragLeave(ev: DragEvent): void {
    ev.preventDefault();
    this.dragging.set(false);
  }

  onDrop(ev: DragEvent): void {
    ev.preventDefault();
    this.dragging.set(false);
    const file = ev.dataTransfer?.files?.[0];
    if (file) this.uploadFile(file);
  }

  reload(): void {
    if (!this.entityId) {
      this.docs.set([]);
      return;
    }
    const q = `module_code=${encodeURIComponent(this.moduleCode)}&entity=${encodeURIComponent(this.entity)}&entity_id=${encodeURIComponent(this.entityId)}`;
    this.api.get<{ items: GedDoc[] }>(`/ged/documents?${q}`).subscribe({
      next: (res) => this.docs.set(res.items ?? []),
      error: () => this.erreur.set('Lecture GED impossible (permission ged.read ?).'),
    });
  }

  download(doc: GedDoc): void {
    this.api.download(`/ged/documents/${doc.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = doc.filename || 'document';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Téléchargement impossible.'),
    });
  }

  detacher(doc: GedDoc): void {
    this.detaching.set(doc.id);
    this.feedback
      .runWithReason(
        (motif) => this.api.delete(`/ged/documents/${doc.id}?reason=${encodeURIComponent(motif)}`),
        {
          reason: detacherReason(doc.filename),
          loading: 'Détachement de la pièce…',
          errorTitle: 'Détachement refusé',
          success: { title: 'Pièce détachée', details: [{ label: 'Fichier', value: doc.filename }] },
        },
      )
      .subscribe({
        next: () => {
          this.detaching.set(null);
          this.docs.update((list) => list.filter((d) => d.id !== doc.id));
          this.changed.emit();
        },
        error: () => this.detaching.set(null),
        complete: () => this.detaching.set(null),
      });
  }

  onFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) this.uploadFile(file);
    input.value = '';
  }

  private uploadFile(file: File): void {
    if (!this.entityId) return;
    const refus = verifierPieceJointe(file);
    if (refus) {
      this.erreur.set(refus);
      return;
    }
    const fields: Record<string, string> = {
      espace_code: this.espaceCode,
      module_code: this.moduleCode,
      source_type: this.entity,
      source_id: this.entityId,
      doc_type: this.docType,
      title: file.name,
    };
    if (this.reference) fields['reference'] = this.reference;
    this.uploading.set(true);
    this.api.upload<GedDoc>('/documents/from-operation', file, fields).subscribe({
      next: () => {
        this.erreur.set(null);
        this.msg.set('Document déposé avec succès. L\'analyse OCR est en cours.');
        this.uploading.set(false);
        this.reload();
      },
      error: (err: { status?: number; error?: { detail?: unknown; message?: unknown } }) => {
        this.uploading.set(false);
        const detail = err?.error?.detail ?? err?.error?.message;
        this.erreur.set(
          typeof detail === 'string' && err.status !== 403 ? detail : 'Archivage refusé (permission ged.write ?).',
        );
      },
    });
  }
}
