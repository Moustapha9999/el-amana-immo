import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
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
  CqLog,
  CqResult,
  cqDuration,
  cqPermissions,
  cqSourceLabel,
  cqStatusLabel,
} from './core-query.models';
import {
  CqFailureComponent,
  CqHeaderComponent,
  CqResultsComponent,
  CqSqlViewComponent,
  CqWorkspaceService,
} from './core-query-shared.component';

const TZ = 'Africa/Nouakchott';

/* ------------------------------------------------------------------ */
/* Requêtes favorites                                                  */
/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-core-admin-query-favorites',
  imports: [DatePipe, CoreAdminIconComponent, CqHeaderComponent, CqResultsComponent, CqFailureComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr bea-cq">
      <bea-cq-header title="Requêtes favorites" subtitle="Requêtes enregistrées pour être relancées rapidement. Les favoris système sont partagés par tous les administrateurs." />

      <div class="bea-admin-panel">
        @if (loading() && !items().length) {
          <p class="bea-admin-dash__loading">Chargement des favoris…</p>
        } @else if (!items().length) {
          <p class="bea-admin-panel__empty">Aucun favori. Enregistrez une requête depuis l’Assistant, le Query Builder ou l’éditeur SQL.</p>
        } @else {
          <div class="bea-admin-table-wrap">
            <table class="bea-admin-table">
              <thead>
                <tr>
                  <th>Nom</th>
                  <th>Source</th>
                  <th>Requête</th>
                  <th>Exécutions</th>
                  <th>Dernière exécution</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                @for (f of items(); track f.id) {
                  <tr>
                    <td>
                      <strong>{{ f.name }}</strong>
                      @if (f.is_system) {
                        <span class="bea-cq-tag bea-cq-tag--system">Système</span>
                      }
                      @if (f.description) {
                        <div class="bea-sr-subline">{{ f.description }}</div>
                      }
                    </td>
                    <td><span class="bea-cq-tag">{{ source(f.source) }}</span></td>
                    <td class="bea-cq-ellipsis" [title]="preview(f)">{{ preview(f) }}</td>
                    <td>{{ f.run_count }}</td>
                    <td>{{ f.last_run_at ? (f.last_run_at | date: 'dd/MM/yyyy HH:mm' : tz) : '—' }}</td>
                    <td class="bea-admin-table__actions">
                      <div class="bea-admin-row-actions">
                        @if (perms.execute()) {
                          <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--ok" title="Exécuter" aria-label="Exécuter" [disabled]="running()" (click)="run(f)">
                            <bea-admin-icon name="play_arrow" />
                          </button>
                        }
                        <button type="button" class="bea-admin-icon-btn" title="Ouvrir pour modifier" aria-label="Ouvrir pour modifier" (click)="open(f)">
                          <bea-admin-icon name="open_in_new" />
                        </button>
                        @if (!f.is_system) {
                          <button type="button" class="bea-admin-icon-btn" title="Renommer" aria-label="Renommer" (click)="rename(f)">
                            <bea-admin-icon name="edit" />
                          </button>
                          <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--danger" title="Supprimer" aria-label="Supprimer" (click)="remove(f)">
                            <bea-admin-icon name="delete" />
                          </button>
                        }
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </div>

      @if (failure(); as f) {
        <bea-cq-failure [failure]="f" />
      }
      @if (result(); as r) {
        <p class="bea-cq-running-title"><bea-admin-icon name="star" /> {{ current()?.name }}</p>
        <bea-cq-results [result]="r" [payload]="payload()!" />
      }
    </section>
  `,
})
export class CoreAdminQueryFavoritesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(BeaAdminDialogService);
  private readonly router = inject(Router);
  private readonly ws = inject(CqWorkspaceService);
  readonly perms = cqPermissions();
  readonly tz = TZ;
  readonly source = cqSourceLabel;

  readonly items = signal<CqFavorite[]>([]);
  readonly loading = signal(false);
  readonly running = signal(false);
  readonly busy = signal(false);
  readonly current = signal<CqFavorite | null>(null);
  readonly result = signal<CqResult | null>(null);
  readonly failure = signal<CqFailure | null>(null);
  readonly payload = signal<CqExecutePayload | null>(null);

  ngOnInit(): void {
    this.ws.loadSchema();
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<CqFavorite[]>(`${CQ_API}/favorites`).subscribe({
      next: (f) => {
        this.items.set(f);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  preview(f: CqFavorite): string {
    if (f.source === 'assistant') return f.question ?? '';
    if (f.source === 'sql') return f.sql ?? '';
    return f.spec ? `Table ${f.spec.table} — ${f.spec.columns.length} colonne(s), ${f.spec.filters.length} filtre(s)` : '';
  }

  run(f: CqFavorite): void {
    const payload: CqExecutePayload = { favorite_id: f.id };
    this.current.set(f);
    this.payload.set(payload);
    this.ws.execute(payload, this.running, this.failure).subscribe({
      next: (r) => {
        this.result.set(r);
        this.load();
      },
      error: () => this.result.set(null),
    });
  }

  open(f: CqFavorite): void {
    if (f.source === 'assistant') {
      this.ws.question.set(f.question ?? '');
      this.ws.interpretation.set(null);
      void this.router.navigate(['/admin/core-query']);
    } else if (f.source === 'builder' && f.spec) {
      this.ws.builderSpec.set(f.spec);
      void this.router.navigate(['/admin/core-query/builder']);
    } else {
      this.ws.sqlDraft.set(f.sql ?? '');
      void this.router.navigate(['/admin/core-query/sql']);
    }
  }

  async rename(f: CqFavorite): Promise<void> {
    const values = await this.dialog.prompt({
      title: 'Renommer le favori',
      message: `Nom actuel : « ${f.name} ».`,
      fields: [
        { key: 'name', label: 'Nouveau nom', autocomplete: 'off' },
        { key: 'description', label: 'Description (facultatif)', autocomplete: 'off' },
      ],
      confirmLabel: 'Enregistrer',
      validate: (v) => ((v['name'] ?? '').trim().length < 2 ? 'Le nom est obligatoire (2 caractères minimum).' : null),
    });
    if (!values) return;
    this.feedback
      .run(
        () =>
          this.api.patch<CqFavorite>(`${CQ_API}/favorites/${f.id}`, {
            name: values['name'].trim(),
            description: values['description']?.trim() || null,
          }),
        {
          busy: this.busy,
          retry: false,
          errorTitle: 'Renommage impossible',
          success: (r) => ({ title: 'Favori renommé', message: `« ${r.name} »` }),
        },
      )
      .subscribe(() => this.load());
  }

  async remove(f: CqFavorite): Promise<void> {
    const ok = await this.dialog.confirm({
      title: 'Supprimer le favori',
      message: `Supprimer « ${f.name} » ? L’historique des exécutions est conservé.`,
      tone: 'danger',
      confirmLabel: 'Supprimer',
    });
    if (!ok) return;
    this.feedback
      .run(() => this.api.delete<void>(`${CQ_API}/favorites/${f.id}`), {
        busy: this.busy,
        retry: false,
        errorTitle: 'Suppression impossible',
        success: { title: 'Favori supprimé', message: `« ${f.name} » a été retiré.` },
      })
      .subscribe(() => this.load());
  }
}

/* ------------------------------------------------------------------ */
/* Historique                                                          */
/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-core-admin-query-history',
  imports: [DatePipe, CoreAdminIconComponent, CqHeaderComponent, CqSqlViewComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr bea-cq">
      <bea-cq-header title="Historique" subtitle="Toutes les requêtes CORE QUERY : question, SQL exécuté, durée, nombre de résultats, statut et erreurs." />

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
              <p class="bea-admin-kpi__label">Refusées</p>
              <p class="bea-admin-kpi__value">{{ d.today.refused }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="sessions">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="timer" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Temps moyen</p>
              <p class="bea-admin-kpi__value">{{ duration(d.today.avg_ms) }}</p>
            </div>
          </article>
        </div>
      }

      <div class="bea-admin-toolbar bea-sr-filters">
        @if (allAllowed()) {
          <label class="bea-admin-field">
            <span>Périmètre</span>
            <select [value]="scope()" (change)="setScope($any($event.target).value)">
              <option value="mine">Mes requêtes</option>
              <option value="all">Tous les administrateurs</option>
            </select>
          </label>
        }
        <label class="bea-admin-field">
          <span>Statut</span>
          <select [value]="status()" (change)="setStatus($any($event.target).value)">
            <option value="">Tous</option>
            <option value="success">Réussie</option>
            <option value="refused">Refusée</option>
            <option value="error">Erreur</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Rechercher</span>
          <input type="search" [value]="search()" (change)="setSearch($any($event.target).value)" placeholder="Question ou SQL" />
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="button" class="bea-admin-btn bea-admin-btn--refresh" [disabled]="loading()" (click)="load()">
            <bea-admin-icon name="refresh" /> Actualiser
          </button>
        </div>
      </div>

      <div class="bea-admin-panel">
        @if (loading() && !items().length) {
          <p class="bea-admin-dash__loading">Chargement de l’historique…</p>
        } @else if (!items().length) {
          <p class="bea-admin-panel__empty">Aucune requête pour ces critères.</p>
        } @else {
          <div class="bea-admin-table-wrap">
            <table class="bea-admin-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Utilisateur</th>
                  <th>Source</th>
                  <th>Question / SQL</th>
                  <th>Durée</th>
                  <th>Résultats</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                @for (l of items(); track l.id) {
                  <tr>
                    <td>{{ l.created_at | date: 'dd/MM/yyyy HH:mm:ss' : tz }}</td>
                    <td>{{ l.user_name || l.user_email || '—' }}</td>
                    <td>
                      <span class="bea-cq-tag">{{ source(l.source) }}</span>
                      @if (l.admin_mode) {
                        <div class="bea-sr-subline bea-cq-admin-tag">
                          <bea-admin-icon name="admin_panel_settings" /> {{ l.dry_run ? 'Simulation' : 'Administrateur' }}
                        </div>
                      }
                      @if (l.export_format) {
                        <div class="bea-sr-subline"><bea-admin-icon name="download" /> Export {{ l.export_format.toUpperCase() }}</div>
                      }
                    </td>
                    <td class="bea-cq-ellipsis" [title]="l.question || l.sql || ''">{{ l.question || l.sql }}</td>
                    <td>{{ duration(l.duration_ms) }}</td>
                    <td>{{ l.result_count ?? '—' }}</td>
                    <td>
                      <em class="bea-sr-status" [attr.data-status]="l.status === 'success' ? 'success' : 'failed'" [title]="l.error_message || ''">{{ statusLabel(l.status) }}</em>
                    </td>
                    <td class="bea-admin-table__actions">
                      <div class="bea-admin-row-actions">
                        <button type="button" class="bea-admin-icon-btn" title="Voir détails" aria-label="Voir détails" (click)="detail.set(l)">
                          <bea-admin-icon name="visibility" />
                        </button>
                        <button type="button" class="bea-admin-icon-btn" title="Rejouer" aria-label="Rejouer" (click)="replay(l)">
                          <bea-admin-icon name="replay" />
                        </button>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="bea-admin-pager">
            <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} requête(s)</span>
            <div>
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="go(page() - 1)">Précédent</button>
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages()" (click)="go(page() + 1)">Suivant</button>
            </div>
          </div>
        }
      </div>
    </section>

    @if (detail(); as l) {
      <div class="bea-sr-modal" role="dialog" aria-modal="true" aria-labelledby="bea-cq-detail-title" (click)="detail.set(null)">
        <div class="bea-sr-modal__card" (click)="$event.stopPropagation()">
          <div class="bea-sr-modal__head">
            <div>
              <h2 id="bea-cq-detail-title">Requête du {{ l.created_at | date: 'dd/MM/yyyy à HH:mm:ss' : tz }}</h2>
              <p class="bea-sr-subline">{{ l.user_name || l.user_email || '—' }} · {{ source(l.source) }}</p>
            </div>
            <button type="button" class="bea-admin-icon-btn" title="Fermer" aria-label="Fermer" (click)="detail.set(null)">
              <bea-admin-icon name="close" />
            </button>
          </div>
          <div class="bea-sr-modal__body">
            <dl class="bea-cq-dl">
              <div><dt>Statut</dt><dd><em class="bea-sr-status" [attr.data-status]="l.status === 'success' ? 'success' : 'failed'">{{ statusLabel(l.status) }}</em></dd></div>
              @if (l.question) {
                <div><dt>Question</dt><dd>{{ l.question }}</dd></div>
              }
              <div><dt>Durée</dt><dd>{{ duration(l.duration_ms) }}</dd></div>
              <div><dt>Résultats</dt><dd>{{ resultLabel(l) }}</dd></div>
              @if (l.tables.length) {
                <div><dt>Tables</dt><dd>{{ l.tables.join(', ') }}</dd></div>
              }
              @if (l.admin_mode) {
                <div>
                  <dt>Mode</dt>
                  <dd>Administrateur — {{ l.dry_run ? 'simulation (ROLLBACK)' : 'validée (COMMIT)' }}</dd>
                </div>
                @if (l.command_tag) {
                  <div><dt>Commande</dt><dd class="bea-sr-mono">{{ l.command_tag }}</dd></div>
                }
                @if (l.reason) {
                  <div><dt>Motif</dt><dd>{{ l.reason }}</dd></div>
                }
              }
              @if (l.error_message) {
                <div><dt>Erreur</dt><dd class="bea-cq-error-text">{{ l.error_code }} — {{ l.error_message }}</dd></div>
              }
            </dl>
            @if (l.sql) {
              <bea-cq-sql-view [sql]="l.sql" />
            }
          </div>
          <div class="bea-sr-modal__foot">
            @if (l.sql) {
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="ws.copy(l.sql)">
                <bea-admin-icon name="content_copy" /> Copier SQL
              </button>
            }
            <button type="button" class="bea-admin-btn" (click)="replay(l)">
              <bea-admin-icon name="replay" /> Rejouer
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class CoreAdminQueryHistoryComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly ws = inject(CqWorkspaceService);
  readonly tz = TZ;
  readonly size = 20;
  readonly source = cqSourceLabel;
  readonly statusLabel = cqStatusLabel;
  readonly duration = cqDuration;

  readonly items = signal<CqLog[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly loading = signal(false);
  readonly allAllowed = signal(false);
  readonly scope = signal<'mine' | 'all'>('mine');
  readonly status = signal('');
  readonly search = signal('');
  readonly detail = signal<CqLog | null>(null);
  readonly dashboard = signal<CqDashboard | null>(null);

  ngOnInit(): void {
    this.load();
    this.api.get<CqDashboard>(`${CQ_API}/dashboard`).subscribe({ next: (d) => this.dashboard.set(d), error: () => undefined });
  }

  load(): void {
    const params: Record<string, string | number> = { page: this.page(), size: this.size, scope: this.scope() };
    if (this.status()) params['status'] = this.status();
    if (this.search().trim()) params['q'] = this.search().trim();
    this.loading.set(true);
    this.api
      .get<{ items: CqLog[]; total: number; all_allowed: boolean }>(`${CQ_API}/history`, params)
      .subscribe({
        next: (res) => {
          this.items.set(res.items);
          this.total.set(res.total);
          this.allAllowed.set(res.all_allowed);
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
  }

  setScope(v: 'mine' | 'all'): void {
    this.scope.set(v);
    this.go(1);
  }

  setStatus(v: string): void {
    this.status.set(v);
    this.go(1);
  }

  setSearch(v: string): void {
    this.search.set(v);
    this.go(1);
  }

  go(page: number): void {
    this.page.set(page);
    this.load();
  }

  resultLabel(l: CqLog): string {
    if (l.result_count == null) return '—';
    return `${l.result_count} ligne(s)${l.truncated ? ' (affichage limité)' : ''}`;
  }

  replay(l: CqLog): void {
    this.detail.set(null);
    if (l.source === 'assistant' && l.question) {
      this.ws.question.set(l.question);
      this.ws.interpretation.set(null);
      void this.router.navigate(['/admin/core-query']);
      return;
    }
    this.ws.sqlDraft.set(l.sql ?? '');
    if (l.admin_mode) this.ws.adminMode.set(true);
    void this.router.navigate(['/admin/core-query/sql']);
  }
}
