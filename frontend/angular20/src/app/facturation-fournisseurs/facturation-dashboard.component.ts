import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { FactureDrawerComponent } from './facture-drawer.component';
import { FactureFormComponent } from './facture-form.component';
import { FxBarsComponent, FxDonutComponent, PartDonut } from './facturation-charts';
import {
  ALERTE_LABELS,
  FX_BASE,
  FactureDetail,
  FxDashboard,
  Groupe,
  MOIS,
  TYPE_POINT_LABELS,
  annees,
  dateFr,
  fxStatut,
  fxTone,
  nettoyer,
  pct,
} from './facturation.models';
import { FacturationStore } from './facturation.store';

const TONS_STATUT: Record<string, string> = {
  PAYEE: '#0f766e', VALIDEE: '#1a5278', A_PAYER: '#c2410c', PARTIELLEMENT_PAYEE: '#ca8a04', EN_RETARD: '#b91c1c',
  RECUE: '#0891b2', A_CONTROLER: '#7c3aed', BROUILLON: '#94a3b8', CONTESTEE: '#be123c', ANNULEE: '#cbd5e1', ARCHIVEE: '#64748b',
};

@Component({
  selector: 'bea-fx-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, MontantPipe, FxBarsComponent, FxDonutComponent, FactureDrawerComponent, FactureFormComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances · Factures</p>
          <h1>Factures — vue 360°</h1>
          <p class="bea-ct-head__sub">
            Agences, sièges, PDV Amanty et fournisseurs : montants, échéances, retards et factures manquantes, calculés à partir des factures saisies.
            @if (store.config()?.agence_scope; as s) { <span class="bea-ct-badge" data-tone="INFO">Périmètre : {{ s.libelle || 'votre agence' }}</span> }
          </p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap().create) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="formOuvert.set(true)"><mat-icon>post_add</mat-icon> Nouvelle facture</button>
          }
          <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="base + '/factures'"><mat-icon>receipt_long</mat-icon> Facturation</a>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Actualiser" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      <form class="bea-mg__search bea-ct-filters bea-fx-filters" [formGroup]="filtres">
        <label class="bea-mg__field">Année
          <select formControlName="year" (change)="appliquer()">
            @for (a of annees; track a) { <option [ngValue]="a">{{ a }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Mois
          <select formControlName="month" (change)="appliquer()">
            <option [ngValue]="null">Toute l'année</option>
            @for (m of mois; track $index) { <option [ngValue]="$index + 1">{{ m }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Fournisseur
          <select formControlName="supplier_id" (change)="appliquer()">
            <option value="">Tous</option>
            @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Profil
          <select formControlName="profil_id" (change)="appliquer()">
            <option value="">Tous</option>
            @for (p of store.ref()?.profils ?? []; track p.id) { <option [value]="p.id">{{ p.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Type de site
          <select formControlName="type" (change)="appliquer()">
            <option value="">Tous</option>
            @for (t of store.config()?.types_point ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
          </select>
        </label>
        @if (!store.config()?.agence_scope) {
          <label class="bea-mg__field">Agence
            <select formControlName="agency_id" (change)="appliquer()">
              <option value="">Toutes</option>
              @for (a of store.ref()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
            </select>
          </label>
        }
        <label class="bea-mg__field">PDV / point
          <select formControlName="pdv_id" (change)="appliquer()">
            <option value="">Tous</option>
            @for (p of points(); track p.id) { <option [value]="p.id">{{ p.nom }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Statut
          <select formControlName="status" (change)="appliquer()">
            <option value="">Tous</option>
            @for (s of store.config()?.statuts ?? []; track s.code) { <option [value]="s.code">{{ s.libelle }}</option> }
          </select>
        </label>
        @if (filtresActifs()) {
          <div class="bea-ct-filters__btns"><button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()"><mat-icon>filter_alt_off</mat-icon> Réinitialiser</button></div>
        }
      </form>

      @if (fil().length) {
        <nav class="bea-fx-crumbs" aria-label="Niveau d'analyse">
          <button type="button" (click)="reinitialiser()"><mat-icon>public</mat-icon> Global</button>
          @for (c of fil(); track c.key) {
            <mat-icon>chevron_right</mat-icon>
            <button type="button" (click)="retirer(c.key)" [title]="'Retirer ce filtre'">{{ c.label }} <mat-icon>close</mat-icon></button>
          }
        </nav>
      }

      @if (dash(); as d) {
        <div class="bea-fx-kpis">
          <a class="bea-fx-kpi" [routerLink]="base + '/factures'" [queryParams]="listeParams()">
            <mat-icon>receipt_long</mat-icon><p>Factures {{ d.periode_label }}</p><strong>{{ d.kpis.nb_factures }}</strong>
            <small>{{ d.kpis.a_controler }} à contrôler</small>
          </a>
          <article class="bea-fx-kpi" data-tone="brand">
            <mat-icon>account_balance_wallet</mat-icon><p>Total facturé</p><strong>{{ d.kpis.total | montant }}</strong>
            <small [class.bea-ct-neg]="(d.kpis.variation_pct ?? 0) > 0">{{ pct(d.kpis.variation_pct) }} vs {{ d.mois ? 'même mois N-1' : 'N-1 (même période)' }}</small>
          </article>
          <a class="bea-fx-kpi" data-tone="warn" [routerLink]="base + '/factures'" [queryParams]="{ vue: 'a_payer' }">
            <mat-icon>payments</mat-icon><p>Reste à payer</p><strong>{{ d.kpis.a_payer | montant }}</strong>
            <small>{{ d.kpis.nb_a_payer }} facture{{ d.kpis.nb_a_payer > 1 ? 's' : '' }} ouvertes</small>
          </a>
          <a class="bea-fx-kpi" data-tone="danger" [routerLink]="base + '/factures'" [queryParams]="{ vue: 'retard' }">
            <mat-icon>running_with_errors</mat-icon><p>En retard</p><strong>{{ d.kpis.en_retard }}</strong>
            <small>{{ d.kpis.montant_retard | montant }} à régulariser</small>
          </a>
          <article class="bea-fx-kpi" data-tone="ok">
            <mat-icon>task_alt</mat-icon><p>Payé (période)</p><strong>{{ d.kpis.paye | montant }}</strong>
            <small>Moyenne mensuelle {{ d.kpis.moyenne_mensuelle | montant }}</small>
          </article>
          <a class="bea-fx-kpi" data-tone="alert" [routerLink]="base + '/alertes'">
            <mat-icon>notification_important</mat-icon><p>Alertes</p><strong>{{ d.kpis.nb_alertes }}</strong>
            <small>{{ d.alerts_count['manquante'] || 0 }} manquante{{ (d.alerts_count['manquante'] || 0) > 1 ? 's' : '' }} · {{ d.alerts_count['hausse'] || 0 }} hausse{{ (d.alerts_count['hausse'] || 0) > 1 ? 's' : '' }}</small>
          </a>
        </div>

        <div class="bea-fx-grid">
          <div class="bea-mg__panel bea-ct-panel bea-fx-span2">
            <div class="bea-mg__panel-top">
              <h2><mat-icon>bar_chart</mat-icon> Évolution mensuelle {{ d.annee }} <small>vs {{ d.annee - 1 }}</small></h2>
              <span class="bea-fx-hint">Cliquez sur un mois pour la vue mensuelle</span>
            </div>
            <bea-fx-bars [series]="d.monthly_evolution" [avecN1]="true" [legende]="legende(d.annee)" [actif]="d.mois" (choisir)="choisirMois($event)" />
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>event</mat-icon> Échéances ouvertes</h2></div>
            <div class="bea-fx-buckets">
              @for (b of buckets(); track b.key) {
                <a class="bea-fx-bucket" [attr.data-tone]="b.tone" [routerLink]="base + '/echeances'" [queryParams]="{ echeance: b.key }">
                  <span>{{ b.label }}</span><strong>{{ b.nb }}</strong><small>{{ b.montant | montant }}</small>
                </a>
              }
            </div>
            @if (d.echeances.sans_echeance.nb) {
              <p class="bea-ct-help"><mat-icon>info</mat-icon> {{ d.echeances.sans_echeance.nb }} facture(s) ouverte(s) sans échéance ({{ d.echeances.sans_echeance.montant | montant }}).</p>
            }
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>donut_large</mat-icon> Statuts</h2></div>
            <bea-fx-donut [parts]="statuts()" unite="factures" />
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>account_balance</mat-icon> Par agence</h2><a class="bea-ct-link" [routerLink]="base + '/analyses'" [queryParams]="{ vue: 'agences' }">Analyse</a></div>
            <ul class="bea-ct-bars">
              @for (g of d.by_agency; track g.id) {
                <li class="is-click" (click)="filtrer('agency_id', g.id)">
                  <span class="bea-ct-bars__label">{{ g.label }} <small>{{ g.nb }}</small></span>
                  <span class="bea-ct-bars__track"><span class="bea-ct-bars__fill" [style.width.%]="part(g.montant, d.by_agency)"></span></span>
                  <span class="bea-ct-bars__value">{{ g.montant | montant }}</span>
                </li>
              } @empty { <li class="bea-ct-dash__none">Aucune facture rattachée à une agence.</li> }
            </ul>
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>storefront</mat-icon> PDV Amanty</h2><a class="bea-ct-link" [routerLink]="base + '/analyses'" [queryParams]="{ vue: 'pdv' }">Analyse</a></div>
            <ul class="bea-ct-bars">
              @for (g of d.by_pdv; track g.id) {
                <li class="is-click" (click)="filtrer('pdv_id', g.id)">
                  <span class="bea-ct-bars__label">{{ g.label }} <small>{{ g.nb }}</small></span>
                  <span class="bea-ct-bars__track"><span class="bea-ct-bars__fill bea-ct-bars__fill--alt" [style.width.%]="part(g.montant, d.by_pdv)"></span></span>
                  <span class="bea-ct-bars__value">{{ g.montant | montant }}</span>
                </li>
              } @empty { <li class="bea-ct-dash__none">Aucune facture PDV sur la période.</li> }
            </ul>
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>local_shipping</mat-icon> Par fournisseur</h2><a class="bea-ct-link" [routerLink]="base + '/analyses'" [queryParams]="{ vue: 'fournisseurs' }">Analyse</a></div>
            <ul class="bea-ct-bars">
              @for (g of d.by_supplier; track g.id) {
                <li class="is-click" (click)="filtrer('profil_id', g.id)">
                  <span class="bea-ct-bars__label">{{ g.label }} <small>{{ g.nb }}</small></span>
                  <span class="bea-ct-bars__track"><span class="bea-ct-bars__fill" [style.width.%]="part(g.montant, d.by_supplier)"></span></span>
                  <span class="bea-ct-bars__value">{{ g.montant | montant }}</span>
                </li>
              } @empty { <li class="bea-ct-dash__none">Aucune facture sur la période.</li> }
            </ul>
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>category</mat-icon> Par type de site</h2></div>
            <bea-fx-donut [parts]="typesSite()" unite="MRU (k)" />
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>bolt</mat-icon> Par nature de facture</h2></div>
            <bea-fx-donut [parts]="natures()" unite="MRU (k)" />
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>fact_check</mat-icon> Contrôles</h2><a class="bea-ct-link" [routerLink]="base + '/controles'">File de contrôle</a></div>
            <div class="bea-fx-buckets">
              <a class="bea-fx-bucket" data-tone="warn" [routerLink]="base + '/controles'"><span>À contrôler</span><strong>{{ d.kpis.a_controler }}</strong><small>Reçues / en contrôle</small></a>
              <a class="bea-fx-bucket" data-tone="info" [routerLink]="base + '/controles'"><span>À valider</span><strong>{{ d.kpis.controlees ?? 0 }}</strong><small>Contrôle clôturé</small></a>
            </div>
            <p class="bea-ct-help"><mat-icon>rule</mat-icon> Contrôles selon le profil de chaque fournisseur : champs obligatoires, TVA configurée, période, pièces.</p>
          </div>

          <div class="bea-mg__panel bea-ct-panel">
            <div class="bea-mg__panel-top"><h2><mat-icon>notifications_active</mat-icon> Alertes prioritaires</h2><a class="bea-ct-link" [routerLink]="base + '/alertes'">Tout voir</a></div>
            <ul class="bea-ct-dash__list">
              @for (a of d.alerts; track $index) {
                <li>
                  <a [routerLink]="a.facture_id ? null : base + '/points'" [queryParams]="a.point_id && !a.facture_id ? { point: a.point_id } : null" (click)="a.facture_id && ouvrir(a.facture_id)">
                    <span class="bea-ct-badge" [attr.data-tone]="tone(a.niveau)"><mat-icon class="bea-fx-ico">{{ alerte(a.type).icon }}</mat-icon></span>
                    <span class="bea-ct-dash__main"><strong>{{ a.titre }}</strong> {{ a.point_nom || a.reference }}<small>{{ a.message }}</small></span>
                  </a>
                </li>
              } @empty { <li class="bea-ct-dash__none">Aucune alerte : tout est à jour.</li> }
            </ul>
          </div>

          <div class="bea-mg__panel bea-ct-panel bea-fx-span2">
            <div class="bea-mg__panel-top"><h2><mat-icon>history</mat-icon> Dernières factures</h2><a class="bea-ct-link" [routerLink]="base + '/factures'">Tout voir</a></div>
            <ul class="bea-ct-dash__list">
              @for (r of d.recentes; track r.id) {
                <li>
                  <a (click)="ouvrir(r.id)">
                    <span class="bea-ct-dash__date"><strong>{{ date(r.date_facture) }}</strong><small>{{ r.periode_label }}</small></span>
                    <span class="bea-ct-dash__main"><strong>{{ r.reference }}</strong> {{ r.point_nom || r.fournisseur }}<small>{{ r.fournisseur }}{{ r.agence ? ' · ' + r.agence : '' }}</small></span>
                    <span class="bea-ct-dash__amount">{{ r.montant_a_payer | montant }} <small>{{ r.devise }}</small></span>
                    <span class="bea-ct-badge" [attr.data-tone]="tone(r.statut_affiche)">{{ statut(r.statut_affiche) }}</span>
                  </a>
                </li>
              } @empty {
                <li class="bea-ct-dash__none">
                  Aucune facture. @if (store.cap().manage) { Commencez par <a class="bea-ct-link" [routerLink]="base + '/points'">importer les points de facturation</a>. }
                </li>
              }
            </ul>
          </div>
        </div>
      } @else {
        <div class="bea-fx-kpis">@for (i of [1, 2, 3, 4, 5, 6]; track i) { <span class="bea-fx-skel bea-fx-skel--kpi"></span> }</div>
        <div class="bea-fx-grid">
          <span class="bea-fx-skel bea-fx-skel--chart bea-fx-span2"></span>
          @for (i of [1, 2, 3, 4]; track i) { <span class="bea-fx-skel bea-fx-skel--chart"></span> }
        </div>
      }
    </section>

    @if (factureId(); as id) {
      <bea-fx-facture-drawer [factureId]="id" (closed)="factureId.set(null)" (changed)="charger()" />
    }
    @if (formOuvert()) {
      <bea-fx-facture-form (saved)="apresCreation($event)" (closed)="formOuvert.set(false)" />
    }
  `,
})
export class FacturationDashboardComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly base = FX_BASE;
  readonly annees = annees();
  readonly mois = MOIS;
  readonly dash = signal<FxDashboard | null>(null);
  readonly factureId = signal<string | null>(null);
  readonly formOuvert = signal(false);
  private readonly drawer = viewChild(FactureDrawerComponent);
  private readonly form = viewChild(FactureFormComponent);
  private readonly valeurs = signal<Record<string, unknown>>({});

  readonly hasUnsavedChanges = () => !!this.form()?.isDirty() || !!this.drawer()?.dirty();

  readonly filtres = this.fb.group({
    year: this.fb.control<number>(new Date().getFullYear()),
    month: this.fb.control<number | null>(null),
    supplier_id: [''],
    profil_id: [''],
    type: [''],
    agency_id: [''],
    pdv_id: [''],
    status: [''],
  });

  readonly points = computed(() => {
    const t = (this.valeurs()['type'] as string) || '';
    return (this.store.ref()?.points ?? []).filter((p) => !t || p.type_point === t);
  });

  readonly fil = computed(() => {
    const v = this.valeurs();
    const ref = this.store.ref();
    const out: { key: string; label: string }[] = [];
    if (v['month']) out.push({ key: 'month', label: `${MOIS[(v['month'] as number) - 1]} ${v['year']}` });
    if (v['supplier_id']) out.push({ key: 'supplier_id', label: ref?.fournisseurs.find((f) => f.id === v['supplier_id'])?.libelle ?? 'Fournisseur' });
    if (v['profil_id']) out.push({ key: 'profil_id', label: ref?.profils.find((p) => p.id === v['profil_id'])?.libelle ?? 'Profil' });
    if (v['type']) out.push({ key: 'type', label: TYPE_POINT_LABELS[v['type'] as string] ?? String(v['type']) });
    if (v['agency_id']) out.push({ key: 'agency_id', label: ref?.agences.find((a) => a.id === v['agency_id'])?.libelle ?? 'Agence' });
    if (v['pdv_id']) out.push({ key: 'pdv_id', label: ref?.points.find((p) => p.id === v['pdv_id'])?.nom ?? 'Point' });
    if (v['status']) out.push({ key: 'status', label: fxStatut(v['status'] as string) });
    return out;
  });

  readonly filtresActifs = computed(() => this.fil().length > 0 || this.valeurs()['year'] !== new Date().getFullYear());

  readonly buckets = computed(() => {
    const e = this.dash()?.echeances;
    if (!e) return [];
    return [
      { key: 'retard', label: 'En retard', tone: 'danger', ...e.retard },
      { key: 'j7', label: '≤ 7 jours', tone: 'warn', ...e.j7 },
      { key: 'j30', label: '≤ 30 jours', tone: 'info', ...e.j30 },
      { key: 'plus30', label: '> 30 jours', tone: 'ok', ...e.plus30 },
    ];
  });

  readonly statuts = computed<PartDonut[]>(() =>
    (this.dash()?.by_status ?? []).map((s) => ({ label: s.label, value: s.nb, tone: TONS_STATUT[s.code] })),
  );

  readonly natures = computed<PartDonut[]>(() =>
    (this.dash()?.by_type ?? []).map((g) => ({ label: g.label, value: Math.round(g.montant / 1000) })),
  );

  readonly typesSite = computed<PartDonut[]>(() =>
    (this.dash()?.by_type_point ?? []).map((g) => ({ label: g.label, value: Math.round(g.montant / 1000) })),
  );

  ngOnInit(): void {
    this.store.charger();
    const q = this.route.snapshot.queryParamMap;
    this.filtres.patchValue({
      year: Number(q.get('year')) || new Date().getFullYear(),
      month: Number(q.get('month')) || null,
      supplier_id: q.get('supplier_id') ?? '',
      profil_id: q.get('profil_id') ?? '',
      type: q.get('type') ?? '',
      agency_id: q.get('agency_id') ?? '',
      pdv_id: q.get('pdv_id') ?? '',
      status: q.get('status') ?? '',
    });
    this.charger();
  }

  appliquer(): void {
    this.router.navigate([], { queryParams: nettoyer(this.filtres.getRawValue()), replaceUrl: true });
    this.charger();
  }

  charger(): void {
    const v = this.filtres.getRawValue();
    this.valeurs.set(v);
    this.api.get<FxDashboard>('/mg/factures/dashboard', nettoyer(v)).subscribe({
      next: (d) => this.dash.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Tableau de bord indisponible')),
    });
  }

  choisirMois(m: number): void {
    this.filtres.patchValue({ month: this.filtres.controls.month.value === m ? null : m });
    this.appliquer();
  }

  filtrer(key: 'agency_id' | 'pdv_id' | 'supplier_id' | 'profil_id', id: string): void {
    this.filtres.patchValue({ [key]: id });
    this.appliquer();
  }

  retirer(key: string): void {
    this.filtres.patchValue({ [key]: key === 'month' ? null : '' } as never);
    this.appliquer();
  }

  reinitialiser(): void {
    this.filtres.reset({ year: new Date().getFullYear(), month: null, supplier_id: '', profil_id: '', type: '', agency_id: '', pdv_id: '', status: '' });
    this.appliquer();
  }

  listeParams(): Record<string, string> {
    return nettoyer(this.filtres.getRawValue());
  }

  ouvrir(id: string): void {
    this.factureId.set(id);
  }

  apresCreation(f: FactureDetail): void {
    this.formOuvert.set(false);
    this.charger();
    this.factureId.set(f.id);
  }

  part(v: number, groupes: Groupe[]): number {
    const max = Math.max(0, ...groupes.map((g) => g.montant));
    return max > 0 ? Math.max(4, Math.round((v / max) * 100)) : 0;
  }

  alerte(type: string): { label: string; icon: string } {
    return ALERTE_LABELS[type] ?? { label: type, icon: 'warning' };
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

  pct(v: number | null | undefined): string {
    return pct(v);
  }

  legende(annee: number): [string, string] {
    return [String(annee), String(annee - 1)];
  }
}
