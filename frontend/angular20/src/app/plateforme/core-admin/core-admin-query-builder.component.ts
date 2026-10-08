import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CQ_AGGREGATES,
  CQ_API,
  CQ_OPERATORS,
  CqBuildResult,
  CqBuilderColumn,
  CqBuilderFilter,
  CqBuilderJoin,
  CqBuilderSpec,
  CqColumn,
  CqExecutePayload,
  CqFailure,
  CqRelation,
  CqResult,
  cqKindLabel,
  cqPermissions,
} from './core-query.models';
import {
  CqFailureComponent,
  CqHeaderComponent,
  CqResultsComponent,
  CqSqlViewComponent,
  CqWorkspaceService,
} from './core-query-shared.component';

interface CqAliasRef {
  alias: string;
  table: string;
  label: string;
}

interface CqRelationOption {
  key: string;
  from: string;
  direction: 'out' | 'in';
  relation: CqRelation;
  target: string;
  label: string;
}

@Component({
  selector: 'bea-core-admin-query-builder',
  imports: [CoreAdminIconComponent, CqHeaderComponent, CqSqlViewComponent, CqResultsComponent, CqFailureComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr bea-cq">
      <bea-cq-header
        title="Query Builder"
        subtitle="Construisez la requête sans écrire de SQL : table, relations existantes, colonnes, filtres. Le SQL est généré et contrôlé côté serveur."
      />

      <div class="bea-cq-builder">
        <section class="bea-admin-panel">
          <div class="bea-cq-panel-head">
            <h2><span class="bea-cq-stepnum">1</span> Table</h2>
          </div>
          <label class="bea-admin-field">
            <span>Table de départ</span>
            <select [value]="table()" (change)="setTable($any($event.target).value)">
              <option value="">Choisir une table…</option>
              @for (t of ws.schema()?.tables ?? []; track t.name) {
                <option [value]="t.name">{{ t.label }} — {{ t.name }}</option>
              }
            </select>
          </label>
        </section>

        @if (table()) {
          <section class="bea-admin-panel">
            <div class="bea-cq-panel-head">
              <h2><span class="bea-cq-stepnum">2</span> Relations</h2>
              <span class="bea-cq-hint">Uniquement les clés étrangères existantes</span>
            </div>
            <ol class="bea-cq-path">
              @for (a of aliases(); track a.alias; let idx = $index) {
                <li>
                  <span class="bea-cq-tag" [title]="a.table">{{ a.label }}</span>
                  @if (idx > 0 && idx === aliases().length - 1) {
                    <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--danger" title="Retirer cette relation" aria-label="Retirer cette relation" (click)="removeLastJoin()">
                      <bea-admin-icon name="close" />
                    </button>
                  }
                </li>
              }
            </ol>
            @if (relationOptions().length && joins().length < 6) {
              <div class="bea-cq-inline">
                <label class="bea-admin-field">
                  <span>Ajouter une relation</span>
                  <select #rel>
                    @for (o of relationOptions(); track o.key) {
                      <option [value]="o.key">{{ o.label }}</option>
                    }
                  </select>
                </label>
                <label class="bea-admin-field">
                  <span>Type</span>
                  <select #jtype>
                    <option value="left">Garder toutes les lignes (LEFT)</option>
                    <option value="inner">Seulement les correspondances (INNER)</option>
                  </select>
                </label>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="addJoin(rel.value, $any(jtype.value))">
                  <bea-admin-icon name="add_link" /> Ajouter
                </button>
              </div>
            } @else if (!relationOptions().length) {
              <p class="bea-admin-panel__empty">Aucune relation déclarée pour cette table.</p>
            }
          </section>

          <section class="bea-admin-panel">
            <div class="bea-cq-panel-head">
              <h2><span class="bea-cq-stepnum">3</span> Colonnes</h2>
              <label class="bea-cq-check">
                <input type="checkbox" [checked]="countAll()" (change)="countAll.set($any($event.target).checked)" />
                Ajouter le nombre de lignes
              </label>
            </div>
            @for (a of aliases(); track a.alias) {
              <fieldset class="bea-cq-cols">
                <legend>{{ a.label }} <small>{{ a.table }}</small></legend>
                <div class="bea-cq-cols__grid">
                  @for (c of columnsOf(a.table); track c.name) {
                    @let sel = selection(a.alias, c.name);
                    <div class="bea-cq-col" [class.bea-cq-col--on]="!!sel">
                      <label>
                        <input type="checkbox" [checked]="!!sel" (change)="toggleColumn(a.alias, c.name)" />
                        <span>{{ c.name }}</span>
                        <small>{{ kind(c.kind) }}</small>
                      </label>
                      @if (sel) {
                        <select [value]="sel.aggregate || ''" (change)="setAggregate(a.alias, c.name, $any($event.target).value)" aria-label="Agrégat">
                          @for (ag of aggregatesFor(c); track ag.value) {
                            <option [value]="ag.value">{{ ag.label }}</option>
                          }
                        </select>
                      }
                    </div>
                  }
                </div>
              </fieldset>
            }
          </section>

          <section class="bea-admin-panel">
            <div class="bea-cq-panel-head">
              <h2><span class="bea-cq-stepnum">4</span> Filtres</h2>
            </div>
            @for (f of filters(); track $index; let fi = $index) {
              @let col = filterColumn(f);
              @let op = operator(f.operator);
              <div class="bea-cq-filter">
                <label class="bea-admin-field">
                  <span>Colonne</span>
                  <select [value]="f.alias + '.' + f.column" (change)="setFilterColumn(fi, $any($event.target).value)">
                    @for (o of filterColumnOptions(); track o.value) {
                      <option [value]="o.value">{{ o.label }}</option>
                    }
                  </select>
                </label>
                <label class="bea-admin-field">
                  <span>Condition</span>
                  <select [value]="f.operator" (change)="patchFilter(fi, { operator: $any($event.target).value })">
                    @for (o of operators; track o.value) {
                      <option [value]="o.value">{{ o.label }}</option>
                    }
                  </select>
                </label>
                @if (op.needsValue >= 1) {
                  <label class="bea-admin-field">
                    <span>{{ op.needsValue === 2 ? 'De' : 'Valeur' }}</span>
                    @if (col?.kind === 'boolean') {
                      <select [value]="f.value || ''" (change)="patchFilter(fi, { value: $any($event.target).value })">
                        <option value="">—</option>
                        <option value="true">Oui</option>
                        <option value="false">Non</option>
                      </select>
                    } @else if (col?.kind === 'enum' && col?.enum_values?.length) {
                      <select [value]="f.value || ''" (change)="patchFilter(fi, { value: $any($event.target).value })">
                        <option value="">—</option>
                        @for (e of col!.enum_values!; track e) {
                          <option [value]="e">{{ e }}</option>
                        }
                      </select>
                    } @else {
                      <input [type]="inputType(col?.kind)" [value]="f.value || ''" (input)="patchFilter(fi, { value: $any($event.target).value })" />
                    }
                  </label>
                }
                @if (op.needsValue === 2) {
                  <label class="bea-admin-field">
                    <span>À</span>
                    <input [type]="inputType(col?.kind)" [value]="f.value2 || ''" (input)="patchFilter(fi, { value2: $any($event.target).value })" />
                  </label>
                }
                <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--danger" title="Supprimer le filtre" aria-label="Supprimer le filtre" (click)="removeFilter(fi)">
                  <bea-admin-icon name="delete" />
                </button>
              </div>
            }
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="addFilter()">
              <bea-admin-icon name="add" /> Ajouter un filtre
            </button>
          </section>

          <section class="bea-admin-panel">
            <div class="bea-cq-panel-head">
              <h2><span class="bea-cq-stepnum">5</span> Tri et limite</h2>
            </div>
            <div class="bea-cq-inline">
              <label class="bea-admin-field">
                <span>Trier par</span>
                <select [value]="orderKey()" (change)="orderKey.set($any($event.target).value)">
                  <option value="">Aucun tri</option>
                  @for (o of filterColumnOptions(); track o.value) {
                    <option [value]="o.value">{{ o.label }}</option>
                  }
                </select>
              </label>
              <label class="bea-admin-field">
                <span>Sens</span>
                <select [value]="orderDir()" (change)="orderDir.set($any($event.target).value)">
                  <option value="desc">Décroissant</option>
                  <option value="asc">Croissant</option>
                </select>
              </label>
              <label class="bea-admin-field">
                <span>Limite</span>
                <input type="number" min="1" max="5000" [value]="limit() ?? ''" (input)="setLimit($any($event.target).value)" placeholder="500 par défaut" />
              </label>
              <label class="bea-cq-check">
                <input type="checkbox" [checked]="distinct()" (change)="distinct.set($any($event.target).checked)" />
                Lignes distinctes
              </label>
            </div>
          </section>

          <section class="bea-admin-panel bea-cq-generated">
            <div class="bea-cq-panel-head">
              <h2><bea-admin-icon name="code" /> SQL généré</h2>
              @if (previewing()) {
                <span class="bea-cq-hint">Génération…</span>
              }
            </div>
            @if (previewError()) {
              <p class="bea-cq-note" data-tone="danger"><bea-admin-icon name="gpp_bad" /> {{ previewError() }}</p>
            } @else if (preview(); as p) {
              <bea-cq-sql-view [sql]="p.sql" />
              @if (p.relations.length || p.filters.length) {
                <ul class="bea-cq-list bea-cq-list--muted">
                  @for (r of p.relations; track r) {
                    <li>Relation : <code>{{ r }}</code></li>
                  }
                  @for (f of p.filters; track f) {
                    <li>Filtre : {{ f }}</li>
                  }
                </ul>
              }
            } @else {
              <p class="bea-admin-panel__empty">Sélectionnez au moins une colonne.</p>
            }
            <div class="bea-cq-actions">
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="!preview()" (click)="ws.copy(preview()!.sql)">
                <bea-admin-icon name="content_copy" /> Copier SQL
              </button>
              @if (perms.sql()) {
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="!preview()" (click)="openInSql()">
                  <bea-admin-icon name="edit_note" /> Modifier en SQL
                </button>
              }
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="!preview() || saving()" (click)="saveFavorite()">
                <bea-admin-icon name="star_border" /> Ajouter aux favoris
              </button>
              @if (perms.execute()) {
                <button type="button" class="bea-admin-btn" [disabled]="!preview() || running()" (click)="run()">
                  <bea-admin-icon name="play_arrow" /> Exécuter
                </button>
              }
            </div>
          </section>
        }

        @if (failure(); as f) {
          <bea-cq-failure [failure]="f" />
        }
        @if (result(); as r) {
          <bea-cq-results [result]="r" [payload]="payload()!" />
        }
      </div>
    </section>
  `,
})
export class CoreAdminQueryBuilderComponent implements OnInit {
  readonly ws = inject(CqWorkspaceService);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly perms = cqPermissions();
  readonly operators = CQ_OPERATORS;
  readonly kind = cqKindLabel;

  readonly table = signal('');
  readonly joins = signal<CqBuilderJoin[]>([]);
  readonly columns = signal<CqBuilderColumn[]>([]);
  readonly countAll = signal(false);
  readonly filters = signal<CqBuilderFilter[]>([]);
  readonly orderKey = signal('');
  readonly orderDir = signal<'asc' | 'desc'>('desc');
  readonly distinct = signal(false);
  readonly limit = signal<number | null>(null);

  readonly preview = signal<CqBuildResult | null>(null);
  readonly previewError = signal<string | null>(null);
  readonly previewing = signal(false);
  readonly running = signal(false);
  readonly saving = signal(false);
  readonly result = signal<CqResult | null>(null);
  readonly failure = signal<CqFailure | null>(null);
  readonly payload = signal<CqExecutePayload | null>(null);

  readonly aliases = computed<CqAliasRef[]>(() => {
    const base = this.table();
    if (!base) return [];
    const out: CqAliasRef[] = [{ alias: 't0', table: base, label: this.ws.tableLabel(base) }];
    const rels = this.ws.schema()?.relations ?? [];
    this.joins().forEach((j, i) => {
      const rel = rels.find((r) => r.name === j.relation);
      if (!rel) return;
      const target = j.direction === 'out' ? rel.ref_table : rel.table;
      out.push({ alias: `t${i + 1}`, table: target, label: this.ws.tableLabel(target) });
    });
    return out;
  });

  readonly relationOptions = computed<CqRelationOption[]>(() => {
    const rels = this.ws.schema()?.relations ?? [];
    const used = new Set(this.joins().map((j) => `${j.from}|${j.relation}|${j.direction}`));
    const opts: CqRelationOption[] = [];
    for (const a of this.aliases()) {
      for (const r of rels) {
        if (r.table === a.table && !used.has(`${a.alias}|${r.name}|out`)) {
          opts.push({
            key: `${a.alias}|${r.name}|out`,
            from: a.alias,
            direction: 'out',
            relation: r,
            target: r.ref_table,
            label: `${a.label} → ${this.ws.tableLabel(r.ref_table)} (${r.table}.${r.columns.join(', ')})`,
          });
        }
        if (r.ref_table === a.table && !used.has(`${a.alias}|${r.name}|in`)) {
          opts.push({
            key: `${a.alias}|${r.name}|in`,
            from: a.alias,
            direction: 'in',
            relation: r,
            target: r.table,
            label: `${a.label} ← ${this.ws.tableLabel(r.table)} (${r.table}.${r.columns.join(', ')})`,
          });
        }
      }
    }
    return opts.sort((x, y) => x.label.localeCompare(y.label, 'fr'));
  });

  readonly filterColumnOptions = computed(() =>
    this.aliases().flatMap((a) =>
      this.columnsOf(a.table).map((c) => ({ value: `${a.alias}.${c.name}`, label: `${a.label} — ${c.name}` })),
    ),
  );

  readonly spec = computed<CqBuilderSpec | null>(() => {
    if (!this.table()) return null;
    const cols = [...this.columns()];
    if (this.countAll()) cols.push({ alias: 't0', column: '*', aggregate: 'count' });
    const [alias, column] = this.orderKey() ? this.orderKey().split('.') : ['', ''];
    return {
      table: this.table(),
      joins: this.joins(),
      columns: cols,
      filters: this.filters().filter((f) => {
        const need = this.operator(f.operator).needsValue;
        return need === 0 || (!!`${f.value ?? ''}`.trim() && (need === 1 || !!`${f.value2 ?? ''}`.trim()));
      }),
      order_by: alias ? [{ alias, column, direction: this.orderDir() }] : [],
      distinct: this.distinct(),
      limit: this.limit(),
    };
  });

  constructor() {
    effect((onCleanup) => {
      const spec = this.spec();
      this.ws.builderSpec.set(spec);
      if (!spec || !spec.columns.length) {
        this.preview.set(null);
        this.previewError.set(null);
        return;
      }
      const timer = setTimeout(() => this.refreshPreview(spec), 350);
      onCleanup(() => clearTimeout(timer));
    });
  }

  ngOnInit(): void {
    this.ws.loadSchema();
    const saved = this.ws.builderSpec();
    if (saved?.table) this.hydrate(saved);
  }

  private hydrate(spec: CqBuilderSpec): void {
    this.table.set(spec.table);
    this.joins.set(spec.joins ?? []);
    this.columns.set((spec.columns ?? []).filter((c) => c.column !== '*'));
    this.countAll.set((spec.columns ?? []).some((c) => c.column === '*'));
    this.filters.set(spec.filters ?? []);
    const o = spec.order_by?.[0];
    this.orderKey.set(o ? `${o.alias}.${o.column}` : '');
    this.orderDir.set(o?.direction ?? 'desc');
    this.distinct.set(!!spec.distinct);
    this.limit.set(spec.limit ?? null);
  }

  private refreshPreview(spec: CqBuilderSpec): void {
    this.previewing.set(true);
    this.api.post<CqBuildResult>(`${CQ_API}/build`, { spec }).subscribe({
      next: (r) => {
        this.preview.set(r);
        this.previewError.set(null);
        this.previewing.set(false);
      },
      error: (e: HttpErrorResponse) => {
        this.preview.set(null);
        this.previewError.set(e.error?.message || 'Configuration invalide.');
        this.previewing.set(false);
      },
    });
  }

  columnsOf(table: string): CqColumn[] {
    return this.ws.tables().get(table)?.columns ?? [];
  }

  setTable(name: string): void {
    this.table.set(name);
    this.joins.set([]);
    this.filters.set([]);
    this.orderKey.set('');
    this.result.set(null);
    this.failure.set(null);
    const preferred = this.columnsOf(name)
      .filter((c) => c.kind !== 'uuid' && c.kind !== 'json')
      .slice(0, 4)
      .map((c) => ({ alias: 't0', column: c.name, aggregate: null }));
    this.columns.set(preferred);
  }

  addJoin(key: string, type: 'left' | 'inner'): void {
    const opt = this.relationOptions().find((o) => o.key === key);
    if (!opt) return;
    this.joins.update((j) => [...j, { relation: opt.relation.name, from: opt.from, direction: opt.direction, type }]);
  }

  removeLastJoin(): void {
    const removed = `t${this.joins().length}`;
    this.joins.update((j) => j.slice(0, -1));
    this.columns.update((c) => c.filter((x) => x.alias !== removed));
    this.filters.update((f) => f.filter((x) => x.alias !== removed));
    if (this.orderKey().startsWith(`${removed}.`)) this.orderKey.set('');
  }

  selection(alias: string, column: string): CqBuilderColumn | undefined {
    return this.columns().find((c) => c.alias === alias && c.column === column);
  }

  toggleColumn(alias: string, column: string): void {
    this.columns.update((cols) =>
      cols.some((c) => c.alias === alias && c.column === column)
        ? cols.filter((c) => !(c.alias === alias && c.column === column))
        : [...cols, { alias, column, aggregate: null }],
    );
  }

  setAggregate(alias: string, column: string, aggregate: string): void {
    this.columns.update((cols) =>
      cols.map((c) => (c.alias === alias && c.column === column ? { ...c, aggregate: aggregate || null } : c)),
    );
  }

  aggregatesFor(c: CqColumn) {
    return CQ_AGGREGATES.filter((a) => c.kind === 'number' || !['sum', 'avg'].includes(a.value));
  }

  filterColumn(f: CqBuilderFilter): CqColumn | undefined {
    const table = this.aliases().find((a) => a.alias === f.alias)?.table;
    return table ? this.columnsOf(table).find((c) => c.name === f.column) : undefined;
  }

  operator(value: string) {
    return CQ_OPERATORS.find((o) => o.value === value) ?? CQ_OPERATORS[0];
  }

  inputType(kind: string | undefined): string {
    if (kind === 'number') return 'number';
    if (kind === 'date' || kind === 'datetime') return 'date';
    return 'text';
  }

  addFilter(): void {
    const first = this.columnsOf(this.table())[0];
    if (!first) return;
    this.filters.update((f) => [...f, { alias: 't0', column: first.name, operator: 'eq', value: '', value2: '' }]);
  }

  setFilterColumn(index: number, key: string): void {
    const [alias, column] = key.split('.');
    this.patchFilter(index, { alias, column, value: '', value2: '' });
  }

  patchFilter(index: number, patch: Partial<CqBuilderFilter>): void {
    this.filters.update((f) => f.map((x, i) => (i === index ? { ...x, ...patch } : x)));
  }

  removeFilter(index: number): void {
    this.filters.update((f) => f.filter((_, i) => i !== index));
  }

  setLimit(v: string): void {
    const n = parseInt(v, 10);
    this.limit.set(Number.isFinite(n) && n > 0 ? Math.min(n, 5000) : null);
  }

  run(): void {
    const spec = this.spec();
    if (!spec) return;
    const payload: CqExecutePayload = { mode: 'builder', spec };
    this.payload.set(payload);
    this.ws.execute(payload, this.running, this.failure).subscribe({
      next: (r) => this.result.set(r),
      error: () => this.result.set(null),
    });
  }

  openInSql(): void {
    this.ws.sqlDraft.set(this.preview()?.sql ?? '');
    void this.router.navigate(['/admin/core-query/sql']);
  }

  saveFavorite(): void {
    const spec = this.spec();
    if (!spec) return;
    void this.ws.saveFavorite('builder', { spec }, this.ws.tableLabel(spec.table), this.saving);
  }
}
