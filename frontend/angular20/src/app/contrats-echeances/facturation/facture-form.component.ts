import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiErrorInfo } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { UiDialogService } from '../../shared/ui-dialog/ui-dialog.service';
import { MontantPipe, parseMontant } from '../../shared/montant.pipe';
import { FactureDetail, MOIS, TYPE_POINT_LABELS, aujourdhui } from './facturation.models';
import { FacturationStore } from './facturation.store';

type Num = number | null;

/** Modale création / modification d'une facture. Aucun montant n'est déduit hors saisie. */
@Component({
  selector: 'bea-fx-facture-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, MontantPipe],
  template: `
    <div class="bea-mg__backdrop" (click)="fermer()"></div>
    <form class="bea-mg__modal bea-mg__modal--lg bea-ct-modal bea-fx-form" role="dialog" aria-modal="true" aria-labelledby="bea-fx-form-title"
      [formGroup]="form" (ngSubmit)="enregistrer(true)">
      <header class="bea-ct-modal__head">
        <h2 id="bea-fx-form-title"><mat-icon>{{ facture() ? 'edit_note' : 'post_add' }}</mat-icon>
          {{ facture() ? 'Modifier la facture ' + facture()!.reference : 'Nouvelle facture' }}</h2>
        <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
      </header>

      <div class="bea-ct-modal__body bea-fx-form__body">
        @if (verrouMontants()) {
          <p class="bea-ct-help"><mat-icon>lock</mat-icon> Facture validée : seuls la réception, l'échéance et l'observation restent modifiables. Contestez-la pour corriger les montants.</p>
        }
        <fieldset class="bea-fx-form__set">
          <legend>Rattachement</legend>
          <div class="bea-ct-grid">
            <label class="bea-ct-span2">Point de facturation
              <select formControlName="point_facturation_id" (change)="onPoint()">
                <option value="">— Aucun (facture ponctuelle) —</option>
                @for (p of pointsFiltres(); track p.id) {
                  <option [value]="p.id">{{ p.code }} · {{ p.nom }} — {{ typePoint(p.type_point) }} · réf. {{ p.reference_fournisseur }}{{ p.statut !== 'ACTIF' ? ' (inactif)' : '' }}</option>
                }
              </select>
            </label>
            <label>Fournisseur *
              <select formControlName="fournisseur_id" (change)="onFournisseur()">
                <option value="">— Sélectionner —</option>
                @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
              </select>
            </label>
            <label>Agence
              <select formControlName="agence_id">
                <option value="">— Aucune / siège —</option>
                @for (a of store.ref()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
              </select>
            </label>
            <label>Type de facture
              <select formControlName="type_facture">
                <option value="">—</option>
                @for (t of store.config()?.types_facture ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            <label>Contrat
              <select formControlName="contrat_id">
                <option value="">— Aucun —</option>
                @for (c of contratsFiltres(); track c.id) { <option [value]="c.id">{{ c.reference }} — {{ c.titre }}</option> }
              </select>
            </label>
            <label>Réf. fournisseur (compteur / abonnement)
              <input formControlName="reference_fournisseur" maxlength="80" placeholder="Reprise du point si vide" />
            </label>
          </div>
        </fieldset>

        <fieldset class="bea-fx-form__set">
          <legend>Facture</legend>
          <div class="bea-ct-grid">
            <label>N° facture fournisseur <input formControlName="numero_fournisseur" maxlength="80" /></label>
            <label>Date de facture * <input type="date" formControlName="date_facture" /></label>
            <label>Date de réception <input type="date" formControlName="date_reception" /></label>
            <label>Échéance <input type="date" formControlName="date_echeance" /></label>
            <label>Début de période <input type="date" formControlName="periode_debut" /></label>
            <label>Fin de période <input type="date" formControlName="periode_fin" /></label>
            <label>Mois facturé
              <select formControlName="mois">
                <option [ngValue]="null">Auto ({{ periodeAuto() }})</option>
                @for (m of mois; track $index) { <option [ngValue]="$index + 1">{{ m }}</option> }
              </select>
            </label>
            <label>Année <input type="number" min="2000" max="2100" formControlName="annee" placeholder="Auto" /></label>
          </div>
        </fieldset>

        <fieldset class="bea-fx-form__set">
          <legend>Montants <small>(facultatifs — saisir uniquement ce qui figure sur la facture)</small></legend>
          <div class="bea-ct-grid bea-fx-form__montants">
            <label>Montant HT <input inputmode="decimal" formControlName="montant_ht" (input)="recalculer()" /></label>
            <label>TVA <input inputmode="decimal" formControlName="montant_tva" (input)="recalculer()" /></label>
            <label>Autres taxes / redevances <input inputmode="decimal" formControlName="autres_taxes" (input)="recalculer()" /></label>
            <label>Remise <input inputmode="decimal" formControlName="remise" (input)="recalculer()" /></label>
            <label>Montant TTC
              <input inputmode="decimal" formControlName="montant_ttc" [readonly]="ttcCalcule()" [class.is-auto]="ttcCalcule()" />
              @if (ttcCalcule()) { <small class="bea-fx-form__hint">Calculé : HT + TVA + taxes − remise</small> }
            </label>
            <label>Montant à payer
              <input inputmode="decimal" formControlName="montant_a_payer" [placeholder]="'= TTC'" />
            </label>
            <label>Devise
              <select formControlName="devise">
                @for (d of store.config()?.devises ?? ['MRU']; track d) { <option [value]="d">{{ d }}</option> }
              </select>
            </label>
          </div>

          <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-fx-form__toggle" (click)="lignesOuvertes.set(!lignesOuvertes())" [disabled]="verrouMontants()">
            <mat-icon>{{ lignesOuvertes() ? 'expand_less' : 'list' }}</mat-icon> Lignes de facture ({{ lignes.length }})
          </button>
          @if (lignesOuvertes()) {
            <div class="bea-fx-lignes" formArrayName="lignes">
              @for (l of lignes.controls; track $index; let i = $index) {
                <div class="bea-fx-lignes__row" [formGroupName]="i">
                  <input formControlName="description" placeholder="Désignation (consommation, redevance…)" />
                  <input inputmode="decimal" formControlName="quantite" placeholder="Qté" />
                  <input formControlName="unite" placeholder="Unité" maxlength="20" />
                  <input inputmode="decimal" formControlName="prix_unitaire" placeholder="P.U." />
                  <input inputmode="decimal" formControlName="montant" placeholder="Montant" />
                  <button type="button" class="bea-mg__icon-btn" aria-label="Retirer la ligne" (click)="retirerLigne(i)"><mat-icon>delete</mat-icon></button>
                </div>
              }
              <div class="bea-fx-lignes__foot">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ajouterLigne()"><mat-icon>add</mat-icon> Ajouter une ligne</button>
                @if (lignes.length) { <span>Total lignes : <strong>{{ totalLignes() | montant }}</strong> (repris en HT si le HT est vide)</span> }
              </div>
            </div>
          }
        </fieldset>

        <label class="bea-fx-form__obs">Observation
          <textarea formControlName="observation" rows="2" maxlength="4000"></textarea>
        </label>
      </div>

      <footer class="bea-ct-modal__foot">
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
        @if (!facture()) {
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="form.invalid || busy()" (click)="enregistrer(false)"><mat-icon>edit_note</mat-icon> Brouillon</button>
        }
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || busy()">
          <mat-icon>save</mat-icon> {{ busy() ? 'Enregistrement…' : facture() ? 'Enregistrer' : 'Enregistrer (reçue)' }}
        </button>
      </footer>
    </form>
  `,
})
export class FactureFormComponent implements OnInit {
  readonly facture = input<FactureDetail | null>(null);
  readonly preset = input<{ point_facturation_id?: string; annee?: number; mois?: number } | null>(null);
  readonly saved = output<FactureDetail>();
  readonly closed = output<void>();

  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly mois = MOIS;
  readonly busy = signal(false);
  readonly lignesOuvertes = signal(false);
  readonly ttcCalcule = signal(false);
  private readonly fournisseurSel = signal('');

