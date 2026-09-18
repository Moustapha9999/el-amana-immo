import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CoreAdminSessionKpis,
  CoreAdminSessionPage,
  CoreAdminSessionRow,
  coreAdminSessionsError,
  sessionKindLabel,
  sessionStatusLabel,
} from './core-admin-sessions.models';

@Component({
  selector: 'bea-core-admin-sessions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Sessions</h1>
          <p>
            Sessions JWT révocables — Login 1 (<code>platform</code>) et Login 2 (<code>module</code>). La session
            courante ne peut pas être révoquée ici.
          </p>
        </div>
      </header>

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of kpiCards(k); track card.key; let i = $index) {
            <button
              type="button"
              class="bea-admin-kpi bea-admin-kpi--link"
              [attr.data-tone]="card.tone"
              [class.bea-admin-kpi--on]="card.on"
              [style.animation-delay]="i * 60 + 'ms'"
              (click)="applyKpi(card.key)"
            >
              <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="card.icon" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">{{ card.label }}</p>
                <p class="bea-admin-kpi__value">{{ card.value }}</p>
              </div>
            </button>
          }
        </div>
      }

      <form class="bea-admin-toolbar" [formGroup]="filters" (ngSubmit)="search()">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input type="search" formControlName="search" placeholder="Nom, e-mail, IP, module, agent…" />
        </label>
        <label class="bea-admin-field">
          <span>Type</span>
          <select formControlName="kind">
            <option value="tous">Tous</option>
            <option value="platform">BEA DIGITAL</option>
            <option value="module">Module</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Statut</span>
          <select formControlName="status">
            <option value="actives">Actives</option>
            <option value="expirees">Expirées</option>
            <option value="revoquees">Révoquées</option>
            <option value="tous">Tous</option>
          </select>
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="submit" class="bea-admin-btn">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="resetFilters()">Réinitialiser</button>
        </div>
      </form>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement des sessions…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-users__list">
          <div class="bea-admin-users__list-head">
            <h2>Liste des sessions</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          @if (rows().length === 0) {
            <p class="bea-admin-panel__empty">Aucune session pour ces critères.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Utilisateur</th>
                    <th>Type</th>
                    <th>Module</th>
                    <th>IP</th>
                    <th>Créée</th>
                    <th>Expire</th>
                    <th>Statut</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr [class.bea-admin-sessions__current]="row.is_current">
                      <td>
                        <a class="bea-admin-table__link" [routerLink]="['/admin/users', row.user_id]">
                          {{ row.user_full_name || row.user_email }}
                        </a>
                        <div class="bea-admin-sessions__meta">{{ row.user_email }}</div>
                        @if (row.is_current) {
                          <span class="bea-admin-pill">Courante</span>
                        }
                      </td>
                      <td>{{ kindLabel(row.kind) }}</td>
                      <td>{{ row.module_code || '—' }}</td>
                      <td><code>{{ row.ip_address || '—' }}</code></td>
                      <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>{{ row.expires_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>
                        <span
                          class="bea-badge"
                          [class.bea-badge--actif]="row.active"
                          [class.bea-badge--bientot]="!row.active && !row.revoked_at"
                          [class.bea-badge--inactif]="!!row.revoked_at"
                        >
                          {{ statusLabel(row) }}
                        </span>
                      </td>
                      <td class="bea-admin-table__actions">
                        <div class="bea-admin-row-actions">
                          <a
                            class="bea-admin-icon-btn"
                            [routerLink]="['/admin/users', row.user_id]"
                            title="Fiche utilisateur"
                            aria-label="Fiche utilisateur"
                          >
                            <bea-admin-icon name="visibility" />
                          </a>
                          <button
                            type="button"
                            class="bea-admin-icon-btn bea-admin-icon-btn--danger"
                            [disabled]="!row.active || row.is_current || saving()"
                            (click)="askRevoke(row)"
                            title="Révoquer"
                            aria-label="Révoquer"
                          >
                            <bea-admin-icon name="block" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="bea-admin-pager">
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} session(s)</span>
              <div>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="go(page() - 1)">
                  Précédent
                </button>
                <button
                  type="button"
                  class="bea-admin-btn bea-admin-btn--ghost"
                  [disabled]="page() >= totalPages()"
                  (click)="go(page() + 1)"
                >
                  Suivant
                </button>
              </div>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class CoreAdminSessionsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(BeaAdminDialogService);

  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly erreur = signal('');
  readonly rows = signal<CoreAdminSessionRow[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = signal(20);
  readonly kpis = signal<CoreAdminSessionKpis | null>(null);
  readonly kpiFilter = signal<string | null>(null);

  readonly filters = this.fb.nonNullable.group({
    search: '',
    kind: 'tous',
    status: 'actives',
  });

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size())));

  ngOnInit(): void {
    this.reload();
  }

  kindLabel = sessionKindLabel;
  statusLabel = sessionStatusLabel;

  kpiCards(k: CoreAdminSessionKpis) {
    const on = this.kpiFilter();
    return [
      { key: 'actives', label: 'Actives', value: k.actives, icon: 'devices', tone: 'blue', on: on === 'actives' },
      { key: 'platform', label: 'BEA DIGITAL', value: k.platform, icon: 'language', tone: 'teal', on: on === 'platform' },
      { key: 'module', label: 'Module', value: k.module, icon: 'apps', tone: 'green', on: on === 'module' },
      { key: 'expirees', label: 'Expirées', value: k.expirees, icon: 'schedule', tone: 'amber', on: on === 'expirees' },
      { key: 'revoquees', label: 'Révoquées', value: k.revoquees, icon: 'block', tone: 'rose', on: on === 'revoquees' },
    ];
  }

  applyKpi(key: string): void {
    this.kpiFilter.set(key);
    if (key === 'platform' || key === 'module') {
      this.filters.patchValue({ kind: key, status: 'actives' });
    } else if (key === 'actives' || key === 'expirees' || key === 'revoquees') {
      this.filters.patchValue({ kind: 'tous', status: key });
    }
    this.page.set(1);
    this.reload();
  }

  search(): void {
    this.kpiFilter.set(null);
    this.page.set(1);
    this.reload();
  }

  resetFilters(): void {
    this.kpiFilter.set(null);
    this.filters.reset({ search: '', kind: 'tous', status: 'actives' });
    this.page.set(1);
    this.reload();
  }

  go(page: number): void {
    this.page.set(page);
    this.reload();
  }

  async askRevoke(row: CoreAdminSessionRow): Promise<void> {
    if (!row.active || row.is_current) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: 'Révoquer la session',
      message: `Révoquer la session ${this.kindLabel(row.kind)} de ${row.user_full_name || row.user_email} ? Les jetons associés cesseront immédiatement.`,
      tone: 'danger',
      confirmLabel: 'Révoquer',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    this.api.post<CoreAdminSessionRow>(`/plateforme/admin/sessions/${row.id}/revoke`, {}).subscribe({
      next: async () => {
        this.saving.set(false);
        await this.dialogs.success('Session révoquée.');
        this.reload();
      },
      error: async (err) => {
        this.saving.set(false);
        this.erreur.set(coreAdminSessionsError(err, 'Impossible de révoquer la session.'));
        await this.dialogs.error(this.erreur());
      },
    });
  }

  private reload(): void {
    this.loading.set(true);
    this.erreur.set('');
    const value = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.size(),
      status: value.status,
      kind: value.kind,
    };
    if (value.search.trim()) {
      params['search'] = value.search.trim();
    }
    this.api.get<CoreAdminSessionPage>('/plateforme/admin/sessions', params).subscribe({
      next: (data) => {
        this.rows.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.page.set(data.page ?? 1);
        this.kpis.set(data.kpis ?? null);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminSessionsError(err, 'Impossible de charger les sessions.'));
      },
    });
  }
}
