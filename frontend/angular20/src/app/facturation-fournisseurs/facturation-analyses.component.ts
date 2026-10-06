import { ChangeDetectionStrategy, Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { FxBarsComponent, FxSparkComponent, SerieMois } from './facturation-charts';
import { FX_BASE, FactureRow, Groupe, MOIS_COURTS, PointRow, annees, dateFr, fxStatut, fxTone, nettoyer, pct } from './facturation.models';
import { FacturationStore } from './facturation.store';

type Vue = 'mensuel' | 'annuel' | 'agences' | 'pdv' | 'fournisseurs' | 'points' | 'comparaison';

const ENDPOINTS: Record<Vue, string> = {
  mensuel: 'monthly',
  annuel: 'annual',
  agences: 'agencies',
  pdv: 'pdv',
  fournisseurs: 'suppliers',
  points: 'points',
  comparaison: 'comparison',
};

interface Synthese {
  id: string;
  code: string;
  libelle?: string;
  raison_sociale?: string;
  annee: number;
  total_annee: number;
  total_n1: number;
  variation_n1_pct: number | null;
  mensuel: number[];
  mensuel_n1: number[];
  nb_factures: number;
  reste_a_payer: number;
  en_retard?: number;
  par_fournisseur?: { label: string; montant: number }[];
  par_type?: { label: string; montant: number }[];
  points: PointRow[];
  contrats?: { id: string; reference: string; titre: string; statut: string }[];
  factures: FactureRow[];
}

@Component({
  selector: 'bea-fx-analyses',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet, ReactiveFormsModule, RouterLink, MatIconModule, MontantPipe, FxBarsComponent, FxSparkComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances · Factures</p>
          <h1>Analyses</h1>
          <p class="bea-ct-head__sub">Toutes les statistiques sont recalculées à partir des factures (aucune donnée agrégée stockée). Comparaisons à l’année précédente.</p>
        </div>
        <div class="bea-mg__actions"><a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="base"><mat-icon>dashboard</mat-icon> Vue 360°</a></div>
      </header>

      <nav class="bea-ct-tabs" aria-label="Analyses">
        @for (t of onglets; track t.code) {
          <button type="button" class="bea-ct-tab" [class.is-on]="vue() === t.code" (click)="choisir(t.code)"><mat-icon>{{ t.icon }}</mat-icon> {{ t.label }}</button>
        }
      </nav>

      <form class="bea-mg__search bea-ct-filters bea-fx-filters" [formGroup]="filtres">
        @if (vue() !== 'annuel') {
          <label class="bea-mg__field">Année
            <select formControlName="year" (change)="charger()">
              @for (a of annees; track a) { <option [ngValue]="a">{{ a }}</option> }
            </select>
          </label>
        }
        @if (vue() === 'comparaison') {
          <label class="bea-mg__field">Comparée à
            <select formControlName="annee_reference" (change)="charger()">
              @for (a of annees; track a) { <option [ngValue]="a">{{ a }}</option> }
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
        <label class="bea-mg__field">Type de site
          <select formControlName="type" (change)="charger()">
            <option value="">Tous</option>
            @for (t of store.config()?.types_point ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Type de facture
          <select formControlName="type_facture" (change)="charger()">
            <option value="">Tous</option>
            @for (t of store.config()?.types_facture ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
          </select>
        </label>
      </form>

      @if (data(); as d) {
        @switch (vue()) {
          @case ('mensuel') {
            <div class="bea-fx-kpis bea-fx-kpis--3">
              <article class="bea-fx-kpi" data-tone="brand"><mat-icon>calendar_month</mat-icon><p>Total {{ d.annee }}</p><strong>{{ d.total | montant }}</strong></article>
              <article class="bea-fx-kpi"><mat-icon>history</mat-icon><p>Total {{ d.annee - 1 }}</p><strong>{{ d.total_n1 | montant }}</strong></article>
              <article class="bea-fx-kpi" [attr.data-tone]="variation(d.total, d.total_n1) > 0 ? 'danger' : 'ok'"><mat-icon>trending_up</mat-icon><p>Variation</p><strong>{{ pct(d.total_n1 ? variation(d.total, d.total_n1) : null) }}</strong></article>
            </div>
            <div class="bea-mg__panel bea-ct-panel">
              <div class="bea-mg__panel-top"><h2><mat-icon>bar_chart</mat-icon> Évolution mensuelle</h2><span class="bea-fx-hint">Cliquez sur un mois pour voir ses factures</span></div>
              <bea-fx-bars [series]="d.items" [avecN1]="true" [legende]="legende(d.annee)" (choisir)="voirMois(d.annee, $event)" />
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table bea-fx-table">
                  <thead><tr><th>Mois</th><th class="is-num">Factures</th><th class="is-num">Montant</th><th class="is-num">Payé</th><th class="is-num">{{ d.annee - 1 }}</th><th class="is-num">Variation</th></tr></thead>
                  <tbody>
                    @for (m of d.items; track m.mois) {
                      <tr class="bea-fx-row" (click)="voirMois(d.annee, m.mois)">
                        <td>{{ m.label }}</td><td class="is-num">{{ m.nb }}</td><td class="is-num">{{ m.montant | montant }}</td>
                        <td class="is-num">{{ m.paye | montant }}</td><td class="is-num">{{ m.n1 | montant }}</td>
                        <td class="is-num" [class.bea-ct-neg]="(m.variation_pct ?? 0) > 0">{{ pct(m.variation_pct) }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            </div>
          }
          @case ('annuel') {
            <div class="bea-mg__panel bea-ct-panel">
              <div class="bea-mg__panel-top"><h2><mat-icon>stacked_bar_chart</mat-icon> Évolution annuelle</h2></div>
              <bea-fx-bars [series]="seriesAnnuelles()" titre="Évolution annuelle" (choisir)="voirAnnee($event)" />
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table bea-fx-table">
                  <thead><tr><th>Année</th><th class="is-num">Factures</th><th class="is-num">Montant</th><th class="is-num">Payé</th><th class="is-num">Moyenne mensuelle</th><th class="is-num">Variation</th></tr></thead>
                  <tbody>
                    @for (a of d.items; track a.annee) {
                      <tr class="bea-fx-row" (click)="filtrerAnnee(a.annee)">
                        <td><strong>{{ a.annee }}</strong></td><td class="is-num">{{ a.nb }}</td><td class="is-num">{{ a.montant | montant }}</td>
                        <td class="is-num">{{ a.paye | montant }}</td><td class="is-num">{{ a.moyenne_mensuelle | montant }}</td>
                        <td class="is-num" [class.bea-ct-neg]="(a.variation_pct ?? 0) > 0">{{ pct(a.variation_pct) }}</td>
                      </tr>
                    } @empty { <tr><td colspan="6"><div class="bea-ct-empty"><mat-icon>insights</mat-icon><p>Aucune donnée.</p></div></td></tr> }
                  </tbody>
                </table>
              </div>
            </div>
          }
          @case ('comparaison') {
            <div class="bea-fx-kpis bea-fx-kpis--3">
              <article class="bea-fx-kpi" data-tone="brand"><mat-icon>calendar_month</mat-icon><p>Cumul {{ d.annee }} ({{ d.cumul_mois }} mois)</p><strong>{{ d.cumul | montant }}</strong></article>
              <article class="bea-fx-kpi"><mat-icon>history</mat-icon><p>Cumul {{ d.annee_reference }}</p><strong>{{ d.cumul_reference | montant }}</strong></article>
              <article class="bea-fx-kpi" [attr.data-tone]="(d.variation_pct ?? 0) > 0 ? 'danger' : 'ok'"><mat-icon>compare_arrows</mat-icon><p>Écart</p><strong>{{ pct(d.variation_pct) }}</strong><small>{{ d.cumul - d.cumul_reference | montant }}</small></article>
            </div>
            <div class="bea-mg__panel bea-ct-panel">
              <bea-fx-bars [series]="seriesComparaison()" [avecN1]="true" [legende]="paire(d.annee, d.annee_reference)" (choisir)="voirMois(d.annee, $event)" />
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table bea-fx-table">
                  <thead><tr><th>Mois</th><th class="is-num">{{ d.annee }}</th><th class="is-num">{{ d.annee_reference }}</th><th class="is-num">Écart</th><th class="is-num">Variation</th></tr></thead>
                  <tbody>
                    @for (m of d.items; track m.mois) {
                      <tr><td>{{ m.label }}</td><td class="is-num">{{ m.montant | montant }}</td><td class="is-num">{{ m.reference | montant }}</td>
                        <td class="is-num" [class.bea-ct-neg]="m.ecart > 0">{{ m.ecart | montant }}</td><td class="is-num" [class.bea-ct-neg]="(m.variation_pct ?? 0) > 0">{{ pct(m.variation_pct) }}</td></tr>
                    }
                  </tbody>
                </table>
              </div>
            </div>
            <div class="bea-mg__panel bea-ct-panel">
              <div class="bea-mg__panel-top"><h2><mat-icon>account_balance</mat-icon> Agences — {{ d.annee }} vs {{ d.annee - 1 }}</h2></div>
              <ng-container *ngTemplateOutlet="dimension; context: { $implicit: d.agences, kind: 'agences' }" />
            </div>
          }
          @default {
            <div class="bea-mg__panel bea-ct-panel">
              <div class="bea-fx-totaux"><span>{{ d.items.length }} élément(s)</span><span>Total {{ d.annee }} <strong>{{ d.total | montant }}</strong></span></div>
              <ng-container *ngTemplateOutlet="dimension; context: { $implicit: d.items, kind: vue() }" />
            </div>
          }
        }
      } @else {
        <div class="bea-fx-grid"><span class="bea-fx-skel bea-fx-skel--chart bea-fx-span2"></span></div>
      }

      <ng-template #dimension let-items let-kind="kind">
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-fx-table">
            <thead><tr><th>{{ libelleDimension(kind) }}</th><th>Tendance</th><th class="is-num">Factures</th><th class="is-num">Montant</th><th class="is-num">Part</th><th class="is-num">N-1</th><th class="is-num">Variation</th><th class="is-num">Moy. mensuelle</th><th class="is-num">Reste</th></tr></thead>
            <tbody>
              @for (g of asGroupes(items); track g.id ?? $index) {
                <tr class="bea-fx-row" (click)="detail(kind, g)">
                  <td><strong>{{ g.label }}</strong></td>
                  <td class="bea-fx-spark-cell"><bea-fx-spark [values]="g.mensuel ?? []" /></td>
                  <td class="is-num">{{ g.nb }}</td>
                  <td class="is-num">{{ g.montant | montant }}</td>
                  <td class="is-num"><span class="bea-fx-part"><i [style.width.%]="g.part_pct ?? 0"></i></span>{{ g.part_pct ?? 0 }} %</td>
                  <td class="is-num">{{ g.n1 ?? 0 | montant }}</td>
                  <td class="is-num" [class.bea-ct-neg]="(g.variation_pct ?? 0) > 0">{{ pct(g.variation_pct) }}</td>
                  <td class="is-num">{{ g.moyenne_mensuelle ?? 0 | montant }}</td>
                  <td class="is-num">{{ g.reste | montant }}</td>
                </tr>
              } @empty { <tr><td colspan="9"><div class="bea-ct-empty"><mat-icon>insights</mat-icon><p>Aucune facture sur la période.</p></div></td></tr> }
            </tbody>
          </table>
        </div>
      </ng-template>
    </section>

    @if (synthese() || chargementSynthese()) {
      <div class="bea-fx-drawer__backdrop" (click)="fermer()"></div>
      <aside class="bea-fx-drawer" role="dialog" aria-label="Synthèse">
        @if (synthese(); as s) {
          <header class="bea-fx-drawer__head">
            <div>
              <p class="bea-ct-view__kicker">{{ s.code }} · {{ s.libelle ? 'Agence' : 'Fournisseur' }} · {{ s.annee }}</p>
              <h2>{{ s.libelle || s.raison_sociale }}</h2>
            </div>
            <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
          </header>
          <div class="bea-fx-drawer__actions">
            <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="base + '/factures'" [queryParams]="s.libelle ? { agency_id: s.id, year: s.annee } : { supplier_id: s.id, year: s.annee }"><mat-icon>receipt_long</mat-icon> Toutes les factures</a>
          </div>
          <div class="bea-fx-drawer__body">
            <div class="bea-fx-mini">
              <div><span>Total {{ s.annee }}</span><strong>{{ s.total_annee | montant }}</strong></div>
              <div><span>N-1</span><strong>{{ s.total_n1 | montant }}</strong><small [class.bea-ct-neg]="(s.variation_n1_pct ?? 0) > 0">{{ pct(s.variation_n1_pct) }}</small></div>
              <div><span>Factures</span><strong>{{ s.nb_factures }}</strong></div>
              <div><span>Reste à payer</span><strong class="bea-ct-neg">{{ s.reste_a_payer | montant }}</strong></div>
            </div>
            <bea-fx-bars [series]="seriesSynthese(s)" [avecN1]="true" [legende]="legende(s.annee)" />
            @if (s.par_fournisseur?.length) {
              <h3 class="bea-fx-h3"><mat-icon>local_shipping</mat-icon> Par fournisseur</h3>
              <ul class="bea-ct-bars">
                @for (g of s.par_fournisseur; track g.label) {
                  <li><span class="bea-ct-bars__label">{{ g.label }}</span><span class="bea-ct-bars__track"><span class="bea-ct-bars__fill" [style.width.%]="partDe(g.montant, s.par_fournisseur!)"></span></span><span class="bea-ct-bars__value">{{ g.montant | montant }}</span></li>
                }
              </ul>
            }
            @if (s.contrats?.length) {
              <h3 class="bea-fx-h3"><mat-icon>description</mat-icon> Contrats</h3>
              <ul class="bea-ct-dash__list">
                @for (c of s.contrats; track c.id) {
                  <li><a [routerLink]="'/contrats-echeances/' + c.id"><span class="bea-ct-dash__main"><strong>{{ c.reference }}</strong> {{ c.titre }}</span><span class="bea-ct-badge" [attr.data-tone]="c.statut">{{ c.statut }}</span></a></li>
                }
              </ul>
            }
            <h3 class="bea-fx-h3"><mat-icon>place</mat-icon> Points de facturation ({{ s.points.length }})</h3>
            <ul class="bea-ct-dash__list">
              @for (p of s.points; track p.id) {
                <li><a [routerLink]="base + '/points'" [queryParams]="{ point: p.id }">
                  <span class="bea-ct-dash__main"><strong>{{ p.nom }}</strong> <small>{{ p.code }} · {{ p.reference_fournisseur }}</small></span>
                  <span class="bea-ct-dash__amount">{{ p.total_annee | montant }}</span>
                </a></li>
              } @empty { <li class="bea-ct-dash__none">Aucun point.</li> }
            </ul>
            <h3 class="bea-fx-h3"><mat-icon>receipt_long</mat-icon> Factures récentes</h3>
            <ul class="bea-ct-dash__list">
              @for (r of s.factures.slice(0, 15); track r.id) {
                <li><a [routerLink]="base + '/factures'" [queryParams]="{ facture: r.id }">
                  <span class="bea-ct-dash__date"><strong>{{ r.periode_label || date(r.date_facture) }}</strong><small>{{ r.reference }}</small></span>
                  <span class="bea-ct-dash__main">{{ r.point_nom || r.fournisseur }}</span>
                  <span class="bea-ct-dash__amount">{{ r.montant_a_payer === null ? '—' : (r.montant_a_payer | montant) }}</span>
                  <span class="bea-ct-badge" [attr.data-tone]="tone(r.statut_affiche)">{{ statut(r.statut_affiche) }}</span>
                </a></li>
              } @empty { <li class="bea-ct-dash__none">Aucune facture.</li> }
            </ul>
          </div>
        } @else {
          <div class="bea-fx-drawer__body"><span class="bea-fx-skel bea-fx-skel--title"></span><span class="bea-fx-skel bea-fx-skel--chart"></span></div>
        }
      </aside>
    }
  `,
})
export class FacturationAnalysesComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly base = FX_BASE;
  readonly annees = annees();
  readonly onglets: { code: Vue; label: string; icon: string }[] = [
    { code: 'mensuel', label: 'Mensuelle', icon: 'calendar_month' },
    { code: 'annuel', label: 'Annuelle', icon: 'stacked_bar_chart' },
    { code: 'agences', label: 'Agences', icon: 'account_balance' },
    { code: 'pdv', label: 'PDV Amanty', icon: 'storefront' },
    { code: 'fournisseurs', label: 'Fournisseurs', icon: 'local_shipping' },
    { code: 'points', label: 'Points', icon: 'place' },
    { code: 'comparaison', label: 'Comparaison N / N-1', icon: 'compare_arrows' },
  ];

  readonly vue = signal<Vue>('mensuel');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  readonly data = signal<any | null>(null);
  readonly synthese = signal<Synthese | null>(null);
  readonly chargementSynthese = signal(false);

  readonly filtres = this.fb.nonNullable.group({
    year: [new Date().getFullYear()],
    annee_reference: [new Date().getFullYear() - 1],
    supplier_id: [''],
    agency_id: [''],
    type: [''],
    type_facture: [''],
  });

  readonly seriesAnnuelles = computed<SerieMois[]>(() =>
    ((this.data()?.items ?? []) as { annee: number; montant: number }[]).map((a) => ({ label: String(a.annee), montant: a.montant })),
  );

  readonly seriesComparaison = computed<SerieMois[]>(() =>
    ((this.data()?.items ?? []) as { mois: number; montant: number; reference: number }[]).map((m) => ({ label: MOIS_COURTS[m.mois - 1], montant: m.montant, n1: m.reference })),
  );

  ngOnInit(): void {
    this.store.charger();
    const q = this.route.snapshot.queryParamMap;
    const v = q.get('vue') as Vue | null;
    if (v && v in ENDPOINTS) this.vue.set(v);
    if (q.get('year')) this.filtres.patchValue({ year: Number(q.get('year')) });
    this.charger();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.synthese() || this.chargementSynthese()) this.fermer();
  }

  choisir(v: Vue): void {
    this.vue.set(v);
    this.router.navigate([], { queryParams: { vue: v }, queryParamsHandling: 'merge', replaceUrl: true });
    this.charger();
  }

  charger(): void {
    this.data.set(null);
    const vue = this.vue();
    const v = this.filtres.getRawValue();
    const params = nettoyer({ ...v, year: vue === 'annuel' ? '' : v.year, annee_reference: vue === 'comparaison' ? v.annee_reference : '' });
    this.api.get<unknown>(`/mg/factures/analytics/${ENDPOINTS[vue]}`, params).subscribe({
      next: (d) => {
        if (this.vue() !== vue) return;
        const r = d as { items?: { mois?: number; label?: string }[] };
        if (vue === 'mensuel' && r.items) r.items = r.items.map((m) => ({ ...m, label: MOIS_COURTS[(m.mois ?? 1) - 1] }));
        this.data.set(r);
      },
      error: (e) => {
        this.data.set({ items: [], total: 0, annee: v.year });
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Analyse indisponible'));
      },
    });
  }

  voirMois(annee: number, mois: number): void {
    this.router.navigate([this.base + '/factures'], { queryParams: nettoyer({ ...this.filtresListe(), year: annee, month: mois }) });
  }

  voirAnnee(index: number): void {
    const a = (this.data()?.items ?? [])[index - 1] as { annee: number } | undefined;
    if (a) this.filtrerAnnee(a.annee);
  }

  filtrerAnnee(annee: number): void {
    this.filtres.patchValue({ year: annee });
    this.choisir('mensuel');
  }

  private filtresListe(): Record<string, unknown> {
    const v = this.filtres.getRawValue();
    return { supplier_id: v.supplier_id, agency_id: v.agency_id, type: v.type, type_facture: v.type_facture };
  }

  detail(kind: Vue, g: Groupe): void {
    if (!g.id) return;
    const annee = this.filtres.controls.year.value;
    if (kind === 'pdv' || kind === 'points') {
      this.router.navigate([this.base + '/points'], { queryParams: { point: g.id } });
      return;
    }
    const url = kind === 'agences' || kind === 'comparaison' ? `/mg/factures/agences/${g.id}/synthese` : `/mg/factures/fournisseurs/${g.id}/synthese`;
    this.synthese.set(null);
    this.chargementSynthese.set(true);
    this.api.get<Synthese>(url, { year: annee }).subscribe({
      next: (s) => {
        this.synthese.set(s);
        this.chargementSynthese.set(false);
      },
      error: (e) => {
        this.chargementSynthese.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Synthèse indisponible'));
      },
    });
  }

  fermer(): void {
    this.synthese.set(null);
    this.chargementSynthese.set(false);
  }

  seriesSynthese(s: Synthese): SerieMois[] {
    return s.mensuel.map((v, i) => ({ label: MOIS_COURTS[i], montant: v, n1: s.mensuel_n1[i] ?? 0 }));
  }

  asGroupes(items: unknown): Groupe[] {
    return (items ?? []) as Groupe[];
  }

  libelleDimension(kind: Vue): string {
    return ({ agences: 'Agence', comparaison: 'Agence', pdv: 'PDV', fournisseurs: 'Fournisseur', points: 'Point' } as Record<string, string>)[kind] ?? 'Élément';
  }

  partDe(v: number, groupes: { montant: number }[]): number {
    const max = Math.max(0, ...groupes.map((g) => g.montant));
    return max > 0 ? Math.max(4, Math.round((v / max) * 100)) : 0;
  }

  variation(a: number, b: number): number {
    return b ? Math.round(((a - b) / b) * 1000) / 10 : 0;
  }

  legende(annee: number): [string, string] {
    return [String(annee), String(annee - 1)];
  }

  paire(a: number, b: number): [string, string] {
    return [String(a), String(b)];
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
}