  readonly form = this.fb.group({
    point_facturation_id: [''],
    fournisseur_id: ['', Validators.required],
    agence_id: [''],
    contrat_id: [''],
    type_facture: [''],
    reference_fournisseur: [''],
    numero_fournisseur: [''],
    date_facture: [aujourdhui(), Validators.required],
    date_reception: [aujourdhui()],
    date_echeance: [''],
    periode_debut: [''],
    periode_fin: [''],
    mois: this.fb.control<number | null>(null),
    annee: this.fb.control<number | null>(null),
    montant_ht: [''],
    montant_tva: [''],
    autres_taxes: [''],
    remise: [''],
    montant_ttc: [''],
    montant_a_payer: [''],
    devise: ['MRU'],
    observation: [''],
    lignes: this.fb.array<ReturnType<FactureFormComponent['ligneGroup']>>([]),
  });

  readonly isDirty = unsavedChanges(() => this.form.dirty && !this.busy(), () => this.form);

  get lignes(): FormArray {
    return this.form.controls.lignes as FormArray;
  }

  readonly verrouMontants = computed(() => !!this.facture() && !this.facture()!.montants_modifiables);

  readonly pointsFiltres = computed(() => {
    const f = this.fournisseurSel();
    const actuel = this.facture()?.point_facturation_id;
    return (this.store.ref()?.points ?? []).filter((p) => (!f || p.fournisseur_id === f) && (p.statut === 'ACTIF' || p.id === actuel));
  });

