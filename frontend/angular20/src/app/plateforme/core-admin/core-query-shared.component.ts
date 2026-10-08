import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  Injectable,
  WritableSignal,
  computed,
  effect,
  inject,
  input,
  model,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { Observable, catchError, throwError } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CQ_API,
  CqBuilderSpec,
  CqExecutePayload,
  CqFailure,
  CqFavorite,
  CqInterpretation,
  CqResult,
  CqSchema,
  CqSource,
  CqStep,
  CqTable,
  cqDuration,
  cqPermissions,
  cqTokenizeSql,
} from './core-query.models';

const TZ = 'Africa/Nouakchott';

const CQ_TABS = [
  { label: 'Assistant', path: '/admin/core-query', icon: 'manage_search' },
  { label: 'Query Builder', path: '/admin/core-query/builder', icon: 'account_tree' },
  { label: 'SQL', path: '/admin/core-query/sql', icon: 'code' },
  { label: 'Requêtes favorites', path: '/admin/core-query/favoris', icon: 'star' },
  { label: 'Historique', path: '/admin/core-query/historique', icon: 'history' },
];

/** État partagé entre les écrans CORE QUERY (schéma, brouillons, exécution, export). */
@Injectable({ providedIn: 'root' })
export class CqWorkspaceService {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(BeaAdminDialogService);

  readonly schema = signal<CqSchema | null>(null);
  readonly schemaError = signal<string | null>(null);
  readonly tables = computed(() => {
    const map = new Map<string, CqTable>();
    for (const t of this.schema()?.tables ?? []) map.set(t.name, t);
    return map;
  });

  readonly question = signal('');
  readonly interpretation = signal<CqInterpretation | null>(null);
  readonly sqlDraft = signal('');
  readonly adminMode = signal(false);
  readonly builderSpec = signal<CqBuilderSpec | null>(null);

  loadSchema(refresh = false): void {
    if (this.schema() && !refresh) return;
    this.schemaError.set(null);
    this.api.get<CqSchema>(`${CQ_API}/schema`, refresh ? { refresh: true } : undefined).subscribe({
      next: (s) => this.schema.set(s),
      error: () => this.schemaError.set('Schéma indisponible : vérifiez vos droits CORE QUERY.'),
    });
  }

  tableLabel(name: string): string {
    return this.tables().get(name)?.label ?? name;
  }

  execute(
    payload: CqExecutePayload,
    busy: WritableSignal<boolean>,
    failure: WritableSignal<CqFailure | null>,
  ): Observable<CqResult> {
    let detail: { reason?: string; steps?: CqStep[]; sql?: string } | null = null;
    failure.set(null);
    return this.feedback.run(
      () =>
        this.api.post<CqResult>(`${CQ_API}/execute`, payload).pipe(
          catchError((err: HttpErrorResponse) => {
            detail = err.error?.detail && typeof err.error.detail === 'object' ? err.error.detail : null;
            return throwError(() => err);
          }),
        ),
      {
        loading: !payload.admin
          ? 'Exécution en lecture seule…'
          : payload.dry_run
            ? 'Simulation (annulée à la fin)…'
            : 'Exécution en mode administrateur…',
        busy,
        retry: false,
        errorTitle: 'Requête non exécutée',
        onError: (e) =>
          failure.set({
            code: e.code,
            reason: detail?.reason ?? e.code,
            message: e.message,
            requestId: e.requestId,
            steps: detail?.steps ?? [],
            sql: detail?.sql ?? null,
          }),
        success: (r) =>
          r.admin_mode && r.committed && r.is_write
            ? { title: 'Modification enregistrée', message: `${r.command_tag ?? 'Commande exécutée'} — transaction validée (COMMIT).` }
            : null,
      },
    );
  }

