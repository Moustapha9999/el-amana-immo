import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
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

const ONGLETS: { id: string; label: string }[] = [
  { id: 'synthese', label: 'Synthèse' },
  { id: 'clientele', label: 'Clientèle' },
  { id: 'risques', label: 'Risques' },
  { id: 'kyc', label: 'KYC / EER' },
  { id: 'operations', label: 'Opérations' },
  { id: 'evolutions', label: 'Évolutions' },
  { id: 'qualite', label: 'Qualité & anomalies' },
  { id: 'exports', label: 'Exports & rapports' },
];

const SYNTHESE = [
  'cli.stock', 'cli.pp', 'cli.pm', 'cli.comptes', 'cli.nouveaux',
  'cli.risque.eleve', 'cli.risque.interdit', 'eer.maj_periode', 'alerte.stock', 'alerte.faux_positifs',
];

const LIBELLES_COLONNES: Record<string, string> = {
  racine_client: 'Racine client', nom_client: 'Nom client', profil_derive: 'Profil', code_agence: 'Agence',
  etat_client: 'État client', nb_comptes: 'Nb comptes', premiere_extraction: 'Première extraction',
  compte: 'Compte', rib: 'RIB', etat_compte: 'État compte', date_ouverture: 'Date d’ouverture',
  niveau: 'Niveau de risque', ancienne_classe: 'Ancienne classe', nouvelle_classe: 'Nouvelle classe',
  created_at: 'Date', id: 'Identifiant', statut: 'Statut', motif: 'Motif', reference: 'Référence',
  date_eer: 'Date EER', operation_type: 'Type d’opération',
};

function ongletDe(code: string): string {
  if (code.startsWith('eer.')) return 'kyc';
  if (code.startsWith('alerte.')) return 'qualite';
  if (code.startsWith('bcm.t2') || code.startsWith('bcm.t3')) return 'operations';
  if (code.includes('reclass')) return 'evolutions';
  if (code.includes('risque') || code === 'bcm.map.interdit') return 'risques';
  if (code.startsWith('cli.')) return 'clientele';
  return 'synthese';
}

