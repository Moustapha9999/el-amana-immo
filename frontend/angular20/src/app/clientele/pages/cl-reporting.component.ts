import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { PaginationComponent } from '../../shared/pagination.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateFr, telecharger, valeurIndic } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface PeriodeOpt { code: string; libelle: string; }
interface Fenetre {
  code: string; date_debut: string; date_fin: string; type: string;
  simulation: boolean; bcm_officielle: boolean;
}
interface Indicateur {
  code: string; libelle: string; definition: string; formule: string; source: string;
  cle: string; periode: string; statut: string; reserve: string | null;
  bcm_tableau: string | null; valeur: number | null; mapping_provisoire: string | null;
  fenetre_appliquee: Fenetre;
}
interface Tableau {
  moteur_version: string; fenetre: Fenetre; periodes: PeriodeOpt[];
  bcm_periodicite_officielle: string; indicateurs: Indicateur[];
}
interface Detail extends Indicateur {
  calcule: boolean; total: number; page: number; taille: number;
  colonnes: string[]; items: Record<string, string | number | null>[];
}

const GROUPES: { titre: string; test: (c: string) => boolean }[] = [
  { titre: 'Stock', test: (c) => c.startsWith('cli.') && !c.includes('risque') && !c.includes('reclass') },
  { titre: 'Classification à la date', test: (c) => c.includes('risque') || c === 'bcm.map.interdit' },
  { titre: 'Reclassements', test: (c) => c.includes('reclass') },
  { titre: 'EER', test: (c) => c.startsWith('eer.') },
  { titre: 'Alertes et BCM', test: (c) => c.startsWith('alerte.') || (c.startsWith('bcm.') && c !== 'bcm.map.interdit') },
];

