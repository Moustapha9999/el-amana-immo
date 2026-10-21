import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { OrgEntiteSelectComponent } from '../../core/org/org-entite-select.component';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  estAccesRefuse,
  IntegrationEnvironnement,
  messageErreur,
  sansSecret,
  texteOuNull,
  uneLigne,
} from './core-admin-integration-clients.models';
import { AUCUN_APPEL, FournisseurFiche, FournisseurSaisie, urlBaseValide } from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { ACCES_REFUSE_FOURNISSEURS, BANDEAU_AUCUN_APPEL } from './core-admin-integration-fournisseurs.component';
import { squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

@Component({
  selector: 'bea-core-admin-integration-fournisseur-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, OrgEntiteSelectComponent, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations/fournisseurs">Fournisseurs externes</a></p>
          <h1>{{ creation() ? 'Nouveau fournisseur d’API' : 'Modifier ' + (fiche()?.nom ?? 'le fournisseur') }}</h1>
          <p>Fiche de configuration — aucun secret, aucune clé, aucun mot de passe n'est saisi ni stocké ici.</p>
        </div>
      </header>

      ${BANDEAU_AUCUN_APPEL}

      @if (chargement()) {
        ${squelette('Chargement de la fiche…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_FOURNISSEURS}
      } @else if (erreurChargement(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/fournisseurs">Retour à la liste</a>
      } @else if (fiche() && !fiche()!.modifiable) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert">
          <p>Fiche non modifiable au statut actuel : repassez-la « À valider » ou « Brouillon » pour la modifier.</p>
        </div>
      } @else {
        <form class="bea-integ-form" [formGroup]="form" (ngSubmit)="enregistrer()" novalidate>
          <p class="bea-integ-help">Les champs marqués <abbr class="bea-integ-req" title="obligatoire">*</abbr> sont obligatoires. Aucun secret n'est saisi ici.</p>
          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="fourn-s1">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">1</span>
              <div><h2 id="fourn-s1">Identité</h2><p>Nom du fournisseur et environnement de la documentation.</p></div>
            </div>
            <div class="bea-integ-grid2">
              <label class="bea-admin-field">
                <span>Nom<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <input type="text" formControlName="nom" maxlength="120" autocomplete="off"
                       [attr.aria-invalid]="!!erreurChamp('nom')" aria-describedby="fourn-nom-err" />
                @if (erreurChamp('nom'); as m) { <span id="fourn-nom-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field">
                <span>Environnement<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <select formControlName="environnement" aria-describedby="fourn-env-aide">
                  <option value="DEV">DEV</option>
                  <option value="TEST">TEST</option>
                </select>
                <span id="fourn-env-aide" class="bea-integ-help">TEST exige une URL https. Verrouillé dès qu'une spécification ou une opération existe.</span>
              </label>
              <label class="bea-admin-field bea-integ-full">
                <span>Description</span>
                <textarea formControlName="description" rows="3" maxlength="2000"
                          [attr.aria-invalid]="!!erreurChamp('description')" aria-describedby="fourn-desc-err"></textarea>
                @if (erreurChamp('description'); as m) { <span id="fourn-desc-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="fourn-s2">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">2</span>
              <div><h2 id="fourn-s2">Responsabilité</h2><p>Qui porte la relation chez BEA et qui contacter chez le fournisseur.</p></div>
            </div>
            <div class="bea-integ-grid3">
              <label class="bea-admin-field">
                <span>Service responsable</span>
                <bea-org-entite-select formControlName="org_entite_id" ariaLabel="Service responsable" />
                <span class="bea-integ-help">Organigramme BEA — obligatoire pour la validation.</span>
              </label>
              <label class="bea-admin-field">
                <span>Responsable interne</span>
                <input type="text" formControlName="responsable_interne" maxlength="160"
                       [attr.aria-invalid]="!!erreurChamp('responsable_interne')" aria-describedby="fourn-resp-err" />
                @if (erreurChamp('responsable_interne'); as m) { <span id="fourn-resp-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field">
                <span>Contact technique (fournisseur)</span>
                <input type="text" formControlName="contact_technique" maxlength="160" placeholder="Nom ou fonction (pas de mot de passe)"
                       [attr.aria-invalid]="!!erreurChamp('contact_technique')" aria-describedby="fourn-contact-err" />
                @if (erreurChamp('contact_technique'); as m) { <span id="fourn-contact-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="fourn-s3">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">3</span>
              <div><h2 id="fourn-s3">Point d'accès déclaré</h2><p>Métadonnée documentaire : les tests passent uniquement par une destination TEST approuvée.</p></div>
            </div>
            <label class="bea-admin-field">
              <span>URL de base déclarée</span>
              <input type="url" formControlName="url_base" maxlength="300" placeholder="https://api.fournisseur.example/v1" autocomplete="off"
                     [attr.aria-invalid]="!!erreurChamp('url_base')" aria-describedby="fourn-url-aide fourn-url-err" />
              <span id="fourn-url-aide" class="bea-integ-help">Enregistrée telle quelle, jamais contactée. Sans identifiant, paramètre ni fragment.</span>
              @if (erreurChamp('url_base'); as m) { <span id="fourn-url-err" class="bea-integ-error" role="alert">{{ m }}</span> }
            </label>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="fourn-s4">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">4</span>
              <div><h2 id="fourn-s4">Documentation et notes</h2><p>Références, procédure d'obtention des accès, remarques d'administration.</p></div>
            </div>
            <div class="bea-integ-grid2">
              <label class="bea-admin-field">
                <span>Documentation</span>
                <textarea formControlName="documentation" rows="4" maxlength="4000"
                          [attr.aria-invalid]="!!erreurChamp('documentation')" aria-describedby="fourn-doc-err"></textarea>
                @if (erreurChamp('documentation'); as m) { <span id="fourn-doc-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field">
                <span>Notes d'administration</span>
                <textarea formControlName="notes" rows="4" maxlength="4000"
                          [attr.aria-invalid]="!!erreurChamp('notes')" aria-describedby="fourn-notes-err"></textarea>
                @if (erreurChamp('notes'); as m) { <span id="fourn-notes-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
            </div>
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
export class CoreAdminIntegrationFournisseurFormComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(
    () => this.form.dirty && !this.enregistrement(),
    () => this.form,
  );
  private readonly service = inject(CoreAdminIntegrationFournisseursService);
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
  readonly fiche = signal<FournisseurFiche | null>(null);

  readonly form = this.fb.group({
    nom: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(120), uneLigne, sansSecret]),
    environnement: this.fb.nonNullable.control<IntegrationEnvironnement>('DEV', Validators.required),
    org_entite_id: this.fb.control<string | null>(null),
    responsable_interne: this.fb.nonNullable.control('', [Validators.maxLength(160), uneLigne, sansSecret]),
    contact_technique: this.fb.nonNullable.control('', [Validators.maxLength(160), uneLigne, sansSecret]),
    url_base: this.fb.nonNullable.control('', [Validators.maxLength(300), urlBaseValide]),
    description: this.fb.nonNullable.control('', [Validators.maxLength(2000), sansSecret]),
    documentation: this.fb.nonNullable.control('', [Validators.maxLength(4000), sansSecret]),
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
          this.erreurChargement.set(messageErreur(err, 'Fournisseur introuvable.'));
          this.chargement.set(false);
        },
      });
    }
  }

  retour(): unknown[] {
    const f = this.fiche();
    return f ? ['/admin/integrations/fournisseurs', f.id] : ['/admin/integrations/fournisseurs'];
  }

  erreurChamp(nom: keyof typeof this.form.controls): string | null {
    const c = this.form.controls[nom];
    if (!c.errors || !(c.touched || c.dirty)) return null;
    if (c.errors['required']) return 'Champ obligatoire.';
    if (c.errors['maxlength']) return `${c.errors['maxlength'].requiredLength} caractères maximum.`;
    if (c.errors['multiligne']) return 'Une seule ligne attendue.';
    if (c.errors['secret']) return 'Ne saisissez aucun secret (mot de passe, jeton, clé).';
    if (c.errors['urlIdentifiants']) return 'Aucun identifiant ni mot de passe dans l’URL.';
    if (c.errors['url']) return 'URL absolue http(s) attendue, sans paramètre ni fragment.';
    return 'Valeur invalide.';
  }

  saisie(): FournisseurSaisie {
    const v = this.form.getRawValue();
    return {
      nom: v.nom.trim(),
      environnement: v.environnement,
      org_entite_id: v.org_entite_id || null,
      responsable_interne: texteOuNull(v.responsable_interne),
      contact_technique: texteOuNull(v.contact_technique),
      url_base: texteOuNull(v.url_base),
      description: texteOuNull(v.description),
      documentation: texteOuNull(v.documentation),
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
        ? `Enregistrer les modifications de « ${saisie.nom} » ? Aucune URL ne sera contactée.`
        : `Créer la fiche « ${saisie.nom} » (${saisie.environnement}) ? Aucune URL ne sera contactée.`,
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
          .success(`${f ? `« ${resultat.nom} » enregistré` : `« ${resultat.nom} » créé (${resultat.code})`}. ${AUCUN_APPEL}`)
          .then(() => void this.router.navigate(['/admin/integrations/fournisseurs', resultat.id]));
      },
      error: (err) => {
        this.enregistrement.set(false);
        const message = messageErreur(err, f ? 'Enregistrement impossible.' : 'Création impossible.');
        this.erreurServeur.set(message);
        void this.dialogs.error(message);
      },
    });
  }

  private remplir(f: FournisseurFiche): void {
    this.fiche.set(f);
    this.form.reset({
      nom: f.nom,
      environnement: f.environnement,
      org_entite_id: f.entite?.id ?? null,
      responsable_interne: f.responsable_interne ?? '',
      contact_technique: f.contact_technique ?? '',
      url_base: f.url_base ?? '',
      description: f.description ?? '',
      documentation: f.documentation ?? '',
      notes: f.notes ?? '',
    });
  }
}
