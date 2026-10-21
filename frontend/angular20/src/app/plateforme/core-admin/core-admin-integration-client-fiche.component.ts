import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  clientStatutLabel,
  clientStatutTone,
  clientTransitionLabel,
  estAccesRefuse,
  GRANT_ACTIONS,
  GrantAction,
  grantStatutLabel,
  grantStatutTone,
  IntegrationClientFiche,
  IntegrationClientStatut,
  integrationClientsPermissions,
  IntegrationDocumentation,
  IntegrationGrant,
  IntegrationGrantEvenement,
  IntegrationGrantStatut,
  IntegrationOperationAdmissible,
  messageErreur,
  sansSecret,
  STATUTS_OUVERTS,
  telechargerTexte,
  texteOuNull,
} from './core-admin-integration-clients.models';
import { CoreAdminIntegrationClientsService } from './core-admin-integration-clients.service';
import { ACCES_REFUSE_CLIENTS } from './core-admin-integration-clients.component';
import { IntegrationSuppressionService, squelette } from './core-admin-integration-ui';
import { INTEGRATIONS_STYLES } from './core-admin-integrations.styles';

export type OngletClient = 'fiche' | 'operations' | 'autorisations' | 'historique' | 'documentation';

const ONGLETS: readonly OngletClient[] = ['fiche', 'operations', 'autorisations', 'historique', 'documentation'];

