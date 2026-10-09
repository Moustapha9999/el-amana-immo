import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, TableauBord, dateHeureFr, n, valeurIndic } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface IndicDash { code: string; libelle: string; statut: string; valeur: number | null; }
interface DeclarationDash { id: string; libelle: string; statut: string; }

const KPI_CONFORMITE = [
  'cli.stock', 'cli.nouveaux', 'cli.risque.eleve', 'cli.risque.interdit',
  'cli.reclass.vers_eleve', 'eer.maj_periode', 'bcm.t2.suivi', 'alerte.faux_positifs', 'cli.actifs',
];

@Component({
  selector: 'bea-cl-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Conformité &amp; sécurité financière</p>
          <h1>Référentiel clients</h1>
          <p class="bea-cl-head__sub">Vue de synthèse pour les agents et responsables. Un client = une racine ORION (COUNT DISTINCT). Le mapping des colonnes est dans Imports → Mapping &amp; sources.</p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/mapping"><mat-icon>account_tree</mat-icon> Mapping &amp; sources</a>
      </header>

      <div class="bea-cl-pilot">
        <a class="bea-cl-kpi" routerLink="/clientele/situation-pp">
          <mat-icon class="bea-cl-kpi__ico">groups</mat-icon>
          <span>Clients référencés</span>
          <strong>{{ n(t()?.nb_clients) }}</strong>
          <small>PP {{ n(t()?.pp) }} · PM {{ n(t()?.pm) }} · non identifiés {{ n(t()?.non_identifies) }}</small>
          <small>Constructions juridiques : à configurer</small>
          <em>{{ t()?.periode_libelle || 'Période non chargée' }} · clientele_situation</em>
        </a>
        <div class="bea-cl-kpi">
          <mat-icon class="bea-cl-kpi__ico">account_balance_wallet</mat-icon>
          <span>Comptes référencés</span>
          <strong>{{ n(t()?.nb_comptes) }}</strong>
          <small>{{ n(t()?.nb_rib ?? t()?.nb_comptes) }} RIB distincts · {{ n(t()?.ouverts) }} clients ouverts · {{ n(t()?.clotures) }} clôturés</small>
          <em>{{ t()?.periode_libelle || 'Période non chargée' }} · clientele_comptes</em>
        </div>
        @if (store.cap().imports_voir) {
          <a class="bea-cl-kpi" routerLink="/clientele/imports">
            <mat-icon class="bea-cl-kpi__ico">cloud_sync</mat-icon>
            <span>Dernier import ORION</span>
            <strong>{{ importLibelle() }}</strong>
            <small>{{ importDetail() }}</small>
            <em>clientele_imports · statut réel du dernier traitement</em>
          </a>
        } @else {
          <div class="bea-cl-kpi">
            <mat-icon class="bea-cl-kpi__ico">cloud_sync</mat-icon>
            <span>Dernier import ORION</span>
            <strong>{{ importLibelle() }}</strong>
            <small>{{ importDetail() }}</small>
            <em>clientele_imports · statut réel du dernier traitement</em>
          </div>
        }
        <a class="bea-cl-kpi" routerLink="/clientele/mapping" fragment="qualite" [attr.data-tone]="t()?.anomalies?.a_traiter ? 'warn' : null">
          <mat-icon class="bea-cl-kpi__ico">report_problem</mat-icon>
          <span>Anomalies à traiter</span>
          <strong>{{ n(t()?.anomalies?.a_traiter) }}</strong>
          <small>{{ n(t()?.anomalies?.sans_identifiant) }} sans identifiant · {{ n(t()?.anomalies?.agence_inconnue) }} agence inconnue</small>
          <small>{{ n(t()?.anomalies?.alertes_ouvertes) }} alertes ouvertes · {{ n(t()?.anomalies?.rejets_dernier_import) }} rejets du dernier import</small>
          <em>{{ t()?.periode_libelle || 'Stock courant' }} · situation, alertes, import</em>
        </a>
      </div>

      <div class="bea-cl-grid">
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Évolution de la clientèle</h2></div>
          <p class="bea-cl-hint" style="padding:0 1.1rem">Premières extractions par mois (racines nouvellement vues). Ce n’est pas un stock mensuel reconstitué.</p>
          <div class="bea-cl-cols">
            @for (e of t()?.evolution ?? []; track e.mois; let i = $index) {
              <div class="bea-cl-col" [style.--d]="i">
                <b>{{ n(e.nouveaux) }}</b>
                <i [style.height.%]="part(e.nouveaux, maxEvolution())"></i>
                <span>{{ e.libelle }}</span>
              </div>
            } @empty {
              <div class="bea-cl-empty" style="grid-column:1/-1">Aucune extraction enregistrée.</div>
            }
          </div>
        </section>
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Répartition par agence</h2></div>
          <p class="bea-cl-hint" style="padding:0 1.1rem">Agence du compte le plus ancien. Source : clientele_situation.</p>
          <ul class="bea-cl-bars">
            @for (a of t()?.agences ?? []; track a.code + a.libelle; let i = $index) {
              <li [style.--d]="i">
                <span><strong>{{ a.code }}</strong> {{ a.libelle }}</span>
                <b>{{ n(a.clients) }}</b>
                <i><em [style.width.%]="part(a.clients, maxAgence())"></em></i>
              </li>
            } @empty {
              <li><div class="bea-cl-empty">Aucune agence.</div></li>
            }
          </ul>
        </section>
      </div>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Vue des risques</h2>
          @if (store.cap().classif_voir) {
            <a routerLink="/clientele/classification">Classification</a>
          }
        </div>
        <p class="bea-cl-hint" style="padding:0 1.1rem">Niveaux réellement enregistrés. Les non classés ne sont pas comptés en Faible. Source : clientele_classifications.</p>
        @if (totalRisques()) {
          <div class="bea-cl-stack" role="img" [attr.aria-label]="'Répartition des ' + n(totalRisques()) + ' clients par niveau de risque'">
            @for (r of t()?.risques ?? []; track r.niveau) {
              @if (r.clients) { <i [attr.data-n]="r.niveau" [style.flex-grow]="r.clients" [title]="r.libelle + ' : ' + n(r.clients)"></i> }
            }
            @if (t()?.non_classes) { <i data-n="NON_CLASSE" [style.flex-grow]="t()!.non_classes" [title]="'Non classés : ' + n(t()?.non_classes)"></i> }
          </div>
        }
        <div class="bea-cl-kpis" style="margin:0.85rem 1rem 1rem">
          @for (r of t()?.risques ?? []; track r.niveau) {
            <div class="bea-cl-kpi bea-cl-kpi--niv" [attr.data-n]="r.niveau">
              <span>{{ r.libelle }}</span>
              <strong>{{ n(r.clients) }}</strong>
              <small>{{ pct(r.clients, totalRisques()) }}</small>
            </div>
          }
          <div class="bea-cl-kpi bea-cl-kpi--niv" data-n="NON_CLASSE">
            <span>Non classés</span>
            <strong>{{ n(t()?.non_classes) }}</strong>
            <small>{{ pct(t()?.non_classes, totalRisques()) }}</small>
          </div>
        </div>
      </section>

      <section class="bea-mg__panel" id="qualite">
        <div class="bea-mg__panel-top"><h2>Qualité des données</h2></div>
        <p class="bea-cl-hint" style="padding:0 1.1rem">{{ t()?.periode_libelle || 'Stock courant' }}. Une racine est unique : il n’y a pas de doublon de client en base.</p>
        <div class="bea-cl-stats">
          <div class="bea-cl-stat" [attr.data-tone]="tone(t()?.anomalies?.sans_identifiant)"><span>Sans identifiant exploitable</span><strong>{{ n(t()?.anomalies?.sans_identifiant) }}</strong></div>
          <div class="bea-cl-stat" [attr.data-tone]="tone(t()?.anomalies?.agence_inconnue)"><span>Agence inconnue</span><strong>{{ n(t()?.anomalies?.agence_inconnue) }}</strong></div>
          <div class="bea-cl-stat"><span>Multi-agences</span><strong>{{ n(t()?.anomalies?.multi_agences) }}</strong></div>
          <div class="bea-cl-stat" [attr.data-tone]="tone(t()?.anomalies?.secteur_vide)"><span>Secteur vide</span><strong>{{ n(t()?.anomalies?.secteur_vide) }}</strong></div>
          <div class="bea-cl-stat" [attr.data-tone]="tone(t()?.anomalies?.nationalite_vide)"><span>Nationalité vide</span><strong>{{ n(t()?.anomalies?.nationalite_vide) }}</strong></div>
          <div class="bea-cl-stat" [attr.data-tone]="tone(t()?.anomalies?.anomalies_dernier_import)"><span>Anomalies du dernier import</span><strong>{{ n(t()?.anomalies?.anomalies_dernier_import) }}</strong></div>
        </div>
      </section>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Activité récente</h2></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Quand</th><th>Opération</th><th>Statut</th><th>Détail</th></tr></thead>
            <tbody>
              @for (a of t()?.activite ?? []; track a.type + a.id) {
                <tr>
                  <td>{{ dh(a.le) }}</td>
                  <td class="bea-cl-act">
                    <mat-icon [attr.data-t]="a.type">{{ a.type === 'import' ? 'upload_file' : 'compare_arrows' }}</mat-icon>
                    @if (a.type === 'import' && store.cap().imports_voir) {
                      <a routerLink="/clientele/imports"><strong>{{ a.libelle }}</strong></a>
                    } @else if (a.type === 'rapprochement' && store.cap().rapprochement_voir) {
                      <a routerLink="/clientele/rapprochements"><strong>{{ a.libelle }}</strong></a>
                    } @else {
                      <strong>{{ a.libelle }}</strong>
                    }
                  </td>
                  <td><span class="bea-cl-badge" [attr.data-s]="a.statut">{{ a.statut }}</span></td>
                  <td>{{ a.detail || '—' }}</td>
                </tr>
              } @empty {
                <tr><td colspan="4"><div class="bea-cl-empty">Aucun import ni rapprochement.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>

      @if (store.cap().reporting_voir && conformite().length) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Conformité — mois précédent</h2></div>
          <p class="bea-cl-hint" style="padding:0 1.1rem">Même moteur que le reporting et la déclaration BCM. Période : mois précédent.</p>
          <div class="bea-cl-kpis" style="margin:0.85rem 1rem 1rem">
            @for (i of conformite(); track i.code) {
              <a class="bea-cl-kpi" [class.is-lock]="i.statut==='A_CONFIGURER'" routerLink="/clientele/reporting" [queryParams]="{ periode: 'mois_precedent', code: i.code }">
                <span>{{ i.libelle }}</span>
                <strong>{{ valeurIndic(i.statut, i.valeur) }}</strong>
              </a>
            }
            @if (store.cap().bcm_voir) {
              <a class="bea-cl-kpi" [routerLink]="derniere() ? ['/clientele/declarations', derniere()!.id] : '/clientele/declarations'">
                <span>Dernière déclaration BCM</span>
                <strong>{{ derniere()?.libelle ?? 'Aucune' }}</strong>
                @if (derniere(); as dd) { <span class="bea-cl-badge" [attr.data-s]="dd.statut">{{ dd.statut.replaceAll('_', ' ') }}</span> }
              </a>
            }
          </div>
        </section>
      }
    </div>
  `,
})
export class ClDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly t = signal<TableauBord | null>(null);
  readonly conformite = signal<IndicDash[]>([]);
  readonly derniere = signal<DeclarationDash | null>(null);
  readonly n = n;
  readonly dh = dateHeureFr;
  readonly valeurIndic = valeurIndic;
  readonly maxEvolution = computed(() => Math.max(0, ...(this.t()?.evolution ?? []).map((e) => e.nouveaux)));
  readonly maxAgence = computed(() => Math.max(0, ...(this.t()?.agences ?? []).map((a) => a.clients)));
  readonly totalRisques = computed(() =>
    (this.t()?.risques ?? []).reduce((s, r) => s + r.clients, 0) + (this.t()?.non_classes ?? 0));

  private conformiteDemandee = false;
  private declarationDemandee = false;

  constructor() {
    effect(() => {
      const cap = this.store.cap();
      if (cap.reporting_voir && !this.conformiteDemandee) {
        this.conformiteDemandee = true;
        this.chargerConformite();
      }
      if (cap.bcm_voir && !this.declarationDemandee) {
        this.declarationDemandee = true;
        this.chargerDeclaration();
      }
    });
  }

  ngOnInit(): void {
    this.store.charger();
    this.api.get<TableauBord>(`${CL_BASE}/tableau-de-bord`).subscribe({
      next: (d) => this.t.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Tableau de bord indisponible')),
    });
  }

  importLibelle(): string {
    const d = this.t()?.dernier_import;
    if (!this.t()) return '…';
    if (!d) return 'Aucun';
    return dateHeureFr(d.importe_le || d.cree_le);
  }

  importDetail(): string {
    const d = this.t()?.dernier_import;
    if (!d) return 'Aucun traitement ORION enregistré';
    return `${d.fichier_nom} · ${d.statut} · ${n(d.nb_clients)} clients`;
  }

  tone(v: number | null | undefined): string {
    return v ? 'warn' : '';
  }

  part(v: number | null | undefined, max: number): number {
    return max ? Math.max(2, Math.round(((v ?? 0) / max) * 100)) : 0;
  }

  pct(v: number | null | undefined, total: number): string {
    if (!total) return '—';
    return `${(((v ?? 0) / total) * 100).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;
  }

  private chargerConformite(): void {
    this.api.get<{ indicateurs: IndicDash[] }>(`${CL_BASE}/indicateurs`, { periode: 'mois_precedent' }).subscribe({
      next: (d) => this.conformite.set(d.indicateurs.filter((i) => KPI_CONFORMITE.includes(i.code))
        .sort((a, b) => KPI_CONFORMITE.indexOf(a.code) - KPI_CONFORMITE.indexOf(b.code))),
      error: () => this.conformite.set([]),
    });
  }

  private chargerDeclaration(): void {
    this.api.get<DeclarationDash[]>(`${CL_BASE}/declarations`).subscribe({
      next: (d) => this.derniere.set(d[0] ?? null),
      error: () => this.derniere.set(null),
    });
  }
}
