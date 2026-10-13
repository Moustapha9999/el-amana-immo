import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { ApercuClient, depuisSaisieLocale, maintenantLocal } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

const CARTE_MASQUEE = /^[0-9]{0,6}[\s*Xx•-]+[0-9]{0,4}$/;

/** Enregistrement d'une réclamation. La référence est attribuée par le serveur ; les pièces se déposent sur la fiche. */
@Component({
  selector: 'bea-rc-nouvelle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, ReclamationsUiComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Nouvelle réclamation</h1>
          <p class="bea-ct-head__sub">La référence REC-AAAA-NNNNNN est attribuée à l’enregistrement. Les dates saisies sont les dates réelles de réception ; l’heure de saisie est tracée séparément.</p>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reclamations/dossiers"><mat-icon>arrow_back</mat-icon> Réclamations</a>
        </div>
      </header>

      @if (!store.config()) {
        <section class="bea-mg__panel bea-rc-pad"><p class="bea-rc-muted">Chargement de la configuration…</p></section>
      } @else {
        @if (!unitesReception().length) {
          <div class="bea-rc-note bea-rc-note--warn"><mat-icon>warning</mat-icon>
            <span>Vous n’êtes rattaché à aucune unité de réception. Demandez à l’administrateur du module de vous rattacher à votre agence ou service (Paramètres → Unités & membres).</span>
          </div>
        }
        <form [formGroup]="form" (ngSubmit)="enregistrer()">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Réception</h2></div>
            <div class="bea-rc-form">
              <div class="bea-rc-row">
                <label>Canal de réception <em>*</em>
                  <select formControlName="canal_id" [class.is-invalid]="invalide('canal_id')">
                    <option value="">— Choisir —</option>
                    @for (c of store.refs('CANAL'); track c.id) { <option [value]="c.id">{{ c.libelle }}</option> }
                  </select>
                  @if (invalide('canal_id')) { <span class="bea-rc-err">Le canal est obligatoire</span> }
                </label>
                <label>Unité qui a reçu la réclamation <em>*</em>
                  <select formControlName="unite_reception_id" [class.is-invalid]="invalide('unite_reception_id')">
                    <option value="">— Choisir —</option>
                    @for (u of unitesReception(); track u.id) { <option [value]="u.id">{{ u.libelle }} ({{ u.type_libelle }})</option> }
                  </select>
                  @if (invalide('unite_reception_id')) { <span class="bea-rc-err">L’unité de réception est obligatoire</span> }
                </label>
                <label>Date et heure de première réception <em>*</em>
                  <input type="datetime-local" formControlName="date_premiere_reception" [max]="maintenant" [class.is-invalid]="invalide('date_premiere_reception')" />
                  <span class="bea-rc-hint">Date à laquelle la banque a reçu la réclamation (cachet, e-mail, appel…).</span>
                </label>
              </div>
              @if (peutReceptionSr()) {
                <label class="bea-rc-check"><input type="checkbox" formControlName="recue_sr" /> Déjà reçue par le Service Réclamations</label>
                @if (form.controls.recue_sr.value) {
                  <div class="bea-rc-row">
                    <label>Date et heure de réception par le Service Réclamations <em>*</em>
                      <input type="datetime-local" formControlName="date_reception_sr" [max]="maintenant" />
                    </label>
                  </div>
                }
              }
            </div>
          </section>

          @if (telephone()) {
            <section class="bea-mg__panel" formGroupName="appel">
              <div class="bea-mg__panel-top"><h2>Appel téléphonique</h2></div>
              <div class="bea-rc-form">
                <div class="bea-rc-row">
                  <label>Date et heure de l’appel <em>*</em>
                    <input type="datetime-local" formControlName="appel_le" [max]="maintenant" />
                  </label>
                  <label>Numéro de l’appelant <em>*</em>
                    <input formControlName="numero_appelant" maxlength="40" placeholder="+222 …" />
                  </label>
                  <label>Référence de l’appel
                    <input formControlName="reference_appel" maxlength="120" placeholder="N° de ticket du centre d’appel" />
                  </label>
                </div>
                <div class="bea-rc-row">
                  <label class="bea-rc-check"><input type="checkbox" formControlName="identite_verifiee" /> Identité de l’appelant vérifiée</label>
                  <label>Mode de vérification
                    <input formControlName="mode_verification" maxlength="200" placeholder="Questions de sécurité, date de naissance…" />
                  </label>
                </div>
                <div class="bea-rc-row">
                  <label>Rappel
                    <select formControlName="rappel_statut">
                      @for (r of store.libelles('statuts_rappel'); track r.code) { <option [value]="r.code">{{ r.libelle }}</option> }
                    </select>
                  </label>
                  @if (form.controls.appel.controls.rappel_statut.value === 'A_RAPPELER') {
                    <label>Rappel prévu le <em>*</em>
                      <input type="datetime-local" formControlName="rappel_prevu_le" />
                    </label>
                  }
                  @if (store.config()!.parametres.enregistrement_appels_autorise) {
                    <label>Référence de l’enregistrement
                      <input formControlName="reference_enregistrement" maxlength="200" />
                    </label>
                  }
                </div>
                @if (!store.config()!.parametres.enregistrement_appels_autorise) {
                  <p class="bea-rc-hint">La référence d’enregistrement d’appel n’est pas activée : la banque ne l’a pas autorisée.</p>
                }
                <label>Notes de l’appel
                  <textarea formControlName="commentaire" maxlength="4000" rows="2"></textarea>
                </label>
              </div>
            </section>
          }

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Réclamant</h2></div>
            <div class="bea-rc-form">
              <div class="bea-rc-row">
                <div class="bea-rc-label">Racine client (ORION)
                  <span class="bea-rc-inline">
                    <input class="bea-rc-input" formControlName="client_racine" maxlength="6" inputmode="numeric" placeholder="6 chiffres" [class.is-invalid]="invalide('client_racine')" />
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="recherche()" (click)="chercherClient()"><mat-icon>person_search</mat-icon> Rechercher</button>
                  </span>
                  @if (invalide('client_racine')) { <span class="bea-rc-err">La racine comporte 6 chiffres</span> }
                  @else if (client()) { <span class="bea-rc-hint">Client trouvé : {{ client()!.nom }} — {{ client()!.comptes.length }} compte(s)</span> }
                  @else { <span class="bea-rc-hint">Facultatif : laissez vide pour un non-client.</span> }
                </div>
                <label>Catégorie
                  <select formControlName="client_categorie">
                    <option value="">— Non précisée —</option>
                    @for (c of store.libelles('categories_client'); track c.code) { <option [value]="c.code">{{ c.libelle }}</option> }
                  </select>
                </label>
                <label>Nom / raison sociale <em>*</em>
                  <input formControlName="client_nom" maxlength="255" [class.is-invalid]="invalide('client_nom')" />
                  @if (invalide('client_nom')) { <span class="bea-rc-err">Le nom du réclamant est obligatoire</span> }
                </label>
              </div>
              <div class="bea-rc-row">
                <label>Téléphone <input formControlName="client_telephone" maxlength="40" /></label>
                <label>E-mail <input type="email" formControlName="client_email" maxlength="255" /></label>
                <label>Agence du client
                  <select formControlName="client_agence_id">
                    <option value="">—</option>
                    @for (a of store.config()!.agences; track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
                  </select>
                </label>
              </div>
              <label>Adresse <textarea formControlName="client_adresse" maxlength="2000" rows="2"></textarea></label>
            </div>
          </section>

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Objet de la réclamation</h2></div>
            <div class="bea-rc-form">
              <div class="bea-rc-row">
                <label>Objet <em>*</em>
                  <input formControlName="objet" maxlength="255" [class.is-invalid]="invalide('objet')" placeholder="Ex. Prélèvement non autorisé" />
                  @if (invalide('objet')) { <span class="bea-rc-err">L’objet est obligatoire</span> }
                </label>
                <label>Priorité
                  <select formControlName="priorite">
                    @for (p of store.libelles('priorites'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
                  </select>
                </label>
              </div>
              <label>Description <em>*</em>
                <textarea formControlName="description" maxlength="20000" rows="5" [class.is-invalid]="invalide('description')" placeholder="Faits exposés par le client, demande formulée…"></textarea>
                @if (invalide('description')) { <span class="bea-rc-err">La description est obligatoire</span> }
              </label>
              <div class="bea-rc-row">
                <label>Type
                  <select formControlName="type_id">
                    <option value="">— À qualifier —</option>
                    @for (t of store.refs('TYPE'); track t.id) { <option [value]="t.id">{{ t.libelle }}</option> }
                  </select>
                </label>
                <label>Motif
                  <select formControlName="motif_id" [attr.disabled]="!motifs().length ? true : null">
                    <option value="">{{ motifs().length ? '— Choisir —' : '— Aucun motif pour ce type —' }}</option>
                    @for (m of motifs(); track m.id) { <option [value]="m.id">{{ m.libelle }}</option> }
                  </select>
                </label>
                <label>Sous-motif
                  <select formControlName="sous_motif_id" [attr.disabled]="!sousMotifs().length ? true : null">
                    <option value="">{{ sousMotifs().length ? '— Choisir —' : '—' }}</option>
                    @for (m of sousMotifs(); track m.id) { <option [value]="m.id">{{ m.libelle }}</option> }
                  </select>
                </label>
              </div>
              <p class="bea-rc-hint">La qualification peut être complétée ou corrigée par le Service Réclamations.</p>
            </div>
          </section>

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Compte et opération concernés <small class="bea-rc-hint">(facultatif)</small></h2></div>
            <div class="bea-rc-form">
              <div class="bea-rc-row">
                <label>Compte concerné
                  @if (client()?.comptes?.length) {
                    <select formControlName="compte_reference">
                      <option value="">—</option>
                      @for (c of client()!.comptes; track c.compte) { <option [value]="c.compte">{{ c.compte }} · {{ c.devise }} · {{ c.etat }}</option> }
                    </select>
                  } @else {
                    <input formControlName="compte_reference" maxlength="60" />
                  }
                </label>
                <label>Carte (masquée)
                  <input formControlName="carte_masquee" maxlength="25" placeholder="123456******1234" [class.is-invalid]="invalide('carte_masquee')" />
                  @if (invalide('carte_masquee')) { <span class="bea-rc-err">Saisissez au plus les 6 premiers et 4 derniers chiffres</span> }
                  @else { <span class="bea-rc-hint">Jamais le numéro complet.</span> }
                </label>
                <label>Référence de l’opération <input formControlName="operation_reference" maxlength="120" /></label>
              </div>
              <div class="bea-rc-row">
                <label>Date de l’opération <input type="date" formControlName="operation_date" /></label>
                <label>Montant contesté <input type="number" min="0" step="0.01" formControlName="montant_conteste" /></label>
                <label>Devise <input formControlName="devise" maxlength="3" placeholder="MRU" /></label>
              </div>
            </div>
          </section>

          <div class="bea-rc-savebar">
            <span>Le scan original et les pièces du client s’ajoutent ensuite dans l’onglet « Documents » de la fiche.</span>
            <span class="bea-mg__actions">
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reclamations/dossiers">Annuler</a>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer la réclamation</button>
            </span>
          </div>
        </form>
      }
    </section>
  `,
})
export class RcNouvelleComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  readonly store = inject(ReclamationsStore);

  readonly maintenant = maintenantLocal();
  readonly busy = signal(false);
  readonly tente = signal(false);
  readonly recherche = signal(false);
  readonly client = signal<ApercuClient | null>(null);
  private readonly canal = signal('');
  private readonly typeId = signal('');
  private readonly motifId = signal('');
  private initial = '';

  readonly form = this.fb.nonNullable.group({
    canal_id: ['', Validators.required],
    unite_reception_id: ['', Validators.required],
    date_premiere_reception: [maintenantLocal(), Validators.required],
    recue_sr: [false],
    date_reception_sr: [maintenantLocal()],
    appel: this.fb.nonNullable.group({
      appel_le: [maintenantLocal()],
      numero_appelant: [''],
      reference_appel: [''],
      identite_verifiee: [false],
      mode_verification: [''],
      rappel_statut: ['AUCUN'],
      rappel_prevu_le: [''],
      reference_enregistrement: [''],
      commentaire: [''],
    }),
    client_racine: ['', Validators.pattern(/^[0-9]{6}$/)],
    client_categorie: [''],
    client_nom: ['', Validators.required],
    client_telephone: [''],
    client_email: [''],
    client_agence_id: [''],
    client_adresse: [''],
    objet: ['', Validators.required],
    description: ['', Validators.required],
    priorite: ['NORMALE'],
    type_id: [''],
    motif_id: [''],
    sous_motif_id: [''],
    compte_reference: [''],
    carte_masquee: ['', Validators.pattern(CARTE_MASQUEE)],
    operation_reference: [''],
    operation_date: [''],
    montant_conteste: [null as number | null],
    devise: [''],
  });

  readonly unitesReception = computed(() => this.store.unitesReception());
  readonly telephone = computed(() => this.store.refs('CANAL', true).find((c) => c.id === this.canal())?.code === 'TELEPHONE');
  readonly motifs = computed(() => this.store.enfants('MOTIF', this.typeId()));
  readonly sousMotifs = computed(() => this.store.enfants('SOUS_MOTIF', this.motifId()));
  readonly peutReceptionSr = computed(() => {
    const c = this.store.config();
    return !!c && (c.acces.membre_service_central || c.acces.capacites.qualifier);
  });

  readonly hasUnsavedChanges = unsavedChanges(() => !this.busy() && JSON.stringify(this.form.getRawValue()) !== this.initial);

  ngOnInit(): void {
    this.store.charger();
    this.initial = JSON.stringify(this.form.getRawValue());
    const c = this.form.controls;
    c.canal_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.canal.set(v));
    c.type_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => {
      this.typeId.set(v);
      c.motif_id.setValue('');
    });
    c.motif_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => {
      this.motifId.set(v);
      c.sous_motif_id.setValue('');
    });
    c.date_premiere_reception.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => {
      if (!c.appel.controls.appel_le.dirty) c.appel.controls.appel_le.setValue(v, { emitEvent: false });
    });
    c.client_racine.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.client.set(null));
  }

  /** Point de réception mono-unité : unité pré-sélectionnée dès que la configuration est disponible. */
  private readonly preselection = effect(() => {
    const unites = this.unitesReception();
    const ctl = this.form.controls.unite_reception_id;
    if (unites.length === 1 && !ctl.value) {
      ctl.setValue(unites[0].id);
      this.initial = JSON.stringify(this.form.getRawValue());
    }
  });

  invalide(nom: 'canal_id' | 'unite_reception_id' | 'date_premiere_reception' | 'client_nom' | 'objet' | 'description' | 'client_racine' | 'carte_masquee'): boolean {
    const ctl = this.form.controls[nom];
    return ctl.invalid && (ctl.touched || this.tente());
  }

  chercherClient(): void {
    const racine = this.form.controls.client_racine.value.trim();
    if (!/^[0-9]{6}$/.test(racine)) {
      this.form.controls.client_racine.markAsTouched();
      return;
    }
    this.recherche.set(true);
    this.rc.apercuClient(racine).subscribe({
      next: (cl) => {
        this.recherche.set(false);
        this.client.set(cl);
        const c = this.form.controls;
        if (!c.client_nom.value.trim()) c.client_nom.setValue(cl.nom);
        if (!c.client_categorie.value) c.client_categorie.setValue(cl.categorie);
        const agences = new Set(cl.comptes.map((x) => x.agence_id));
        if (!c.client_agence_id.value && agences.size === 1) c.client_agence_id.setValue([...agences][0]);
      },
      error: (e) => {
        this.recherche.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Client introuvable'));
      },
    });
  }

  enregistrer(): void {
    this.tente.set(true);
    this.form.markAllAsTouched();
    const v = this.form.getRawValue();
    if (this.form.invalid) {
      this.feedback.warning({ title: 'Champs à corriger', message: 'Vérifiez les champs signalés en rouge.' });
      return;
    }
    const premiere = depuisSaisieLocale(v.date_premiere_reception);
    const receptionSr = v.recue_sr && this.peutReceptionSr() ? depuisSaisieLocale(v.date_reception_sr) : null;
    if (!premiere || (v.recue_sr && this.peutReceptionSr() && !receptionSr)) {
      this.feedback.warning({ title: 'Date invalide', message: 'Renseignez les dates et heures de réception.' });
      return;
    }
    let appel: Record<string, unknown> | null = null;
    if (this.telephone()) {
      const a = v.appel;
      if (!a.numero_appelant.trim() || !depuisSaisieLocale(a.appel_le) || (a.rappel_statut === 'A_RAPPELER' && !a.rappel_prevu_le)) {
        this.feedback.warning({ title: 'Appel incomplet', message: 'Date de l’appel, numéro de l’appelant et, le cas échéant, date de rappel sont obligatoires.' });
        return;
      }
      appel = {
        appel_le: depuisSaisieLocale(a.appel_le), numero_appelant: a.numero_appelant.trim(),
        reference_appel: a.reference_appel.trim() || null, identite_verifiee: a.identite_verifiee,
        mode_verification: a.mode_verification.trim() || null, rappel_statut: a.rappel_statut,
        rappel_prevu_le: a.rappel_statut === 'A_RAPPELER' ? depuisSaisieLocale(a.rappel_prevu_le) : null,
        reference_enregistrement: a.reference_enregistrement.trim() || null, commentaire: a.commentaire.trim() || null,
      };
    }
    const texte = (s: string) => s.trim() || null;
    const corps = {
      canal_id: v.canal_id, unite_reception_id: v.unite_reception_id, date_premiere_reception: premiere,
      date_reception_sr: receptionSr, appel,
      client_racine: texte(v.client_racine), client_categorie: v.client_categorie || null, client_nom: v.client_nom.trim(),
      client_telephone: texte(v.client_telephone), client_email: texte(v.client_email),
      client_agence_id: v.client_agence_id || null, client_adresse: texte(v.client_adresse),
      objet: v.objet.trim(), description: v.description.trim(), priorite: v.priorite,
      type_id: v.type_id || null, motif_id: v.motif_id || null, sous_motif_id: v.sous_motif_id || null,
      compte_reference: texte(v.compte_reference), carte_masquee: texte(v.carte_masquee),
      operation_reference: texte(v.operation_reference), operation_date: v.operation_date || null,
      montant_conteste: v.montant_conteste ?? null, devise: texte(v.devise)?.toUpperCase() ?? null,
    };
    this.feedback
      .run(() => this.rc.creer(corps), {
        busy: this.busy,
        loading: 'Enregistrement de la réclamation…',
        success: (d) => ({
          title: 'Réclamation enregistrée',
          details: [
            { label: 'Référence', value: d.reference },
            { label: 'Statut', value: d.statut_libelle },
          ],
        }),
        errorTitle: 'Enregistrement refusé',
        errorHint: 'Vos données saisies ont été conservées.',
      })
      .subscribe((d) => {
        this.initial = JSON.stringify(this.form.getRawValue());
        void this.router.navigate(['/reclamations/dossiers', d.id], { queryParams: { onglet: 'documents' } });
      });
  }
}