@Component({
  selector: 'bea-core-admin-integration-client-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DatePipe, CoreAdminIconComponent],
  styles: [INTEGRATIONS_STYLES],
  template: `
    <section class="bea-admin-dash">
      @if (chargement()) {
        ${squelette('Chargement de l’application…')}
      } @else if (accesRefuse()) {
        ${ACCES_REFUSE_CLIENTS}
      } @else if (erreur(); as e) {
        <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/integrations/clients">Retour à la liste</a>
      } @else if (fiche(); as f) {
        <header class="bea-admin-dash__head bea-admin-users__head">
          <div>
            <p class="bea-admin-kicker"><a routerLink="/admin/integrations/clients">Applications clientes</a></p>
            <h1>{{ f.nom }}</h1>
            <p><code>{{ f.code }}</code> — identifiant interne de la fiche, pas un identifiant d'authentification.</p>
          </div>
          <div class="bea-admin-users__head-actions">
            <span class="bea-badge">{{ f.environnement }}</span>
            <span [class]="statutTone(f.statut)">{{ statutLabel(f.statut) }}</span>
          </div>
        </header>

        <div class="bea-integ-notice" role="note">
          <bea-admin-icon name="info" />
          <p>{{ f.avertissement }}</p>
        </div>

        <div class="bea-integ-tabs" role="tablist" aria-label="Sections de l'application">
          @for (o of ongletsVisibles(); track o.id) {
            <button type="button" role="tab" class="bea-admin-btn bea-admin-btn--ghost" [attr.aria-selected]="onglet() === o.id" (click)="choisir(o.id)">
              {{ o.libelle }}
            </button>
          }
        </div>

        @switch (onglet()) {
          @case ('fiche') {
            <section class="bea-admin-panel">
              <h2>Fiche</h2>
              <dl class="bea-admin-dl">
                <div><dt>Identifiant interne</dt><dd><code>{{ f.code }}</code></dd></div>
                <div><dt>Environnement</dt><dd>{{ f.environnement }}</dd></div>
                <div><dt>Statut</dt><dd>{{ statutLabel(f.statut) }}</dd></div>
                <div>
                  <dt>Service responsable</dt>
                  <dd>{{ f.entite?.libelle ?? '—' }} @if (f.entite && !f.entite.actif) { <span class="bea-badge bea-badge--inactif">désactivé</span> }</dd>
                </div>
                <div><dt>Contact technique</dt><dd>{{ f.contact_technique ?? '—' }}</dd></div>
                <div><dt>Description</dt><dd>{{ f.description ?? '—' }}</dd></div>
                <div><dt>Finalité</dt><dd>{{ f.finalite ?? '—' }}</dd></div>
                <div><dt>Notes d'administration</dt><dd>{{ f.notes ?? '—' }}</dd></div>
                <div><dt>Opérations demandées</dt><dd>{{ f.nb_operations }} (dont {{ f.nb_approuvees }} approuvée(s))</dd></div>
                <div><dt>Créée</dt><dd>{{ f.created_at | date: 'dd/MM/yyyy HH:mm' }} — {{ f.cree_par?.nom ?? '—' }}</dd></div>
                <div><dt>Modifiée</dt><dd>{{ f.updated_at | date: 'dd/MM/yyyy HH:mm' }} — {{ f.modifie_par?.nom ?? '—' }}</dd></div>
                @if (f.statut === 'archivee') {
                  <div><dt>Archivée</dt><dd>{{ f.archived_at | date: 'dd/MM/yyyy HH:mm' }} — {{ f.archive_par?.nom ?? '—' }} : {{ f.motif_archivage }}</dd></div>
                }
              </dl>
            </section>
            @if (droits.clientsManage() && f.statut !== 'archivee') {
              <div class="bea-admin-actions">
                <a class="bea-admin-btn" [routerLink]="['/admin/integrations/clients', f.id, 'modifier']">Modifier</a>
                @for (t of f.transitions; track t) {
                  <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="action()" (click)="changerStatut(t)">
                    {{ transitionLabel(t) }}
                  </button>
                }
                <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="action()" (click)="archiver()">Archiver</button>
                <button type="button" class="bea-admin-btn bea-integ-btn-danger-ghost" [disabled]="action()" (click)="supprimer()"
                        title="Possible seulement pour une fiche brouillon sans demande de droits">
                  <bea-admin-icon name="delete" /> Supprimer
                </button>
              </div>
            }
          }

          @case ('operations') {
            <section class="bea-admin-panel">
              <h2>Sélection d'opérations du catalogue</h2>
              <p class="bea-admin-panel__hint">
                Seules les opérations documentées sans réserve (authentification et permission identifiées, schéma explicite,
                module actif, ni suppression, ni export, ni opération d'administration) peuvent être demandées.
                Une sélection est une demande : elle n'ouvre aucun accès.
              </p>
              @if (f.statut === 'archivee' || f.statut === 'suspendue') {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>Application au statut « {{ statutLabel(f.statut) }} » : aucune nouvelle demande possible.</p></div>
              }
              <form class="bea-admin-toolbar" [formGroup]="recherche" (ngSubmit)="chercherOperations(1)">
                <label class="bea-admin-field bea-admin-toolbar__search">
                  <span>Recherche</span>
                  <input type="search" formControlName="q" maxlength="120" placeholder="Nom, chemin, module, permission…" />
                </label>
                <label class="bea-admin-field">
                  <span>Module</span>
                  <input type="text" formControlName="module" maxlength="80" />
                </label>
                <label class="bea-admin-field">
                  <span>Méthode</span>
                  <select formControlName="methode">
                    <option value="">Toutes</option>
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                    <option value="PUT">PUT</option>
                    <option value="PATCH">PATCH</option>
                  </select>
                </label>
                <label class="bea-admin-field">
                  <span>Afficher</span>
                  <span><input type="checkbox" formControlName="tout" /> Aussi les non admissibles</span>
                </label>
                <div class="bea-admin-toolbar__actions">
                  <button type="submit" class="bea-admin-btn" [disabled]="opsChargement()">Rechercher</button>
                </div>
              </form>

              @if (opsChargement()) {
                <p class="bea-admin-dash__loading">Recherche des opérations…</p>
              } @else if (opsErreur(); as e) {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
              } @else if (operations().length === 0) {
                <p class="bea-admin-panel__empty">Aucune opération ne correspond.</p>
              } @else {
                <div class="bea-admin-table-wrap">
                  <table class="bea-admin-table">
                    <thead>
                      <tr><th></th><th>Opération</th><th>Module</th><th>Permission(s)</th><th>État</th></tr>
                    </thead>
                    <tbody>
                      @for (op of operations(); track op.operation_id) {
                        <tr>
                          <td>
                            <input
                              type="checkbox"
                              [attr.aria-label]="'Sélectionner ' + op.operation_id"
                              [disabled]="!selectionnable(op)"
                              [checked]="selection().has(op.operation_id)"
                              (change)="basculer(op)"
                            />
                          </td>
                          <td>
                            <span class="bea-integ-method" [attr.data-m]="op.methode">{{ op.methode }}</span>
                            <a class="bea-admin-table__link" [routerLink]="['/admin/integrations/catalogue', op.operation_id]">
                              <span class="bea-integ-path">{{ op.chemin }}</span>
                            </a>
                            <div class="bea-integ-muted">{{ op.resume ?? op.operation_id }}</div>
                          </td>
                          <td>{{ op.module }}</td>
                          <td><code>{{ op.exigence_permissions ?? (op.permissions.join(', ') || '—') }}</code></td>
                          <td>
                            @if (op.deja_demandee) {
                              <span [class]="grantTone(op.deja_demandee)">{{ grantLabel(op.deja_demandee) }}</span>
                            } @else if (op.admissible) {
                              <span class="bea-badge bea-badge--actif">Admissible</span>
                            } @else {
                              <span class="bea-badge bea-badge--inactif" [title]="op.motif_inadmissible ?? ''">Indisponible</span>
                              <div class="bea-integ-muted">{{ op.motif_inadmissible }}</div>
                            }
                          </td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
                <div class="bea-admin-pager">
                  <span>Page {{ opsPage() }} / {{ opsPages() }} — {{ opsTotal() }} opération(s)</span>
                  <div>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="opsPage() <= 1" (click)="chercherOperations(opsPage() - 1)">Précédent</button>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="opsPage() >= opsPages()" (click)="chercherOperations(opsPage() + 1)">Suivant</button>
                  </div>
                </div>
              }
            </section>

            <section class="bea-admin-panel">
              <h2>Accès envisagés ({{ selection().size }})</h2>
              @if (selection().size === 0) {
                <p class="bea-admin-panel__empty">Aucune opération sélectionnée.</p>
              } @else {
                <ul>
                  @for (op of selectionListe(); track op.operation_id) {
                    <li>
                      <span class="bea-integ-method" [attr.data-m]="op.methode">{{ op.methode }}</span>
                      <span class="bea-integ-path">{{ op.chemin }}</span>
                      — <code>{{ op.exigence_permissions ?? op.permissions.join(', ') }}</code>
                      <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="basculer(op)">Retirer</button>
                    </li>
                  }
                </ul>
                <p class="bea-admin-note">
                  Ces opérations seront enregistrées comme « demandées ». Elles devront être soumises puis approuvées
                  explicitement ; aucune permission utilisateur ni aucun rôle n'est modifié.
                </p>
                <label class="bea-admin-field bea-admin-toolbar__search">
                  <span>Justification</span>
                  <textarea [formControl]="justification" rows="2" maxlength="1000"></textarea>
                  @if (justification.errors?.['secret']) { <span class="bea-admin-note" role="alert">Ne saisissez aucun secret.</span> }
                </label>
                <div class="bea-admin-form__actions">
                  <button type="button" class="bea-admin-btn" [disabled]="action() || justification.invalid" (click)="demander()">
                    Demander ces opérations
                  </button>
                  <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="viderSelection()">Vider la sélection</button>
                </div>
              }
            </section>
          }

          @case ('autorisations') {
            <section class="bea-admin-panel">
              <h2>Autorisations demandées</h2>
              @if (grantsAvertissement()) {
                <p class="bea-admin-panel__hint">{{ grantsAvertissement() }}</p>
              }
              @if (grantsChargement()) {
                <p class="bea-admin-dash__loading">Chargement des autorisations…</p>
              } @else if (grantsErreur(); as e) {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
                <button type="button" class="bea-admin-btn" (click)="chargerGrants()">Réessayer</button>
              } @else if (grants().length === 0) {
                <p class="bea-admin-panel__empty">Aucune opération demandée pour cette application.</p>
              } @else {
                <p class="bea-integ-muted">
                  @for (c of compteurs(); track c.statut) { {{ grantLabel(c.statut) }} : {{ c.nombre }} &nbsp; }
                </p>
                <div class="bea-admin-table-wrap">
                  <table class="bea-admin-table">
                    <thead>
                      <tr><th>Opération</th><th>Permission(s)</th><th>Statut</th><th>Demande</th><th>Décision</th><th></th></tr>
                    </thead>
                    <tbody>
                      @for (g of grants(); track g.id) {
                        <tr>
                          <td>
                            <span class="bea-integ-method" [attr.data-m]="g.methode">{{ g.methode }}</span>
                            <span class="bea-integ-path">{{ g.chemin }}</span>
                            <div class="bea-integ-muted">{{ g.operation_id }}</div>
                            @if (!g.admissible && isOuvert(g.statut)) {
                              <div class="bea-admin-note" role="note">Opération indisponible : {{ g.motif_inadmissible }}</div>
                            }
                          </td>
                          <td><code>{{ g.exigence_permissions ?? (g.permissions.join(', ') || '—') }}</code></td>
                          <td><span [class]="grantTone(g.statut)">{{ grantLabel(g.statut) }}</span></td>
                          <td>
                            {{ g.demande_par?.nom ?? '—' }}
                            @if (g.justification) { <div class="bea-integ-muted">{{ g.justification }}</div> }
                          </td>
                          <td>
                            @if (g.decide_par) {
                              {{ g.decide_par.nom }} — {{ g.decide_le | date: 'dd/MM/yyyy HH:mm' }}
                            } @else { — }
                            @if (g.motif) { <div class="bea-integ-muted">Motif : {{ g.motif }}</div> }
                          </td>
                          <td>
                            @if (f.statut !== 'archivee') {
                              @for (a of actionsPour(g); track a.cible) {
                                <button type="button" class="bea-admin-btn" [class.bea-admin-btn--danger]="a.tone === 'danger'" [class.bea-admin-btn--ghost]="a.tone !== 'danger'" [disabled]="action()" (click)="decider(g, a)">
                                  {{ a.libelle }}
                                </button>
                              }
                            }
                          </td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              }
            </section>
          }

          @case ('historique') {
            <section class="bea-admin-panel">
              <h2>Historique des décisions</h2>
              @if (histChargement()) {
                <p class="bea-admin-dash__loading">Chargement de l'historique…</p>
              } @else if (histErreur(); as e) {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
              } @else if (historique().length === 0) {
                <p class="bea-admin-panel__empty">Aucune décision enregistrée.</p>
              } @else {
                <div class="bea-admin-table-wrap">
                  <table class="bea-admin-table">
                    <thead><tr><th>Date</th><th>Opération</th><th>Ancien statut</th><th>Nouveau statut</th><th>Par</th><th>Motif</th></tr></thead>
                    <tbody>
                      @for (e of historique(); track e.id) {
                        <tr>
                          <td>{{ e.created_at | date: 'dd/MM/yyyy HH:mm:ss' }}</td>
                          <td><code>{{ e.operation_id }}</code></td>
                          <td>{{ grantLabel(e.ancien_statut) }}</td>
                          <td><span [class]="grantTone(e.nouveau_statut)">{{ grantLabel(e.nouveau_statut) }}</span></td>
                          <td>{{ e.acteur?.nom ?? '—' }}</td>
                          <td>{{ e.motif ?? '—' }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
                <div class="bea-admin-pager">
                  <span>Page {{ histPage() }} / {{ histPages() }} — {{ histTotal() }} évènement(s)</span>
                  <div>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="histPage() <= 1" (click)="chargerHistorique(histPage() - 1)">Précédent</button>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="histPage() >= histPages()" (click)="chargerHistorique(histPage() + 1)">Suivant</button>
                  </div>
                </div>
              }
            </section>
          }

          @case ('documentation') {
            <section class="bea-admin-panel">
              <h2>Documentation de l'application</h2>
              <p class="bea-admin-panel__hint">
                Documentation des opérations approuvées, générée à la demande. Aucun jeton, aucune clé ni aucun secret n'y figure.
              </p>
              <div class="bea-admin-form__actions">
                <button type="button" class="bea-admin-btn" [disabled]="docChargement()" (click)="genererDoc()">
                  {{ doc() ? 'Régénérer' : 'Générer la documentation' }}
                </button>
                @if (doc(); as d) {
                  <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="telecharger(d)">Télécharger (Markdown)</button>
                }
              </div>
              @if (docChargement()) {
                <p class="bea-admin-dash__loading">Génération…</p>
              } @else if (docErreur(); as e) {
                <div class="bea-integ-notice bea-integ-notice--danger" role="alert"><p>{{ e }}</p></div>
              } @else if (doc(); as d) {
                <div class="bea-integ-notice" role="note">
                  <bea-admin-icon name="warning" />
                  <ul>
                    @for (a of d.avertissements; track a) { <li>{{ a }}</li> }
                  </ul>
                </div>
                <p class="bea-integ-muted">
                  {{ d.operations.length }} opération(s) approuvée(s), {{ d.en_attente }} demande(s) en cours — générée le {{ d.genere_le | date: 'dd/MM/yyyy HH:mm' }}.
                </p>
                @if (d.operations.length === 0) {
                  <p class="bea-admin-panel__empty">Aucune opération approuvée : la documentation ne contient que les avertissements.</p>
                }
                @for (op of d.operations; track op.operation_id) {
                  <div class="bea-integ-section">
                    <h3>
                      <span class="bea-integ-method" [attr.data-m]="op.methode">{{ op.methode }}</span>
                      <span class="bea-integ-path">{{ op.chemin }}</span>
                    </h3>
                    <p class="bea-integ-muted">{{ op.resume ?? op.operation_id }} — permission(s) : <code>{{ op.exigence_permissions ?? op.permissions.join(', ') }}</code></p>
                    @if (op.prerequis.length) {
                      <ul>@for (p of op.prerequis; track p) { <li>{{ p }}</li> }</ul>
                    }
                    @for (ex of op.exemples; track ex.langage) {
                      <p><strong>{{ ex.libelle }}</strong></p>
                      <pre class="bea-integ-pre">{{ ex.code }}</pre>
                    }
                    @if (op.exemples_motif) {
                      <p class="bea-admin-note">Exemples non générés : {{ op.exemples_motif }}</p>
                    }
                  </div>
                }
              }
            </section>
          }
        }
      }
    </section>
  `,
})
export class CoreAdminIntegrationClientFicheComponent implements OnInit {
  private readonly service = inject(CoreAdminIntegrationClientsService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly suppressions = inject(IntegrationSuppressionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  readonly droits = integrationClientsPermissions();

  readonly chargement = signal(true);
  readonly accesRefuse = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly fiche = signal<IntegrationClientFiche | null>(null);
  readonly onglet = signal<OngletClient>('fiche');
  readonly action = signal(false);

  readonly operations = signal<IntegrationOperationAdmissible[]>([]);
  readonly opsTotal = signal(0);
  readonly opsPage = signal(1);
  readonly opsChargement = signal(false);
  readonly opsErreur = signal<string | null>(null);
  readonly opsPages = computed(() => Math.max(1, Math.ceil(this.opsTotal() / 25)));
  readonly selection = signal<Map<string, IntegrationOperationAdmissible>>(new Map());
  readonly selectionListe = computed(() => [...this.selection().values()]);
  readonly recherche = this.fb.nonNullable.group({ q: '', module: '', methode: '', tout: false });
  readonly justification = this.fb.nonNullable.control('', [sansSecret]);

  readonly grants = signal<IntegrationGrant[]>([]);
  readonly compteurs = signal<{ statut: IntegrationGrantStatut; nombre: number }[]>([]);
  readonly grantsAvertissement = signal('');
  readonly grantsChargement = signal(false);
  readonly grantsErreur = signal<string | null>(null);

  readonly historique = signal<IntegrationGrantEvenement[]>([]);
  readonly histTotal = signal(0);
  readonly histPage = signal(1);
  readonly histChargement = signal(false);
  readonly histErreur = signal<string | null>(null);
  readonly histPages = computed(() => Math.max(1, Math.ceil(this.histTotal() / 50)));

  readonly doc = signal<IntegrationDocumentation | null>(null);
  readonly docChargement = signal(false);
  readonly docErreur = signal<string | null>(null);

  readonly statutLabel = clientStatutLabel;
  readonly statutTone = clientStatutTone;
  readonly transitionLabel = clientTransitionLabel;
  readonly grantLabel = grantStatutLabel;
  readonly grantTone = grantStatutTone;

  readonly ongletsVisibles = computed(() => {
    const d = this.droits;
    const tous: { id: OngletClient; libelle: string; visible: boolean }[] = [
      { id: 'fiche', libelle: 'Fiche', visible: true },
      { id: 'operations', libelle: 'API et opérations', visible: d.grantsManage() },
      { id: 'autorisations', libelle: 'Autorisations', visible: d.grantsView() },
      { id: 'historique', libelle: 'Historique des décisions', visible: d.grantsView() },
      { id: 'documentation', libelle: 'Documentation', visible: d.export() },
    ];
    return tous.filter((o) => o.visible);
  });

  private id = '';

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    const demande = this.route.snapshot.queryParamMap.get('onglet') as OngletClient | null;
    this.chargerFiche(() => {
      if (demande && ONGLETS.includes(demande) && this.ongletsVisibles().some((o) => o.id === demande)) {
        this.choisir(demande);
      }
    });
  }

  chargerFiche(apres?: () => void): void {
    this.service.fiche(this.id).subscribe({
      next: (f) => {
        this.fiche.set(f);
        this.chargement.set(false);
        apres?.();
      },
      error: (err) => {
        this.accesRefuse.set(estAccesRefuse(err));
        this.erreur.set(messageErreur(err, 'Application introuvable.'));
        this.chargement.set(false);
      },
    });
  }

  choisir(o: OngletClient): void {
    this.onglet.set(o);
    void this.router.navigate([], { relativeTo: this.route, queryParams: { onglet: o === 'fiche' ? null : o }, replaceUrl: true });
    if (o === 'operations' && this.operations().length === 0) this.chercherOperations(1);
    if (o === 'autorisations') this.chargerGrants();
    if (o === 'historique') this.chargerHistorique(1);
  }

  isOuvert(s: IntegrationGrantStatut): boolean {
    return STATUTS_OUVERTS.includes(s);
  }

  // ------------------------------------------------------------------ fiche
  async changerStatut(cible: IntegrationClientStatut): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    const ok = await this.dialogs.confirm({
      title: clientTransitionLabel(cible),
      message:
        cible === 'active'
          ? `Activer la fiche « ${f.nom} » ? La fiche devient active pour la configuration ; l'application ne pourra toujours pas s'authentifier.`
          : `${clientTransitionLabel(cible)} : « ${f.nom} » ?`,
      confirmLabel: 'Confirmer',
      tone: cible === 'suspendue' ? 'danger' : 'primary',
    });
    if (!ok) return;
    this.action.set(true);
    this.service.modifier(f.id, f.revision, { statut: cible }).subscribe({
      next: (r) => {
        this.fiche.set(r);
        this.action.set(false);
        void this.dialogs.success(`Statut : ${clientStatutLabel(r.statut)}.`);
      },
      error: (err) => {
        this.action.set(false);
        void this.dialogs.error(messageErreur(err, 'Changement de statut impossible.'));
      },
    });
  }

