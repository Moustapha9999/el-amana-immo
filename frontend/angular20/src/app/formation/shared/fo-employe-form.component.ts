import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Observable, startWith } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { Employe, FO_BASE, nettoyer } from '../formation.models';
import { FormationStore } from '../formation.store';
import { FoRefAddComponent } from './fo-ref-add.component';

/** Création / modification d'un employé (Nom, Prénom, Fonction, Entité → Périmètre déduit, Email, Téléphone). */
@Component({
  selector: 'bea-fo-employe-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, FoRefAddComponent],
  template: `
    <div class="bea-mg__backdrop" [class.bea-fx-over]="dessus()" (click)="quitter()"></div>
    <div class="bea-mg__modal bea-mg__modal--lg bea-ct-modal" [class.bea-fx-over]="dessus()" role="dialog" aria-modal="true">
      <header class="bea-ct-modal__head">
        <h2><mat-icon>{{ employe() ? 'edit' : 'person_add' }}</mat-icon> {{ employe() ? 'Modifier l’employé' : 'Nouvel employé' }}</h2>
        <button type="button" class="bea-ct-view__close" (click)="quitter()" aria-label="Fermer"><mat-icon>close</mat-icon></button>
      </header>
      <form class="bea-ct-modal__body bea-fo-form" [formGroup]="form" (ngSubmit)="enregistrer()">
        <div class="bea-fo-row">
          <label>Nom <em>*</em>
            <input formControlName="nom" maxlength="120" (blur)="verifierDoublons()" [class.is-invalid]="invalide('nom')" autofocus />
            @if (invalide('nom')) { <span class="bea-fo-err">Le nom est obligatoire</span> }
          </label>
          <label>Prénom
            <input formControlName="prenom" maxlength="120" (blur)="verifierDoublons()" />
          </label>
        </div>
        <div class="bea-fo-row">
          <label>Fonction
            <span class="bea-fo-inline">
              <select formControlName="fonction_id">
                <option value="">— Non renseignée —</option>
                @for (f of fonctions(); track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
              </select>
              @if (store.cap().referentiels_gerer) {
                <button type="button" class="bea-fo-addbtn" title="Ajouter une fonction" (click)="ajoutFonction.set(true)"><mat-icon>add</mat-icon></button>
              }
            </span>
          </label>
          <label>Entité
            <select formControlName="entite_id">
              <option value="">— Non renseignée —</option>
              @for (e of store.entitesActives(); track e.id) { <option [value]="e.id">{{ e.libelle }}</option> }
            </select>
          </label>
          <label>Périmètre <span class="bea-fo-hint">(déduit de l’entité)</span>
            <input [value]="perimetre() || '—'" readonly tabindex="-1" style="background:#f8fafc" />
          </label>
        </div>
        <div class="bea-fo-row">
          <label>Email
            <input type="email" formControlName="email" maxlength="255" [class.is-invalid]="invalide('email')" />
            @if (invalide('email')) { <span class="bea-fo-err">Adresse e-mail invalide</span> }
          </label>
          <label>Téléphone
            <input formControlName="telephone" maxlength="40" />
          </label>
        </div>

        @if (doublons().length) {
          <div class="bea-fo-note" [class.bea-fo-note--danger]="identique()">
            <mat-icon>{{ identique() ? 'report' : 'warning' }}</mat-icon>
            <div style="flex:1">
              <strong>{{ identique() ? 'Cet employé existe déjà.' : 'Employé(s) au nom proche :' }}</strong>
              <ul class="bea-fo-dup">
                @for (d of doublons(); track d.id) {
                  <li [class.is-same]="d.identique">
                    <span class="bea-fo-avatar">{{ d.nom_complet.slice(0, 2).toUpperCase() }}</span>
                    <span style="flex:1"><strong>{{ d.nom_complet }}</strong> · {{ d.entite || 'Entité non renseignée' }}{{ d.actif ? '' : ' · désactivé' }}</span>
                    <button type="button" class="bea-fo-linkbtn" (click)="choisirExistant.emit(d)">Ouvrir</button>
                  </li>
                }
              </ul>
              <label class="bea-fo-check" style="margin-top:0.6rem">
                <input type="checkbox" [checked]="differente()" (change)="differente.set($any($event.target).checked)" />
                Je confirme qu’il s’agit d’une personne différente
              </label>
            </div>
          </div>
        }
        @if (erreur()) { <div class="bea-fo-note bea-fo-note--danger"><mat-icon>error</mat-icon>{{ erreur() }}</div> }

        <footer class="bea-ct-modal__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="quitter()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || (doublons().length > 0 && !differente())">
            <mat-icon>save</mat-icon> Enregistrer
          </button>
        </footer>
      </form>
    </div>
    @if (ajoutFonction()) {
      <bea-fo-ref-add domaine="FONCTION" (fermer)="ajoutFonction.set(false)" (cree)="fonctionCreee($event.id)" />
    }
  `,
})
export class FoEmployeFormComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  readonly store = inject(FormationStore);

  readonly employe = input<Employe | null>(null);
  readonly dessus = input(false);
  readonly enregistre = output<Employe>();
  readonly fermer = output<void>();
  readonly choisirExistant = output<Employe>();

  readonly busy = signal(false);
  readonly erreur = signal('');
  readonly doublons = signal<Employe[]>([]);
  readonly differente = signal(false);
  readonly ajoutFonction = signal(false);
  readonly identique = computed(() => this.doublons().some((d) => d.identique));
  private dernierControle = '';

  readonly form = this.fb.nonNullable.group({
    nom: ['', [Validators.required, Validators.maxLength(120)]],
    prenom: [''],
    fonction_id: [''],
    entite_id: [''],
    email: ['', Validators.email],
    telephone: [''],
  });

  private readonly entiteId = toSignal(
    this.form.controls.entite_id.valueChanges.pipe(startWith(this.form.controls.entite_id.value)) as Observable<string>,
    { initialValue: '' },
  );
  readonly perimetre = computed(() => this.store.entite(this.entiteId())?.perimetre ?? '');
  readonly fonctions = computed(() => {
    const actuel = this.employe()?.fonction_id;
    return this.store.refs('FONCTION', true).filter((f) => f.actif || f.id === actuel);
  });

  ngOnInit(): void {
    const e = this.employe();
    if (e) {
      this.form.reset({
        nom: e.nom, prenom: e.prenom ?? '', fonction_id: e.fonction_id ?? '', entite_id: e.entite_id ?? '',
        email: e.email ?? '', telephone: e.telephone ?? '',
      });
      this.dernierControle = `${e.nom}|${e.prenom ?? ''}`.toLowerCase();
    }
  }

  invalide(c: 'nom' | 'email'): boolean {
    const ctl = this.form.controls[c];
    return ctl.invalid && (ctl.touched || ctl.dirty);
  }

  fonctionCreee(id: string): void {
    this.ajoutFonction.set(false);
    this.form.controls.fonction_id.setValue(id);
    this.form.markAsDirty();
  }

  verifierDoublons(): void {
    const { nom, prenom } = this.form.getRawValue();
    const cle = `${nom.trim()}|${prenom.trim()}`.toLowerCase();
    if (!nom.trim() || cle === this.dernierControle) return;
    this.dernierControle = cle;
    this.api
      .get<Employe[]>(`${FO_BASE}/employes/doublons`, nettoyer({ nom: nom.trim(), prenom: prenom.trim(), exclure: this.employe()?.id }))
      .subscribe({
        next: (d) => {
          this.doublons.set(d);
          this.differente.set(false);
        },
        error: () => this.doublons.set([]),
      });
  }

  quitter(): void {
    if (!this.form.dirty) {
      this.fermer.emit();
      return;
    }
    this.feedback
      .confirm({ action: 'annulation', title: 'Abandonner la saisie ?', message: 'Les informations saisies ne seront pas enregistrées.' })
      .subscribe((ok) => ok && this.fermer.emit());
  }

  enregistrer(): void {
    this.form.markAllAsTouched();
    if (this.form.invalid) return;
    this.erreur.set('');
    const v = this.form.getRawValue();
    const corps = {
      nom: v.nom.trim(),
      prenom: v.prenom.trim() || null,
      fonction_id: v.fonction_id || null,
      entite_id: v.entite_id || null,
      email: v.email.trim() || null,
      telephone: v.telephone.trim() || null,
    };
    const forcer = this.doublons().length > 0 && this.differente();
    const e = this.employe();
    const q = forcer ? '?forcer=true' : '';
    this.feedback
      .run(
        () => (e ? this.api.patch<Employe>(`${FO_BASE}/employes/${e.id}${q}`, corps) : this.api.post<Employe>(`${FO_BASE}/employes${q}`, corps)),
        {
          busy: this.busy,
          loading: 'Enregistrement…',
          success: (r) => ({ title: e ? 'Employé modifié' : 'Employé créé', message: r.nom_complet }),
          errorTitle: "Échec de l'enregistrement",
          errorHint: 'Vos données saisies ont été conservées.',
          idempotent: !e,
          onError: (err) => {
            if (err.code === 'DOUBLON_EMPLOYE') {
              this.dernierControle = '';
              this.verifierDoublons();
            } else {
              this.erreur.set(err.message);
            }
          },
        },
      )
      .subscribe((r) => {
        this.form.markAsPristine();
        this.enregistre.emit(r);
      });
  }
}
