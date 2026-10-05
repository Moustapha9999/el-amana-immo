import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { formatMontant, parseMontant } from '../../shared/montant.pipe';
import { DetailDrawerComponent, DetailTimelineComponent, DrawerKpi, TimelineItem } from '../shared/detail-drawer.component';
import { ACTION_LABELS, FactureDetail, FxDocument, FxPaiement, aujourdhui, dateFr, dateHeureFr, fxStatut, fxTone, telechargerBlob } from './facturation.models';
import { FacturationStore } from './facturation.store';

/** Mini-page paiement de facture : montant facture, déjà payé, ce paiement, reste après ; justificatif ; historique. */
@Component({
  selector: 'bea-fx-paiement-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, DetailDrawerComponent, DetailTimelineComponent],
  template: `
    <bea-detail-drawer
      kicker="Paiement de facture"
      [titre]="p() ? p()!.reference : null"
      [sousTitre]="f() ? f()!.reference + (f()!.point_nom ? ' · ' + f()!.point_nom : '') + (f()!.fournisseur ? ' · ' + f()!.fournisseur : '') : null"
      [chargement]="chargement()"
      [erreur]="erreur()"
      [kpis]="kpis()"
      [onglets]="[{ key: 'detail', label: 'Détail' }, { key: 'justificatif', label: 'Justificatif' }, { key: 'historique', label: 'Historique' }]"
      [(onglet)]="onglet"
      (fermer)="fermer.emit()"
      (reessayer)="charger()"
    >
      @if (p(); as p) { <span drawerBadges class="bea-ct-badge" [attr.data-tone]="tone(p.statut)">{{ statut(p.statut) }}</span> }
      @if (p(); as p) {
        <ng-container drawerActions>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirFacture.emit(factureId())"><mat-icon>receipt_long</mat-icon> Ouvrir la facture</button>
          @if (modifiable()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="ouvrirEdition()"><mat-icon>edit</mat-icon> Modifier</button>
          }
          @if (p.statut !== 'ANNULE' && store.cap().payment_delete) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-mg__btn--danger" [disabled]="busy()" (click)="annuler(p)"><mat-icon>undo</mat-icon> Annuler le paiement</button>
          }
        </ng-container>
      }
      @if (p(); as p) {
        @switch (onglet()) {
          @case ('detail') {
            <div class="bea-pay-recap">
              <div><span>Montant facture</span><strong>{{ m(f()?.montant_a_payer) }}</strong></div>
              <div><span>Déjà payé avant</span><strong>{{ m(dejaPaye()) }}</strong></div>
              <div><span>Ce paiement</span><strong>{{ m(p.montant) }}</strong></div>
              <div [attr.data-tone]="resteApres() === 0 ? 'ok' : null"><span>Reste après</span><strong>{{ m(resteApres()) }}</strong></div>
            </div>
            <dl class="bea-fx-dl">
              <dt>Date de paiement</dt><dd>{{ date(p.date_paiement) }}</dd>
              <dt>Mode</dt><dd>{{ p.mode_paiement || '—' }}</dd>
              <dt>Réf. bancaire</dt><dd>{{ p.reference_paiement || '—' }}</dd>
              <dt>Saisi par</dt><dd>{{ p.created_by || '—' }}@if (p.created_at) { <small> {{ dateHeure(p.created_at) }}</small> }</dd>
              @if (p.annule_at) { <dt>Annulé le</dt><dd>{{ dateHeure(p.annule_at) }}</dd> }
              @if (p.observation) { <dt>Observation</dt><dd class="bea-fx-dl__wrap">{{ p.observation }}</dd> }
              <dt>Reste actuel de la facture</dt><dd>{{ m(f()?.reste) }} {{ f()?.devise }}</dd>
            </dl>
          }
          @case ('justificatif') {
            @if (justificatif(); as d) {
              <ul class="bea-ct-dash__list">
                <li><span class="bea-ct-dash__main"><mat-icon>description</mat-icon> {{ d.title || d.filename }}</span>
                  <button type="button" class="bea-mg__icon-btn" title="Télécharger" (click)="telecharger(d)"><mat-icon>download</mat-icon></button></li>
              </ul>
            } @else {
              <div class="bea-ct-empty"><mat-icon>attach_file</mat-icon><p>Aucun justificatif rattaché à ce paiement.</p>
                <small>Ajoutez la pièce dans l’onglet Documents de la facture puis rattachez-la au paiement.</small></div>
            }
          }
          @case ('historique') {
            <bea-detail-timeline [items]="historique()" vide="Aucun événement de paiement sur cette facture." />
          }
        }
      }
    </bea-detail-drawer>

    @if (edition() && p() && f(); as f) {
      <div class="bea-mg__backdrop bea-fx-over" (click)="fermerEdition()"></div>
      <form class="bea-mg__modal bea-ct-modal bea-fx-over" role="dialog" aria-modal="true" aria-labelledby="bea-fx-payedit-title" [formGroup]="form" (ngSubmit)="enregistrer()">
        <header class="bea-ct-modal__head">
          <h2 id="bea-fx-payedit-title"><mat-icon>edit</mat-icon> Modifier {{ p()!.reference }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermerEdition()"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-ct-grid bea-ct-modal__body">
          <div class="bea-ct-span2 bea-pay-recap">
            <div><span>Montant facture</span><strong>{{ m(f.montant_a_payer) }}</strong></div>
            <div><span>Autres paiements</span><strong>{{ m(autresPaiements()) }}</strong></div>
            <div><span>Ce paiement</span><strong>{{ m(saisi()) }}</strong></div>
            <div [attr.data-tone]="resteEdition() < 0 ? 'danger' : resteEdition() === 0 ? 'ok' : null"><span>Reste après</span><strong>{{ m(resteEdition()) }}</strong></div>
          </div>
          @if (resteEdition() < 0) { <p class="bea-ct-span2 bea-ct-help bea-ct-neg"><mat-icon>error</mat-icon> Le montant dépasse le reste à payer de la facture.</p> }
          <label>Date de paiement * <input type="date" formControlName="date_paiement" [max]="today" /></label>
          <label>Montant * <input inputmode="decimal" formControlName="montant" /></label>
          <label>Mode
            <select formControlName="mode_paiement">
              <option value="">—</option>
              @for (mo of store.config()?.modes_paiement ?? []; track mo) { <option [value]="mo">{{ mo }}</option> }
            </select>
          </label>
          <label>Référence (OV, chèque…) <input formControlName="reference_paiement" maxlength="120" /></label>
          <label class="bea-ct-span2">Justificatif (document de la facture)
            <select formControlName="justificatif_document_id">
              <option value="">— Aucun —</option>
              @for (d of f.documents; track d.id) { <option [value]="d.id">{{ d.title }} ({{ d.doc_type_label }})</option> }
            </select>
          </label>
          <label class="bea-ct-span2">Observation <input formControlName="observation" maxlength="2000" /></label>
        </div>
        <footer class="bea-ct-modal__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerEdition()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || busy() || resteEdition() < 0"><mat-icon>save</mat-icon> {{ busy() ? 'Enregistrement…' : 'Enregistrer' }}</button>
        </footer>
      </form>
    }
  `,
})
export class FxPaiementDrawerComponent {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);

  readonly factureId = input.required<string>();
  readonly paiementId = input.required<string>();
  readonly editionInitiale = input(false);
  readonly ongletInitial = input('detail');
  readonly fermer = output<void>();
  readonly modifie = output<void>();
  readonly ouvrirFacture = output<string>();

  readonly onglet = signal('detail');
  readonly f = signal<FactureDetail | null>(null);
  readonly chargement = signal(true);
  readonly erreur = signal<string | null>(null);
  readonly busy = signal(false);
  readonly edition = signal(false);
  readonly today = aujourdhui();
  private editionEnAttente = false;

  readonly form = this.fb.nonNullable.group({
    date_paiement: ['', Validators.required],
    montant: ['', Validators.required],
    mode_paiement: [''],
    reference_paiement: [''],
    justificatif_document_id: [''],
    observation: [''],
  });
  private readonly montantSaisi = toSignal(this.form.controls.montant.valueChanges, { initialValue: '' });
  readonly isDirty = unsavedChanges(() => this.edition() && this.form.dirty, () => this.form);

  readonly modifiable = computed(() => this.p()?.statut === 'PAYE' && this.f()?.statut === 'VALIDEE' && !!this.store.cap().payment_update);
  readonly saisi = computed(() => parseMontant(this.montantSaisi() ?? '') ?? 0);
  readonly autresPaiements = computed(() =>
    (this.f()?.paiements ?? []).filter((x) => x.statut === 'PAYE' && x.id !== this.paiementId()).reduce((s, x) => s + x.montant, 0),
  );
  readonly resteEdition = computed(() => Math.round(((this.f()?.montant_a_payer ?? 0) - this.autresPaiements() - this.saisi()) * 100) / 100);

  readonly p = computed<FxPaiement | null>(() => this.f()?.paiements.find((x) => x.id === this.paiementId()) ?? null);
  readonly dejaPaye = computed(() => {
    const p = this.p();
    const f = this.f();
    if (!p || !f) return 0;
    const cle = (x: FxPaiement) => `${x.date_paiement ?? ''}|${x.created_at ?? ''}`;
    return f.paiements.filter((x) => x.statut === 'PAYE' && x.id !== p.id && cle(x) < cle(p)).reduce((s, x) => s + x.montant, 0);
  });
  readonly resteApres = computed(() => {
    const p = this.p();
    const total = this.f()?.montant_a_payer ?? 0;
    if (!p) return 0;
    const apres = total - this.dejaPaye() - (p.statut === 'PAYE' ? p.montant : 0);
    return Math.max(Math.round(apres * 100) / 100, 0);
  });
  readonly justificatif = computed<FxDocument | null>(() => {
    const id = this.p()?.justificatif_document_id;
    return id ? this.f()?.documents.find((d) => d.id === id) ?? null : null;
  });
  readonly historique = computed<TimelineItem[]>(() =>
    (this.f()?.historique ?? [])
      .filter((h) => h.action.toUpperCase().includes('PAIEMENT'))
      .map((h) => ({ titre: ACTION_LABELS[h.action]?.label ?? h.action, date: h.created_at ? dateHeureFr(h.created_at) : '', auteur: h.user_nom, detail: h.message })),
  );
  readonly kpis = computed<DrawerKpi[]>(() => {
    const p = this.p();
    const f = this.f();
    if (!p || !f) return [];
    return [
      { label: 'Ce paiement', value: formatMontant(p.montant), hint: f.devise, tone: p.statut === 'PAYE' ? 'ok' : null },
      { label: 'Facture', value: formatMontant(f.montant_a_payer ?? 0), hint: f.periode_label },
      { label: 'Payé (total)', value: formatMontant(f.montant_paye ?? 0), hint: f.devise },
      { label: 'Reste facture', value: formatMontant(f.reste ?? 0), hint: f.devise, tone: f.reste ? 'warn' : 'ok' },
    ];
  });

  constructor() {
    this.store.charger();
    effect(() => {
      this.factureId();
      this.paiementId();
      const edition = this.editionInitiale();
      const onglet = this.ongletInitial();
      untracked(() => {
        this.onglet.set(onglet);
        this.editionEnAttente = edition;
        this.charger();
      });
    });
  }

  charger(): void {
    this.chargement.set(!this.f());
    this.erreur.set(null);
    this.api.get<FactureDetail>(`/mg/factures/${this.factureId()}`).subscribe({
      next: (f) => {
        this.f.set(f);
        this.chargement.set(false);
        if (!this.p()) this.erreur.set('Paiement introuvable sur cette facture.');
        if (this.editionEnAttente) {
          this.editionEnAttente = false;
          if (this.modifiable()) this.ouvrirEdition();
          else if (this.p()) this.feedback.warning({ title: 'Modification impossible', message: 'Seul un paiement valide sur une facture validée peut être modifié.' });
        }
      },
      error: (e: { status?: number }) => {
        this.chargement.set(false);
        this.erreur.set(e?.status === 403 ? 'Accès refusé.' : e?.status === 404 ? 'Facture introuvable.' : 'Le serveur n’a pas répondu correctement.');
      },
    });
  }

  annuler(p: FxPaiement): void {
    this.feedback
      .runWithReason((motif) => this.api.post(`/mg/factures/paiements/${p.id}/annuler`, { motif }), {
        reason: {
          title: `Annuler le paiement ${p.reference}`,
          message: 'Le paiement est conservé dans l’historique avec le statut « Annulé » ; la facture repasse en reste à payer.',
          reasonLabel: 'Motif de l’annulation',
          required: true,
          tone: 'danger',
          confirmLabel: 'Annuler le paiement',
        },
        loading: 'Annulation…',
        busy: this.busy,
        errorTitle: 'Annulation impossible',
        success: { title: 'Paiement annulé', message: p.reference },
      })
      .subscribe(() => {
        this.modifie.emit();
        this.charger();
      });
  }

  ouvrirEdition(): void {
    const p = this.p();
    if (!p) return;
    this.form.reset({
      date_paiement: p.date_paiement ?? this.today,
      montant: String(p.montant),
      mode_paiement: p.mode_paiement ?? '',
      reference_paiement: p.reference_paiement ?? '',
      justificatif_document_id: p.justificatif_document_id ?? '',
      observation: p.observation ?? '',
    });
    this.edition.set(true);
  }

  fermerEdition(): void {
    if (this.busy()) return;
    this.edition.set(false);
    this.form.markAsPristine();
  }

  enregistrer(): void {
    const p = this.p();
    if (!p || this.form.invalid) return;
    const v = this.form.getRawValue();
    const montant = parseMontant(v.montant);
    if (!montant || montant <= 0) {
      this.feedback.warning({ title: 'Montant invalide', message: 'Saisissez un montant positif.' });
      return;
    }
    const body = {
      date_paiement: v.date_paiement,
      montant,
      mode_paiement: v.mode_paiement || null,
      reference_paiement: v.reference_paiement.trim() || null,
      justificatif_document_id: v.justificatif_document_id || null,
      observation: v.observation.trim() || null,
    };
    this.feedback
      .run(() => this.api.patch<FactureDetail>(`/mg/factures/paiements/${p.id}`, body), {
        loading: 'Enregistrement…',
        busy: this.busy,
        errorTitle: 'Modification refusée',
        errorHint: 'Vos saisies ont été conservées.',
        success: (d) => ({
          title: 'Paiement modifié',
          details: [
            { label: 'Montant', value: `${formatMontant(montant)} ${d.devise}` },
            { label: 'Reste facture', value: `${formatMontant(d.reste ?? 0)} ${d.devise}` },
          ],
        }),
      })
      .subscribe((d) => {
        this.form.markAsPristine();
        this.edition.set(false);
        this.f.set(d);
        this.modifie.emit();
      });
  }

  telecharger(d: FxDocument): void {
    this.api.download(`/mg/factures/${this.factureId()}/documents/${d.id}/download`).subscribe({
      next: (blob) => telechargerBlob(blob, d.filename),
      error: () => this.feedback.warning({ title: 'Téléchargement impossible', message: 'Le document n’est pas accessible.' }),
    });
  }

  statut(c: string): string {
    return fxStatut(c);
  }
  tone(c: string): string {
    return fxTone(c);
  }
  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }
  dateHeure(iso: string): string {
    return dateHeureFr(iso);
  }
  m(v: number | null | undefined): string {
    return v === null || v === undefined ? '—' : formatMontant(v);
  }
}
