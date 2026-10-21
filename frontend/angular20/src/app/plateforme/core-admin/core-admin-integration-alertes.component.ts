import { DatePipe, JsonPipe, KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CoreAdminIntegrationAccesComponent } from './core-admin-integration-acces.component';
import { estAccesRefuse, messageErreur } from './core-admin-integration-clients.models';
import {
  AlerteHistorique,
  AlerteItem,
  AlerteStatut,
  alerteStatutLabel,
  alerteStatutTone,
  alerteTypeLabel,
  bornesPeriode,
  integrationStudioPermissions,
  niveauLabel,
  niveauTone,
  PeriodeCode,
  PERIODES,
  PERMISSIONS_STUDIO,
  sansVides,
  STATUTS_ALERTE,
  TYPES_ALERTE,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionService } from './core-admin-integration-execution.service';
import { FournisseurResume } from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

const FILTRES = { q: '', statut: '', type: '', niveau: '', fournisseur_id: '', periode: 'tout' as PeriodeCode, depuis: '', jusqua: '' };
type Filtres = typeof FILTRES;

const ACTIONS: Record<AlerteStatut, { libelle: string; message: string; tone: 'primary' | 'danger' }> = {
  en_cours: { libelle: 'Prendre en charge', message: 'Marquer cette alerte comme en cours de traitement ?', tone: 'primary' },
  resolue: { libelle: 'Résoudre', message: 'Marquer cette alerte comme résolue ? Une nouvelle alerte sera ouverte si la condition se reproduit.', tone: 'primary' },
  ignoree: { libelle: 'Ignorer', message: 'Ignorer cette alerte ? Elle sortira des alertes actives ; l’action est journalisée.', tone: 'danger' },
  nouvelle: {
    libelle: 'Rouvrir',
    message: 'Rouvrir cette alerte ? Elle redevient active. Refusé si une alerte identique est déjà ouverte.',
    tone: 'primary',
  },
};

/** Repli si le serveur ne renvoie pas `transitions` (le serveur reste seul juge). */
const TRANSITIONS_PAR_DEFAUT: Record<AlerteStatut, AlerteStatut[]> = {
  nouvelle: ['en_cours', 'resolue', 'ignoree'],
  en_cours: ['resolue', 'ignoree'],
  resolue: ['nouvelle'],
  ignoree: ['nouvelle'],
};

const KPI: { statut: AlerteStatut; libelle: string; tone: string }[] = [
  { statut: 'nouvelle', libelle: 'Nouvelles', tone: 'danger' },
  { statut: 'en_cours', libelle: 'En cours', tone: 'warn' },
  { statut: 'resolue', libelle: 'Résolues', tone: 'ok' },
  { statut: 'ignoree', libelle: 'Ignorées', tone: 'muted' },
];

