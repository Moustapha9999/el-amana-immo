import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { FormationUiComponent } from '../formation-ui.component';
import { Domaine, Employe, FO_BASE, RefItem, Session, dateLongue } from '../formation.models';
import { FormationStore } from '../formation.store';
import { FoEmployePickerComponent } from '../shared/fo-employe-picker.component';
import { FoRefAddComponent } from '../shared/fo-ref-add.component';

@Component({
  selector: 'bea-fo-session-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, FormationUiComponent, FoEmployePickerComponent, FoRefAddComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <button type="button" class="bea-fo-back" (click)="retour()"><mat-icon>arrow_back</mat-icon> {{ session() ? session()!.reference : 'Formations' }}</button>
          <h1>{{ session() ? 'Modifier la formation' : 'Nouvelle formation' }}</h1>
          <p class="bea-fo-head__sub">Date, thème, lieu et formateur sont obligatoires. Les participants sélectionnés sont convoqués : aucun n’est présent par défaut.</p>
        </div>
      </header>

      @if (chargement()) {
        <section class="bea-mg__panel bea-fo-pad">
          @for (i of [1, 2, 3, 4]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
        </section>
      } @else {
        <form [formGroup]="form" (ngSubmit)="enregistrer()">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2><mat-icon style="vertical-align:middle;color:#1a5278">event</mat-icon> Informations de la formation</h2></div>
            <div class="bea-fo-form bea-fo-pad">
              <div class="bea-fo-row">
                <label>Date <em>*</em>
                  <input type="date" formControlName="date_session" [class.is-invalid]="invalide('date_session')" />
                  @if (invalide('date_session')) { <span class="bea-fo-err">La date est obligatoire</span> }
                  @else if (form.controls.date_session.value) { <span class="bea-fo-hint">{{ dateLongue(form.controls.date_session.value) }}</span> }
                </label>
                <label>Lieu <em>*</em>
                  <span class="bea-fo-inline">
                    <select formControlName="lieu_id" [class.is-invalid]="invalide('lieu_id')">
                      <option value="">— Choisir un lieu —</option>
                      @for (r of options('LIEU', form.controls.lieu_id.value ? [form.controls.lieu_id.value] : []); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
                    </select>
                    @if (store.cap().referentiels_gerer) { <button type="button" class="bea-fo-addbtn" title="Ajouter un lieu" (click)="ajout.set('LIEU')"><mat-icon>add</mat-icon></button> }
                  </span>
                  @if (invalide('lieu_id')) { <span class="bea-fo-err">Le lieu est obligatoire</span> }
                </label>
                <label>Intitulé <span class="bea-fo-hint">(facultatif)</span>
                  <input formControlName="intitule" maxlength="255" placeholder="Ex. Session de sensibilisation agences Nord" />
                </label>
              </div>

              <div class="bea-fo-row">
                <div class="bea-fo-label">Thème(s) <em>*</em>
                  <span class="bea-fo-inline">
                    <div class="bea-fo-multi" style="flex:1" [class.is-invalid]="tente() && !themes().length">
                      @for (id of themes(); track id) {
                        <span class="bea-fo-multi__chip">{{ store.libelle('THEME', id) }}<button type="button" (click)="retirer('THEME', id)" aria-label="Retirer"><mat-icon>close</mat-icon></button></span>
                      }
                      <select (change)="ajouter('THEME', $any($event.target))">
                        <option value="">{{ themes().length ? '+ Ajouter un thème' : 'Choisir un ou plusieurs thèmes' }}</option>
                        @for (r of disponibles('THEME', themes()); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
                      </select>
                    </div>
                    @if (store.cap().referentiels_gerer) { <button type="button" class="bea-fo-addbtn" title="Nouveau thème" (click)="ajout.set('THEME')"><mat-icon>add</mat-icon></button> }
                  </span>
                  @if (tente() && !themes().length) { <span class="bea-fo-err">Au moins un thème est obligatoire</span> }
                </div>
                <div class="bea-fo-label">Formateur(s) <em>*</em>
                  <span class="bea-fo-inline">
                    <div class="bea-fo-multi" style="flex:1" [class.is-invalid]="tente() && !formateurs().length">
                      @for (id of formateurs(); track id) {
                        <span class="bea-fo-multi__chip">{{ store.libelle('FORMATEUR', id) }}<button type="button" (click)="retirer('FORMATEUR', id)" aria-label="Retirer"><mat-icon>close</mat-icon></button></span>
                      }
                      <select (change)="ajouter('FORMATEUR', $any($event.target))">
                        <option value="">{{ formateurs().length ? '+ Ajouter un formateur' : 'Choisir un ou plusieurs formateurs' }}</option>
                        @for (r of disponibles('FORMATEUR', formateurs()); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
                      </select>
                    </div>
                    @if (store.cap().referentiels_gerer) { <button type="button" class="bea-fo-addbtn" title="Nouveau formateur" (click)="ajout.set('FORMATEUR')"><mat-icon>add</mat-icon></button> }
                  </span>
                  @if (tente() && !formateurs().length) { <span class="bea-fo-err">Au moins un formateur est obligatoire</span> }
                </div>
              </div>
              <label>Observations
                <textarea formControlName="observations" maxlength="4000" rows="2"></textarea>
              </label>
            </div>
          </section>

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <div><h2><mat-icon style="vertical-align:middle;color:#1a5278">groups</mat-icon> Participants</h2>
                <p class="bea-fo-panel-sub">Sélection multiple, filtrable par périmètre et entité. Le périmètre est déduit de l’entité.</p></div>
              <span class="bea-mg__count">{{ employes().length }} sélectionné(s)</span>
            </div>
            <div class="bea-fo-pad">
              <bea-fo-employe-picker [(selection)]="employes" [connus]="connus()" />
            </div>
          </section>

          @if (avecPresences()) {
            <div class="bea-fo-note">
              <mat-icon>lock_clock</mat-icon>
              <div style="flex:1;display:grid;gap:0.45rem">
                <strong>Des présences ont déjà été saisies pour cette formation.</strong>
                <span>Toute modification est tracée dans l’historique : indiquez-en le motif.</span>
                <textarea class="bea-fo-input" formControlName="motif" rows="2" maxlength="1000" placeholder="Motif de la modification (obligatoire)"
                  [class.is-invalid]="tente() && !form.controls.motif.value.trim()"></textarea>
              </div>
            </div>
          }

          <div class="bea-fo-saisie-bar">
            <span>
              <strong>{{ employes().length }}</strong> participant(s) ·
              <strong>{{ themes().length }}</strong> thème(s) · <strong>{{ formateurs().length }}</strong> formateur(s)
            </span>
            <span style="display:flex;gap:0.5rem">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="retour()">Annuler</button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()">
                <mat-icon>save</mat-icon> {{ session() ? 'Enregistrer les modifications' : 'Créer la formation' }}
              </button>
            </span>
          </div>
        </form>
      }
    </div>
    @if (ajout(); as d) {
      <bea-fo-ref-add [domaine]="d" (fermer)="ajout.set(null)" (cree)="refCree(d, $event)" />
    }
  `,
})
export class FoSessionFormComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  readonly store = inject(FormationStore);

  readonly dateLongue = dateLongue;
  readonly session = signal<Session | null>(null);
  readonly chargement = signal(false);
  readonly busy = signal(false);
  readonly tente = signal(false);
  readonly ajout = signal<Domaine | null>(null);
  readonly themes = signal<string[]>([]);
  readonly formateurs = signal<string[]>([]);
  readonly employes = signal<string[]>([]);
  private initial = '';

  readonly form = this.fb.nonNullable.group({
    date_session: ['', Validators.required],
    lieu_id: ['', Validators.required],
    intitule: [''],
    observations: [''],
    motif: [''],
  });

  readonly avecPresences = computed(() => {
    const s = this.session();
    return !!s && s.stats.presents + s.stats.absents > 0;
  });
  readonly connus = computed<Employe[]>(() =>
    (this.session()?.participants ?? []).map((p) => ({
      id: p.employe_id, nom: p.nom, prenom: p.prenom, nom_complet: p.nom_complet, fonction: p.fonction, entite: p.entite,
      perimetre: p.perimetre, actif: p.employe_actif,
    }) as Employe),
  );

  readonly hasUnsavedChanges = unsavedChanges(() => !this.busy() && this.instantane() !== this.initial);

  ngOnInit(): void {
    this.store.charger();
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.initial = this.instantane();
      return;
    }
    this.chargement.set(true);
    this.api.get<Session>(`${FO_BASE}/sessions/${id}`).subscribe({
      next: (s) => {
        if (!s.actions.modifier) {
          this.feedback.warning({ title: 'Modification impossible', message: `Formation ${s.statut_libelle.toLowerCase()}.` });
          void this.router.navigate(['/formation/sessions', s.id]);
          return;
        }
        this.session.set(s);
        this.form.reset({
          date_session: s.date_session, lieu_id: s.lieu?.id ?? '', intitule: s.intitule ?? '', observations: s.observations ?? '', motif: '',
        });
        this.themes.set(s.themes.map((t) => t.id));
        this.formateurs.set(s.formateurs.map((f) => f.id));
        this.employes.set((s.participants ?? []).map((p) => p.employe_id));
        this.initial = this.instantane();
        this.chargement.set(false);
      },
      error: (e) => {
        this.chargement.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Formation introuvable'));
        void this.router.navigate(['/formation/sessions']);
      },
    });
  }

  private instantane(): string {
    const v = this.form.getRawValue();
    return JSON.stringify([v.date_session, v.lieu_id, v.intitule, v.observations, v.motif, this.themes(), this.formateurs(), this.employes()]);
  }

  invalide(c: 'date_session' | 'lieu_id'): boolean {
    const ctl = this.form.controls[c];
    return ctl.invalid && (ctl.touched || this.tente());
  }

  options(domaine: Domaine, garder: string[]): RefItem[] {
    return this.store.refs(domaine, true).filter((r) => r.actif || garder.includes(r.id));
  }

  disponibles(domaine: Domaine, choisis: string[]): RefItem[] {
    return this.store.refs(domaine).filter((r) => !choisis.includes(r.id));
  }

  ajouter(domaine: 'THEME' | 'FORMATEUR', select: HTMLSelectElement): void {
    const id = select.value;
    select.value = '';
    if (!id) return;
    const cible = domaine === 'THEME' ? this.themes : this.formateurs;
    if (!cible().includes(id)) cible.set([...cible(), id]);
  }

  retirer(domaine: 'THEME' | 'FORMATEUR', id: string): void {
    const cible = domaine === 'THEME' ? this.themes : this.formateurs;
    cible.set(cible().filter((x) => x !== id));
  }

  refCree(domaine: Domaine, r: RefItem): void {
    this.ajout.set(null);
    if (domaine === 'LIEU') this.form.controls.lieu_id.setValue(r.id);
    else if (domaine === 'THEME') this.themes.set([...this.themes(), r.id]);
    else if (domaine === 'FORMATEUR') this.formateurs.set([...this.formateurs(), r.id]);
  }

  retour(): void {
    const s = this.session();
    void this.router.navigate(s ? ['/formation/sessions', s.id] : ['/formation/sessions']);
  }

  enregistrer(): void {
    this.tente.set(true);
    this.form.markAllAsTouched();
    const v = this.form.getRawValue();
    if (this.form.invalid || !this.themes().length || !this.formateurs().length) {
      this.feedback.warning({ title: 'Champs obligatoires manquants', message: 'Renseignez la date, le thème, le lieu et le formateur.' });
      return;
    }
    const s = this.session();
    if (s && this.avecPresences() && !v.motif.trim()) {
      this.feedback.warning({ title: 'Motif obligatoire', message: 'Des présences sont déjà saisies : indiquez le motif de la modification.' });
      return;
    }
    const corps = {
      date_session: v.date_session,
      lieu_id: v.lieu_id,
      theme_ids: this.themes(),
      formateur_ids: this.formateurs(),
      employe_ids: this.employes(),
      intitule: v.intitule.trim() || null,
      observations: v.observations.trim() || null,
    };
    const retires = s ? (s.participants ?? []).filter((p) => !this.employes().includes(p.employe_id)).length : 0;
    this.feedback
      .run(
        () =>
          s
            ? this.api.patch<Session>(`${FO_BASE}/sessions/${s.id}`, { ...corps, revision: s.revision, motif: v.motif.trim() || null })
            : this.api.post<Session>(`${FO_BASE}/sessions`, corps),
        {
          confirm: s && retires
            ? { action: 'modification', message: `${retires} participant(s) seront retiré(s) de la formation.`, hint: 'Le retrait est tracé dans l’historique.' }
            : undefined,
          busy: this.busy,
          loading: s ? 'Enregistrement…' : 'Création de la formation…',
          success: (r) => ({
            title: s ? 'Formation modifiée' : 'Formation créée',
            details: [
              { label: 'Référence', value: r.reference },
              { label: 'Participants', value: String(r.stats.participants) },
            ],
          }),
          errorTitle: s ? 'Échec de la modification' : 'Échec de la création',
          errorHint: 'Vos données saisies ont été conservées.',
          idempotent: !s,
        },
      )
      .subscribe((r) => {
        this.initial = this.instantane();
        void this.router.navigate(['/formation/sessions', r.id]);
      });
  }
}
