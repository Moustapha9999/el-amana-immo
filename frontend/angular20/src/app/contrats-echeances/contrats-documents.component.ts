import { ChangeDetectionStrategy, Component, HostListener, Input, OnChanges, OnDestroy, computed, inject, signal } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { MatIconModule } from '@angular/material/icon';
import { from } from 'rxjs';
import { concatMap, finalize } from 'rxjs/operators';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { PIECES_ACCEPT, detacherReason, extensionFichier, iconePiece, naturePiece, verifierPieceJointe } from '../shared/pieces-jointes';
import { dateHeureFr, telechargerBlob } from './contrats.models';

interface GedDoc {
  id: string;
  filename: string;
  size_bytes: number;
  mime_type: string | null;
  created_at: string | null;
  title: string | null;
  doc_type: string | null;
  version: number;
  parent_document_id: string | null;
  version_comment: string | null;
}

interface DocGroupe {
  courant: GedDoc;
  anciennes: GedDoc[];
}

@Component({
  selector: 'bea-contrats-documents',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <section class="bea-ct-docs">
      @if (!lectureSeule) {
        <div
          class="bea-ct-docs__drop"
          [class.is-drag]="dragging()"
          (dragover)="onDragOver($event)"
          (dragleave)="dragging.set(false)"
          (drop)="onDrop($event)"
        >
          <mat-icon>cloud_upload</mat-icon>
          <div class="bea-ct-docs__drop-text">
            <strong>Glissez-déposez vos fichiers ici</strong>
            <small>PDF, Word, Excel, PNG, JPG — {{ tailleMaxMo }} Mo maximum par fichier · sélection multiple possible</small>
          </div>
          <label class="bea-ct-docs__type">Typologie
            <select [value]="docType()" (change)="docType.set($any($event.target).value)">
              @for (t of typesDocument; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
            </select>
          </label>
          <label class="bea-mg__btn bea-mg__btn--primary bea-ct-docs__pick" [class.is-busy]="uploading()">
            <mat-icon>attach_file</mat-icon> {{ uploading() ? progression() : 'Choisir des fichiers' }}
            <input type="file" multiple [accept]="accept" hidden [disabled]="uploading()" (change)="onFiles($event)" />
          </label>
        </div>
      }

      @if (groupes().length) {
        <ul class="bea-ct-docs__list">
          @for (g of groupes(); track g.courant.id) {
            <li>
              <div class="bea-ct-docs__row">
                <span class="bea-ct-docs__icon" [attr.data-nature]="nature(g.courant)"><mat-icon>{{ icone(g.courant) }}</mat-icon></span>
                <div class="bea-ct-docs__meta">
                  <strong>{{ g.courant.title || g.courant.filename }}</strong>
                  <small>
                    <span class="bea-ct-badge" data-tone="INFO">{{ typeLabel(g.courant.doc_type) }}</span>
                    v{{ g.courant.version }} · {{ taille(g.courant.size_bytes) }}
                    @if (g.courant.created_at) { · {{ dateHeure(g.courant.created_at) }} }
                    @if (g.courant.version_comment) { · « {{ g.courant.version_comment }} » }
                  </small>
                </div>
                <div class="bea-ct-docs__tools">
                  @if (previsualisable(g.courant)) {
                    <button type="button" class="bea-mg__icon-btn" title="Prévisualiser" (click)="previsualiser(g.courant)"><mat-icon>visibility</mat-icon></button>
                  }
                  <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="telecharger(g.courant)"><mat-icon>download</mat-icon></button>
                  @if (!lectureSeule) {
                    <label class="bea-mg__icon-btn" title="Déposer une nouvelle version">
                      <mat-icon>upload</mat-icon>
                      <input type="file" [accept]="accept" hidden (change)="nouvelleVersion(g, $event)" />
                    </label>
                    <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Détacher" (click)="detacher(g.courant)"><mat-icon>link_off</mat-icon></button>
                  }
                  @if (g.anciennes.length) {
                    <button type="button" class="bea-mg__icon-btn" [title]="ouvert() === g.courant.id ? 'Masquer les versions' : 'Versions précédentes'" (click)="basculer(g.courant.id)">
                      <mat-icon>history</mat-icon>
                    </button>
                  }
                </div>
              </div>
              @if (ouvert() === g.courant.id) {
                <ul class="bea-ct-docs__versions">
                  @for (v of g.anciennes; track v.id) {
                    <li>
                      <span>v{{ v.version }} — {{ v.filename }}</span>
                      <small>{{ v.created_at ? dateHeure(v.created_at) : '' }}{{ v.version_comment ? ' · ' + v.version_comment : '' }}</small>
                      @if (previsualisable(v)) {
                        <button type="button" class="bea-mg__icon-btn" title="Prévisualiser" (click)="previsualiser(v)"><mat-icon>visibility</mat-icon></button>
                      }
                      <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="telecharger(v)"><mat-icon>download</mat-icon></button>
                    </li>
                  }
                </ul>
              }
            </li>
          }
        </ul>
      } @else {
        <div class="bea-ct-empty"><mat-icon>folder_open</mat-icon><p>Aucun document associé à ce contrat.</p></div>
      }
    </section>

    @if (apercu(); as a) {
      <div class="bea-mg__backdrop" (click)="fermerApercu()"></div>
      <div class="bea-mg__modal bea-mg__modal--lg bea-ct-preview" role="dialog" aria-modal="true" [attr.aria-label]="'Aperçu ' + a.nom">
        <header class="bea-ct-view__head">
          <div><h2>{{ a.nom }}</h2></div>
          <button type="button" class="bea-ct-view__close" title="Fermer" aria-label="Fermer" (click)="fermerApercu()"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-ct-preview__body">
          @if (a.image) {
            <img [src]="a.url" [alt]="a.nom" />
          } @else {
            <iframe [src]="a.url" [title]="a.nom"></iframe>
          }
        </div>
      </div>
    }
  `,
})
export class ContratsDocumentsComponent implements OnChanges, OnDestroy {
  @Input({ required: true }) contratId!: string;
  @Input() reference: string | null = null;
  @Input() lectureSeule = false;
  @Input() typesDocument: { code: string; libelle: string }[] = [];
  @Input() tailleMaxMo = 15;
  /** Typologie présélectionnée (ex. PREUVE_PAIEMENT depuis un paiement). */
  @Input() typeInitial: string | null = null;

  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly sanitizer = inject(DomSanitizer);

  readonly accept = PIECES_ACCEPT;
  readonly docs = signal<GedDoc[]>([]);
  readonly docType = signal('CONTRAT_SIGNE');
  readonly dragging = signal(false);
  readonly uploading = signal(false);
  readonly progression = signal('');
  readonly ouvert = signal<string | null>(null);
  readonly apercu = signal<{ nom: string; url: SafeResourceUrl; brut: string; image: boolean } | null>(null);

  readonly groupes = computed<DocGroupe[]>(() => {
    const all = this.docs();
    const racines = all.filter((d) => !d.parent_document_id || !all.some((x) => x.id === d.parent_document_id));
    return racines
      .map((r) => {
        const famille = [r, ...all.filter((d) => d.parent_document_id === r.id)].sort((a, b) => b.version - a.version);
        return { courant: famille[0], anciennes: famille.slice(1) };
      })
      .sort((a, b) => (b.courant.created_at ?? '').localeCompare(a.courant.created_at ?? ''));
  });

  ngOnChanges(): void {
    if (this.typeInitial) this.docType.set(this.typeInitial);
    this.reload();
  }

  ngOnDestroy(): void {
    this.fermerApercu();
  }

  reload(): void {
    const q = `module_code=contrats-echeances&entity=contrat&entity_id=${encodeURIComponent(this.contratId)}`;
    this.api.get<{ items: GedDoc[] }>(`/ged/documents?${q}`).subscribe({
      next: (res) => this.docs.set(res.items ?? []),
      error: (e) => this.fail(e, 'Lecture des documents impossible'),
    });
  }

  onDragOver(ev: DragEvent): void {
    ev.preventDefault();
    this.dragging.set(true);
  }

  onDrop(ev: DragEvent): void {
    ev.preventDefault();
    this.dragging.set(false);
    this.envoyer(Array.from(ev.dataTransfer?.files ?? []));
  }

  onFiles(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    this.envoyer(Array.from(input.files ?? []));
    input.value = '';
  }

  private verifier(file: File): string | null {
    const refus = verifierPieceJointe(file);
    if (refus) return refus;
    if (file.size > this.tailleMaxMo * 1024 * 1024) return `Fichier trop volumineux (${this.tailleMaxMo} Mo maximum).`;
    return null;
  }

  private envoyer(files: File[]): void {
    if (!files.length || this.uploading()) return;
    const refus = files.map((f) => ({ f, msg: this.verifier(f) })).filter((x) => x.msg);
    if (refus.length) {
      this.feedback.warning({
        title: refus.length > 1 ? `${refus.length} fichiers refusés` : 'Fichier refusé',
        details: refus.map((x) => ({ label: x.f.name, value: x.msg ?? '' })),
      });
    }
    const ok = files.filter((f) => !this.verifier(f));
    if (!ok.length) return;
    const type = this.docType();
    let n = 0;
    let reussis = 0;
    this.uploading.set(true);
    from(ok)
      .pipe(
        concatMap((file) => {
          n += 1;
          this.progression.set(`Envoi ${n}/${ok.length}…`);
          const fields: Record<string, string> = {
            espace_code: 'moyens-generaux',
            module_code: 'contrats-echeances',
            source_type: 'contrat',
            source_id: this.contratId,
            doc_type: type,
            title: file.name,
          };
          if (this.reference) fields['reference'] = this.reference;
          return this.api.upload<GedDoc>('/documents/from-operation', file, fields);
        }),
        finalize(() => {
          this.uploading.set(false);
          this.progression.set('');
          this.reload();
          if (reussis) {
            this.feedback.success({
              title: reussis > 1 ? `${reussis} documents déposés` : 'Document déposé',
              details: [{ label: 'Typologie', value: this.typeLabel(type) }],
            });
          }
        }),
      )
      .subscribe({
        next: () => (reussis += 1),
        error: (e) => this.fail(e, 'Dépôt refusé'),
      });
  }

  nouvelleVersion(g: DocGroupe, ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    const refus = this.verifier(file);
    if (refus) {
      this.feedback.warning({ title: 'Fichier refusé', message: refus });
      return;
    }
    const racine = g.courant.parent_document_id ?? g.courant.id;
    this.feedback
      .runWithReason(
        (commentaire) => this.api.upload<GedDoc>(`/documents/${racine}/versions`, file, commentaire ? { version_comment: commentaire } : {}),
        {
          reason: {
            title: 'Nouvelle version',
            message: `Déposer « ${file.name} » comme version ${g.courant.version + 1} de « ${g.courant.title || g.courant.filename} » ?`,
            hint: 'Les versions précédentes restent consultables.',
            confirmLabel: 'Déposer',
            cancelLabel: 'Annuler',
            reasonLabel: 'Commentaire de version (optionnel)',
            reasonPlaceholder: 'Ex. : version signée, correction de l’annexe…',
            required: false,
            maxLength: 500,
            icon: 'upload',
          },
          loading: 'Dépôt de la nouvelle version…',
          errorTitle: 'Dépôt refusé',
          success: (d) => ({ title: 'Nouvelle version déposée', details: [{ label: 'Version', value: `v${d.version}` }] }),
        },
      )
      .subscribe(() => this.reload());
  }

  detacher(doc: GedDoc): void {
    this.feedback
      .runWithReason((motif) => this.api.delete(`/ged/documents/${doc.id}?reason=${encodeURIComponent(motif)}`), {
        reason: detacherReason(doc.filename),
        loading: 'Détachement de la pièce…',
        errorTitle: 'Détachement refusé',
        success: { title: 'Pièce détachée', details: [{ label: 'Fichier', value: doc.filename }] },
      })
      .subscribe(() => this.reload());
  }

  telecharger(doc: GedDoc): void {
    this.api.download(`/ged/documents/${doc.id}/download`).subscribe({
      next: (blob) => telechargerBlob(blob, doc.filename || 'document'),
      error: (e) => this.fail(e, 'Téléchargement impossible'),
    });
  }

  previsualiser(doc: GedDoc): void {
    const image = this.nature(doc) === 'image';
    this.api.download(`/ged/documents/${doc.id}/download`).subscribe({
      next: (blob) => {
        this.fermerApercu();
        const typed = new Blob([blob], { type: image ? blob.type || 'image/png' : 'application/pdf' });
        const brut = URL.createObjectURL(typed);
        this.apercu.set({ nom: doc.title || doc.filename, url: this.sanitizer.bypassSecurityTrustResourceUrl(brut), brut, image });
      },
      error: (e) => this.fail(e, 'Prévisualisation impossible'),
    });
  }

  @HostListener('document:keydown.escape')
  fermerApercu(): void {
    const a = this.apercu();
    if (a) URL.revokeObjectURL(a.brut);
    this.apercu.set(null);
  }

  basculer(id: string): void {
    this.ouvert.update((o) => (o === id ? null : id));
  }

  nature(doc: GedDoc): string {
    return naturePiece(doc.filename, doc.mime_type);
  }

  icone(doc: GedDoc): string {
    return iconePiece(doc.filename, doc.mime_type);
  }

  previsualisable(doc: GedDoc): boolean {
    const n = this.nature(doc);
    return n === 'pdf' || (n === 'image' && !['tif', 'tiff'].includes(extensionFichier(doc.filename)));
  }

  typeLabel(code: string | null): string {
    return this.typesDocument.find((t) => t.code === code)?.libelle ?? code ?? 'Document';
  }

  taille(bytes: number): string {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  }

  dateHeure(iso: string): string {
    return dateHeureFr(iso);
  }

  private fail(err: unknown, title: string): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, title));
  }
}
