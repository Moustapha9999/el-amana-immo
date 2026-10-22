import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  OnInit,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { AbstractControl, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { forkJoin } from 'rxjs';
import { ApiService } from '../core/services/api.service';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiErrorInfo, describeApiErrorAsync } from '../core/feedback/api-error';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { OrgReferentielService } from '../core/org/org-referentiel.service';
import { OrgAgenceOption, OrgEntiteOption } from '../core/org/org-referentiel.models';
import { QuantitePipe, formatQuantite } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { AUTRE, CHAMP_AUTRE_PAR_CODE, corpsOrg, erreurAutre, libelleOrg } from './org-autre';
import { SortieMotif, SortieMouvement } from './stock-sortie-form.component';

type Provenance = 'FOURNISSEUR' | 'RETOUR_DEPARTEMENT' | 'RETOUR_AGENCE' | 'AUTRE';

interface EntreeArticle {
  id: string;
  code: string;
  designation: string;
  uom: string;
  stock_actuel: number;
  stock_max: number | null;
  fournisseur_habituel: string | null;
  quantite_entiere: boolean;
}

interface EntreeFournisseur {
  id: string;
  code: string;
  raison_sociale: string;
}

interface EntreeReferentiels {
  articles: EntreeArticle[];
  fournisseurs: EntreeFournisseur[];
  motifs: (SortieMotif & { code: string })[];
  types_departement: string[];
  types_service: string[];
  utilisateur: { id: string; nom: string };
}

export interface EntreeMouvement extends SortieMouvement {
  provenance_type?: string | null;
  provenance_libelle?: string | null;
  piece_reference?: string | null;
}

type Champ =
  | 'article_id'
  | 'quantite'
  | 'fournisseur_id'
  | 'piece_reference'
  | 'departement_id'
  | 'departement_autre'
  | 'service_id'
  | 'service_autre'
  | 'agence_id'
  | 'motif_id'
  | 'observation';

const CHAMP_PAR_CODE: Record<string, Champ> = {
  ARTICLE_INTROUVABLE: 'article_id',
  ARTICLE_INACTIF: 'article_id',
  QUANTITE_INVALIDE: 'quantite',
  QUANTITE_ENTIERE: 'quantite',
  STOCK_MODIFIE: 'quantite',
  FOURNISSEUR_OBLIGATOIRE: 'fournisseur_id',
  FOURNISSEUR_INVALIDE: 'fournisseur_id',
  DEPARTEMENT_OBLIGATOIRE: 'departement_id',
  DEPARTEMENT_INVALIDE: 'departement_id',
  SERVICE_INVALIDE: 'service_id',
  SERVICE_HORS_DEPARTEMENT: 'service_id',
  AGENCE_OBLIGATOIRE: 'agence_id',
  AGENCE_INVALIDE: 'agence_id',
  MOTIF_INVALIDE: 'motif_id',
  OBSERVATION_OBLIGATOIRE: 'observation',
  ...CHAMP_AUTRE_PAR_CODE,
};

/** Motif proposé par défaut selon la provenance (modifiable). */
const MOTIF_PAR_PROVENANCE: Record<Provenance, string> = {
  FOURNISSEUR: 'E_ACHAT',
  RETOUR_DEPARTEMENT: 'E_RETOUR',
  RETOUR_AGENCE: 'E_RETOUR',
  AUTRE: 'E_AUTRE',
};

const LIBELLE_PROVENANCE: Record<Provenance, string> = {
  FOURNISSEUR: 'Fournisseur',
  RETOUR_DEPARTEMENT: 'Retour département',
  RETOUR_AGENCE: 'Retour agence',
  AUTRE: 'Autre provenance',
};

/**
 * Formulaire « Nouvelle entrée de stock » : provenance Fournisseur / Retour département / Retour agence / Autre
 * (référentiels CORE), motif configurable. Règles revérifiées côté serveur (`POST /mg/stock/entrees`).
 * Les réceptions de bons de commande restent sur « Réception BC ».
 */
