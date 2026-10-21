import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal, WritableSignal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin, map, Observable } from 'rxjs';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CoreAdminIntegrationAccesComponent } from './core-admin-integration-acces.component';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  bornesPeriode,
  ExecutionResume,
  executionStatutLabel,
  executionStatutTone,
  integrationStudioPermissions,
  PERMISSIONS_ENTREE_STUDIO,
  PERMISSIONS_STUDIO,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionService } from './core-admin-integration-execution.service';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import {
  authLabel,
  disponibiliteLabel,
  disponibiliteTone,
  IntegrationCatalogueFiltres,
  IntegrationCatalogueFiltreValeurs,
  IntegrationCatalogueKpis,
  IntegrationErreur,
  integrationErreur,
  IntegrationOperationResume,
  PERMISSION_STUDIO,
  permissionStatutLabel,
  schemaStatutLabel,
} from './core-admin-integrations.models';
import { CoreAdminIntegrationsService } from './core-admin-integrations.service';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

const ACCES_REFUSE = `
  <div class="bea-admin-panel">
    <h2>Accès refusé</h2>
    <p class="bea-admin-panel__hint">
      Le Studio d'intégration API exige une session BEA DIGITAL (Login 1) et la permission
      <code>${PERMISSION_STUDIO}</code>. Un jeton de module (Login 2) n'est pas accepté.
    </p>
  </div>
`;

type Bloc<T> =
  | { etat: 'interdit' }
  | { etat: 'chargement' }
  | { etat: 'erreur'; message: string }
  | { etat: 'ok'; valeur: T };

interface KpiFournisseurs { total: number; valides: number; operations: number; partiel: boolean }
interface KpiDestinations { total: number; actives: number; suspendues: number }
interface KpiExecutions { total: number; succes: number; dernieres: ExecutionResume[] }
interface KpiAlertes { nouvelles: number; enCours: number }

const PERIODE_ACCUEIL_JOURS = 7;

