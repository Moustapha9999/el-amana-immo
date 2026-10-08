import { ChangeDetectionStrategy, Component, OnInit, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, TableauBord, n, valeurIndic } from '../clientele.models';
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
          <p class="bea-cl-head__sub">Un client = une racine ORION (6 chiffres). Les comptes et RIB sont rattachés à cette racine. Comptage : COUNT DISTINCT racine.</p>
        </div>
      </header>
      <div class="bea-cl-kpis">
        <a class="bea-cl-kpi" routerLink="/clientele/situation-pp"><span>Clients PP</span><strong>{{ n(t()?.pp) }}</strong></a>
        <a class="bea-cl-kpi" routerLink="/clientele/situation-pm"><span>Clients PM</span><strong>{{ n(t()?.pm) }}</strong></a>
        <div class="bea-cl-kpi"><span>Non identifiés</span><strong>{{ n(t()?.non_identifies) }}</strong></div>
        <div class="bea-cl-kpi"><span>Clients (distincts)</span><strong>{{ n(t()?.nb_clients) }}</strong></div>
        <div class="bea-cl-kpi"><span>Comptes</span><strong>{{ n(t()?.nb_comptes) }}</strong></div>
        <div class="bea-cl-kpi"><span>Ouverts</span><strong>{{ n(t()?.ouverts) }}</strong></div>
        <div class="bea-cl-kpi"><span>Clôturés</span><strong>{{ n(t()?.clotures) }}</strong></div>
        <a class="bea-cl-kpi" routerLink="/clientele/reporting"><span>Reporting</span><strong>Indicateurs</strong></a>
        <a class="bea-cl-kpi" routerLink="/clientele/declarations"><span>Déclaration BCM</span><strong>Mensuelle</strong></a>
      </div>
      @if (store.cap().reporting_voir && conformite().length) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Conformité — mois précédent</h2></div>
          <p class="bea-cl-hint" style="padding:0 1.1rem">Même moteur que le reporting et la déclaration BCM. Cliquer pour voir la population.</p>
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
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Sources des colonnes Situation</h2></div>
        <p class="bea-cl-hint" style="padding:0 1.1rem">Les colonnes absentes d’ORION ne sont pas inventées.</p>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Colonne métier</th><th>Source</th><th>Précision</th></tr></thead>
            <tbody>
              @for (s of t()?.sources ?? []; track s.colonne) {
                <tr>
                  <td><strong>{{ s.colonne }}</strong></td>
                  <td><span class="bea-cl-badge" [attr.data-s]="s.source === 'ABSENT' ? 'CLOTURE' : 'PP'">{{ s.source }}</span></td>
                  <td>{{ s.detail }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </section>
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
  readonly valeurIndic = valeurIndic;

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