@Component({
  selector: 'bea-cl-reporting',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, PaginationComponent, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Pilotage</p>
          <h1>Reporting interne</h1>
          <p class="bea-cl-head__sub">Moteur d’indicateurs commun ({{ t()?.moteur_version }}). Un client = COUNT DISTINCT racine. La déclaration BCM officielle est mensuelle (<a routerLink="/clientele/declarations">Déclaration BCM</a>) ; les autres périodes sont des simulations.</p>
        </div>
        @if (store.cap().exporter) {
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporterTableau()"><mat-icon>download</mat-icon> Excel</button>
        }
      </header>
      @if (t()?.fenetre?.simulation) {
        <p class="bea-cl-note"><mat-icon>info</mat-icon>Période de simulation — ce n’est pas une déclaration BCM.</p>
      } @else if (t()?.fenetre?.bcm_officielle) {
        <p class="bea-cl-note bea-cl-note--info"><mat-icon>verified</mat-icon>Mois calendaire clos — période officielle BCM. Pour figer un snapshot : <a routerLink="/clientele/declarations">Déclaration BCM</a>.</p>
      }
      <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); charger()">
        <label>Période
          <select [(ngModel)]="periode" name="periode" (ngModelChange)="charger()">
            @for (p of t()?.periodes ?? periodesDefaut; track p.code) {
              <option [value]="p.code">{{ p.libelle }}</option>
            }
          </select>
        </label>
        @if (periode === 'personnalisee') {
          <label>Du<input type="date" [(ngModel)]="dateDebut" name="debut" /></label>
          <label>Au<input type="date" [(ngModel)]="dateFin" name="fin" /></label>
        }
        <label>Profil
          <select [(ngModel)]="profil" name="profil">
            <option value="">Tous</option>
            <option value="PP">PP</option>
            <option value="PM">PM</option>
            <option value="NON_IDENTIFIE">Non identifié</option>
          </select>
        </label>
        <label>Agence
          <select [(ngModel)]="agence" name="agence">
            <option value="">Toutes</option>
            @for (a of store.agences(); track a.code) {
              <option [value]="a.code">{{ a.code }} — {{ a.libelle }}</option>
            }
          </select>
        </label>
        <label>Résidence
          <select [(ngModel)]="residence" name="residence">
            <option value="">Tous</option>
            <option value="R">Résident</option>
            <option value="N">Non résident</option>
          </select>
        </label>
        <div style="display:flex;align-items:end">
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary"><mat-icon>search</mat-icon> Calculer</button>
        </div>
      </form>
      <div class="bea-cl-groups">
        @for (g of groupes(); track g.titre) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>{{ g.titre }}</h2></div>
            <div class="bea-cl-kpis" style="margin:0.85rem 1rem 1rem">
              @for (i of g.items; track i.code) {
                <button type="button" class="bea-cl-kpi" [class.is-on]="choisi()===i.code" [class.is-lock]="i.statut==='A_CONFIGURER'" (click)="ouvrir(i)">
                  <span>{{ i.libelle }}</span>
                  <strong>{{ val(i) }}</strong>
                  <span class="bea-cl-badge" [attr.data-s]="i.statut">{{ i.statut === 'PRET_SOUS_RESERVE' ? 'sous réserve' : i.statut === 'A_CONFIGURER' ? 'à configurer' : 'prêt' }}</span>
                </button>
              }
            </div>
          </section>
        }
      </div>
      @if (detail(); as d) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>{{ d.libelle }}</h2>
            @if (d.calcule && store.cap().exporter) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporterLignes()"><mat-icon>download</mat-icon> Population</button>
            }
          </div>
          <dl class="bea-cl-dl">
            <dt>Définition</dt><dd>{{ d.definition }}</dd>
            <dt>Formule</dt><dd><code>{{ d.formule }}</code></dd>
            <dt>Fenêtre</dt><dd>{{ dateFr(d.fenetre_appliquee.date_debut) }} → {{ dateFr(d.fenetre_appliquee.date_fin) }} ({{ d.periode }})</dd>
            @if (d.reserve) { <dt>Réserve</dt><dd>{{ d.reserve }}</dd> }
            @if (d.mapping_provisoire) { <dt>Mapping provisoire</dt><dd>{{ d.mapping_provisoire }}</dd> }
          </dl>
          @if (!d.calcule) {
            <p class="bea-cl-note"><mat-icon>block</mat-icon>Aucun chiffre n’est produit tant que la Conformité n’a pas défini cet indicateur.</p>
          } @else {
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr>@for (c of d.colonnes; track c) { <th>{{ c }}</th> }</tr></thead>
                <tbody>
                  @for (r of d.items; track $index) {
                    <tr>
                      @for (c of d.colonnes; track c) {
                        <td>
                          @if (c === 'racine_client' && r[c]) {
                            <a [routerLink]="['/clientele/clients', r[c]]"><code>{{ r[c] }}</code></a>
                          } @else { {{ r[c] ?? '—' }} }
                        </td>
                      }
                    </tr>
                  } @empty {
                    <tr><td [attr.colspan]="d.colonnes.length"><div class="bea-cl-empty">Aucune ligne.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
            <app-pagination [page]="d.page" [total]="d.total" [pageSize]="d.taille" label="lignes" (pageChange)="page.set($event); chargerDetail()" />
          }
        </section>
      }
    </div>
  `,
})
export class ClReportingComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly store = inject(ClienteleStore);
  readonly t = signal<Tableau | null>(null);
  readonly detail = signal<Detail | null>(null);
  readonly choisi = signal<string | null>(null);
  readonly page = signal(1);
  readonly dateFr = dateFr;
  readonly periodesDefaut: PeriodeOpt[] = [
    { code: 'mois_courant', libelle: 'Mois courant' },
    { code: 'mois_precedent', libelle: 'Mois précédent' },
    { code: 'personnalisee', libelle: 'Personnalisée' },
  ];
  periode = 'mois_courant';
  dateDebut = '';
  dateFin = '';
  profil = '';
  agence = '';
  residence = '';

  readonly groupes = computed(() => {
    const items = this.t()?.indicateurs ?? [];
    return GROUPES.map((g) => ({ titre: g.titre, items: items.filter((i) => g.test(i.code)) }))
      .filter((g) => g.items.length);
  });

  ngOnInit(): void {
    this.store.charger();
    const qp = this.route.snapshot.queryParamMap;
    const periode = qp.get('periode');
    if (periode) this.periode = periode;
    const code = qp.get('code');
    if (code) this.choisi.set(code);
    this.charger();
  }

  val(i: Indicateur): string {
    return valeurIndic(i.statut, i.valeur);
  }

  params(): Record<string, string> {
    const p: Record<string, string> = { periode: this.periode };
    if (this.periode === 'personnalisee' && this.dateDebut) p['date_debut'] = this.dateDebut;
    if (this.periode === 'personnalisee' && this.dateFin) p['date_fin'] = this.dateFin;
    if (this.agence.trim()) p['agence'] = this.agence.trim();
    if (this.profil) p['profil'] = this.profil;
    if (this.residence) p['residence'] = this.residence;
    return p;
  }

  charger(): void {
    this.api.get<Tableau>(`${CL_BASE}/indicateurs`, this.params()).subscribe({
      next: (d) => {
        this.t.set(d);
        const code = this.choisi();
        if (code) this.chargerDetail();
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Indicateurs indisponibles')),
    });
  }

  ouvrir(i: Indicateur): void {
    this.choisi.set(i.code);
    this.page.set(1);
    this.chargerDetail();
  }

  chargerDetail(): void {
    const code = this.choisi();
    if (!code) return;
    this.api.get<Detail>(`${CL_BASE}/indicateurs/${code}`, { ...this.params(), page: this.page(), taille: 50 }).subscribe({
      next: (d) => this.detail.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Détail indicateur indisponible')),
    });
  }

  exporterTableau(): void {
    this.api.download(`${CL_BASE}/indicateurs.xlsx`, this.params()).subscribe({
      next: (b) => telecharger(b, 'indicateurs-clientele.xlsx'),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible')),
    });
  }

  exporterLignes(): void {
    const code = this.choisi();
    if (!code) return;
    this.api.download(`${CL_BASE}/indicateurs/${code}/lignes.xlsx`, this.params()).subscribe({
      next: (b) => telecharger(b, `indicateur-${code}.xlsx`),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible')),
    });
  }
}
