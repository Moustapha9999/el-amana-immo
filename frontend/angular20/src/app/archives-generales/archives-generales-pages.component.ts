import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { DocumentViewerComponent, GedDoc } from './document-viewer.component';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { FeedbackService } from '../core/feedback/feedback.service';

interface OcrDash {
  ocr: { pending: number; processing: number; done: number; failed: number; en_cours: number };
}

interface MissingItem {
  code: string;
  label: string;
  module_code: string;
  source_type: string;
  source_id: string;
  reference?: string | null;
  detail?: string | null;
}

interface VerifyItem {
  motifs: string[];
  document: GedDoc;
}

interface DupGroup {
  filename: string;
  size_bytes: number;
  criterion: string;
  documents: GedDoc[];
}

interface Dossier {
  espace_code: string;
  module_code: string;
  entity: string;
  entity_id: string;
  count: number;
  reference?: string | null;
  updated_at?: string | null;
}

interface ActivityEvent {
  id: string;
  action: string;
  label: string;
  created_at: string | null;
  entity_id?: string | null;
  espace_code?: string | null;
  module_code?: string | null;
  filename?: string | null;
}

@Component({
  selector: 'bea-ag-ocr',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, DecimalPipe, MatIconModule, DocumentViewerComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Archive Générale</p>
          <h1>OCR & Traitement</h1>
        </div>
      </header>
      <div class="bea-nf-kpi">
        @for (k of kpis(); track k.key) {
          <button type="button" class="bea-nf-kpi__card" [class.active]="filter() === k.key" (click)="setFilter(k.key)">
            <p>{{ k.label }}</p><strong>{{ k.value | number }}</strong>
          </button>
        }
      </div>
      <div class="bea-ag-pipe">
        <span>Import</span><i></i><span>Archivage</span><i></i><span>OCR</span><i></i><span>Recherche</span>
      </div>
      <div class="bea-mg__panel">
        <table class="bea-mg__table">
          <thead><tr><th>Document</th><th>Département</th><th>Statut</th><th>Tentatives</th><th>Date</th><th></th></tr></thead>
          <tbody>
            @for (d of docs(); track d.id) {
              <tr class="bea-ag-row">
                <td><strong>{{ d.title || d.filename }}</strong></td>
                <td>{{ espaceLabel(d.espace_code) }}</td>
                <td><span class="bea-ocr-badge" [attr.data-status]="d.ocr_status">{{ label(d.ocr_status) }}</span></td>
                <td>{{ d.ocr_attempts ?? 0 }}</td>
                <td>{{ d.created_at ? (d.created_at | date: 'dd/MM/yyyy') : '—' }}</td>
                <td class="bea-ag-icons">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="viewerId.set(d.id)"><mat-icon>visibility</mat-icon></button>
                  <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="download(d)"><mat-icon>download</mat-icon></button>
                  @if (canRetry() && d.ocr_status !== 'done') {
                    <button type="button" class="bea-mg__icon-btn" title="Relancer OCR" (click)="retry(d)"><mat-icon>refresh</mat-icon></button>
                  }
                  @if (canWrite()) {
                    <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="askTrash(d)"><mat-icon>delete</mat-icon></button>
                  }
                </td>
              </tr>
            } @empty {
              <tr><td colspan="6"><div class="bea-mg__empty"><p>Aucun document dans cet état.</p></div></td></tr>
            }
          </tbody>
        </table>
      </div>
      @if (trash(); as d) {
        <div class="bea-modal" role="dialog">
          <div class="bea-modal__card">
            <h2>Mettre à la corbeille ?</h2>
            <p>{{ d.filename }} ne sera pas supprimé définitivement.</p>
            <footer>
              <button type="button" class="bea-mg__btn" (click)="trash.set(null)">Annuler</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="confirmTrash()">Supprimer</button>
            </footer>
          </div>
        </div>
      }
    </section>
    <bea-document-viewer [documentId]="viewerId()" (closed)="viewerId.set(null)" (openRelated)="viewerId.set($event)" />
  `,
  styles: `
    .bea-nf-kpi__card { cursor: pointer; text-align: left; border: 1px solid transparent; }
    .bea-nf-kpi__card.active { border-color: #1a5278; }
    .bea-ocr-badge { font-size: 0.72rem; font-weight: 650; padding: 0.15rem 0.45rem; border-radius: 0.35rem; background: #fef3c7; color: #92400e; }
    .bea-ocr-badge[data-status='processing'] { background: #dbeafe; color: #1e40af; }
    .bea-ocr-badge[data-status='done'] { background: #dcfce7; color: #166534; }
    .bea-ocr-badge[data-status='failed'] { background: #ffedd5; color: #9a3412; }
    .bea-ag-pipe { display: flex; align-items: center; gap: 0.45rem; margin: 0.8rem 0; color: #1a5278; font-size: 0.82rem; font-weight: 650; }
    .bea-ag-pipe i { width: 1.4rem; height: 2px; background: #93c5fd; display: block; }
    .bea-ag-icons { display: flex; gap: 0.15rem; }
    .bea-ag-row { animation: beaIn 0.35s ease both; }
    .bea-modal { position: fixed; inset: 0; z-index: 70; background: rgb(15 23 42 / 45%); display: grid; place-items: center; }
    .bea-modal__card { background: #fff; border-radius: 0.75rem; padding: 1rem; width: min(26rem, 92vw); display: grid; gap: 0.6rem; }
    .bea-modal__card h2 { margin: 0; font-size: 1.05rem; }
    .bea-modal__card footer { display: flex; justify-content: flex-end; gap: 0.4rem; }
    @keyframes beaIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
    @media (prefers-reduced-motion: reduce) { .bea-ag-row { animation: none; } }
  `,
})
export class ArchivesGeneralesOcrComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  readonly filter = signal<'pending' | 'processing' | 'done' | 'failed'>('pending');
  readonly counts = signal({ pending: 0, processing: 0, done: 0, failed: 0 });
  readonly docs = signal<GedDoc[]>([]);
  readonly erreur = feedbackSignal('error', null);
  readonly viewerId = signal<string | null>(null);
  readonly trash = signal<GedDoc | null>(null);

  readonly kpis = () => {
    const c = this.counts();
    return [
      { key: 'pending' as const, label: 'En attente', value: c.pending },
      { key: 'processing' as const, label: 'En cours', value: c.processing },
      { key: 'done' as const, label: 'Terminés', value: c.done },
      { key: 'failed' as const, label: 'À vérifier', value: c.failed },
    ];
  };

  ngOnInit(): void {
    this.api.get<OcrDash>('/doc-archives/general/dashboard').subscribe({
      next: (d) => this.counts.set({
        pending: d.ocr?.pending ?? 0,
        processing: d.ocr?.processing ?? 0,
        done: d.ocr?.done ?? 0,
        failed: d.ocr?.failed ?? 0,
      }),
    });
    this.load();
  }

  canRetry(): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const codes = u.permission_codes ?? [];
    return codes.includes('ged.write') || codes.includes('archives.general.ocr.retry') || codes.includes('*');
  }

  setFilter(key: 'pending' | 'processing' | 'done' | 'failed'): void {
    this.filter.set(key);
    this.load();
  }

  label(s: string | null | undefined): string {
    return { pending: 'En attente', processing: 'En cours', done: 'Terminé', failed: 'À vérifier' }[s || 'pending'] || 'En attente';
  }

  espaceLabel(code: string | null | undefined): string {
    return ({ 'moyens-generaux': 'Moyens Généraux', comptabilite: 'Comptabilité', archives: 'Archives' } as Record<string, string>)[code || ''] || code || '—';
  }

  retry(d: GedDoc): void {
    this.api.post(`/documents/${d.id}/retry-ocr`, {}).subscribe({
      next: () => this.load(),
      error: () => this.erreur.set('Relance OCR refusée.'),
    });
  }

  canWrite(): boolean {
    const u = this.auth.user();
    return !!u && (u.is_superuser || (u.permission_codes ?? []).includes('ged.write') || (u.permission_codes ?? []).includes('*'));
  }

  download(d: GedDoc): void {
    this.api.download(`/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Téléchargement refusé.'),
    });
  }

  askTrash(d: GedDoc): void {
    this.trash.set(d);
  }

  confirmTrash(): void {
    const d = this.trash();
    if (!d) return;
    this.api.delete(`/documents/${d.id}`).subscribe({
      next: () => {
        this.trash.set(null);
        this.load();
      },
      error: () => this.erreur.set('Suppression refusée.'),
    });
  }

  private load(): void {
    this.api.get<{ items: GedDoc[] }>('/doc-archives/general', {
      ocr_status: this.filter(),
      page: 1,
      size: 100,
    }).subscribe({
      next: (res) => this.docs.set(res.items ?? []),
      error: () => this.erreur.set('Liste OCR indisponible.'),
    });
  }
}

@Component({
  selector: 'bea-ag-manquants',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrôle</p>
          <h1>Documents manquants</h1>
        </div>
      </header>
      <p class="bea-ag-lead">{{ items().length }} opération(s) sans pièce dans la GED. Ajoutez le fichier ou ouvrez le dossier.</p>
      <div class="bea-ag-miss">
        @for (m of items(); track m.source_type + m.source_id; let i = $index) {
          <article [style.--i]="i">
            <mat-icon>folder_off</mat-icon>
            <div>
              <h2>{{ m.reference || 'Sans référence' }}</h2>
              <p>{{ m.label }}</p>
              <p>{{ m.module_code }} · {{ m.detail || 'Pièce attendue absente de la GED' }}</p>
              <span class="bea-ocr-badge">À vérifier</span>
            </div>
            <div class="bea-ag-icons">
              <a class="bea-mg__icon-btn" title="Voir le dossier" [routerLink]="['/archives-generales/documents']" [queryParams]="{ module_code: m.module_code, entity: m.source_type, entity_id: m.source_id }"><mat-icon>folder_open</mat-icon></a>
              <a class="bea-mg__icon-btn" title="Ajouter un document" routerLink="/archives-generales/numeriser" [queryParams]="{ module_code: m.module_code, entity: m.source_type, entity_id: m.source_id, reference: m.reference || '' }"><mat-icon>upload_file</mat-icon></a>
            </div>
          </article>
        } @empty {
          <div class="bea-mg__empty"><p>Aucun document manquant détecté.</p></div>
        }
      </div>
    </section>
  `,
  styles: `
    .bea-ocr-badge { background: #ffedd5; color: #9a3412; font-size: 0.72rem; font-weight: 650; padding: 0.15rem 0.45rem; border-radius: 0.35rem; }
    .bea-ag-icons { display: flex; gap: 0.2rem; }
    .bea-ag-miss { display: grid; gap: 0.7rem; }
    .bea-ag-lead { margin: 0 0 0.8rem; color: #9a3412; font-size: 0.88rem; }
    .bea-ag-miss article {
      display: grid; grid-template-columns: auto 1fr auto; gap: 0.8rem; align-items: center;
      background: #fff; border: 1px solid #fed7aa; border-radius: 0.75rem; padding: 0.9rem 1rem;
      animation: beaIn 0.35s ease both;
    }
    .bea-ag-miss > article > mat-icon { color: #c2410c; }
    .bea-ag-miss h2 { margin: 0; font-size: 1rem; }
    .bea-ag-miss p { margin: 0.2rem 0 0; color: #64748b; font-size: 0.84rem; }
    @keyframes beaIn { from { opacity: 0; transform: translateY(4px);} to { opacity: 1; transform: none; } }
  `,
})
export class ArchivesGeneralesManquantsComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly items = signal<MissingItem[]>([]);
  readonly erreur = feedbackSignal('error', null);
  ngOnInit(): void {
    this.api.get<MissingItem[]>('/doc-archives/general/manquants').subscribe({
      next: (rows) => this.items.set(rows ?? []),
      error: () => this.erreur.set('Liste des manquants indisponible.'),
    });
  }
}

@Component({
  selector: 'bea-ag-verifier',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, MatIconModule, DocumentViewerComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrôle</p>
          <h1>À vérifier</h1>
          <p class="bea-stock-page__kicker">{{ items().length }} document(s) avec une référence, un type ou un OCR incomplet.</p>
        </div>
      </header>
      <div class="bea-mg__panel">
        <table class="bea-mg__table">
          <thead><tr><th>Document</th><th>Motif</th><th>Département</th><th>Date</th><th></th></tr></thead>
          <tbody>
            @for (row of items(); track row.document.id) {
              <tr>
                <td>
                  <strong>{{ row.document.reference || row.document.filename }}</strong>
                  <div class="bea-ag__sub">{{ row.document.filename }}</div>
                </td>
                <td>
                  @for (m of row.motifs; track m) { <span class="bea-ag-chip">{{ m }}</span> }
                </td>
                <td>{{ row.document.espace_code }}</td>
                <td>{{ row.document.created_at ? (row.document.created_at | date: 'dd/MM/yyyy') : '—' }}</td>
                <td class="bea-ag-icons">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="viewerId.set(row.document.id)"><mat-icon>visibility</mat-icon></button>
                  <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="download(row.document)"><mat-icon>download</mat-icon></button>
                  <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="startEdit(row.document)"><mat-icon>edit</mat-icon></button>
                  <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="trash.set(row.document)"><mat-icon>delete</mat-icon></button>
                </td>
              </tr>
            } @empty {
              <tr><td colspan="5"><div class="bea-mg__empty"><p>Rien à vérifier.</p></div></td></tr>
            }
          </tbody>
        </table>
      </div>
    </section>
    @if (editing(); as d) {
      <div class="bea-modal" role="dialog">
        <form class="bea-modal__card" (ngSubmit)="saveEdit()">
          <h2>Compléter les métadonnées</h2>
          <label>Nom<input [(ngModel)]="editTitle" name="title" /></label>
          <label>Type<input [(ngModel)]="editType" name="type" /></label>
          <label>Référence<input [(ngModel)]="editRef" name="ref" /></label>
          <footer>
            <button type="button" class="bea-mg__btn" (click)="editing.set(null)">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Enregistrer</button>
          </footer>
        </form>
      </div>
    }
    @if (trash(); as d) {
      <div class="bea-modal" role="dialog">
        <div class="bea-modal__card">
          <h2>Mettre à la corbeille ?</h2>
          <p>{{ d.filename }}</p>
          <footer>
            <button type="button" class="bea-mg__btn" (click)="trash.set(null)">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="remove(d)">Supprimer</button>
          </footer>
        </div>
      </div>
    }
    <bea-document-viewer [documentId]="viewerId()" (closed)="viewerId.set(null)" (openRelated)="viewerId.set($event)" />
  `,
  styles: `
    .bea-ag__sub { font-size: 0.78rem; color: #94a3b8; }
    .bea-ag-icons { display: flex; gap: 0.15rem; white-space: nowrap; }
    .bea-ag-chip { display: inline-block; margin: 0.1rem 0.25rem 0.1rem 0; padding: 0.12rem 0.4rem; border-radius: 999px; background: #fff7ed; color: #9a3412; font-size: 0.75rem; }
    .bea-modal { position: fixed; inset: 0; z-index: 70; background: rgb(15 23 42 / 45%); display: grid; place-items: center; }
    .bea-modal__card { background: #fff; border-radius: 0.75rem; padding: 1rem; width: min(26rem, 92vw); display: grid; gap: 0.55rem; }
    .bea-modal__card h2 { margin: 0; font-size: 1.05rem; }
    .bea-modal__card label { display: grid; gap: 0.2rem; font-size: 0.82rem; }
    .bea-modal__card input { font: inherit; padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 0.4rem; }
    .bea-modal__card footer { display: flex; justify-content: flex-end; gap: 0.4rem; }
  `,
})
export class ArchivesGeneralesVerifierComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly items = signal<VerifyItem[]>([]);
  readonly erreur = feedbackSignal('error', null);
  readonly viewerId = signal<string | null>(null);
  readonly editing = signal<GedDoc | null>(null);
  readonly trash = signal<GedDoc | null>(null);
  editTitle = '';
  editType = '';
  editRef = '';
  ngOnInit(): void {
    this.api.get<VerifyItem[]>('/doc-archives/general/a-verifier').subscribe({
      next: (rows) => this.items.set(rows ?? []),
      error: () => this.erreur.set('Liste à vérifier indisponible.'),
    });
  }

  download(d: GedDoc): void {
    this.api.download(`/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Téléchargement refusé.'),
    });
  }

  startEdit(d: GedDoc): void {
    this.editTitle = d.title || d.filename;
    this.editType = d.doc_type || d.entity || '';
    this.editRef = d.reference || '';
    this.editing.set(d);
  }

  saveEdit(): void {
    const d = this.editing();
    if (!d) return;
    this.api.patch(`/documents/${d.id}`, {
      title: this.editTitle || null,
      doc_type: this.editType || null,
      reference: this.editRef || null,
    }).subscribe({
      next: () => {
        this.editing.set(null);
        this.ngOnInit();
      },
      error: () => this.erreur.set('Modification refusée.'),
    });
  }

  remove(d: GedDoc): void {
    this.api.delete(`/documents/${d.id}`).subscribe({
      next: () => {
        this.trash.set(null);
        this.items.update((rows) => rows.filter((r) => r.document.id !== d.id));
      },
      error: () => this.erreur.set('Suppression refusée.'),
    });
  }
}

@Component({
  selector: 'bea-ag-doublons',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, MatIconModule, DocumentViewerComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrôle</p>
          <h1>Doublons potentiels</h1>
        </div>
      </header>
      <p class="bea-ag-lead">Même nom de fichier et même taille. Aucune suppression automatique.</p>
      <div class="bea-ag-dups">
        @for (g of groups(); track g.filename + g.size_bytes) {
          <article>
            <header>
              <mat-icon>file_copy</mat-icon>
              <div>
                <h2>{{ g.filename }}</h2>
                <p>{{ g.criterion }} · {{ g.size_bytes | number }} octets · {{ g.documents.length }} fichiers</p>
              </div>
            </header>
            @for (d of g.documents; track d.id) {
              <div class="bea-ag-dup">
                <div>
                  <strong>{{ d.title || d.filename }}</strong>
                  <p>{{ d.espace_code }} · {{ d.module_code }}</p>
                </div>
                <div class="bea-ag-icons">
                  <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="viewerId.set(d.id)"><mat-icon>visibility</mat-icon></button>
                  <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="download(d)"><mat-icon>download</mat-icon></button>
                  <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="remove(d)"><mat-icon>delete</mat-icon></button>
                </div>
              </div>
            }
          </article>
        } @empty {
          <div class="bea-mg__empty"><p>Aucun doublon potentiel détecté.</p></div>
        }
      </div>
    </section>
    <bea-document-viewer [documentId]="viewerId()" (closed)="viewerId.set(null)" (openRelated)="viewerId.set($event)" />
  `,
  styles: `
    .bea-ag-lead { margin: 0 0 0.8rem; color: #64748b; font-size: 0.88rem; }
    .bea-ag-dups { display: grid; gap: 0.8rem; }
    .bea-ag-dups article { background: #fff; border: 1px solid #e2e8f0; border-radius: 0.8rem; padding: 0.9rem 1rem; animation: beaIn 0.4s ease both; }
    .bea-ag-dups header { display: flex; gap: 0.7rem; align-items: center; margin-bottom: 0.6rem; }
    .bea-ag-dups h2 { margin: 0; font-size: 1rem; }
    .bea-ag-dups header p, .bea-ag-dup p { margin: 0.15rem 0 0; color: #64748b; font-size: 0.82rem; }
    .bea-ag-dup { display: flex; justify-content: space-between; align-items: center; gap: 0.6rem; padding: 0.55rem 0; border-top: 1px solid #f1f5f9; }
    .bea-ag-icons { display: flex; gap: 0.15rem; }
    @keyframes beaIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
    @media (prefers-reduced-motion: reduce) { .bea-ag-dups article { animation: none; } }
  `,
})
export class ArchivesGeneralesDoublonsComponent implements OnInit {
  private readonly feedback = inject(FeedbackService);
  private readonly api = inject(ApiService);
  readonly groups = signal<DupGroup[]>([]);
  readonly erreur = feedbackSignal('error', null);
  readonly viewerId = signal<string | null>(null);
  ngOnInit(): void {
    this.api.get<DupGroup[]>('/doc-archives/general/doublons').subscribe({
      next: (rows) => this.groups.set(rows ?? []),
      error: () => this.erreur.set('Détection des doublons indisponible.'),
    });
  }

  download(d: GedDoc): void {
    this.api.download(`/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Téléchargement refusé.'),
    });
  }

  remove(d: GedDoc): void {
    this.feedback
      .run(() => this.api.delete(`/documents/${d.id}`), {
        confirm: {
          action: 'suppression',
          message: `Mettre le doublon potentiel « ${d.filename} » à la corbeille ?`,
          hint: 'Le document reste restaurable depuis la corbeille.',
        },
        loading: 'Mise à la corbeille…',
        errorTitle: 'Suppression refusée',
        success: { title: 'Document mis à la corbeille', details: [{ label: 'Fichier', value: d.filename }] },
      })
      .subscribe(() =>
        this.groups.update((groups) =>
          groups
            .map((g) => ({ ...g, documents: g.documents.filter((x) => x.id !== d.id) }))
            .filter((g) => g.documents.length > 1),
        ),
      );
  }
}

@Component({
  selector: 'bea-ag-dossiers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, RouterLink],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Documents</p>
          <h1>Dossiers documentaires</h1>
          <p class="bea-stock-page__kicker">Chaque dossier regroupe les pièces GED d'une même opération.</p>
        </div>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="creating.set(true)">
          <mat-icon>create_new_folder</mat-icon> Nouveau dossier
        </button>
      </header>
      <div class="bea-ag-folders">
        @for (d of items(); track d.entity + d.entity_id) {
          <article class="bea-ag-folder">
            <mat-icon>folder</mat-icon>
            <div>
              <h2>{{ d.reference || typeLabel(d.entity) }}</h2>
              <p>{{ espaceLabel(d.espace_code) }} · {{ moduleLabel(d.module_code) }}</p>
              <p>{{ typeLabel(d.entity) }}</p>
              <span class="bea-ag-count">{{ d.count }} document(s)</span>
            </div>
            <div class="bea-ag-icons">
              <a class="bea-mg__icon-btn" title="Ouvrir" routerLink="/archives-generales/documents" [queryParams]="{ module_code: d.module_code, entity: d.entity, entity_id: d.entity_id, espace_code: d.espace_code }"><mat-icon>visibility</mat-icon></a>
              <a class="bea-mg__icon-btn" title="Ajouter" routerLink="/archives-generales/numeriser" [queryParams]="{ module_code: d.module_code, entity: d.entity, entity_id: d.entity_id, reference: d.reference || '', espace_code: d.espace_code }"><mat-icon>upload_file</mat-icon></a>
              <button type="button" class="bea-mg__icon-btn" title="Modifier la référence" (click)="startEdit(d)"><mat-icon>edit</mat-icon></button>
              <button type="button" class="bea-mg__icon-btn" title="Supprimer le dossier" (click)="removing.set(d)"><mat-icon>delete</mat-icon></button>
            </div>
          </article>
        } @empty {
          <div class="bea-mg__empty"><p>Aucun dossier.</p></div>
        }
      </div>
    </section>

    @if (editing(); as d) {
      <div class="bea-modal" role="dialog">
        <form class="bea-modal__card" (ngSubmit)="saveEdit()">
          <h2>Modifier le dossier</h2>
          <label>Référence<input [(ngModel)]="editRef" name="ref" /></label>
          <p class="bea-stock-page__kicker">Met à jour la référence GED des documents du dossier. L'opération métier n'est pas modifiée.</p>
          <footer>
            <button type="button" class="bea-mg__btn" (click)="editing.set(null)">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Enregistrer</button>
          </footer>
        </form>
      </div>
    }
    @if (removing(); as d) {
      <div class="bea-modal" role="dialog">
        <div class="bea-modal__card">
          <h2>Supprimer ce dossier ?</h2>
          <p>Les {{ d.count }} document(s) seront mis à la corbeille. Pas de suppression définitive.</p>
          <footer>
            <button type="button" class="bea-mg__btn" (click)="removing.set(null)">Annuler</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="confirmRemove()">Supprimer</button>
          </footer>
        </div>
      </div>
    }
    @if (creating()) {
      <div class="bea-modal" role="dialog">
        <form class="bea-modal__card" (ngSubmit)="create()">
          <h2>Nouveau dossier</h2>
          <label>Département
            <select [(ngModel)]="espace" name="espace">
              <option value="moyens-generaux">Moyens Généraux</option>
              <option value="comptabilite">Comptabilité</option>
              <option value="archives">Archives</option>
            </select>
          </label>
          <label>Module<input [(ngModel)]="moduleCode" name="module" required /></label>
          <label>Type<input [(ngModel)]="entity" name="entity" required /></label>
          <label>Référence<input [(ngModel)]="reference" name="reference" /></label>
          <label>Premier document<input type="file" (change)="onCreateFile($event)" accept=".pdf,.png,.jpg,.jpeg" /></label>
          <footer>
            <button type="button" class="bea-mg__btn" (click)="creating.set(false)">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!createFile || busy()">Créer</button>
          </footer>
        </form>
      </div>
    }
  `,
  styles: `
    .bea-mg__head .bea-mg__btn { display: inline-flex; align-items: center; gap: 0.35rem; }
    .bea-ag-folders { display: grid; grid-template-columns: repeat(auto-fill, minmax(22rem, 1fr)); gap: 0.75rem; }
    .bea-ag-folder {
      display: grid; grid-template-columns: auto 1fr auto; gap: 0.8rem; align-items: center;
      background: linear-gradient(180deg, #fff, #f8fafc); border: 1px solid #e2e8f0; border-radius: 0.8rem; padding: 0.95rem 1rem;
      animation: beaIn 0.4s ease both;
    }
    .bea-ag-folder > mat-icon { color: #1a5278; font-size: 2rem; width: 2rem; height: 2rem; }
    .bea-ag-count { display: inline-block; margin-top: 0.35rem; background: #eff6ff; color: #1e40af; border-radius: 999px; padding: 0.1rem 0.5rem; font-size: 0.75rem; font-weight: 650; }
    .bea-ag-folder h2 { margin: 0; font-size: 1rem; }
    .bea-ag-folder p { margin: 0.15rem 0 0; color: #64748b; font-size: 0.84rem; }
    .bea-ag-icons { display: flex; gap: 0.15rem; }
    .bea-modal { position: fixed; inset: 0; background: rgb(15 23 42 / 45%); display: grid; place-items: center; z-index: 70; }
    .bea-modal__card { background: #fff; width: min(28rem, 92vw); border-radius: 0.75rem; padding: 1rem; display: grid; gap: 0.55rem; }
    .bea-modal__card h2 { margin: 0; }
    .bea-modal__card label { display: grid; gap: 0.2rem; font-size: 0.82rem; }
    .bea-modal__card input, .bea-modal__card select { font: inherit; padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 0.4rem; }
    .bea-modal__card footer { display: flex; justify-content: flex-end; gap: 0.4rem; }
    @keyframes beaIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
    @media (prefers-reduced-motion: reduce) { .bea-ag-folder { animation: none; } }
  `,
})
export class ArchivesGeneralesDossiersComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly items = signal<Dossier[]>([]);
  readonly erreur = feedbackSignal('error', null);
  readonly toast = feedbackSignal('success', null);
  readonly editing = signal<Dossier | null>(null);
  readonly removing = signal<Dossier | null>(null);
  readonly creating = signal(false);
  readonly busy = signal(false);
  editRef = '';
  espace = 'moyens-generaux';
  moduleCode = 'achats-appro';
  entity = 'manuel';
  reference = '';
  createFile: File | null = null;

  ngOnInit(): void {
    this.reload();
  }

  espaceLabel(code: string): string {
    return ({ 'moyens-generaux': 'Moyens Généraux', comptabilite: 'Comptabilité', archives: 'Archives' } as Record<string, string>)[code] || code;
  }
  moduleLabel(code: string): string {
    return ({ 'notes-frais': 'Notes de frais', 'stock-fournitures': 'Stock & Fournitures', 'achats-appro': 'Achats' } as Record<string, string>)[code] || code;
  }
  typeLabel(value: string): string {
    return (value || '—').replaceAll('_', ' ');
  }

  startEdit(d: Dossier): void {
    this.editRef = d.reference || '';
    this.editing.set(d);
  }

  saveEdit(): void {
    const d = this.editing();
    if (!d) return;
    this.api.get<{ items: GedDoc[] }>('/doc-archives/general', {
      module_code: d.module_code, entity: d.entity, entity_id: d.entity_id, size: 100, page: 1,
    }).subscribe({
      next: (res) => {
        const docs = res.items ?? [];
        if (!docs.length) {
          this.editing.set(null);
          return;
        }
        let left = docs.length;
        for (const doc of docs) {
          this.api.patch(`/documents/${doc.id}`, { reference: this.editRef || null }).subscribe({
            next: () => {
              left -= 1;
              if (left === 0) {
                this.editing.set(null);
                this.flash('Référence mise à jour.');
                this.reload();
              }
            },
            error: () => this.erreur.set('Modification refusée.'),
          });
        }
      },
      error: () => this.erreur.set('Dossier illisible.'),
    });
  }

  confirmRemove(): void {
    const d = this.removing();
    if (!d) return;
    this.api.get<{ items: GedDoc[] }>('/doc-archives/general', {
      module_code: d.module_code, entity: d.entity, entity_id: d.entity_id, size: 100, page: 1,
    }).subscribe({
      next: (res) => {
        const docs = res.items ?? [];
        this.removing.set(null);
        if (!docs.length) return;
        let left = docs.length;
        for (const doc of docs) {
          this.api.delete(`/documents/${doc.id}`).subscribe({
            next: () => {
              left -= 1;
              if (left === 0) {
                this.flash('Dossier mis à la corbeille.');
                this.reload();
              }
            },
            error: () => this.erreur.set('Suppression refusée.'),
          });
        }
      },
    });
  }

  onCreateFile(ev: Event): void {
    this.createFile = (ev.target as HTMLInputElement).files?.[0] ?? null;
  }

  create(): void {
    if (!this.createFile) return;
    this.busy.set(true);
    this.api.upload<GedDoc>('/documents', this.createFile, {
      espace_code: this.espace,
      module_code: this.moduleCode,
      entity: this.entity || 'manuel',
      reference: this.reference,
      doc_type: this.entity || 'MANUEL',
    }).subscribe({
      next: () => {
        this.busy.set(false);
        this.creating.set(false);
        this.createFile = null;
        this.flash('Dossier créé.');
        this.reload();
      },
      error: () => {
        this.busy.set(false);
        this.erreur.set('Création refusée (permission ged.write ?).');
      },
    });
  }

  private reload(): void {
    this.api.get<Dossier[]>('/doc-archives/general/dossiers').subscribe({
      next: (rows) => this.items.set(rows ?? []),
      error: () => this.erreur.set('Dossiers indisponibles.'),
    });
  }

  private flash(msg: string): void {
    this.toast.set(msg);
  }
}

@Component({
  selector: 'bea-ag-numeriser',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Numérisation</p>
          <h1>Scanner / Importer</h1>
        </div>
      </header>
      @if (!canUpload()) {
        <p class="bea-stock-page__error">Import réservé à la permission ged.write.</p>
      }
      <div class="bea-scan">
        <form class="bea-drop" [class.bea-drop--on]="dragOver()" (ngSubmit)="submit()"
          (dragover)="onDrag($event, true)" (dragleave)="onDrag($event, false)" (drop)="onDrop($event)">
          <mat-icon class="bea-drop__ico">document_scanner</mat-icon>
          <h2>Importer un document</h2>
          <p>Glissez un PDF, JPG ou PNG, ou parcourez vos fichiers. Le fichier est archivé, puis envoyé à l'OCR.</p>
          <div class="bea-drop__chips"><span>PDF</span><span>JPG</span><span>PNG</span></div>
          <input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" (change)="onFile($event)" />
          @if (file()) { <p class="bea-drop__file">{{ file()!.name }} · {{ file()!.size }} octets</p> }
          <label>Département
            <select [(ngModel)]="espace" name="espace" required>
              <option value="moyens-generaux">Moyens Généraux</option>
              <option value="comptabilite">Comptabilité</option>
              <option value="archives">Archives</option>
            </select>
          </label>
          <label>Module<input [(ngModel)]="moduleCode" name="module" required /></label>
          <label>Type d'entité<input [(ngModel)]="entity" name="entity" /></label>
          <label>Référence<input [(ngModel)]="reference" name="ref" /></label>
          <button class="bea-mg__btn bea-mg__btn--primary" type="submit" [disabled]="!file() || !canUpload() || busy()">
            {{ busy() ? 'Envoi…' : 'Importer' }}
          </button>
        </form>
        <aside class="bea-scan__side">
          <h2>Parcours</h2>
          <ol>
            <li [class.on]="!!file()">Dépôt du fichier</li>
            <li [class.on]="busy()">Archivage GED</li>
            <li [class.on]="!!result()">OCR puis indexation</li>
            <li>Disponible dans la recherche</li>
          </ol>
          <h2>Derniers documents</h2>
          <div class="bea-scan__recents">
            @for (r of recents(); track r.id) {
              <p><mat-icon>description</mat-icon> {{ r.filename }}</p>
            } @empty {
              <p>Aucun import récent.</p>
            }
          </div>
        </aside>
      </div>
    </section>
  `,
  styles: `
    .bea-scan { display: grid; grid-template-columns: 1.4fr 0.8fr; gap: 1rem; }
    .bea-drop {
      border: 1.5px dashed #64748b; border-radius: 0.9rem; padding: 1.4rem;
      display: grid; gap: 0.55rem; justify-items: start; background: #f8fafc;
      transition: border-color 0.35s ease, background 0.35s ease, transform 0.35s ease;
    }
    .bea-drop--on { border-color: #1a5278; background: #eff6ff; transform: translateY(-2px); }
    .bea-drop__ico { font-size: 2.4rem; width: 2.4rem; height: 2.4rem; color: #1a5278; animation: beaPulse 2.4s ease-in-out infinite; }
    .bea-drop__chips { display: flex; gap: 0.35rem; }
    .bea-drop__chips span { background: #e0f2fe; color: #075985; border-radius: 999px; padding: 0.15rem 0.55rem; font-size: 0.75rem; font-weight: 650; }
    .bea-scan__recents p { display: flex; align-items: center; gap: 0.35rem; margin: 0.35rem 0; font-size: 0.84rem; }
    @keyframes beaPulse { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
    .bea-drop h2 { margin: 0; }
    .bea-drop__file { font-weight: 650; color: #1a5278; }
    .bea-drop label { display: grid; gap: 0.2rem; font-size: 0.82rem; width: min(24rem, 100%); }
    .bea-drop input, .bea-drop select { font: inherit; padding: 0.4rem 0.5rem; border: 1px solid #cbd5e1; border-radius: 0.4rem; width: 100%; }
    .bea-scan__side { background: #fff; border: 1px solid #e2e8f0; border-radius: 0.8rem; padding: 1rem; }
    .bea-scan__side ol { margin: 0 0 1rem; padding-left: 1.1rem; display: grid; gap: 0.4rem; }
    .bea-scan__side li.on { color: #1a5278; font-weight: 650; }
    @media (max-width: 900px) { .bea-scan { grid-template-columns: 1fr; } }
    @media (prefers-reduced-motion: reduce) { .bea-drop, .bea-drop__ico { transition: none; animation: none; } }
  `,
})
export class ArchivesGeneralesNumeriserComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  readonly file = signal<File | null>(null);
  readonly busy = signal(false);
  readonly erreur = feedbackSignal('error', null);
  readonly result = feedbackSignal('success', null);
  readonly dragOver = signal(false);
  readonly recents = signal<{ id: string; filename: string }[]>([]);
  espace = 'moyens-generaux';
  moduleCode = 'achats-appro';
  entity = 'manuel';
  reference = '';

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    this.moduleCode = qp.get('module_code') || this.moduleCode;
    this.entity = qp.get('entity') || this.entity;
    this.reference = qp.get('reference') || '';
    if (qp.get('espace_code')) this.espace = qp.get('espace_code') || this.espace;
    this.api.get<{ recents: { id: string; filename: string }[] }>('/doc-archives/general/dashboard').subscribe({
      next: (d) => this.recents.set(d.recents ?? []),
    });
  }

  onDrag(ev: DragEvent, on: boolean): void {
    ev.preventDefault();
    this.dragOver.set(on);
  }

  canUpload(): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const codes = u.permission_codes ?? [];
    return codes.includes('ged.write') || codes.includes('*');
  }

  onFile(ev: Event): void {
    this.file.set((ev.target as HTMLInputElement).files?.[0] ?? null);
  }

  onDrop(ev: DragEvent): void {
    ev.preventDefault();
    this.dragOver.set(false);
    const f = ev.dataTransfer?.files?.[0];
    if (f) this.file.set(f);
  }

  submit(): void {
    const f = this.file();
    if (!f) return;
    const ok = ['application/pdf', 'image/jpeg', 'image/png'];
    const ext = f.name.toLowerCase();
    if (!ok.includes(f.type) && !/\.(pdf|jpe?g|png)$/.test(ext)) {
      this.erreur.set('Format refusé. PDF, JPG ou PNG uniquement.');
      return;
    }
    this.busy.set(true);
    this.erreur.set(null);
    this.api.upload<GedDoc>('/documents', f, {
      espace_code: this.espace,
      module_code: this.moduleCode,
      entity: this.entity || 'manuel',
      reference: this.reference,
      doc_type: this.entity || 'MANUEL',
    }).subscribe({
      next: (row) => {
        this.busy.set(false);
        this.file.set(null);
        this.result.set(`Archivé : ${row.filename}. OCR : ${row.ocr_status || 'en attente'}.`);
      },
      error: () => {
        this.busy.set(false);
        this.erreur.set('Import refusé.');
      },
    });
  }
}

@Component({
  selector: 'bea-ag-activite',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, MatIconModule, RouterLink, DocumentViewerComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div><p class="bea-stock-page__kicker">Activité</p><h1>Historique documentaire</h1></div>
        <a class="bea-mg__btn" routerLink="/archives-generales/dashboard">Dashboard</a>
      </header>
      <ol class="bea-ag-feed">
        @for (ev of events(); track ev.id) {
          <li>
            <span class="bea-ag-feed__dot" [attr.data-action]="ev.action">
              <mat-icon>{{ icon(ev.action) }}</mat-icon>
            </span>
            <div>
              <time>{{ ev.created_at ? (ev.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</time>
              <strong>{{ ev.label }}</strong>
              <p>{{ ev.filename || 'Document' }} · {{ ev.espace_code || '—' }} · {{ ev.module_code || '—' }}</p>
              @if (ev.entity_id) {
                <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="viewerId.set(ev.entity_id!)"><mat-icon>visibility</mat-icon></button>
              }
            </div>
          </li>
        } @empty {
          <li>Aucune activité récente dans le journal d'audit.</li>
        }
      </ol>
    </section>
    <bea-document-viewer [documentId]="viewerId()" (closed)="viewerId.set(null)" (openRelated)="viewerId.set($event)" />
  `,
  styles: `
    .bea-ag-feed { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.65rem; }
    .bea-ag-feed li {
      display: grid; grid-template-columns: auto 1fr; gap: 0.75rem; align-items: start;
      background: #fff; border: 1px solid #e2e8f0; border-radius: 0.75rem; padding: 0.75rem 0.9rem;
      animation: beaIn 0.35s ease both;
    }
    .bea-ag-feed__dot {
      width: 2.2rem; height: 2.2rem; border-radius: 0.6rem; display: grid; place-items: center;
      background: #eff6ff; color: #1a5278;
    }
    .bea-ag-feed__dot[data-action*='download'] { background: #ecfdf5; color: #166534; }
    .bea-ag-feed__dot[data-action*='ocr'] { background: #fff7ed; color: #9a3412; }
    .bea-ag-feed time { display: block; color: #94a3b8; font-size: 0.78rem; }
    .bea-ag-feed p { margin: 0.15rem 0 0.35rem; color: #64748b; font-size: 0.84rem; }
    @keyframes beaIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
    @media (prefers-reduced-motion: reduce) { .bea-ag-feed li { animation: none; } }
  `,
})
export class ArchivesGeneralesActiviteComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly events = signal<ActivityEvent[]>([]);
  readonly erreur = feedbackSignal('error', null);
  readonly viewerId = signal<string | null>(null);
  ngOnInit(): void {
    this.api.get<{ activite_recente: ActivityEvent[] }>('/doc-archives/general/dashboard').subscribe({
      next: (d) => this.events.set(d.activite_recente ?? []),
      error: () => this.erreur.set('Historique indisponible.'),
    });
  }

  icon(action: string): string {
    if (action.includes('download')) return 'download';
    if (action.includes('ocr')) return 'document_scanner';
    if (action.includes('version')) return 'history';
    if (action.includes('delete') || action.includes('trash')) return 'delete';
    if (action.includes('ingest') || action.includes('archive')) return 'upload_file';
    if (action.includes('update')) return 'edit';
    return 'visibility';
  }
}

@Component({
  selector: 'bea-ag-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Administration</p>
          <h1>Paramètres GED</h1>
        </div>
      </header>
      <div class="bea-ag-settings">
        <article>
          <mat-icon>picture_as_pdf</mat-icon>
          <h2>Formats acceptés</h2>
          <p>PDF, JPG, JPEG, PNG</p>
        </article>
        <article>
          <mat-icon>lock</mat-icon>
          <h2>Confidentialité</h2>
          <p>public · internal · confidential · restricted</p>
        </article>
        <article>
          <mat-icon>admin_panel_settings</mat-icon>
          <h2>Accès</h2>
          <p>Chaque utilisateur ne voit que les documents de ses départements. Lecture, téléchargement, écriture et OCR sont contrôlés par le serveur.</p>
        </article>
      </div>
    </section>
  `,
  styles: `
    .bea-ag-settings { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.8rem; }
    .bea-ag-settings article { background: #fff; border: 1px solid #e2e8f0; border-radius: 0.8rem; padding: 1rem; }
    .bea-ag-settings mat-icon { color: #1a5278; }
    .bea-ag-settings h2 { margin: 0 0 0.4rem; font-size: 1rem; }
    @media (max-width: 900px) { .bea-ag-settings { grid-template-columns: 1fr; } }
  `,
})
export class ArchivesGeneralesParametresComponent {}
