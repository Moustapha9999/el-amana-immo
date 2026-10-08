import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CQ_API,
  CqDashboard,
  CqExecutePayload,
  CqFailure,
  CqFavorite,
  CqInterpretation,
  CqResult,
  cqDuration,
  cqIsWriteSql,
  cqKindLabel,
  cqPermissions,
  cqSourceLabel,
} from './core-query.models';
import {
  CqFailureComponent,
  CqHeaderComponent,
  CqResultsComponent,
  CqSqlEditorComponent,
  CqSqlViewComponent,
  CqWorkspaceService,
} from './core-query-shared.component';

/* ------------------------------------------------------------------ */
/* Assistant                                                           */
/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-core-admin-query-assistant',
  imports: [DecimalPipe, CoreAdminIconComponent, CqHeaderComponent, CqSqlViewComponent, CqResultsComponent, CqFailureComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr bea-cq">
      <bea-cq-header
        title="Assistant"
        subtitle="Posez une question en français : CORE QUERY identifie les tables, génère le SQL, le contrôle puis l’exécute en lecture seule."
      />

      @if (dashboard(); as d) {
        <div class="bea-admin-kpis">
          <article class="bea-admin-kpi" data-tone="modules">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="query_stats" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Requêtes du jour</p>
              <p class="bea-admin-kpi__value">{{ d.today.total }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="org">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="task_alt" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Réussies</p>
              <p class="bea-admin-kpi__value">{{ d.today.success }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="alert">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="block" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Refusées / erreurs</p>
              <p class="bea-admin-kpi__value">{{ d.today.refused }} <small>/ {{ d.today.errors }}</small></p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="sessions">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="timer" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Temps moyen</p>
              <p class="bea-admin-kpi__value">{{ duration(d.today.avg_ms) }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="actions">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="star" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Requêtes favorites</p>
              <p class="bea-admin-kpi__value">{{ d.favorites_count }}</p>
            </div>
          </article>
        </div>
      }

      <div class="bea-cq-grid">
        <div class="bea-cq-main">
          <section class="bea-admin-panel bea-cq-ask">
            <label class="bea-cq-ask__label" for="bea-cq-question">Que voulez-vous rechercher ?</label>
            <textarea
              id="bea-cq-question"
              class="bea-cq-ask__input"
              rows="3"
              maxlength="1000"
              placeholder="Ex. : Quels utilisateurs se sont connectés hier entre 8h et 17h ?"
              [value]="ws.question()"
              (input)="ws.question.set($any($event.target).value)"
              (keydown.control.enter)="analyze()"
              (keydown.meta.enter)="analyze()"
            ></textarea>
            <div class="bea-cq-ask__actions">
              <span class="bea-cq-hint">Ctrl + Entrée pour analyser · aucune donnée n’est modifiée</span>
              <button type="button" class="bea-admin-btn" [disabled]="analyzing() || !ws.question().trim()" (click)="analyze()">
                <bea-admin-icon name="manage_search" /> Analyser
              </button>
            </div>
            <div class="bea-cq-chips" aria-label="Exemples de questions">
              @for (ex of examples(); track ex) {
                <button type="button" class="bea-cq-chip" (click)="useExample(ex)">{{ ex }}</button>
              }
            </div>
          </section>

          @if (interp(); as i) {
            @if (!i.ok) {
              <section class="bea-admin-panel bea-cq-clarify">
                <h2><bea-admin-icon name="help_outline" /> Précision nécessaire</h2>
                <p>{{ i.clarification }}</p>
                @if (i.suggestions.length) {
                  <div class="bea-cq-chips">
                    @for (s of i.suggestions; track s) {
                      <button type="button" class="bea-cq-chip" (click)="useExample(s)">{{ s }}</button>
                    }
                  </div>
                }
              </section>
            } @else {
              <div class="bea-cq-split">
                <section class="bea-admin-panel bea-cq-understand">
                  <div class="bea-cq-panel-head">
                    <h2><bea-admin-icon name="fact_check" /> Compréhension</h2>
                    <span class="bea-cq-confidence" [attr.data-level]="i.confidence">Confiance {{ i.confidence }}</span>
                  </div>
                  <p class="bea-cq-understand__title">{{ i.title }}</p>
                  <dl class="bea-cq-dl">
                    <div><dt>Date</dt><dd>{{ periodDate(i) }}</dd></div>
                    <div><dt>Heure</dt><dd>{{ i.period?.hours || 'Toute la journée' }}</dd></div>
                    <div>
                      <dt>Tables</dt>
                      <dd>
                        @for (t of i.tables; track t) {
                          <span class="bea-cq-tag" [title]="t">{{ ws.tableLabel(t) }}</span>
                        }
                      </dd>
                    </div>
                    <div>
                      <dt>Colonnes</dt>
                      <dd>
                        @for (c of i.columns; track c) {
                          <code class="bea-cq-tag bea-cq-tag--code">{{ c }}</code>
                        }
                      </dd>
                    </div>
                    <div>
                      <dt>Filtres</dt>
                      <dd>
                        @if (i.filters.length) {
                          <ul class="bea-cq-list">
                            @for (f of i.filters; track f) {
                              <li>{{ f }}</li>
                            }
                          </ul>
                        } @else {
                          Aucun
                        }
                      </dd>
                    </div>
                    <div>
                      <dt>Relations</dt>
                      <dd>
                        @if (i.relations.length) {
                          <ul class="bea-cq-list">
                            @for (r of i.relations; track r) {
                              <li><code>{{ r }}</code></li>
                            }
                          </ul>
                        } @else {
                          Aucune (une seule table)
                        }
                      </dd>
                    </div>
                    @if (i.group_by.length) {
                      <div><dt>Regroupement</dt><dd><code>{{ i.group_by.join(', ') }}</code></dd></div>
                    }
                    @if (i.limit) {
                      <div><dt>Limite</dt><dd>{{ i.limit | number: '1.0-0' : 'fr' }} lignes</dd></div>
                    }
                  </dl>
                  @if (i.assumptions.length) {
                    <ul class="bea-cq-assumptions">
                      @for (a of i.assumptions; track a) {
                        <li><bea-admin-icon name="info" /> {{ a }}</li>
                      }
                    </ul>
                  }
                  @if (i.validation; as v) {
                    <p class="bea-cq-note" [attr.data-tone]="v.ok ? 'ok' : 'danger'">
                      <bea-admin-icon [name]="v.ok ? 'verified_user' : 'gpp_bad'" />
                      {{ v.ok ? 'Contrôle de sécurité conforme : lecture seule, tables et colonnes autorisées.' : v.message }}
                    </p>
                  }
                </section>

                <section class="bea-admin-panel bea-cq-generated">
                  <div class="bea-cq-panel-head">
                    <h2><bea-admin-icon name="code" /> Requête générée</h2>
                  </div>
                  <bea-cq-sql-view [sql]="i.sql || ''" />
                  <div class="bea-cq-actions">
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="ws.copy(i.sql || '')">
                      <bea-admin-icon name="content_copy" /> Copier SQL
                    </button>
                    @if (perms.sql()) {
                      <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="editInSql(i)">
                        <bea-admin-icon name="edit_note" /> Modifier en SQL
                      </button>
                    }
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="saving()" (click)="saveFavorite(i)">
                      <bea-admin-icon name="star_border" /> Ajouter aux favoris
                    </button>
                    @if (perms.execute()) {
                      <button type="button" class="bea-admin-btn" [disabled]="running() || i.validation?.ok === false" (click)="run(i)">
                        <bea-admin-icon name="play_arrow" /> Exécuter
                      </button>
                    }
                  </div>
                </section>
              </div>
            }
          }

          @if (failure(); as f) {
            <bea-cq-failure [failure]="f" />
          }
          @if (result(); as r) {
            <bea-cq-results [result]="r" [payload]="payload()!" />
          }
        </div>

        <aside class="bea-cq-side">
          <section class="bea-admin-panel">
            <div class="bea-cq-panel-head">
              <h2><bea-admin-icon name="star" /> Favorites</h2>
            </div>
            @if (dashboard()?.favorites?.length) {
              <ul class="bea-cq-favlist">
                @for (f of dashboard()!.favorites; track f.id) {
                  <li>
                    <button type="button" class="bea-cq-favlist__run" [disabled]="running() || !perms.execute()" (click)="runFavorite(f)" [title]="f.question || f.sql || ''">
                      <bea-admin-icon name="play_circle" />
                      <span>{{ f.name }}</span>
                    </button>
                  </li>
                }
              </ul>
            } @else {
              <p class="bea-admin-panel__empty">Aucune requête favorite.</p>
            }
          </section>
          <section class="bea-admin-panel">
            <div class="bea-cq-panel-head">
              <h2><bea-admin-icon name="history" /> Dernières requêtes</h2>
            </div>
            @if (dashboard()?.recent?.length) {
              <ul class="bea-cq-recent">
                @for (l of dashboard()!.recent; track l.id) {
                  <li>
                    <em class="bea-sr-status" [attr.data-status]="l.status === 'success' ? 'success' : 'failed'">{{ l.status === 'success' ? 'OK' : l.status === 'refused' ? 'Refusée' : 'Erreur' }}</em>
                    <span class="bea-cq-recent__text" [title]="l.question || l.sql || ''">{{ l.question || l.sql }}</span>
                    <small>{{ source(l.source) }} · {{ duration(l.duration_ms) }}</small>
                  </li>
                }
              </ul>
            } @else {
              <p class="bea-admin-panel__empty">Aucune requête aujourd’hui.</p>
            }
          </section>
          @if (ws.schema(); as s) {
            <p class="bea-cq-note" [attr.data-tone]="s.reader_role.available ? 'ok' : 'warn'">
              <bea-admin-icon [name]="s.reader_role.available ? 'lock' : 'lock_open'" />
              {{ s.reader_role.available ? 'Exécution sous rôle PostgreSQL restreint (' + s.reader_role.role + ').' : (s.reader_role.error || 'Rôle restreint indisponible.') }}
            </p>
          }
        </aside>
      </div>
    </section>
  `,
})
export class CoreAdminQueryAssistantComponent implements OnInit {
  readonly ws = inject(CqWorkspaceService);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  readonly perms = cqPermissions();

  readonly interp = this.ws.interpretation;
  readonly analyzing = signal(false);
  readonly running = signal(false);
  readonly saving = signal(false);
  readonly result = signal<CqResult | null>(null);
  readonly failure = signal<CqFailure | null>(null);
  readonly payload = signal<CqExecutePayload | null>(null);
  readonly dashboard = signal<CqDashboard | null>(null);
  readonly examples = computed(() => this.ws.schema()?.examples ?? []);
  readonly duration = cqDuration;
  readonly source = cqSourceLabel;

  ngOnInit(): void {
    this.ws.loadSchema();
    this.loadDashboard();
  }

  loadDashboard(): void {
    this.api.get<CqDashboard>(`${CQ_API}/dashboard`).subscribe({ next: (d) => this.dashboard.set(d), error: () => undefined });
  }

  periodDate(i: CqInterpretation): string {
    if (!i.period) return 'Aucune période (toutes dates)';
    return i.period.date ? `${i.period.label} — ${i.period.date}` : i.period.label;
  }

  analyze(): void {
    const question = this.ws.question().trim();
    if (!question) return;
    this.feedback
      .run(() => this.api.post<CqInterpretation>(`${CQ_API}/analyze`, { question }), {
        loading: 'Analyse de la question…',
        busy: this.analyzing,
        retry: false,
        errorTitle: 'Analyse impossible',
        success: () => null,
      })
      .subscribe((i) => {
        this.interp.set(i);
        this.result.set(null);
        this.failure.set(null);
      });
  }

  useExample(q: string): void {
    this.ws.question.set(q);
    this.analyze();
  }

  run(i: CqInterpretation): void {
    const payload: CqExecutePayload = { mode: 'assistant', question: this.ws.question().trim(), expected_sql: i.sql };
    this.payload.set(payload);
    this.ws.execute(payload, this.running, this.failure).subscribe({
      next: (r) => {
        this.result.set(r);
        this.loadDashboard();
      },
      error: () => {
        this.result.set(null);
        this.loadDashboard();
      },
    });
  }

  runFavorite(f: CqFavorite): void {
    const payload: CqExecutePayload = { favorite_id: f.id };
    this.payload.set(payload);
    if (f.source === 'assistant' && f.question) this.ws.question.set(f.question);
    this.interp.set(null);
    this.ws.execute(payload, this.running, this.failure).subscribe({
      next: (r) => {
        this.result.set(r);
        this.loadDashboard();
      },
      error: () => this.result.set(null),
    });
  }

  editInSql(i: CqInterpretation): void {
    this.ws.sqlDraft.set(i.sql ?? '');
    void this.router.navigate(['/admin/core-query/sql']);
  }

  saveFavorite(i: CqInterpretation): void {
    void this.ws.saveFavorite('assistant', { question: this.ws.question().trim() }, i.title, this.saving);
  }
}

/* ------------------------------------------------------------------ */
/* SQL                                                                 */
/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-core-admin-query-sql',
  imports: [CoreAdminIconComponent, CqHeaderComponent, CqSqlEditorComponent, CqResultsComponent, CqFailureComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr bea-cq">
      <bea-cq-header
        title="SQL"
        [admin]="admin()"
        [subtitle]="
          admin()
            ? 'Mode administrateur : toutes les requêtes sont autorisées (lecture, écriture, structure). Chaque exécution est tracée avec son motif.'
            : 'Consultez et modifiez la requête. Seules les lectures sont acceptées : chaque exécution est validée, limitée et tracée.'
        "
      />

      <div class="bea-cq-grid bea-cq-grid--sql">
        <aside class="bea-admin-panel bea-cq-schema">
          <div class="bea-cq-panel-head">
            <h2><bea-admin-icon name="schema" /> Schéma</h2>
            <button type="button" class="bea-admin-icon-btn" title="Recharger le schéma" aria-label="Recharger le schéma" (click)="ws.loadSchema(true)">
              <bea-admin-icon name="refresh" />
            </button>
          </div>
          <label class="bea-admin-field">
            <span>Rechercher une table</span>
            <input type="search" [value]="tableSearch()" (input)="tableSearch.set($any($event.target).value)" placeholder="users, agences, audit…" />
          </label>
          @if (ws.schemaError()) {
            <p class="bea-admin-dash__error">{{ ws.schemaError() }}</p>
          }
          <ul class="bea-cq-schema__list">
            @for (t of filteredTables(); track t.name) {
              <li>
                <div class="bea-cq-schema__table">
                  <button type="button" class="bea-cq-schema__toggle" [attr.aria-expanded]="open() === t.name" (click)="open.set(open() === t.name ? null : t.name)">
                    <bea-admin-icon [name]="open() === t.name ? 'expand_more' : 'chevron_right'" />
                    <span>{{ t.name }}</span>
                  </button>
                  <button type="button" class="bea-admin-icon-btn" title="Insérer le nom de table" aria-label="Insérer le nom de table" (click)="insert(t.name)">
                    <bea-admin-icon name="input" />
                  </button>
                </div>
                @if (open() === t.name) {
                  <p class="bea-cq-schema__label">{{ t.label }}@if (t.hidden_columns) {<span> · {{ t.hidden_columns }} colonne(s) protégée(s)</span>}</p>
                  <ul class="bea-cq-schema__cols">
                    @for (c of t.columns; track c.name) {
                      <li>
                        <button type="button" (click)="insert(c.name)" [title]="c.type">
                          @if (c.primary_key) {
                            <bea-admin-icon name="key" />
                          }
                          {{ c.name }} <small>{{ kind(c.kind) }}</small>
                        </button>
                      </li>
                    }
                  </ul>
                }
              </li>
            }
          </ul>
        </aside>

        <div class="bea-cq-main">
          <section class="bea-admin-panel" [class.bea-cq-admin]="admin()">
            <div class="bea-cq-panel-head">
              <h2><bea-admin-icon name="code" /> Requête SQL</h2>
              <span class="bea-cq-hint">Ctrl + Entrée pour exécuter · Tab pour indenter</span>
            </div>
            @if (perms.admin()) {
              <label class="bea-cq-admin-toggle">
                <input type="checkbox" [checked]="admin()" (change)="setAdmin($any($event.target).checked)" />
                <span>
                  <strong>Mode administrateur</strong>
                  <small>Écriture et modification de structure autorisées (INSERT, UPDATE, DELETE, CREATE, ALTER…)</small>
                </span>
              </label>
            }
            @if (admin()) {
              <p class="bea-cq-note" data-tone="danger">
                <bea-admin-icon name="admin_panel_settings" />
                Les requêtes s’exécutent directement sur la base BEA DIGITAL. « Simuler » exécute puis annule (ROLLBACK) ;
                « Exécuter » valide (COMMIT) et demande un motif pour toute modification. Un script entier est atomique : une erreur annule tout.
                Avant une modification importante, faites une sauvegarde.
              </p>
            }
            <bea-cq-sql-editor #editor [(value)]="draft" (run)="run()" />
            @if (validation(); as v) {
              <p class="bea-cq-note" [attr.data-tone]="v.ok ? 'ok' : 'danger'">
                <bea-admin-icon [name]="v.ok ? 'verified_user' : 'gpp_bad'" />
                {{ v.ok ? 'Requête conforme (lecture seule). Tables : ' + (v.tables || []).join(', ') : v.message }}
              </p>
            }
            @if (!perms.sql()) {
              <p class="bea-cq-note" data-tone="warn">
                <bea-admin-icon name="lock" />
                Exécution du SQL libre réservée à la permission core.admin.query.sql. Vous pouvez consulter, valider et copier la requête.
              </p>
            }
            <div class="bea-cq-actions">
              @if (!admin()) {
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="!draft().trim() || validating()" (click)="validate()">
                  <bea-admin-icon name="rule" /> Valider
                </button>
              }
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="!draft().trim()" (click)="ws.copy(draft())">
                <bea-admin-icon name="content_copy" /> Copier
              </button>
              @if (admin()) {
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="!draft().trim() || running()" (click)="run(true)">
                  <bea-admin-icon name="science" /> Simuler
                </button>
                <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="!draft().trim() || running()" (click)="run()">
                  <bea-admin-icon name="play_arrow" /> Exécuter
                </button>
              } @else if (perms.sql()) {
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="!draft().trim() || saving()" (click)="saveFavorite()">
                  <bea-admin-icon name="star_border" /> Ajouter aux favoris
                </button>
                <button type="button" class="bea-admin-btn" [disabled]="!draft().trim() || running()" (click)="run()">
                  <bea-admin-icon name="play_arrow" /> Exécuter
                </button>
              }
            </div>
          </section>

          @if (failure(); as f) {
            <bea-cq-failure [failure]="f" />
          }
          @if (result(); as r) {
            <bea-cq-results [result]="r" [payload]="payload()!" />
          }
        </div>
      </div>
    </section>
  `,
})
export class CoreAdminQuerySqlComponent implements OnInit {
  readonly ws = inject(CqWorkspaceService);
  private readonly api = inject(ApiService);
  private readonly dialog = inject(BeaAdminDialogService);
  readonly perms = cqPermissions();
  readonly draft = this.ws.sqlDraft;
  readonly admin = computed(() => this.perms.admin() && this.ws.adminMode());
  private readonly editor = viewChild<CqSqlEditorComponent>('editor');

  readonly tableSearch = signal('');
  readonly open = signal<string | null>(null);
  readonly running = signal(false);
  readonly saving = signal(false);
  readonly validating = signal(false);
  readonly validation = signal<{ ok: boolean; tables?: string[]; message?: string } | null>(null);
  readonly result = signal<CqResult | null>(null);
  readonly failure = signal<CqFailure | null>(null);
  readonly payload = signal<CqExecutePayload | null>(null);
  readonly kind = cqKindLabel;

  readonly filteredTables = computed(() => {
    const q = this.tableSearch().trim().toLowerCase();
    const tables = this.ws.schema()?.tables ?? [];
    return q ? tables.filter((t) => t.name.includes(q) || t.label.toLowerCase().includes(q)) : tables;
  });

  ngOnInit(): void {
    this.ws.loadSchema();
  }

  insert(text: string): void {
    this.editor()?.insert(text);
  }

  validate(): void {
    this.validating.set(true);
    this.api.post<{ ok: boolean; tables?: string[]; message?: string }>(`${CQ_API}/validate`, { sql: this.draft() }).subscribe({
      next: (v) => {
        this.validation.set(v);
        this.validating.set(false);
      },
      error: () => this.validating.set(false),
    });
  }

  setAdmin(on: boolean): void {
    this.ws.adminMode.set(on);
    this.validation.set(null);
    this.failure.set(null);
    this.result.set(null);
  }

  async run(dryRun = false): Promise<void> {
    const sql = this.draft();
    if (!sql.trim() || this.running()) return;
    let payload: CqExecutePayload;
    if (this.admin()) {
      payload = { mode: 'sql', sql, admin: true, dry_run: dryRun };
      if (!dryRun && cqIsWriteSql(sql)) {
        const preview = sql.trim().length > 400 ? `${sql.trim().slice(0, 400)}…` : sql.trim();
        const values = await this.dialog.prompt({
          title: 'Exécuter une modification',
          message:
            `${preview}\n\nCette requête modifie la base BEA DIGITAL et sera validée (COMMIT). ` +
            'Utilisez « Simuler » pour vérifier l’effet sans rien enregistrer.',
          tone: 'danger',
          confirmLabel: 'Exécuter',
          fields: [{ key: 'reason', label: 'Motif (obligatoire, tracé dans l’audit)' }],
          validate: (v) => ((v['reason'] ?? '').trim().length < 5 ? 'Indiquez un motif (5 caractères minimum).' : null),
        });
        if (!values) return;
        payload.reason = values['reason'].trim();
      }
    } else {
      if (!this.perms.sql()) return;
      payload = { mode: 'sql', sql };
    }
    this.payload.set(payload);
    this.validation.set(null);
    this.ws.execute(payload, this.running, this.failure).subscribe({
      next: (r) => {
        this.result.set(r);
        if (r.admin_mode && r.committed && r.is_write) this.ws.loadSchema(true);
      },
      error: () => this.result.set(null),
    });
  }

  saveFavorite(): void {
    void this.ws.saveFavorite('sql', { sql: this.draft() }, 'Requête SQL', this.saving);
  }
}
