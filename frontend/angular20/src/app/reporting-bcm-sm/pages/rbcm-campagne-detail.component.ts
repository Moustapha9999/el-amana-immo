import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import { RbcmCampagneDocumentsComponent } from './rbcm-campagne-documents.component';
import { formatMontantOuTiret } from '../../shared/montant.pipe';
import {
  CONTROL_CATEGORY_LABELS,
  CONTROL_RESULT_LABELS,
  RBCM_API,
  RESOLUTION_LABELS,
  RbcmCampaign,
  RbcmComplementItem,
  RbcmComplements,
  RbcmControlRun,
  RbcmDeleteCheck,
  RbcmHistoryEvent,
  RbcmOwnerCandidate,
  RbcmOwnerHistory,
  RbcmProgress,
  CELL_STATUS_LABELS,
  SM_GUIDED_STEPS,
  STATUS_LABELS,
  RbcmCellResult,
  RbcmCellResultList,
  currentGuidedStep,
  deleteCampaignConfirm,
  guidedStepState,
  periodLabel,
  statusTone,
} from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-campagne-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, DatePipe, FormsModule, RbcmStylesComponent, RbcmCampagneDocumentsComponent],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Situation Mensuelle</p>
          <h1>SM {{ camp() ? periodLabel(camp()!) : '…' }}</h1>
          @if (camp(); as c) {
            <p class="bea-rbcm-statusline">
              <span class="bea-ct-badge" [attr.data-tone]="statusTone(c.status)">{{ STATUS_LABELS[c.status] || c.status }}</span>
              <span class="bea-rbcm-hint">Étape {{ step() }} / 7 — {{ stepLabel() }}</span>
            </p>
          }
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/campagnes">Liste</a>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="reload()">
            <mat-icon>refresh</mat-icon>
          </button>
        </div>
      </header>

      @if (loading()) {
        <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
      } @else if (camp(); as c) {
        <div class="bea-rbcm-grid">
          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Parcours</h2>
                <p class="bea-rbcm-sub">Guidage métier — les détails techniques restent dans l’accès expert.</p>
              </div>
            </div>
            <div class="bea-rbcm-steps">
              @for (s of steps; track s.n) {
                <div class="bea-rbcm-step" [attr.data-state]="guidedStepState(s.n, step())">
                  <mat-icon>{{ stepIcon(s.n) }}</mat-icon>
                  <span>{{ s.n }}. {{ s.label }}</span>
                  <small>{{ stepCaption(s.n) }}</small>
                </div>
              }
            </div>
            <div class="bea-rbcm-quick" style="margin-top:0.85rem">
              @if (showImportAction()) {
                <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/reporting-bcm-sm/imports">
                  <mat-icon>upload_file</mat-icon> Importer BAL DET
                </a>
              }
              @if (showControlAction()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="lancerControles()">
                  <mat-icon>fact_check</mat-icon> {{ progress()?.last_control_run_id ? 'Relancer les contrôles' : 'Contrôler la SM' }}
                </button>
              }
            </div>
            <p class="bea-rbcm-hint" style="margin-top:0.65rem">{{ nextHint() }}</p>
          </section>

          <section class="bea-mg__panel bea-rbcm-span6">
            <div class="bea-mg__panel-top"><div><h2>Informations de la SM</h2></div></div>
            <dl class="bea-rbcm-dl">
              <div><dt>Période</dt><dd>{{ periodLabel(c) }}</dd></div>
              <div><dt>Créateur</dt><dd>{{ c.preparer_name || '—' }}</dd></div>
              <div><dt>Responsable</dt><dd>{{ c.reporting_owner_name || '—' }}</dd></div>
              <div>
                <dt>Désigné le</dt>
                <dd>{{ c.reporting_owner_set_at ? (c.reporting_owner_set_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</dd>
              </div>
              <div><dt>Créée le</dt><dd>{{ c.created_at | date: 'dd/MM/yyyy HH:mm' }}</dd></div>
            </dl>
            @if (canChangeOwner() && c.status !== 'APPROUVEE' && c.status !== 'CLOTUREE') {
              <div class="bea-rbcm-form-grid" style="margin-top:0.85rem">
                <label class="bea-mg__field bea-rbcm-form-wide">
                  <mat-icon>person</mat-icon>
                  <select [(ngModel)]="nextOwnerId" name="nextOwner" aria-label="Nouveau responsable">
                    @for (u of owners(); track u.id) {
                      <option [value]="u.id">{{ u.full_name }} — {{ u.email }}</option>
                    }
                  </select>
                </label>
              </div>
              <div class="bea-rbcm-quick" style="margin-top:0.65rem">
                <button
                  type="button"
                  class="bea-mg__btn bea-mg__btn--ghost"
                  [disabled]="busy() || !nextOwnerId || nextOwnerId === c.reporting_owner_id"
                  (click)="changerResponsable()"
                >
                  <mat-icon>swap_horiz</mat-icon> Changer le responsable
                </button>
              </div>
            }
            <div class="bea-rbcm-quick" style="margin-top:0.75rem">
              @if (canChangeOwner() && c.status !== 'APPROUVEE' && c.status !== 'CLOTUREE') {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="editNotes()">
                  <mat-icon>edit</mat-icon> Modifier les notes
                </button>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="supprimer()">
                <mat-icon>delete</mat-icon> Supprimer
              </button>
              @if (deleteCheck()?.can_archive) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="archiver()">
                  <mat-icon>inventory_2</mat-icon> Archiver
                </button>
              }
              @if (c.status === 'CLOTUREE') {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="rouvrir()">
                  <mat-icon>lock_open</mat-icon> Rouvrir
                </button>
              }
            </div>
            <p class="bea-rbcm-hint" style="margin-top:0.75rem">
              Suppression possible quel que soit le statut — imports, calculs et documents liés sont retirés définitivement.
            </p>
          </section>

          <section class="bea-mg__panel bea-rbcm-span6">
            <div class="bea-mg__panel-top"><div><h2>Historique du responsable</h2></div></div>
            @if (!ownerHistory().length) {
              <p class="bea-rbcm-hint">Aucune désignation enregistrée.</p>
            } @else {
              <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Date</th><th>De</th><th>Vers</th><th>Motif</th></tr></thead>
                <tbody>
                  @for (h of ownerHistory(); track h.id) {
                    <tr>
                      <td>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>{{ h.from_owner_name || '—' }}</td>
                      <td>{{ h.to_owner_name || '—' }}</td>
                      <td>{{ h.motif }}</td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Contrôles</h2>
                <p class="bea-rbcm-sub">Chaque lancement produit un rapport horodaté. Les rapports précédents restent consultables.</p>
              </div>
            </div>
            @if (!runs().length) {
              <p class="bea-rbcm-hint">Aucun contrôle lancé. Importez la BAL DET puis cliquez sur « Contrôler la SM ».</p>
            } @else {
              <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Date</th><th>Résultat</th><th>Lancé par</th><th class="bea-rbcm-col-actions"></th></tr></thead>
                <tbody>
                  @for (r of runs(); track r.id) {
                    <tr>
                      <td>{{ r.created_at ? (r.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                      <td>
                        <span class="bea-ct-badge" [attr.data-tone]="resultTone(r.result)">
                          {{ CONTROL_RESULT_LABELS[r.result] || r.result }}
                        </span>
                      </td>
                      <td>{{ r.actor_name || '—' }}</td>
                      <td class="bea-rbcm-col-actions">
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="voirRapport(r.id)">
                          Consulter
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
            }
            @if (historicRun(); as hr) {
              <div class="bea-rbcm-hint" style="margin-top:0.85rem">
                <p>
                  Rapport du {{ hr.created_at ? (hr.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}
                  — consultation historique (non modifié).
                </p>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="historicRun.set(null)">Fermer</button>
              </div>
              <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Catégorie</th><th>Intitulé</th><th>État</th><th>Gravité</th></tr></thead>
                <tbody>
                  @for (i of hr.issues || []; track i.id) {
                    <tr>
                      <td>{{ i.category || '—' }}</td>
                      <td>{{ i.title }}</td>
                      <td>{{ RESOLUTION_LABELS[i.resolution_state] || i.resolution_state }}</td>
                      <td>{{ i.severity }}</td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Informations à compléter</h2>
                <p class="bea-rbcm-sub">File métier A / B / C / D — les détails NCG et mapping restent dans l’accès expert.</p>
              </div>
            </div>
            @if (complements()?.technical_failure) {
              <p class="bea-rbcm-hint">Le dernier contrôle a échoué techniquement. Il n’est pas un résultat métier OK. Relancez les contrôles.</p>
            }
            @if (!complements()?.run) {
              <p class="bea-rbcm-hint">Lancez les contrôles pour constituer la file.</p>
            } @else {
              <div class="bea-rbcm-quick" style="margin-bottom:0.75rem">
                @for (cat of categories; track cat) {
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--ghost"
                    [class.bea-mg__btn--primary]="catFilter() === cat"
                    (click)="catFilter.set(cat)"
                  >
                    {{ cat }} · {{ complements()?.counts?.[cat] || 0 }}
                  </button>
                }
              </div>
              @for (cat of categories; track cat) {
                @if (catFilter() === cat) {
                  <h3 style="margin:0 0 0.5rem;font-size:0.95rem">{{ CONTROL_CATEGORY_LABELS[cat] }}</h3>
                  @if (!(complements()?.by_category?.[cat] || []).length) {
                    <p class="bea-rbcm-hint">Aucun élément dans cette catégorie.</p>
                  } @else {
                    <div class="bea-rbcm-sources">
                      @for (it of complements()?.by_category?.[cat] || []; track it.id) {
                        <article class="bea-rbcm-source" [attr.data-state]="itemState(it)">
                          <header>
                            <p class="bea-rbcm-source__name">{{ it.title }}</p>
                            <span class="bea-ct-badge">{{ RESOLUTION_LABELS[it.live_state || it.resolution_state] || it.resolution_state }}</span>
                          </header>
                          <p class="bea-rbcm-hint">{{ it.message }}</p>
                          <dl class="bea-rbcm-dl">
                            <div><dt>Gravité</dt><dd>{{ it.severity }}</dd></div>
                            @if (it.observed !== null && it.observed !== undefined) {
                              <div><dt>Observé</dt><dd>{{ displayObserved(it.observed) }}</dd></div>
                            }
                            @if (it.expected) {
                              <div><dt>Attendu</dt><dd>{{ it.expected }}</dd></div>
                            }
                            @if (it.source) {
                              <div><dt>Source</dt><dd>{{ it.source }}</dd></div>
                            }
                            @if (it.expected_source) {
                              <div><dt>Source attendue</dt><dd>{{ it.expected_source }}</dd></div>
                            }
                            @if (it.consequence) {
                              <div><dt>Si absent</dt><dd>{{ it.consequence }}</dd></div>
                            }
                          </dl>
                          <div class="bea-rbcm-quick">
                            @for (a of it.available_actions || []; track a) {
                              @if (a === 'CONSULTER') {
                                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="selected.set(it)">Consulter le détail</button>
                              }
                              @if (a === 'SAISIR') {
                                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirSaisie(it)">Saisir une valeur</button>
                              }
                              @if (a === 'RELANCER') {
                                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="lancerControles()">Relancer les contrôles</button>
                              }
                              @if (a === 'IMPORTER') {
                                <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/reporting-bcm-sm/imports">Importer BAL DET</a>
                              }
                            }
                          </div>
                        </article>
                      }
                    </div>
                  }
                }
              }
            }
            @if (selected(); as it) {
              <div class="bea-mg__panel" style="margin-top:1rem">
                <div class="bea-mg__panel-top">
                  <div><h2>{{ it.title }}</h2><p class="bea-rbcm-sub">{{ CONTROL_CATEGORY_LABELS[it.category || ''] }} · {{ it.code }}</p></div>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="selected.set(null)">Fermer</button>
                </div>
                <p>{{ it.message }}</p>
                @if (it.recommended_action) {
                  <p class="bea-rbcm-hint">{{ it.recommended_action }}</p>
                }
                @if (it.category === 'D') {
                  <p class="bea-rbcm-hint">Décision métier — aucune activation automatique. Accès expert : Correspondances.</p>
                }
              </div>
            }
            @if (saisie(); as it) {
              <div class="bea-mg__panel" style="margin-top:1rem">
                <div class="bea-mg__panel-top">
                  <div><h2>Saisir — {{ it.title }}</h2></div>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="saisie.set(null)">Annuler</button>
                </div>
                <div class="bea-rbcm-form-grid">
                  <label class="bea-mg__field bea-rbcm-form-wide">
                    <mat-icon>payments</mat-icon>
                    <input [(ngModel)]="saisieForm.value" name="saisieValue" placeholder="Valeur (laisser vide = non renseigné, pas zéro)" />
                  </label>
                  <label class="bea-mg__field">
                    <mat-icon>source</mat-icon>
                    <input [(ngModel)]="saisieForm.source" name="saisieSource" placeholder="Source" />
                  </label>
                  <label class="bea-mg__field">
                    <mat-icon>description</mat-icon>
                    <input [(ngModel)]="saisieForm.justificatif_ref" name="saisieJustifRef" placeholder="Référence justificatif (optionnel)" />
                  </label>
                  <label class="bea-mg__field bea-rbcm-form-wide bea-rbcm-form-textarea">
                    <mat-icon>notes</mat-icon>
                    <textarea rows="3" [(ngModel)]="saisieForm.justification" name="saisieJustif" placeholder="Justification obligatoire"></textarea>
                  </label>
                </div>
                <p class="bea-rbcm-hint">Une valeur vide n’est jamais transformée en 0,00. Relancez les contrôles après enregistrement.</p>
                <div class="bea-rbcm-quick" style="margin-top:0.65rem">
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="enregistrerSaisie()">Enregistrer</button>
                </div>
              </div>
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Valeurs alimentées</h2>
                <p class="bea-rbcm-sub">Calculées depuis la BAL DET. Les cellules orange restent à saisir (paramètres ou Excel après téléchargement).</p>
              </div>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !progress()?.det_validated" (click)="calculer()">
                <mat-icon>calculate</mat-icon> Alimenter depuis la BAL DET
              </button>
            </div>
            @if (!cells().length) {
              <p class="bea-rbcm-hint">Aucun calcul pour cette SM. Importez la BAL DET puis lancez l’alimentation.</p>
            } @else {
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead>
                    <tr>
                      <th>Cellule</th>
                      <th>Origine</th>
                      <th>Calculé</th>
                      <th>Retenu</th>
                      <th>Statut</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (row of visibleCells(); track row.cell_ref) {
                      <tr>
                        <td>{{ row.cell_ref }}</td>
                        <td>{{ row.origin || '—' }}</td>
                        <td>{{ displayCellAmount(row.calculated_value) }}</td>
                        <td>{{ displayCellAmount(row.retained_value) }}</td>
                        <td>{{ CELL_STATUS_LABELS[row.value_status] || row.value_status }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </section>

          <bea-rbcm-campagne-documents [campaignId]="c.id" [refreshNonce]="docNonce()" />

          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Accès expert</h2>
                <p class="bea-rbcm-sub">Écrans techniques — hors parcours comptable principal.</p>
              </div>
            </div>
            <div class="bea-rbcm-quick">
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/imports"><mat-icon>upload_file</mat-icon> Imports</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/bal-det"><mat-icon>table_rows</mat-icon> Lignes DET</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/rapprochement"><mat-icon>fact_check</mat-icon> Contrôles</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/parametres"><mat-icon>tune</mat-icon> Paramètres</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/mapping"><mat-icon>account_tree</mat-icon> Correspondances</a>
              @if (progress()?.cond_validated) {
                <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/bal-cond"><mat-icon>inventory_2</mat-icon> Archives COND</a>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="true" title="Bloqué tant que D01 n’est pas validé">
                <mat-icon>lock</mat-icon> Soumettre au contrôle
              </button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="true" title="Bloqué — D01/D02">
                <mat-icon>lock</mat-icon> Approuver
              </button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="calculer()">
                <mat-icon>calculate</mat-icon> Calcul (expert)
              </button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exportExcel()">
                <mat-icon>table_view</mat-icon> Export technique
              </button>
            </div>
            @if (history().length) {
              <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Date</th><th>Action</th><th>De → Vers</th></tr></thead>
                <tbody>
                  @for (h of history(); track h.id) {
                    <tr>
                      <td>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>{{ h.action }}</td>
                      <td>{{ h.from_status || '—' }} → {{ h.to_status || '—' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
            }
          </section>
        </div>
      }
    </div>
  `,
})
export class RbcmCampagneDetailComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly ctx = inject(RbcmContextService);

  readonly STATUS_LABELS = STATUS_LABELS;
  readonly CELL_STATUS_LABELS = CELL_STATUS_LABELS;
  readonly CONTROL_RESULT_LABELS = CONTROL_RESULT_LABELS;
  readonly CONTROL_CATEGORY_LABELS = CONTROL_CATEGORY_LABELS;
  readonly RESOLUTION_LABELS = RESOLUTION_LABELS;
  readonly statusTone = statusTone;
  readonly periodLabel = periodLabel;
  readonly guidedStepState = guidedStepState;
  readonly steps = SM_GUIDED_STEPS;
  readonly categories = ['A', 'B', 'C', 'D'] as const;

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly camp = signal<RbcmCampaign | null>(null);
  readonly progress = signal<RbcmProgress | null>(null);
  readonly history = signal<RbcmHistoryEvent[]>([]);
  readonly ownerHistory = signal<RbcmOwnerHistory[]>([]);
  readonly owners = signal<RbcmOwnerCandidate[]>([]);
  readonly deleteCheck = signal<RbcmDeleteCheck | null>(null);
  readonly runs = signal<RbcmControlRun[]>([]);
  readonly complements = signal<RbcmComplements | null>(null);
  readonly historicRun = signal<RbcmControlRun | null>(null);
  readonly selected = signal<RbcmComplementItem | null>(null);
  readonly saisie = signal<RbcmComplementItem | null>(null);
  readonly catFilter = signal<'A' | 'B' | 'C' | 'D'>('C');
  readonly cells = signal<RbcmCellResult[]>([]);
  readonly docNonce = signal(0);
  saisieForm = { value: '', source: '', justification: '', justificatif_ref: '' };
  nextOwnerId = '';
  private id = '';

  readonly step = computed(() => {
    const c = this.camp();
    return c ? currentGuidedStep(c, this.progress()) : 1;
  });
  readonly stepLabel = computed(() => {
    const n = this.step();
    return this.steps.find((s) => s.n === n)?.label || '';
  });
  readonly visibleCells = computed(() =>
    this.cells().filter((r) => {
      const origin = r.origin || '';
      if (r.cell_ref.endsWith(':H')) return false;
      return ['AUTO', 'MANUAL', 'AUTO_THEN_ADJUST', 'PCT', 'REMAINDER', 'COPY'].includes(origin);
    }),
  );

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') || '';
    this.ctx.select(this.id);
    this.reload();
  }

  canChangeOwner(): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const codes = u.permission_codes ?? [];
    return (
      codes.includes('*') ||
      codes.includes('reporting-bcm-sm.prepare') ||
      codes.includes('reporting-bcm-sm.admin')
    );
  }

  showImportAction(): boolean {
    const c = this.camp();
    const p = this.progress();
    if (!c || c.status === 'APPROUVEE' || c.status === 'CLOTUREE') return false;
    if (!this.canImport()) return false;
    return !p?.det_validated;
  }

  showControlAction(): boolean {
    const c = this.camp();
    const p = this.progress();
    if (!c || c.status === 'APPROUVEE' || c.status === 'CLOTUREE') return false;
    if (!p?.det_validated) return false;
    return this.canControl();
  }

  canControl(): boolean {
    return this.hasPerm(
      'reporting-bcm-sm.prepare',
      'reporting-bcm-sm.control',
      'reporting-bcm-sm.import',
      'reporting-bcm-sm.admin',
    );
  }

  canSaisir(): boolean {
    return this.hasPerm(
      'reporting-bcm-sm.parameters.write',
      'reporting-bcm-sm.prepare',
      'reporting-bcm-sm.control',
      'reporting-bcm-sm.correct',
      'reporting-bcm-sm.admin',
    );
  }

  canImport(): boolean {
    return this.hasPerm(
      'reporting-bcm-sm.import',
      'reporting-bcm-sm.prepare',
      'reporting-bcm-sm.control',
      'reporting-bcm-sm.admin',
    );
  }

  private hasPerm(...codes: string[]): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const have = u.permission_codes ?? [];
    if (have.includes('*')) return true;
    return codes.some((c) => have.includes(c));
  }

  nextHint(): string {
    const p = this.progress();
    if (!p?.det_validated) return 'Étape suivante : importer et confirmer la BAL DET.';
    if (!p.last_control_run_id) return 'Étape suivante : lancer les contrôles de la SM.';
    const n = p.complements_open ?? this.complements()?.counts?.['open'] ?? 0;
    if (n > 0) return `${n} information(s) à compléter ou décision(s) en attente.`;
    return 'Contrôles à jour. Alimentez la SM depuis la BAL DET puis générez le canevas.';
  }

  resultTone(result: string): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (result === 'OK') return 'ok';
    if (result === 'BLOCKING' || result === 'FAILED') return 'danger';
    if (result === 'INCOMPLETE' || result === 'DECISIONS_PENDING') return 'warn';
    return 'info';
  }

  itemState(it: RbcmComplementItem): string {
    if (it.live_state === 'SAISIE_A_RECONTROLER') return 'ready';
    if (it.severity === 'BLOCKING' || it.resolution_state === 'STILL_BLOCKING') return 'error';
    if (it.category === 'D') return 'missing';
    return 'ready';
  }

  displayObserved(value: string | null | undefined): string {
    if (value == null || value === '') return '—';
    if (/^-?\d+([.,]\d+)?$/.test(value.trim())) return formatMontantOuTiret(value);
    return value;
  }

  stepIcon(n: number): string {
    const st = guidedStepState(n, this.step());
    if (st === 'done') return 'check_circle';
    if (st === 'current') return 'play_circle';
    if (st === 'blocked') return 'lock';
    return 'radio_button_unchecked';
  }

  stepCaption(n: number): string {
    const st = guidedStepState(n, this.step());
    if (st === 'done') return 'Terminé';
    if (st === 'current') return 'En cours';
    if (st === 'blocked') return n >= 5 ? 'Plus tard — D01/D02' : 'À venir';
    return 'À venir';
  }

  reload(): void {
    this.loading.set(true);
    this.api.get<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}`).subscribe({
      next: (c) => {
        this.camp.set(c);
        this.nextOwnerId = c.reporting_owner_id || '';
        this.loading.set(false);
        this.api.get<RbcmProgress>(`${RBCM_API}/campaigns/${this.id}/progress`).subscribe((p) => this.progress.set(p));
        this.api.get<{ items: RbcmControlRun[] }>(`${RBCM_API}/campaigns/${this.id}/controls/runs`).subscribe({
          next: (r) => this.runs.set(r.items || []),
          error: () => this.runs.set([]),
        });
        this.api.get<RbcmComplements>(`${RBCM_API}/campaigns/${this.id}/complements`).subscribe({
          next: (cplt) => {
            this.complements.set(cplt);
            const order = ['C', 'D', 'B', 'A'] as const;
            const first = order.find((k) => (cplt.counts?.[k] || 0) > 0);
            if (first) this.catFilter.set(first);
          },
          error: () => this.complements.set(null),
        });
        this.api.get<RbcmHistoryEvent[]>(`${RBCM_API}/campaigns/${this.id}/history`).subscribe((h) => this.history.set(h));
        this.api
          .get<RbcmOwnerHistory[]>(`${RBCM_API}/campaigns/${this.id}/reporting-owner/history`)
          .subscribe((h) => this.ownerHistory.set(h));
        this.api.get<RbcmDeleteCheck>(`${RBCM_API}/campaigns/${this.id}/delete-check`).subscribe((d) => this.deleteCheck.set(d));
        this.api.get<RbcmCellResultList>(`${RBCM_API}/campaigns/${this.id}/cells`).subscribe({
          next: (res) => this.cells.set(res.items || []),
          error: () => this.cells.set([]),
        });
        if (this.canChangeOwner()) {
          this.api.get<RbcmOwnerCandidate[]>(`${RBCM_API}/preparateurs`).subscribe({
            next: (rows) => this.owners.set(rows),
            error: () => this.owners.set([]),
          });
        }
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'SM introuvable');
          this.loading.set(false);
        }),
    });
  }

  changerResponsable(): void {
    const c = this.camp();
    if (!c || !this.nextOwnerId || this.nextOwnerId === c.reporting_owner_id) return;
    const dest = this.owners().find((u) => u.id === this.nextOwnerId);
    this.feedback
      .runWithReason(
        (motif) =>
          this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}/reporting-owner`, {
            reporting_owner_id: this.nextOwnerId,
            motif,
          }),
        {
          busy: this.busy,
          reason: {
            title: 'Changer le responsable ?',
            message: `Nouveau responsable : ${dest?.full_name || 'sélectionné'}. Le motif est obligatoire.`,
            confirmLabel: 'Enregistrer',
            required: true,
          },
          loading: 'Enregistrement…',
          success: { title: 'Responsable mis à jour' },
          errorTitle: 'Changement impossible',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  editNotes(): void {
    const c = this.camp();
    if (!c) return;
    this.feedback
      .runWithReason(
        (notes) => this.api.patch<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}`, { notes }),
        {
          busy: this.busy,
          reason: {
            title: 'Modifier les notes',
            message: periodLabel(c),
            confirmLabel: 'Enregistrer',
            reasonLabel: 'Notes',
            required: false,
          },
          loading: 'Enregistrement…',
          success: { title: 'SM mise à jour' },
          errorTitle: 'Modification impossible',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  rouvrir(): void {
    const c = this.camp();
    if (!c) return;
    this.feedback
      .runWithReason(
        (comment) => this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}/reopen`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Réouverture contrôlée',
            message: 'Une nouvelle version sera créée. Les anciennes versions sont conservées.',
            confirmLabel: 'Rouvrir',
            reasonLabel: 'Motif',
            required: true,
          },
          loading: 'Réouverture…',
          success: { title: 'Nouvelle version créée' },
          errorTitle: 'Réouverture impossible',
        },
      )
      .subscribe({
        next: (n) => {
          this.ctx.select(n.id);
          void this.router.navigate(['/reporting-bcm-sm/campagnes', n.id]);
        },
      });
  }

  supprimer(): void {
    const c = this.camp();
    if (!c) return;
    this.feedback
      .run(() => this.api.delete(`${RBCM_API}/campaigns/${this.id}`), {
        busy: this.busy,
        confirm: {
          title: 'Supprimer ?',
          message: deleteCampaignConfirm(c, this.deleteCheck()),
          confirmLabel: 'Supprimer',
          tone: 'danger',
        },
        loading: 'Suppression…',
        success: { title: 'SM supprimée' },
        errorTitle: 'Suppression impossible',
      })
      .subscribe({ next: () => void this.router.navigate(['/reporting-bcm-sm/campagnes']) });
  }

  archiver(): void {
    this.feedback
      .runWithReason(
        (comment) => this.api.post(`${RBCM_API}/campaigns/${this.id}/archive`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Archiver ?',
            message: 'Données conservées, statut CLOTUREE.',
            confirmLabel: 'Archiver',
            required: false,
          },
          loading: 'Archivage…',
          success: { title: 'SM archivée' },
          errorTitle: 'Archivage impossible',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  lancerControles(): void {
    this.feedback
      .run(() => this.api.post<RbcmControlRun>(`${RBCM_API}/campaigns/${this.id}/controls/runs`, {}), {
        busy: this.busy,
        loading: 'Contrôles en cours…',
        success: { title: 'Contrôles enregistrés' },
        errorTitle: 'Contrôles impossibles',
      })
      .subscribe({
        next: () => {
          this.historicRun.set(null);
          this.selected.set(null);
          this.saisie.set(null);
          this.reload();
        },
      });
  }

  voirRapport(runId: string): void {
    this.api.get<RbcmControlRun>(`${RBCM_API}/campaigns/${this.id}/controls/runs/${runId}`).subscribe({
      next: (r) => this.historicRun.set(r),
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Rapport introuvable')),
    });
  }

  ouvrirSaisie(it: RbcmComplementItem): void {
    this.saisieForm = {
      value: it.proposed_value || '',
      source: it.expected_source || it.source || '',
      justification: '',
      justificatif_ref: '',
    };
    this.saisie.set(it);
    this.selected.set(null);
  }

  enregistrerSaisie(): void {
    const it = this.saisie();
    const code = it?.parameter_code;
    if (!it || !code) return;
    const value = this.saisieForm.value.trim() === '' ? null : this.saisieForm.value.trim();
    this.feedback
      .run(
        () =>
          this.api.post(`${RBCM_API}/campaigns/${this.id}/parameters`, {
            parameter_code: code,
            value,
            source: this.saisieForm.source || null,
            justification: this.saisieForm.justification || null,
            justificatif_ref: this.saisieForm.justificatif_ref || null,
            expected_value_id: it.current_value_id || it.details?.['current_value_id'] || null,
          }),
        {
          busy: this.busy,
          loading: 'Enregistrement…',
          success: { title: 'Information enregistrée' },
          errorTitle: 'Saisie impossible',
        },
      )
      .subscribe({
        next: () => {
          this.saisie.set(null);
          this.reload();
        },
      });
  }

  calculer(): void {
    this.feedback
      .run(() => this.api.post(`${RBCM_API}/campaigns/${this.id}/calculate`, {}), {
        busy: this.busy,
        loading: 'Alimentation depuis la BAL DET…',
        success: { title: 'SM alimentée' },
        errorTitle: 'Calcul impossible',
      })
      .subscribe({
        next: () => {
          this.docNonce.update((n) => n + 1);
          this.reload();
        },
      });
  }

  displayCellAmount(value: string | number | null | undefined): string {
    if (value == null || value === '') return '—';
    return formatMontantOuTiret(String(value));
  }

  exportExcel(): void {
    this.feedback
      .run(
        () =>
          this.api.post<{ id: string; filename: string }>(`${RBCM_API}/campaigns/${this.id}/exports/excel`, {}),
        {
          busy: this.busy,
          loading: 'Export…',
          success: { title: 'Excel généré' },
          errorTitle: 'Export impossible',
        },
      )
      .subscribe({
        next: (d) => {
          if (!d?.id) return;
          this.feedback
            .run(
              () => this.api.download(`${RBCM_API}/campaigns/${this.id}/exports/${d.id}/download`),
              {
                busy: this.busy,
                loading: 'Téléchargement…',
                success: { title: 'Fichier prêt' },
                errorTitle: 'Téléchargement impossible',
              },
            )
            .subscribe({
              next: (blob) => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = d.filename || 'export-bcm.xlsx';
                a.click();
                URL.revokeObjectURL(url);
              },
            });
        },
      });
  }
}