  readonly contratsFiltres = computed(() => {
    const f = this.fournisseurSel();
    return (this.store.ref()?.contrats ?? []).filter((c) => !f || !c.fournisseur_id || c.fournisseur_id === f);
  });

  ngOnInit(): void {
    this.store.charger();
    const f = this.facture();
    if (f) {
      this.form.reset({
        point_facturation_id: f.point_facturation_id ?? '',
        fournisseur_id: f.fournisseur_id ?? '',
        agence_id: f.agence_id ?? '',
        contrat_id: f.contrat_id ?? '',
        type_facture: f.type_facture ?? '',
        reference_fournisseur: f.reference_fournisseur ?? '',
        numero_fournisseur: f.numero_fournisseur ?? '',
        date_facture: f.date_facture,
        date_reception: f.date_reception ?? '',
        date_echeance: f.date_echeance ?? '',
        periode_debut: f.periode_debut ?? '',
        periode_fin: f.periode_fin ?? '',
        mois: f.mois,
        annee: f.annee,
        montant_ht: this.txt(f.montant_ht),
        montant_tva: this.txt(f.montant_tva),
        autres_taxes: f.autres_taxes ? this.txt(f.autres_taxes) : '',
        remise: f.remise ? this.txt(f.remise) : '',
        montant_ttc: f.montant_ttc ? this.txt(f.montant_ttc) : '',
        montant_a_payer: f.montant_a_payer && f.montant_a_payer !== f.montant_ttc ? this.txt(f.montant_a_payer) : '',
        devise: f.devise || 'MRU',
        observation: f.observation ?? '',
      });
      for (const l of f.lignes) this.lignes.push(this.ligneGroup(l));
      this.lignesOuvertes.set(f.lignes.length > 0);
      this.fournisseurSel.set(f.fournisseur_id ?? '');
      if (this.verrouMontants()) {
        for (const k of ['point_facturation_id', 'fournisseur_id', 'agence_id', 'contrat_id', 'numero_fournisseur', 'date_facture', 'periode_debut', 'periode_fin', 'mois', 'annee', 'montant_ht', 'montant_tva', 'autres_taxes', 'remise', 'montant_ttc', 'montant_a_payer', 'devise', 'lignes'] as const) {
          this.form.controls[k].disable();
        }
      }
    } else {
      const p = this.preset();
      if (p?.point_facturation_id) {
        this.form.patchValue({ point_facturation_id: p.point_facturation_id });
        this.onPoint();
      }
      if (p?.annee && p?.mois) {
        this.form.patchValue({ annee: p.annee, mois: p.mois, periode_debut: `${p.annee}-${String(p.mois).padStart(2, '0')}-01` });
      }
    }
    this.recalculer();
    this.form.markAsPristine();
  }

