import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CoreAdminIntegrationAccesComponent } from './core-admin-integration-acces.component';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  bornesPeriode,
  DestinationResume,
  disponibiliteLabel,
  ExecutionResume,
  executionFamilleLabel,
  executionStatutLabel,
  executionStatutTone,
  EXPORT_MAX_LIGNES,
  integrationStudioPermissions,
  PeriodeCode,
  PERIODES,
  PERMISSIONS_STUDIO,
  sansVides,
  SerieJour,
  TableauSupervision,
  telechargerBlob,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionService } from './core-admin-integration-execution.service';
import { FournisseurResume } from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

interface PointCourbe { x: number; y: number; titre: string }

/** Courbe SVG (viewBox 320×120) ; une valeur nulle coupe le tracé au lieu d'inventer un point. */
export function courbe(valeurs: (number | null | undefined)[], max: number, jours: string[], format: (v: number) => string) {
  const L = 320, H = 120, pad = 8;
  const n = valeurs.length;
  const pas = n > 1 ? (L - 2 * pad) / (n - 1) : 0;
  const points: PointCourbe[] = [];
  let d = '';
  let ouvert = false;
  valeurs.forEach((v, i) => {
    if (v === null || v === undefined) {
      ouvert = false;
      return;
    }
    const x = Math.round((n > 1 ? pad + i * pas : L / 2) * 10) / 10;
    const y = Math.round((H - pad - (Math.min(v, max) / (max || 1)) * (H - 2 * pad)) * 10) / 10;
    d += `${ouvert ? 'L' : 'M'}${x} ${y} `;
    ouvert = true;
    points.push({ x, y, titre: `${jours[i]} : ${format(v)}` });
  });
  return { d: d.trim(), points };
}

export function construireGraphe(series: SerieJour[]) {
  const maxVol = Math.max(1, ...series.map((s) => s.total));
  const pasAxe = Math.max(1, Math.ceil(series.length / 8));
  const jours = series.map((s) => s.jour.slice(8, 10) + '/' + s.jour.slice(5, 7));
  const cols = series.map((s, i) => ({
    jour: s.jour,
    total: s.total,
    h: Math.max(2, Math.round((s.total / maxVol) * 100)),
    okPct: s.total ? Math.round((s.succes / s.total) * 100) : 0,
    label: i % pasAxe === 0 ? jours[i] : '',
    titre: `${jours[i]} : ${s.total} test(s), ${s.succes} succès, ${s.echecs} échec(s)`,
  }));
  const latMax = Math.max(1, ...series.map((s) => s.latence_moyenne_ms ?? 0));
  const pct = (v: number) => `${Math.round(v * 1000) / 10} %`.replace('.', ',');
  const taux = courbe(series.map((s) => s.taux_succes), 1, jours, pct);
  const latence = courbe(series.map((s) => s.latence_moyenne_ms), latMax, jours, (v) => `${v} ms`);
  const total = series.reduce((a, s) => a + s.total, 0);
  return {
    cols,
    taux,
    latence,
    latMax,
    aDonnees: total > 0,
    resumeVolume: `${total} test(s) sur ${series.length} jour(s) ; maximum ${maxVol} sur un jour.`,
    resumeTaux: taux.points.map((p) => p.titre).join(' ; ') || 'Aucune donnée',
    resumeLatence: latence.points.map((p) => p.titre).join(' ; ') || 'Aucune mesure',
  };
}

const FILTRES = { periode: '7j' as PeriodeCode, depuis: '', jusqua: '', fournisseur_id: '', destination_id: '' };
type Filtres = typeof FILTRES;

