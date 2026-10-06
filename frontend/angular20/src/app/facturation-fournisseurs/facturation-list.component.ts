import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { Subject, debounceTime } from 'rxjs';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { FactureActionInitiale, FactureDrawerComponent } from './facture-drawer.component';
import { FactureFormComponent } from './facture-form.component';
import {
  ACTION_LABELS,
  FX_BASE,
  FactureDetail,
  FacturePage,
  FactureRow,
  actionsFacture,
  facturePayable,
  factureModifiable,
  factureSupprimable,
  MOIS,
  TYPE_POINT_ICONS,
  VUES,
  annees,
  dateFr,
  fxStatut,
  fxTone,
  joursLabel,
  nettoyer,
  telechargerBlob,
} from './facturation.models';
import { FacturationStore } from './facturation.store';
import { RowMenu, RowMenuComponent, RowMenuItem } from '../contrats-echeances/shared/row-menu';

const FILTRES_VIDES = {
  q: '',
  year: null as number | null,
  month: null as number | null,
  supplier_id: '',
  profil_id: '',
  agency_id: '',
  type: '',
  pdv_id: '',
  statut: '',
  statut_paiement: '',
  type_facture: '',
  echeance: '',
  date_from: '',
  date_to: '',
};

@Component({
  selector: 'bea-fx-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, MontantPipe, FactureDrawerComponent, FactureFormComponent, RowMenuComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances · Factures</p>
          <h1>Facturation</h1>
          <p class="bea-ct-head__sub">Registre unique des factures (agences, sièges, PDV Amanty, autres fournisseurs) : saisie, facture scannée, validation, paiement.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap().create) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouvelle()"><mat-icon>post_add</mat-icon> Nouvelle facture</button>
          }
          <div class="bea-fx-export">
            @if (store.cap().export || store.cap().reports) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="exportBusy()" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="exportBusy()" (click)="exporter('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
            }
          </div>
        </div>
      </header>

      <nav class="bea-ct-tabs bea-fx-vues" aria-label="Vues de facturation">
        @for (v of vues; track v.code) {
          <button type="button" class="bea-ct-tab" [class.is-on]="vue() === v.code" (click)="choisirVue(v.code)">
            <mat-icon>{{ v.icon }}</mat-icon> {{ v.label }}
            @if (compteurs()[v.code] !== undefined) { <span class="bea-fx-count" [attr.data-vue]="v.code">{{ compteurs()[v.code] }}</span> }
          </button>
        }
      </nav>

      <form class="bea-mg__search bea-ct-filters bea-fx-filters" [formGroup]="filtres" (ngSubmit)="rechercher()">
        <label class="bea-mg__field bea-fx-q">Recherche
          <span class="bea-fx-q__box">
            <mat-icon>search</mat-icon>
            <input formControlName="q" type="search" placeholder="Référence SOMELEC, n° facture, point, agence, montant, mois, statut…" (input)="saisie$.next()" />
          </span>
        </label>
        <label class="bea-mg__field">Année
          <select formControlName="year" (change)="rechercher()">
            <option [ngValue]="null">Toutes</option>
            @for (a of annees; track a) { <option [ngValue]="a">{{ a }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Mois
          <select formControlName="month" (change)="rechercher()">
            <option [ngValue]="null">Tous</option>
            @for (m of mois; track $index) { <option [ngValue]="$index + 1">{{ m }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Fournisseur
          <select formControlName="supplier_id" (change)="rechercher()">
            <option value="">Tous</option>
            @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Profil
          <select formControlName="profil_id" (change)="rechercher()">
            <option value="">Tous</option>
            @for (p of store.ref()?.profils ?? []; track p.id) { <option [value]="p.id">{{ p.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Statut
          <select formControlName="statut" (change)="rechercher()">
            <option value="">Tous</option>
            @for (s of store.config()?.statuts ?? []; track s.code) { <option [value]="s.code">{{ s.libelle }}</option> }
          </select>
        </label>
        <div class="bea-ct-filters__btns">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="avance.set(!avance())">
            <mat-icon>tune</mat-icon> Filtres @if (nbAvances()) { <span class="bea-fx-count">{{ nbAvances() }}</span> }
          </button>
          @if (filtresActifs()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()"><mat-icon>filter_alt_off</mat-icon></button>
          }
        </div>
        @if (avance()) {
          <div class="bea-fx-filters__more">
            @if (!store.config()?.agence_scope) {
              <label class="bea-mg__field">Agence
                <select formControlName="agency_id" (change)="rechercher()">
                  <option value="">Toutes</option>
                  @for (a of store.ref()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
                </select>
              </label>
            }
            <label class="bea-mg__field">Type de site
              <select formControlName="type" (change)="rechercher()">
                <option value="">Tous</option>
                @for (t of store.config()?.types_point ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Point / PDV
              <select formControlName="pdv_id" (change)="rechercher()">
                <option value="">Tous</option>
                @for (p of points(); track p.id) { <option [value]="p.id">{{ p.nom }} · {{ p.reference_fournisseur }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Paiement
              <select formControlName="statut_paiement" (change)="rechercher()">
                <option value="">Tous</option>
                @for (s of store.config()?.statuts_paiement ?? []; track s.code) { <option [value]="s.code">{{ s.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Type de facture
              <select formControlName="type_facture" (change)="rechercher()">
                <option value="">Tous</option>
                @for (t of store.config()?.types_facture ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
              </select>
            </label>
            <label class="bea-mg__field">Échéance
              <select formControlName="echeance" (change)="rechercher()">
                <option value="">Toutes</option>
                <option value="retard">En retard</option>
                <option value="j7">≤ 7 jours</option>
                <option value="j30">≤ 30 jours</option>
                <option value="plus30">&gt; 30 jours</option>
                <option value="sans">Sans échéance</option>
              </select>
            </label>
            <label class="bea-mg__field">Du <input type="date" formControlName="date_from" (change)="rechercher()" /></label>
            <label class="bea-mg__field">Au <input type="date" formControlName="date_to" (change)="rechercher()" /></label>
          </div>
        }
      </form>

      <div class="bea-mg__panel bea-ct-panel">
        <div class="bea-fx-totaux">
          <span><strong>{{ page()?.total ?? 0 }}</strong> facture{{ (page()?.total ?? 0) > 1 ? 's' : '' }}</span>
          <span>Montant <strong>{{ page()?.montant_total ?? 0 | montant }}</strong></span>
          <span>Reste à payer <strong class="bea-ct-neg">{{ page()?.reste_total ?? 0 | montant }}</strong></span>
          @if (chargement()) { <span class="bea-fx-spin"><mat-icon>autorenew</mat-icon></span> }
        </div>

        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-fx-table bea-fx-table--fit">
            <thead>
              <tr>
                <th><button type="button" class="bea-fx-sort" (click)="trier('reference')">Référence <mat-icon>{{ icone('reference') }}</mat-icon></button></th>
                <th>Point / site</th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('fournisseur')">Fournisseur <mat-icon>{{ icone('fournisseur') }}</mat-icon></button></th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('agence')">Agence <mat-icon>{{ icone('agence') }}</mat-icon></button></th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('periode')">Période <mat-icon>{{ icone('periode') }}</mat-icon></button></th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('date_facture')">Date <mat-icon>{{ icone('date_facture') }}</mat-icon></button></th>
                <th class="is-num"><button type="button" class="bea-fx-sort" (click)="trier('montant')">Montant <mat-icon>{{ icone('montant') }}</mat-icon></button></th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('statut')">Statut <mat-icon>{{ icone('statut') }}</mat-icon></button></th>
                <th class="is-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @if (page() === null) {
                @for (i of [1, 2, 3, 4, 5, 6]; track i) {
                  <tr class="bea-fx-skelrow"><td colspan="9"><span class="bea-fx-skel bea-fx-skel--line"></span></td></tr>
                }
              } @else {
                @for (r of page()!.items; track r.id; let i = $index) {
                  <tr class="bea-fx-row" [class.is-active]="factureId() === r.id" [style.animation-delay.ms]="i < 20 ? i * 18 : 0" (click)="ouvrir(r.id)">
                    <td>
                      <strong class="bea-fx-ref">{{ r.reference }}</strong>
                      @if (r.numero_fournisseur) { <small class="bea-fx-sub">N° {{ r.numero_fournisseur }}</small> }
                    </td>
                    <td>
                      @if (r.point_nom) {
                        <span class="bea-fx-site"><mat-icon>{{ iconeSite(r.type_point) }}</mat-icon> {{ r.point_nom }}</span>
                        <small class="bea-fx-sub">{{ r.reference_fournisseur }}</small>
                      } @else { <span class="bea-fx-sub">—</span> }
                    </td>
                    <td>{{ r.profil || r.fournisseur || '—' }}@if (r.profil && r.fournisseur) { <small class="bea-fx-sub">{{ r.fournisseur }}</small> }</td>
                    <td>{{ r.agence || '—' }}</td>
                    <td>{{ r.periode_label || '—' }}</td>
                    <td>
                      {{ date(r.date_facture) }}
                      @if (r.date_echeance) { <small class="bea-fx-sub">Éch. {{ date(r.date_echeance) }}</small> }
                      @if (r.etat_echeance === 'EN_RETARD' || r.etat_echeance === 'PROCHE') {
                        <small class="bea-fx-sub" [class.bea-ct-neg]="r.etat_echeance === 'EN_RETARD'">{{ jours(r.jours_echeance) }}</small>
                      }
                    </td>
                    <td class="is-num">
                      @if (r.montant_a_payer !== null) { {{ r.montant_a_payer | montant }} <small>{{ r.devise }}</small> } @else { <span class="bea-fx-sub">Non saisi</span> }
                      @if ((r.reste ?? 0) > 0) { <small class="bea-fx-sub bea-ct-neg">Reste {{ r.reste | montant }}</small> }
                    </td>
                    <td>
                      <span class="bea-ct-badge" [attr.data-tone]="tone(r.statut_affiche)">{{ statut(r.statut_affiche) }}</span>
                      @if (r.nb_documents) { <mat-icon class="bea-fx-clip" title="Pièces jointes">attach_file</mat-icon> }
                    </td>
                    <td class="is-nowrap" (click)="$event.stopPropagation()">
                      <span class="bea-row-actions">
                        <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="ouvrir(r.id)"><mat-icon>visibility</mat-icon></button>
                        @if (modifiable(r)) {
                          <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="ouvrir(r.id, 'modifier')"><mat-icon>edit</mat-icon></button>
                        }
                        @if (payable(r)) {
                          <button type="button" class="bea-mg__icon-btn" title="Enregistrer un paiement" (click)="ouvrir(r.id, 'payer')"><mat-icon>payments</mat-icon></button>
                        }
                        <button type="button" class="bea-mg__icon-btn" title="Plus d'actions" aria-haspopup="menu" (click)="menuFacture($event, r)"><mat-icon>more_vert</mat-icon></button>
                      </span>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="9">
                      <div class="bea-ct-empty">
                        <mat-icon>receipt_long</mat-icon>
                        <p>Aucune facture ne correspond.</p>
                        @if (filtresActifs()) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()">Effacer les filtres</button> }
                        @else if (store.cap().create) { <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouvelle()"><mat-icon>post_add</mat-icon> Saisir une facture</button> }
                      </div>
                    </td>
                  </tr>
                }
              }
            </tbody>
          </table>
        </div>

        @if (pages() > 1) {
          <div class="bea-fx-pager">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="numero() <= 1" (click)="aller(numero() - 1)"><mat-icon>chevron_left</mat-icon></button>
            <span>Page {{ numero() }} / {{ pages() }}</span>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="numero() >= pages()" (click)="aller(numero() + 1)"><mat-icon>chevron_right</mat-icon></button>
            <select [value]="taille()" (change)="changerTaille($event)" aria-label="Lignes par page">
              @for (n of [25, 50, 100]; track n) { <option [value]="n">{{ n }} / page</option> }
            </select>
          </div>
        }
      </div>
      <p class="bea-ct-help"><mat-icon>info</mat-icon> Les montants non saisis restent vides : ils ne sont jamais estimés. <a class="bea-ct-link" [routerLink]="base">Vue 360°</a></p>
    </section>

    @if (factureId(); as id) {
      <bea-fx-facture-drawer [factureId]="id" [actionInitiale]="actionInitiale()" (closed)="fermer()" (changed)="charger(true)" />
    }
    <bea-row-menu [menu]="rowMenu" />
    @if (formOuvert()) {
      <bea-fx-facture-form [preset]="preset()" (saved)="apresCreation($event)" (closed)="formOuvert.set(false)" />
    }
  `,
})
export class FacturationListComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly base = FX_BASE;
  readonly vues = VUES;
  readonly annees = annees();
  readonly mois = MOIS;

  readonly vue = signal('toutes');
  readonly page = signal<FacturePage | null>(null);
  readonly compteurs = signal<Record<string, number>>({});
  readonly chargement = signal(false);
  readonly exportBusy = signal(false);
  readonly avance = signal(false);
  readonly tri = signal('-date_facture');
  readonly numero = signal(1);
  readonly taille = signal(25);
  readonly factureId = signal<string | null>(null);
  readonly actionInitiale = signal<FactureActionInitiale | null>(null);
  readonly rowMenu = new RowMenu();
  readonly formOuvert = signal(false);
  readonly preset = signal<{ point_facturation_id?: string; annee?: number; mois?: number } | null>(null);
  readonly saisie$ = new Subject<void>();
  private readonly valeurs = signal<typeof FILTRES_VIDES>({ ...FILTRES_VIDES });
  private readonly drawer = viewChild(FactureDrawerComponent);
  private readonly form = viewChild(FactureFormComponent);

  readonly hasUnsavedChanges = () => !!this.form()?.isDirty() || !!this.drawer()?.dirty();

  readonly filtres = this.fb.nonNullable.group({ ...FILTRES_VIDES });

  readonly pages = computed(() => {
    const p = this.page();
    return p ? Math.max(1, Math.ceil(p.total / p.page_size)) : 1;
  });

  readonly points = computed(() => {
    const t = this.valeurs().type;
    return (this.store.ref()?.points ?? []).filter((p) => !t || p.type_point === t);
  });

  readonly nbAvances = computed(() => {
    const v = this.valeurs();
    return ['agency_id', 'type', 'pdv_id', 'statut_paiement', 'type_facture', 'echeance', 'date_from', 'date_to'].filter((k) => !!v[k as keyof typeof v]).length;
  });

  readonly filtresActifs = computed(() => Object.values(this.valeurs()).some((x) => x !== '' && x !== null));

  ngOnInit(): void {
    this.store.charger();
    this.saisie$.pipe(debounceTime(350), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.rechercher());
    const q = this.route.snapshot.queryParamMap;
    const patch: Partial<typeof FILTRES_VIDES> = {};
    for (const k of Object.keys(FILTRES_VIDES) as (keyof typeof FILTRES_VIDES)[]) {
      const v = q.get(k === 'statut' && !q.get('statut') ? 'status' : k);
      if (v === null) continue;
      (patch as Record<string, unknown>)[k] = k === 'year' || k === 'month' ? Number(v) || null : v;
    }
    this.filtres.patchValue(patch);
    this.vue.set(q.get('vue') ?? 'toutes');
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((m) => {
      this.factureId.set(m.get('facture'));
      if (m.get('nouvelle') && this.store.cap().create !== false) {
        this.preset.set({
          point_facturation_id: m.get('point') ?? undefined,
          annee: Number(m.get('annee')) || undefined,
          mois: Number(m.get('mois')) || undefined,
        });
        this.formOuvert.set(true);
      }
    });
    this.charger();
    if (this.nbAvances()) this.avance.set(true);
  }

  private params(): Record<string, string> {
    return nettoyer({ ...this.filtres.getRawValue(), vue: this.vue() === 'toutes' ? '' : this.vue() });
  }

  private syncUrl(): void {
    const facture = this.factureId();
    this.router.navigate([], { queryParams: { ...this.params(), ...(facture ? { facture } : {}) }, replaceUrl: true });
  }

  charger(compteurs = true): void {
    this.valeurs.set(this.filtres.getRawValue());
    this.chargement.set(true);
    this.api
      .get<FacturePage>('/mg/factures', { ...this.params(), page: String(this.numero()), page_size: String(this.taille()), sort: this.tri() })
      .subscribe({
        next: (p) => {
          this.page.set(p);
          this.chargement.set(false);
        },
        error: (e) => {
          this.chargement.set(false);
          this.page.set({ items: [], total: 0, page: 1, page_size: this.taille(), montant_total: 0, reste_total: 0 });
          void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Liste des factures indisponible'));
        },
      });
    if (compteurs) {
      this.api.get<Record<string, number>>('/mg/factures/compteurs').subscribe({ next: (c) => this.compteurs.set(c), error: () => undefined });
    }
  }

  rechercher(): void {
    this.numero.set(1);
    this.syncUrl();
    this.charger(false);
  }

  choisirVue(code: string): void {
    this.vue.set(code);
    this.rechercher();
  }

  reinitialiser(): void {
    this.filtres.reset({ ...FILTRES_VIDES });
    this.rechercher();
  }

  trier(col: string): void {
    this.tri.set(this.tri() === `-${col}` ? col : `-${col}`);
    this.charger(false);
  }

  icone(col: string): string {
    if (this.tri() === col) return 'arrow_upward';
    if (this.tri() === `-${col}`) return 'arrow_downward';
    return 'unfold_more';
  }

  aller(n: number): void {
    this.numero.set(n);
    this.charger(false);
  }

  changerTaille(e: Event): void {
    this.taille.set(Number((e.target as HTMLSelectElement).value) || 25);
    this.numero.set(1);
    this.charger(false);
  }

  ouvrir(id: string, action: FactureActionInitiale | null = null): void {
    this.actionInitiale.set(action);
    this.factureId.set(id);
    this.syncUrl();
  }

  fermer(): void {
    this.actionInitiale.set(null);
    this.factureId.set(null);
    this.syncUrl();
  }

  modifiable(r: FactureRow): boolean {
    return factureModifiable(r, this.store.cap());
  }

  payable(r: FactureRow): boolean {
    return facturePayable(r, this.store.cap());
  }

  menuFacture(ev: MouseEvent, r: FactureRow): void {
    const cap = this.store.cap();
    const items: RowMenuItem[] = actionsFacture(r, cap).map((a) => ({
      icone: ACTION_LABELS[a]?.icon ?? 'bolt',
      label: ACTION_LABELS[a]?.label ?? a,
      danger: a === 'annuler',
      action: () => this.ouvrir(r.id, a),
    }));
    if (cap.documents_view) items.push({ icone: 'folder_open', label: 'Documents', action: () => this.ouvrir(r.id, 'documents') });
    if (cap.payment_view) items.push({ icone: 'payments', label: 'Paiements', action: () => this.ouvrir(r.id, 'paiements') });
    items.push({ icone: 'history', label: 'Historique', action: () => this.ouvrir(r.id, 'historique') });
    if (cap.create) items.push({ icone: 'content_copy', label: 'Dupliquer (période suivante)', action: () => this.ouvrir(r.id, 'dupliquer') });
    if (factureSupprimable(r, cap)) items.push({ icone: 'delete', label: 'Supprimer', danger: true, action: () => this.ouvrir(r.id, 'supprimer') });
    this.rowMenu.ouvrir(ev, items);
  }

  nouvelle(): void {
    this.preset.set(null);
    this.formOuvert.set(true);
  }

  apresCreation(f: FactureDetail): void {
    this.formOuvert.set(false);
    this.charger(true);
    this.ouvrir(f.id);
  }

  exporter(format: 'xlsx' | 'pdf'): void {
    const stamp = new Date().toISOString().slice(0, 10);
    this.feedback
      .run(() => this.api.download('/mg/factures/rapports/factures', { ...this.params(), format }), {
        loading: 'Préparation de l’export…',
        busy: this.exportBusy,
        errorTitle: 'Export impossible',
        success: (blob) => {
          telechargerBlob(blob, `factures_${stamp}.${format}`);
          return { title: 'Export prêt', message: 'Le fichier a été téléchargé.' };
        },
      })
      .subscribe();
  }

  iconeSite(type: string | null): string {
    return TYPE_POINT_ICONS[type ?? ''] ?? 'place';
  }

  statut(code: string | null | undefined): string {
    return fxStatut(code);
  }

  tone(code: string | null | undefined): string {
    return fxTone(code);
  }

  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }

  jours(j: number | null | undefined): string {
    return joursLabel(j);
  }
}
