import { ChangeDetectionStrategy, Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { Piece, Pieces, dateFr, ouvrirBlob, taille, telechargerBlob } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

const NATURE_ICONE: Record<Piece['nature'], string> = {
  pdf: 'picture_as_pdf', image: 'image', excel: 'table_chart', word: 'description', autre: 'insert_drive_file',
};

/** Pièces du dossier : chaque dépôt est un nouveau fichier (jamais d'écrasement), retrait logique motivé. */
@Component({
  selector: 'bea-rc-pieces',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  template: `
    @if (pieces(); as p) {
      @if (p.actions.deposer) {
        <div class="bea-ct-docs__drop" [class.is-drag]="survol()" (dragover)="$event.preventDefault(); survol.set(true)"
             (dragleave)="survol.set(false)" (drop)="deposerDrop($event)">
          <mat-icon>cloud_upload</mat-icon>
          <div class="bea-ct-docs__drop-text">
            <strong>Ajouter une pièce</strong>
            <small>PDF, image, Word ou Excel. Un nouveau dépôt n’écrase jamais une pièce existante.</small>
          </div>
          <label class="bea-ct-docs__type">Catégorie
            <select [(ngModel)]="categorie" name="categorie">
              @for (c of store.libelles('categories_document'); track c.code) { <option [value]="c.code">{{ c.libelle }}</option> }
            </select>
          </label>
          <label class="bea-ct-docs__type">Commentaire
            <input class="bea-rc-input" [(ngModel)]="commentaire" name="commentaire" maxlength="2000" placeholder="Facultatif" />
          </label>
          <label class="bea-mg__btn bea-mg__btn--primary bea-ct-docs__pick" [class.is-busy]="busy()">
            <mat-icon>attach_file</mat-icon> Choisir un fichier
            <input type="file" hidden [disabled]="busy()" (change)="deposerInput($event)" />
          </label>
        </div>
      }
      <ul class="bea-ct-docs__list">
        @for (d of p.items; track d.id) {
          <li>
            <div class="bea-ct-docs__row">
              <span class="bea-ct-docs__icon" [attr.data-nature]="d.nature"><mat-icon>{{ icone(d) }}</mat-icon></span>
              <div class="bea-ct-docs__meta">
                <strong [title]="d.filename">{{ d.filename }}</strong>
                <small>
                  <span class="bea-ct-badge" [attr.data-tone]="d.categorie === 'ORIGINAL' ? 'ACTIF' : 'INFO'">{{ d.categorie_libelle }}</span>
                  {{ taille(d.size_bytes) }} · {{ date(d.created_at) }}{{ d.depose_par ? ' · ' + d.depose_par : '' }}
                </small>
                @if (d.commentaire) { <small>{{ d.commentaire }}</small> }
              </div>
              <div class="bea-ct-docs__tools">
                @if (p.actions.telecharger) {
                  @if (d.nature === 'pdf' || d.nature === 'image') {
                    <button type="button" class="bea-mg__icon-btn" title="Aperçu" (click)="apercu(d)"><mat-icon>visibility</mat-icon></button>
                  }
                  <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="telecharger(d)"><mat-icon>download</mat-icon></button>
                }
                @if (p.actions.retirer) {
                  <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Retirer (motif obligatoire)" [disabled]="busy()" (click)="retirer(d)"><mat-icon>delete</mat-icon></button>
                }
              </div>
            </div>
          </li>
        } @empty {
          <li><div class="bea-ct-empty"><mat-icon>folder_off</mat-icon><p>Aucune pièce dans ce dossier.</p></div></li>
        }
      </ul>
    } @else if (erreur()) {
      <div class="bea-ct-empty"><mat-icon>cloud_off</mat-icon><p>Pièces indisponibles.</p>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon> Réessayer</button>
      </div>
    } @else {
      <p class="bea-rc-muted">Chargement des pièces…</p>
    }
  `,
})
export class RcPiecesComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);

  readonly dossierId = input.required<string>();
  readonly reference = input.required<string>();
  readonly modifie = output<number>();

  readonly pieces = signal<Pieces | null>(null);
  readonly erreur = signal(false);
  readonly busy = signal(false);
  readonly survol = signal(false);
  readonly taille = taille;
  categorie = 'ORIGINAL';
  commentaire = '';

  ngOnInit(): void {
    this.charger();
  }

  charger(): void {
    this.erreur.set(false);
    this.rc.pieces(this.dossierId()).subscribe({
      next: (p) => this.pieces.set(p),
      error: (e) => {
        this.erreur.set(true);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Pièces indisponibles'));
      },
    });
  }

  icone(d: Piece): string {
    return NATURE_ICONE[d.nature] ?? 'insert_drive_file';
  }

  date(iso: string | null): string {
    return dateFr(iso, true);
  }

  deposerInput(ev: Event): void {
    const champ = ev.target as HTMLInputElement;
    const fichier = champ.files?.[0];
    champ.value = '';
    if (fichier) this.deposer(fichier);
  }

  deposerDrop(ev: DragEvent): void {
    ev.preventDefault();
    this.survol.set(false);
    const fichier = ev.dataTransfer?.files?.[0];
    if (fichier && !this.busy()) this.deposer(fichier);
  }

  private deposer(fichier: File): void {
    const categorie = this.categorie;
    const libelle = this.store.libelles('categories_document').find((c) => c.code === categorie)?.libelle ?? categorie;
    this.feedback
      .run(() => this.rc.deposer(this.dossierId(), fichier, categorie, this.commentaire.trim()), {
        busy: this.busy,
        loading: 'Dépôt de la pièce…',
        success: () => ({ title: 'Pièce ajoutée', details: [{ label: 'Fichier', value: fichier.name }, { label: 'Catégorie', value: libelle }] }),
        errorTitle: 'Dépôt refusé',
        retry: false,
      })
      .subscribe((p) => {
        this.pieces.set(p);
        this.commentaire = '';
        if (categorie === 'ORIGINAL') this.categorie = 'PIECE_CLIENT';
        this.modifie.emit(p.items.length);
      });
  }

  apercu(d: Piece): void {
    this.rc.fichier(this.dossierId(), d.id, true).subscribe({
      next: (blob) => ouvrirBlob(blob),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Aperçu impossible')),
    });
  }

  telecharger(d: Piece): void {
    this.rc.fichier(this.dossierId(), d.id).subscribe({
      next: (blob) => telechargerBlob(blob, d.filename),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Téléchargement impossible')),
    });
  }

  retirer(d: Piece): void {
    this.feedback
      .runWithReason((motif) => this.rc.retirer(this.dossierId(), d.id, motif), {
        reason: {
          title: 'Retirer la pièce',
          message: `${d.filename} (${d.categorie_libelle}) — ${this.reference()}. La pièce passe à la corbeille GED : elle n’est pas détruite et le retrait est tracé.`,
          reasonLabel: 'Motif du retrait',
          required: true,
          maxLength: 1000,
          tone: 'danger',
          confirmLabel: 'Retirer',
        },
        busy: this.busy,
        loading: 'Retrait…',
        success: () => ({ title: 'Pièce retirée', details: [{ label: 'Fichier', value: d.filename }] }),
        errorTitle: 'Retrait refusé',
        retry: false,
      })
      .subscribe((p) => {
        this.pieces.set(p);
        this.modifie.emit(p.items.length);
      });
  }
}
