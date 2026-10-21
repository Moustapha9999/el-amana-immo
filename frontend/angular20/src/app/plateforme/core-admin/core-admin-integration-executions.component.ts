import { DatePipe, KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIntegrationAccesComponent } from './core-admin-integration-acces.component';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  bornesPeriode,
  DestinationResume,
  ExecutionDetail,
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
  STATUTS_EXECUTION,
  telechargerBlob,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionService } from './core-admin-integration-execution.service';
import { FournisseurResume, OperationResume } from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { ariaSort, basculerTri, etatExecution, IntegrationTriComponent, OrdreTri, squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

const FILTRES = {
  periode: '7j' as PeriodeCode, depuis: '', jusqua: '', fournisseur_id: '', operation_id: '', destination_id: '', statut: '', q: '',
  tri: 'started_at', ordre: 'desc',
};
type Filtres = typeof FILTRES;

@Component({
  selector: 'bea-core-admin-integration-executions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DatePipe, KeyValuePipe, CoreAdminIntegrationAccesComponent, CoreAdminIconComponent, IntegrationTriComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations">Studio d'intégration API</a></p>
          <h1>Historique des exécutions</h1>
          <p>Tests explicitement exécutés depuis le Studio, conservés {{ retention() }} jours. Aucune sonde automatique.</p>
        </div>
        <div class="bea-integ-head-actions">
          @if (d.testsView()) {
            <button type="button" class="bea-admin-btn bea-admin-btn--refresh" [disabled]="chargement()" (click)="charger()">
              <bea-admin-icon name="refresh" /> Actualiser
            </button>
          }
          @if (d.testsView() && d.supervisionExport()) {
            <button type="button" class="bea-admin-btn" [disabled]="exportEnCours() || chargement()" (click)="exporter()" [attr.aria-busy]="exportEnCours()">
              <bea-admin-icon name="download" /> {{ exportEnCours() ? 'Export…' : 'Exporter CSV' }}
            </button>
          }
        </div>
      </header>
      <div class="bea-integ-notice" role="note">
        <bea-admin-icon name="lock" />
        <p>Les exécutions sont des preuves : elles ne sont ni modifiables ni supprimables depuis le Studio. Seule la purge de rétention ({{ retention() }} jours) les retire.</p>
      </div>

      @if (!d.testsView()) {
        <bea-integ-acces-refuse section="L’historique des exécutions" [permissions]="[P.testsView]" />
      } @else {
        <form class="bea-admin-panel bea-integ-filtres" [formGroup]="filtres" (ngSubmit)="rechercher()" role="search" aria-label="Filtres de l’historique">
          <label class="bea-admin-field">
            <span>Recherche</span>
            <input type="search" formControlName="q" maxlength="120" placeholder="Identifiant de corrélation, chemin, hôte…" />
          </label>
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
            <label class="bea-admin-field">
              <span>Opération</span>
              <select formControlName="operation_id">
                <option value="">{{ filtres.controls.fournisseur_id.value ? 'Toutes' : 'Choisir d’abord un fournisseur' }}</option>
                @for (o of operations(); track o.id) { <option [value]="o.id">{{ o.methode }} {{ o.chemin }}</option> }
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
          <label class="bea-admin-field">
            <span>Statut</span>
            <select formControlName="statut">
              <option value="">Tous</option>
              @for (s of statuts; track s) { <option [value]="s">{{ label(s) }}</option> }
            </select>
          </label>
          <label class="bea-admin-field">
            <span>Environnement</span>
            <input type="text" value="TEST (seul environnement exécutable)" readonly aria-readonly="true" />
          </label>
          <div class="bea-admin-toolbar__actions">
            <button type="submit" class="bea-admin-btn" [disabled]="chargement()">Filtrer</button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
          </div>
        </form>

        @if (chargement() && items().length === 0) {
          ${squelette('Chargement de l’historique…')}
        } @else if (accesRefuse()) {
          <bea-integ-acces-refuse section="L’historique des exécutions" [permissions]="[P.testsView]" />
        } @else if (erreur(); as e) {
          <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
          <button type="button" class="bea-admin-btn" (click)="charger()">Réessayer</button>
        } @else {
          <section class="bea-admin-panel" [attr.aria-busy]="chargement()">
            <div class="bea-integ-list-head">
              <h2>Exécutions</h2>
              <span class="bea-integ-count" aria-live="polite">{{ total() }} résultat(s) — {{ libellePeriode() }}</span>
            </div>
            @if (items().length === 0) {
              <div class="bea-integ-empty">
                <bea-admin-icon name="history" />
                <strong>Aucune donnée : aucune exécution ne correspond à ces critères.</strong>
                <p>Les exécutions n’apparaissent qu’après un test lancé explicitement depuis la page Tests d’intégration.</p>
              </div>
            } @else {
              <div class="bea-admin-table-wrap">
                <table class="bea-admin-table bea-integ-cards">
                  <thead>
                    <tr>
                      <th scope="col" [attr.aria-sort]="sort('started_at')"><bea-integ-tri colonne="started_at" libelle="Date" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                      <th scope="col">Fournisseur</th>
                      <th scope="col">Opération</th>
                      <th scope="col">Destination</th>
                      <th scope="col">Env.</th>
                      <th scope="col" [attr.aria-sort]="sort('statut')"><bea-integ-tri colonne="statut" libelle="Statut" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                      <th scope="col" [attr.aria-sort]="sort('http_status')"><bea-integ-tri colonne="http_status" libelle="HTTP" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                      <th scope="col" [attr.aria-sort]="sort('duree_ms')"><bea-integ-tri colonne="duree_ms" libelle="Durée" [tri]="triActuel().tri" [ordre]="triActuel().ordre" (trier)="trier($event)" /></th>
                      <th scope="col"><span class="bea-integ-muted">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (e of items(); track e.id) {
                      <tr [attr.aria-selected]="detail()?.id === e.id">
                        <td data-label="Date">{{ e.started_at | date: 'dd/MM/yyyy HH:mm:ss' }}</td>
                        <td data-label="Fournisseur">{{ e.fournisseur_nom ?? '—' }}</td>
                        <td data-label="Opération">
                          <span class="bea-integ-method" [attr.data-m]="e.methode">{{ e.methode }}</span>
                          <span class="bea-integ-path">{{ e.chemin }}</span>
                          @if (e.operation_nom) { <div class="bea-integ-muted">{{ e.operation_nom }}</div> }
                        </td>
                        <td data-label="Destination">{{ e.destination_nom ?? '—' }}<div class="bea-integ-muted">{{ e.hote }}</div></td>
                        <td data-label="Env.">{{ e.environnement ?? 'TEST' }}</td>
                        <td data-label="Statut"><span [class]="tone(e.statut)" [title]="famille(e.statut)">{{ label(e.statut) }}</span></td>
                        <td data-label="HTTP">{{ e.http_status ?? '—' }}</td>
                        <td data-label="Durée">{{ e.duree_ms != null ? e.duree_ms + ' ms' : '—' }}</td>
                        <td data-label="">
                          <div class="bea-integ-row-actions">
                            <button type="button" class="bea-integ-icon-btn" (click)="ouvrir(e.id)" [attr.aria-label]="'Détail de l’exécution ' + e.correlation_id" title="Détail">
                              <bea-admin-icon name="visibility" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              <nav class="bea-admin-pager" aria-label="Pagination">
                <span>Page {{ page() }} / {{ totalPages() }}</span>
                <div>
                  <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1 || chargement()" (click)="aller(page() - 1)">Précédent</button>
                  <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages() || chargement()" (click)="aller(page() + 1)">Suivant</button>
                </div>
              </nav>
            }
          </section>
        }

        @if (chargementDetail()) {
          ${squelette('Chargement du détail…')}
        } @else if (erreurDetail(); as e) {
          <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        } @else if (detail(); as r) {
          <section class="bea-admin-panel" aria-live="polite" aria-labelledby="exec-detail-titre">
            <div class="bea-integ-list-head">
              <h2 id="exec-detail-titre">Exécution <code>{{ r.correlation_id }}</code></h2>
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="fermer()">Fermer</button>
            </div>
            <div class="bea-integ-etat" [attr.data-etat]="etatVisuel(r.statut)" role="status">
              <div>
                <h3><span [class]="tone(r.statut)">{{ label(r.statut) }}</span> — {{ famille(r.statut) }}</h3>
                <p>{{ r.message ?? '—' }}</p>
              </div>
            </div>
            <div class="bea-integ-detail" style="margin-top: 1rem">
              <section>
                <h3>Résultat</h3>
                <dl class="bea-integ-recap">
                  <dt>Statut HTTP</dt><dd>{{ r.http_status ?? '—' }}</dd>
                  <dt>Latence</dt><dd>{{ r.duree_ms != null ? r.duree_ms + ' ms' : '—' }}</dd>
                  <dt>Début</dt><dd>{{ r.started_at | date: 'dd/MM/yyyy HH:mm:ss' }}</dd>
                  <dt>Exécuté par</dt><dd>{{ r.acteur?.nom ?? '—' }}</dd>
                  @if (r.erreur_categorie) { <dt>Catégorie</dt><dd>{{ r.erreur_categorie }}</dd> }
                </dl>
              </section>
              <section>
                <h3>Cible</h3>
                <dl class="bea-integ-recap">
                  <dt>Fournisseur</dt>
                  <dd>
                    @if (d.fournisseurs()) {
                      <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/fournisseurs', r.fournisseur_id]">{{ r.fournisseur_nom ?? r.fournisseur_id }}</a>
                    } @else { {{ r.fournisseur_nom ?? '—' }} }
                  </dd>
                  <dt>Opération</dt><dd><span class="bea-integ-path">{{ r.methode }} {{ r.chemin }}</span> {{ r.operation_nom ? '— ' + r.operation_nom : '' }}</dd>
                  <dt>Destination</dt>
                  <dd>
                    @if (d.destinations()) {
                      <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/destinations', r.destination_id]">{{ r.destination_nom ?? r.destination_id }}</a>
                    } @else { {{ r.destination_nom ?? '—' }} }
                  </dd>
                  <dt>Hôte</dt><dd class="bea-integ-path">{{ r.hote }}:{{ r.port }} ({{ r.environnement }})</dd>
                </dl>
              </section>
              @if (r.controles && (r.controles | keyvalue).length) {
                <section>
                  <h3>Contrôles appliqués</h3>
                  <dl class="bea-integ-recap">
                    @for (c of r.controles | keyvalue; track c.key) { <dt>{{ c.key }}</dt><dd>{{ valeur(c.value) }}</dd> }
                  </dl>
                </section>
              }
              @if (r.limites && (r.limites | keyvalue).length) {
                <section>
                  <h3>Limites</h3>
                  <dl class="bea-integ-recap">
                    @for (c of r.limites | keyvalue; track c.key) { <dt>{{ c.key }}</dt><dd>{{ valeur(c.value) }}</dd> }
                  </dl>
                </section>
              }
            </div>
            @if (r.reponse) {
              <section style="margin-top: 1rem">
                <h3>Réponse</h3>
                @if (r.reponse.type_contenu) {
                  <p class="bea-integ-muted">{{ r.reponse.type_contenu }} — {{ r.reponse.taille ?? 0 }} octets{{ r.reponse.tronque ? ' (tronqué)' : '' }}</p>
                }
                @if (r.reponse.redirection) { <p class="bea-integ-muted">Redirection refusée vers : {{ r.reponse.redirection }}</p> }
                @if (r.reponse.extrait) {
                  <p class="bea-integ-muted">Extrait assaini (secrets masqués) :</p>
                  <pre class="bea-integ-result">{{ r.reponse.extrait }}</pre>
                }
              </section>
            }
          </section>
        }
      }
    </section>
  `,
})
export class CoreAdminIntegrationExecutionsComponent implements OnInit {
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
  readonly statuts = STATUTS_EXECUTION;
  readonly label = executionStatutLabel;
  readonly tone = executionStatutTone;
  readonly famille = executionFamilleLabel;
  readonly filtres = this.fb.nonNullable.group({ ...FILTRES });
  readonly items = signal<ExecutionResume[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 25;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly retention = signal(90);
  readonly chargement = signal(true);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly detail = signal<ExecutionDetail | null>(null);
  readonly chargementDetail = signal(false);
  readonly erreurDetail = signal<string | null>(null);
  readonly exportEnCours = signal(false);
  readonly fournisseurs = signal<FournisseurResume[]>([]);
  readonly operations = signal<OperationResume[]>([]);
  readonly destinations = signal<DestinationResume[]>([]);
  private readonly fournisseurChoisi = signal('');
  readonly destinationsFiltrees = computed(() => {
    const f = this.fournisseurChoisi();
    return f ? this.destinations().filter((x) => x.fournisseur_id === f) : this.destinations();
  });
  readonly libellePeriode = signal('');

  ngOnInit(): void {
    if (!this.d.testsView()) return;
    const qp = this.route.snapshot.queryParamMap;
    const initial: Partial<Filtres> = {};
    for (const cle of Object.keys(FILTRES) as (keyof Filtres)[]) {
      const v = qp.get(cle);
      if (v) (initial as Record<string, string>)[cle] = v;
    }
    this.filtres.patchValue(initial);
    this.page.set(Math.max(1, Number(qp.get('page')) || 1));
    this.fournisseurChoisi.set(this.filtres.controls.fournisseur_id.value);
    if (this.d.fournisseurs()) {
      this.fourn.lister({ inclure_archives: true }, 1, 100).subscribe({ next: (p) => this.fournisseurs.set(p.items), error: () => this.fournisseurs.set([]) });
      this.chargerOperations(this.filtres.controls.fournisseur_id.value);
    }
    if (this.d.destinations()) {
      this.service.listerDestinations({ inclure_archivees: true }, 1, 100).subscribe({ next: (p) => this.destinations.set(p.items), error: () => this.destinations.set([]) });
    }
    this.filtres.controls.fournisseur_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((id) => {
      this.fournisseurChoisi.set(id);
      this.filtres.patchValue({ operation_id: '', destination_id: '' }, { emitEvent: false });
      this.chargerOperations(id);
    });
    this.charger();
    const execution = qp.get('execution');
    if (execution) this.ouvrir(execution);
  }

  private chargerOperations(fournisseurId: string): void {
    this.operations.set([]);
    if (!fournisseurId || !this.d.fournisseurs()) return;
    this.fourn.operations(fournisseurId, {}, 1, 200).subscribe({ next: (r) => this.operations.set(r.items), error: () => this.operations.set([]) });
  }

  params(): Record<string, string> {
    const v = this.filtres.getRawValue();
    return sansVides({
      ...bornesPeriode(v.periode, v.depuis, v.jusqua),
      fournisseur_id: v.fournisseur_id,
      operation_id: v.operation_id,
      destination_id: v.destination_id,
      statut: v.statut,
      q: v.q,
      tri: v.tri === FILTRES.tri ? '' : v.tri,
      ordre: v.tri === FILTRES.tri && v.ordre === FILTRES.ordre ? '' : v.ordre,
    });
  }

  triActuel(): { tri: string; ordre: OrdreTri } {
    const v = this.filtres.getRawValue();
    return { tri: v.tri, ordre: v.ordre === 'asc' ? 'asc' : 'desc' };
  }

  sort(colonne: string) {
    return ariaSort(this.triActuel(), colonne);
  }

  trier(colonne: string): void {
    this.filtres.patchValue(basculerTri(this.triActuel(), colonne, colonne === 'started_at' || colonne === 'duree_ms' ? 'desc' : 'asc'));
    this.rechercher();
  }

  etatVisuel(statut: string): string {
    return etatExecution(statut);
  }

  valeur(v: unknown): string {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'boolean') return v ? 'oui' : 'non';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  }

  rechercher(): void {
    this.page.set(1);
    this.charger();
  }

  reinitialiser(): void {
    this.filtres.reset({ ...FILTRES });
    this.rechercher();
  }

  aller(page: number): void {
    this.page.set(page);
    this.charger();
  }

  charger(): void {
    this.chargement.set(true);
    this.erreur.set(null);
    this.accesRefuse.set(false);
    this.synchroniserUrl();
    const v = this.filtres.getRawValue();
    this.libellePeriode.set(PERIODES.find((p) => p.code === v.periode)?.libelle ?? '');
    this.service.executions(this.params(), this.page(), this.size).subscribe({
      next: (r) => {
        this.items.set(r.items);
        this.total.set(r.total);
        this.retention.set(r.retention_jours);
        this.chargement.set(false);
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Historique indisponible.'));
        this.chargement.set(false);
      },
    });
  }

  ouvrir(id: string): void {
    this.chargementDetail.set(true);
    this.erreurDetail.set(null);
    this.service.execution(id).subscribe({
      next: (r) => {
        this.detail.set(r);
        this.chargementDetail.set(false);
        this.synchroniserUrl();
      },
      error: (err) => {
        this.erreurDetail.set(messageErreur(err, 'Exécution introuvable.'));
        this.chargementDetail.set(false);
      },
    });
  }

  fermer(): void {
    this.detail.set(null);
    this.synchroniserUrl();
  }

  async exporter(): Promise<void> {
    if (this.exportEnCours()) return;
    if (this.total() === 0) {
      await this.dialogs.info('Aucune donnée à exporter pour ces critères.', 'Export CSV');
      return;
    }
    this.exportEnCours.set(true);
    this.service.exporter(this.params()).subscribe({
      next: (blob) => {
        telechargerBlob(blob, 'historique-integrations.csv');
        this.exportEnCours.set(false);
        const tronque = this.total() > EXPORT_MAX_LIGNES;
        void this.dialogs.success(
          tronque
            ? `Export généré : ${EXPORT_MAX_LIGNES} lignes les plus récentes sur ${this.total()}. Affinez les filtres pour le reste.`
            : `Export généré : ${this.total()} ligne(s).`,
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
    const queryParams: Record<string, string> = sansVides({
      ...v,
      periode: v.periode === '7j' ? '' : v.periode,
      tri: v.tri === FILTRES.tri ? '' : v.tri,
      ordre: v.ordre === FILTRES.ordre ? '' : v.ordre,
    });
    if (v.periode !== 'perso') {
      delete queryParams['depuis'];
      delete queryParams['jusqua'];
    }
    if (this.page() > 1) queryParams['page'] = String(this.page());
    const exec = this.detail()?.id;
    if (exec) queryParams['execution'] = exec;
    void this.router.navigate([], { relativeTo: this.route, queryParams, replaceUrl: true });
  }
}