  ligneGroup(l?: Partial<{ description: string; quantite: Num; unite: string | null; prix_unitaire: Num; montant: Num; type_ligne: string | null }>) {
    return this.fb.group({
      description: [l?.description ?? '', Validators.required],
      quantite: [this.txt(l?.quantite ?? null)],
      unite: [l?.unite ?? ''],
      prix_unitaire: [this.txt(l?.prix_unitaire ?? null)],
      montant: [this.txt(l?.montant ?? null)],
      type_ligne: [l?.type_ligne ?? ''],
    });
  }

  ajouterLigne(): void {
    this.lignes.push(this.ligneGroup());
    this.form.markAsDirty();
  }

  retirerLigne(i: number): void {
    this.lignes.removeAt(i);
    this.form.markAsDirty();
  }

  totalLignes(): number {
    return this.lignes.controls.reduce((acc, c) => {
      const v = c.value as { quantite: string; prix_unitaire: string; montant: string };
      const m = parseMontant(v.montant) ?? ((parseMontant(v.quantite) ?? 0) * (parseMontant(v.prix_unitaire) ?? 0));
      return acc + (m || 0);
    }, 0);
  }

  periodeAuto(): string {
    const v = this.form.getRawValue();
    const ref = v.periode_debut || v.date_facture;
    if (!ref) return '—';
    const [y, m] = ref.split('-');
    return `${MOIS[Number(m) - 1]} ${y}`;
  }

  typePoint(code: string): string {
    return TYPE_POINT_LABELS[code] ?? code;
  }

  onFournisseur(): void {
    const f = this.form.controls.fournisseur_id.value ?? '';
    this.fournisseurSel.set(f);
    const p = this.store.ref()?.points.find((x) => x.id === this.form.controls.point_facturation_id.value);
    if (p && p.fournisseur_id !== f) this.form.patchValue({ point_facturation_id: '' });
  }

  onPoint(): void {
    const p = this.store.ref()?.points.find((x) => x.id === this.form.controls.point_facturation_id.value);
    if (!p) return;
    this.form.patchValue({
      fournisseur_id: p.fournisseur_id,
      agence_id: p.agence_id ?? '',
      contrat_id: p.contrat_id ?? this.form.controls.contrat_id.value ?? '',
      type_facture: p.type_facture ?? this.form.controls.type_facture.value ?? '',
      reference_fournisseur: p.reference_fournisseur,
    });
    this.fournisseurSel.set(p.fournisseur_id);
  }

  recalculer(): void {
    const v = this.form.getRawValue();
    const ht = parseMontant(v.montant_ht);
    this.ttcCalcule.set(ht !== null);
    if (ht === null) return;
    const ttc = ht + (parseMontant(v.montant_tva) ?? 0) + (parseMontant(v.autres_taxes) ?? 0) - (parseMontant(v.remise) ?? 0);
    this.form.controls.montant_ttc.setValue(ttc.toFixed(2), { emitEvent: false });
  }

