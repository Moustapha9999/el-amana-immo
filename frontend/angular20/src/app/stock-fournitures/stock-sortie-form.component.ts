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
import { StockMouvementRow } from './stock-mouvement-edit.component';

export interface SortieArticle {
  id: string;
  code: string;
  designation: string;
  uom: string;
  stock_actuel: number;
  quantite_entiere: boolean;
}

export interface SortieMotif {
  id: string;
  code: string;
  libelle: string;
  observation_obligatoire: boolean;
}

interface SortieReferentiels {
  articles: SortieArticle[];
  motifs: SortieMotif[];
  demandeur_libre: boolean;
  types_departement: string[];
  types_service: string[];
  utilisateur: { id: string; nom: string };
}

interface Demandeur {
  id: string;
  nom: string;
  email: string;
  entite: string | null;
}

export interface SortieMouvement extends StockMouvementRow {
  destination_libelle?: string | null;
  demandeur_nom?: string | null;
  initiateur_nom?: string | null;
}

type Champ =
  | 'article_id'
  | 'quantite'
  | 'departement_id'
  | 'service_id'
  | 'agence_id'
  | 'demandeur'
  | 'motif_id'
  | 'observation';

/** Code d'erreur métier backend → champ du formulaire concerné. */
const CHAMP_PAR_CODE: Record<string, Champ> = {
  ARTICLE_INTROUVABLE: 'article_id',
  ARTICLE_INACTIF: 'article_id',
  QUANTITE_INVALIDE: 'quantite',
  QUANTITE_ENTIERE: 'quantite',
  STOCK_INSUFFISANT: 'quantite',
  STOCK_MODIFIE: 'quantite',
  DEPARTEMENT_OBLIGATOIRE: 'departement_id',
  DEPARTEMENT_INVALIDE: 'departement_id',
  SERVICE_INVALIDE: 'service_id',
  SERVICE_HORS_DEPARTEMENT: 'service_id',
  AGENCE_OBLIGATOIRE: 'agence_id',
  AGENCE_INVALIDE: 'agence_id',
  DEMANDEUR_OBLIGATOIRE: 'demandeur',
  DEMANDEUR_INVALIDE: 'demandeur',
  DEMANDEUR_REFERENCE_REQUIS: 'demandeur',
  MOTIF_INVALIDE: 'motif_id',
  OBSERVATION_OBLIGATOIRE: 'observation',
};

/**
 * Formulaire « Nouvelle sortie de stock » : destination Département / Service ou Agence
 * (référentiels CORE), demandeur distinct de l'exécutant, motif configurable.
 * Les règles sont revérifiées côté serveur (`POST /mg/stock/sorties`).
 */
