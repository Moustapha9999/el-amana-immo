import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { estAccesRefuse, messageErreur, texteOuNull, uneLigne } from './core-admin-integration-clients.models';
import { DestinationFiche, hotesDepuisTexte } from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionService } from './core-admin-integration-execution.service';
import { ACCES_REFUSE_DEST } from './core-admin-integration-destinations.component';
import { FournisseurResume, OperationResume } from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

@Component({
  selector: 'bea-core-admin-integration-destination-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations/destinations">Destinations TEST</a></p>
          <h1>{{ creation() ? 'Nouvelle destination TEST' : 'Modifier la destination' }}</h1>
          <p>Hôtes publics HTTPS uniquement. Aucun secret, aucune URL exécutable saisie ici. L’enregistrement ne déclenche aucun appel.</p>
        </div>
      </header>
      @if (chargement()) {
        ${squelette('Chargement de la destination…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_DEST}
      } @else if (erreur(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/destinations">Retour à la liste</a>
      } @else {
        <form class="bea-integ-form" [formGroup]="form" (ngSubmit)="enregistrer()" novalidate>
          <p class="bea-integ-help">Les champs marqués <abbr class="bea-integ-req" title="obligatoire">*</abbr> sont obligatoires.</p>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="dst-s1">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">1</span>
              <div><h2 id="dst-s1">Identité</h2><p>Le fournisseur devra être validé avant toute approbation de la destination.</p></div>
            </div>
            <div class="bea-integ-grid2">
              <label class="bea-admin-field">
                <span>Nom<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                <input type="text" formControlName="nom" maxlength="120" autocomplete="off"
                       [attr.aria-invalid]="invalide('nom')" aria-describedby="dst-nom-err" />
                @if (invalide('nom')) { <span id="dst-nom-err" class="bea-integ-error" role="alert">Nom obligatoire, sur une seule ligne (120 caractères maximum).</span> }
              </label>
              <label class="bea-admin-field">
                <span>Fournisseur<abbr class="bea-integ-req" title="obligatoire">*</abbr></span>
                @if (creation()) {
                  <select formControlName="fournisseur_id" (change)="chargerOperations()" [attr.aria-invalid]="invalide('fournisseur_id')" aria-describedby="dst-f-aide dst-f-err">
                    <option value="">— Choisir —</option>
                    @for (f of fournisseurs(); track f.id) {
                      <option [value]="f.id">{{ f.nom }} ({{ f.code }}) — {{ statutFournisseur(f.statut) }}</option>
                    }
                  </select>
                  <span id="dst-f-aide" class="bea-integ-help">Fournisseurs non archivés. Seul un fournisseur validé permet l’approbation.</span>
                } @else {
                  <input type="text" [value]="fiche()?.fournisseur_nom ?? ''" readonly aria-describedby="dst-f-aide" />
                  <span id="dst-f-aide" class="bea-integ-help">Le fournisseur d’une destination ne change pas.</span>
                }
                @if (invalide('fournisseur_id')) { <span id="dst-f-err" class="bea-integ-error" role="alert">Choisissez un fournisseur.</span> }
              </label>
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="dst-s2">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">2</span>
              <div><h2 id="dst-s2">Point d’accès TEST</h2><p>Environnement TEST, protocole HTTPS et port 443 imposés par le serveur.</p></div>
            </div>
            <div class="bea-integ-grid2">
              <label class="bea-admin-field bea-integ-full">
                <span>Hôtes approuvés<abbr class="bea-integ-req" title="obligatoire">*</abbr> (un par ligne)</span>
                <textarea formControlName="hotes" rows="3" maxlength="800" placeholder="api.test.example" class="bea-integ-path"
                          [attr.aria-invalid]="invalide('hotes') || !!erreurHotes()" aria-describedby="dst-h-aide dst-h-err"></textarea>
                <span id="dst-h-aide" class="bea-integ-help">Noms d’hôte publics. Interdit : localhost, adresses IP privées, métadonnées cloud. Le serveur revérifie la résolution DNS à chaque test.</span>
                @if (invalide('hotes') || erreurHotes()) { <span id="dst-h-err" class="bea-integ-error" role="alert">{{ erreurHotes() ?? 'Indiquez au moins un hôte public.' }}</span> }
              </label>
              <label class="bea-admin-field">
                <span>Méthodes autorisées</span>
                <select formControlName="methodes">
                  <option value="GET,HEAD">GET et HEAD</option>
                  <option value="GET">GET seulement</option>
                  <option value="HEAD">HEAD seulement</option>
                </select>
              </label>
              <div class="bea-admin-field">
                <span>Environnement / protocole / port</span>
                <span><span class="bea-integ-pill">TEST</span> <span class="bea-integ-pill">HTTPS</span> <span class="bea-integ-pill">443</span></span>
              </div>
            </div>
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="dst-s3">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">3</span>
              <div>
                <h2 id="dst-s3">Opérations autorisées</h2>
                <p>Restreignez la destination à certaines opérations. Si aucune n’est cochée, toutes les opérations GET/HEAD du fournisseur sont acceptées.</p>
              </div>
            </div>
            @if (!form.controls.fournisseur_id.value) {
              <p class="bea-integ-muted">Choisissez d’abord un fournisseur.</p>
            } @else if (chargementOps()) {
              <p class="bea-integ-muted" role="status">Chargement des opérations…</p>
            } @else if (erreurOps(); as e) {
              <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
            } @else if (operationsDispo().length === 0 && selection().length === 0) {
              <p class="bea-integ-muted">Aucune opération GET ou HEAD active pour ce fournisseur.</p>
            } @else {
              <fieldset class="bea-integ-checklist">
                <legend class="bea-integ-muted">{{ selection().length ? selection().length + ' opération(s) cochée(s)' : 'Aucune restriction : toutes les opérations' }}</legend>
                @for (op of operationsDispo(); track op.id) {
                  <label>
                    <input type="checkbox" [checked]="selection().includes(op.id)" (change)="basculer(op.id)" />
                    <span class="bea-integ-method" [attr.data-m]="op.methode">{{ op.methode }}</span>
                    <span class="bea-integ-path">{{ op.chemin }}</span>
                    <span class="bea-integ-muted">{{ op.origine === 'openapi' ? 'importée' : 'manuelle' }}</span>
                  </label>
                }
                @for (id of orphelines(); track id) {
                  <label>
                    <input type="checkbox" checked (change)="basculer(id)" />
                    <span class="bea-integ-muted">Opération {{ id.slice(0, 8) }}… (archivée ou hors GET/HEAD)</span>
                  </label>
                }
              </fieldset>
            }
          </section>

          <section class="bea-admin-panel bea-integ-fieldset" aria-labelledby="dst-s4">
            <div class="bea-integ-fieldset__head">
              <span class="bea-integ-fieldset__num" aria-hidden="true">4</span>
              <div><h2 id="dst-s4">Notes</h2><p>Aucun secret : ni clé, ni mot de passe, ni jeton.</p></div>
            </div>
            <label class="bea-admin-field">
              <span>Notes internes</span>
              <textarea formControlName="notes" rows="3" maxlength="4000"></textarea>
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
              {{ enregistrement() ? 'Enregistrement…' : creation() ? 'Créer la destination' : 'Enregistrer' }}
            </button>
          </div>
        </form>
      }
    </section>
  `,
})
export class CoreAdminIntegrationDestinationFormComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(() => this.form.dirty && !this.enregistrement(), () => this.form);
  private readonly service = inject(CoreAdminIntegrationExecutionService);
  private readonly fournisseursService = inject(CoreAdminIntegrationFournisseursService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly creation = signal(true);
  readonly chargement = signal(false);
  readonly enregistrement = signal(false);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly erreurServeur = signal<string | null>(null);
  readonly erreurHotes = signal<string | null>(null);
  readonly fiche = signal<DestinationFiche | null>(null);
  readonly fournisseurs = signal<FournisseurResume[]>([]);
  readonly operationsDispo = signal<OperationResume[]>([]);
  readonly selection = signal<string[]>([]);
  readonly chargementOps = signal(false);
  readonly erreurOps = signal<string | null>(null);
  readonly form = this.fb.group({
    nom: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(120), uneLigne]),
    fournisseur_id: this.fb.nonNullable.control('', [Validators.required, Validators.minLength(36)]),
    hotes: this.fb.nonNullable.control('', Validators.required),
    methodes: this.fb.nonNullable.control('GET,HEAD'),
    notes: this.fb.control(''),
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      const fourn = this.route.snapshot.queryParamMap.get('fournisseur');
      if (fourn) this.form.patchValue({ fournisseur_id: fourn });
      this.fournisseursService.lister({}, 1, 100).subscribe({
        next: (r) => this.fournisseurs.set(r.items ?? []),
        error: () => this.fournisseurs.set([]),
      });
      if (fourn) this.chargerOperations();
      return;
    }
    this.creation.set(false);
    this.chargement.set(true);
    this.service.ficheDestination(id).subscribe({
      next: (f) => {
        this.fiche.set(f);
        this.selection.set([...(f.operations ?? [])]);
        this.form.patchValue({
          nom: f.nom, fournisseur_id: f.fournisseur_id, hotes: f.hotes.join('\n'),
          methodes: f.methodes.join(','), notes: f.notes ?? '',
        });
        this.form.markAsPristine();
        this.chargement.set(false);
        this.chargerOperations();
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Destination introuvable.'));
        this.chargement.set(false);
      },
    });
  }

  statutFournisseur(s: string): string {
    return ({ brouillon: 'brouillon', a_valider: 'à valider', valide: 'validé', suspendu: 'suspendu' } as Record<string, string>)[s] ?? s;
  }

  invalide(champ: 'nom' | 'fournisseur_id' | 'hotes'): boolean {
    const c = this.form.controls[champ];
    return c.invalid && (c.touched || c.dirty);
  }

  /** Sélection conservée même si une opération n'est plus listée (archivée) : jamais d'élargissement silencieux. */
  orphelines(): string[] {
    const dispo = new Set(this.operationsDispo().map((o) => o.id));
    return this.selection().filter((id) => !dispo.has(id));
  }

  basculer(id: string): void {
    this.selection.update((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
    this.form.markAsDirty();
  }

  chargerOperations(): void {
    const fid = this.form.controls.fournisseur_id.value;
    this.operationsDispo.set([]);
    this.erreurOps.set(null);
    if (this.creation()) this.selection.set([]);
    if (!fid) return;
    this.chargementOps.set(true);
    this.fournisseursService.operations(fid, {}, 1, 200).subscribe({
      next: (r) => {
        this.operationsDispo.set((r.items ?? []).filter((o) => o.statut === 'active' && (o.methode === 'GET' || o.methode === 'HEAD')));
        this.chargementOps.set(false);
      },
      error: (err) => {
        this.erreurOps.set(messageErreur(err, 'Impossible de charger les opérations du fournisseur.'));
        this.chargementOps.set(false);
      },
    });
  }

  retour(): string[] {
    const f = this.fiche();
    return f ? ['/admin/integrations/destinations', f.id] : ['/admin/integrations/destinations'];
  }

  enregistrer(): void {
    if (this.enregistrement()) return;
    this.erreurServeur.set(null);
    this.erreurHotes.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const hotes = hotesDepuisTexte(v.hotes);
    if (!hotes.length) {
      this.erreurHotes.set('Indiquez au moins un hôte public.');
      return;
    }
    const saisie = {
      nom: v.nom.trim(),
      fournisseur_id: v.fournisseur_id.trim(),
      hotes,
      ports: [443],
      methodes: v.methodes.split(',').filter((m): m is 'GET' | 'HEAD' => m === 'GET' || m === 'HEAD'),
      operations: [...this.selection()],
      notes: texteOuNull(v.notes),
    };
    this.enregistrement.set(true);
    const req = this.creation()
      ? this.service.creerDestination(saisie)
      : this.service.modifierDestination(this.fiche()!.id, this.fiche()!.revision, saisie);
    req.subscribe({
      next: (r) => {
        this.form.markAsPristine();
        this.enregistrement.set(false);
        void this.dialogs.success('Destination enregistrée — aucun appel réseau.').then(() => {
          void this.router.navigate(['/admin/integrations/destinations', r.id]);
        });
      },
      error: (err) => {
        this.enregistrement.set(false);
        this.erreurServeur.set(messageErreur(err, 'Enregistrement refusé.'));
      },
    });
  }
}