function dansOnglet(id: string, code: string): boolean {
  if (id === 'clientele') return code.startsWith('cli.') && !code.includes('risque') && !code.includes('reclass');
  if (id === 'risques') return code.includes('risque') || code === 'bcm.map.interdit';
  if (id === 'kyc') return code.startsWith('eer.');
  if (id === 'operations') return code.startsWith('bcm.t2') || code.startsWith('bcm.t3');
  if (id === 'evolutions') return code.includes('reclass');
  if (id === 'qualite') return code.startsWith('alerte.');
  return false;
}

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
          <p class="bea-cl-head__sub">Moteur d’indicateurs commun ({{ t()?.moteur_version }}). Un client = COUNT DISTINCT racine. Analyse à la demande : la déclaration officielle reste dans <a routerLink="/clientele/declarations">Déclaration BCM</a>.</p>
        </div>
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
      <div class="bea-cl-tabs" role="tablist" aria-label="Reporting interne">
        @for (o of onglets; track o.id) {
          <button type="button" role="tab" [class.is-on]="onglet() === o.id" [attr.aria-selected]="onglet() === o.id" (click)="choisirOnglet(o.id)">{{ o.label }}</button>
        }
      </div>

      @if (onglet() === 'exports') {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Exports &amp; rapports</h2></div>
          <p class="bea-cl-hint" style="padding:0 1.1rem">Chaque fichier reprend les filtres affichés et porte l’en-tête de la banque, la période, la date d’export et des colonnes ajustées au contenu.</p>
          <div class="bea-cl-chips">
            <span><mat-icon>event</mat-icon>{{ libellePeriode() }}</span>
            <span><mat-icon>person</mat-icon>{{ profil || 'Tous profils' }}</span>
            <span><mat-icon>store</mat-icon>{{ agence ? 'Agence ' + agence : 'Toutes agences' }}</span>
            <span><mat-icon>public</mat-icon>{{ residence === 'R' ? 'Résidents' : residence === 'N' ? 'Non-résidents' : 'Toutes résidences' }}</span>
          </div>
          @if (store.cap().exporter) {
            <div class="bea-cl-exports">
              <article class="bea-cl-export">
                <mat-icon class="bea-cl-export__ico">summarize</mat-icon>
                <h3>Tableau des indicateurs</h3>
                <p>Excel : un onglet par rubrique (Clientèle, Risques, KYC, Opérations…) et un onglet Définitions. PDF : tableau unique regroupé par rubrique.</p>
                <div class="bea-cl-export__act">
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="exporterTableau('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporterTableau('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
                </div>
              </article>
              <article class="bea-cl-export">
                <mat-icon class="bea-cl-export__ico">group</mat-icon>
                <h3>Population d’un indicateur</h3>
                @if (detail(); as d) {
                  @if (d.calcule) {
                    <p>Liste détaillée de <strong>{{ d.libelle }}</strong> ({{ d.total }} ligne(s)). Excel : jusqu’à 20 000 lignes ; PDF : 3 000 premières lignes.</p>
                    <div class="bea-cl-export__act">
                      <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="exporterLignes('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporterLignes('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
                    </div>
                  } @else {
                    <p>{{ d.libelle }} est à configurer : aucune population n’est produite.</p>
                  }
                } @else {
                  <p>Ouvrez un indicateur dans l’un des onglets pour exporter sa population.</p>
                }
              </article>
              <article class="bea-cl-export">
                <mat-icon class="bea-cl-export__ico">account_balance</mat-icon>
                <h3>Déclaration BCM</h3>
                <p>Les états officiels (snapshot figé, Excel et PDF) se produisent dans le module de déclaration.</p>
                <div class="bea-cl-export__act">
                  <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/declarations"><mat-icon>arrow_forward</mat-icon> Déclarations</a>
                </div>
              </article>
            </div>
          } @else {
            <p class="bea-cl-hint" style="padding:0 1.1rem 1rem">Votre profil ne permet pas d’exporter.</p>
          }
        </section>
      } @else {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>{{ titreOnglet() }}</h2></div>
          @if (onglet() === 'operations') {
            <p class="bea-cl-hint" style="padding:0 1.1rem">Ces indicateurs alimentent aussi les tableaux BCM. Ici ils restent une analyse ; la validation et le snapshot se font dans la déclaration.</p>
          }
          @if (onglet() === 'qualite') {
            <p class="bea-cl-hint" style="padding:0 1.1rem">Alertes de filtrage sur la période choisie. Les trous de mapping se consultent dans <a routerLink="/clientele/mapping">Mapping &amp; sources</a>.</p>
          }
          <div class="bea-cl-kpis" style="margin:0.85rem 1rem 1rem">
            @for (i of visibles(); track i.code) {
              <button type="button" class="bea-cl-kpi" [class.is-on]="choisi()===i.code" [class.is-lock]="i.statut==='A_CONFIGURER'" (click)="ouvrir(i)">
                <span>{{ i.libelle }}</span>
                <strong>{{ val(i) }}</strong>
                <span class="bea-cl-badge" [attr.data-s]="i.statut">{{ i.statut === 'PRET_SOUS_RESERVE' ? 'sous réserve' : i.statut === 'A_CONFIGURER' ? 'à configurer' : 'prêt' }}</span>
              </button>
            } @empty {
              <p class="bea-cl-empty">Aucun indicateur dans cet onglet.</p>
            }
          </div>
        </section>
      }
      @if (detail(); as d) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>{{ d.libelle }}</h2>
            @if (d.calcule && store.cap().exporter) {
              <div style="display:flex;gap:0.4rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporterLignes('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporterLignes('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
              </div>
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
                <thead><tr>@for (c of d.colonnes; track c) { <th>{{ entete(c) }}</th> }</tr></thead>
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
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  readonly onglets = ONGLETS;
  readonly onglet = signal('synthese');
  readonly t = signal<Tableau | null>(null);
  readonly detail = signal<Detail | null>(null);
  readonly choisi = signal<string | null>(null);
  readonly page = signal(1);
  readonly busy = signal(false);
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

  readonly visibles = computed(() => {
    const items = this.t()?.indicateurs ?? [];
    const id = this.onglet();
    if (id === 'exports') return [];
    if (id === 'synthese') {
      return SYNTHESE.map((code) => items.find((i) => i.code === code)).filter((i): i is Indicateur => !!i);
    }
    return items.filter((i) => dansOnglet(id, i.code));
  });

  titreOnglet(): string {
    return this.onglets.find((o) => o.id === this.onglet())?.label ?? 'Synthèse';
  }

  ngOnInit(): void {
    this.store.charger();
    const qp = this.route.snapshot.queryParamMap;
    const periode = qp.get('periode');
    if (periode) this.periode = periode;
    const code = qp.get('code');
    const onglet = qp.get('onglet');
    if (code) {
      this.choisi.set(code);
      this.onglet.set(ongletDe(code));
    } else if (onglet && ONGLETS.some((o) => o.id === onglet)) {
      this.onglet.set(onglet);
    }
    this.charger();
  }

  choisirOnglet(id: string): void {
    this.onglet.set(id);
    if (id !== 'exports') {
      this.detail.set(null);
      this.choisi.set(null);
    }
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { onglet: id, code: null },
      queryParamsHandling: 'merge',
    });
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

  libellePeriode(): string {
    const f = this.t()?.fenetre;
    const lib = (this.t()?.periodes ?? this.periodesDefaut).find((p) => p.code === this.periode)?.libelle ?? this.periode;
    return f ? `${lib} · ${dateFr(f.date_debut)} → ${dateFr(f.date_fin)}` : lib;
  }

  entete(c: string): string {
    return LIBELLES_COLONNES[c] ?? c;
  }

  exporterTableau(fmt: 'xlsx' | 'pdf'): void {
    this.exporter(`${CL_BASE}/indicateurs.${fmt}`, `indicateurs-clientele.${fmt}`);
  }

  exporterLignes(fmt: 'xlsx' | 'pdf'): void {
    const code = this.choisi();
    if (code) this.exporter(`${CL_BASE}/indicateurs/${code}/lignes.${fmt}`, `indicateur-${code}.${fmt}`);
  }

  private exporter(url: string, nom: string): void {
    this.busy.set(true);
    this.api.download(url, this.params()).subscribe({
      next: (b) => {
        this.busy.set(false);
        telecharger(b, nom);
      },
      error: (e) => {
        this.busy.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible'));
      },
    });
  }
}
