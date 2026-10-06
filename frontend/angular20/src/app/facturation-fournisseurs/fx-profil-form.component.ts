import { ChangeDetectionStrategy, Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { parseMontant } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { ChampProfil, EtatChamp, FX_BASE, FxProfil, LIBELLES_CHAMPS } from './facturation.models';
import { FacturationStore } from './facturation.store';

const CHAMPS = Object.keys(LIBELLES_CHAMPS) as ChampProfil[];
const ETATS: { code: EtatChamp; label: string }[] = [
  { code: 'obligatoire', label: 'Obligatoire' },
  { code: 'facultatif', label: 'Facultatif' },
  { code: 'masque', label: 'Masqué' },
];

/** Création / configuration d'un profil fournisseur : champs applicables, libellés, taux de TVA. Aucun code par fournisseur. */
@Component({
  selector: 'bea-fx-profil-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, RouterLink],
  template: `
    <div class="bea-mg__backdrop" (click)="fermer()"></div>
    <form class="bea-mg__modal bea-mg__modal--lg bea-ct-modal bea-fx-form" role="dialog" aria-modal="true" aria-labelledby="bea-fx-profil-title"
      [formGroup]="form" (ngSubmit)="enregistrer()">
      <header class="bea-ct-modal__head">
        <h2 id="bea-fx-profil-title"><mat-icon>{{ profil() ? 'tune' : 'add_business' }}</mat-icon>
          {{ profil() ? 'Configurer ' + profil()!.libelle : 'Nouveau fournisseur' }}</h2>
        <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
      </header>

      <div class="bea-ct-modal__body bea-fx-form__body">
        <fieldset class="bea-fx-form__set">
          <legend>Fournisseur</legend>
          @if (!profil()) {
            <div class="bea-fx-seg" role="radiogroup" aria-label="Fournisseur">
              <button type="button" [class.is-on]="mode() === 'existant'" (click)="mode.set('existant')"><mat-icon>list</mat-icon> Fournisseur existant</button>
              <button type="button" [class.is-on]="mode() === 'nouveau'" (click)="mode.set('nouveau')"><mat-icon>add</mat-icon> Nouveau fournisseur</button>
            </div>
          }
          <div class="bea-ct-grid">
            @if (mode() === 'existant' || profil()) {
              <label class="bea-ct-span2">Fournisseur du référentiel *
                <select formControlName="fournisseur_id">
                  <option value="">— Sélectionner —</option>
                  @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }} ({{ f.code }})</option> }
                </select>
                @if (profil() && profilUtilise()) { <small class="bea-fx-form__hint">Profil déjà utilisé : le fournisseur n’est plus modifiable.</small> }
              </label>
            } @else {
              <ng-container formGroupName="nouveau">
                <label class="bea-ct-span2">Raison sociale * <input formControlName="raison_sociale" maxlength="255" placeholder="Ex. MAURITEL" /></label>
                <label>Téléphone <input formControlName="telephone" maxlength="40" /></label>
                <label>E-mail <input type="email" formControlName="email" maxlength="255" /></label>
                <label>NIF <input formControlName="nif" maxlength="60" /></label>
                <label>Délai de paiement (jours) <input type="number" min="0" max="365" formControlName="delai_paiement_jours" /></label>
              </ng-container>
              <p class="bea-ct-help bea-ct-span2"><mat-icon>info</mat-icon> Créé dans le référentiel fournisseurs commun (code FRS attribué automatiquement).</p>
            }
          </div>
        </fieldset>

        <fieldset class="bea-fx-form__set">
          <legend>Profil de facturation</legend>
          <div class="bea-ct-grid">
            <label>Libellé affiché * <input formControlName="libelle" maxlength="120" placeholder="Ex. MAURITEL ADSL" (input)="proposerCode()" /></label>
            <label>Code *
              <input formControlName="code" maxlength="40" placeholder="MAURITEL_ADSL" [readonly]="!!profil()" />
            </label>
            <label>Type de facture
              <select formControlName="type_facture">
                <option value="">—</option>
                @for (t of store.config()?.types_facture ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            @if (profil(); as p) {
              <div class="bea-fx-form__ro">
                <span>TVA en vigueur</span>
                <strong>{{ p.taux_tva === null ? 'Non configurée' : p.taux_tva + ' %' }}</strong>
                <small class="bea-fx-form__hint">{{ p.taux_tva_liste.length }} taux daté(s) ·
                  <a [routerLink]="base + '/parametres'" fragment="tva">Gérer dans Paramètres</a></small>
              </div>
            } @else {
              <label>Taux de TVA (%)
                <input inputmode="decimal" formControlName="taux_tva" placeholder="Non configuré" />
                <small class="bea-fx-form__hint">Laisser vide tant que le taux n’est pas confirmé : aucune TVA ne sera proposée ni contrôlée. Les changements de taux se gèrent ensuite dans Paramètres.</small>
              </label>
            }
            @if (!profil()) {
              <label>Partir du modèle
                <select (change)="copierModele($any($event.target).value)">
                  <option value="">— Tous les champs facultatifs —</option>
                  @for (p of store.ref()?.profils ?? []; track p.id) { <option [value]="p.id">{{ p.libelle }}</option> }
                </select>
              </label>
            }
            <label>Ordre d’affichage <input type="number" min="0" max="9999" formControlName="ordre" /></label>
            <label class="bea-fx-check"><input type="checkbox" formControlName="actif" /> Profil actif (proposé à la saisie)</label>
            <label class="bea-ct-span2">Description / consignes de saisie <textarea formControlName="description" rows="2" maxlength="4000"></textarea></label>
          </div>
        </fieldset>

        <fieldset class="bea-fx-form__set">
          <legend>Champs de la facture <small>(obligatoire, facultatif ou masqué, libellé tel qu’imprimé sur la facture)</small></legend>
          <div class="bea-fx-champs">
            @for (c of champs; track c) {
              <div class="bea-fx-champs__row">
                <span class="bea-fx-champs__nom">{{ defaut(c) }}</span>
                <div class="bea-fx-seg bea-fx-seg--sm" role="radiogroup" [attr.aria-label]="defaut(c)">
                  @for (e of etats; track e.code) {
                    <button type="button" [class.is-on]="etat(c) === e.code" [attr.data-etat]="e.code"
                      [disabled]="e.code === 'masque' && c === 'montant_ttc'" (click)="choisirEtat(c, e.code)">{{ e.label }}</button>
                  }
                </div>
                <input class="bea-fx-champs__lib" [value]="libelles()[c] || ''" [placeholder]="defaut(c)" maxlength="80"
                  [disabled]="etat(c) === 'masque'" (input)="choisirLibelle(c, $any($event.target).value)" [attr.aria-label]="'Libellé ' + defaut(c)" />
              </div>
            }
          </div>
          <p class="bea-ct-help"><mat-icon>rule</mat-icon> Le montant TTC reste toujours saisi. Un champ masqué n’apparaît pas à la saisie et n’est jamais stocké.</p>
        </fieldset>
      </div>

      <footer class="bea-ct-modal__foot">
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="invalide() || busy()">
          <mat-icon>save</mat-icon> {{ busy() ? 'Enregistrement…' : profil() ? 'Enregistrer' : 'Créer le fournisseur' }}
        </button>
      </footer>
    </form>
  `,
})
export class FxProfilFormComponent implements OnInit {
  readonly profil = input<FxProfil | null>(null);
  readonly fournisseurId = input<string | null>(null);
  readonly profilUtilise = input(false);
  readonly saved = output<FxProfil>();
  readonly closed = output<void>();
  readonly base = FX_BASE;

  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly champs = CHAMPS;
  readonly etats = ETATS;
  readonly busy = signal(false);
  readonly mode = signal<'existant' | 'nouveau'>('existant');
  readonly etatsChamps = signal<Record<string, EtatChamp>>(Object.fromEntries(CHAMPS.map((c) => [c, 'facultatif'])));
  readonly libelles = signal<Record<string, string>>({});
  private readonly modifie = signal(false);
  private codeManuel = false;

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.pattern(/^[A-Za-z0-9_]{2,40}$/)]],
    libelle: ['', Validators.required],
    fournisseur_id: [''],
    type_facture: [''],
    taux_tva: [''],
    description: [''],
    ordre: [0],
    actif: [true],
    nouveau: this.fb.nonNullable.group({
      raison_sociale: [''],
      telephone: [''],
      email: [''],
      nif: [''],
      delai_paiement_jours: this.fb.control<number | null>(null),
    }),
  });

  readonly isDirty = unsavedChanges(() => (this.form.dirty || this.modifie()) && !this.busy(), () => this.form);

  ngOnInit(): void {
    this.store.charger();
    const p = this.profil();
    if (p) {
      this.form.reset({
        code: p.code, libelle: p.libelle, fournisseur_id: p.fournisseur_id, type_facture: p.type_facture ?? '',
        taux_tva: p.taux_tva === null ? '' : String(p.taux_tva), description: p.description ?? '', ordre: p.ordre, actif: p.actif,
      });
      this.etatsChamps.set({ ...this.etatsChamps(), ...p.champs });
      this.libelles.set({ ...p.libelles });
      this.codeManuel = true;
      if (this.profilUtilise()) this.form.controls.fournisseur_id.disable();
    } else if (this.fournisseurId()) {
      this.form.patchValue({ fournisseur_id: this.fournisseurId()! });
    }
    this.form.controls.code.valueChanges.subscribe(() => (this.codeManuel = true));
  }

  defaut(c: ChampProfil): string {
    return LIBELLES_CHAMPS[c];
  }

  etat(c: ChampProfil): EtatChamp {
    return this.etatsChamps()[c] ?? 'facultatif';
  }

  choisirEtat(c: ChampProfil, e: EtatChamp): void {
    this.etatsChamps.update((m) => ({ ...m, [c]: e }));
    this.modifie.set(true);
  }

  choisirLibelle(c: ChampProfil, v: string): void {
    this.libelles.update((m) => ({ ...m, [c]: v }));
    this.modifie.set(true);
  }

  proposerCode(): void {
    if (this.profil() || (this.codeManuel && this.form.controls.code.value)) return;
    const code = this.form.controls.libelle.value
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 40);
    this.form.controls.code.setValue(code, { emitEvent: false });
  }

  copierModele(id: string): void {
    const p = (this.store.ref()?.profils ?? []).find((x) => x.id === id);
    this.etatsChamps.set({ ...Object.fromEntries(CHAMPS.map((c) => [c, 'facultatif'])), ...(p?.champs ?? {}) });
    this.libelles.set({ ...(p?.libelles ?? {}) });
    if (p && !this.form.controls.type_facture.value) this.form.patchValue({ type_facture: p.type_facture ?? '' });
    this.modifie.set(true);
  }

  private taux(): number | null | 'invalide' {
    const brut = this.form.controls.taux_tva.value.trim();
    if (!brut) return null;
    const t = parseMontant(brut);
    return t === null || t < 0 || t > 100 ? 'invalide' : t;
  }

  invalide(): boolean {
    if (this.form.controls.code.invalid || this.form.controls.libelle.invalid || this.taux() === 'invalide') return true;
    if (this.profil()) return false;
    return this.mode() === 'existant'
      ? !this.form.controls.fournisseur_id.value
      : this.form.controls.nouveau.controls.raison_sociale.value.trim().length < 2;
  }

  fermer(): void {
    if (this.busy()) return;
    if (!this.form.dirty && !this.modifie()) {
      this.closed.emit();
      return;
    }
    this.dialog
      .confirmAction('depart', 'Fermer sans enregistrer ?', undefined, 'La configuration saisie sera perdue.')
      .subscribe((ok) => {
        if (ok) {
          this.form.markAsPristine();
          this.modifie.set(false);
          this.closed.emit();
        }
      });
  }

  enregistrer(): void {
    if (this.invalide() || this.busy()) return;
    const v = this.form.getRawValue();
    const libelles = Object.fromEntries(
      Object.entries(this.libelles()).filter(([c, l]) => l?.trim() && this.etat(c as ChampProfil) !== 'masque').map(([c, l]) => [c, l.trim()]),
    );
    const body: Record<string, unknown> = {
      libelle: v.libelle.trim(),
      type_facture: v.type_facture || null,
      description: v.description.trim() || null,
      ordre: v.ordre || 0,
      actif: v.actif,
      champs: this.etatsChamps(),
      libelles,
    };
    const p = this.profil();
    if (p) {
      if (!this.profilUtilise()) body['fournisseur_id'] = v.fournisseur_id;
    } else {
      body['code'] = v.code.trim().toUpperCase();
      body['taux_tva'] = this.taux();
      if (this.mode() === 'existant') {
        body['fournisseur_id'] = v.fournisseur_id;
      } else {
        const n = v.nouveau;
        body['nouveau_fournisseur'] = {
          raison_sociale: n.raison_sociale.trim(),
          telephone: n.telephone.trim() || null,
          email: n.email.trim() || null,
          nif: n.nif.trim() || null,
          delai_paiement_jours: n.delai_paiement_jours,
        };
      }
    }
    this.feedback
      .run(() => (p ? this.api.patch<FxProfil>(`/mg/factures/profils/${p.id}`, body) : this.api.post<FxProfil>('/mg/factures/profils', body)), {
        loading: p ? 'Enregistrement du profil…' : 'Création du fournisseur…',
        busy: this.busy,
        idempotent: !p,
        retry: false,
        errorTitle: p ? 'Profil non enregistré' : 'Fournisseur non créé',
        errorHint: 'Votre saisie a été conservée.',
        success: (r) => ({
          title: p ? 'Profil mis à jour' : 'Fournisseur créé',
          details: [
            { label: 'Profil', value: r.libelle },
            { label: 'Fournisseur', value: r.fournisseur ?? '—' },
            { label: 'TVA', value: r.taux_tva === null ? 'Non configurée' : `${r.taux_tva} %` },
          ],
        }),
      })
      .subscribe((r) => {
        this.form.markAsPristine();
        this.modifie.set(false);
        this.store.charger(true);
        this.saved.emit(r);
      });
  }
}