@Component({
  selector: 'bea-core-admin-integration-alertes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DatePipe, JsonPipe, KeyValuePipe, CoreAdminIntegrationAccesComponent, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/integrations">Studio d'intégration API</a></p>
          <h1>Alertes des intégrations</h1>
          <p>
            Alertes ouvertes par des règles fixes appliquées aux tests enregistrés. Une alerte ne déclenche jamais d’appel sortant
            et une même condition n’ouvre qu’une alerte active à la fois.
          </p>
        </div>
        @if (d.supervision()) {
          <div class="bea-integ-head-actions">
            <button type="button" class="bea-admin-btn bea-admin-btn--refresh" [disabled]="chargement()" (click)="charger()">
              <bea-admin-icon name="refresh" /> Actualiser
            </button>
          </div>
        }
      </header>

      @if (!d.supervision()) {
        <bea-integ-acces-refuse section="Les alertes des intégrations" [permissions]="[P.supervision]" />
      } @else {
        @if (compteurs(); as c) {
          <div class="bea-integ-kpi-filtres" role="group" aria-label="Compteurs par statut (cliquer pour filtrer)">
            <div class="bea-integ-kpi-filtre" data-tone="danger" style="cursor: default">
              <span>Actives</span>
              <strong>{{ (c['nouvelle'] ?? 0) + (c['en_cours'] ?? 0) }}</strong>
            </div>
            @for (k of kpis; track k.statut) {
              <button type="button" class="bea-integ-kpi-filtre" [attr.data-tone]="k.tone"
                      [attr.aria-pressed]="filtres.controls.statut.value === k.statut" (click)="filtrerStatut(k.statut)">
                <span>{{ k.libelle }}</span>
                <strong>{{ c[k.statut] ?? 0 }}</strong>
              </button>
            }
          </div>
        }

        <form class="bea-admin-panel bea-integ-filtres" [formGroup]="filtres" (ngSubmit)="rechercher()" role="search" aria-label="Filtres des alertes">
          <label class="bea-admin-field">
            <span>Recherche</span>
            <input type="search" formControlName="q" maxlength="120" placeholder="Message de l’alerte…" />
          </label>
          <label class="bea-admin-field">
            <span>Niveau</span>
            <select formControlName="niveau">
              <option value="">Tous</option>
              <option value="elevee">Élevé</option>
              <option value="moyenne">Moyen</option>
              <option value="info">Information</option>
            </select>
          </label>
          <label class="bea-admin-field">
            <span>Type</span>
            <select formControlName="type">
              <option value="">Tous</option>
              @for (t of types; track t) { <option [value]="t">{{ typeLabel(t) }}</option> }
            </select>
          </label>
          <label class="bea-admin-field">
            <span>Statut</span>
            <select formControlName="statut">
              <option value="">Tous</option>
              @for (s of statuts; track s) { <option [value]="s">{{ statutLabel(s) }}</option> }
            </select>
          </label>
          @if (d.fournisseurs()) {
            <label class="bea-admin-field">
              <span>Fournisseur</span>
              <select formControlName="fournisseur_id">
                <option value="">Tous</option>
                @for (f of fournisseurs(); track f.id) { <option [value]="f.id">{{ f.nom }}</option> }
              </select>
            </label>
          }
          <label class="bea-admin-field">
            <span>Dernière occurrence</span>
            <select formControlName="periode">
              @for (p of periodes; track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
            </select>
          </label>
          @if (filtres.controls.periode.value === 'perso') {
            <label class="bea-admin-field"><span>Depuis</span><input type="datetime-local" formControlName="depuis" /></label>
            <label class="bea-admin-field"><span>Jusqu’à</span><input type="datetime-local" formControlName="jusqua" /></label>
          }
          <div class="bea-admin-toolbar__actions">
            <button type="submit" class="bea-admin-btn" [disabled]="chargement()">Filtrer</button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
          </div>
        </form>

        @if (!d.supervisionManage()) {
          <div class="bea-integ-notice bea-integ-notice--info" role="note">
            <p>Consultation seule : traiter une alerte exige <code>{{ permManage }}</code>.</p>
          </div>
        }

        @if (chargement() && items().length === 0) {
          ${squelette('Chargement des alertes…')}
        } @else if (accesRefuse()) {
          <bea-integ-acces-refuse section="Les alertes des intégrations" [permissions]="[P.supervision]" />
        } @else if (erreur(); as e) {
          <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
          <button type="button" class="bea-admin-btn" (click)="charger()">Réessayer</button>
        } @else {
          <section class="bea-admin-panel" [attr.aria-busy]="chargement()">
            <div class="bea-integ-list-head">
              <h2>Alertes</h2>
              <span class="bea-integ-count" aria-live="polite">{{ total() }} résultat(s)</span>
            </div>
            @if (items().length === 0) {
              <div class="bea-integ-empty">
                <bea-admin-icon name="notifications_off" />
                <strong>Aucune alerte ne correspond à ces critères.</strong>
                <p>Les alertes ne sont jamais supprimées : élargissez la période ou le statut pour retrouver l’historique.</p>
              </div>
            } @else {
              <div class="bea-admin-table-wrap">
                <table class="bea-admin-table bea-integ-cards">
                  <thead>
                    <tr>
                      <th scope="col">Niveau</th><th scope="col">Type</th><th scope="col">Message</th><th scope="col">Fournisseur</th>
                      <th scope="col">Statut</th><th scope="col">Occurrences</th><th scope="col">Dernière</th>
                      <th scope="col"><span class="bea-integ-muted">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (a of items(); track a.id) {
                      <tr>
                        <td data-label="Niveau"><span [class]="niveauTone(a.niveau)">{{ niveauLabel(a.niveau) }}</span></td>
                        <td data-label="Type">{{ typeLabel(a.type) }}</td>
                        <td data-label="Message">{{ a.message }}</td>
                        <td data-label="Fournisseur">{{ a.fournisseur_nom ?? '—' }}</td>
                        <td data-label="Statut"><span [class]="statutTone(a.statut)">{{ statutLabel(a.statut) }}</span></td>
                        <td data-label="Occurrences">{{ a.occurences }}</td>
                        <td data-label="Dernière">{{ a.derniere_le | date: 'dd/MM/yyyy HH:mm' }}</td>
                        <td data-label="">
                          <div class="bea-integ-actions-ligne">
                            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [attr.aria-expanded]="ouverte() === a.id"
                                    [attr.aria-controls]="'alerte-' + a.id" (click)="basculer(a.id)">Détail</button>
                            @if (d.supervisionManage()) {
                              @for (t of transitions(a); track t) {
                                <button type="button" class="bea-admin-btn" [class.bea-admin-btn--danger]="actions[t].tone === 'danger'"
                                        [class.bea-admin-btn--ghost]="actions[t].tone !== 'danger'"
                                        [disabled]="enCours() !== null" (click)="traiter(a, t)">{{ actions[t].libelle }}</button>
                              }
                            }
                          </div>
                        </td>
                      </tr>
                      @if (ouverte() === a.id) {
                        <tr [id]="'alerte-' + a.id">
                          <td colspan="8">
                            <div class="bea-integ-detail">
                              <section>
                                <h3>Règle et contexte</h3>
                                <dl class="bea-integ-recap">
                                  <dt>Règle</dt><dd>{{ a.regle ?? '—' }}</dd>
                                  <dt>Première occurrence</dt><dd>{{ a.created_at | date: 'dd/MM/yyyy HH:mm' }}</dd>
                                  @if (a.resolue_le) {
                                    <dt>Clôturée le</dt><dd>{{ a.resolue_le | date: 'dd/MM/yyyy HH:mm' }} — {{ a.resolue_par?.nom ?? '—' }}</dd>
                                  }
                                  @if (a.fournisseur_id) {
                                    <dt>Fournisseur</dt>
                                    <dd>
                                      @if (d.fournisseurs()) {
                                        <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/fournisseurs', a.fournisseur_id]">{{ a.fournisseur_nom ?? 'Ouvrir le fournisseur' }}</a>
                                      } @else { {{ a.fournisseur_nom ?? a.fournisseur_id }} }
                                    </dd>
                                  }
                                  @if (a.destination_id) {
                                    <dt>Destination</dt>
                                    <dd>
                                      @if (d.destinations()) {
                                        <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/destinations', a.destination_id]">{{ a.destination_nom ?? 'Ouvrir la destination' }}</a>
                                      } @else { {{ a.destination_nom ?? a.destination_id }} }
                                    </dd>
                                  }
                                  @if (a.operation_nom) { <dt>Opération</dt><dd class="bea-integ-path">{{ a.operation_nom }}</dd> }
                                  @if (d.testsView() && a.destination_id) {
                                    <dt>Tests liés</dt>
                                    <dd><a class="bea-admin-table__link" routerLink="/admin/integrations/executions" [queryParams]="{ destination_id: a.destination_id, periode: 'tout' }">Historique de la destination</a></dd>
                                  }
                                </dl>
                              </section>
                              @if ((a.details | keyvalue).length) {
                                <section>
                                  <h3>Mesures</h3>
                                  <dl class="bea-integ-recap">
                                    @for (x of a.details | keyvalue; track x.key) { <dt>{{ x.key }}</dt><dd><code>{{ x.value | json }}</code></dd> }
                                  </dl>
                                </section>
                              }
                              <section>
                                <h3>Historique du traitement</h3>
                                @if (historique() === null) {
                                  <p class="bea-integ-muted" role="status">Chargement…</p>
                                } @else if (historique()!.length === 0) {
                                  <p class="bea-integ-muted">Aucune action enregistrée : l’alerte n’a pas encore été traitée.</p>
                                } @else {
                                  <ol class="bea-integ-timeline">
                                    @for (h of historique(); track h.id) {
                                      <li>
                                        {{ h.created_at | date: 'dd/MM/yyyy HH:mm' }} — {{ h.acteur?.nom ?? '—' }} :
                                        {{ h.avant ?? '—' }} → <strong>{{ h.apres ?? '—' }}</strong>
                                      </li>
                                    }
                                  </ol>
                                }
                              </section>
                            </div>
                          </td>
                        </tr>
                      }
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
      }
    </section>
  `,
})
export class CoreAdminIntegrationAlertesComponent implements OnInit {
  private readonly service = inject(CoreAdminIntegrationExecutionService);
  private readonly fourn = inject(CoreAdminIntegrationFournisseursService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly d = integrationStudioPermissions();
  readonly P = PERMISSIONS_STUDIO;
  readonly permManage = 'core.admin.integrations.supervision.manage';
  readonly periodes = PERIODES;
  readonly types = TYPES_ALERTE;
  readonly statuts = STATUTS_ALERTE;
  readonly kpis = KPI;
  readonly actions = ACTIONS;
  readonly typeLabel = alerteTypeLabel;
  readonly statutLabel = alerteStatutLabel;
  readonly statutTone = alerteStatutTone;
  readonly niveauLabel = niveauLabel;
  readonly niveauTone = niveauTone;
  readonly filtres = this.fb.nonNullable.group({ ...FILTRES });
  readonly items = signal<AlerteItem[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 25;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly compteurs = signal<Partial<Record<AlerteStatut, number>> | null>(null);
  readonly fournisseurs = signal<FournisseurResume[]>([]);
  readonly chargement = signal(true);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly ouverte = signal<string | null>(null);
  readonly historique = signal<AlerteHistorique[] | null>(null);
  readonly enCours = signal<string | null>(null);

  ngOnInit(): void {
    if (!this.d.supervision()) return;
    const qp = this.route.snapshot.queryParamMap;
    const initial: Partial<Filtres> = {};
    for (const cle of Object.keys(FILTRES) as (keyof Filtres)[]) {
      const v = qp.get(cle);
      if (v) (initial as Record<string, string>)[cle] = v;
    }
    this.filtres.patchValue(initial);
    this.page.set(Math.max(1, Number(qp.get('page')) || 1));
    if (this.d.fournisseurs()) {
      this.fourn.lister({ inclure_archives: true }, 1, 100).subscribe({ next: (p) => this.fournisseurs.set(p.items), error: () => this.fournisseurs.set([]) });
    }
    this.charger();
  }

  params(): Record<string, string> {
    const v = this.filtres.getRawValue();
    return sansVides({
      ...bornesPeriode(v.periode, v.depuis, v.jusqua),
      statut: v.statut, type: v.type, niveau: v.niveau, fournisseur_id: v.fournisseur_id, q: v.q,
    });
  }

  transitions(a: AlerteItem): AlerteStatut[] {
    return a.transitions ?? TRANSITIONS_PAR_DEFAUT[a.statut] ?? [];
  }

  filtrerStatut(statut: AlerteStatut): void {
    this.filtres.patchValue({ statut: this.filtres.controls.statut.value === statut ? '' : statut });
    this.rechercher();
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

  basculer(id: string): void {
    if (this.ouverte() === id) {
      this.ouverte.set(null);
      return;
    }
    this.ouverte.set(id);
    this.historique.set(null);
    this.service.historiqueAlerte(id).subscribe({
      next: (h) => {
        if (this.ouverte() === id) this.historique.set(h.items ?? []);
      },
      error: () => {
        if (this.ouverte() === id) this.historique.set([]);
      },
    });
  }

  charger(): void {
    this.chargement.set(true);
    this.erreur.set(null);
    this.accesRefuse.set(false);
    this.synchroniserUrl();
    this.service.alertes(this.params(), this.page(), this.size).subscribe({
      next: (r) => {
        this.items.set(r.items ?? []);
        this.total.set(r.total ?? 0);
        this.compteurs.set(r.compteurs ?? null);
        this.chargement.set(false);
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Alertes indisponibles.'));
        this.chargement.set(false);
      },
    });
  }

  async traiter(a: AlerteItem, statut: AlerteStatut): Promise<void> {
    if (this.enCours() !== null || !this.d.supervisionManage()) return;
    const action = ACTIONS[statut];
    const ok = await this.dialogs.confirm({
      title: action.libelle,
      message: `${action.message}\n« ${a.message} »`,
      tone: action.tone,
      confirmLabel: action.libelle,
    });
    if (!ok) return;
    this.enCours.set(a.id);
    this.service.changerAlerte(a.id, statut).subscribe({
      next: () => {
        this.enCours.set(null);
        void this.dialogs.success(`Alerte : ${alerteStatutLabel(statut).toLowerCase()}.`);
        if (this.ouverte() === a.id) this.ouverte.set(null);
        this.charger();
      },
      error: (err) => {
        this.enCours.set(null);
        void this.dialogs.error(messageErreur(err, 'Mise à jour refusée.'));
      },
    });
  }

  private synchroniserUrl(): void {
    const v = this.filtres.getRawValue();
    const queryParams = sansVides({ ...v, periode: v.periode === 'tout' ? '' : v.periode });
    if (v.periode !== 'perso') {
      delete queryParams['depuis'];
      delete queryParams['jusqua'];
    }
    if (this.page() > 1) queryParams['page'] = String(this.page());
    void this.router.navigate([], { relativeTo: this.route, queryParams, replaceUrl: true });
  }
}
