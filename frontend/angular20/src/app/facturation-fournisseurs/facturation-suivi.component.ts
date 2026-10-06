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
  ALERTE_LABELS,
  actionsFacture,
  factureModifiable,
  facturePayable,
  Bucket,
  FX_BASE,
  FactureDetail,
  FactureRow,
  FxAlerte,
  MOIS,
  annees,
  dateFr,
  detailPaiement,
  fxStatut,
  fxTone,
  joursLabel,
  nettoyer,
  telechargerBlob,
} from './facturation.models';
import { FacturationStore } from './facturation.store';
import { FxPaiementDrawerComponent } from './fx-paiement-drawer.component';
import { PagerComponent, TableState } from '../contrats-echeances/shared/table-state';
import { RowMenu, RowMenuComponent, RowMenuItem } from '../contrats-echeances/shared/row-menu';

type Mode = 'paiements' | 'echeances' | 'alertes';

interface PaiementRow {
  id: string;
  reference: string;
  facture_id: string;
  facture_reference: string;
  numero_fournisseur: string | null;
  periode_label: string | null;
  fournisseur: string | null;
  agence: string | null;
  point_nom: string | null;
  date_paiement: string | null;
  montant: number;
  mode_paiement: string | null;
  reference_paiement: string | null;
  compte: string | null;
  banque: string | null;
  numero_cheque: string | null;
  carte_masquee: string | null;
  statut: string;
  observation: string | null;
}

const TITRES: Record<Mode, { titre: string; sous: string; icon: string }> = {
  paiements: { titre: 'Paiements', sous: 'Règlements enregistrés sur les factures (un ou plusieurs par facture). Une annulation est tracée et recalcule le statut de paiement.', icon: 'payments' },
  echeances: { titre: 'Échéances', sous: 'Factures validées non soldées, classées par date d’échéance.', icon: 'event' },
  alertes: { titre: 'Alertes', sous: 'Factures manquantes, échéances proches, retards, hausses anormales et doublons — calculés en temps réel.', icon: 'notifications_active' },
};

