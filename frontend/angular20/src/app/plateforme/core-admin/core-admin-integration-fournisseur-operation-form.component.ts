import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { AbstractControl, FormArray, FormBuilder, FormGroup, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { estAccesRefuse, messageErreur, sansSecret, texteOuNull, uneLigne } from './core-admin-integration-clients.models';
import {
  AUCUN_APPEL,
  cheminValide,
  codesReponse,
  lireSchema,
  MECANISMES_AUTH,
  MecanismeAuth,
  MethodeHttp,
  OperationDetail,
  OperationManuelleSaisie,
  placeholders,
  schemaJson,
} from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { ACCES_REFUSE_FOURNISSEURS, BANDEAU_AUCUN_APPEL } from './core-admin-integration-fournisseurs.component';
import { squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

const NOM_PARAMETRE = /^[A-Za-z0-9_.\-[\]]{1,100}$/;
const NOM_ENTETE = /^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,100}$/;
const ENTETES_RESERVES = new Set(['authorization', 'proxy-authorization', 'cookie', 'set-cookie', 'host', 'content-length']);
const SANS_CORPS: readonly MethodeHttp[] = ['GET', 'HEAD', 'DELETE', 'OPTIONS'];

interface LigneParametre {
  nom: string;
  emplacement: 'path' | 'query';
  requis: boolean;
  type: string;
  description: string;
}

interface LigneEntete {
  nom: string;
  requis: boolean;
  description: string;
}

function codesValides(control: AbstractControl<string | null>): ValidationErrors | null {
  return codesReponse(control.value ?? '') ? null : { codes: true };
}

function enteteValide(control: AbstractControl<string | null>): ValidationErrors | null {
  const v = (control.value ?? '').trim();
  if (!v) return null;
  if (!NOM_ENTETE.test(v)) return { entete: true };
  return ENTETES_RESERVES.has(v.toLowerCase()) ? { reserve: true } : null;
}

@Component({
  selector: 'bea-core-admin-integration-fournisseur-operation-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <p class="bea-admin-kicker">
            <a routerLink="/admin/integrations/fournisseurs">Fournisseurs externes</a> ›
            <a [routerLink]="['/admin/integrations/fournisseurs', fid]" [queryParams]="{ onglet: 'operations' }">Fournisseur</a>
          </p>
          <h1>{{ op() ? 'Modifier l’opération manuelle' : 'Nouvelle opération manuelle' }}</h1>
          <p>Description d'une opération du fournisseur, saisie à la main. Rien n'est vérifié auprès du fournisseur.</p>
        </div>
      </header>

      ${BANDEAU_AUCUN_APPEL}

      @if (chargement()) {
        ${squelette('Chargement de l’opération…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_FOURNISSEURS}
      } @else if (erreurChargement(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
      } @else {
        <form class="bea-integ-form" [formGroup]="form" (ngSubmit)="enregistrer()" novalidate>
          <p class="bea-integ-help">Les champs marqués <abbr class="bea-integ-req" title="obligatoire">*</abbr> sont obligatoires. Aucune valeur secrète n'est saisie.</p>
          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="op-s1">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">1</span>
              <div><h2 id="op-s1">Opération</h2><p>Méthode, chemin relatif à l'URL de base et réponses attendues.</p></div>
            </div>
            <div class="bea-integ-grid2">
              <label class="bea-admin-field">
                <span>Nom<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <input type="text" formControlName="nom" maxlength="200" [attr.aria-invalid]="!!erreur('nom')" aria-describedby="op-nom-err" />
                @if (erreur('nom'); as m) { <span id="op-nom-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field">
                <span>Méthode<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <select formControlName="methode" aria-describedby="op-methode-aide">
                  @for (m of methodes; track m) { <option [value]="m">{{ m }}</option> }
                </select>
                <span id="op-methode-aide" class="bea-integ-help">Seules GET et HEAD pourront être testées.</span>
              </label>
              <label class="bea-admin-field">
                <span>Chemin relatif<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <input type="text" formControlName="chemin" maxlength="300" placeholder="/clients/{id}" autocomplete="off"
                       [attr.aria-invalid]="!!erreur('chemin')" aria-describedby="op-chemin-aide op-chemin-err" />
                <span id="op-chemin-aide" class="bea-integ-help">Relatif à l'URL de base ; chaque {{ '{' }}paramètre{{ '}' }} doit être déclaré en « path ».</span>
                @if (erreur('chemin'); as m) { <span id="op-chemin-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field">
                <span>Codes de réponse attendus<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <input type="text" formControlName="codes" maxlength="80" placeholder="200, 404" [attr.aria-invalid]="!!erreur('codes')" aria-describedby="op-codes-err" />
                @if (erreur('codes'); as m) { <span id="op-codes-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field bea-integ-full">
                <span>Description</span>
                <textarea formControlName="description" rows="2" maxlength="4000" [attr.aria-invalid]="!!erreur('description')" aria-describedby="op-desc-err"></textarea>
                @if (erreur('description'); as m) { <span id="op-desc-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="op-s2">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">2</span>
              <div><h2 id="op-s2">Authentification déclarée</h2><p>Le mécanisme seulement : aucune clé, aucun mot de passe, aucun jeton n'est saisi. Toute authentification rend l'opération non testable tant qu'aucun coffre de secrets n'est approuvé.</p></div>
            </div>
            <div class="bea-integ-grid2">
              <label class="bea-admin-field">
                <span>Mécanisme</span>
                <select formControlName="mecanisme_auth">
                  @for (m of mecanismes; track m.code) { <option [value]="m.code">{{ m.libelle }}</option> }
                </select>
              </label>
              @if (form.controls.mecanisme_auth.value.startsWith('api_key')) {
                <label class="bea-admin-field">
                  <span>Nom de l'en-tête / du paramètre de la clé<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                  <input type="text" formControlName="nom_cle_api" maxlength="100" placeholder="X-API-Key" autocomplete="off"
                         [attr.aria-invalid]="!!erreur('nom_cle_api')" aria-describedby="op-cle-err" />
                  @if (erreur('nom_cle_api'); as m) { <span id="op-cle-err" class="bea-integ-error" role="alert">{{ m }}</span> }
                </label>
              }
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="op-s3">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">3</span>
              <div><h2 id="op-s3">Paramètres</h2><p>Paramètres de chemin et de requête ; ceux du chemin sont toujours requis.</p></div>
            </div>
            <div formArrayName="parametres">
              @for (p of parametres.controls; track p; let i = $index) {
                <div class="bea-admin-grid" [formGroupName]="i">
                  <label class="bea-admin-field"><span>Nom</span><input type="text" formControlName="nom" maxlength="100" /></label>
                  <label class="bea-admin-field">
                    <span>Emplacement</span>
                    <select formControlName="emplacement"><option value="path">path</option><option value="query">query</option></select>
                  </label>
                  <label class="bea-admin-field">
                    <span>Type</span>
                    <select formControlName="type">
                      @for (t of types; track t) { <option [value]="t">{{ t }}</option> }
                    </select>
                  </label>
                  <label class="bea-admin-field"><span>Requis</span><span><input type="checkbox" formControlName="requis" /> Oui</span></label>
                  <label class="bea-admin-field"><span>Description</span><input type="text" formControlName="description" maxlength="500" /></label>
                  <div class="bea-admin-toolbar__actions">
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="parametres.removeAt(i); form.markAsDirty()">Retirer</button>
                  </div>
                  @if (p.invalid && p.touched) { <span class="bea-integ-error" role="alert">Nom invalide (lettres, chiffres, _ . - [ ]) ou description sensible.</span> }
                </div>
              }
            </div>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="parametres.length >= 50" (click)="ajouterParametre()">Ajouter un paramètre</button>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="op-s4">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">4</span>
              <div><h2 id="op-s4">En-têtes</h2><p>Authorization, Cookie, Host… sont réservés : déclarez l'authentification avec le mécanisme dédié.</p></div>
            </div>
            <div formArrayName="entetes">
              @for (h of entetes.controls; track h; let i = $index) {
                <div class="bea-admin-grid" [formGroupName]="i">
                  <label class="bea-admin-field"><span>Nom</span><input type="text" formControlName="nom" maxlength="100" /></label>
                  <label class="bea-admin-field"><span>Requis</span><span><input type="checkbox" formControlName="requis" /> Oui</span></label>
                  <label class="bea-admin-field"><span>Description</span><input type="text" formControlName="description" maxlength="500" /></label>
                  <div class="bea-admin-toolbar__actions">
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="entetes.removeAt(i); form.markAsDirty()">Retirer</button>
                  </div>
                  @if (h.get('nom')?.errors?.['reserve']) { <span class="bea-integ-error" role="alert">En-tête réservé.</span> }
                  @else if (h.invalid && h.touched) { <span class="bea-integ-error" role="alert">Nom d'en-tête invalide.</span> }
                </div>
              }
            </div>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="entetes.length >= 30" (click)="ajouterEntete()">Ajouter un en-tête</button>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="op-s5">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">5</span>
              <div><h2 id="op-s5">Schémas (JSON Schema, facultatifs)</h2><p>Objet JSON, 64 Ko maximum, sans <code>$ref</code>. Les exemples doivent être des valeurs fictives.</p></div>
            </div>
            <div class="bea-integ-grid2">
              @if (!sansCorps()) {
                <label class="bea-admin-field">
                  <span>Corps de requête</span>
                  <textarea formControlName="corps_schema" rows="6" spellcheck="false" class="bea-integ-path"
                            [attr.aria-invalid]="!!erreur('corps_schema')" aria-describedby="op-corps-err"></textarea>
                  @if (erreur('corps_schema'); as m) { <span id="op-corps-err" class="bea-integ-error" role="alert">{{ m }}</span> }
                </label>
              }
              <label class="bea-admin-field">
                <span>Réponse (premier code 2xx)</span>
                <textarea formControlName="reponse_schema" rows="6" spellcheck="false" class="bea-integ-path"
                          [attr.aria-invalid]="!!erreur('reponse_schema')" aria-describedby="op-rep-err"></textarea>
                @if (erreur('reponse_schema'); as m) { <span id="op-rep-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
              <label class="bea-admin-field bea-integ-full">
                <span>Notes</span>
                <textarea formControlName="notes" rows="2" maxlength="4000" [attr.aria-invalid]="!!erreur('notes')" aria-describedby="op-notes-err"></textarea>
                @if (erreur('notes'); as m) { <span id="op-notes-err" class="bea-integ-error" role="alert">{{ m }}</span> }
              </label>
            </div>
          </section>

          @if (erreurCoherence(); as e) {
            <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><bea-admin-icon name="error" /><p>{{ e }}</p></div>
          }

          <div class="bea-integ-form-actions">
            <span class="bea-integ-form-actions__hint" [attr.data-dirty]="form.dirty">
              {{ form.dirty ? 'Modifications non enregistrées' : 'Aucune modification' }}
            </span>
            <a class="bea-admin-btn bea-admin-btn--ghost" [routerLink]="retour()">Annuler</a>
            <button type="submit" class="bea-admin-btn" [disabled]="enregistrement()" [attr.aria-busy]="enregistrement()">
              @if (enregistrement()) { <span class="bea-integ-spinner" aria-hidden="true"></span> }
              {{ enregistrement() ? 'Enregistrement…' : op() ? 'Enregistrer' : 'Créer l’opération' }}
            </button>
          </div>
        </form>
      }
    </section>
  `,
})
export class CoreAdminIntegrationFournisseurOperationFormComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(
    () => this.form.dirty && !this.enregistrement(),
    () => this.form,
  );
  private readonly service = inject(CoreAdminIntegrationFournisseursService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly methodes: MethodeHttp[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
  readonly types = ['string', 'integer', 'number', 'boolean', 'array', 'object'];
  readonly mecanismes = MECANISMES_AUTH;

  readonly chargement = signal(false);
  readonly enregistrement = signal(false);
  readonly accesRefuse = signal(false);
  readonly erreurChargement = signal<string | null>(null);
  readonly erreurCoherence = signal<string | null>(null);
  readonly op = signal<OperationDetail | null>(null);

  readonly form = this.fb.group({
    nom: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(200), uneLigne, sansSecret]),
    methode: this.fb.nonNullable.control<MethodeHttp>('GET'),
    chemin: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(300), cheminValide]),
    codes: this.fb.nonNullable.control('200', [codesValides]),
    mecanisme_auth: this.fb.nonNullable.control<MecanismeAuth>('non_precise'),
    nom_cle_api: this.fb.nonNullable.control('', [Validators.maxLength(100), enteteValide]),
    description: this.fb.nonNullable.control('', [Validators.maxLength(4000), sansSecret]),
    parametres: this.fb.array<FormGroup>([]),
    entetes: this.fb.array<FormGroup>([]),
    corps_schema: this.fb.nonNullable.control('', [schemaJson]),
    reponse_schema: this.fb.nonNullable.control('', [schemaJson]),
    notes: this.fb.nonNullable.control('', [Validators.maxLength(4000), sansSecret]),
  });

  fid = '';

  get parametres(): FormArray {
    return this.form.controls.parametres as FormArray;
  }

  get entetes(): FormArray {
    return this.form.controls.entetes as FormArray;
  }

  ngOnInit(): void {
    this.fid = this.route.snapshot.paramMap.get('id') ?? '';
    const opId = this.route.snapshot.paramMap.get('opId');
    if (!opId) return;
    this.chargement.set(true);
    this.service.operation(this.fid, opId).subscribe({
      next: (o) => {
        if (o.origine !== 'manuelle' || o.statut !== 'active') {
          this.erreurChargement.set('Seule une opération manuelle active est modifiable ; une opération importée se met à jour par un nouvel import.');
        } else {
          this.remplir(o);
        }
        this.chargement.set(false);
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreurChargement.set(messageErreur(err, 'Opération introuvable.'));
        this.chargement.set(false);
      },
    });
  }

  groupeParametre(p?: { nom?: string; emplacement?: string; requis?: boolean; type?: string; description?: string | null }) {
    return this.fb.nonNullable.group({
      nom: this.fb.nonNullable.control(p?.nom ?? '', [Validators.required, Validators.pattern(NOM_PARAMETRE)]),
      emplacement: this.fb.nonNullable.control<'path' | 'query'>(p?.emplacement === 'path' ? 'path' : 'query'),
      requis: this.fb.nonNullable.control(!!p?.requis),
      type: this.fb.nonNullable.control(p?.type ?? 'string'),
      description: this.fb.nonNullable.control(p?.description ?? '', [Validators.maxLength(500), uneLigne, sansSecret]),
    });
  }

  groupeEntete(h?: { nom?: string; requis?: boolean; description?: string | null }) {
    return this.fb.nonNullable.group({
      nom: this.fb.nonNullable.control(h?.nom ?? '', [Validators.required, enteteValide]),
      requis: this.fb.nonNullable.control(!!h?.requis),
      description: this.fb.nonNullable.control(h?.description ?? '', [Validators.maxLength(500), uneLigne, sansSecret]),
    });
  }

  ajouterParametre(): void {
    this.parametres.push(this.groupeParametre());
    this.form.markAsDirty();
  }

  ajouterEntete(): void {
    this.entetes.push(this.groupeEntete());
    this.form.markAsDirty();
  }

  sansCorps(): boolean {
    return SANS_CORPS.includes(this.form.controls.methode.value);
  }

  retour(): unknown[] {
    const o = this.op();
    return o ? ['/admin/integrations/fournisseurs', this.fid, 'operations', o.id] : ['/admin/integrations/fournisseurs', this.fid];
  }

  erreur(nom: 'nom' | 'chemin' | 'codes' | 'nom_cle_api' | 'description' | 'corps_schema' | 'reponse_schema' | 'notes'): string | null {
    const c = this.form.controls[nom];
    if (!c.errors || !(c.touched || c.dirty)) return null;
    if (c.errors['required']) return 'Champ obligatoire.';
    if (c.errors['maxlength']) return `${c.errors['maxlength'].requiredLength} caractères maximum.`;
    if (c.errors['multiligne']) return 'Une seule ligne attendue.';
    if (c.errors['secret']) return 'Ne saisissez aucun secret (mot de passe, jeton, clé).';
    if (c.errors['chemin']) return 'Chemin relatif invalide (commence par /, sans espace, ?, # ni ..).';
    if (c.errors['codes']) return 'Codes HTTP à 3 chiffres entre 100 et 599, séparés par des virgules.';
    if (c.errors['entete']) return 'Nom invalide.';
    if (c.errors['reserve']) return 'En-tête réservé.';
    if (c.errors['schema']) return c.errors['schema'];
    return 'Valeur invalide.';
  }

  /** Mêmes règles de cohérence que le serveur, pour un retour immédiat ; le serveur reste seul juge. */
  coherence(saisie: OperationManuelleSaisie): string | null {
    const places = placeholders(saisie.chemin);
    const chemin = saisie.parametres.filter((p) => p.emplacement === 'path').map((p) => p.nom);
    if (new Set(chemin).size !== chemin.length || places.length !== chemin.length || places.some((p) => !chemin.includes(p))) {
      return 'Chaque {paramètre} du chemin doit être déclaré une fois, en emplacement « path ».';
    }
    const cles = saisie.parametres.map((p) => `${p.emplacement}:${p.nom}`);
    if (new Set(cles).size !== cles.length) return 'Paramètre déclaré deux fois.';
    const noms = saisie.entetes.map((e) => e.nom.toLowerCase());
    if (new Set(noms).size !== noms.length) return 'En-tête déclaré deux fois.';
    if (saisie.mecanisme_auth.startsWith('api_key') && !saisie.nom_cle_api) return 'Nom de l’en-tête ou du paramètre de la clé d’API requis.';
    return null;
  }

  saisie(): OperationManuelleSaisie {
    const v = this.form.getRawValue();
    const apiKey = v.mecanisme_auth.startsWith('api_key');
    return {
      nom: v.nom.trim(),
      description: texteOuNull(v.description),
      methode: v.methode,
      chemin: v.chemin.trim(),
      parametres: (v.parametres as LigneParametre[]).map((p) => ({
        nom: p.nom.trim(),
        emplacement: p.emplacement,
        requis: p.requis || p.emplacement === 'path',
        type: p.type,
        description: texteOuNull(p.description),
      })),
      entetes: (v.entetes as LigneEntete[]).map((h) => ({
        nom: h.nom.trim(),
        requis: h.requis,
        description: texteOuNull(h.description),
      })),
      corps_schema: SANS_CORPS.includes(v.methode) ? null : lireSchema(v.corps_schema).valeur,
      reponse_schema: lireSchema(v.reponse_schema).valeur,
      mecanisme_auth: v.mecanisme_auth,
      nom_cle_api: apiKey ? texteOuNull(v.nom_cle_api) : null,
      codes_reponse: codesReponse(v.codes) ?? [200],
      notes: texteOuNull(v.notes),
    };
  }

  async enregistrer(): Promise<void> {
    if (this.enregistrement()) return;
    this.erreurCoherence.set(null);
    if (this.sansCorps()) this.form.controls.corps_schema.setValue('');
    if (this.form.invalid || !this.form.controls.nom.value.trim()) {
      this.form.markAllAsTouched();
      if (!this.form.controls.nom.value.trim()) this.form.controls.nom.setErrors({ required: true });
      return;
    }
    const saisie = this.saisie();
    const incoherence = this.coherence(saisie);
    if (incoherence) {
      this.erreurCoherence.set(incoherence);
      return;
    }
    const o = this.op();
    const ok = await this.dialogs.confirm({
      title: o ? 'Confirmer la modification' : 'Confirmer la création',
      message: `${o ? 'Enregistrer' : 'Créer'} ${saisie.methode} ${saisie.chemin} ? Aucun appel ne sera effectué vers le fournisseur.`,
      confirmLabel: o ? 'Enregistrer' : 'Créer',
    });
    if (!ok) return;
    this.enregistrement.set(true);
    const appel = o ? this.service.modifierOperation(this.fid, o.id, o.revision, saisie) : this.service.creerOperation(this.fid, saisie);
    appel.subscribe({
      next: (r) => {
        this.form.markAsPristine();
        this.enregistrement.set(false);
        void this.dialogs
          .success(`${r.methode} ${r.chemin} enregistrée. ${AUCUN_APPEL}`)
          .then(() => void this.router.navigate(['/admin/integrations/fournisseurs', this.fid, 'operations', r.id]));
      },
      error: (err) => {
        this.enregistrement.set(false);
        void this.dialogs.error(messageErreur(err, 'Enregistrement impossible.'));
      },
    });
  }

  private remplir(o: OperationDetail): void {
    this.op.set(o);
    const c = o.configuration ?? {};
    this.parametres.clear();
    this.entetes.clear();
    (c.parametres ?? []).forEach((p) => this.parametres.push(this.groupeParametre(p)));
    (c.entetes ?? []).forEach((h) => this.entetes.push(this.groupeEntete(h)));
    this.form.patchValue({
      nom: c.nom ?? o.nom ?? '',
      methode: (c.methode ?? o.methode) as MethodeHttp,
      chemin: c.chemin ?? o.chemin,
      codes: (c.codes_reponse ?? [200]).join(', '),
      mecanisme_auth: c.mecanisme_auth ?? 'non_precise',
      nom_cle_api: c.nom_cle_api ?? '',
      description: c.description ?? '',
      corps_schema: c.corps_schema ? JSON.stringify(c.corps_schema, null, 2) : '',
      reponse_schema: c.reponse_schema ? JSON.stringify(c.reponse_schema, null, 2) : '',
      notes: c.notes ?? '',
    });
    this.form.markAsPristine();
  }
}