  async archiver(): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    const valeurs = await this.dialogs.prompt({
      title: 'Archiver l’application',
      message:
        `Archiver « ${f.nom} » ? Les opérations approuvées seront révoquées et les demandes en cours retirées. ` +
        'Rien n’est supprimé : la fiche et son historique restent consultables.',
      tone: 'danger',
      confirmLabel: 'Archiver',
      fields: [{ key: 'motif', label: 'Motif (obligatoire)' }],
      validate: (v) => ((v['motif'] ?? '').trim().length < 3 ? 'Motif obligatoire (3 caractères minimum).' : null),
    });
    if (!valeurs) return;
    this.action.set(true);
    this.service.archiver(f.id, f.revision, valeurs['motif'].trim()).subscribe({
      next: (r) => {
        this.fiche.set(r);
        this.action.set(false);
        void this.dialogs.success(`« ${r.nom} » a été archivée.`);
      },
      error: (err) => {
        this.action.set(false);
        void this.dialogs.error(messageErreur(err, 'Archivage impossible.'));
      },
    });
  }

  async supprimer(): Promise<void> {
    const f = this.fiche();
    if (!f || this.action()) return;
    this.action.set(true);
    const ok = await this.suppressions.supprimer({
      objet: 'l’application',
      nom: f.nom,
      dependances: () => this.service.dependances(f.id),
      supprimer: (revision) => this.service.supprimer(f.id, revision),
    });
    this.action.set(false);
    if (ok) void this.router.navigate(['/admin/integrations/clients']);
  }

  // ------------------------------------------------------------------ opérations
  chercherOperations(page: number): void {
    const v = this.recherche.getRawValue();
    this.opsChargement.set(true);
    this.opsErreur.set(null);
    this.service
      .admissibles(this.id, { q: v.q, module: v.module, methode: v.methode, admissibles_seulement: !v.tout }, page, 25)
      .subscribe({
        next: (r) => {
          this.operations.set(r.items ?? []);
          this.opsTotal.set(r.total ?? 0);
          this.opsPage.set(r.page ?? page);
          this.opsChargement.set(false);
        },
        error: (err) => {
          this.opsErreur.set(messageErreur(err, 'Impossible de charger les opérations.'));
          this.opsChargement.set(false);
        },
      });
  }

  selectionnable(op: IntegrationOperationAdmissible): boolean {
    return op.admissible && !(op.deja_demandee && STATUTS_OUVERTS.includes(op.deja_demandee));
  }

  basculer(op: IntegrationOperationAdmissible): void {
    const suivante = new Map(this.selection());
    if (suivante.has(op.operation_id)) {
      suivante.delete(op.operation_id);
    } else if (this.selectionnable(op) && suivante.size < 50) {
      suivante.set(op.operation_id, op);
    }
    this.selection.set(suivante);
  }

  viderSelection(): void {
    this.selection.set(new Map());
  }

  async demander(): Promise<void> {
    const ids = [...this.selection().keys()];
    if (!ids.length || this.action() || this.justification.invalid) return;
    const ok = await this.dialogs.confirm({
      title: 'Demander des opérations',
      message: `Enregistrer ${ids.length} demande(s) ? Elles devront être soumises puis approuvées ; aucun accès n'est ouvert.`,
      confirmLabel: 'Demander',
    });
    if (!ok) return;
    this.action.set(true);
    this.service.demander(this.id, ids, texteOuNull(this.justification.value)).subscribe({
      next: () => {
        this.action.set(false);
        this.viderSelection();
        this.justification.reset('');
        this.chercherOperations(this.opsPage());
        this.chargerFiche();
        void this.dialogs.success(`${ids.length} opération(s) demandée(s).`);
      },
      error: (err) => {
        this.action.set(false);
        void this.dialogs.error(messageErreur(err, 'Demande impossible.'));
      },
    });
  }

  // ------------------------------------------------------------------ autorisations
  chargerGrants(): void {
    this.grantsChargement.set(true);
    this.grantsErreur.set(null);
    this.service.grants(this.id).subscribe({
      next: (r) => {
        this.grants.set(r.items ?? []);
        this.grantsAvertissement.set(r.avertissement);
        this.compteurs.set(
          Object.entries(r.compteurs ?? {}).map(([statut, nombre]) => ({ statut: statut as IntegrationGrantStatut, nombre: nombre ?? 0 })),
        );
        this.grantsChargement.set(false);
      },
      error: (err) => {
        this.grantsErreur.set(messageErreur(err, 'Impossible de charger les autorisations.'));
        this.grantsChargement.set(false);
      },
    });
  }

  actionsPour(g: IntegrationGrant): GrantAction[] {
    return GRANT_ACTIONS[g.statut].filter((a) => this.droits[a.droit]());
  }

  async decider(g: IntegrationGrant, a: GrantAction): Promise<void> {
    if (this.action()) return;
    let motif: string | null = null;
    const message = `${a.libelle} : ${g.methode} ${g.chemin}`;
    if (a.motif === 'aucun') {
      const ok = await this.dialogs.confirm({ title: a.libelle, message, confirmLabel: a.libelle, tone: a.tone });
      if (!ok) return;
    } else {
      const valeurs = await this.dialogs.prompt({
        title: a.libelle,
        message:
          a.cible === 'approuvee'
            ? `${message}. L'approbation est une configuration : elle n'ouvre aucun accès tant que l'authentification machine-à-machine n'existe pas.`
            : message,
        confirmLabel: a.libelle,
        tone: a.tone,
        fields: [{ key: 'motif', label: a.motif === 'obligatoire' ? 'Motif (obligatoire)' : 'Motif (facultatif)' }],
        validate: (v) => (a.motif === 'obligatoire' && !(v['motif'] ?? '').trim() ? 'Motif obligatoire.' : null),
      });
      if (!valeurs) return;
      motif = texteOuNull(valeurs['motif']);
    }
    this.action.set(true);
    this.service.decider(this.id, g.id, a.cible, motif).subscribe({
      next: (r) => {
        this.action.set(false);
        this.chargerGrants();
        this.chargerFiche();
        void this.dialogs.success(`${r.methode} ${r.chemin} : ${grantStatutLabel(r.statut)}.`);
      },
      error: (err) => {
        this.action.set(false);
        void this.dialogs.error(messageErreur(err, 'Décision impossible.'));
      },
    });
  }

  // ------------------------------------------------------------------ historique & documentation
  chargerHistorique(page: number): void {
    this.histChargement.set(true);
    this.histErreur.set(null);
    this.service.historique(this.id, page, 50).subscribe({
      next: (r) => {
        this.historique.set(r.items ?? []);
        this.histTotal.set(r.total ?? 0);
        this.histPage.set(r.page ?? page);
        this.histChargement.set(false);
      },
      error: (err) => {
        this.histErreur.set(messageErreur(err, "Impossible de charger l'historique."));
        this.histChargement.set(false);
      },
    });
  }

  genererDoc(): void {
    this.docChargement.set(true);
    this.docErreur.set(null);
    this.service.documentation(this.id).subscribe({
      next: (d) => {
        this.doc.set(d);
        this.docChargement.set(false);
      },
      error: (err) => {
        this.docErreur.set(messageErreur(err, 'Documentation indisponible.'));
        this.docChargement.set(false);
      },
    });
  }

  telecharger(d: IntegrationDocumentation): void {
    telechargerTexte(`${d.client_code}-${d.environnement}-documentation.md`, d.markdown);
  }
}
