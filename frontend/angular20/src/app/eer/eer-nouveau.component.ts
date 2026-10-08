import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, WritableSignal, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { EerAgence, EerApercuClientele, EerReferentiel, EerService } from './eer.service';

@Component({
  selector: 'bea-eer-nouveau',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">KYC · Gestion des EER</p>
          <h1>Nouvelle entrée en relation</h1>
          <p class="bea-ct-head__sub">
            Saisie initiale du client. Les fiches officielles se complètent ensuite dans l’onglet « Formulaires » du dossier
            (saisie unique : chaque donnée n’est saisie qu’une fois).
          </p>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/eer/dossiers"><mat-icon>arrow_back</mat-icon> Retour</a>
        </div>
      </header>

      <form class="bea-mg__panel eer-form" [formGroup]="form" (ngSubmit)="creer()">
        <h2>Cadre de l’entrée en relation</h2>
        <div class="bea-ct-grid">
          <label>Agence *
            <select formControlName="agence_id">
              <option value="">— Choisir —</option>
              @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
            </select>
          </label>
          <label>Type de client *
            <select formControlName="type_client">
              <option value="">— Choisir —</option>
              @for (t of types(); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
            </select>
          </label>
          <label>Profil *
            <select formControlName="profil">
              <option value="">— Choisir —</option>
              @for (p of profilsDuType(); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
            </select>
          </label>
          <label>Tranche de mouvement
            <select formControlName="tranche_mouvement_code">
              <option value="">—</option>
              @for (t of tranches(); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
            </select>
          </label>
          <label>Risque LBC-FT
            @if (risqueImpose(); as r) {
              <input [value]="r" readonly />
              <small class="bea-ct-sub">Imposé par le type de client (référentiel)</small>
            } @else {
              <select formControlName="risque_lbcft">
                <option value="">Non évalué</option>
                <option value="FAIBLE">Faible</option>
                <option value="MOYEN">Moyen</option>
                <option value="ELEVE">Élevé</option>
              </select>
            }
          </label>
        </div>

        <h2>{{ estPP() ? 'Identité du client' : 'Identification de la personne morale' }}</h2>
        <div class="bea-ct-grid">
          <label>{{ estPP() ? 'Nom *' : 'Raison sociale / dénomination *' }}
            <input formControlName="nom" maxlength="255" />
          </label>
          @if (estPP()) {
            <label>Prénom
              <input formControlName="prenom" maxlength="120" />
            </label>
          }
          <label>Racine client (ORION)
            <input formControlName="racine_client" maxlength="6" placeholder="000001" />
            <small class="bea-ct-sub">6 chiffres, zéros conservés. Un client = une racine, pas un compte.</small>
          </label>
          <div style="display:flex;align-items:end">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="chargerOrion()" [disabled]="busy() || form.controls.racine_client.value.trim().length !== 6">
              <mat-icon>cloud_download</mat-icon> Charger ORION
            </button>
          </div>
        </div>
        @if (orion(); as o) {
          @if (o.present) {
            <p class="bea-ct-note">
              <strong>{{ o.nom }}</strong>
              @if (o.prenoms) { — {{ o.prenoms }} }
              · {{ o.nb_comptes }} compte(s)
              @if (o.profil_derive) { · {{ o.profil_derive }} }
              @if (o.compte_retenu) { · compte retenu {{ o.compte_retenu.compte }} }
              <br />Les champs ORION seront préremplis (à confirmer). Une saisie déjà faite n’est pas écrasée.
            </p>
            @for (r of o.reserves ?? []; track r) { <p class="bea-ct-note">{{ r }}</p> }
          } @else {
            <p class="bea-ct-note">{{ o.message }}</p>
          }
        }

        @if (estPP()) {
          <h2>Pièce d’identité</h2>
          <div class="bea-ct-grid">
            <label>Type de pièce
              <select formControlName="piece_type">
                <option value="">—</option>
                @for (t of typesPiece(); track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            <label>Numéro
              <input formControlName="piece_numero" maxlength="60" />
            </label>
            <label>Date de délivrance
              <input type="date" formControlName="piece_delivrance" />
            </label>
            <label>Date d’expiration
              <input type="date" formControlName="piece_expiration" />
            </label>
          </div>
        }

        @if (ppeFatca()) {
          <h2>PPE / FATCA</h2>
          <div class="bea-ct-grid">
            <label>Personne politiquement exposée
              <select formControlName="ppe">
                <option value="">Non renseigné</option>
                <option value="non">Non</option>
                <option value="oui">Oui</option>
              </select>
            </label>
            @if (form.controls.ppe.value === 'oui') {
              <label>Motif PPE *
                <input formControlName="ppe_motif" maxlength="500" />
              </label>
            }
            <label>Indice FATCA
              <select formControlName="fatca_indice">
                <option value="">Non renseigné</option>
                <option value="non">Non</option>
                <option value="oui">Oui</option>
              </select>
            </label>
            @if (form.controls.fatca_indice.value === 'oui') {
              <label>Détail FATCA *
                <input formControlName="fatca_detail" maxlength="500" />
              </label>
            }
          </div>
          <p class="bea-ct-note">Un client PPE déclenche l’avis obligatoire du Service Conformité KYC avant validation.</p>
        }

        <div class="eer-form__foot">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/eer/dossiers">Annuler</a>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || form.invalid || !motifsOk()">
            <mat-icon>save</mat-icon> Créer le dossier (brouillon)
          </button>
        </div>
      </form>
    </section>
  `,
  styles: [`
    .eer-form { padding: 1.1rem 1.25rem; }
    .eer-form h2 { margin: 1.1rem 0 0.6rem; font-size: 0.95rem; color: #0f172a; }
    .eer-form h2:first-child { margin-top: 0; }
    .eer-form__foot { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 1.25rem; }
  `],
})
export class EerNouveauComponent implements OnInit {
  private readonly eer = inject(EerService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly busy = signal(false);
  readonly orion = signal<EerApercuClientele | null>(null);
  readonly agences = signal<EerAgence[]>([]);
  readonly types = signal<EerReferentiel[]>([]);
  readonly profils = signal<EerReferentiel[]>([]);
  readonly tranchesPP = signal<EerReferentiel[]>([]);
  readonly tranchesPM = signal<EerReferentiel[]>([]);
  readonly typesPiece = signal<EerReferentiel[]>([]);
  private readonly typeChoisi = signal('');

  readonly form = this.fb.nonNullable.group({
    agence_id: ['', Validators.required],
    type_client: ['', Validators.required],
    profil: ['', Validators.required],
    tranche_mouvement_code: '',
    risque_lbcft: '',
    nom: ['', [Validators.required, Validators.maxLength(255)]],
    prenom: '',
    racine_client: ['', Validators.pattern(/^[0-9]{6}$/)],
    piece_type: '',
    piece_numero: '',
    piece_delivrance: '',
    piece_expiration: '',
    ppe: '',
    ppe_motif: '',
    fatca_indice: '',
    fatca_detail: '',
  });

  readonly hasUnsavedChanges = unsavedChanges(() => this.form.dirty && !this.busy(), () => this.form);

  readonly estPP = computed(() => this.typeChoisi() === 'PP');
  readonly typeRef = computed(() => this.types().find((t) => t.code === this.typeChoisi()) ?? null);
  readonly ppeFatca = computed(() => this.typeRef()?.meta?.['ppe_fatca'] === true);
  readonly risqueImpose = computed(() => (this.typeRef()?.meta?.['risque_impose'] as string | null) ?? null);
  readonly profilsDuType = computed(() => this.profils().filter((p) => p.parent_code === this.typeChoisi()));
  readonly tranches = computed(() => (this.estPP() ? this.tranchesPP() : this.typeChoisi() ? this.tranchesPM() : []));

  ngOnInit(): void {
    this.eer.agences().subscribe({
      next: (a) => {
        this.agences.set(a);
        if (a.length === 1) this.form.controls.agence_id.setValue(a[0].id);
      },
      error: (e) => this.fail(e),
    });
    const charger = (domaine: string, cible: WritableSignal<EerReferentiel[]>) =>
      this.eer.referentiels(domaine).subscribe({ next: (r) => cible.set(r), error: (e) => this.fail(e) });
    charger('TYPE_CLIENT', this.types);
    charger('PROFIL', this.profils);
    charger('TRANCHE_PP', this.tranchesPP);
    charger('TRANCHE_PM', this.tranchesPM);
    charger('TYPE_PIECE', this.typesPiece);
    this.form.controls.type_client.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((t) => {
      this.typeChoisi.set(t);
      this.form.patchValue({ profil: '', tranche_mouvement_code: '', ppe: '', fatca_indice: '' });
    });
  }

  chargerOrion(): void {
    const racine = this.form.controls.racine_client.value.trim();
    if (!/^[0-9]{6}$/.test(racine)) return;
    this.eer.apercuClientele(racine).subscribe({
      next: (o) => {
        this.orion.set(o);
        if (o.present) {
          if (o.nom) this.form.controls.nom.setValue(o.nom);
          if (o.prenoms) this.form.controls.prenom.setValue(o.prenoms);
        }
      },
      error: (e) => this.fail(e),
    });
  }

  motifsOk(): boolean {
    const v = this.form.getRawValue();
    return (v.ppe !== 'oui' || !!v.ppe_motif.trim()) && (v.fatca_indice !== 'oui' || !!v.fatca_detail.trim());
  }

  creer(): void {
    if (this.form.invalid || !this.motifsOk()) return;
    const v = this.form.getRawValue();
    const client: Record<string, unknown> = { nom: v.nom.trim() };
    if (v.racine_client.trim()) client['racine_client'] = v.racine_client.trim();
    if (this.estPP()) {
      if (v.prenom.trim()) client['pp'] = { prenom: v.prenom.trim() };
      if (v.piece_type && v.piece_numero.trim()) {
        client['piece'] = {
          type: v.piece_type,
          numero: v.piece_numero.trim(),
          date_delivrance: v.piece_delivrance || null,
          date_expiration: v.piece_expiration || null,
        };
      }
    }
    const clientRole: Record<string, unknown> = {};
    if (this.ppeFatca()) {
      if (v.ppe) clientRole['ppe'] = v.ppe === 'oui';
      if (v.ppe === 'oui') clientRole['ppe_motif'] = v.ppe_motif.trim();
      if (v.fatca_indice) clientRole['fatca_indice'] = v.fatca_indice === 'oui';
      if (v.fatca_indice === 'oui') clientRole['fatca_detail'] = v.fatca_detail.trim();
    }
    const dossier: Record<string, unknown> = {};
    if (v.tranche_mouvement_code) dossier['tranche_mouvement_code'] = v.tranche_mouvement_code;
    if (v.risque_lbcft && !this.risqueImpose()) dossier['risque_lbcft'] = v.risque_lbcft;

    this.feedback
      .run(
        () => this.eer.creer({
          agence_id: v.agence_id,
          type_client: v.type_client,
          profil: v.profil,
          operation_type: 'ENTREE_RELATION',
          client,
          client_role: clientRole,
          dossier,
        }),
        {
          loading: 'Création du dossier…',
          busy: this.busy,
          idempotent: true,
          errorTitle: 'Création refusée',
          errorHint: 'Vos données saisies ont été conservées.',
          success: (d) => ({
            title: 'Dossier EER créé',
            details: [
              { label: 'Référence', value: d.reference },
              { label: 'Statut', value: 'Brouillon' },
            ],
          }),
        },
      )
      .subscribe((d) => {
        this.form.markAsPristine();
        void this.router.navigate(['/eer/dossiers', d.id]);
      });
  }

  private fail(err: unknown): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, 'Chargement impossible'));
  }
}