@Component({
  selector: 'bea-fx-suivi',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, MontantPipe, FactureDrawerComponent, FactureFormComponent, FxPaiementDrawerComponent, PagerComponent, RowMenuComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances · Factures</p>
          <h1>{{ titre().titre }}</h1>
          <p class="bea-ct-head__sub">{{ titre().sous }}</p>
        </div>
        <div class="bea-mg__actions">
          @if (mode() === 'paiements' && store.cap().payment_create) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouveauPaiement()"><mat-icon>add_card</mat-icon> Nouveau paiement</button>
          } @else if (mode() !== 'paiements' && store.cap().create) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouvelleFacture()"><mat-icon>post_add</mat-icon> Nouvelle facture</button>
          }
          <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="base"><mat-icon>dashboard</mat-icon> Vue 360°</a>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Actualiser" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      <form class="bea-mg__search bea-ct-filters bea-fx-filters" [formGroup]="filtres">
        @if (mode() !== 'echeances') {
          <label class="bea-mg__field bea-fx-q">Recherche
            <span class="bea-fx-q__box"><mat-icon>search</mat-icon>
              <input formControlName="q" type="search" placeholder="Référence, point, fournisseur…" (input)="saisie$.next()" />
            </span>
          </label>
        }
        @if (mode() === 'paiements') {
          <label class="bea-mg__field">Année
            <select formControlName="year" (change)="charger()">
              <option [ngValue]="null">Toutes</option>
              @for (a of annees; track a) { <option [ngValue]="a">{{ a }}</option> }
            </select>
          </label>
          <label class="bea-mg__field">Mois
            <select formControlName="month" (change)="charger()">
              <option [ngValue]="null">Tous</option>
              @for (m of mois; track $index) { <option [ngValue]="$index + 1">{{ m }}</option> }
            </select>
          </label>
          <label class="bea-mg__field">Mode
            <select formControlName="mode_paiement" (change)="charger()">
              <option value="">Tous</option>
              @for (m of store.config()?.modes_paiement ?? []; track m) { <option [value]="m">{{ m }}</option> }
            </select>
          </label>
          <label class="bea-mg__field">Statut
            <select formControlName="statut" (change)="charger()">
              <option value="">Tous</option>
              <option value="PAYE">Valides</option>
              <option value="ANNULE">Annulés</option>
            </select>
          </label>
        }
        <label class="bea-mg__field">Fournisseur
          <select formControlName="supplier_id" (change)="charger()">
            <option value="">Tous</option>
            @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
          </select>
        </label>
        @if (!store.config()?.agence_scope) {
          <label class="bea-mg__field">Agence
            <select formControlName="agency_id" (change)="charger()">
              <option value="">Toutes</option>
              @for (a of store.ref()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
            </select>
          </label>
        }
        @if (mode() !== 'paiements') {
          <label class="bea-mg__field">Type de site
            <select formControlName="type" (change)="charger()">
              <option value="">Tous</option>
              @for (t of store.config()?.types_point ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
            </select>
          </label>
        }
      </form>

      @switch (mode()) {
        @case ('paiements') {
          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-fx-totaux">
              <span><strong>{{ paiementsValides().length }}</strong> paiement(s) valide(s)</span>
              <span>Total réglé <strong>{{ totalPaye() | montant }}</strong></span>
              @if (paiementsAnnules()) { <span>{{ paiementsAnnules() }} annulé(s)</span> }
              @if (store.cap().export || store.cap().reports) {
                <span class="bea-fx-export">
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!(paiements()?.length) || exportBusy()" (click)="exporterPaiements('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="!(paiements()?.length) || exportBusy()" (click)="exporterPaiements('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
                </span>
              }
            </div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table bea-fx-table">
                <thead><tr><th>Paiement</th><th>Date</th><th>Facture</th><th>Point / fournisseur</th><th>Moyen</th><th>Détail</th><th class="is-num">Montant</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
                <tbody>
                  @if (paiements() === null) {
                    @for (i of [1, 2, 3, 4]; track i) { <tr><td colspan="9"><span class="bea-fx-skel bea-fx-skel--line"></span></td></tr> }
                  } @else {
                    @for (p of tPaiements.lignes(); track p.id; let i = $index) {
                      <tr class="bea-fx-row" [class.is-muted]="p.statut === 'ANNULE'" [style.animation-delay.ms]="i < 20 ? i * 15 : 0">
                        <td><a class="bea-ct-link" (click)="voirPaiement(p)"><strong class="bea-fx-ref">{{ p.reference }}</strong></a></td>
                        <td>{{ date(p.date_paiement) }}</td>
                        <td><a class="bea-ct-link" (click)="ouvrir(p.facture_id)">{{ p.facture_reference }}</a><small class="bea-fx-sub">{{ p.periode_label }}</small></td>
                        <td>{{ p.point_nom || '—' }}<small class="bea-fx-sub">{{ p.fournisseur }}{{ p.agence ? ' · ' + p.agence : '' }}</small></td>
                        <td>{{ p.mode_paiement || '—' }}</td>
                        <td>{{ detail(p) || '—' }}</td>
                        <td class="is-num">{{ p.montant | montant }}</td>
                        <td><span class="bea-ct-badge" [attr.data-tone]="tone(p.statut)">{{ statut(p.statut) }}</span></td>
                        <td class="is-nowrap">
                          <span class="bea-row-actions">
                            <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="voirPaiement(p)"><mat-icon>visibility</mat-icon></button>
                            @if (p.statut !== 'ANNULE' && store.cap().payment_update) {
                              <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="voirPaiement(p, 'detail', true)"><mat-icon>edit</mat-icon></button>
                            }
                            <button type="button" class="bea-mg__icon-btn" title="Plus d'actions" aria-haspopup="menu" (click)="menuPaiement($event, p)"><mat-icon>more_vert</mat-icon></button>
                          </span>
                        </td>
                      </tr>
                    } @empty {
                      <tr><td colspan="9"><div class="bea-ct-empty"><mat-icon>payments</mat-icon><p>Aucun paiement.</p></div></td></tr>
                    }
                  }
                </tbody>
              </table>
            </div>
            <bea-pager [etat]="tPaiements" />
          </div>
        }

        @case ('echeances') {
          <div class="bea-fx-buckets bea-fx-buckets--row">
            @for (b of buckets(); track b.key) {
              <button type="button" class="bea-fx-bucket" [attr.data-tone]="b.tone" [class.is-active]="tranche() === b.key" (click)="choisirTranche(b.key)">
                <span>{{ b.label }}</span><strong>{{ b.nb }}</strong><small>{{ b.montant | montant }}</small>
              </button>
            }
          </div>
          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table bea-fx-table">
                <thead><tr><th>Échéance</th><th>Facture</th><th>Point / site</th><th>Fournisseur</th><th>Période</th><th class="is-num">Reste</th><th>Statut</th><th class="is-actions">Actions</th></tr></thead>
                <tbody>
                  @if (echeances() === null) {
                    @for (i of [1, 2, 3, 4]; track i) { <tr><td colspan="8"><span class="bea-fx-skel bea-fx-skel--line"></span></td></tr> }
                  } @else {
                    @for (r of tEcheances.lignes(); track r.id; let i = $index) {
                      <tr class="bea-fx-row" [style.animation-delay.ms]="i < 20 ? i * 15 : 0" (click)="ouvrir(r.id)">
                        <td><strong>{{ date(r.date_echeance) }}</strong><small class="bea-fx-sub" [class.bea-ct-neg]="(r.jours_echeance ?? 0) < 0">{{ jours(r.jours_echeance) }}</small></td>
                        <td><strong class="bea-fx-ref">{{ r.reference }}</strong></td>
                        <td>{{ r.point_nom || '—' }}<small class="bea-fx-sub">{{ r.agence }}</small></td>
                        <td>{{ r.fournisseur || '—' }}</td>
                        <td>{{ r.periode_label || '—' }}</td>
                        <td class="is-num">{{ r.reste | montant }}</td>
                        <td><span class="bea-ct-badge" [attr.data-tone]="tone(r.statut_affiche)">{{ statut(r.statut_affiche) }}</span></td>
                        <td class="is-nowrap" (click)="$event.stopPropagation()">
                          <span class="bea-row-actions">
                            <button type="button" class="bea-mg__icon-btn" title="Voir" (click)="ouvrir(r.id)"><mat-icon>visibility</mat-icon></button>
                            @if (payable(r)) {
                              <button type="button" class="bea-mg__icon-btn" title="Enregistrer un paiement" (click)="ouvrir(r.id, 'payer')"><mat-icon>payments</mat-icon></button>
                            }
                            @if (modifiable(r)) {
                              <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="ouvrir(r.id, 'modifier')"><mat-icon>edit</mat-icon></button>
                            }
                            <button type="button" class="bea-mg__icon-btn" title="Plus d'actions" aria-haspopup="menu" (click)="menuFacture($event, r)"><mat-icon>more_vert</mat-icon></button>
                          </span>
                        </td>
                      </tr>
                    } @empty {
                      <tr><td colspan="8"><div class="bea-ct-empty"><mat-icon>event_available</mat-icon><p>Aucune échéance ouverte.</p></div></td></tr>
                    }
                  }
                </tbody>
              </table>
            </div>
            <bea-pager [etat]="tEcheances" />
          </div>
        }

        @case ('alertes') {
          <nav class="bea-ct-tabs" aria-label="Types d'alertes">
            <button type="button" class="bea-ct-tab" [class.is-on]="typeAlerte() === ''" (click)="typeAlerte.set('')">
              <mat-icon>notifications</mat-icon> Toutes <span class="bea-fx-count">{{ alertes()?.items?.length ?? 0 }}</span>
            </button>
            @for (t of typesAlerte; track t.code) {
              <button type="button" class="bea-ct-tab" [class.is-on]="typeAlerte() === t.code" (click)="typeAlerte.set(t.code)">
                <mat-icon>{{ t.icon }}</mat-icon> {{ t.label }} <span class="bea-fx-count" [attr.data-vue]="t.code">{{ alertes()?.compteurs?.[t.code] ?? 0 }}</span>
              </button>
            }
          </nav>
          @if (alertes(); as a) {
            <p class="bea-ct-help"><mat-icon>tune</mat-icon> Seuils : échéance proche ≤ {{ a.seuils['alerte_echeance_jours'] }} j · hausse ≥ {{ a.seuils['seuil_hausse_pct'] }} % vs moyenne · facture attendue {{ a.seuils['delai_reception_jours'] }} j après la fin du mois.
              @if (store.cap().manage) { <a class="bea-ct-link" [routerLink]="base + '/parametres'">Modifier</a> }
            </p>
          }
          <div class="bea-fx-alerts">
            @if (alertes() === null) {
              @for (i of [1, 2, 3]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
            } @else {
              @for (al of alertesFiltrees(); track $index; let i = $index) {
                <article class="bea-fx-alert" [attr.data-niveau]="al.niveau" [style.animation-delay.ms]="i * 20">
                  <mat-icon class="bea-fx-alert__ico">{{ icone(al.type) }}</mat-icon>
                  <div class="bea-fx-alert__body">
                    <strong>{{ al.titre }} — {{ al.point_nom || al.reference || al.fournisseur }}</strong>
                    <p>{{ al.message }}</p>
                    <small>
                      {{ al.fournisseur }}{{ al.agence ? ' · ' + al.agence : '' }}{{ al.periode_label ? ' · ' + al.periode_label : '' }}
                      @if (al.montant !== null) { · {{ al.montant | montant }} }
                    </small>
                  </div>
                  <div class="bea-fx-alert__actions">
                    @if (al.facture_id) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrir(al.facture_id)"><mat-icon>visibility</mat-icon> Voir</button>
                      @if ((al.type === 'retard' || al.type === 'proche') && store.cap().payment_create) {
                        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrir(al.facture_id, 'payer')"><mat-icon>payments</mat-icon> Payer</button>
                      }
                      @if (al.type === 'hausse' && store.cap().validate) {
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrir(al.facture_id, 'contester')"><mat-icon>report</mat-icon> Contester</button>
                      }
                      @if (al.type === 'doublon' && store.cap().delete) {
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-mg__btn--danger" (click)="ouvrir(al.facture_id, 'annuler')"><mat-icon>block</mat-icon> Annuler</button>
                      }
                    }
                    @if (al.type === 'manquante' && al.point_id && store.cap().create) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="saisirManquante(al)"><mat-icon>post_add</mat-icon> Saisir</button>
                    }
                    @if (al.point_id) {
                      <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="base + '/points'" [queryParams]="{ point: al.point_id }"><mat-icon>place</mat-icon> Point</a>
                    }
                  </div>
                </article>
              } @empty {
                <div class="bea-ct-empty"><mat-icon>verified</mat-icon><p>Aucune alerte.</p></div>
              }
            }
          </div>
        }
      }
    </section>

    @if (paiementVu(); as pv) {
      <bea-fx-paiement-drawer [factureId]="pv.p.facture_id" [paiementId]="pv.p.id" [ongletInitial]="pv.onglet" [editionInitiale]="pv.edition"
        (fermer)="paiementVu.set(null)" (modifie)="charger()" (ouvrirFacture)="paiementVu.set(null); ouvrir($event)" />
    }
    @if (factureId(); as id) {
      <bea-fx-facture-drawer [factureId]="id" [actionInitiale]="actionInitiale()" (closed)="fermerFacture()" (changed)="charger()" />
    }
    @if (saisie(); as p) {
      <bea-fx-facture-form [preset]="p" (saved)="apresSaisie($event)" (closed)="saisie.set(null)" />
    }
    <bea-row-menu [menu]="rowMenu" />

    @if (choixFacture(); as liste) {
      <div class="bea-mg__backdrop" (click)="choixFacture.set(null)"></div>
      <div class="bea-mg__modal bea-ct-modal" role="dialog" aria-modal="true" aria-labelledby="bea-fx-choix-title">
        <header class="bea-ct-modal__head">
          <h2 id="bea-fx-choix-title"><mat-icon>add_card</mat-icon> Nouveau paiement — choisir la facture</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="choixFacture.set(null)"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-ct-modal__body">
          <label class="bea-mg__field">Rechercher <input type="search" [value]="choixQ()" (input)="choixQ.set($any($event.target).value)" placeholder="Référence, point, fournisseur…" /></label>
          <ul class="bea-ct-dash__list bea-fx-choix">
            @for (r of choixFiltre(); track r.id) {
              <li>
                <button type="button" class="bea-fx-choix__item" (click)="choixFacture.set(null); ouvrir(r.id, 'payer')">
                  <span><strong>{{ r.reference }}</strong> · {{ r.point_nom || r.fournisseur || '—' }}<small class="bea-fx-sub">{{ r.periode_label }} · échéance {{ date(r.date_echeance) }}</small></span>
                  <strong>{{ r.reste | montant }}</strong>
                </button>
              </li>
            } @empty {
              <li class="bea-ct-dash__none">{{ liste.length ? 'Aucune facture ne correspond.' : 'Aucune facture validée avec un reste à payer.' }}</li>
            }
          </ul>
        </div>
      </div>
    }
  `,
})
export class FacturationSuiviComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly base = FX_BASE;
  readonly annees = annees();
  readonly mois = MOIS;
  readonly typesAlerte = Object.entries(ALERTE_LABELS).map(([code, v]) => ({ code, ...v }));

  readonly mode = signal<Mode>('echeances');
  readonly titre = computed(() => TITRES[this.mode()]);
  readonly paiements = signal<PaiementRow[] | null>(null);
  readonly echeances = signal<{ items: FactureRow[]; buckets: Record<string, Bucket> } | null>(null);
  readonly alertes = signal<{ items: FxAlerte[]; compteurs: Record<string, number>; seuils: Record<string, number> } | null>(null);
  readonly tranche = signal('');
  readonly typeAlerte = signal('');
  readonly factureId = signal<string | null>(null);
  readonly saisie = signal<{ point_facturation_id?: string; annee?: number; mois?: number } | null>(null);
  readonly actionInitiale = signal<FactureActionInitiale | null>(null);
  readonly rowMenu = new RowMenu();
  readonly choixFacture = signal<FactureRow[] | null>(null);
  readonly choixQ = signal('');
  readonly choixFiltre = computed(() => {
    const q = this.choixQ().trim().toLowerCase();
    return (this.choixFacture() ?? []).filter((r) =>
      !q || [r.reference, r.numero_fournisseur, r.point_nom, r.fournisseur, r.agence, r.periode_label].some((x) => (x ?? '').toLowerCase().includes(q)),
    );
  });
  readonly saisie$ = new Subject<void>();
  private readonly drawer = viewChild(FactureDrawerComponent);
  private readonly form = viewChild(FactureFormComponent);

  readonly hasUnsavedChanges = () => !!this.form()?.isDirty() || !!this.drawer()?.dirty();

  readonly filtres = this.fb.nonNullable.group({
    q: [''],
    year: this.fb.control<number | null>(null),
    month: this.fb.control<number | null>(null),
    mode_paiement: [''],
    statut: [''],
    supplier_id: [''],
    agency_id: [''],
    type: [''],
  });

  readonly paiementsValides = computed(() => (this.paiements() ?? []).filter((p) => p.statut !== 'ANNULE'));
  readonly paiementsAnnules = computed(() => (this.paiements() ?? []).length - this.paiementsValides().length);
  readonly totalPaye = computed(() => this.paiementsValides().reduce((a, p) => a + p.montant, 0));

  readonly buckets = computed(() => {
    const b = this.echeances()?.buckets;
    const vide = { nb: 0, montant: 0 };
    return [
      { key: 'retard', label: 'En retard', tone: 'danger', ...(b?.['retard'] ?? vide) },
      { key: 'j7', label: '≤ 7 jours', tone: 'warn', ...(b?.['j7'] ?? vide) },
      { key: 'j30', label: '≤ 30 jours', tone: 'info', ...(b?.['j30'] ?? vide) },
      { key: 'plus30', label: '> 30 jours', tone: 'ok', ...(b?.['plus30'] ?? vide) },
    ];
  });

  readonly echeancesFiltrees = computed(() => {
    const t = this.tranche();
    return (this.echeances()?.items ?? []).filter((r) => !t || r.tranche === t);
  });

  readonly alertesFiltrees = computed(() => {
    const t = this.typeAlerte();
    return (this.alertes()?.items ?? []).filter((a) => !t || a.type === t);
  });

  readonly paiementVu = signal<{ p: PaiementRow; onglet: string; edition: boolean } | null>(null);

  voirPaiement(p: PaiementRow, onglet = 'detail', edition = false): void {
    this.paiementVu.set({ p, onglet, edition });
  }

  menuPaiement(ev: MouseEvent, p: PaiementRow): void {
    const items: RowMenuItem[] = [
      { icone: 'attach_file', label: 'Justificatif', action: () => this.voirPaiement(p, 'justificatif') },
      { icone: 'history', label: 'Historique', action: () => this.voirPaiement(p, 'historique') },
      { icone: 'receipt_long', label: 'Ouvrir la facture', action: () => this.ouvrir(p.facture_id) },
    ];
    if (p.statut !== 'ANNULE' && this.store.cap().payment_delete) {
      items.push({ icone: 'undo', label: 'Annuler le paiement', danger: true, action: () => this.annulerPaiement(p) });
    }
    this.rowMenu.ouvrir(ev, items);
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
    this.rowMenu.ouvrir(ev, items);
  }

  nouvelleFacture(): void {
    this.saisie.set({});
  }

  nouveauPaiement(): void {
    this.choixQ.set('');
    this.api.get<{ items: FactureRow[] }>('/mg/factures/echeances').subscribe({
      next: (r) => this.choixFacture.set(r.items.filter((x) => (x.reste ?? 0) > 0)),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Factures à payer indisponibles')),
    });
  }

  fermerFacture(): void {
    this.actionInitiale.set(null);
    this.factureId.set(null);
  }
  readonly tPaiements = new TableState<PaiementRow>(() => this.paiements() ?? [], {});
  readonly tEcheances = new TableState<FactureRow>(() => this.echeancesFiltrees(), {});

  readonly exportBusy = signal(false);

  exporterPaiements(format: 'pdf' | 'xlsx'): void {
    const v = this.filtres.getRawValue();
    const params = nettoyer({ q: v.q, year: v.year, month: v.month, mode_paiement: v.mode_paiement, statut: v.statut, supplier_id: v.supplier_id, agency_id: v.agency_id, format });
    const stamp = new Date().toISOString().slice(0, 10);
    this.feedback
      .run(() => this.api.download('/mg/factures/rapports/paiements', params), {
        loading: 'Préparation de l’export…',
        busy: this.exportBusy,
        errorTitle: 'Export impossible',
        success: (blob) => {
          telechargerBlob(blob, `paiements-factures_${stamp}.${format}`);
          return { title: 'Export prêt', message: 'Le fichier a été téléchargé.' };
        },
      })
      .subscribe();
  }

  ngOnInit(): void {
    this.store.charger();
    this.mode.set((this.route.snapshot.data['mode'] as Mode) ?? 'echeances');
    const q = this.route.snapshot.queryParamMap;
    this.tranche.set(q.get('echeance') ?? '');
    this.typeAlerte.set(q.get('type') ?? '');
    this.saisie$.pipe(debounceTime(300), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.charger());
    this.charger();
  }

  charger(): void {
    const v = this.filtres.getRawValue();
    const fail = (titre: string) => (e: unknown) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, titre));
    switch (this.mode()) {
      case 'paiements':
        this.api.get<PaiementRow[]>('/mg/factures/paiements', nettoyer({ q: v.q, year: v.year, month: v.month, mode_paiement: v.mode_paiement, statut: v.statut, supplier_id: v.supplier_id, agency_id: v.agency_id }))
          .subscribe({ next: (r) => this.paiements.set(r), error: (e) => { this.paiements.set([]); fail('Paiements indisponibles')(e); } });
        break;
      case 'echeances':
        this.api.get<{ items: FactureRow[]; buckets: Record<string, Bucket> }>('/mg/factures/echeances', nettoyer({ supplier_id: v.supplier_id, agency_id: v.agency_id, type: v.type }))
          .subscribe({ next: (r) => this.echeances.set(r), error: (e) => { this.echeances.set({ items: [], buckets: {} }); fail('Échéances indisponibles')(e); } });
        break;
      case 'alertes':
        this.api.get<{ items: FxAlerte[]; compteurs: Record<string, number>; seuils: Record<string, number> }>('/mg/factures/alertes', nettoyer({ q: v.q, supplier_id: v.supplier_id, agency_id: v.agency_id, type: v.type }))
          .subscribe({ next: (r) => this.alertes.set(r), error: (e) => { this.alertes.set({ items: [], compteurs: {}, seuils: {} }); fail('Alertes indisponibles')(e); } });
        break;
    }
  }

  choisirTranche(key: string): void {
    this.tranche.set(this.tranche() === key ? '' : key);
    this.router.navigate([], { queryParams: { echeance: this.tranche() || null }, queryParamsHandling: 'merge', replaceUrl: true });
  }

  ouvrir(id: string, action: FactureActionInitiale | null = null): void {
    this.actionInitiale.set(action);
    this.factureId.set(id);
  }

  saisirManquante(a: FxAlerte): void {
    const p = a.periodes?.[0];
    this.saisie.set({ point_facturation_id: a.point_id!, ...(p ? { annee: p.annee, mois: p.mois } : {}) });
  }

  apresSaisie(f: FactureDetail): void {
    this.saisie.set(null);
    this.charger();
    this.ouvrir(f.id);
  }

  annulerPaiement(p: PaiementRow): void {
    this.feedback
      .runWithReason((motif) => this.api.post(`/mg/factures/paiements/${p.id}/annuler`, { motif }), {
        reason: {
          title: `Annuler le paiement ${p.reference}`,
          message: 'Le paiement est conservé dans l’historique avec le statut « Annulé » ; la facture repasse en reste à payer.',
          reasonLabel: 'Motif de l’annulation',
          required: true,
          tone: 'danger',
          confirmLabel: 'Annuler le paiement',
        },
        loading: 'Annulation…',
        errorTitle: 'Annulation impossible',
        success: { title: 'Paiement annulé', message: p.reference },
      })
      .subscribe(() => this.charger());
  }

  icone(type: string): string {
    return ALERTE_LABELS[type]?.icon ?? 'warning';
  }

  statut(code: string | null | undefined): string {
    return fxStatut(code);
  }

  tone(code: string | null | undefined): string {
    return fxTone(code);
  }

  detail(p: PaiementRow): string {
    return detailPaiement(p);
  }

  date(iso: string | null | undefined): string {
    return dateFr(iso);
  }

  jours(j: number | null | undefined): string {
    return joursLabel(j);
  }
}
