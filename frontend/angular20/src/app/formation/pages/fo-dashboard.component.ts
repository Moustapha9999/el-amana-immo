import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FoDonutComponent, FoGaugeComponent, FoHBarsComponent, FoLineComponent, FoStackComponent } from '../formation-charts';
import { FormationUiComponent } from '../formation-ui.component';
import { Dashboard, FO_BASE, SessionCourte, dateFr, jourMois, taux } from '../formation.models';
import { FormationStore } from '../formation.store';
import { FoSearchComponent } from '../shared/fo-search.component';

@Component({
  selector: 'bea-fo-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, FormationUiComponent, FoSearchComponent, FoStackComponent, FoDonutComponent, FoHBarsComponent, FoGaugeComponent, FoLineComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <p class="bea-stock-page__kicker">Conformité &amp; sécurité financière</p>
          <h1>Formation &amp; Sensibilisation</h1>
          <p class="bea-fo-head__sub">Suivi des formations, des présences et de la couverture des collaborateurs de la banque.</p>
        </div>
        <div class="bea-mg__actions">
          @if (cap().creer) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/formation/sessions/nouvelle"><mat-icon>add</mat-icon> Nouvelle formation</a>
          }
          @if (cap().reporting_voir) {
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/formation/reporting"><mat-icon>assessment</mat-icon> Reporting</a>
          }
        </div>
      </header>

      <div class="bea-mg__search">
        <bea-fo-search />
        <div class="bea-fo-yearbar" style="margin:0">
          <button type="button" class="bea-fx-chip" [class.is-active]="annee() === null" (click)="choisirAnnee(null)">Toutes années</button>
          @for (a of annees(); track a) {
            <button type="button" class="bea-fx-chip" [class.is-active]="annee() === a" (click)="choisirAnnee(a)">{{ a }}</button>
          }
        </div>
      </div>

      @if (!data()) {
        <div class="bea-fx-kpis">@for (i of [1, 2, 3, 4, 5, 6]; track i) { <span class="bea-fx-skel bea-fx-skel--kpi"></span> }</div>
        <div class="bea-fo-grid">
          <span class="bea-fx-skel bea-fx-skel--chart bea-fo-span2"></span><span class="bea-fx-skel bea-fx-skel--chart"></span>
          <span class="bea-fx-skel bea-fx-skel--chart"></span><span class="bea-fx-skel bea-fx-skel--chart"></span><span class="bea-fx-skel bea-fx-skel--chart"></span>
        </div>
      } @else {
        @let d = data()!;
        <div class="bea-fx-kpis">
          <a class="bea-fx-kpi" routerLink="/formation/sessions" [queryParams]="annee() ? { annee: annee() } : {}">
            <mat-icon>school</mat-icon><p>Formations</p><strong>{{ d.kpis.formations }}</strong>
            <small>{{ d.kpis.formations_realisees }} réalisée(s) · {{ d.kpis.formations_a_venir }} à venir</small>
          </a>
          <a class="bea-fx-kpi" data-tone="brand" routerLink="/formation/employes" [queryParams]="{ forme: 'oui' }">
            <mat-icon>verified_user</mat-icon><p>Employés formés</p><strong>{{ d.kpis.employes_formes }}</strong>
            <small>sur {{ d.kpis.employes_actifs }} employé(s) actif(s)</small>
          </a>
          <div class="bea-fx-kpi" data-tone="alert">
            <mat-icon>groups</mat-icon><p>Participations</p><strong>{{ d.kpis.participations }}</strong>
            <small>{{ d.kpis.employes_concernes }} employé(s) convoqué(s)</small>
          </div>
          <div class="bea-fx-kpi" data-tone="ok">
            <mat-icon>how_to_reg</mat-icon><p>Présents</p><strong>{{ d.kpis.presents }}</strong>
            <small>taux de présence {{ taux(d.kpis.taux_presence) }}</small>
          </div>
          <div class="bea-fx-kpi" data-tone="danger">
            <mat-icon>person_off</mat-icon><p>Absents</p><strong>{{ d.kpis.absents }}</strong>
            <small>{{ d.kpis.non_saisis }} présence(s) non saisie(s)</small>
          </div>
          <div class="bea-fx-kpi" data-tone="warn">
            <mat-icon>category</mat-icon><p>Thèmes couverts</p><strong>{{ d.kpis.themes_couverts }}</strong>
            <small>sur {{ nbThemes() }} thème(s) au référentiel</small>
          </div>
        </div>

        @if (d.nb_a_saisir || d.nb_a_cloturer || d.prochaines.length) {
          <div class="bea-fo-alerts">
            @if (d.nb_a_saisir) {
              <button type="button" class="bea-fo-alert" data-tone="warn" (click)="router.navigate(['/formation/presences'])">
                <mat-icon>edit_calendar</mat-icon>
                <span><strong>{{ d.nb_a_saisir }}</strong><small>formation(s) passée(s) : présences à saisir</small></span>
              </button>
            }
            @if (d.nb_a_cloturer) {
              <button type="button" class="bea-fo-alert" data-tone="alert" (click)="router.navigate(['/formation/sessions'], { queryParams: { statut: 'REALISEE' } })">
                <mat-icon>task_alt</mat-icon>
                <span><strong>{{ d.nb_a_cloturer }}</strong><small>formation(s) réalisée(s) à clôturer</small></span>
              </button>
            }
            @if (d.prochaines.length) {
              <button type="button" class="bea-fo-alert" (click)="ouvrir(d.prochaines[0]!)">
                <mat-icon>event_upcoming</mat-icon>
                <span><strong>{{ dateFr(d.prochaines[0]!.date) }}</strong><small>prochaine : {{ d.prochaines[0]!.theme }}</small></span>
              </button>
            }
            <button type="button" class="bea-fo-alert" data-tone="ok" (click)="router.navigate(['/formation/employes'], { queryParams: { forme: 'non' } })">
              <mat-icon>person_search</mat-icon>
              <span><strong>{{ d.couverture_globale.jamais_formes }}</strong><small>employé(s) actif(s) jamais formé(s){{ annee() ? ' en ' + annee() : '' }}</small></span>
            </button>
          </div>
        }

        <div class="bea-fo-grid">
          <section class="bea-mg__panel bea-fo-span2">
            <div class="bea-mg__panel-top">
              <div><h2>{{ annee() ? 'Évolution mensuelle ' + annee() : 'Participations par année' }}</h2><p class="bea-fo-panel-sub">Présents, absents et présences non saisies</p></div>
            </div>
            @if (annee()) {
              <bea-fo-line [series]="d.par_mois" />
            } @else {
              <bea-fo-stack [series]="d.par_annee" (choisir)="choisirAnnee(+$event)" />
            }
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><div><h2>Présence / absence</h2><p class="bea-fo-panel-sub">Sur les présences saisies</p></div></div>
            <bea-fo-donut [parts]="presenceParts()" [centre]="taux(d.kpis.taux_presence)" unite="présence" />
          </section>

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><div><h2>Couverture des employés</h2><p class="bea-fo-panel-sub">Actifs ayant suivi au moins une formation</p></div></div>
            <bea-fo-gauge [valeur]="d.couverture_globale.taux" libelle="formés">
              <span><strong>{{ d.couverture_globale.formes }}</strong> formé(s)</span>
              <span><strong>{{ d.couverture_globale.jamais_formes }}</strong> jamais formé(s)</span>
              <span><strong>{{ d.couverture_globale.actifs }}</strong> actif(s)</span>
            </bea-fo-gauge>
          </section>
          <section class="bea-mg__panel bea-fo-span2">
            <div class="bea-mg__panel-top"><div><h2>Couverture par périmètre</h2><p class="bea-fo-panel-sub">Part des employés actifs formés</p></div></div>
            <ul class="bea-fo-hbars">
              @for (c of d.couverture; track c.libelle; let i = $index) {
                <li [style.--i]="i">
                  <span class="bea-fo-hbars__label" [title]="c.libelle">{{ c.libelle }}</span>
                  <span class="bea-fo-hbars__track"><i class="is-v" [style.width.%]="c.taux ?? 0"></i></span>
                  <span class="bea-fo-hbars__value">{{ taux(c.taux) }}<small>{{ c.formes }}/{{ c.actifs }}</small></span>
                </li>
              } @empty {
                <li><span class="bea-fo-hint">Aucun employé actif.</span></li>
              }
            </ul>
          </section>

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><div><h2>Par thème</h2><p class="bea-fo-panel-sub">Participations</p></div></div>
            <bea-fo-hbars [groupes]="d.par_theme" [cliquable]="cap().reporting_voir" (choisir)="versReporting('theme_id', 'THEME', $event)" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><div><h2>Par périmètre</h2><p class="bea-fo-panel-sub">Participations</p></div></div>
            <bea-fo-hbars [groupes]="d.par_perimetre" [cliquable]="cap().reporting_voir" (choisir)="versReporting('perimetre_id', 'PERIMETRE', $event)" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><div><h2>Par entité</h2><p class="bea-fo-panel-sub">Top 8 des participations</p></div></div>
            <bea-fo-hbars [groupes]="d.par_entite" [cliquable]="cap().reporting_voir" (choisir)="versEntite($event)" />
          </section>

          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Présences à saisir</h2>
              @if (d.nb_a_saisir) { <span class="bea-mg__count">{{ d.nb_a_saisir }}</span> }
            </div>
            <ul class="bea-fo-list">
              @for (s of d.a_saisir; track s.id; let i = $index) {
                <li [style.--i]="i" (click)="ouvrir(s, true)">
                  <span class="bea-fo-date bea-fo-date--warn"><b>{{ jm(s.date).jour }}</b><span>{{ jm(s.date).mois }}</span></span>
                  <span class="bea-fo-list__main"><strong>{{ s.theme }}</strong><small>{{ s.lieu }} · {{ s.reference }}</small></span>
                  <span class="bea-fo-list__aside"><span>{{ s.participants }} pers.</span></span>
                </li>
              } @empty {
                <li style="cursor:default"><span class="bea-fo-hint"><mat-icon style="vertical-align:middle;color:#15803d">check_circle</mat-icon> Toutes les présences sont à jour.</span></li>
              }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Prochaines formations</h2></div>
            <ul class="bea-fo-list">
              @for (s of d.prochaines; track s.id; let i = $index) {
                <li [style.--i]="i" (click)="ouvrir(s)">
                  <span class="bea-fo-date"><b>{{ jm(s.date).jour }}</b><span>{{ jm(s.date).mois }}</span></span>
                  <span class="bea-fo-list__main"><strong>{{ s.theme }}</strong><small>{{ s.lieu }} · {{ s.reference }}</small></span>
                  <span class="bea-fo-list__aside"><span>{{ s.participants }} pers.</span></span>
                </li>
              } @empty {
                <li style="cursor:default"><span class="bea-fo-hint">Aucune formation planifiée.</span></li>
              }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Dernières réalisées</h2></div>
            <ul class="bea-fo-list">
              @for (s of d.dernieres; track s.id; let i = $index) {
                <li [style.--i]="i" (click)="ouvrir(s)">
                  <span class="bea-fo-date bea-fo-date--muted"><b>{{ jm(s.date).jour }}</b><span>{{ jm(s.date).mois }}</span></span>
                  <span class="bea-fo-list__main"><strong>{{ s.theme }}</strong><small>{{ s.lieu }} · {{ jm(s.date).annee }}</small></span>
                  <span class="bea-fo-list__aside"><span class="bea-fo-badge" [attr.data-s]="s.statut">{{ s.statut_libelle }}</span></span>
                </li>
              } @empty {
                <li style="cursor:default"><span class="bea-fo-hint">Aucune formation réalisée.</span></li>
              }
            </ul>
          </section>
        </div>
      }
    </div>
  `,
})
export class FoDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly store = inject(FormationStore);
  readonly router = inject(Router);

  readonly cap = this.store.cap;
  readonly data = signal<Dashboard | null>(null);
  readonly annee = signal<number | null>(null);
  private readonly anneesConnues = signal<number[]>([]);

  readonly dateFr = dateFr;
  readonly taux = taux;
  readonly jm = jourMois;

  readonly annees = computed(() => this.anneesConnues().slice(0, 8));
  readonly nbThemes = computed(() => this.store.refs('THEME').length);
  readonly presenceParts = computed(() => {
    const d = this.data();
    if (!d) return [];
    const couleurs: Record<string, string> = { PRESENT: '#15803d', ABSENT: '#dc2626', NON_SAISI: '#cbd5e1' };
    return d.presence.map((p) => ({ label: p.libelle, value: p.valeur, color: couleurs[p.cle], cle: p.cle }));
  });

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  choisirAnnee(a: number | null): void {
    if (this.annee() === a) return;
    this.annee.set(a);
    this.data.set(null);
    this.charger();
  }

  private charger(): void {
    const a = this.annee();
    this.api.get<Dashboard>(`${FO_BASE}/tableau-de-bord`, a ? { annee: a } : undefined).subscribe({
      next: (d) => {
        if (!this.anneesConnues().length || !a) this.anneesConnues.set(d.annees);
        this.data.set(d);
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Tableau de bord indisponible')),
    });
  }

  ouvrir(s: SessionCourte, saisie = false): void {
    void this.router.navigate(['/formation/sessions', s.id], saisie ? { queryParams: { saisie: 1 } } : {});
  }

  versReporting(champ: string, domaine: 'THEME' | 'PERIMETRE', libelle: string): void {
    const id = this.store.refs(domaine, true).find((r) => r.libelle === libelle)?.id;
    const qp: Record<string, string | number> = id ? { [champ]: id } : {};
    if (this.annee()) qp['annee'] = this.annee()!;
    void this.router.navigate(['/formation/reporting'], { queryParams: qp });
  }

  versEntite(libelle: string): void {
    const id = this.store.entites().find((e) => e.libelle === libelle)?.id;
    const qp: Record<string, string | number> = id ? { entite_id: id } : {};
    if (this.annee()) qp['annee'] = this.annee()!;
    void this.router.navigate(['/formation/reporting'], { queryParams: qp });
  }
}