  export(payload: CqExecutePayload, format: 'xlsx' | 'pdf' | 'csv', busy: WritableSignal<boolean>): void {
    const labels = { xlsx: 'Excel', pdf: 'PDF', csv: 'CSV' };
    this.feedback
      .run(() => this.api.downloadPost(`${CQ_API}/export`, { ...payload, format }), {
        loading: `Préparation de l’export ${labels[format]}…`,
        busy,
        retry: false,
        errorTitle: 'Export impossible',
        success: { title: 'Export prêt', message: `Fichier ${labels[format]} transmis au navigateur.` },
      })
      .subscribe((blob) => {
        const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `core-query-${stamp}.${format}`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
  }

  async saveFavorite(
    source: CqSource,
    data: { question?: string | null; sql?: string | null; spec?: CqBuilderSpec | null },
    suggestedName: string,
    busy: WritableSignal<boolean>,
  ): Promise<void> {
    const values = await this.dialog.prompt({
      title: 'Ajouter aux requêtes favorites',
      message: 'Donnez un nom court pour retrouver et relancer cette requête rapidement.',
      tone: 'primary',
      fields: [
        { key: 'name', label: 'Nom du favori', autocomplete: 'off' },
        { key: 'description', label: 'Description (facultatif)', autocomplete: 'off' },
      ],
      confirmLabel: 'Enregistrer',
      validate: (v) => ((v['name'] ?? '').trim().length < 2 ? 'Le nom est obligatoire (2 caractères minimum).' : null),
    });
    if (!values) return;
    this.feedback
      .run(
        () =>
          this.api.post<CqFavorite>(`${CQ_API}/favorites`, {
            name: values['name'].trim() || suggestedName,
            description: values['description']?.trim() || null,
            source,
            ...data,
          }),
        {
          loading: 'Enregistrement du favori…',
          busy,
          retry: false,
          errorTitle: 'Favori non enregistré',
          success: (f) => ({ title: 'Favori enregistré', message: `« ${f.name} » est disponible dans Requêtes favorites.` }),
        },
      )
      .subscribe();
  }

  copy(sql: string): void {
    void navigator.clipboard
      .writeText(sql)
      .then(() => this.feedback.success({ title: 'SQL copié', message: 'La requête est dans le presse-papiers.' }))
      .catch(() => this.feedback.error({ title: 'Copie impossible', message: 'Le navigateur a refusé l’accès au presse-papiers.' }));
  }
}

/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-cq-header',
  imports: [RouterLink, RouterLinkActive, CoreAdminIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="bea-admin-dash__head bea-sr-head">
      <div>
        <p class="bea-sr-head__kicker">CORE QUERY — {{ admin() ? 'mode administrateur' : 'lecture seule' }}</p>
        <h1>{{ title() }}</h1>
        <p>{{ subtitle() }}</p>
      </div>
      <ng-content />
    </header>
    <nav class="bea-sr-tabs" aria-label="CORE QUERY">
      @for (t of tabs; track t.path) {
        <a class="bea-sr-tabs__item" [routerLink]="t.path" routerLinkActive="bea-sr-tabs__item--on" [routerLinkActiveOptions]="{ exact: true }">
          <bea-admin-icon [name]="t.icon" />
          {{ t.label }}
        </a>
      }
    </nav>
  `,
})
export class CqHeaderComponent {
  readonly title = input.required<string>();
  readonly subtitle = input<string>('');
  readonly admin = input(false);
  readonly tabs = CQ_TABS;
}

@Component({
  selector: 'bea-cq-sql-view',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<pre class="bea-cq-sql" aria-label="Requête SQL"><code>@for (t of tokens(); track $index) {<span [class]="'bea-cq-sql__' + t.k">{{ t.v }}</span>}</code></pre>`,
})
export class CqSqlViewComponent {
  readonly sql = input.required<string>();
  readonly tokens = computed(() => cqTokenizeSql(this.sql()));
}

@Component({
  selector: 'bea-cq-sql-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-cq-editor" [style.min-height.rem]="rows() * 1.45">
      <pre class="bea-cq-sql bea-cq-editor__hl" aria-hidden="true" #hl><code>@for (t of tokens(); track $index) {<span [class]="'bea-cq-sql__' + t.k">{{ t.v }}</span>}<span> </span></code></pre>
      <textarea
        #area
        class="bea-cq-editor__input"
        spellcheck="false"
        autocomplete="off"
        [attr.aria-label]="label()"
        [placeholder]="placeholder()"
        [value]="value()"
        (input)="value.set($any($event.target).value)"
        (scroll)="sync()"
        (keydown)="onKey($event)"
      ></textarea>
    </div>
  `,
})
export class CqSqlEditorComponent {
  readonly value = model<string>('');
  readonly label = input('Éditeur SQL');
  readonly placeholder = input('SELECT … FROM … WHERE …');
  readonly rows = input(14);
  readonly run = output<void>();
  readonly tokens = computed(() => cqTokenizeSql(this.value()));
  private readonly area = viewChild<ElementRef<HTMLTextAreaElement>>('area');
  private readonly hl = viewChild<ElementRef<HTMLPreElement>>('hl');

  constructor() {
    effect(() => {
      this.value();
      queueMicrotask(() => this.sync());
    });
  }

  sync(): void {
    const a = this.area()?.nativeElement;
    const h = this.hl()?.nativeElement;
    if (a && h) {
      h.scrollTop = a.scrollTop;
      h.scrollLeft = a.scrollLeft;
    }
  }

  insert(text: string): void {
    const a = this.area()?.nativeElement;
    if (!a) {
      this.value.set(this.value() + text);
      return;
    }
    const start = a.selectionStart;
    const end = a.selectionEnd;
    const next = a.value.slice(0, start) + text + a.value.slice(end);
    this.value.set(next);
    queueMicrotask(() => {
      a.focus();
      a.selectionStart = a.selectionEnd = start + text.length;
    });
  }

  onKey(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      this.run.emit();
      return;
    }
    if (event.key === 'Tab' && !event.shiftKey) {
      event.preventDefault();
      this.insert('  ');
    }
  }
}

@Component({
  selector: 'bea-cq-steps',
  imports: [CoreAdminIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ol class="bea-cq-steps" aria-label="Contrôles de sécurité">
      @for (s of steps(); track s.key) {
        <li [attr.data-status]="s.status">
          <bea-admin-icon [name]="s.status === 'ok' ? 'check_circle' : s.status === 'failed' ? 'cancel' : 'radio_button_unchecked'" />
          {{ s.label }}
        </li>
      }
    </ol>
  `,
})
export class CqStepsComponent {
  readonly steps = input.required<CqStep[]>();
}

@Component({
  selector: 'bea-cq-failure',
  imports: [CoreAdminIconComponent, CqStepsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-panel bea-cq-failure" role="alert">
      <h2>
        <bea-admin-icon [name]="refused() ? 'block' : 'error'" />
        {{ refused() ? 'Requête refusée' : 'Erreur d’exécution' }}
      </h2>
      <p class="bea-cq-failure__msg">{{ failure().message }}</p>
      <p class="bea-cq-failure__meta">{{ meta() }}</p>
      @if (failure().steps.length) {
        <bea-cq-steps [steps]="failure().steps" />
      }
    </section>
  `,
})
export class CqFailureComponent {
  readonly failure = input.required<CqFailure>();
  readonly refused = computed(() => this.failure().code === 'QUERY_REFUSED');
  readonly meta = computed(() => {
    const f = this.failure();
    const parts = [`Motif : ${f.reason}`];
    if (f.requestId) parts.push(`Référence : ${f.requestId}`);
    parts.push('La tentative est tracée dans l’historique et l’audit.');
    return parts.join(' · ');
  });
}

/* ------------------------------------------------------------------ */
/* Résultats                                                           */
/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-cq-results',
  imports: [DatePipe, DecimalPipe, CoreAdminIconComponent, CqStepsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let r = result();
    <section class="bea-admin-panel bea-cq-results">
      <div class="bea-cq-results__head">
        <div>
          <h2>Résultats</h2>
          <p class="bea-cq-results__meta">{{ summary() }}</p>
        </div>
        @if (perms.export() && !r.is_write && r.columns.length) {
          <div class="bea-cq-results__exports">
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="exporting()" (click)="exportAs('xlsx')">
              <bea-admin-icon name="table_view" /> Excel
            </button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="exporting()" (click)="exportAs('pdf')">
              <bea-admin-icon name="picture_as_pdf" /> PDF
            </button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="exporting()" (click)="exportAs('csv')">
              <bea-admin-icon name="description" /> CSV
            </button>
          </div>
        }
      </div>
      <bea-cq-steps [steps]="r.steps" />
      @if (r.admin_mode) {
        <p class="bea-cq-note" [attr.data-tone]="r.committed ? (r.is_write ? 'danger' : 'ok') : 'warn'">
          <bea-admin-icon [name]="r.committed ? 'task_alt' : 'undo'" />
          {{ adminNote() }}
        </p>
      }
      @if (r.truncated) {
        <p class="bea-cq-note" data-tone="warn">
          <bea-admin-icon name="info" />
          {{ truncatedNote() }}
        </p>
      }
      @if (!r.columns.length) {
        <p class="bea-admin-panel__empty">Commande exécutée sans résultat tabulaire.</p>
      } @else if (!r.rows.length) {
        <p class="bea-admin-panel__empty">Aucune ligne ne correspond à cette requête.</p>
      } @else {
        <div class="bea-cq-results__toolbar">
          <label class="bea-admin-field bea-cq-results__search">
            <span>Rechercher dans les résultats</span>
            <input type="search" [value]="search()" (input)="setSearch($any($event.target).value)" placeholder="Filtrer les lignes affichées" />
          </label>
          <label class="bea-admin-field">
            <span>Lignes par page</span>
            <select [value]="pageSize()" (change)="setPageSize(+$any($event.target).value)">
              @for (n of [25, 50, 100, 250]; track n) {
                <option [value]="n">{{ n }}</option>
              }
            </select>
          </label>
        </div>
        <div class="bea-admin-table-wrap bea-cq-results__wrap">
          <table class="bea-admin-table bea-sr-plain bea-cq-table">
            <thead>
              <tr>
                @for (c of r.columns; track $index) {
                  <th [attr.aria-sort]="sortCol() === $index ? (sortDir() === 'asc' ? 'ascending' : 'descending') : null">
                    <button type="button" class="bea-cq-table__sort" (click)="toggleSort($index)" [title]="'Trier par ' + c.name">
                      {{ c.name }}
                      @if (sortCol() === $index) {
                        <bea-admin-icon [name]="sortDir() === 'asc' ? 'arrow_upward' : 'arrow_downward'" />
                      }
                    </button>
                  </th>
                }
              </tr>
            </thead>
            <tbody>
              @for (row of pageRows(); track $index) {
                <tr>
                  @for (c of r.columns; track $index; let ci = $index) {
                    @let v = row[ci];
                    <td [attr.data-kind]="c.kind">
                      @if (v === null || v === undefined) {
                        <span class="bea-cq-null">—</span>
                      } @else if (c.kind === 'datetime') {
                        {{ $any(v) | date: 'dd/MM/yyyy HH:mm:ss' : tz }}
                      } @else if (c.kind === 'date') {
                        {{ $any(v) | date: 'dd/MM/yyyy' }}
                      } @else if (c.kind === 'number') {
                        {{ $any(v) | number: '1.0-2' : 'fr' }}
                      } @else if (c.kind === 'boolean') {
                        {{ v ? 'Oui' : 'Non' }}
                      } @else if (c.kind === 'json') {
                        <code>{{ json(v) }}</code>
                      } @else {
                        {{ v }}
                      }
                    </td>
                  }
                </tr>
              }
            </tbody>
          </table>
        </div>
        <div class="bea-admin-pager">
          <span>{{ pagerLabel() }}</span>
          <div>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="page.set(page() - 1)">Précédent</button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages()" (click)="page.set(page() + 1)">Suivant</button>
          </div>
        </div>
      }
      <p class="bea-cq-results__foot">Exécutée le {{ r.executed_at | date: 'dd/MM/yyyy à HH:mm:ss' : tz }}</p>
    </section>
  `,
})
export class CqResultsComponent {
  private readonly ws = inject(CqWorkspaceService);
  readonly perms = cqPermissions();
  readonly result = input.required<CqResult>();
  readonly payload = input.required<CqExecutePayload>();
  readonly tz = TZ;

  readonly search = signal('');
  readonly sortCol = signal<number | null>(null);
  readonly sortDir = signal<'asc' | 'desc'>('asc');
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly exporting = signal(false);

  constructor() {
    effect(() => {
      this.result();
      this.page.set(1);
      this.sortCol.set(null);
      this.search.set('');
    });
  }

  readonly filtered = computed(() => {
    const rows = this.result().rows;
    const q = this.search().trim().toLowerCase();
    let out = q ? rows.filter((r) => r.some((v) => v != null && String(typeof v === 'object' ? JSON.stringify(v) : v).toLowerCase().includes(q))) : rows;
    const col = this.sortCol();
    if (col !== null) {
      const dir = this.sortDir() === 'asc' ? 1 : -1;
      out = [...out].sort((a, b) => {
        const x = a[col];
        const y = b[col];
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        if (typeof x === 'number' && typeof y === 'number') return (x - y) * dir;
        return String(x).localeCompare(String(y), 'fr', { numeric: true }) * dir;
      });
    }
    return out;
  });
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.filtered().length / this.pageSize())));
  readonly pageRows = computed(() => {
    const start = (this.page() - 1) * this.pageSize();
    return this.filtered().slice(start, start + this.pageSize());
  });

  readonly summary = computed(() => {
    const r = this.result();
    if (r.admin_mode) {
      return `${r.command_tag ?? 'Commande exécutée'} · ${cqDuration(r.duration_ms)} · mode administrateur`;
    }
    const role = r.read_only_role ? 'rôle lecture seule' : 'transaction lecture seule';
    return `${r.total.toLocaleString('fr-FR')} ligne(s) au total · ${cqDuration(r.duration_ms)} · ${role}`;
  });
  readonly adminNote = computed(() => {
    const r = this.result();
    const affected = r.affected_rows != null ? ` — ${r.affected_rows.toLocaleString('fr-FR')} ligne(s) concernée(s)` : '';
    if (!r.committed) return `Simulation : la transaction a été annulée (ROLLBACK), aucune donnée n’a été modifiée${affected}.`;
    return r.is_write
      ? `Transaction validée (COMMIT) : modification enregistrée en base${affected}. Tracée dans l’historique et l’audit avec son motif.`
      : `Lecture exécutée en mode administrateur (sans filtre de colonnes)${affected}.`;
  });
  readonly truncatedNote = computed(() => {
    const r = this.result();
    if (r.admin_mode) {
      return `Affichage limité aux ${r.returned.toLocaleString('fr-FR')} premières lignes. Ajoutez une limite ou des filtres pour cibler le résultat.`;
    }
    return `Affichage limité aux ${r.returned.toLocaleString('fr-FR')} premières lignes sur ${r.total.toLocaleString('fr-FR')}. Affinez la requête ou exportez (jusqu’à 20 000 lignes).`;
  });
  readonly pagerLabel = computed(() => {
    const n = this.filtered().length;
    const shown = this.search().trim() ? ` (filtrées sur ${this.result().rows.length})` : '';
    return `Page ${this.page()} / ${this.totalPages()} — ${n.toLocaleString('fr-FR')} ligne(s)${shown}`;
  });

  setSearch(v: string): void {
    this.search.set(v);
    this.page.set(1);
  }

  setPageSize(n: number): void {
    this.pageSize.set(n);
    this.page.set(1);
  }

  toggleSort(i: number): void {
    if (this.sortCol() === i) this.sortDir.set(this.sortDir() === 'asc' ? 'desc' : 'asc');
    else {
      this.sortCol.set(i);
      this.sortDir.set('asc');
    }
    this.page.set(1);
  }

  json(v: unknown): string {
    return JSON.stringify(v);
  }

  exportAs(format: 'xlsx' | 'pdf' | 'csv'): void {
    this.ws.export(this.payload(), format, this.exporting);
  }
}