  fermer(): void {
    if (this.busy()) return;
    if (!this.form.dirty) {
      this.closed.emit();
      return;
    }
    this.dialog
      .confirmAction('depart', 'Fermer sans enregistrer ?', undefined, 'Les informations saisies seront perdues.')
      .subscribe((ok) => {
        if (ok) {
          this.form.markAsPristine();
          this.closed.emit();
        }
      });
  }

  enregistrer(recue: boolean, forcer = false): void {
    if (this.form.invalid || this.busy()) return;
    const body = this.corps();
    const f = this.facture();
    const payload = f ? { ...body, forcer } : { ...body, enregistrer: recue, forcer };
    this.feedback
      .run(() => (f ? this.api.patch<FactureDetail>(`/mg/factures/${f.id}`, payload) : this.api.post<FactureDetail>('/mg/factures', payload)), {
        loading: 'Enregistrement de la facture…',
        busy: this.busy,
        idempotent: !f,
        retry: false,
        errorTitle: 'Facture non enregistrée',
        errorHint: 'Vos données saisies ont été conservées.',
        onError: (e: ApiErrorInfo) => {
          if (e.code === 'FACTURE_PERIODE_EXISTANTE' && !forcer) {
            this.dialog
              .confirm({ title: 'Facture déjà saisie pour cette période', message: e.message, confirmLabel: 'Enregistrer quand même', tone: 'warn', icon: 'content_copy' })
              .subscribe((ok) => ok && this.enregistrer(recue, true));
          }
        },
        success: (r) => ({
          title: f ? 'Facture mise à jour' : recue ? 'Facture enregistrée' : 'Brouillon enregistré',
          details: [
            { label: 'Référence', value: r.reference },
            ...(r.periode_label ? [{ label: 'Période', value: r.periode_label }] : []),
          ],
        }),
      })
      .subscribe((r) => {
        this.form.markAsPristine();
        this.saved.emit(r);
      });
  }

  private corps(): Record<string, unknown> {
    const v = this.form.getRawValue();
    const ht = parseMontant(v.montant_ht);
    const body: Record<string, unknown> = {
      point_facturation_id: v.point_facturation_id || null,
      fournisseur_id: v.fournisseur_id || null,
      agence_id: v.agence_id || null,
      contrat_id: v.contrat_id || null,
      type_facture: v.type_facture || null,
      reference_fournisseur: v.reference_fournisseur?.trim() || null,
      numero_fournisseur: v.numero_fournisseur?.trim() || null,
      date_facture: v.date_facture,
      date_reception: v.date_reception || null,
      date_echeance: v.date_echeance || null,
      periode_debut: v.periode_debut || null,
      periode_fin: v.periode_fin || null,
      mois: v.mois && v.annee ? v.mois : null,
      annee: v.mois && v.annee ? v.annee : null,
      montant_ht: ht,
      montant_tva: parseMontant(v.montant_tva),
      autres_taxes: parseMontant(v.autres_taxes) ?? 0,
      remise: parseMontant(v.remise) ?? 0,
      montant_ttc: ht === null ? parseMontant(v.montant_ttc) : null,
      montant_a_payer: parseMontant(v.montant_a_payer),
      devise: v.devise || 'MRU',
      observation: v.observation?.trim() || null,
      lignes: (v.lignes as { description: string; quantite: string; unite: string; prix_unitaire: string; montant: string; type_ligne: string }[]).map((l) => ({
        description: l.description.trim(),
        quantite: parseMontant(l.quantite),
        unite: l.unite || null,
        prix_unitaire: parseMontant(l.prix_unitaire),
        montant: parseMontant(l.montant),
        type_ligne: l.type_ligne || null,
      })),
    };
    if (this.verrouMontants()) {
      return { date_reception: body['date_reception'], date_echeance: body['date_echeance'], observation: body['observation'], type_facture: body['type_facture'], reference_fournisseur: body['reference_fournisseur'] };
    }
    return body;
  }

  private txt(v: number | null | undefined): string {
    return v === null || v === undefined ? '' : String(v);
  }
}