@Component({
  selector: 'bea-stock-sortie-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, QuantitePipe],
  template: `
    <div class="bea-mg__backdrop" (click)="demanderFermeture()" role="presentation"></div>
    <div class="bea-mg__modal bea-mg__modal--lg bea-sortie" role="dialog" aria-modal="true" aria-labelledby="sortie-title">
      <header class="bea-mg__modal-head">
        <div>
          <p class="bea-stock-page__kicker">Stock &amp; Fournitures · Sorties</p>
          <h2 id="sortie-title">Nouvelle sortie de stock</h2>
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
                  @else if (!articles().length) { <small class="bea-sortie__hint">Aucun article actif avec du stock disponible.</small> }
                </label>
                <label>
                  Quantité *
                  <input
                    type="number"
                    formControlName="quantite"
                    min="0"
                    [step]="article()?.quantite_entiere === false ? 0.001 : 1"
                    [attr.max]="article()?.stock_actuel ?? null"
                    [attr.aria-invalid]="!!erreur('quantite')"
                  />
                  @if (erreur('quantite'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                  @else { <small class="bea-sortie__hint">Strictement positive, au plus le stock disponible.</small> }
                </label>
                <div class="bea-sortie__stock" [attr.data-alerte]="stockApres() !== null && stockApres()! < 0">
                  @if (article(); as a) {
                    <span>Stock disponible <strong>{{ a.stock_actuel | quantite }} {{ a.uom }}</strong></span>
                    @if (stockApres() !== null && stockApres()! >= 0) {
                      <span>Après sortie <strong>{{ stockApres() | quantite }} {{ a.uom }}</strong></span>
                    }
                  } @else {
                    <span>Choisissez un article pour voir son stock.</span>
                  }
                </div>
              </div>
            </fieldset>

            <fieldset class="bea-sortie__section">
              <legend><span>2</span> Destination de l’article</legend>
              <div class="bea-sortie__toggle" role="radiogroup" aria-label="Type de destination">
                <label [class.is-on]="destination() === 'DEPARTEMENT'">
                  <input type="radio" formControlName="destination_type" value="DEPARTEMENT" />
                  <mat-icon>account_tree</mat-icon> Département / Service
                </label>
                <label [class.is-on]="destination() === 'AGENCE'">
                  <input type="radio" formControlName="destination_type" value="AGENCE" />
                  <mat-icon>storefront</mat-icon> Agence
                </label>
              </div>
              <div class="bea-mg__grid">
                @if (destination() === 'DEPARTEMENT') {
                  <label>
                    Département *
                    <select formControlName="departement_id" [attr.aria-invalid]="!!erreur('departement_id')">
                      <option value="">Choisir le département</option>
                      @for (d of departements(); track d.id) {
                        <option [value]="d.id">{{ indent(d) }}{{ d.libelle }}{{ d.sigle ? ' (' + d.sigle + ')' : '' }}{{ d.a_confirmer ? ' — à confirmer' : '' }}</option>
                      }
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
                    </select>
                    @if (erreur('service_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                    @else { <small class="bea-sortie__hint">Limité aux services du département choisi.</small> }
                  </label>
                } @else {
                  <label class="bea-mg__span2">
                    Agence destinataire *
                    <select formControlName="agence_id" [attr.aria-invalid]="!!erreur('agence_id')">
                      <option value="">Choisir l’agence</option>
                      @for (a of agences(); track a.id) {
                        <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option>
                      }
                    </select>
                    @if (erreur('agence_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                  </label>
                }
              </div>
            </fieldset>

            <fieldset class="bea-sortie__section">
              <legend><span>3</span> Demande et justification</legend>
              <div class="bea-mg__grid">
                <div class="bea-mg__span2 bea-sortie__demandeur">
                  <label for="sortie-demandeur">Demandé par *</label>
                  @if (demandeurChoisi(); as d) {
                    <div class="bea-sortie__chip">
                      <mat-icon>person</mat-icon>
                      <span><strong>{{ d.nom }}</strong>{{ d.entite ? ' — ' + d.entite : '' }}</span>
                      <button type="button" class="bea-mg__icon-btn" title="Changer de demandeur" (click)="effacerDemandeur()">
                        <mat-icon>close</mat-icon>
                      </button>
                    </div>
                  } @else {
                    <input
                      id="sortie-demandeur"
                      formControlName="demandeur_nom"
                      autocomplete="off"
                      [placeholder]="ref()?.demandeur_libre ? 'Rechercher un utilisateur ou saisir le nom' : 'Rechercher un utilisateur BEA DIGITAL'"
                      (input)="chercherDemandeur()"
                      [attr.aria-invalid]="!!erreur('demandeur')"
                    />
                    @if (resultats().length) {
                      <ul class="bea-sortie__suggestions" role="listbox">
                        @for (u of resultats(); track u.id) {
                          <li role="option" (mousedown)="$event.preventDefault()" (click)="choisirDemandeur(u)">
                            <strong>{{ u.nom }}</strong>
                            <small>{{ u.entite || u.email }}</small>
                          </li>
                        }
                      </ul>
                    }
                  }
                  @if (erreur('demandeur'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                  @else {
                    <small class="bea-sortie__hint">
                      La personne qui a demandé l’article, et non nécessairement celle qui saisit la sortie.
                      @if (demandeurLibre()) { Personne non référencée : le nom saisi sera enregistré tel quel. }
                    </small>
                  }
                </div>
                <label class="bea-mg__span2">
                  Motif de la sortie *
                  <select formControlName="motif_id" [attr.aria-invalid]="!!erreur('motif_id')">
                    <option value="">Choisir le motif</option>
                    @for (m of ref()?.motifs ?? []; track m.id) {
                      <option [value]="m.id">{{ m.libelle }}</option>
                    }
                  </select>
                  @if (erreur('motif_id'); as e) { <small class="bea-sortie__err">{{ e }}</small> }
                </label>
                <label class="bea-mg__span2">
                  Observations {{ motif()?.observation_obligatoire ? '*' : '(facultatif)' }}
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
                <div><dt>Sorti par</dt><dd>{{ ref()?.utilisateur?.nom || '—' }}</dd></div>
                <div><dt>Date et heure</dt><dd>Générées par le serveur à la validation</dd></div>
                <div><dt>Référence</dt><dd>Numéro unique attribué automatiquement</dd></div>
              </dl>
            </fieldset>
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="demanderFermeture()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="saving()">
              <mat-icon>south_east</mat-icon> {{ saving() ? 'Validation…' : 'Valider la sortie' }}
            </button>
          </footer>
        </form>
      }
    </div>
  `,
  styleUrl: './stock-mouvement-form.css',
})
export class StockSortieFormComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly feedback = inject(FeedbackService);
  private readonly dialogs = inject(UiDialogService);
  private readonly org = inject(OrgReferentielService);

  readonly closed = output<void>();
  readonly saved = output<SortieMouvement>();

  readonly chargement = signal(true);
  readonly saving = signal(false);
  readonly soumis = signal(false);
  readonly ref = signal<SortieReferentiels | null>(null);
  readonly entites = signal<OrgEntiteOption[]>([]);
  readonly agences = signal<OrgAgenceOption[]>([]);
  readonly resultats = signal<Demandeur[]>([]);
  readonly demandeurChoisi = signal<Demandeur | null>(null);
  /** Erreurs renvoyées par le serveur, effacées dès que le champ est modifié. */
  readonly erreursServeur = signal<Partial<Record<Champ, string>>>({});
  private rechercheTimer: ReturnType<typeof setTimeout> | null = null;

  readonly form = this.fb.nonNullable.group({
    article_id: ['', Validators.required],
    quantite: [1 as number | null, Validators.required],
    destination_type: ['DEPARTEMENT' as 'DEPARTEMENT' | 'AGENCE'],
    departement_id: [''],
    service_id: [''],
    agence_id: [''],
    demandeur_id: [''],
    demandeur_nom: [''],
    motif_id: ['', Validators.required],
    observation: [''],
  });

  private readonly valeurs = toSignal(this.form.valueChanges, { initialValue: this.form.getRawValue() });

  readonly hasUnsavedChanges = unsavedChanges(() => this.form.dirty && !this.saving(), () => this.form);

  readonly articles = computed(() => this.ref()?.articles ?? []);
  readonly article = computed(() => this.articles().find((a) => a.id === this.valeurs().article_id) ?? null);
  readonly motif = computed(() => this.ref()?.motifs.find((m) => m.id === this.valeurs().motif_id) ?? null);
  readonly destination = computed(() => this.valeurs().destination_type ?? 'DEPARTEMENT');
  readonly departementId = computed(() => this.valeurs().departement_id || '');
  readonly stockApres = computed(() => {
    const a = this.article();
    const q = Number(this.valeurs().quantite);
    return a && Number.isFinite(q) && q > 0 ? Math.round((a.stock_actuel - q) * 1000) / 1000 : null;
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
  readonly demandeurLibre = computed(
    () => !!this.ref()?.demandeur_libre && !this.demandeurChoisi() && !!(this.valeurs().demandeur_nom || '').trim(),
  );

  constructor() {
    this.form.controls.destination_type.valueChanges.subscribe((type) => {
      if (type === 'AGENCE') {
        this.form.patchValue({ departement_id: '', service_id: '' }, { emitEvent: false });
      } else {
        this.form.patchValue({ agence_id: '' }, { emitEvent: false });
      }
      this.form.updateValueAndValidity();
    });
    this.form.controls.departement_id.valueChanges.subscribe(() => {
      this.form.controls.service_id.setValue('', { emitEvent: false });
    });
    for (const [nom, ctrl] of Object.entries(this.form.controls) as [string, AbstractControl][]) {
      const champ = (nom === 'demandeur_nom' || nom === 'demandeur_id' ? 'demandeur' : nom) as Champ;
      ctrl.valueChanges.subscribe(() => this.effacerErreurServeur(champ));
    }
  }

  ngOnInit(): void {
    forkJoin({
      ref: this.api.get<SortieReferentiels>('/mg/stock/sorties/referentiels'),
      entites: this.org.entitesActives(),
      agences: this.org.agences(),
    }).subscribe({
      next: ({ ref, entites, agences }) => {
        this.ref.set(ref);
        this.entites.set(entites);
        this.agences.set(agences);
        this.chargement.set(false);
      },
      error: (err) => {
        this.chargement.set(false);
        describeApiErrorAsync(err).then((i) => this.feedback.apiError(i, 'Formulaire de sortie indisponible'));
        this.closed.emit();
      },
    });
  }

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.resultats().length) {
      this.resultats.set([]);
      return;
    }
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
    const visible = this.soumis() || this.controle(champ).touched;
    return visible ? this.erreurLocale(champ) : null;
  }

  chercherDemandeur(): void {
    this.form.controls.demandeur_id.setValue('');
    if (this.rechercheTimer) clearTimeout(this.rechercheTimer);
    const q = this.form.controls.demandeur_nom.value.trim();
    if (q.length < 2) {
      this.resultats.set([]);
      return;
    }
    this.rechercheTimer = setTimeout(() => {
      this.api.get<Demandeur[]>('/mg/stock/sorties/demandeurs', { q }).subscribe({
        next: (rows) => this.resultats.set(rows),
        error: () => this.resultats.set([]),
      });
    }, 300);
  }

  choisirDemandeur(u: Demandeur): void {
    this.demandeurChoisi.set(u);
    this.resultats.set([]);
    this.form.patchValue({ demandeur_id: u.id, demandeur_nom: u.nom });
    this.form.markAsDirty();
  }

  effacerDemandeur(): void {
    this.demandeurChoisi.set(null);
    this.form.patchValue({ demandeur_id: '', demandeur_nom: '' });
  }

  demanderFermeture(): void {
    if (this.saving()) return;
    if (!this.form.dirty) {
      this.closed.emit();
      return;
    }
    this.dialogs
      .confirmAction('depart', 'La sortie n’a pas été validée.', undefined, 'Les informations saisies seront perdues.')
      .subscribe((ok) => {
        if (ok) {
          this.form.markAsPristine();
          this.closed.emit();
        }
      });
  }

  valider(): void {
    this.soumis.set(true);
    this.resultats.set([]);
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
      destination_type: v.destination_type,
      motif_id: v.motif_id,
      observation: v.observation.trim() || null,
      stock_attendu: article.stock_actuel,
    };
    if (v.destination_type === 'DEPARTEMENT') {
      body['departement_id'] = v.departement_id;
      if (v.service_id) body['service_id'] = v.service_id;
    } else {
      body['agence_id'] = v.agence_id;
    }
    if (v.demandeur_id) body['demandeur_id'] = v.demandeur_id;
    else body['demandeur_nom'] = v.demandeur_nom.trim();

    const destination = this.libelleDestination();
    const quantite = `${formatQuantite(Number(v.quantite))} ${article.uom}`;
    this.feedback
      .run(() => this.api.post<SortieMouvement>('/mg/stock/sorties', body), {
        confirm: {
          action: 'validation',
          title: 'Valider la sortie de stock',
          message: `Sortir ${quantite} de « ${article.designation} » vers ${destination} ?`,
          hint: `Demandé par ${v.demandeur_nom.trim()} · motif : ${this.motif()?.libelle}. Le stock sera décrémenté immédiatement.`,
        },
        loading: 'Validation de la sortie…',
        busy: this.saving,
        idempotent: true,
        errorTitle: 'Sortie refusée',
        errorHint: 'Vos données saisies ont été conservées.',
        onError: (e) => this.surErreur(e),
        success: (m) => ({
          title: 'Sortie validée',
          details: [
            { label: 'Référence', value: m.reference },
            { label: 'Article', value: `${m.article_code ?? article.code} — ${m.article_designation ?? article.designation}` },
            { label: 'Quantité', value: quantite },
            { label: 'Destination', value: m.destination_libelle || destination },
            { label: 'Demandé par', value: m.demandeur_nom || v.demandeur_nom.trim() },
            { label: 'Sorti par', value: m.initiateur_nom || this.ref()?.utilisateur.nom || '—' },
          ],
        }),
      })
      .subscribe((m) => {
        this.form.markAsPristine();
        this.saved.emit(m);
      });
  }

  private libelleDestination(): string {
    const v = this.form.getRawValue();
    if (v.destination_type === 'AGENCE') {
      return this.agences().find((a) => a.id === v.agence_id)?.libelle ?? 'l’agence';
    }
    const dep = this.entites().find((e) => e.id === v.departement_id)?.libelle ?? 'le département';
    const srv = this.entites().find((e) => e.id === v.service_id)?.libelle;
    return srv ? `${dep} › ${srv}` : dep;
  }

  private surErreur(e: ApiErrorInfo): void {
    const champ = CHAMP_PAR_CODE[e.code];
    if (champ) this.erreursServeur.update((m) => ({ ...m, [champ]: e.message }));
    if (['STOCK_INSUFFISANT', 'STOCK_MODIFIE', 'ARTICLE_INACTIF', 'MOTIF_INVALIDE'].includes(e.code)) {
      this.rafraichirReferentiels();
    }
  }

  /** Recharge stocks et motifs sans toucher à la saisie (stock affiché = stock attendu au prochain envoi). */
  private rafraichirReferentiels(): void {
    this.api.get<SortieReferentiels>('/mg/stock/sorties/referentiels').subscribe({
      next: (ref) => this.ref.set(ref),
    });
  }

  private controle(champ: Champ): AbstractControl {
    return champ === 'demandeur' ? this.form.controls.demandeur_nom : this.form.controls[champ];
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
        return v.article_id ? null : 'Sélectionnez l’article à sortir.';
      case 'quantite': {
        const q = Number(v.quantite);
        const a = this.article();
        if (v.quantite === null || !Number.isFinite(q) || q <= 0) return 'La quantité doit être strictement positive.';
        if (a?.quantite_entiere && !Number.isInteger(q)) return `Article compté à l’unité (${a.uom}) : quantité entière.`;
        if (a && q > a.stock_actuel) {
          return `Stock insuffisant. Stock disponible : ${formatQuantite(a.stock_actuel)} ${a.uom}. Quantité demandée : ${formatQuantite(q)} ${a.uom}.`;
        }
        return null;
      }
      case 'departement_id':
        return v.destination_type === 'DEPARTEMENT' && !v.departement_id ? 'Choisissez le département destinataire.' : null;
      case 'agence_id':
        return v.destination_type === 'AGENCE' && !v.agence_id ? 'Choisissez l’agence destinataire.' : null;
      case 'demandeur': {
        if (v.demandeur_id) return null;
        const nom = v.demandeur_nom.trim();
        if (!this.ref()?.demandeur_libre) return 'Sélectionnez le demandeur dans la liste des utilisateurs.';
        return nom.length >= 3 ? null : 'Indiquez la personne qui a demandé l’article.';
      }
      case 'motif_id':
        return v.motif_id ? null : 'Choisissez le motif de la sortie.';
      case 'observation':
        return this.motif()?.observation_obligatoire && !v.observation.trim()
          ? `Le motif « ${this.motif()?.libelle} » exige une observation.`
          : null;
      default:
        return null;
    }
  }

  private premierChampEnErreur(): Champ | null {
    const ordre: Champ[] = ['article_id', 'quantite', 'departement_id', 'service_id', 'agence_id', 'demandeur', 'motif_id', 'observation'];
    return ordre.find((c) => this.erreurLocale(c) || this.erreursServeur()[c]) ?? null;
  }

  private focusPremiereErreur(): void {
    setTimeout(() => {
      const el = document.querySelector<HTMLElement>('.bea-sortie [aria-invalid="true"]');
      el?.focus();
    });
  }
}
