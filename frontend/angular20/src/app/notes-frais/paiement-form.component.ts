import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  OnInit,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import {
  MODES_PAIEMENT,
  NotePaiement,
  NoteRegistre,
  formatNoteApiError,
  statutPaiementLabel,
  statutPaiementTone,
} from './notes-frais.shared';

const TODAY = () => new Date().toISOString().slice(0, 10);

/** Fiche de saisie d'un paiement : création (depuis un registre) ou modification. */
@Component({
  selector: 'bea-paiement-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, MontantPipe, DatePipe],
  template: `
    <div class="bea-mg__backdrop" (click)="close()"></div>
    <div class="bea-mg__modal bea-ct-view bea-pay-form" role="dialog" aria-modal="true" aria-labelledby="bea-pay-form-title">
      <header class="bea-ct-view__head">
        <div>
          <p class="bea-ct-view__kicker">
            <span class="bea-pay-steps">
              <span [class.is-on]="!registre()">1 · Registre</span>
              <mat-icon>chevron_right</mat-icon>
              <span [class.is-on]="!!registre()">2 · Paiement</span>
            </span>
          </p>
          <h2 id="bea-pay-form-title">{{ paiementId() ? 'Modifier le paiement ' + (edited()?.numero || '') : 'Nouveau paiement' }}</h2>
          <p class="bea-ct-view__sub">
            {{ registre() ? 'Les informations du registre sont reprises automatiquement.' : 'Sélectionnez la note de frais à payer.' }}
          </p>
        </div>
        <button type="button" class="bea-ct-view__close" title="Fermer" aria-label="Fermer" (click)="close()">
          <mat-icon>close</mat-icon>
        </button>
      </header>

      @if (loading()) {
        <div class="bea-ct-view__loading"><span class="bea-ct-view__spinner"></span> Chargement…</div>
      } @else if (!registre()) {
        <div class="bea-ct-view__body">
          <label class="bea-mg__field bea-pay-search">
            <mat-icon>search</mat-icon>
            <input
              #search
              [value]="q()"
              (input)="onSearch(search.value)"
              placeholder="Référence, bénéficiaire, motif…"
              autofocus
            />
          </label>
          <ul class="bea-pay-pick">
            @for (r of payables(); track r.id; let i = $index) {
              <li [style.animation-delay.ms]="i * 30">
                <button type="button" (click)="select(r)">
                  <span class="bea-pay-pick__main">
                    <code class="bea-mg__code">{{ r.reference }}</code>
                    <strong>{{ r.beneficiaire || '—' }}</strong>
                    <small>{{ r.motif || r.intitule || '—' }} · {{ r.date_demande | date: 'dd/MM/yyyy' }}</small>
                  </span>
                  <span class="bea-pay-pick__amount">
                    <small>Solde</small>
                    <strong>{{ r.solde | montant }} {{ r.devise }}</strong>
                    <span class="bea-nf-badge" [attr.data-tone]="payTone(r.statut_paiement)">{{ payLabel(r.statut_paiement) }}</span>
                  </span>
                  <mat-icon>chevron_right</mat-icon>
                </button>
              </li>
            } @empty {
              <li class="bea-pay-pick__empty">
                <mat-icon>task_alt</mat-icon>
                <p>{{ searching() ? 'Recherche…' : 'Aucune note en attente de paiement.' }}</p>
                <small>Seules les notes validées avec un solde restant apparaissent ici.</small>
              </li>
            }
          </ul>
        </div>
        <footer class="bea-ct-view__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="close()">Annuler</button>
        </footer>
      } @else {
        @if (registre(); as r) {
          <form class="bea-ct-view__body" [formGroup]="form" (ngSubmit)="submit()" id="bea-pay-form">
            <section class="bea-pay-registre">
              <div class="bea-pay-registre__head">
                <h3><mat-icon>receipt_long</mat-icon> Registre concerné</h3>
                @if (!paiementId() && !lockedNote()) {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-pay-change" (click)="registre.set(null)">
                    <mat-icon>swap_horiz</mat-icon> Changer
                  </button>
                }
              </div>
              <dl class="bea-ct-view__dl">
                <div><dt>Référence</dt><dd><code class="bea-mg__code">{{ r.reference }}</code></dd></div>
                <div><dt>Date</dt><dd>{{ r.date_demande | date: 'dd/MM/yyyy' }}</dd></div>
                <div><dt>Bénéficiaire</dt><dd>{{ r.beneficiaire || '—' }}</dd></div>
                <div><dt>Département / service</dt><dd>{{ r.departement || '—' }}</dd></div>
                <div class="bea-pay-registre__wide"><dt>Motif</dt><dd>{{ r.motif || r.intitule || '—' }}</dd></div>
              </dl>
              <div class="bea-ct-view__kpis bea-pay-kpis">
                <div><span>Montant initial</span><strong>{{ r.montant_initial | montant }}</strong></div>
                <div><span>Déjà payé</span><strong>{{ dejaPaye() | montant }}</strong></div>
                <div class="is-due"><span>Solde restant</span><strong>{{ disponible() | montant }}</strong></div>
              </div>
            </section>

            <section class="bea-ct-view__section">
              <h3><mat-icon>payments</mat-icon> Informations du paiement</h3>
              <div class="bea-mg__grid">
                <label>Date du paiement *
                  <input type="date" formControlName="date_paiement" [max]="today" />
                </label>
                <label>Montant payé ({{ r.devise }}) *
                  <span class="bea-pay-amount">
                    <input type="number" formControlName="montant" min="0.01" step="0.01" [max]="disponible()" />
                    <button type="button" class="bea-pay-amount__all" (click)="payerSolde()" title="Régler tout le solde">Solde</button>
                  </span>
                </label>
                <label class="bea-mg__span2">Mode de paiement *
                  <span class="bea-pay-modes" role="radiogroup">
                    @for (m of modes; track m) {
                      <button
                        type="button"
                        role="radio"
                        [attr.aria-checked]="mode() === m"
                        [class.is-on]="mode() === m"
                        (click)="setMode(m)"
                      >
                        <mat-icon>{{ modeIcon(m) }}</mat-icon> {{ m }}
                      </button>
                    }
                  </span>
                </label>

                @switch (mode()) {
                  @case ('Chèque') {
                    <label>Numéro de chèque *<input formControlName="numero_cheque" placeholder="Ex. 0012345" /></label>
                    <label>Banque<input formControlName="banque" placeholder="Banque émettrice" /></label>
                  }
                  @case ('Virement') {
                    <label>Référence du virement *<input formControlName="reference" placeholder="Ex. VIR-2026-0456" /></label>
                    <label>Banque<input formControlName="banque" placeholder="Banque utilisée" /></label>
                    <label class="bea-mg__span2">Compte débité<input formControlName="compte" placeholder="N° de compte / RIB" /></label>
                  }
                  @case ('Amanty') {
                    <label>Référence transaction Amanty *<input formControlName="reference" placeholder="Ex. 31004531" /></label>
                    <label>Numéro Amanty<input formControlName="compte" placeholder="Compte Amanty" /></label>
                  }
                  @case ('Carte') {
                    <label>N° de transaction<input formControlName="reference" placeholder="Autorisation / ticket" /></label>
                    <label>Banque<input formControlName="banque" placeholder="Banque de la carte" /></label>
                  }
                  @default {
                    <label class="bea-mg__span2">N° de reçu<input formControlName="reference" placeholder="Reçu de caisse (facultatif)" /></label>
                  }
                }

                <label class="bea-mg__span2">Observations
                  <textarea formControlName="observation" rows="2" placeholder="Informations complémentaires"></textarea>
                </label>

                @if (!paiementId()) {
                  <label class="bea-mg__span2">Pièce justificative
                    <span class="bea-pay-file">
                      <input type="file" (change)="onFile($event)" accept=".pdf,.png,.jpg,.jpeg,.webp" />
                      @if (fichier(); as f) {
                        <small><mat-icon>attach_file</mat-icon> {{ f.name }}</small>
                      } @else {
                        <small>PDF ou image — déposée dans la GED à l’enregistrement.</small>
                      }
                    </span>
                  </label>
                }
              </div>
            </section>

            <div class="bea-pay-apres" [attr.data-tone]="apres().tone">
              <mat-icon>{{ apres().icon }}</mat-icon>
              <span>
                Après ce paiement : <strong>{{ apres().label }}</strong>
                · solde restant <strong>{{ soldeApres() | montant }} {{ r.devise }}</strong>
              </span>
            </div>

            @if (erreur()) {
              <p class="bea-pay-error"><mat-icon>error_outline</mat-icon> {{ erreur() }}</p>
            }
          </form>
        }
        <footer class="bea-ct-view__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="close()">Annuler</button>
          <button type="submit" form="bea-pay-form" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()">
            <mat-icon>{{ paiementId() ? 'save' : 'check_circle' }}</mat-icon>
            {{ busy() ? 'Enregistrement…' : paiementId() ? 'Enregistrer les modifications' : 'Valider le paiement' }}
          </button>
        </footer>
      }
    </div>
  `,
})
export class PaiementFormComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  /** Registre présélectionné (bouton « Payer »). */
  readonly noteId = input<string | null>(null);
  /** Paiement à modifier. */
  readonly paiementId = input<string | null>(null);
  readonly saved = output<NotePaiement>();
  readonly closed = output<void>();

  readonly modes = MODES_PAIEMENT;
  readonly today = TODAY();
  readonly registre = signal<NoteRegistre | null>(null);
  readonly edited = signal<NotePaiement | null>(null);
  readonly payables = signal<NoteRegistre[]>([]);
  readonly q = signal('');
  readonly searching = signal(false);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly erreur = signal('');
  readonly fichier = signal<File | null>(null);
  readonly lockedNote = computed(() => !!this.noteId());
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  readonly form = this.fb.nonNullable.group({
    date_paiement: [TODAY(), Validators.required],
    montant: [0, [Validators.required, Validators.min(0.01)]],
    mode_paiement: ['Virement', Validators.required],
    reference: [''],
    numero_cheque: [''],
    banque: [''],
    compte: [''],
    observation: [''],
  });

  private readonly values = toSignal(this.form.valueChanges, { initialValue: this.form.getRawValue() });
  readonly mode = computed(() => this.values().mode_paiement ?? 'Virement');

  /** Solde disponible pour ce paiement (en modification : solde + montant actuel). */
  readonly disponible = computed(() => {
    const r = this.registre();
    if (!r) return 0;
    const p = this.edited();
    const extra = p && p.statut === 'VALIDE' ? Number(p.montant) : 0;
    return round(Number(r.solde) + extra);
  });
  readonly dejaPaye = computed(() => {
    const r = this.registre();
    return r ? round(Number(r.montant_initial) - this.disponible()) : 0;
  });
  readonly soldeApres = computed(() => Math.max(0, round(this.disponible() - (Number(this.values().montant) || 0))));
  readonly apres = computed(() => {
    const montant = Number(this.values().montant) || 0;
    if (montant > this.disponible() + 0.001) return { label: 'montant supérieur au solde', tone: 'danger', icon: 'block' };
    if (this.soldeApres() <= 0.001) return { label: 'Payé', tone: 'ok', icon: 'task_alt' };
    return { label: 'Partiellement payé', tone: 'warn', icon: 'hourglass_bottom' };
  });

  readonly payLabel = statutPaiementLabel;
  readonly payTone = statutPaiementTone;

  ngOnInit(): void {
    const pid = this.paiementId();
    const nid = this.noteId();
    if (pid) {
      this.loading.set(true);
      this.api.get<NotePaiement>(`/mg/notes-frais/paiements/${pid}`).subscribe({
        next: (p) => {
          this.edited.set(p);
          this.registre.set(p.registre);
          this.form.reset({
            date_paiement: p.date_paiement,
            montant: Number(p.montant),
            mode_paiement: p.mode_paiement,
            reference: p.reference ?? '',
            numero_cheque: p.numero_cheque ?? '',
            banque: p.banque ?? '',
            compte: p.compte ?? '',
            observation: p.observation ?? '',
          });
          this.loading.set(false);
        },
        error: (err) => this.fail(err, 'Paiement introuvable'),
      });
      return;
    }
    if (nid) {
      this.loading.set(true);
      this.api.get<NoteRegistre>(`/mg/notes-frais/paiements/registres/${nid}`).subscribe({
        next: (r) => {
          this.loading.set(false);
          if (Number(r.solde) <= 0) {
            this.feedback.info({ title: 'Rien à payer', message: `La note ${r.reference} est déjà totalement payée.` });
            this.closed.emit();
            return;
          }
          this.select(r);
        },
        error: (err) => this.fail(err, 'Registre introuvable'),
      });
      return;
    }
    this.loadPayables();
  }

  private fail(err: unknown, fallback: string): void {
    this.loading.set(false);
    this.feedback.error({ title: fallback, message: formatNoteApiError(err, '') || undefined });
    this.closed.emit();
  }

  onSearch(value: string): void {
    this.q.set(value);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.loadPayables(), 250);
  }

  loadPayables(): void {
    this.searching.set(true);
    const params: Record<string, string | number> = { limit: 50 };
    if (this.q().trim()) params['q'] = this.q().trim();
    this.api.get<{ items: NoteRegistre[] }>('/mg/notes-frais/paiements/registres', params).subscribe({
      next: (r) => {
        this.payables.set(r.items);
        this.searching.set(false);
      },
      error: () => {
        this.payables.set([]);
        this.searching.set(false);
      },
    });
  }

  select(r: NoteRegistre): void {
    this.registre.set(r);
    this.erreur.set('');
    this.form.reset({
      date_paiement: TODAY(),
      montant: Number(r.solde),
      mode_paiement: 'Virement',
      reference: '',
      numero_cheque: '',
      banque: '',
      compte: '',
      observation: '',
    });
  }

  setMode(m: string): void {
    this.form.patchValue({ mode_paiement: m });
    this.form.markAsDirty();
  }

  payerSolde(): void {
    this.form.patchValue({ montant: this.disponible() });
  }

  modeIcon(m: string): string {
    switch (m) {
      case 'Espèces':
        return 'payments';
      case 'Virement':
        return 'account_balance';
      case 'Chèque':
        return 'edit_note';
      case 'Carte':
        return 'credit_card';
      default:
        return 'smartphone';
    }
  }

  onFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    this.fichier.set(input.files?.[0] ?? null);
  }

  private validate(): string | null {
    const v = this.form.getRawValue();
    const montant = Number(v.montant);
    if (!v.date_paiement) return 'Indiquez la date du paiement.';
    if (!(montant > 0)) return 'Le montant doit être supérieur à 0.';
    if (montant > this.disponible() + 0.001) return 'Le montant dépasse le solde restant à payer.';
    if (v.mode_paiement === 'Chèque' && !v.numero_cheque.trim()) return 'Indiquez le numéro de chèque.';
    if (v.mode_paiement === 'Virement' && !v.reference.trim()) return 'Indiquez la référence du virement.';
    if (v.mode_paiement === 'Amanty' && !v.reference.trim()) return 'Indiquez la référence de la transaction Amanty.';
    return null;
  }

  /** Seuls les champs pertinents pour le mode choisi sont envoyés. */
  private body() {
    const v = this.form.getRawValue();
    const keep = (k: 'reference' | 'numero_cheque' | 'banque' | 'compte'): string | null => {
      const relevant: Record<string, string[]> = {
        Espèces: ['reference'],
        Virement: ['reference', 'banque', 'compte'],
        Chèque: ['numero_cheque', 'banque'],
        Carte: ['reference', 'banque'],
        Amanty: ['reference', 'compte'],
      };
      return relevant[v.mode_paiement]?.includes(k) ? v[k].trim() || null : null;
    };
    return {
      date_paiement: v.date_paiement,
      montant: round(Number(v.montant)),
      mode_paiement: v.mode_paiement,
      reference: keep('reference'),
      numero_cheque: keep('numero_cheque'),
      banque: keep('banque'),
      compte: keep('compte'),
      observation: v.observation.trim() || null,
    };
  }

  submit(): void {
    const r = this.registre();
    if (!r || this.busy()) return;
    const refus = this.validate();
    this.erreur.set(refus ?? '');
    if (refus) return;

    const pid = this.paiementId();
    const body = this.body();
    const req = pid
      ? () => this.api.patch<NotePaiement>(`/mg/notes-frais/paiements/${pid}`, body)
      : () => this.api.post<NotePaiement>('/mg/notes-frais/paiements', { ...body, note_id: r.id });
    this.feedback
      .run(req, {
        loading: pid ? 'Enregistrement des modifications…' : 'Enregistrement du paiement…',
        errorTitle: pid ? 'Modification refusée' : 'Paiement refusé',
        busy: this.busy,
        idempotent: !pid,
        onError: (e) => this.erreur.set(e.message),
        success: (p) => ({
          title: pid ? 'Paiement modifié' : 'Paiement enregistré',
          details: [
            { label: 'N° paiement', value: p.numero },
            { label: 'Registre', value: p.registre.reference },
            { label: 'Statut', value: statutPaiementLabel(p.registre.statut_paiement) },
          ],
        }),
      })
      .subscribe((p) => {
        const file = this.fichier();
        if (!pid && file) this.uploadJustificatif(p, file);
        this.form.markAsPristine();
        this.saved.emit(p);
      });
  }

  private uploadJustificatif(p: NotePaiement, file: File): void {
    this.api
      .upload('/documents/from-operation', file, {
        espace_code: 'moyens-generaux',
        module_code: 'notes-frais',
        source_type: 'note_frais_paiement',
        source_id: p.id,
        doc_type: 'JUSTIFICATIF',
        title: file.name,
        reference: p.numero,
      })
      .subscribe({
        error: () =>
          this.feedback.warning({
            title: 'Justificatif non déposé',
            message: `Le paiement ${p.numero} est enregistré ; ajoutez la pièce depuis son détail.`,
          }),
      });
  }

  @HostListener('document:keydown.escape')
  close(): void {
    if (this.busy()) return;
    if (!this.form.dirty || !this.registre()) {
      this.closed.emit();
      return;
    }
    this.dialogs
      .confirmAction('depart', 'Les informations saisies pour ce paiement seront perdues.')
      .subscribe((ok) => {
        if (ok) this.closed.emit();
      });
  }
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}
