import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  OnChanges,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { MontantPipe } from '../shared/montant.pipe';
import {
  Note,
  canDeleteNote,
  canEditNote,
  canPayNotes,
  isNotePayable,
  deleteNoteHint,
  editNoteHint,
  formatNoteApiError,
  noteStatutLabel,
  noteStatutTone,
  statutPaiementLabel,
} from './notes-frais.shared';

/** Aperçu d'une note de frais en modale (Registre, Rapports). */
@Component({
  selector: 'bea-note-apercu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, DatePipe, MontantPipe],
  template: `
    <div class="bea-mg__backdrop" (click)="close()"></div>
    <div class="bea-mg__modal bea-ct-view bea-nf-view" role="dialog" aria-modal="true" aria-labelledby="bea-nf-view-title">
      @if (note(); as n) {
        <header class="bea-ct-view__head">
          <div>
            <p class="bea-ct-view__kicker">
              <code class="bea-mg__code">{{ n.reference }}</code>
              <span class="bea-nf-badge" [attr.data-tone]="tone(n.statut)">{{ label(n.statut) }}</span>
            </p>
            <h2 id="bea-nf-view-title">{{ n.agence_libelle_snapshot || 'Note de frais' }}</h2>
            <p class="bea-ct-view__sub">
              Demandée le {{ n.date_demande | date: 'dd/MM/yyyy' }}
              @if (n.demandeur_nom) { · par {{ n.demandeur_nom }} }
            </p>
          </div>
          <button type="button" class="bea-ct-view__close" title="Fermer" aria-label="Fermer" (click)="close()">
            <mat-icon>close</mat-icon>
          </button>
        </header>

        <div class="bea-ct-view__body">
          <div class="bea-ct-view__kpis">
            <div>
              <span>Total</span>
              <strong>{{ n.total_mru | montant }} {{ n.devise || 'MRU' }}</strong>
              <small>{{ n.lignes.length }} dépense(s)</small>
            </div>
            <div>
              <span>Payé</span>
              <strong>{{ n.montant_paye | montant }} {{ n.devise || 'MRU' }}</strong>
              <small>{{ tauxPaye() }} % réglé</small>
            </div>
            <div [class.bea-nf-view__kpi--due]="reste() > 0">
              <span>Reste à payer</span>
              <strong>{{ reste() | montant }} {{ n.devise || 'MRU' }}</strong>
              <small>{{ payLabel(n.statut_paiement) }}</small>
            </div>
          </div>
          <div class="bea-nf-view__progress" aria-hidden="true"><i [style.width.%]="tauxPaye()"></i></div>

          @if (n.motif_rejet || n.motif_correction) {
            <p class="bea-nf-view__alert">
              <mat-icon>{{ n.motif_rejet ? 'block' : 'edit_note' }}</mat-icon>
              <span>
                <strong>{{ n.motif_rejet ? 'Motif du rejet' : 'Correction demandée' }} :</strong>
                {{ n.motif_rejet || n.motif_correction }}
              </span>
            </p>
          }

          <section class="bea-ct-view__section">
            <h3><mat-icon>badge</mat-icon> Demandeur</h3>
            <dl class="bea-ct-view__dl">
              <div><dt>Identité</dt><dd>{{ n.demandeur_nom || '—' }}</dd></div>
              <div><dt>Département</dt><dd>{{ n.departement || '—' }}</dd></div>
              <div><dt>Fonction</dt><dd>{{ n.fonction || '—' }}</dd></div>
              <div><dt>Objet</dt><dd>{{ n.objet || '—' }}</dd></div>
            </dl>
          </section>

          <section class="bea-ct-view__section">
            <h3><mat-icon>receipt_long</mat-icon> Dépenses <small>{{ n.lignes.length }}</small></h3>
            @if (n.lignes.length) {
              <div class="bea-nf-view__table">
                <table class="bea-mg__table">
                  <thead>
                    <tr><th>Date</th><th>Description</th><th>Motif</th><th>Règlement</th><th class="is-num">Montant</th></tr>
                  </thead>
                  <tbody>
                    @for (l of n.lignes; track $index) {
                      <tr>
                        <td class="is-nowrap">{{ l.date_depense | date: 'dd/MM/yyyy' }}</td>
                        <td>{{ l.description }}</td>
                        <td>{{ l.motif || '—' }}</td>
                        <td>{{ l.mode_reglement || '—' }}</td>
                        <td class="is-num">{{ l.montant | montant }}</td>
                      </tr>
                    }
                  </tbody>
                  <tfoot>
                    <tr><td colspan="4">Total</td><td class="is-num">{{ n.total_mru | montant }} MRU</td></tr>
                  </tfoot>
                </table>
              </div>
            } @else {
              <p class="bea-ct-view__none">Aucune dépense saisie.</p>
            }
          </section>

          <section class="bea-ct-view__section">
            <h3><mat-icon>timeline</mat-icon> Workflow <small>{{ n.historique.length }}</small></h3>
            @if (n.historique.length) {
              <ol class="bea-nf-view__timeline">
                @for (h of n.historique; track h.id) {
                  <li>
                    <span class="bea-nf-view__dot" [attr.data-tone]="tone(h.to_statut)"></span>
                    <div>
                      <strong>{{ h.to_statut ? label(h.to_statut) : h.action }}</strong>
                      <small>
                        {{ h.created_at | date: 'dd/MM/yyyy HH:mm' }}
                        @if (h.user_nom) { · {{ h.user_nom }} }
                      </small>
                      @if (h.commentaire) { <p>{{ h.commentaire }}</p> }
                    </div>
                  </li>
                }
              </ol>
            } @else {
              <p class="bea-ct-view__none">Aucun historique.</p>
            }
          </section>
        </div>

        <footer class="bea-ct-view__foot">
          <button
            type="button"
            class="bea-mg__btn bea-mg__btn--danger bea-nf-view__foot-left"
            [disabled]="!canDelete() || deleting()"
            [title]="deleteHint()"
            (click)="remove(n)"
          >
            <mat-icon>delete</mat-icon> {{ deleting() ? 'Suppression…' : 'Supprimer' }}
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="close()">Fermer</button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="downloading()" (click)="downloadPdf(n)">
            <mat-icon>picture_as_pdf</mat-icon> {{ downloading() ? 'Préparation…' : 'PDF' }}
          </button>
          @if (canPay()) {
            <a class="bea-mg__btn bea-mg__btn--ghost bea-pay-btn" [routerLink]="['/notes-frais/paiements']" [queryParams]="{ note: n.id }">
              <mat-icon>payments</mat-icon> Payer
            </a>
          }
          <a class="bea-mg__btn bea-mg__btn--primary" [routerLink]="['/notes-frais/notes', n.id]" [title]="editHint()">
            <mat-icon>{{ canEdit() ? 'edit' : 'open_in_new' }}</mat-icon>
            {{ canEdit() ? 'Modifier' : 'Ouvrir la fiche' }}
          </a>
        </footer>
      } @else if (loadError()) {
        <div class="bea-ct-view__loading">
          <mat-icon>error_outline</mat-icon> {{ loadError() }}
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="close()">Fermer</button>
        </div>
      } @else {
        <div class="bea-ct-view__loading"><span class="bea-ct-view__spinner"></span> Chargement de la note…</div>
      }
    </div>
  `,
})
export class NoteApercuComponent implements OnChanges {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);

  readonly noteId = input.required<string>();
  readonly closed = output<void>();
  readonly deleted = output<Note>();

  readonly note = signal<Note | null>(null);
  readonly loadError = signal('');
  readonly deleting = signal(false);
  readonly downloading = signal(false);

  readonly reste = computed(() => {
    const n = this.note();
    return n ? Math.max(0, Math.round((n.total_mru - (n.montant_paye || 0)) * 100) / 100) : 0;
  });
  readonly tauxPaye = computed(() => {
    const n = this.note();
    if (!n || !n.total_mru) return 0;
    return Math.min(100, Math.round(((n.montant_paye || 0) / n.total_mru) * 100));
  });
  readonly canEdit = computed(() => {
    const n = this.note();
    return !!n && canEditNote(this.auth.user(), n);
  });
  readonly canDelete = computed(() => {
    const n = this.note();
    return !!n && canDeleteNote(this.auth.user(), n);
  });
  readonly canPay = computed(() => {
    const n = this.note();
    return !!n && canPayNotes(this.auth.user()) && isNotePayable(n);
  });
  readonly editHint = computed(() => {
    const n = this.note();
    return n ? editNoteHint(this.auth.user(), n) : '';
  });
  readonly deleteHint = computed(() => {
    const n = this.note();
    return n ? deleteNoteHint(this.auth.user(), n) : '';
  });

  readonly label = noteStatutLabel;
  readonly tone = noteStatutTone;
  readonly payLabel = statutPaiementLabel;

  ngOnChanges(): void {
    this.note.set(null);
    this.loadError.set('');
    this.api.get<Note>(`/mg/notes-frais/notes/${this.noteId()}`).subscribe({
      next: (n) => this.note.set(n),
      error: (err) => this.loadError.set(formatNoteApiError(err, 'Note introuvable ou accès refusé')),
    });
  }

  @HostListener('document:keydown.escape')
  close(): void {
    if (this.deleting()) return;
    this.closed.emit();
  }

  remove(n: Note): void {
    this.feedback
      .run(() => this.api.delete<{ ok: boolean }>(`/mg/notes-frais/notes/${n.id}`), {
        confirm: {
          action: 'suppression',
          message: `Supprimer la note « ${n.reference} » ? Elle sera retirée du registre.`,
        },
        loading: 'Suppression…',
        errorTitle: 'Suppression refusée',
        busy: this.deleting,
        success: { title: 'Note supprimée', details: [{ label: 'Référence', value: n.reference }] },
      })
      .subscribe(() => this.deleted.emit(n));
  }

  downloadPdf(n: Note): void {
    if (this.downloading()) return;
    this.downloading.set(true);
    this.api
      .download(`/mg/notes-frais/notes/${n.id}/pdf`, {
        signataire_1: 'Signature Chef Sce Moyens Généraux',
        signataire_2: 'Signature Directrice des Ressources',
        orientation: 'paysage',
      })
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${n.reference}.pdf`;
          a.click();
          URL.revokeObjectURL(url);
          this.downloading.set(false);
        },
        error: (err) => {
          this.downloading.set(false);
          this.feedback.error({ title: 'Export PDF impossible', message: formatNoteApiError(err, '') || undefined });
        },
      });
  }
}
