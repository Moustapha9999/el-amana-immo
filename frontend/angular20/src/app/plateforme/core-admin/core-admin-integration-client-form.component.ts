import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { OrgEntiteSelectComponent } from '../../core/org/org-entite-select.component';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import {
  clientStatutLabel,
  estAccesRefuse,
  IntegrationClientFiche,
  IntegrationClientSaisie,
  IntegrationClientStatut,
  IntegrationEnvironnement,
  messageErreur,
  sansSecret,
  texteOuNull,
  uneLigne,
} from './core-admin-integration-clients.models';
import { CoreAdminIntegrationClientsService } from './core-admin-integration-clients.service';
import { ACCES_REFUSE_CLIENTS } from './core-admin-integration-clients.component';
import { squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

@Component({
  selector: 'bea-core-admin-integration-client-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, OrgEntiteSelectComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations/clients">Applications clientes</a></p>
          <h1>{{ creation() ? 'Nouvelle application cliente' : 'Modifier ' + (fiche()?.nom ?? 'l’application') }}</h1>
          <p>Fiche de configuration — aucune clé, aucun secret, aucun identifiant d'authentification n'est créé.</p>
        </div>
      </header>

      @if (chargement()) {
        ${squelette('Chargement de la fiche…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_CLIENTS}
      } @else if (erreurChargement(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/clients">Retour à la liste</a>
      } @else if (fiche()?.statut === 'archivee') {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>Application archivée : la fiche n'est plus modifiable.</p></div>
      } @else {
        <form class="bea-integ-form" [formGroup]="form" (ngSubmit)="enregistrer()" novalidate aria-describedby="client-form-obligatoires">
          <p id="client-form-obligatoires" class="bea-integ-help">Les champs marqués <abbr class="bea-integ-req" title="obligatoire">*</abbr> sont obligatoires.</p>
          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="client-s1">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">1</span>
              <div><h2 id="client-s1">Identité</h2><p>Nom affiché dans le Studio et environnement cible de la configuration.</p></div>
            </div>
            <div class="bea-integ-grid3">
              <label class="bea-admin-field">
                <span>Nom<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <input type="text" formControlName="nom" maxlength="120" autocomplete="off"
                       [attr.aria-invalid]="!!erreurChamp('nom')" aria-describedby="client-nom-err" />
                @if (erreurChamp('nom'); as m) { <span id="client-nom-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field">
                <span>Environnement<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <select formControlName="environnement" aria-describedby="client-env-aide">
                  <option value="DEV">DEV</option>
                  <option value="TEST">TEST</option>
                </select>
                <span id="client-env-aide" class="bea-integ-help">
                  {{ creation() ? 'Choisi à la création ; verrouillé dès qu’une opération est soumise ou décidée.' : 'Verrouillé dès qu’une opération a été soumise ou décidée.' }}
                </span>
              </label>
              <label class="bea-admin-field">
                <span>Statut</span>
                <select formControlName="statut" aria-describedby="client-statut-aide">
                  @for (s of statutsPossibles(); track s) {
                    <option [value]="s">{{ statutLabel(s) }}</option>
                  }
                </select>
                <span id="client-statut-aide" class="bea-integ-help">« Active » = fiche active, pas une application authentifiée.</span>
              </label>
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="client-s2">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">2</span>
              <div><h2 id="client-s2">Responsabilité</h2><p>Service de l'organigramme BEA qui porte l'application, et son contact technique.</p></div>
            </div>
            <div class="bea-integ-grid2">
              <label class="bea-admin-field">
                <span>Service responsable</span>
                <bea-org-entite-select formControlName="org_entite_id" ariaLabel="Service responsable" />
                <span class="bea-integ-help">Obligatoire pour activer la fiche.</span>
              </label>
              <label class="bea-admin-field">
                <span>Contact technique</span>
                <input type="text" formControlName="contact_technique" maxlength="160" placeholder="Nom ou fonction (pas de mot de passe)"
                       [attr.aria-invalid]="!!erreurChamp('contact_technique')" aria-describedby="client-contact-err" />
                @if (erreurChamp('contact_technique'); as m) { <span id="client-contact-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="client-s3">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">3</span>
              <div><h2 id="client-s3">Usage</h2><p>À quoi servira l'application : utilisé lors de l'examen des demandes de droits.</p></div>
            </div>
            <div class="bea-integ-grid2">
              <label class="bea-admin-field bea-integ-full">
                <span>Description</span>
                <textarea formControlName="description" rows="3" maxlength="2000"
                          [attr.aria-invalid]="!!erreurChamp('description')" aria-describedby="client-desc-err"></textarea>
                @if (erreurChamp('description'); as m) { <span id="client-desc-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field bea-integ-full">
                <span>Finalité</span>
                <textarea formControlName="finalite" rows="3" maxlength="2000" placeholder="Usage prévu, données consultées, bénéficiaires"
                          [attr.aria-invalid]="!!erreurChamp('finalite')" aria-describedby="client-fin-aide client-fin-err"></textarea>
                <span id="client-fin-aide" class="bea-integ-help">Obligatoire pour activer la fiche.</span>
                @if (erreurChamp('finalite'); as m) { <span id="client-fin-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="client-s4">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">4</span>
              <div><h2 id="client-s4">Notes d'administration</h2><p>Visibles des administrateurs du Studio uniquement. Aucun secret.</p></div>
            </div>
            <label class="bea-admin-field">
              <span>Notes</span>
              <textarea formControlName="notes" rows="3" maxlength="4000"
                        [attr.aria-invalid]="!!erreurChamp('notes')" aria-describedby="client-notes-err"></textarea>
              @if (erreurChamp('notes'); as m) { <span id="client-notes-err" class="bea-integ-error" role="alert">{{ m }}</span> }
            </label>
          </section>

          @if (erreurServeur(); as e) {
            <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }} Vos saisies sont conservées.</p></div>
          }
          <div class="bea-integ-form-actions">
            <span class="bea-integ-form-actions__hint" [attr.data-dirty]="form.dirty">
              {{ form.dirty ? 'Modifications non enregistrées' : 'Aucune modification' }}
            </span>
            <a class="bea-admin-btn bea-admin-btn--ghost" [routerLink]="retour()">Annuler</a>
            <button type="submit" class="bea-admin-btn" [disabled]="enregistrement()" [attr.aria-busy]="enregistrement()">
              @if (enregistrement()) { <span class="bea-integ-spinner" aria-hidden="true"></span> }
              {{ enregistrement() ? 'Enregistrement…' : creation() ? 'Créer la fiche' : 'Enregistrer' }}
            </button>
          </div>
        </form>
      }
    </section>
  `,
})
export class CoreAdminIntegrationClientFormComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(
    () => this.form.dirty && !this.enregistrement(),
    () => this.form,
  );
  private readonly service = inject(CoreAdminIntegrationClientsService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly creation = signal(true);
  readonly chargement = signal(false);
  readonly enregistrement = signal(false);
  readonly accesRefuse = signal(false);
  readonly erreurChargement = signal<string | null>(null);
  readonly erreurServeur = signal<string | null>(null);
  readonly fiche = signal<IntegrationClientFiche | null>(null);
  readonly statutsPossibles = signal<IntegrationClientStatut[]>(['brouillon', 'en_preparation']);
  readonly statutLabel = clientStatutLabel;

  readonly form = this.fb.group({
    nom: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(120), uneLigne, sansSecret]),
    environnement: this.fb.nonNullable.control<IntegrationEnvironnement>('DEV', Validators.required),
    statut: this.fb.nonNullable.control<IntegrationClientStatut>('brouillon'),
    org_entite_id: this.fb.control<string | null>(null),
    contact_technique: this.fb.nonNullable.control('', [Validators.maxLength(160), uneLigne, sansSecret]),
    description: this.fb.nonNullable.control('', [Validators.maxLength(2000), sansSecret]),
    finalite: this.fb.nonNullable.control('', [Validators.maxLength(2000), sansSecret]),
    notes: this.fb.nonNullable.control('', [Validators.maxLength(4000), sansSecret]),
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    this.creation.set(!id);
    if (id) {
      this.chargement.set(true);
      this.service.fiche(id).subscribe({
        next: (f) => {
          this.remplir(f);
          this.chargement.set(false);
        },
        error: (err) => {
          this.accesRefuse.set(estAccesRefuse(err));
          this.erreurChargement.set(messageErreur(err, 'Application introuvable.'));
          this.chargement.set(false);
        },
      });
    }
  }

  retour(): unknown[] {
    const f = this.fiche();
    return f ? ['/admin/integrations/clients', f.id] : ['/admin/integrations/clients'];
  }

  erreurChamp(nom: keyof typeof this.form.controls): string | null {
    const c = this.form.controls[nom];
    if (!c.errors || !(c.touched || c.dirty)) return null;
    if (c.errors['required']) return 'Champ obligatoire.';
    if (c.errors['maxlength']) return `${c.errors['maxlength'].requiredLength} caractères maximum.`;
    if (c.errors['multiligne']) return 'Une seule ligne attendue.';
    if (c.errors['secret']) return 'Ne saisissez aucun secret (mot de passe, jeton, clé).';
    return 'Valeur invalide.';
  }

  saisie(): IntegrationClientSaisie {
    const v = this.form.getRawValue();
    return {
      nom: v.nom.trim(),
      environnement: v.environnement,
      statut: v.statut,
      org_entite_id: v.org_entite_id || null,
      contact_technique: texteOuNull(v.contact_technique),
      description: texteOuNull(v.description),
      finalite: texteOuNull(v.finalite),
      notes: texteOuNull(v.notes),
    };
  }

  async enregistrer(): Promise<void> {
    if (this.enregistrement()) return;
    if (this.form.invalid || !this.form.controls.nom.value.trim()) {
      this.form.markAllAsTouched();
      if (!this.form.controls.nom.value.trim()) this.form.controls.nom.setErrors({ required: true });
      return;
    }
    const saisie = this.saisie();
    const f = this.fiche();
    const ok = await this.dialogs.confirm({
      title: f ? 'Confirmer la modification' : 'Confirmer la création',
      message: f
        ? `Enregistrer les modifications de « ${saisie.nom} » ?`
        : `Créer la fiche « ${saisie.nom} » (${saisie.environnement}) ? Aucune clé ni aucun secret ne sera généré.`,
      confirmLabel: f ? 'Enregistrer' : 'Créer',
    });
    if (!ok) return;
    this.enregistrement.set(true);
    this.erreurServeur.set(null);
    const appel = f ? this.service.modifier(f.id, f.revision, saisie) : this.service.creer(saisie);
    appel.subscribe({
      next: (resultat) => {
        this.form.markAsPristine();
        this.enregistrement.set(false);
        void this.dialogs
          .success(f ? `« ${resultat.nom} » a été enregistrée.` : `« ${resultat.nom} » a été créée (${resultat.code}).`)
          .then(() => void this.router.navigate(['/admin/integrations/clients', resultat.id]));
      },
      error: (err) => {
        this.enregistrement.set(false);
        const message = messageErreur(err, f ? 'Enregistrement impossible.' : 'Création impossible.');
        this.erreurServeur.set(message);
        void this.dialogs.error(message);
      },
    });
  }

  private remplir(f: IntegrationClientFiche): void {
    this.fiche.set(f);
    this.statutsPossibles.set([f.statut, ...f.transitions.filter((s) => s !== 'archivee')]);
    this.form.reset({
      nom: f.nom,
      environnement: f.environnement,
      statut: f.statut,
      org_entite_id: f.entite?.id ?? null,
      contact_technique: f.contact_technique ?? '',
      description: f.description ?? '',
      finalite: f.finalite ?? '',
      notes: f.notes ?? '',
    });
  }
}
