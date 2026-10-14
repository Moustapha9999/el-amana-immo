import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { Compteur, TableauBord, dateFr, montantFr, tonePriorite, toneStatut } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcComparaisonComponent } from '../shared/rc-comparaison.component';
import { RcExportComponent } from '../shared/rc-export.component';

type Periode = 'tout' | '30' | '90' | '365' | 'annee';

const PERIODES: { code: Periode; libelle: string }[] = [
  { code: 'tout', libelle: 'Tout' },
  { code: '30', libelle: '30 jours' },
  { code: '90', libelle: '90 jours' },
  { code: '365', libelle: '12 mois' },
  { code: 'annee', libelle: 'Année en cours' },
];
const DUREE_ANIMATION = 900;

/** Tableau de bord 360° : volumes, tendances et files du périmètre, sans donnée inventée. */
@Component({
  selector: 'bea-rc-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, ReclamationsUiComponent, RcExportComponent, RcComparaisonComponent],
  styleUrls: ['./rc-dashboard.component.css', './rc-dashboard-graphiques.css'],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc rcd">
      <header class="rcd-hero">
        <div class="rcd-hero__text">
          <p class="rcd-hero__kicker">Management & Qualité · Réclamations</p>
          <h1>Tableau de bord 360°</h1>
          <p>Stock ouvert, tendances et volumes dans votre périmètre.</p>
        </div>
        <div class="rcd-hero__actions">
          <bea-rc-export />
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [class.is-spin]="chargement()" (click)="charger()" title="Actualiser" aria-label="Actualiser">
            <mat-icon>refresh</mat-icon>
          </button>
        </div>
        <div class="rcd-filtres">
          <div class="rcd-periodes" role="tablist" aria-label="Période">
            @for (p of periodes; track p.code) {
              <button type="button" role="tab" [attr.aria-selected]="periode() === p.code" [class.is-on]="periode() === p.code" (click)="choisirPeriode(p.code)">{{ p.libelle }}</button>
            }
          </div>
          <label class="rcd-agence"><mat-icon>store</mat-icon>
            <select [value]="agence()" (change)="choisirAgence($any($event.target).value)" aria-label="Agence du client">
              <option value="">Toutes les agences</option>
              <option value="AUCUNE">Sans agence</option>
              @for (a of store.config()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
            </select>
          </label>
        </div>
      </header>

      @if (erreur()) {
        <div class="bea-ct-empty bea-ct-empty--hero"><mat-icon>cloud_off</mat-icon>
          <p>Impossible de charger le tableau de bord.</p>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon> Réessayer</button>
        </div>
      } @else if (data(); as d) {
        <div class="rcd-kpis" [class.is-loading]="chargement()">
          <a class="rcd-kpi" style="--i: 0" routerLink="/reclamations/dossiers" [queryParams]="kpi('total')">
            <span class="rcd-kpi__ico"><mat-icon>forum</mat-icon></span>
            <p>Total</p><strong>{{ n(d.total) }}</strong><small>dans le périmètre</small>
          </a>
          <a class="rcd-kpi" style="--i: 1" routerLink="/reclamations/dossiers" [queryParams]="kpi('ouvertes')">
            <span class="rcd-kpi__ico"><mat-icon>pending_actions</mat-icon></span>
            <p>Ouvertes</p><strong>{{ n(d.ouvertes) }}</strong><small>{{ pct(d.ouvertes, d.total) }} % du total</small>
          </a>
          <a class="rcd-kpi" style="--i: 2" routerLink="/reclamations/dossiers" [queryParams]="kpi('volume_30j')">
            <span class="rcd-kpi__ico"><mat-icon>calendar_month</mat-icon></span>
            <p>Reçues 30 j</p><strong>{{ n(d.volume_30j) }}</strong>
            <small class="rcd-delta" [attr.data-sens]="delta(d).sens"><mat-icon>{{ delta(d).icone }}</mat-icon>{{ delta(d).texte }}</small>
          </a>
          <a class="rcd-kpi" style="--i: 3" data-tone="ok" routerLink="/reclamations/dossiers" [queryParams]="kpi('delai_moyen')">
            <span class="rcd-kpi__ico"><mat-icon>task_alt</mat-icon></span>
            <p>Délai moyen de clôture</p>
            <strong>{{ d.performance.delai_cloture_jours === null ? 'N/A' : d.performance.delai_cloture_jours + ' j' }}</strong>
            <small>sur {{ d.performance.delai_cloture_n }} dossier(s) clôturé(s)</small>
          </a>
          <a class="rcd-kpi" style="--i: 4" routerLink="/reclamations/dossiers" [queryParams]="kpi('operations')">
            <span class="rcd-kpi__ico"><mat-icon>receipt_long</mat-icon></span>
            <p>Opérations</p><strong>{{ n(d.nb_operations) }}</strong><small>dans {{ d.dossiers_avec_operations }} dossier(s)</small>
          </a>
          <a class="rcd-kpi" style="--i: 5" routerLink="/reclamations/dossiers" [queryParams]="kpi('operations')">
            <span class="rcd-kpi__ico"><mat-icon>payments</mat-icon></span>
            <p>Montant total</p><strong class="rcd-kpi__montant">{{ montant(d.montant_total, d.devise) }}</strong>
            <small>chaque opération comptée une fois</small>
          </a>
        </div>

        @if (store.cap('reporting_voir')) {
          <section class="bea-mg__panel rcd-card rcd-bloc" style="--i: 10">
            <div class="bea-mg__panel-top"><h2><mat-icon>compare_arrows</mat-icon> Comparer deux périodes</h2>
              <small class="bea-rc-hint">{{ agenceLibelle() }}</small>
            </div>
            <bea-rc-comparaison [filtres]="base()" />
          </section>
        }

        <div class="rcd-row rcd-row--chart">
          <section class="bea-mg__panel rcd-card" style="--i: 8">
            <div class="bea-mg__panel-top"><h2>Évolution sur 12 mois</h2>
              <span class="rcd-legende"><i data-k="recues"></i> Reçues <i data-k="cloturees"></i> Clôturées</span>
            </div>
            <div class="rcd-chart" role="img" [attr.aria-label]="'Réclamations reçues et clôturées par mois, total reçu ' + totalTendance()">
              @for (m of d.tendance; track m.mois) {
                <div class="rcd-chart__col" [title]="m.libelle + ' : ' + m.recues + ' reçue(s), ' + m.cloturees + ' clôturée(s)'">
                  <div class="rcd-chart__bars">
                    <span data-k="recues" [style.height.%]="hauteur(m.recues)" [style.transition-delay.ms]="$index * 40">
                      @if (m.recues) { <b>{{ m.recues }}</b> }
                    </span>
                    <span data-k="cloturees" [style.height.%]="hauteur(m.cloturees)" [style.transition-delay.ms]="$index * 40 + 20"></span>
                  </div>
                  <small>{{ m.libelle }}</small>
                </div>
              }
            </div>
          </section>
          <section class="bea-mg__panel rcd-card" style="--i: 9">
            <div class="bea-mg__panel-top"><h2>Ancienneté du stock ouvert</h2><small class="bea-rc-hint">{{ d.ouvertes }} dossier(s)</small></div>
            <div class="rcd-stack" role="img" aria-label="Répartition des dossiers ouverts par ancienneté">
              @for (t of d.anciennete; track t.code) {
                @if (t.n) { <span [attr.data-k]="t.code" [style.flex-grow]="pret() ? t.n : 0" [title]="t.libelle + ' : ' + t.n"></span> }
              }
            </div>
            <ul class="rcd-stack__legend">
              @for (t of d.anciennete; track t.code) {
                <li><i [attr.data-k]="t.code"></i>{{ t.libelle }}<b>{{ t.n }}</b></li>
              }
            </ul>
          </section>
        </div>

        <div class="rcd-row">
          @for (bloc of blocsStatut(); track bloc.titre; let bi = $index) {
            <section class="bea-mg__panel rcd-card" [style.--i]="10 + bi">
              <div class="bea-mg__panel-top"><h2>{{ bloc.titre }}</h2></div>
              <ul class="rcd-bars" [attr.data-ton]="bloc.ton">
                @for (g of bloc.items; track g.code) {
                  <li>
                    <a [routerLink]="['/reclamations/dossiers']" [queryParams]="bloc.filtre(g)">
                      <span class="rcd-bars__lib">{{ g.libelle }}</span><span class="rcd-bars__n">{{ g.n }}</span>
                    </a>
                    <span class="rcd-bars__track"><span class="rcd-bars__fill" [style.width.%]="largeur(g.n, bloc.max)" [style.transition-delay.ms]="$index * 50"></span></span>
                  </li>
                }
              </ul>
            </section>
          }
        </div>

        <div class="rcd-row">
          <section class="bea-mg__panel rcd-card" style="--i: 14">
            <div class="bea-mg__panel-top"><h2>Résultat des dossiers clôturés</h2></div>
            @if (d.resultats.length) {
              <ul class="rcd-bars" data-ton="ok">
                @for (r of d.resultats; track r.code) {
                  <li>
                    <span class="rcd-bars__row"><span class="rcd-bars__lib">{{ r.libelle }}</span><span class="rcd-bars__n">{{ r.n }}</span></span>
                    <span class="rcd-bars__track"><span class="rcd-bars__fill" [style.width.%]="largeur(r.n, maxDe(d.resultats))"></span></span>
                  </li>
                }
              </ul>
            } @else {
              <p class="rcd-vide"><mat-icon>inventory</mat-icon> Aucun dossier clôturé avec résultat.</p>
            }
          </section>
          <section class="bea-mg__panel rcd-card" style="--i: 15">
            <div class="bea-mg__panel-top"><h2>Clients récurrents</h2><small class="bea-rc-hint">2 réclamations ou plus</small></div>
            @if (d.clients_recurrents.length) {
              <ul class="rcd-clients">
                @for (c of d.clients_recurrents; track c.racine) {
                  <li>
                    <a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ q: c.racine }">
                      <span class="rcd-clients__av">{{ initiales(c.nom) }}</span>
                      <span class="rcd-clients__nom"><strong>{{ c.nom || 'Client' }}</strong><small>Racine {{ c.racine }}</small></span>
                      <span class="rcd-clients__n">{{ c.n }}@if (c.ouvertes) { <small>{{ c.ouvertes }} ouverte(s)</small> }</span>
                    </a>
                  </li>
                }
              </ul>
            } @else {
              <p class="rcd-vide"><mat-icon>person_search</mat-icon> Aucun client récurrent.</p>
            }
          </section>
        </div>

        <div class="rcd-row">
          @for (r of repartitions(); track r.titre; let ri = $index) {
            <section class="bea-mg__panel rcd-card" [style.--i]="16 + ri">
              <div class="bea-mg__panel-top"><h2>{{ r.titre }}</h2><small class="bea-rc-hint">dossiers · opérations · montant</small></div>
              @if (r.items.length) {
                <ul class="rcd-bars">
                  @for (c of r.items; track c.id) {
                    <li>
                      @if (r.param && c.id !== 'None') {
                        <a [routerLink]="['/reclamations/dossiers']" [queryParams]="filtre(r.param, c)">
                          <span class="rcd-bars__lib">{{ c.libelle }}</span><span class="rcd-bars__n">{{ c.n }}</span>
                        </a>
                      } @else {
                        <span class="rcd-bars__row"><span class="rcd-bars__lib">{{ c.libelle === '—' ? 'Non renseigné' : c.libelle }}</span><span class="rcd-bars__n">{{ c.n }}</span></span>
                      }
                      <span class="rcd-bars__track"><span class="rcd-bars__fill" [style.width.%]="largeur(c.n, r.max)" [style.transition-delay.ms]="$index * 50"></span></span>
                      @if (c.nb_operations) { <small class="rcd-bars__sub">{{ c.nb_operations }} op. · {{ montant(c.montant ?? null, d.devise) }}</small> }
                    </li>
                  }
                </ul>
              } @else {
                <p class="rcd-vide"><mat-icon>bar_chart</mat-icon> Aucune donnée.</p>
              }
            </section>
          }
        </div>

        <section class="bea-mg__panel rcd-card" style="--i: 20">
          <div class="bea-mg__panel-top"><h2><mat-icon>history</mat-icon> Derniers dossiers</h2>
            <a class="bea-ct-link" routerLink="/reclamations/dossiers" [queryParams]="kpi('total')">Toutes les réclamations</a>
          </div>
          @if (d.recents.length) {
            <ul class="bea-rc-mini">
              @for (r of d.recents; track r.id) {
                <li>
                  <a class="bea-rc-mini__row" [routerLink]="['/reclamations/dossiers', r.id]">
                    <code>{{ r.reference }}</code>
                    <span class="bea-rc-mini__obj">{{ r.objet }}</span>
                    <span class="bea-ct-badge" [attr.data-tone]="toneStatut(r.statut)">{{ r.statut_libelle }}</span>
                    <span class="bea-ct-badge" [attr.data-tone]="tonePriorite(r.priorite)">{{ r.priorite_libelle }}</span>
                    <small>{{ date(r.date_premiere_reception) }}</small>
                  </a>
                </li>
              }
            </ul>
          } @else {
            <p class="rcd-vide"><mat-icon>inbox</mat-icon> Aucune réclamation dans votre périmètre.</p>
          }
        </section>
      } @else {
        <div class="rcd-kpis">
          @for (i of squelette; track i) { <div class="rcd-kpi rcd-skel"></div> }
        </div>
        <div class="rcd-row rcd-row--chart"><div class="rcd-skel rcd-skel--lg"></div><div class="rcd-skel rcd-skel--lg"></div></div>
      }
    </section>
  `,
})
export class RcDashboardComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);

  readonly toneStatut = toneStatut;
  readonly tonePriorite = tonePriorite;
  readonly periodes = PERIODES;
  readonly squelette = [0, 1, 2, 3, 4, 5];
  readonly data = signal<TableauBord | null>(null);
  readonly erreur = signal(false);
  readonly chargement = signal(false);
  readonly periode = signal<Periode>('tout');
  readonly agence = signal('');
  /** Avancement 0 → 1 de l'animation d'entrée (compteurs, barres). */
  private readonly progres = signal(1);
  readonly pret = computed(() => this.progres() > 0);
  private frame = 0;

  constructor() {
    inject(DestroyRef).onDestroy(() => cancelAnimationFrame(this.frame));
  }

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  /** Filtres de la page repris par chaque lien vers la liste (agence, y compris « sans agence », et période). */
  readonly base = computed<Record<string, string | null>>(() => ({
    client_agence_id: this.agence() || null,
    date_debut: this.dateDebut(this.periode()),
  }));

  readonly agenceLibelle = computed(() => {
    const a = this.agence();
    if (!a) return 'Toutes les agences';
    if (a === 'AUCUNE') return 'Dossiers sans agence';
    const ag = this.store.config()?.agences.find((x) => x.id === a);
    return ag ? `Agence ${ag.code} — ${ag.libelle}` : '';
  });

  charger(): void {
    this.erreur.set(false);
    this.chargement.set(true);
    this.rc.tableauDeBord(this.base()).subscribe({
      next: (d) => {
        this.data.set(d);
        this.chargement.set(false);
        this.animer();
      },
      error: (e) => {
        this.chargement.set(false);
        this.erreur.set(true);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Tableau de bord indisponible'));
      },
    });
  }

  choisirPeriode(p: Periode): void {
    if (p === this.periode()) return;
    this.periode.set(p);
    this.charger();
  }

  choisirAgence(a: string): void {
    if (a === this.agence()) return;
    this.agence.set(a);
    this.charger();
  }

  /** Paramètres de liste d'un KPI : fournis par le serveur (même condition que le calcul) + agence. */
  kpi(code: string): Record<string, string | null> {
    const l = this.data()?.liens[code] ?? {};
    return { ...l, client_agence_id: this.agence() || null };
  }

  private avecBase(params: Record<string, string>): Record<string, string | null> {
    return { ...this.base(), ...params };
  }

  private dateDebut(p: Periode): string | null {
    if (p === 'tout') return null;
    const d = new Date();
    if (p === 'annee') d.setMonth(0, 1);
    else d.setDate(d.getDate() - Number(p));
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  private animer(): void {
    cancelAnimationFrame(this.frame);
    if (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) {
      this.progres.set(1);
      return;
    }
    this.progres.set(0);
    const t0 = performance.now();
    const pas = (t: number) => {
      const x = Math.min(1, (t - t0) / DUREE_ANIMATION);
      this.progres.set(Math.max(0.001, 1 - Math.pow(1 - x, 3)));
      if (x < 1) this.frame = requestAnimationFrame(pas);
    };
    this.frame = requestAnimationFrame(pas);
  }

  n(v: number): number {
    return Math.round(v * this.progres());
  }

  pct(part: number, total: number): number {
    return total ? Math.round((100 * part) / total) : 0;
  }

  largeur(v: number, max: number): number {
    return this.pret() && max ? Math.max(2, (100 * v) / max) : 0;
  }

  maxDe(items: { n: number }[]): number {
    return Math.max(0, ...items.map((i) => i.n));
  }

  readonly maxTendance = computed(() => {
    const t = this.data()?.tendance ?? [];
    return Math.max(1, ...t.map((m) => Math.max(m.recues, m.cloturees)));
  });

  readonly totalTendance = computed(() => (this.data()?.tendance ?? []).reduce((s, m) => s + m.recues, 0));

  hauteur(v: number): number {
    return this.pret() && v ? Math.max(3, (100 * v) / this.maxTendance()) : 0;
  }

  delta(d: TableauBord): { sens: string; icone: string; texte: string } {
    const avant = d.volume_30j_precedent;
    const ecart = d.volume_30j - avant;
    if (!avant) return { sens: 'neutre', icone: 'remove', texte: `${avant} sur les 30 j précédents` };
    const p = Math.round((100 * ecart) / avant);
    if (ecart === 0) return { sens: 'neutre', icone: 'trending_flat', texte: 'stable vs 30 j précédents' };
    return ecart > 0
      ? { sens: 'hausse', icone: 'trending_up', texte: `+${p} % vs 30 j précédents` }
      : { sens: 'baisse', icone: 'trending_down', texte: `${p} % vs 30 j précédents` };
  }

  initiales(nom: string | null): string {
    const mots = (nom ?? '').trim().split(/\s+/).filter(Boolean);
    return (mots.slice(0, 2).map((m) => m[0]).join('') || '?').toUpperCase();
  }

  readonly blocsStatut = computed(() => {
    const d = this.data();
    if (!d) return [];
    return [
      { titre: 'Par statut', ton: 'statut', items: d.statuts, max: this.maxDe(d.statuts),
        filtre: (g: Compteur) => this.avecBase({ statut: g.code ?? '' }) },
      { titre: 'Par étape du circuit', ton: 'etape', items: d.etapes, max: this.maxDe(d.etapes),
        filtre: (g: Compteur) => this.avecBase({ etape: g.code ?? '' }) },
      { titre: 'Par priorité', ton: 'priorite', items: d.priorites, max: this.maxDe(d.priorites),
        filtre: (g: Compteur) => this.avecBase({ priorite: g.code ?? '' }) },
    ];
  });

  readonly repartitions = computed(() => {
    const d = this.data();
    if (!d) return [];
    return [
      { titre: 'Par motif', items: d.motifs, param: 'motif_id' },
      { titre: 'Par canal', items: d.canaux, param: 'canal_id' },
      { titre: 'Par agence', items: d.agences, param: 'client_agence_id' },
      { titre: 'Par service', items: d.services, param: '' },
    ].map((r) => ({ ...r, max: this.maxDe(r.items) }));
  });

  filtre(param: string, c: Compteur): Record<string, string | null> {
    return this.avecBase({ [param]: c.id ?? '' });
  }

  montant(v: string | null, devise: string): string {
    return montantFr(v, devise);
  }

  date(iso: string | null): string {
    return dateFr(iso);
  }
}
