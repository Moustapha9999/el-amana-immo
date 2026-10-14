import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { UiDialogService } from '../../shared/ui-dialog/ui-dialog.service';
import { Piece, Pieces, dateFr, maintenantLocal, ouvrirBlob, taille, telechargerBlob } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

const NATURE_ICONE: Record<Piece['nature'], string> = {
  pdf: 'picture_as_pdf', image: 'image', excel: 'table_chart', word: 'description', autre: 'insert_drive_file',
};
const NOTE = 'NOTE';
const FORMATS_SCAN = '.pdf,.jpg,.jpeg,.png,.tif,.tiff,.webp';
const FORMATS_DOCUMENT = `${FORMATS_SCAN},.doc,.docx,.xls,.xlsx,.gif`;
/** Types proposés en premier pour « un autre document » (le reste suit dans l'ordre du référentiel). */
const TYPES_PRINCIPAUX = ['COURRIER', 'JUSTIFICATIF', 'FICHE_TRAITEMENT', 'RETOUR_SERVICE', 'AUTRE'];

type Mode = 'note' | 'document';
type Filtre = 'tout' | 'notes' | 'autres';

interface Saisie {
  categorie: string;
  titre: string;
  date: string;
  commentaire: string;
  fichier: File | null;
}

/** Notes et pièces jointes : chaque ajout est un nouveau fichier (jamais d'écrasement), retrait logique motivé. */
@Component({
  selector: 'bea-rc-pieces',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  template: `
    <div class="bea-rc-pj__head">
      <div>
        <h2>Notes et pièces jointes</h2>
        <p class="bea-rc-muted">Notes signées et scannées, courriers, justificatifs et documents de traitement du dossier {{ reference() }}.</p>
      </div>
      @if (pieces()?.actions?.deposer) {
        <div class="bea-rc-pj__add">
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" [attr.aria-expanded]="menu()" (click)="menu.set(!menu())">
            <mat-icon>note_add</mat-icon> Ajouter une note <mat-icon>expand_more</mat-icon>
          </button>
          @if (menu()) {
            <div class="bea-rc-pj__menu" role="menu">
              <button type="button" role="menuitem" (click)="ouvrir('note')">
                <mat-icon>document_scanner</mat-icon>
                <span><strong>Joindre une note scannée</strong><small>Note administrative ou interne rédigée, signée puis scannée (PDF ou image).</small></span>
              </button>
              <button type="button" role="menuitem" (click)="ouvrir('document')">
                <mat-icon>attach_file</mat-icon>
                <span><strong>Joindre un autre document</strong><small>Courrier, justificatif, document de traitement, retour du service…</small></span>
              </button>
            </div>
          }
        </div>
      }
    </div>

    @if (pieces(); as p) {
      @if (p.items.length) {
        <div class="bea-rc-pj__chips" role="tablist" aria-label="Filtrer les pièces">
          <button type="button" role="tab" [class.is-on]="filtre() === 'tout'" (click)="filtre.set('tout')">Tout <small>{{ p.items.length }}</small></button>
          <button type="button" role="tab" [class.is-on]="filtre() === 'notes'" (click)="filtre.set('notes')">Notes <small>{{ nbNotes() }}</small></button>
          <button type="button" role="tab" [class.is-on]="filtre() === 'autres'" (click)="filtre.set('autres')">Autres documents <small>{{ p.items.length - nbNotes() }}</small></button>
        </div>
      }
      <ul class="bea-ct-docs__list">
        @for (d of visibles(); track d.id) {
          <li>
            <div class="bea-ct-docs__row">
              <span class="bea-ct-docs__icon" [attr.data-nature]="d.nature"><mat-icon>{{ icone(d) }}</mat-icon></span>
              <div class="bea-ct-docs__meta">
                <strong [title]="d.titre || d.filename">{{ d.titre || d.filename }}</strong>
                <small>
                  <span class="bea-ct-badge" [attr.data-tone]="ton(d.categorie)">{{ d.categorie_libelle }}</span>
                  @if (d.date_document) { <span>Daté du {{ date(d.date_document) }}</span> · }
                  <span class="bea-rc-pj__file" [title]="d.filename">{{ d.filename }}</span> · {{ taille(d.size_bytes) }}
                </small>
                <small>Ajouté le {{ date(d.created_at, true) }}{{ d.depose_par ? ' par ' + d.depose_par : '' }}</small>
                @if (d.commentaire) { <small class="bea-rc-pj__comment">{{ d.commentaire }}</small> }
              </div>
              <div class="bea-ct-docs__tools">
                @if (p.actions.telecharger) {
                  @if (d.nature === 'pdf' || d.nature === 'image') {
                    <button type="button" class="bea-mg__icon-btn" title="Consulter" aria-label="Consulter" (click)="apercu(d)"><mat-icon>visibility</mat-icon></button>
                  }
                  <button type="button" class="bea-mg__icon-btn" title="Télécharger" aria-label="Télécharger" (click)="telecharger(d)"><mat-icon>download</mat-icon></button>
                }
                @if (p.actions.retirer) {
                  <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Retirer (motif obligatoire)" aria-label="Retirer" [disabled]="busy()" (click)="retirer(d)"><mat-icon>delete</mat-icon></button>
                }
              </div>
            </div>
          </li>
        } @empty {
          <li><div class="bea-ct-empty"><mat-icon>folder_off</mat-icon>
            <p>{{ p.items.length ? 'Aucune pièce de ce type.' : 'Aucune note ni pièce jointe dans ce dossier.' }}</p>
          </div></li>
        }
      </ul>
      @if (!p.actions.telecharger && p.items.length) {
        <p class="bea-rc-hint">Vous pouvez voir la liste des pièces mais pas les ouvrir : la consultation et le téléchargement relèvent d’une permission distincte.</p>
      }
    } @else if (erreur()) {
      <div class="bea-ct-empty"><mat-icon>cloud_off</mat-icon><p>Pièces indisponibles.</p>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon> Réessayer</button>
      </div>
    } @else {
      <p class="bea-rc-muted">Chargement des pièces…</p>
    }

    @if (mode(); as m) {
      <div class="bea-mg__backdrop" (click)="fermer()"></div>
      <form class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" (ngSubmit)="enregistrer()">
        <div class="bea-mg__modal-head">
          <h2>{{ m === 'note' ? 'Joindre une note scannée' : 'Joindre un document' }} — {{ reference() }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
        </div>
        <div class="bea-rc-form">
          @if (m === 'note') {
            <div class="bea-rc-note"><mat-icon>info</mat-icon>
              <span>Rédigez et signez la note hors de BEA DIGITAL, puis joignez son scan (PDF ou image). Elle s’ajoute au dossier sans remplacer les documents existants.</span>
            </div>
          }
          <div class="bea-rc-row">
            <label>Type de document <em>*</em>
              <select name="categorie" [(ngModel)]="saisie.categorie" [disabled]="m === 'note'">
                @for (c of types(); track c.code) { <option [value]="c.code">{{ c.libelle }}</option> }
              </select>
            </label>
            <label>{{ m === 'note' ? 'Date de la note' : 'Date du document' }} <em>*</em>
              <input type="date" name="date" [(ngModel)]="saisie.date" [max]="aujourdhui" [class.is-invalid]="tente() && !dateValide()" />
            </label>
          </div>
          <label>Titre ou objet @if (m === 'note') { <em>*</em> }
            <input name="titre" [(ngModel)]="saisie.titre" maxlength="255" [class.is-invalid]="tente() && m === 'note' && !saisie.titre.trim()"
                   [placeholder]="m === 'note' ? 'Ex. Note interne — analyse du prélèvement contesté' : 'Facultatif — sinon le type de document est repris'" />
          </label>
          <label>Commentaire
            <textarea name="commentaire" [(ngModel)]="saisie.commentaire" rows="2" maxlength="2000" placeholder="Facultatif — contenu ou contexte du document"></textarea>
          </label>
          <div class="bea-ct-docs__drop" [class.is-drag]="survol()" [class.is-invalid]="tente() && !saisie.fichier"
               (dragover)="$event.preventDefault(); survol.set(true)" (dragleave)="survol.set(false)" (drop)="deposerDrop($event)">
            <mat-icon>{{ saisie.fichier ? 'task' : 'cloud_upload' }}</mat-icon>
            <div class="bea-ct-docs__drop-text">
              <strong>{{ saisie.fichier ? saisie.fichier.name : 'Glissez le fichier ici' }}</strong>
              <small>{{ saisie.fichier ? taille(saisie.fichier.size) : (m === 'note' ? 'PDF ou image scannée (JPG, PNG, TIFF), 25 Mo maximum.' : 'PDF, image, Word ou Excel, 25 Mo maximum.') }}</small>
            </div>
            <label class="bea-mg__btn bea-mg__btn--ghost bea-ct-docs__pick">
              <mat-icon>attach_file</mat-icon> {{ saisie.fichier ? 'Changer' : 'Choisir un fichier' }}
              <input type="file" hidden [accept]="m === 'note' ? formatsScan : formatsDocument" (change)="choisirFichier($event)" />
            </label>
          </div>
        </div>
        <div class="bea-mg__modal-foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="fermer()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Joindre au dossier</button>
        </div>
      </form>
    }
  `,
})
export class RcPiecesComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialogs = inject(UiDialogService);
  readonly store = inject(ReclamationsStore);

  readonly dossierId = input.required<string>();
  readonly reference = input.required<string>();
  readonly modifie = output<number>();

  readonly pieces = signal<Pieces | null>(null);
  readonly erreur = signal(false);
  readonly busy = signal(false);
  readonly survol = signal(false);
  readonly menu = signal(false);
  readonly mode = signal<Mode | null>(null);
  readonly tente = signal(false);
  readonly filtre = signal<Filtre>('tout');
  readonly taille = taille;
  readonly aujourdhui = maintenantLocal().slice(0, 10);
  readonly formatsScan = FORMATS_SCAN;
  readonly formatsDocument = FORMATS_DOCUMENT;
  saisie: Saisie = this.vide(NOTE);

  readonly nbNotes = computed(() => (this.pieces()?.items ?? []).filter((d) => d.categorie === NOTE).length);
  readonly visibles = computed(() => {
    const items = this.pieces()?.items ?? [];
    const f = this.filtre();
    return f === 'tout' ? items : items.filter((d) => (d.categorie === NOTE) === (f === 'notes'));
  });
  readonly types = computed(() => {
    const tous = this.store.libelles('categories_document');
    if (this.mode() === 'note') return tous.filter((c) => c.code === NOTE);
    const autres = tous.filter((c) => c.code !== NOTE);
    const rang = (code: string) => {
      const i = TYPES_PRINCIPAUX.indexOf(code);
      return i < 0 ? TYPES_PRINCIPAUX.length : i;
    };
    return [...autres].sort((a, b) => rang(a.code) - rang(b.code));
  });

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

  ton(categorie: string): string {
    if (categorie === NOTE) return 'ACTIF';
    return categorie === 'ORIGINAL' || categorie === 'REPONSE_CLIENT' || categorie === 'PREUVE_ENVOI' ? 'ATTENTION' : 'INFO';
  }

  date(iso: string | null, heure = false): string {
    return dateFr(iso, heure);
  }

  dateValide(): boolean {
    return !!this.saisie.date && this.saisie.date <= this.aujourdhui;
  }

  private vide(categorie: string): Saisie {
    return { categorie, titre: '', date: maintenantLocal().slice(0, 10), commentaire: '', fichier: null };
  }

  ouvrir(m: Mode): void {
    this.menu.set(false);
    this.tente.set(false);
    this.saisie = this.vide(m === 'note' ? NOTE : 'COURRIER');
    this.mode.set(m);
  }

  fermer(): void {
    if (this.busy()) return;
    const s = this.saisie;
    if (!s.fichier && !s.titre.trim() && !s.commentaire.trim()) {
      this.mode.set(null);
      return;
    }
    this.dialogs.confirmAction('depart', 'Le document saisi ne sera pas joint au dossier.').subscribe((ok) => {
      if (ok) this.mode.set(null);
    });
  }

  choisirFichier(ev: Event): void {
    const champ = ev.target as HTMLInputElement;
    const fichier = champ.files?.[0];
    champ.value = '';
    if (fichier) this.saisie = { ...this.saisie, fichier };
  }

  deposerDrop(ev: DragEvent): void {
    ev.preventDefault();
    this.survol.set(false);
    const fichier = ev.dataTransfer?.files?.[0];
    if (fichier && !this.busy()) this.saisie = { ...this.saisie, fichier };
  }

  enregistrer(): void {
    const m = this.mode();
    const s = this.saisie;
    this.tente.set(true);
    const manque = !s.fichier ? 'Choisissez le fichier à joindre.'
      : m === 'note' && !s.titre.trim() ? 'Indiquez le titre ou l’objet de la note.'
      : !this.dateValide() ? 'La date du document est obligatoire et ne peut pas être dans le futur.'
      : m === 'note' && !/\.(pdf|jpe?g|png|tiff?|webp)$/i.test(s.fichier.name) ? 'Une note scannée se joint en PDF ou en image.'
      : null;
    if (manque || !s.fichier) {
      this.feedback.warning({ title: 'Document incomplet', message: manque ?? '' });
      return;
    }
    const fichier = s.fichier;
    const libelle = this.store.libelles('categories_document').find((c) => c.code === s.categorie)?.libelle ?? s.categorie;
    this.feedback
      .run(() => this.rc.deposer(this.dossierId(), fichier, s.categorie, s.commentaire.trim(), {
        titre: s.titre.trim(), date_document: s.date,
      }), {
        busy: this.busy,
        loading: 'Ajout du document…',
        success: () => ({ title: m === 'note' ? 'Note jointe au dossier' : 'Document joint au dossier', details: [
          { label: 'Type', value: libelle },
          ...(s.titre.trim() ? [{ label: 'Titre', value: s.titre.trim() }] : []),
          { label: 'Fichier', value: fichier.name },
        ] }),
        errorTitle: 'Ajout refusé',
        errorHint: 'Votre saisie a été conservée.',
        retry: false,
      })
      .subscribe((p) => {
        this.pieces.set(p);
        this.mode.set(null);
        this.modifie.emit(p.items.length);
      });
  }

  apercu(d: Piece): void {
    this.rc.fichier(this.dossierId(), d.id, true).subscribe({
      next: (blob) => ouvrirBlob(blob),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Consultation impossible')),
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
          message: `${d.titre || d.filename} (${d.categorie_libelle}) — ${this.reference()}. La pièce passe à la corbeille GED : elle n’est pas détruite et le retrait est tracé.`,
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
