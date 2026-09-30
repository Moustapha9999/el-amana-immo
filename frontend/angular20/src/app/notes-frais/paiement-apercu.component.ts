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
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { MontantPipe } from '../shared/montant.pipe';
import {
  NotePaiement,
  canDeletePaiement,
  canEditPaiement,
  formatNoteApiError,
  noteStatutLabel,
  paiementLockHint,
  paiementReference,
  paiementStatutLabel,
  paiementStatutTone,
  statutPaiementLabel,
  statutPaiementTone,
} from './notes-frais.shared';

/** Détail d'un paiement et de son registre concerné. */
@Component({
  selector: 'bea-paiement-apercu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, DatePipe, MontantPipe, MgGedPanelComponent],
  template: `
    <div class="bea-mg__backdrop" (click)="close()"></div>
    <div class="bea-mg__modal bea-ct-view bea-nf-view" role="dialog" aria-modal="true" aria-labelledby="bea-pay-view-title">
      @if (paiement(); as p) {
        <header class="bea-ct-view__head">
          <div>
            <p class="bea-ct-view__kicker">
              <code class="bea-mg__code">{{ p.numero }}</code>
              <span class="bea-nf-badge" [attr.data-tone]="payTone(p.statut)">{{ payLabel(p.statut) }}</span>
            </p>
            <h2 id="bea-pay-view-title">{{ p.montant | montant }} {{ p.registre.devise }} · {{ p.mode_paiement }}</h2>
            <p class="bea-ct-view__sub">
              Payé le {{ p.date_paiement | date: 'dd/MM/yyyy' }} à {{ p.registre.beneficiaire || '—' }}
            </p>
          </div>
          <button type="button" class="bea-ct-view__close" title="Fermer" aria-label="Fermer" (click)="close()">
            <mat-icon>close</mat-icon>
          </button>
        </header>

        <div class="bea-ct-view__body">
          @if (p.statut === 'ANNULE') {
            <p class="bea-nf-view__alert">
              <mat-icon>block</mat-icon>
              <span>
                <strong>Annulé</strong>
                le {{ p.annule_at | date: 'dd/MM/yyyy HH:mm' }}
                @if (p.annule_par_nom) { par {{ p.annule_par_nom }} }
                @if (p.motif_annulation) { — {{ p.motif_annulation }} }
              </span>
            </p>
          }

          <section class="bea-ct-view__section">
            <h3><mat-icon>payments</mat-icon> Informations du paiement</h3>
            <dl class="bea-ct-view__dl">
              <div><dt>N° paiement</dt><dd>{{ p.numero }}</dd></div>
              <div><dt>Date</dt><dd>{{ p.date_paiement | date: 'dd/MM/yyyy' }}</dd></div>
              <div><dt>Montant</dt><dd>{{ p.montant | montant }} {{ p.registre.devise }}</dd></div>
              <div><dt>Mode de paiement</dt><dd>{{ p.mode_paiement }}</dd></div>
              <div><dt>Référence</dt><dd>{{ reference(p) }}</dd></div>
              @if (p.banque) { <div><dt>Banque</dt><dd>{{ p.banque }}</dd></div> }
              @if (p.compte) { <div><dt>{{ p.mode_paiement === 'Amanty' ? 'Numéro Amanty' : 'Compte' }}</dt><dd>{{ p.compte }}</dd></div> }
              <div><dt>Bénéficiaire</dt><dd>{{ p.registre.beneficiaire || '—' }}</dd></div>
              <div><dt>Saisi par</dt><dd>{{ p.created_by_nom || '—' }} · {{ p.created_at | date: 'dd/MM/yyyy HH:mm' }}</dd></div>
              @if (p.updated_by_nom) {
                <div><dt>Modifié par</dt><dd>{{ p.updated_by_nom }} · {{ p.updated_at | date: 'dd/MM/yyyy HH:mm' }}</dd></div>
              }
            </dl>
            @if (p.observation) { <p class="bea-ct-view__text bea-pay-obs">{{ p.observation }}</p> }
          </section>

          <section class="bea-ct-view__section bea-pay-registre">
            <div class="bea-pay-registre__head">
              <h3><mat-icon>receipt_long</mat-icon> Registre concerné</h3>
              <span class="bea-nf-badge" [attr.data-tone]="regTone(p.registre.statut_paiement)">{{ regLabel(p.registre.statut_paiement) }}</span>
            </div>
            <dl class="bea-ct-view__dl">
              <div><dt>Référence</dt><dd><code class="bea-mg__code">{{ p.registre.reference }}</code></dd></div>
              <div><dt>Date</dt><dd>{{ p.registre.date_demande | date: 'dd/MM/yyyy' }}</dd></div>
              <div><dt>Bénéficiaire</dt><dd>{{ p.registre.beneficiaire || '—' }}</dd></div>
              <div><dt>Motif</dt><dd>{{ p.registre.motif || p.registre.intitule || '—' }}</dd></div>
              <div><dt>Statut de la note</dt><dd>{{ noteLabel(p.registre.statut) }}</dd></div>
              <div><dt>Paiements valides</dt><dd>{{ p.registre.nb_paiements }}</dd></div>
            </dl>
            <div class="bea-ct-view__kpis bea-pay-kpis">
              <div><span>Montant initial</span><strong>{{ p.registre.montant_initial | montant }}</strong></div>
              <div><span>Total payé</span><strong>{{ p.registre.montant_paye | montant }}</strong></div>
              <div [class.is-due]="p.registre.solde > 0"><span>Solde restant</span><strong>{{ p.registre.solde | montant }}</strong></div>
            </div>
            <div class="bea-nf-view__progress" aria-hidden="true"><i [style.width.%]="taux()"></i></div>
          </section>

          <section class="bea-ct-view__section">
            <h3><mat-icon>attach_file</mat-icon> Pièce justificative</h3>
            <bea-mg-ged
              moduleCode="notes-frais"
              entity="note_frais_paiement"
              [entityId]="p.id"
              [reference]="p.numero"
              [lectureSeule]="!canEdit()"
            />
          </section>
        </div>

        <footer class="bea-ct-view__foot">
          @if (canDelete()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--danger bea-nf-view__foot-left" [disabled]="busy()" (click)="remove(p)">
              <mat-icon>delete</mat-icon> Supprimer
            </button>
          }
          <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/notes-frais/notes', p.note_id]">
            <mat-icon>receipt_long</mat-icon> Voir le registre
          </a>
          @if (canEdit()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="cancel(p)">
              <mat-icon>block</mat-icon> Annuler le paiement
            </button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="edit.emit(p)">
              <mat-icon>edit</mat-icon> Modifier
            </button>
          } @else if (lockHint()) {
            <span class="bea-pay-lock"><mat-icon>lock</mat-icon> {{ lockHint() }}</span>
          }
        </footer>
      } @else {
        <div class="bea-ct-view__loading"><span class="bea-ct-view__spinner"></span> Chargement du paiement…</div>
      }
    </div>
  `,
})
export class PaiementApercuComponent implements OnChanges {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);

  readonly paiementId = input.required<string>();
  readonly closed = output<void>();
  readonly changed = output<void>();
  readonly edit = output<NotePaiement>();

  readonly paiement = signal<NotePaiement | null>(null);
  readonly busy = signal(false);

  readonly canEdit = computed(() => {
    const p = this.paiement();
    return !!p && canEditPaiement(this.auth.user(), p);
  });
  readonly canDelete = computed(() => {
    const p = this.paiement();
    return !!p && canDeletePaiement(this.auth.user(), p);
  });
  readonly lockHint = computed(() => {
    const p = this.paiement();
    return p ? paiementLockHint(p) : null;
  });
  readonly taux = computed(() => {
    const r = this.paiement()?.registre;
    if (!r || !Number(r.montant_initial)) return 0;
    return Math.min(100, Math.round((Number(r.montant_paye) / Number(r.montant_initial)) * 100));
  });

  readonly reference = paiementReference;
  readonly payLabel = paiementStatutLabel;
  readonly payTone = paiementStatutTone;
  readonly regLabel = statutPaiementLabel;
  readonly regTone = statutPaiementTone;
  readonly noteLabel = noteStatutLabel;

  ngOnChanges(): void {
    this.load();
  }

  load(): void {
    this.api.get<NotePaiement>(`/mg/notes-frais/paiements/${this.paiementId()}`).subscribe({
      next: (p) => this.paiement.set(p),
      error: (err) => {
        this.feedback.error({ title: 'Paiement introuvable', message: formatNoteApiError(err, '') || undefined });
        this.closed.emit();
      },
    });
  }

  cancel(p: NotePaiement): void {
    this.feedback
      .runWithReason(
        (motif) => this.api.post<NotePaiement>(`/mg/notes-frais/paiements/${p.id}/annuler`, { motif }),
        {
          reason: {
            title: 'Annuler le paiement',
            message: `Le paiement ${p.numero} (${p.montant} ${p.registre.devise}) sera annulé et le solde de ${p.registre.reference} recalculé.`,
            confirmLabel: 'Annuler le paiement',
            cancelLabel: 'Retour',
            tone: 'danger',
            icon: 'block',
            reasonLabel: 'Motif de l’annulation',
          },
          loading: 'Annulation…',
          errorTitle: 'Annulation refusée',
          busy: this.busy,
          success: (res) => ({
            title: 'Paiement annulé',
            details: [
              { label: 'N° paiement', value: res.numero },
              { label: 'Solde du registre', value: `${res.registre.solde} ${res.registre.devise}` },
            ],
          }),
        },
      )
      .subscribe((res) => {
        this.paiement.set(res);
        this.changed.emit();
      });
  }

  remove(p: NotePaiement): void {
    this.feedback
      .run(() => this.api.delete<{ ok: boolean }>(`/mg/notes-frais/paiements/${p.id}`), {
        confirm: {
          action: 'suppression',
          message: `Supprimer le paiement ${p.numero} ? Le solde de ${p.registre.reference} sera recalculé.`,
          hint: 'La suppression est tracée dans l’audit. Préférez l’annulation en exploitation.',
        },
        loading: 'Suppression…',
        errorTitle: 'Suppression refusée',
        busy: this.busy,
        success: { title: 'Paiement supprimé', details: [{ label: 'N° paiement', value: p.numero }] },
      })
      .subscribe(() => {
        this.changed.emit();
        this.closed.emit();
      });
  }

  @HostListener('document:keydown.escape')
  close(): void {
    if (this.busy()) return;
    this.closed.emit();
  }
}