@Component({
  selector: 'bea-stock-entree-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, QuantitePipe],
  template: `
    <div class="bea-mg__backdrop" (click)="demanderFermeture()" role="presentation"></div>
    <div class="bea-mg__modal bea-mg__modal--lg bea-sortie" role="dialog" aria-modal="true" aria-labelledby="entree-title">
      <header class="bea-mg__modal-head">
        <div>
          <p class="bea-stock-page__kicker">Stock &amp; Fournitures · Entrées</p>
          <h2 id="entree-title">Nouvelle entrée de stock</h2>
        </div>
        <button type="button" class="bea-mg__icon-btn" (click)="demanderFermeture()" title="Fermer">
          <mat-icon>close</mat-icon>
        </button>
      </header>

      @if (chargement()) {
        <div class="bea-mg__modal-body"><p class="bea-sortie__hint">Chargement des référentiels…</p></div>
      } @else {
        <form [formGroup]="form" (ngSubmit)="valider()" novalidate>
          <div class="bea-mg__modal-body bea-sortie__body">
            <fieldset class="bea-sortie__section">
              <legend><span>1</span> Article et quantité</legend>
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">
                  Article *
                  <select formControlName="article_id" [attr.aria-invalid]="!!erreur('article_id')">
                    <option value="">Sélectionner un article</option>
                    @for (a of articles(); track a.id) {
                      <option [value]="a.id">{{ a.code }} — {{ a.designation }} · {{ a.stock_actuel | quantite }} {{ a.uom }}</option>
                    }
                  </select>
                  @if (erreur('article_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                  @else if (!articles().length) { <small class="bea-sortie__hint">Aucun article actif et stockable.</small> }
                </label>
                <label>
                  Quantité reçue *
                  <input
                    type="number"
                    formControlName="quantite"
                    min="0"
                    [step]="article()?.quantite_entiere === false ? 0.001 : 1"
                    [attr.aria-invalid]="!!erreur('quantite')"
                  />
                  @if (erreur('quantite'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                  @else { <small class="bea-sortie__hint">Strictement positive{{ article()?.quantite_entiere === false ? '' : ', nombre entier' }}.</small> }
                </label>
                <div class="bea-sortie__stock" [attr.data-attention]="depasseMax()">
                  @if (article(); as a) {
                    <span>Stock actuel <strong>{{ a.stock_actuel | quantite }} {{ a.uom }}</strong></span>
                    @if (stockApres() !== null) {
                      <span>Après entrée <strong>{{ stockApres() | quantite }} {{ a.uom }}</strong></span>
                    }
                    @if (depasseMax()) {
                      <span class="bea-sortie__warn">Dépasse le stock maximum ({{ a.stock_max | quantite }} {{ a.uom }}).</span>
                    }
                  } @else {
                    <span>Choisissez un article pour voir son stock.</span>
                  }
                </div>
              </div>
            </fieldset>

            <fieldset class="bea-sortie__section">
              <legend><span>2</span> Provenance de l’article</legend>
              <div class="bea-sortie__toggle bea-sortie__toggle--4" role="radiogroup" aria-label="Provenance">
                @for (p of provenances; track p.value) {
                  <label [class.is-on]="provenance() === p.value">
                    <input type="radio" formControlName="provenance_type" [value]="p.value" />
                    <mat-icon>{{ p.icon }}</mat-icon> {{ p.label }}
                  </label>
                }
              </div>
              <div class="bea-mg__grid">
                @switch (provenance()) {
                  @case ('FOURNISSEUR') {
                    <label>
                      Fournisseur *
                      <select formControlName="fournisseur_id" [attr.aria-invalid]="!!erreur('fournisseur_id')">
                        <option value="">Choisir le fournisseur</option>
                        @for (f of ref()?.fournisseurs ?? []; track f.id) {
                          <option [value]="f.id">{{ f.raison_sociale }} ({{ f.code }})</option>
                        }
                      </select>
                      @if (erreur('fournisseur_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                      @else if (fournisseurHabituel(); as fh) {
                        <small class="bea-sortie__hint">
                          Fournisseur habituel : {{ fh.raison_sociale }}
                          @if (form.controls.fournisseur_id.value !== fh.id) {
                            · <a href="" (click)="$event.preventDefault(); form.controls.fournisseur_id.setValue(fh.id); form.markAsDirty()">utiliser</a>
                          }
                        </small>
                      } @else if (!(ref()?.fournisseurs ?? []).length) {
                        <small class="bea-sortie__hint">Aucun fournisseur actif dans le référentiel.</small>
                      }
                    </label>
                    <label>
                      N° bon de livraison / facture
                      <input formControlName="piece_reference" maxlength="80" placeholder="Ex. BL-2026-0412" />
                      <small class="bea-sortie__hint">Recommandé pour le rapprochement avec la facture.</small>
                    </label>
                  }
                  @case ('RETOUR_DEPARTEMENT') {
                    <label>
                      Département *
                      <select formControlName="departement_id" [attr.aria-invalid]="!!erreur('departement_id')">
                        <option value="">Choisir le département</option>
                        @for (d of departements(); track d.id) {
                          <option [value]="d.id">{{ indent(d) }}{{ d.libelle }}{{ d.sigle ? ' (' + d.sigle + ')' : '' }}{{ d.a_confirmer ? ' — à confirmer' : '' }}</option>
                        }
                        <option [value]="AUTRE">Autre (préciser)…</option>
                      </select>
                      @if (erreur('departement_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                    </label>
                    <label>
                      Service (facultatif)
                      <select formControlName="service_id" [attr.aria-invalid]="!!erreur('service_id')">
                        <option value="">{{ departementId() ? (services().length ? 'Aucun service précis' : 'Aucun service rattaché') : 'Choisir d’abord le département' }}</option>
                        @for (s of services(); track s.id) {
                          <option [value]="s.id">{{ indentService(s) }}{{ s.libelle }}{{ s.a_confirmer ? ' — à confirmer' : '' }}</option>
                        }
                        @if (departementId()) {
                          <option [value]="AUTRE">Autre (préciser)…</option>
                        }
                      </select>
                      @if (erreur('service_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                      @else if (departementAutre()) { <small class="bea-sortie__hint">Département saisi : précisez le service avec « Autre » ou laissez vide.</small> }
                      @else { <small class="bea-sortie__hint">Limité aux services du département choisi.</small> }
                    </label>
                    @if (departementAutre()) {
                      <label>
                        Nom du département *
                        <input formControlName="departement_autre" maxlength="120" autocomplete="off"
                               placeholder="Département absent de la liste" [attr.aria-invalid]="!!erreur('departement_autre')" />
                        @if (erreur('departement_autre'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                        @else { <small class="bea-sortie__hint">Enregistré tel quel sur l’entrée, sans être ajouté à l’organigramme.</small> }
                      </label>
                    }
                    @if (serviceAutre()) {
                      <label>
                        Nom du service *
                        <input formControlName="service_autre" maxlength="120" autocomplete="off"
                               placeholder="Service absent de la liste" [attr.aria-invalid]="!!erreur('service_autre')" />
                        @if (erreur('service_autre'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                      </label>
                    }
                  }
                  @case ('RETOUR_AGENCE') {
                    <label class="bea-mg__span2">
                      Agence *
                      <select formControlName="agence_id" [attr.aria-invalid]="!!erreur('agence_id')">
                        <option value="">Choisir l’agence</option>
                        @for (a of agences(); track a.id) {
                          <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option>
                        }
                      </select>
                      @if (erreur('agence_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                    </label>
                  }
                  @default {
                    <p class="bea-sortie__hint bea-mg__span2" style="margin:0">
                      Don, transfert d’un autre site, régularisation… Précisez l’origine dans les observations (obligatoire).
                    </p>
                  }
                }
                <label class="bea-mg__span2">
                  {{ provenance() === 'FOURNISSEUR' ? 'Livré par' : 'Remis par' }} (facultatif)
                  <input formControlName="remis_par" maxlength="255"
                         [placeholder]="provenance() === 'FOURNISSEUR' ? 'Nom du livreur' : 'Personne qui rapporte l’article'" />
                </label>
              </div>
            </fieldset>

            <fieldset class="bea-sortie__section">
              <legend><span>3</span> Justification</legend>
              <div class="bea-mg__grid">
                <label class="bea-mg__span2">
                  Motif de l’entrée *
                  <select formControlName="motif_id" [attr.aria-invalid]="!!erreur('motif_id')">
                    <option value="">Choisir le motif</option>
                    @for (m of ref()?.motifs ?? []; track m.id) {
                      <option [value]="m.id">{{ m.libelle }}</option>
                    }
                  </select>
                  @if (erreur('motif_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                  @else { <small class="bea-sortie__hint">Proposé selon la provenance, modifiable.</small> }
                </label>
                <label class="bea-mg__span2">
                  Observations {{ observationObligatoire() ? '*' : '(facultatif)' }}
                  <textarea formControlName="observation" rows="2" maxlength="2000"
                            [attr.aria-invalid]="!!erreur('observation')"
                            placeholder="Précisions complémentaires"></textarea>
                  @if (erreur('observation'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                </label>
              </div>
            </fieldset>

            <fieldset class="bea-sortie__section bea-sortie__section--auto">
              <legend><span>4</span> Traçabilité automatique</legend>
              <dl class="bea-sortie__trace">
                <div><dt>Reçu par</dt><dd>{{ ref()?.utilisateur?.nom || '—' }}</dd></div>
                <div><dt>Date et heure</dt><dd>Générées par le serveur à la validation</dd></div>
                <div><dt>Référence</dt><dd>Numéro unique attribué automatiquement</dd></div>
              </dl>
            </fieldset>
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="demanderFermeture()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="saving()">
              <mat-icon>south_west</mat-icon> {{ saving() ? 'Validation…' : 'Valider l’entrée' }}
            </button>
          </footer>
        </form>
      }
    </div>
  `,
  styleUrl: './stock-mouvement-form.css',
})
export class StockEntreeFormComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly feedback = inject(FeedbackService);
  private readonly dialogs = inject(UiDialogService);
  private readonly org = inject(OrgReferentielService);

  readonly closed = output<void>();
  readonly saved = output<EntreeMouvement>();

  readonly provenances: { value: Provenance; label: string; icon: string }[] = [
    { value: 'FOURNISSEUR', label: 'Fournisseur', icon: 'local_shipping' },
    { value: 'RETOUR_DEPARTEMENT', label: 'Retour département', icon: 'account_tree' },
    { value: 'RETOUR_AGENCE', label: 'Retour agence', icon: 'storefront' },
    { value: 'AUTRE', label: 'Autre', icon: 'more_horiz' },
  ];

  readonly chargement = signal(true);
  readonly saving = signal(false);
  readonly soumis = signal(false);
  readonly ref = signal<EntreeReferentiels | null>(null);
  readonly entites = signal<OrgEntiteOption[]>([]);
  readonly agences = signal<OrgAgenceOption[]>([]);
  readonly erreursServeur = signal<Partial<Record<Champ, string>>>({});
  /** Vrai tant que le motif affiché est celui proposé automatiquement. */
  private motifAuto = true;

  readonly form = this.fb.nonNullable.group({
    article_id: ['', Validators.required],
    quantite: [1 as number | null, Validators.required],
    provenance_type: ['FOURNISSEUR' as Provenance],
    fournisseur_id: [''],
    piece_reference: [''],
    departement_id: [''],
    departement_autre: [''],
    service_id: [''],
    service_autre: [''],
    agence_id: [''],
    remis_par: [''],
    motif_id: ['', Validators.required],
    observation: [''],
  });

  private readonly valeurs = toSignal(this.form.valueChanges, { initialValue: this.form.getRawValue() });

  readonly hasUnsavedChanges = unsavedChanges(() => this.form.dirty && !this.saving(), () => this.form);

  readonly articles = computed(() => this.ref()?.articles ?? []);
  readonly article = computed(() => this.articles().find((a) => a.id === this.valeurs().article_id) ?? null);
  readonly motif = computed(() => this.ref()?.motifs.find((m) => m.id === this.valeurs().motif_id) ?? null);
  readonly provenance = computed<Provenance>(() => this.valeurs().provenance_type ?? 'FOURNISSEUR');
  readonly departementId = computed(() => this.valeurs().departement_id || '');
  readonly departementAutre = computed(() => this.departementId() === AUTRE);
  readonly serviceAutre = computed(() => this.valeurs().service_id === AUTRE);
  protected readonly AUTRE = AUTRE;
  readonly observationObligatoire = computed(() => !!this.motif()?.observation_obligatoire || this.provenance() === 'AUTRE');
  readonly stockApres = computed(() => {
    const a = this.article();
    const q = Number(this.valeurs().quantite);
    return a && Number.isFinite(q) && q > 0 ? Math.round((a.stock_actuel + q) * 1000) / 1000 : null;
  });
  readonly depasseMax = computed(() => {
    const a = this.article();
    const apres = this.stockApres();
    return !!a && a.stock_max != null && a.stock_max > 0 && apres !== null && apres > a.stock_max;
  });
  readonly fournisseurHabituel = computed(() => {
    const nom = (this.article()?.fournisseur_habituel || '').trim().toLowerCase();
    if (!nom) return null;
    return this.ref()?.fournisseurs.find((f) => f.raison_sociale.trim().toLowerCase() === nom) ?? null;
  });
  readonly departements = computed(() => {
    const types = new Set(this.ref()?.types_departement ?? []);
    return this.entites().filter((e) => types.has(e.type_entite));
  });
  readonly services = computed(() => {
    const racine = this.departementId();
    if (!racine) return [];
    const types = new Set(this.ref()?.types_service ?? []);
    const sousArbre = new Set([racine]);
    for (const e of this.entites()) {
      if (e.parent_id && sousArbre.has(e.parent_id)) sousArbre.add(e.id);
    }
    return this.entites().filter((e) => e.id !== racine && sousArbre.has(e.id) && types.has(e.type_entite));
  });

  constructor() {
    this.form.controls.provenance_type.valueChanges.subscribe((type) => {
      const garder = {
        FOURNISSEUR: ['fournisseur_id', 'piece_reference'],
        RETOUR_DEPARTEMENT: ['departement_id', 'departement_autre', 'service_id', 'service_autre'],
        RETOUR_AGENCE: ['agence_id'],
        AUTRE: [],
      }[type] as string[];
      const effacer: Record<string, string> = {};
      for (const c of [
        'fournisseur_id',
        'piece_reference',
        'departement_id',
        'departement_autre',
        'service_id',
        'service_autre',
        'agence_id',
      ]) {
        if (!garder.includes(c)) effacer[c] = '';
      }
      this.form.patchValue(effacer, { emitEvent: false });
      this.proposerMotif(type);
      this.form.updateValueAndValidity();
    });
    this.form.controls.departement_id.valueChanges.subscribe((id) => {
      this.form.patchValue({ service_id: '', service_autre: '' }, { emitEvent: false });
      if (id !== AUTRE) this.form.controls.departement_autre.setValue('', { emitEvent: false });
      this.form.updateValueAndValidity();
    });
    this.form.controls.service_id.valueChanges.subscribe((id) => {
      if (id !== AUTRE) this.form.controls.service_autre.setValue('', { emitEvent: false });
    });
    this.form.controls.motif_id.valueChanges.subscribe(() => {
      if (this.form.controls.motif_id.dirty) this.motifAuto = false;
    });
    for (const [nom, ctrl] of Object.entries(this.form.controls) as [string, AbstractControl][]) {
      ctrl.valueChanges.subscribe(() => this.effacerErreurServeur(nom as Champ));
    }
  }

  ngOnInit(): void {
    forkJoin({
      ref: this.api.get<EntreeReferentiels>('/mg/stock/entrees/referentiels'),
      entites: this.org.entitesActives(),
      agences: this.org.agences(),
    }).subscribe({
      next: ({ ref, entites, agences }) => {
        this.ref.set(ref);
        this.entites.set(entites);
        this.agences.set(agences);
        this.proposerMotif(this.form.controls.provenance_type.value);
        this.form.markAsPristine();
        this.chargement.set(false);
      },
      error: (err) => {
        this.chargement.set(false);
        describeApiErrorAsync(err).then((i) => this.feedback.apiError(i, 'Formulaire d’entrée indisponible'));
        this.closed.emit();
      },
    });
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    this.demanderFermeture();
  }

  indent(e: OrgEntiteOption): string {
    return '\u00a0\u00a0'.repeat(Math.max(0, (e.profondeur ?? 0) - 1));
  }

  indentService(e: OrgEntiteOption): string {
    const dep = this.entites().find((d) => d.id === this.departementId());
    return '\u00a0\u00a0'.repeat(Math.max(0, (e.profondeur ?? 0) - (dep?.profondeur ?? 0) - 1));
  }

  erreur(champ: Champ): string | null {
    const serveur = this.erreursServeur()[champ];
    if (serveur) return serveur;
    const visible = this.soumis() || this.form.controls[champ].touched;
    return visible ? this.erreurLocale(champ) : null;
  }

  demanderFermeture(): void {
    if (this.saving()) return;
    if (!this.form.dirty) {
      this.closed.emit();
      return;
    }
    this.dialogs
      .confirmAction('depart', 'L’entrée n’a pas été validée.', undefined, 'Les informations saisies seront perdues.')
      .subscribe((ok) => {
        if (ok) {
          this.form.markAsPristine();
          this.closed.emit();
        }
      });
  }

  valider(): void {
    this.soumis.set(true);
    this.form.markAllAsTouched();
    if (this.premierChampEnErreur()) {
      this.focusPremiereErreur();
      return;
    }
    const v = this.form.getRawValue();
    const article = this.article()!;
    const body: Record<string, unknown> = {
      article_id: v.article_id,
      quantite: Number(v.quantite),
      provenance_type: v.provenance_type,
      motif_id: v.motif_id,
      observation: v.observation.trim() || null,
      remis_par: v.remis_par.trim() || null,
      stock_attendu: article.stock_actuel,
    };
    if (v.provenance_type === 'FOURNISSEUR') {
      body['fournisseur_id'] = v.fournisseur_id;
      if (v.piece_reference.trim()) body['piece_reference'] = v.piece_reference.trim();
    } else if (v.provenance_type === 'RETOUR_DEPARTEMENT') {
      Object.assign(body, corpsOrg(v));
    } else if (v.provenance_type === 'RETOUR_AGENCE') {
      body['agence_id'] = v.agence_id;
    }

    const provenance = this.libelleProvenance();
    const quantite = `${formatQuantite(Number(v.quantite))} ${article.uom}`;
    const piece = v.provenance_type === 'FOURNISSEUR' ? v.piece_reference.trim() : '';
    this.feedback
      .run(() => this.api.post<EntreeMouvement>('/mg/stock/entrees', body), {
        confirm: {
          action: 'validation',
          title: 'Valider l’entrée de stock',
          message: `Entrer ${quantite} de « ${article.designation} » (${provenance}) ?`,
          hint: `Motif : ${this.motif()?.libelle}${piece ? ` · pièce ${piece}` : ''}. Le stock sera incrémenté immédiatement.`,
        },
        loading: 'Validation de l’entrée…',
        busy: this.saving,
        idempotent: true,
        errorTitle: 'Entrée refusée',
        errorHint: 'Vos données saisies ont été conservées.',
        onError: (e) => this.surErreur(e),
        success: (m) => ({
          title: 'Entrée validée',
          details: [
            { label: 'Référence', value: m.reference },
            { label: 'Article', value: `${m.article_code ?? article.code} — ${m.article_designation ?? article.designation}` },
            { label: 'Quantité', value: quantite },
            { label: 'Provenance', value: m.provenance_libelle || provenance },
            ...(m.piece_reference ? [{ label: 'Pièce', value: m.piece_reference }] : []),
            { label: 'Reçu par', value: m.initiateur_nom || this.ref()?.utilisateur.nom || '—' },
          ],
        }),
      })
      .subscribe((m) => {
        this.form.markAsPristine();
        this.saved.emit(m);
      });
  }

  private proposerMotif(type: Provenance): void {
    if (!this.motifAuto) return;
    const code = MOTIF_PAR_PROVENANCE[type];
    const motif = this.ref()?.motifs.find((m) => m.code === code);
    this.form.controls.motif_id.setValue(motif?.id ?? '', { emitEvent: false });
  }

  private libelleProvenance(): string {
    const v = this.form.getRawValue();
    switch (v.provenance_type) {
      case 'FOURNISSEUR':
        return this.ref()?.fournisseurs.find((f) => f.id === v.fournisseur_id)?.raison_sociale ?? 'fournisseur';
      case 'RETOUR_AGENCE':
        return `retour ${this.agences().find((a) => a.id === v.agence_id)?.libelle ?? 'agence'}`;
      case 'RETOUR_DEPARTEMENT':
        return `retour ${libelleOrg(v, this.entites(), 'département')}`;
      default:
        return LIBELLE_PROVENANCE.AUTRE.toLowerCase();
    }
  }

  private surErreur(e: ApiErrorInfo): void {
    const champ = CHAMP_PAR_CODE[e.code];
    if (champ) this.erreursServeur.update((m) => ({ ...m, [champ]: e.message }));
    if (['STOCK_MODIFIE', 'ARTICLE_INACTIF', 'MOTIF_INVALIDE', 'FOURNISSEUR_INVALIDE'].includes(e.code)) {
      this.api.get<EntreeReferentiels>('/mg/stock/entrees/referentiels').subscribe({
        next: (ref) => this.ref.set(ref),
      });
    }
  }

  private effacerErreurServeur(champ: Champ): void {
    if (!this.erreursServeur()[champ]) return;
    this.erreursServeur.update((m) => {
      const next = { ...m };
      delete next[champ];
      return next;
    });
  }

  private erreurLocale(champ: Champ): string | null {
    const v = this.form.getRawValue();
    switch (champ) {
      case 'article_id':
        return v.article_id ? null : 'Sélectionnez l’article reçu.';
      case 'quantite': {
        const q = Number(v.quantite);
        const a = this.article();
        if (v.quantite === null || !Number.isFinite(q) || q <= 0) return 'La quantité doit être strictement positive.';
        if (a?.quantite_entiere && !Number.isInteger(q)) return `Article compté à l’unité (${a.uom}) : quantité entière.`;
        return null;
      }
      case 'fournisseur_id':
        return v.provenance_type === 'FOURNISSEUR' && !v.fournisseur_id ? 'Choisissez le fournisseur.' : null;
      case 'departement_id':
        return v.provenance_type === 'RETOUR_DEPARTEMENT' && !v.departement_id
          ? 'Choisissez le département qui retourne l’article.'
          : null;
      case 'departement_autre':
        return v.provenance_type === 'RETOUR_DEPARTEMENT' && v.departement_id === AUTRE
          ? erreurAutre(v.departement_autre, 'département', this.entites())
          : null;
      case 'service_autre':
        return v.provenance_type === 'RETOUR_DEPARTEMENT' && v.service_id === AUTRE
          ? erreurAutre(v.service_autre, 'service', this.entites())
          : null;
      case 'agence_id':
        return v.provenance_type === 'RETOUR_AGENCE' && !v.agence_id ? 'Choisissez l’agence qui retourne l’article.' : null;
      case 'motif_id':
        return v.motif_id ? null : 'Choisissez le motif de l’entrée.';
      case 'observation':
        if (v.observation.trim() || !this.observationObligatoire()) return null;
        return v.provenance_type === 'AUTRE'
          ? 'Précisez l’origine de l’entrée.'
          : `Le motif « ${this.motif()?.libelle} » exige une observation.`;
      default:
        return null;
    }
  }

  private premierChampEnErreur(): Champ | null {
    const ordre: Champ[] = [
      'article_id',
      'quantite',
      'fournisseur_id',
      'departement_id',
      'departement_autre',
      'service_id',
      'service_autre',
      'agence_id',
      'motif_id',
      'observation',
    ];
    return ordre.find((c) => this.erreurLocale(c) || this.erreursServeur()[c]) ?? null;
  }

  private focusPremiereErreur(): void {
    setTimeout(() => {
      const el = document.querySelector<HTMLElement>('.bea-sortie [aria-invalid="true"]');
      el?.focus();
    });
  }
}