@Component({
  selector: 'bea-core-admin-integrations-overview',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe, CoreAdminIconComponent, CoreAdminIntegrationAccesComponent],
  styles: [
    INTEGRATIONS_STYLES,
    `
      .bea-integ-legende { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: 0.5rem 1.25rem; margin: 0; }
      .bea-integ-legende div { display: flex; gap: 0.5rem; align-items: baseline; }
      .bea-integ-legende dt { flex: 0 0 auto; }
      .bea-integ-legende dd { margin: 0; font-size: 0.82rem; color: var(--bea-ink-muted); }
    `,
  ],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Studio d'intégration API</h1>
          <p>
            Vue d'ensemble du Studio : catalogue interne, fournisseurs externes, destinations de test, exécutions et alertes.
            Cette page ne déclenche aucun appel vers un fournisseur ; les indicateurs sont lus dans la base BEA DIGITAL.
          </p>
        </div>
      </header>

      @if (!aucunDroit()) {
        <div class="bea-admin-kpis">
          <a class="bea-admin-kpi" [class.bea-admin-kpi--link]="d.fournisseurs()" data-tone="blue" [routerLink]="d.fournisseurs() ? '/admin/integrations/fournisseurs' : null">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="cloud" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Fournisseurs configurés / validés</p>
              @switch (fournisseurs().etat) {
                @case ('ok') {
                  @if (valeur(fournisseurs()); as f) {
                    <p class="bea-admin-kpi__value">{{ f.total === 0 ? 'Aucune donnée' : f.total + ' / ' + f.valides }}</p>
                  }
                }
                @case ('interdit') { <p class="bea-integ-kpi-note">Permission requise : {{ P.fournisseurs }}</p> }
                @case ('erreur') { <p class="bea-integ-kpi-note" role="alert">Indisponible</p> }
                @default { <p class="bea-integ-kpi-note">Chargement…</p> }
              }
            </div>
          </a>
          <a class="bea-admin-kpi" [class.bea-admin-kpi--link]="d.fournisseurs()" data-tone="teal" [routerLink]="d.fournisseurs() ? '/admin/integrations/fournisseurs' : null">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="list_alt" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Opérations externes configurées</p>
              @switch (fournisseurs().etat) {
                @case ('ok') {
                  @if (valeur(fournisseurs()); as f) {
                    <p class="bea-admin-kpi__value">{{ f.operations === 0 ? 'Aucune donnée' : f.operations }}</p>
                    @if (f.partiel) { <p class="bea-integ-kpi-note">Sur les 100 fournisseurs les plus récents</p> }
                  }
                }
                @case ('interdit') { <p class="bea-integ-kpi-note">Permission requise : {{ P.fournisseurs }}</p> }
                @case ('erreur') { <p class="bea-integ-kpi-note" role="alert">Indisponible</p> }
                @default { <p class="bea-integ-kpi-note">Chargement…</p> }
              }
            </div>
          </a>
          <a class="bea-admin-kpi" [class.bea-admin-kpi--link]="d.destinations()" data-tone="green" [routerLink]="d.destinations() ? '/admin/integrations/destinations' : null">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="public" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Destinations TEST approuvées</p>
              @switch (destinations().etat) {
                @case ('ok') {
                  @if (valeur(destinations()); as dst) {
                    <p class="bea-admin-kpi__value">{{ dst.total === 0 ? 'Aucune donnée' : dst.actives + ' / ' + dst.total }}</p>
                    @if (dst.suspendues) { <p class="bea-integ-kpi-note">{{ dst.suspendues }} suspendue(s)</p> }
                  }
                }
                @case ('interdit') { <p class="bea-integ-kpi-note">Permission requise : {{ P.destinations }}</p> }
                @case ('erreur') { <p class="bea-integ-kpi-note" role="alert">Indisponible</p> }
                @default { <p class="bea-integ-kpi-note">Chargement…</p> }
              }
            </div>
          </a>
          <a class="bea-admin-kpi" [class.bea-admin-kpi--link]="d.testsView()" data-tone="amber" [routerLink]="d.testsView() ? '/admin/integrations/executions' : null">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="science" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Tests exécutés ({{ periodeJours }} derniers jours) — succès</p>
              @switch (executions().etat) {
                @case ('ok') {
                  @if (valeur(executions()); as x) {
                    <p class="bea-admin-kpi__value">{{ x.total === 0 ? 'Aucune donnée' : x.total + ' — ' + taux(x) }}</p>
                  }
                }
                @case ('interdit') { <p class="bea-integ-kpi-note">Permission requise : {{ P.testsView }}</p> }
                @case ('erreur') { <p class="bea-integ-kpi-note" role="alert">Indisponible</p> }
                @default { <p class="bea-integ-kpi-note">Chargement…</p> }
              }
            </div>
          </a>
          <a class="bea-admin-kpi" [class.bea-admin-kpi--link]="d.supervision()" data-tone="rose" [routerLink]="d.supervision() ? '/admin/integrations/alertes' : null">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="notifications_active" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Alertes actives (nouvelles / en cours)</p>
              @switch (alertes().etat) {
                @case ('ok') {
                  @if (valeur(alertes()); as a) {
                    <p class="bea-admin-kpi__value">{{ a.nouvelles + a.enCours === 0 ? 'Aucune' : a.nouvelles + ' / ' + a.enCours }}</p>
                  }
                }
                @case ('interdit') { <p class="bea-integ-kpi-note">Permission requise : {{ P.supervision }}</p> }
                @case ('erreur') { <p class="bea-integ-kpi-note" role="alert">Indisponible</p> }
                @default { <p class="bea-integ-kpi-note">Chargement…</p> }
              }
            </div>
          </a>
        </div>
      }

      @if (aucunDroit()) {
        <bea-integ-acces-refuse section="Le Studio d’intégration API" [permissions]="permissionsEntree" />
      } @else {
        <section class="bea-admin-panel">
          <div class="bea-admin-users__list-head">
            <h2>Dernières exécutions de test</h2>
            @if (d.testsView()) { <a class="bea-admin-table__link" routerLink="/admin/integrations/executions">Tout l’historique</a> }
          </div>
          @switch (executions().etat) {
            @case ('interdit') { <p class="bea-admin-panel__empty">Permission requise : <code>{{ P.testsView }}</code>.</p> }
            @case ('erreur') {
              <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ messageBloc(executions()) }}</p></div>
            }
            @case ('chargement') { <p class="bea-admin-dash__loading">Chargement…</p> }
            @default {
              @if (valeur(executions()); as x) {
                @if (x.dernieres.length === 0) {
                  <p class="bea-admin-panel__empty">Aucune donnée : aucun test n’a été exécuté sur la période.</p>
                } @else {
                  <div class="bea-admin-table-wrap">
                    <table class="bea-admin-table">
                      <thead><tr><th>Date</th><th>Fournisseur</th><th>Opération</th><th>Statut</th><th>HTTP</th><th>Durée</th></tr></thead>
                      <tbody>
                        @for (e of x.dernieres; track e.id) {
                          <tr>
                            <td><a class="bea-admin-table__link" routerLink="/admin/integrations/executions" [queryParams]="{ execution: e.id }">{{ e.started_at | date: 'dd/MM/yyyy HH:mm' }}</a></td>
                            <td>{{ e.fournisseur_nom ?? '—' }}</td>
                            <td><span class="bea-integ-method" [attr.data-m]="e.methode">{{ e.methode }}</span> <span class="bea-integ-path">{{ e.chemin }}</span></td>
                            <td><span [class]="statutTone(e.statut)">{{ statutLabel(e.statut) }}</span></td>
                            <td>{{ e.http_status ?? '—' }}</td>
                            <td>{{ e.duree_ms != null ? e.duree_ms + ' ms' : '—' }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              }
            }
          }
        </section>

        <section class="bea-admin-panel">
          <h2>Lire les statuts</h2>
          <p class="bea-admin-panel__hint">
            Trois notions distinctes : la <strong>validation</strong> (décision humaine sur une configuration),
            la <strong>connectivité</strong> (un test a pu joindre la destination) et la <strong>disponibilité</strong>
            (résultat du dernier test, jamais une garantie de service).
          </p>
          <dl class="bea-integ-legende">
            <div><dt><span class="bea-badge bea-badge--bientot">Brouillon</span></dt><dd>Configuration en cours, modifiable, jamais appelée.</dd></div>
            <div><dt><span class="bea-badge bea-badge--bientot">À valider</span></dt><dd>Soumise à un valideur ; aucun test possible.</dd></div>
            <div><dt><span class="bea-badge bea-badge--actif">Validée</span></dt><dd>Fournisseur validé : configuration approuvée, pas une preuve de connectivité.</dd></div>
            <div><dt><span class="bea-badge bea-badge--inactif">Suspendue</span></dt><dd>Plus aucun test autorisé jusqu’à réactivation.</dd></div>
            <div><dt><span class="bea-badge bea-badge--actif">TEST approuvé</span></dt><dd>Destination de test approuvée : hôtes, port 443 et méthodes figés.</dd></div>
            <div><dt><span class="bea-badge bea-badge--actif">Testée</span></dt><dd>Au moins un test a été exécuté et enregistré.</dd></div>
            <div><dt><span class="bea-badge bea-badge--inactif">En erreur</span></dt><dd>Le dernier test a échoué (HTTP, délai, TLS, DNS ou réponse invalide).</dd></div>
            <div><dt><span class="bea-badge">Aucune mesure</span></dt><dd>Jamais testée ou sans test récent : disponibilité inconnue.</dd></div>
          </dl>
        </section>

        @if (d.catalogue()) {
          @if (catalogue(); as k) {
            <section class="bea-admin-panel">
              <div class="bea-admin-users__list-head">
                <h2>Catalogue de l’API interne BEA DIGITAL</h2>
                <a class="bea-admin-table__link" routerLink="/admin/integrations/catalogue">Ouvrir le catalogue</a>
              </div>
              <div class="bea-admin-kpis">
                @for (card of cartes(k); track card.label) {
                  <a class="bea-admin-kpi bea-admin-kpi--link" [attr.data-tone]="card.tone" [routerLink]="'/admin/integrations/catalogue'" [queryParams]="card.query">
                    <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="card.icon" /></span>
                    <div class="bea-admin-kpi__copy">
                      <p class="bea-admin-kpi__label">{{ card.label }}</p>
                      <p class="bea-admin-kpi__value">{{ card.value }}</p>
                    </div>
                  </a>
                }
              </div>
              <div class="bea-integ-stats">
                @for (bloc of repartitions(k); track bloc.titre) {
                  <div>
                    <h3>{{ bloc.titre }}</h3>
                    <table>
                      <tbody>
                        @for (ligne of bloc.lignes; track ligne.cle) {
                          <tr>
                            <td><a class="bea-admin-table__link" [routerLink]="'/admin/integrations/catalogue'" [queryParams]="ligne.query">{{ ligne.libelle }}</a></td>
                            <td>{{ ligne.valeur }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              </div>
              <p class="bea-integ-muted">{{ avertissement() }}</p>
            </section>
          } @else if (erreurCatalogue(); as e) {
            @if (e.accesRefuse) {
              <bea-integ-acces-refuse section="Le catalogue API" [permissions]="[P.catalogue]" />
            } @else {
              <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e.message }}</p></div>
            }
          }
        }
      }
    </section>
  `,
})
export class CoreAdminIntegrationsOverviewComponent implements OnInit {
  private readonly studio = inject(CoreAdminIntegrationsService);
  private readonly fourn = inject(CoreAdminIntegrationFournisseursService);
  private readonly exec = inject(CoreAdminIntegrationExecutionService);

  readonly d = integrationStudioPermissions();
  readonly P = PERMISSIONS_STUDIO;
  readonly permissionsEntree = PERMISSIONS_ENTREE_STUDIO;
  readonly periodeJours = PERIODE_ACCUEIL_JOURS;
  readonly aucunDroit = computed(
    () => !(this.d.catalogue() || this.d.clients() || this.d.fournisseurs() || this.d.destinations()
      || this.d.testsView() || this.d.testsExecute() || this.d.supervision()),
  );

  readonly catalogue = signal<IntegrationCatalogueKpis | null>(null);
  readonly erreurCatalogue = signal<IntegrationErreur | null>(null);
  readonly avertissement = signal('');
  readonly fournisseurs = signal<Bloc<KpiFournisseurs>>({ etat: 'chargement' });
  readonly destinations = signal<Bloc<KpiDestinations>>({ etat: 'chargement' });
  readonly executions = signal<Bloc<KpiExecutions>>({ etat: 'chargement' });
  readonly alertes = signal<Bloc<KpiAlertes>>({ etat: 'chargement' });
  readonly statutLabel = executionStatutLabel;
  readonly statutTone = executionStatutTone;

  ngOnInit(): void {
    this.charger();
  }

  valeur<T>(b: Bloc<T>): T | null {
    return b.etat === 'ok' ? b.valeur : null;
  }

  messageBloc<T>(b: Bloc<T>): string {
    return b.etat === 'erreur' ? b.message : '';
  }

  taux(x: KpiExecutions): string {
    return x.total ? `${Math.round((x.succes / x.total) * 100)} % de succès` : 'Aucune donnée';
  }

  charger(): void {
    if (this.d.catalogue()) {
      this.studio.catalogue({}, 1, 1).subscribe({
        next: (page) => {
          this.catalogue.set(page.kpis);
          this.avertissement.set(page.avertissement);
        },
        error: (err) => this.erreurCatalogue.set(integrationErreur(err, 'Impossible de charger le catalogue API.')),
      });
    }
    this.bloc(this.fournisseurs, this.d.fournisseurs(), () =>
      forkJoin({ tous: this.fourn.lister({}, 1, 100), valides: this.fourn.lister({ statut: 'valide' }, 1, 1) }).pipe(
        map(({ tous, valides }) => ({
          total: tous.total,
          valides: valides.total,
          operations: tous.items.reduce((s, f) => s + (f.nb_operations ?? 0), 0),
          partiel: tous.total > tous.items.length,
        })),
      ),
    );
    this.bloc(this.destinations, this.d.destinations(), () =>
      forkJoin({
        toutes: this.exec.listerDestinations({}, 1, 1),
        actives: this.exec.listerDestinations({ statut: 'active' }, 1, 1),
        suspendues: this.exec.listerDestinations({ statut: 'suspendue' }, 1, 1),
      }).pipe(map(({ toutes, actives, suspendues }) => ({ total: toutes.total, actives: actives.total, suspendues: suspendues.total }))),
    );
    const depuis = bornesPeriode('7j').depuis ?? '';
    this.bloc(this.executions, this.d.testsView(), () =>
      forkJoin({
        toutes: this.exec.executions({ depuis }, 1, 5),
        succes: this.exec.executions({ depuis, statut: 'succes' }, 1, 1),
      }).pipe(map(({ toutes, succes }) => ({ total: toutes.total, succes: succes.total, dernieres: toutes.items }))),
    );
    this.bloc(this.alertes, this.d.supervision(), () =>
      forkJoin({
        nouvelles: this.exec.alertes({ statut: 'nouvelle' }, 1, 1),
        enCours: this.exec.alertes({ statut: 'en_cours' }, 1, 1),
      }).pipe(map(({ nouvelles, enCours }) => ({ nouvelles: nouvelles.total, enCours: enCours.total }))),
    );
  }

  private bloc<T>(cible: WritableSignal<Bloc<T>>, autorise: boolean, source: () => Observable<T>): void {
    if (!autorise) {
      cible.set({ etat: 'interdit' });
      return;
    }
    cible.set({ etat: 'chargement' });
    source().subscribe({
      next: (valeur) => cible.set({ etat: 'ok', valeur }),
      error: (err) => cible.set(estAccesRefuse(err) ? { etat: 'interdit' } : { etat: 'erreur', message: messageErreur(err, 'Données indisponibles.') }),
    });
  }

  cartes(k: IntegrationCatalogueKpis) {
    return [
      { label: 'Opérations découvertes', value: k.total, icon: 'api', tone: 'blue', query: {} },
      { label: 'Documentées', value: k.documentees, icon: 'verified', tone: 'green', query: { disponibilite: 'documentee' } },
      { label: 'Restreintes', value: k.restreintes, icon: 'help', tone: 'amber', query: { disponibilite: 'restreinte' } },
      { label: 'Exclues', value: k.exclues, icon: 'block', tone: 'rose', query: { disponibilite: 'exclue' } },
      { label: 'Console (lecture seule)', value: k.console, icon: 'terminal', tone: 'teal', query: { console: 'true' } },
    ];
  }

  repartitions(k: IntegrationCatalogueKpis) {
    const lignes = (data: Record<string, number>, param: string, libelle: (c: string) => string) =>
      Object.entries(data)
        .sort((a, b) => b[1] - a[1])
        .map(([cle, valeur]) => ({ cle, valeur, libelle: libelle(cle), query: { [param]: cle } }));
    return [
      { titre: 'Par méthode', lignes: lignes(k.par_methode, 'methode', (c) => c) },
      { titre: 'Par authentification', lignes: lignes(k.par_authentification, 'authentification', authLabel) },
      { titre: 'Par statut de permission', lignes: lignes(k.par_permission_statut, 'permission_statut', permissionStatutLabel) },
      { titre: 'Par schéma de réponse', lignes: lignes(k.par_schema_reponse, 'schema', schemaStatutLabel) },
    ];
  }
}

const FILTRES_VIDES = {
  q: '',
  module: '',
  methode: '',
  authentification: '',
  permission_statut: '',
  schema: '',
  permission: '',
  disponibilite: '',
  console: '',
};

@Component({
  selector: 'bea-core-admin-integrations-catalogue',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Catalogue API</h1>
          <p>Opérations découvertes dans l'application. La présence d'une route ici ne garantit aucune autorisation d'accès.</p>
        </div>
      </header>

      <form class="bea-admin-toolbar" [formGroup]="filtres" (ngSubmit)="rechercher()">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input type="search" formControlName="q" placeholder="Identifiant, chemin, module, permission…" maxlength="120" />
        </label>
        <label class="bea-admin-field">
          <span>Module</span>
          <select formControlName="module">
            <option value="">Tous</option>
            @for (m of options().modules; track m) {
              <option [value]="m">{{ m }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Méthode</span>
          <select formControlName="methode">
            <option value="">Toutes</option>
            @for (m of options().methodes; track m) {
              <option [value]="m">{{ m }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Authentification</span>
          <select formControlName="authentification">
            <option value="">Toutes</option>
            @for (a of options().authentifications; track a) {
              <option [value]="a">{{ authLabel(a) }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Statut permission</span>
          <select formControlName="permission_statut">
            <option value="">Tous</option>
            <option value="identifiee">Permission identifiée</option>
            <option value="non_determinee">Permission non déterminée</option>
            <option value="non_verifiee">Accès non vérifié</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Réponse</span>
          <select formControlName="schema">
            <option value="">Toutes</option>
            <option value="explicite">Schéma explicite</option>
            <option value="generique">Schéma générique</option>
            <option value="absent">Schéma absent</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Permission</span>
          <input type="text" formControlName="permission" placeholder="ex. immobilisations.read" maxlength="120" />
        </label>
        <label class="bea-admin-field">
          <span>Disponibilité</span>
          <select formControlName="disponibilite">
            <option value="">Toutes</option>
            <option value="documentee">Documentée</option>
            <option value="restreinte">Restreinte</option>
            <option value="exclue">Exclue</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Console</span>
          <select formControlName="console">
            <option value="">Indifférent</option>
            <option value="true">Admissible</option>
            <option value="false">Non admissible</option>
          </select>
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="submit" class="bea-admin-btn" [disabled]="loading()">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
        </div>
      </form>

      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement du catalogue…</p>
      } @else if (erreur(); as e) {
        @if (e.accesRefuse) {
          ${ACCES_REFUSE}
        } @else {
          <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e.message }}</p></div>
          <button type="button" class="bea-admin-btn" (click)="charger()">Réessayer</button>
        }
      } @else {
        <div class="bea-admin-panel">
          <div class="bea-admin-users__list-head">
            <h2>Opérations</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          @if (items().length === 0) {
            <p class="bea-admin-panel__empty">Aucune opération ne correspond à ces critères.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Opération</th>
                    <th>Module</th>
                    <th>Authentification</th>
                    <th>Permissions</th>
                    <th>Réponse</th>
                    <th>Disponibilité</th>
                    <th>Console</th>
                  </tr>
                </thead>
                <tbody>
                  @for (op of items(); track op.operation_id) {
                    <tr>
                      <td>
                        <span class="bea-integ-method" [attr.data-m]="op.methode">{{ op.methode }}</span>
                        <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/catalogue', op.operation_id]">
                          <span class="bea-integ-path">{{ op.chemin }}</span>
                        </a>
                        <div class="bea-integ-muted">{{ op.operation_id }}</div>
                      </td>
                      <td>{{ op.module }}</td>
                      <td>{{ authLabel(op.authentification) }}</td>
                      <td>
                        @if (op.exigence_permissions) {
                          <div><code>{{ op.exigence_permissions }}</code></div>
                        }
                        <div class="bea-integ-muted">{{ permissionStatutLabel(op.permission_statut) }}</div>
                      </td>
                      <td>{{ schemaStatutLabel(op.schema_reponse_statut) }}</td>
                      <td>
                        <span class="bea-badge" [class]="'bea-badge ' + disponibiliteTone(op.disponibilite)" [title]="op.motifs.join(' ')">
                          {{ disponibiliteLabel(op.disponibilite) }}
                        </span>
                      </td>
                      <td>
                        @if (op.console) {
                          <a class="bea-admin-icon-btn" [routerLink]="'/admin/integrations/console'" [queryParams]="{ operation: op.operation_id }" title="Ouvrir dans la console" aria-label="Ouvrir dans la console">
                            <bea-admin-icon name="terminal" />
                          </a>
                        } @else {
                          <span class="bea-integ-muted">—</span>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="bea-admin-pager">
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} opération(s)</span>
              <div>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="aller(page() - 1)">Précédent</button>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages()" (click)="aller(page() + 1)">Suivant</button>
              </div>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class CoreAdminIntegrationsCatalogueComponent implements OnInit {
  private readonly studio = inject(CoreAdminIntegrationsService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly loading = signal(true);
  readonly erreur = signal<IntegrationErreur | null>(null);
  readonly items = signal<IntegrationOperationResume[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 25;
  readonly options = signal<IntegrationCatalogueFiltres>({ modules: [], methodes: [], authentifications: [] });
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  readonly filtres = this.fb.nonNullable.group({ ...FILTRES_VIDES });

  readonly authLabel = authLabel;
  readonly permissionStatutLabel = permissionStatutLabel;
  readonly schemaStatutLabel = schemaStatutLabel;
  readonly disponibiliteLabel = disponibiliteLabel;
  readonly disponibiliteTone = disponibiliteTone;

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    const initial: Partial<typeof FILTRES_VIDES> = {};
    for (const cle of Object.keys(FILTRES_VIDES) as (keyof typeof FILTRES_VIDES)[]) {
      const v = qp.get(cle);
      if (v) initial[cle] = v;
    }
    this.filtres.patchValue(initial);
    this.charger();
  }

  rechercher(): void {
    this.page.set(1);
    this.synchroniserUrl();
    this.charger();
  }

  reinitialiser(): void {
    this.filtres.reset({ ...FILTRES_VIDES });
    this.rechercher();
  }

  aller(page: number): void {
    this.page.set(page);
    this.charger();
  }

  valeursFiltres(): IntegrationCatalogueFiltreValeurs {
    const v = this.filtres.getRawValue();
    return {
      q: v.q,
      module: v.module,
      methode: v.methode,
      authentification: v.authentification,
      permission_statut: v.permission_statut,
      schema: v.schema,
      permission: v.permission,
      disponibilite: v.disponibilite,
      console: v.console === 'true' ? true : v.console === 'false' ? false : null,
    };
  }

  charger(): void {
    this.loading.set(true);
    this.erreur.set(null);
    this.studio.catalogue(this.valeursFiltres(), this.page(), this.size).subscribe({
      next: (data) => {
        this.items.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.page.set(data.page ?? 1);
        this.options.set(data.filtres);
        this.loading.set(false);
      },
      error: (err) => {
        this.erreur.set(integrationErreur(err, 'Impossible de charger le catalogue API.'));
        this.loading.set(false);
      },
    });
  }

  private synchroniserUrl(): void {
    const v = this.filtres.getRawValue();
    const queryParams: Record<string, string> = {};
    for (const [cle, valeur] of Object.entries(v)) {
      if (valeur.trim()) queryParams[cle] = valeur.trim();
    }
    void this.router.navigate([], { relativeTo: this.route, queryParams, replaceUrl: true });
  }
}
