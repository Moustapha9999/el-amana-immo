import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { ApercuClient, OperationSaisie, depuisSaisieLocale, maintenantLocal } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { CLASSEMENT_VIDE, Classement, RcClassementComponent, classementCorps, classementErreur } from '../shared/rc-classement.component';
import { RcOperationsComponent, clientsSaisis, operationsCorps, operationsErreur } from '../shared/rc-operations.component';

function aujourdhui(): string {
  return maintenantLocal().slice(0, 10);
}

/** Enregistrement d'une réclamation. La référence est attribuée par le serveur ; les pièces se déposent sur la fiche. */
@Component({
  selector: 'bea-rc-nouvelle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, ReclamationsUiComponent, RcClassementComponent, RcOperationsComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Nouvelle réclamation</h1>
          <p class="bea-ct-head__sub">La référence REC-AAAA-NNNNNN est attribuée automatiquement à l’enregistrement.</p>
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
            <div class="bea-mg__panel-top"><h2>Informations générales</h2></div>
            <div class="bea-rc-form">
              <div class="bea-rc-row">
                <label>Référence
                  <input value="Attribuée à l’enregistrement" disabled />
                </label>
                <label>Date de la réclamation <em>*</em>
                  <input type="date" formControlName="date_reclamation" [max]="aujourdhui" [class.is-invalid]="invalide('date_reclamation')" />
                  @if (invalide('date_reclamation')) { <span class="bea-rc-err">La date de la réclamation est obligatoire</span> }
                  @else { <span class="bea-rc-hint">Date portée par le courrier, l’e-mail ou la demande du client.</span> }
                </label>
                <label>Canal de réception <em>*</em>
                  <select formControlName="canal_id" [class.is-invalid]="invalide('canal_id')">
                    <option value="">— Choisir —</option>
                    @for (c of store.refs('CANAL'); track c.id) { <option [value]="c.id">{{ c.libelle }}</option> }
                  </select>
                  @if (invalide('canal_id')) { <span class="bea-rc-err">Le canal est obligatoire</span> }
                </label>
              </div>
              <label class="bea-rc-check"><input type="checkbox" formControlName="reception_differente" /> Reçue par la banque à une autre date</label>
              @if (form.controls.reception_differente.value) {
                <div class="bea-rc-row">
                  <label>Date et heure de réception par la banque <em>*</em>
                    <input type="datetime-local" formControlName="date_premiere_reception" [max]="maintenant" />
                    <span class="bea-rc-hint">Cachet d’arrivée, horodatage de l’e-mail… Les durées mesurées (prise en charge, clôture) partent de cette date.</span>
                  </label>
                </div>
              }
              <div class="bea-rc-row">
                <label>Agence de réception
                  <select formControlName="agence_reception_id">
                    <option value="">—</option>
                    @for (a of store.config()!.agences; track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
                  </select>
                </label>
                <label>Réception
                  <select formControlName="niveau_concerne">
                    <option value="SERVICE">Service</option>
                    <option value="DEPARTEMENT">Département</option>
                  </select>
                </label>
                @if (form.controls.niveau_concerne.value === 'DEPARTEMENT') {
                  <label>Département concerné <em>*</em>
                    <select formControlName="org_departement_id" [class.is-invalid]="tente() && !form.controls.org_departement_id.value">
                      <option value="">— Choisir —</option>
                      @for (d of store.departements(); track d.id) { <option [value]="d.id" [title]="d.chemin ?? ''">{{ d.libelle }}{{ d.sigle ? ' (' + d.sigle + ')' : '' }}</option> }
                    </select>
                    @if (tente() && !form.controls.org_departement_id.value) { <span class="bea-rc-err">Indiquez le département concerné</span> }
                  </label>
                } @else {
                  <label>Service concerné <em>*</em>
                    <select formControlName="org_service_id" [class.is-invalid]="tente() && !form.controls.org_service_id.value">
                      <option value="">— Choisir —</option>
                      @for (s of store.services(); track s.id) { <option [value]="s.id" [title]="s.chemin ?? ''">{{ s.libelle }}{{ s.sigle ? ' (' + s.sigle + ')' : '' }}</option> }
                    </select>
                    @if (tente() && !form.controls.org_service_id.value) { <span class="bea-rc-err">Indiquez le service concerné</span> }
                  </label>
                }
              </div>
              @if (uniteAChoisir()) {
                <div class="bea-rc-row">
                  <label>Votre unité <em>*</em>
                    <select formControlName="unite_reception_id" [class.is-invalid]="invalide('unite_reception_id')">
                      <option value="">— Choisir —</option>
                      @for (u of unitesReception(); track u.id) { <option [value]="u.id">{{ u.libelle }} ({{ u.type_libelle }})</option> }
                    </select>
                    <span class="bea-rc-hint">Vous êtes rattaché à plusieurs unités : indiquez celle qui enregistre la réclamation.</span>
                  </label>
                </div>
              }
              <div class="bea-rc-row">
                <label>Priorité
                  <select formControlName="priorite">
                    @for (p of store.libelles('priorites'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
                  </select>
                </label>
              </div>
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
                <label>Notes de l’appel
                  <textarea formControlName="commentaire" maxlength="4000" rows="2"></textarea>
                </label>
              </div>
            </section>
          }

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Client</h2></div>
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
                  @if (invalide('client_nom')) { <span class="bea-rc-err">Le nom du client est obligatoire</span> }
                </label>
              </div>
              <div class="bea-rc-row">
                <label>Téléphone <input formControlName="client_telephone" maxlength="40" /></label>
                <label>E-mail <input type="email" formControlName="client_email" maxlength="255" /></label>
              </div>
              <label>Adresse <textarea formControlName="client_adresse" maxlength="2000" rows="2"></textarea></label>
            </div>
          </section>

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Réclamation</h2></div>
            <div class="bea-rc-form">
              <bea-rc-classement [(valeur)]="classement" [tente]="tente()" />
              <label>Objet <em>*</em>
                <input formControlName="objet" maxlength="255" [class.is-invalid]="invalide('objet')" placeholder="Résumé court, ex. Prélèvement non autorisé" />
                @if (invalide('objet')) { <span class="bea-rc-err">L’objet est obligatoire</span> }
              </label>
              <label>Description détaillée <em>*</em>
                <textarea formControlName="description" maxlength="20000" rows="5" [class.is-invalid]="invalide('description')" placeholder="Faits exposés par le client, demande formulée…"></textarea>
                @if (invalide('description')) { <span class="bea-rc-err">La description est obligatoire</span> }
              </label>
            </div>
          </section>

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Opérations concernées</h2></div>
            <div class="bea-rc-form">
              <bea-rc-operations [(lignes)]="operations" [tente]="tente()" [principal]="racineValide()"
                                 [regle]="regle()" [devises]="store.devises()" [motifId]="motifId()" />
              @if (regroupement()) {
                <label>Justification du regroupement multi-clients
                  @if (multiClients()) { <em>*</em> }
                  <textarea [value]="justification()" (input)="justification.set($any($event.target).value)" maxlength="4000" rows="2"
                            [class.is-invalid]="tente() && multiClients() && !justification().trim()"
                            placeholder="Obligatoire si les opérations concernent plusieurs clients (même fait, même fraude…)"></textarea>
                  @if (!store.config()?.parametres?.regroupement_multi_clients_autorise) {
                    <span class="bea-rc-hint">La banque n’autorise pas le regroupement de plusieurs clients : créez un dossier par client.</span>
                  }
                </label>
              }
              <p class="bea-rc-hint">Nombreuses opérations : enregistrez la réclamation, puis importez le fichier Excel depuis la fiche (modèle téléchargeable).</p>
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
  readonly aujourdhui = aujourdhui();
  readonly busy = signal(false);
  readonly tente = signal(false);
  readonly recherche = signal(false);
  readonly client = signal<ApercuClient | null>(null);
  readonly classement = signal<Classement>({ ...CLASSEMENT_VIDE });
  readonly operations = signal<OperationSaisie[]>([]);
  readonly justification = signal('');
  private readonly racine = signal('');
  readonly regroupement = computed(() => this.operations().some((l) => l.client_racine.trim() || l.compte_reference.trim()));
  readonly multiClients = computed(() => clientsSaisis(this.operations(), this.racine().trim() || null) > 1);
  private readonly canal = signal('');
  private readonly agenceReception = signal('');
  readonly motifId = computed(() => classementCorps(this.classement())['motif_id']);
  readonly regle = computed(() => this.store.regle(this.motifId()));
  readonly racineValide = computed(() => (/^\d{6}$/.test(this.racine().trim()) ? this.racine().trim() : null));
  private initial = '';

  readonly form = this.fb.nonNullable.group({
    date_reclamation: [aujourdhui(), Validators.required],
    canal_id: ['', Validators.required],
    reception_differente: [false],
    date_premiere_reception: [maintenantLocal()],
    unite_reception_id: ['', Validators.required],
    agence_reception_id: [''],
    niveau_concerne: ['SERVICE' as 'SERVICE' | 'DEPARTEMENT'],
    org_departement_id: [''],
    org_service_id: [''],
    client_agence_id: [''],
    priorite: ['NORMALE'],
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
    client_adresse: [''],
    objet: ['', Validators.required],
    description: ['', Validators.required],
  });

  readonly unitesReception = computed(() => this.store.unitesReception());
  /** Unité du circuit déduite : seule unité de l'agent, unité de l'agence de réception, sinon Service Réclamations. */
  readonly uniteDeduite = computed(() => {
    const unites = this.unitesReception();
    if (unites.length === 1) return unites[0].id;
    const agence = this.agenceReception();
    const parAgence = agence ? unites.filter((u) => u.agence_id === agence) : [];
    if (parAgence.length === 1) return parAgence[0].id;
    const acces = this.store.config()?.acces;
    const miennes = unites.filter((u) => acces?.unites.includes(u.id));
    if (miennes.length === 1) return miennes[0].id;
    if (acces?.membre_service_central) return unites.find((u) => u.est_service_reclamations)?.id ?? null;
    return null;
  });
  readonly uniteAChoisir = computed(() => this.unitesReception().length > 1 && !this.uniteDeduite());
  readonly telephone = computed(() => this.store.refs('CANAL', true).find((c) => c.id === this.canal())?.code === 'TELEPHONE');

  readonly hasUnsavedChanges = unsavedChanges(() => !this.busy() && this.instantane() !== this.initial);

  private instantane(): string {
    return JSON.stringify([this.form.getRawValue(), this.classement(), this.operations(), this.justification()]);
  }

  ngOnInit(): void {
    this.store.charger();
    this.initial = this.instantane();
    const c = this.form.controls;
    c.canal_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.canal.set(v));
    c.date_premiere_reception.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => {
      if (!c.appel.controls.appel_le.dirty) c.appel.controls.appel_le.setValue(v, { emitEvent: false });
    });
    c.client_racine.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => {
      this.client.set(null);
      this.racine.set(v);
    });
    c.agence_reception_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((v) => this.agenceReception.set(v));
    c.niveau_concerne.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((n) => {
      if (n === 'DEPARTEMENT') c.org_service_id.setValue('');
      else c.org_departement_id.setValue('');
    });
  }

  /** Unité du circuit renseignée automatiquement ; choix manuel seulement si elle ne peut pas être déduite. */
  private readonly preselection = effect(() => {
    const id = this.uniteDeduite();
    const ctl = this.form.controls.unite_reception_id;
    if (id && !ctl.dirty && ctl.value !== id) {
      const vierge = this.instantane() === this.initial;
      ctl.setValue(id);
      if (vierge) this.initial = this.instantane();
    }
  });

  invalide(nom: 'date_reclamation' | 'canal_id' | 'unite_reception_id' | 'client_nom' | 'objet' | 'description' | 'client_racine'): boolean {
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
    const erreur = !v.unite_reception_id && !this.uniteAChoisir()
      ? 'Vous n’êtes rattaché à aucune unité Réclamations : demandez à l’administrateur du module de vous rattacher à votre agence ou service.'
      : this.form.invalid
      ? 'Vérifiez les champs signalés en rouge.'
      : classementErreur(this.classement()) ?? operationsErreur(this.operations(), this.regle())
        ?? (v.niveau_concerne === 'SERVICE' && !v.org_service_id ? 'Indiquez le service concerné.' : null)
        ?? (v.niveau_concerne === 'DEPARTEMENT' && !v.org_departement_id ? 'Indiquez le département concerné.' : null)
        ?? (this.multiClients() && !this.justification().trim()
          ? 'Les opérations concernent plusieurs clients : justifiez le regroupement dans un même dossier.' : null);
    if (erreur) {
      this.feedback.warning({ title: 'Champs à corriger', message: erreur });
      return;
    }
    const premiere = v.reception_differente ? depuisSaisieLocale(v.date_premiere_reception) : null;
    if (v.reception_differente && (!premiere || v.date_premiere_reception.slice(0, 10) < v.date_reclamation)) {
      this.feedback.warning({ title: 'Date invalide', message: 'La réception par la banque ne peut pas précéder la date de la réclamation.' });
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
      date_reclamation: v.date_reclamation, date_premiere_reception: premiere,
      canal_id: v.canal_id, unite_reception_id: v.unite_reception_id, appel,
      client_agence_id: v.client_agence_id || null, agence_reception_id: v.agence_reception_id || null,
      org_departement_id: v.niveau_concerne === 'DEPARTEMENT' ? v.org_departement_id || null : null,
      org_service_id: v.niveau_concerne === 'SERVICE' ? v.org_service_id || null : null,
      priorite: v.priorite,
      client_racine: texte(v.client_racine), client_categorie: v.client_categorie || null, client_nom: v.client_nom.trim(),
      client_telephone: texte(v.client_telephone), client_email: texte(v.client_email), client_adresse: texte(v.client_adresse),
      objet: v.objet.trim(), description: v.description.trim(),
      ...classementCorps(this.classement()),
      operations: operationsCorps(this.operations()),
      justification_regroupement: texte(this.justification()),
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
            ...(d.nb_operations ? [{ label: 'Opérations', value: String(d.nb_operations) }] : []),
          ],
        }),
        errorTitle: 'Enregistrement refusé',
        errorHint: 'Vos données saisies ont été conservées.',
      })
      .subscribe((d) => {
        this.initial = this.instantane();
        void this.router.navigate(['/reclamations/dossiers', d.id], { queryParams: { onglet: 'documents' } });
      });
  }
}