@Component({
  selector: 'bea-core-admin-integration-supervision',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DatePipe, CoreAdminIconComponent, CoreAdminIntegrationAccesComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations">Studio d'intégration API</a></p>
          <h1>Supervision des intégrations</h1>
          <p>
            Indicateurs calculés uniquement sur les tests explicitement exécutés. Aucune sonde automatique :
            une configuration approuvée n’est pas une preuve de disponibilité.
          </p>
        </div>
        <div class="bea-integ-head-actions">
          @if (d.supervision()) {
            <button type="button" class="bea-admin-btn bea-admin-btn--refresh" [disabled]="chargement()" (click)="charger()">
              <bea-admin-icon name="refresh" /> Actualiser
            </button>
          }
          @if (d.supervision() && d.supervisionExport()) {
            <button type="button" class="bea-admin-btn" [disabled]="exportEnCours() || chargement()" (click)="exporter()" [attr.aria-busy]="exportEnCours()">
              <bea-admin-icon name="download" /> {{ exportEnCours() ? 'Export…' : 'Exporter CSV' }}
            </button>
          }
        </div>
      </header>

      @if (!d.supervision()) {
        <bea-integ-acces-refuse section="La supervision des intégrations" [permissions]="[P.supervision]" />
      } @else {
        <form class="bea-admin-panel bea-integ-filtres" [formGroup]="filtres" (ngSubmit)="charger()" aria-label="Filtres de supervision">
          <label class="bea-admin-field">
            <span>Période</span>
            <select formControlName="periode">
              @for (p of periodes; track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
            </select>
          </label>
          @if (filtres.controls.periode.value === 'perso') {
            <label class="bea-admin-field"><span>Depuis</span><input type="datetime-local" formControlName="depuis" /></label>
            <label class="bea-admin-field"><span>Jusqu’à</span><input type="datetime-local" formControlName="jusqua" /></label>
          }
          @if (d.fournisseurs()) {
            <label class="bea-admin-field">
              <span>Fournisseur</span>
              <select formControlName="fournisseur_id">
                <option value="">Tous</option>
                @for (f of fournisseurs(); track f.id) { <option [value]="f.id">{{ f.nom }}</option> }
              </select>
            </label>
          }
          @if (d.destinations()) {
            <label class="bea-admin-field">
              <span>Destination</span>
              <select formControlName="destination_id">
                <option value="">Toutes</option>
                @for (x of destinationsFiltrees(); track x.id) { <option [value]="x.id">{{ x.nom }}</option> }
              </select>
            </label>
          }
          <div class="bea-admin-toolbar__actions">
            <button type="submit" class="bea-admin-btn" [disabled]="chargement()">Appliquer</button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
          </div>
        </form>

        @if (chargement() && !tableau()) {
          ${squelette('Chargement de la supervision…')}
        } @else if (accesRefuse()) {
          <bea-integ-acces-refuse section="La supervision des intégrations" [permissions]="[P.supervision]" />
        } @else if (erreur(); as e) {
          <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
          <button type="button" class="bea-admin-btn" (click)="charger()">Réessayer</button>
        } @else if (tableau(); as t) {
          <div class="bea-integ-notice bea-integ-notice--info" role="note">
            <p>
              Période : {{ t.periode.depuis ? (t.periode.depuis | date: 'dd/MM/yyyy HH:mm') : 'début de la rétention' }}
              → {{ t.periode.jusqua ? (t.periode.jusqua | date: 'dd/MM/yyyy HH:mm') : 'maintenant' }}.
              Base de calcul : {{ t.periode.denominateur }}. Rétention : {{ t.retention_jours }} jours.
            </p>
          </div>
          <div class="bea-admin-kpis">
            <div class="bea-admin-kpi" data-tone="blue">
              <span class="bea-admin-kpi__icon"><bea-admin-icon name="science" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">Tests sur la période</p>
                <p class="bea-admin-kpi__value">{{ t.total === 0 ? 'Aucune donnée' : t.total }}</p>
              </div>
            </div>
            <div class="bea-admin-kpi" data-tone="green">
              <span class="bea-admin-kpi__icon"><bea-admin-icon name="check_circle" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">Taux de succès</p>
                <p class="bea-admin-kpi__value">{{ t.taux_succes == null ? 'Aucune donnée' : pourcent(t.taux_succes) }}</p>
                @if (t.total) { <p class="bea-integ-kpi-note">{{ t.succes }} succès, {{ t.echecs }} échec(s)</p> }
              </div>
            </div>
            <div class="bea-admin-kpi" data-tone="teal">
              <span class="bea-admin-kpi__icon"><bea-admin-icon name="speed" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">Latence moyenne / médiane</p>
                <p class="bea-admin-kpi__value">{{ t.latence_moyenne_ms == null ? 'Aucune mesure' : t.latence_moyenne_ms + ' / ' + t.latence_mediane_ms + ' ms' }}</p>
              </div>
            </div>
            <div class="bea-admin-kpi" data-tone="amber">
              <span class="bea-admin-kpi__icon"><bea-admin-icon name="schedule" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">Dernier test</p>
                <p class="bea-admin-kpi__value">{{ t.dernier ? (t.dernier.started_at | date: 'dd/MM/yyyy HH:mm') : 'Aucune mesure' }}</p>
                <p class="bea-integ-kpi-note">{{ dispo(t.disponibilite) }}</p>
              </div>
            </div>
            <a class="bea-admin-kpi bea-admin-kpi--link" data-tone="rose" routerLink="/admin/integrations/alertes" [queryParams]="{ statut: 'nouvelle' }">
              <span class="bea-admin-kpi__icon"><bea-admin-icon name="notifications_active" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">Alertes nouvelles / en cours</p>
                <p class="bea-admin-kpi__value">{{ alertesActives() ?? '—' }}</p>
              </div>
            </a>
          </div>

          @if (graphe(); as g) {
            @if (!g.aDonnees) {
              <section class="bea-admin-panel">
                <div class="bea-integ-empty">
                  <bea-admin-icon name="insights" />
                  <strong>Aucune donnée à représenter sur cette période.</strong>
                  <p>Les graphiques n’affichent que des tests réellement exécutés ; aucune valeur n’est simulée.</p>
                </div>
              </section>
            } @else {
              <div class="bea-integ-charts">
                <section class="bea-admin-panel">
                  <h2>Volume de tests par jour</h2>
                  <figure class="bea-integ-chart">
                    <div class="bea-integ-cols" role="img" [attr.aria-label]="g.resumeVolume">
                      @for (c of g.cols; track c.jour) {
                        <div class="bea-integ-col" [title]="c.titre">
                          <b>{{ c.total }}</b>
                          <span [style.height.%]="c.h">
                            <i data-k="ok" [style.height.%]="c.okPct"></i>
                            <i data-k="ko" [style.height.%]="100 - c.okPct"></i>
                          </span>
                        </div>
                      }
                    </div>
                    <div class="bea-integ-axe" aria-hidden="true">
                      @for (c of g.cols; track c.jour) { <span>{{ c.label }}</span> }
                    </div>
                    <ul class="bea-integ-legend">
                      <li><i style="background: var(--bea-brand-700)"></i>Succès</li>
                      <li><i style="background: #f59e0b"></i>Échecs</li>
                    </ul>
                    <figcaption>Jours comportant au moins un test (UTC).</figcaption>
                  </figure>
                </section>

                <section class="bea-admin-panel">
                  <h2>Taux de succès par jour</h2>
                  <figure class="bea-integ-chart">
                    <svg class="bea-integ-svg" viewBox="0 0 320 120" role="img" [attr.aria-label]="g.resumeTaux">
                      <line class="grille" x1="8" y1="8" x2="312" y2="8" />
                      <line class="grille" x1="8" y1="60" x2="312" y2="60" />
                      <line class="grille" x1="8" y1="112" x2="312" y2="112" />
                      <text x="10" y="18">100 %</text>
                      <text x="10" y="108">0 %</text>
                      <path class="courbe" [attr.d]="g.taux.d" />
                      @for (p of g.taux.points; track $index) {
                        <circle class="point" r="3" [attr.cx]="p.x" [attr.cy]="p.y"><title>{{ p.titre }}</title></circle>
                      }
                    </svg>
                    <figcaption>Succès ÷ tests du jour. Un jour sans test n’a pas de point.</figcaption>
                  </figure>
                </section>

                <section class="bea-admin-panel">
                  <h2>Latence moyenne par jour</h2>
                  <figure class="bea-integ-chart">
                    @if (g.latence.points.length === 0) {
                      <p class="bea-admin-panel__empty">Aucune mesure de latence.</p>
                    } @else {
                      <svg class="bea-integ-svg" viewBox="0 0 320 120" role="img" [attr.aria-label]="g.resumeLatence">
                        <line class="grille" x1="8" y1="8" x2="312" y2="8" />
                        <line class="grille" x1="8" y1="112" x2="312" y2="112" />
                        <text x="10" y="18">{{ g.latMax }} ms</text>
                        <text x="10" y="108">0 ms</text>
                        <path class="courbe" [attr.d]="g.latence.d" />
                        @for (p of g.latence.points; track $index) {
                          <circle class="point" r="3" [attr.cx]="p.x" [attr.cy]="p.y"><title>{{ p.titre }}</title></circle>
                        }
                      </svg>
                    }
                    <figcaption>Durée moyenne des tests mesurés (ms).</figcaption>
                  </figure>
                </section>

                <section class="bea-admin-panel">
                  <h2>Catégories de résultats</h2>
                  <ul class="bea-integ-hbars">
                    @for (e of t.erreurs; track e.categorie) {
                      <li [title]="famille(e.categorie)">
                        <span>{{ exec(e.categorie) }}</span><b>{{ e.nombre }}</b>
                        <em aria-hidden="true"><i [attr.data-k]="e.categorie === 'succes' ? 'ok' : 'ko'" [style.width.%]="largeur(e.nombre, t.total)"></i></em>
                      </li>
                    }
                  </ul>
                  <p class="bea-integ-muted">Erreur HTTP ou réponse invalide = réponse du fournisseur ; délai, TLS, DNS = connectivité ; refus, quota, secret requis = blocage par BEA DIGITAL.</p>
                </section>

                @if (t.par_fournisseur?.length) {
                  <section class="bea-admin-panel">
                    <h2>Résultats par fournisseur</h2>
                    <ul class="bea-integ-hbars">
                      @for (f of t.par_fournisseur; track f.fournisseur_id) {
                        <li>
                          <span>
                            @if (d.fournisseurs()) {
                              <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/fournisseurs', f.fournisseur_id]">{{ f.nom ?? 'Fournisseur' }}</a>
                            } @else { {{ f.nom ?? 'Fournisseur' }} }
                          </span>
                          <b>{{ f.succes }} / {{ f.total }}</b>
                          <em aria-hidden="true"><i data-k="ok" [style.width.%]="largeur(f.succes, f.total)"></i></em>
                        </li>
                      }
                    </ul>
                    <p class="bea-integ-muted">Succès / tests de la période.</p>
                  </section>
                }
              </div>
            }
          }

          <div class="bea-integ-stats">
            <section class="bea-admin-panel">
              <h2>Derniers résultats</h2>
              <dl class="bea-admin-dl">
                <div><dt>Dernier succès</dt><dd>{{ t.dernier_succes ? (t.dernier_succes.started_at | date: 'dd/MM/yyyy HH:mm') : 'Aucun' }}</dd></div>
                <div><dt>Dernier échec</dt><dd>
                  @if (t.dernier_echec) {
                    {{ t.dernier_echec.started_at | date: 'dd/MM/yyyy HH:mm' }} — {{ exec(t.dernier_echec.statut) }}
                  } @else { Aucun }
                </dd></div>
              </dl>
            </section>
          </div>

          <div class="bea-integ-stats">
            <section class="bea-admin-panel">
              <h2>Sans mesure récente</h2>
              @if (t.sans_mesure.length === 0) {
                <p class="bea-admin-panel__empty">Toutes les destinations ont un test récent.</p>
              } @else {
                <ul>
                  @for (x of t.sans_mesure; track x.id) {
                    <li>
                      @if (d.destinations()) {
                        <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/destinations', x.id]">{{ x.nom }}</a>
                      } @else { {{ x.nom }} }
                      — aucune mesure
                    </li>
                  }
                </ul>
              }
            </section>
            <section class="bea-admin-panel">
              <h2>Destinations suspendues</h2>
              @if (t.destinations_suspendues.length === 0) {
                <p class="bea-admin-panel__empty">Aucune.</p>
              } @else {
                <ul>
                  @for (x of t.destinations_suspendues; track x.id) {
                    <li>
                      @if (d.destinations()) {
                        <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/destinations', x.id]">{{ x.nom }}</a>
                      } @else { {{ x.nom }} }
                    </li>
                  }
                </ul>
              }
            </section>
          </div>

          <section class="bea-admin-panel">
            <div class="bea-admin-users__list-head">
              <h2>Dernières exécutions</h2>
              @if (d.testsView()) {
                <a class="bea-admin-table__link" routerLink="/admin/integrations/executions" [queryParams]="lienHistorique()">Historique complet</a>
              }
            </div>
            @if (!d.testsView()) {
              <p class="bea-admin-panel__empty">Le détail des exécutions exige <code>{{ P.testsView }}</code>.</p>
            } @else if (executions().length === 0) {
              <p class="bea-admin-panel__empty">Aucune donnée.</p>
            } @else {
              <div class="bea-admin-table-wrap">
                <table class="bea-admin-table">
                  <thead><tr><th>Date</th><th>Fournisseur</th><th>Opération</th><th>Statut</th><th>HTTP</th><th>Durée</th></tr></thead>
                  <tbody>
                    @for (e of executions(); track e.id) {
                      <tr>
                        <td><a class="bea-admin-table__link" routerLink="/admin/integrations/executions" [queryParams]="{ execution: e.id, periode: 'tout' }">{{ e.started_at | date: 'dd/MM/yyyy HH:mm:ss' }}</a></td>
                        <td>{{ e.fournisseur_nom ?? '—' }}</td>
                        <td class="bea-integ-path">{{ e.methode }} {{ e.chemin }}</td>
                        <td><span [class]="tone(e.statut)">{{ exec(e.statut) }}</span></td>
                        <td>{{ e.http_status ?? '—' }}</td>
                        <td>{{ e.duree_ms != null ? e.duree_ms + ' ms' : '—' }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </section>
        }
      }
    </section>
  `,
})
export class CoreAdminIntegrationSupervisionComponent implements OnInit {
  private readonly service = inject(CoreAdminIntegrationExecutionService);
  private readonly fourn = inject(CoreAdminIntegrationFournisseursService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  readonly d = integrationStudioPermissions();
  readonly P = PERMISSIONS_STUDIO;
  readonly periodes = PERIODES;
  readonly filtres = this.fb.nonNullable.group({ ...FILTRES });
  readonly tableau = signal<TableauSupervision | null>(null);
  readonly executions = signal<ExecutionResume[]>([]);
  readonly alertesActives = signal<string | null>(null);
  readonly chargement = signal(true);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly exportEnCours = signal(false);
  readonly fournisseurs = signal<FournisseurResume[]>([]);
  readonly destinations = signal<DestinationResume[]>([]);
  private readonly fournisseurChoisi = signal('');
  readonly destinationsFiltrees = computed(() => {
    const f = this.fournisseurChoisi();
    return f ? this.destinations().filter((x) => x.fournisseur_id === f) : this.destinations();
  });
  readonly exec = executionStatutLabel;
  readonly tone = executionStatutTone;
  readonly famille = executionFamilleLabel;
  readonly dispo = disponibiliteLabel;
  readonly graphe = computed(() => {
    const t = this.tableau();
    if (!t) return null;
    return construireGraphe(t.series ?? []);
  });

  ngOnInit(): void {
    if (!this.d.supervision()) return;
    const qp = this.route.snapshot.queryParamMap;
    const initial: Partial<Filtres> = {};
    for (const cle of Object.keys(FILTRES) as (keyof Filtres)[]) {
      const v = qp.get(cle);
      if (v) (initial as Record<string, string>)[cle] = v;
    }
    const dest = qp.get('destination');
    if (dest) initial.destination_id = dest;
    this.filtres.patchValue(initial);
    this.fournisseurChoisi.set(this.filtres.controls.fournisseur_id.value);
    if (this.d.fournisseurs()) {
      this.fourn.lister({}, 1, 100).subscribe({ next: (p) => this.fournisseurs.set(p.items), error: () => this.fournisseurs.set([]) });
    }
    if (this.d.destinations()) {
      this.service.listerDestinations({}, 1, 100).subscribe({ next: (p) => this.destinations.set(p.items), error: () => this.destinations.set([]) });
    }
    this.filtres.controls.fournisseur_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((id) => {
      this.fournisseurChoisi.set(id);
      this.filtres.patchValue({ destination_id: '' }, { emitEvent: false });
    });
    this.charger();
  }

  params(): Record<string, string> {
    const v = this.filtres.getRawValue();
    return sansVides({ ...bornesPeriode(v.periode, v.depuis, v.jusqua), fournisseur_id: v.fournisseur_id, destination_id: v.destination_id });
  }

  lienHistorique(): Record<string, string> {
    const v = this.filtres.getRawValue();
    return sansVides({ periode: v.periode, depuis: v.periode === 'perso' ? v.depuis : '', jusqua: v.periode === 'perso' ? v.jusqua : '', fournisseur_id: v.fournisseur_id, destination_id: v.destination_id });
  }

  reinitialiser(): void {
    this.filtres.reset({ ...FILTRES });
    this.fournisseurChoisi.set('');
    this.charger();
  }

  charger(): void {
    this.chargement.set(true);
    this.erreur.set(null);
    this.accesRefuse.set(false);
    this.synchroniserUrl();
    const p = this.params();
    this.service.tableau(p).subscribe({
      next: (t) => { this.tableau.set(t); this.chargement.set(false); },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Supervision inaccessible.'));
        this.chargement.set(false);
      },
    });
    if (this.d.testsView()) {
      this.service.executions(p, 1, 10).subscribe({ next: (r) => this.executions.set(r.items), error: () => this.executions.set([]) });
    }
    forkJoin({
      nouvelles: this.service.alertes({ statut: 'nouvelle' }, 1, 1),
      enCours: this.service.alertes({ statut: 'en_cours' }, 1, 1),
    }).subscribe({
      next: ({ nouvelles, enCours }) => this.alertesActives.set(`${nouvelles.total} / ${enCours.total}`),
      error: () => this.alertesActives.set(null),
    });
  }

  pourcent(taux: number): string {
    return `${Math.round(taux * 1000) / 10} %`.replace('.', ',');
  }

  largeur(n: number, total: number): number {
    return total ? Math.max(4, Math.round((n / total) * 100)) : 0;
  }

  async exporter(): Promise<void> {
    if (this.exportEnCours()) return;
    const total = this.tableau()?.total ?? 0;
    if (total === 0) {
      await this.dialogs.info('Aucune donnée à exporter sur cette période.', 'Export CSV');
      return;
    }
    this.exportEnCours.set(true);
    this.service.exporter(this.params()).subscribe({
      next: (blob) => {
        telechargerBlob(blob, 'supervision-integrations.csv');
        this.exportEnCours.set(false);
        void this.dialogs.success(
          total > EXPORT_MAX_LIGNES
            ? `Export généré : ${EXPORT_MAX_LIGNES} lignes les plus récentes sur ${total}. Affinez la période pour le reste.`
            : `Export généré : ${total} ligne(s).`,
        );
      },
      error: (err) => {
        this.exportEnCours.set(false);
        void this.dialogs.error(estAccesRefuse(err) ? `Export refusé : permission ${PERMISSIONS_STUDIO.supervisionExport} requise.` : messageErreur(err, 'Export impossible.'));
      },
    });
  }

  private synchroniserUrl(): void {
    const v = this.filtres.getRawValue();
    const queryParams = sansVides({ ...v, periode: v.periode === '7j' ? '' : v.periode });
    if (v.periode !== 'perso') {
      delete queryParams['depuis'];
      delete queryParams['jusqua'];
    }
    void this.router.navigate([], { relativeTo: this.route, queryParams, replaceUrl: true });
  }
}
