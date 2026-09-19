import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CoreAdminAuditKpis,
  CoreAdminAuditPage,
  CoreAdminAuditRow,
  coreAdminAuditActionLabel,
  coreAdminAuditError,
} from './core-admin-audit.models';

@Component({
  selector: 'bea-core-admin-audit',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Audit</h1>
          <p>
            Journal <code>audit_logs</code> — Login 1, lecture seule. Distinct de l’écran Audit du module
            Immobilisations.
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

      <form class="bea-admin-toolbar bea-admin-toolbar--users" [formGroup]="filters" (ngSubmit)="search()">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input type="search" formControlName="search" placeholder="E-mail, action, entité, IP…" />
        </label>
        <label class="bea-admin-field">
          <span>Module</span>
          <select formControlName="module_code">
            <option value="tous">Tous</option>
            @for (mod of modules(); track mod) {
              <option [value]="mod">{{ mod }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Entité</span>
          <select formControlName="entity">
            <option value="tous">Toutes</option>
            @for (ent of entities(); track ent) {
              <option [value]="ent">{{ ent }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Action</span>
          <input type="text" formControlName="action" placeholder="login, update…" />
        </label>
        <label class="bea-admin-field">
          <span>Du</span>
          <input type="date" formControlName="date_debut" />
        </label>
        <label class="bea-admin-field">
          <span>Au</span>
          <input type="date" formControlName="date_fin" />
        </label>
        <div class="bea-admin-toolbar__actions">
          <button
            type="button"
            class="bea-admin-btn bea-admin-btn--refresh"
            (click)="search()"
            [disabled]="loading()"
          >
            <bea-admin-icon name="refresh" />
            Actualiser
          </button>
          <button type="submit" class="bea-admin-btn">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="resetFilters()">Réinitialiser</button>
        </div>
      </form>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement de l’audit…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-users__list">
          <div class="bea-admin-users__list-head">
            <h2>Journal</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          @if (rows().length === 0) {
            <p class="bea-admin-panel__empty">Aucune entrée pour ces critères.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Quand</th>
                    <th>Qui</th>
                    <th>Action</th>
                    <th>Entité</th>
                    <th>Module</th>
                    <th>IP</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        @if (row.created_at) {
                          {{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                        } @else {
                          —
                        }
                      </td>
                      <td>
                        @if (row.user_id) {
                          <a class="bea-admin-table__link" [routerLink]="['/admin/users', row.user_id]">
                            {{ row.user_full_name || row.user_email || 'Utilisateur' }}
                          </a>
                          @if (row.user_email) {
                            <div class="bea-admin-sessions__meta">{{ row.user_email }}</div>
                          }
                        } @else {
                          Système
                        }
                      </td>
                      <td>{{ actionLabel(row.action) }}</td>
                      <td class="bea-admin-table__clip" [title]="entityTitle(row)">
                        {{ row.entity }}{{ row.entity_id ? ' · ' + row.entity_id : '' }}
                      </td>
                      <td>{{ row.module_code || '—' }}</td>
                      <td><code>{{ row.ip_address || '—' }}</code></td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="bea-admin-pager">
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} entrée(s)</span>
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
export class CoreAdminAuditComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly rows = signal<CoreAdminAuditRow[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = signal(20);
  readonly kpis = signal<CoreAdminAuditKpis | null>(null);
  readonly modules = signal<string[]>([]);
  readonly entities = signal<string[]>([]);
  readonly kpiFilter = signal<string | null>(null);

  readonly filters = this.fb.nonNullable.group({
    search: '',
    module_code: 'tous',
    entity: 'tous',
    action: '',
    date_debut: '',
    date_fin: '',
  });

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size())));

  ngOnInit(): void {
    this.reload();
  }

  actionLabel = coreAdminAuditActionLabel;

  entityTitle(row: CoreAdminAuditRow): string {
    return row.entity_id ? `${row.entity} · ${row.entity_id}` : row.entity;
  }

  kpiCards(k: CoreAdminAuditKpis) {
    const on = this.kpiFilter();
    return [
      { key: 'aujourd_hui', label: 'Aujourd’hui', value: k.aujourd_hui, icon: 'today', tone: 'blue', on: on === 'aujourd_hui' },
      { key: 'logins', label: 'Connexions', value: k.logins, icon: 'login', tone: 'teal', on: on === 'logins' },
      { key: 'mutations', label: 'Mutations', value: k.mutations, icon: 'edit', tone: 'amber', on: on === 'mutations' },
      { key: 'core', label: 'CORE', value: k.core, icon: 'policy', tone: 'green', on: on === 'core' },
      { key: 'tous', label: 'Total', value: k.total, icon: 'history', tone: 'rose', on: on === 'tous' },
    ];
  }

  applyKpi(key: string): void {
    this.kpiFilter.set(key);
    this.filters.patchValue({
      search: '',
      module_code: 'tous',
      entity: 'tous',
      action: '',
      date_debut: '',
      date_fin: '',
    });
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
    this.filters.reset({
      search: '',
      module_code: 'tous',
      entity: 'tous',
      action: '',
      date_debut: '',
      date_fin: '',
    });
    this.page.set(1);
    this.reload();
  }

  go(page: number): void {
    this.page.set(page);
    this.reload();
  }

  private reload(): void {
    this.loading.set(true);
    this.erreur.set('');
    const value = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.size(),
    };
    const kind = this.kpiFilter();
    if (kind && kind !== 'tous') {
      params['kind'] = kind;
    }
    if (value.search.trim()) {
      params['search'] = value.search.trim();
    }
    if (value.module_code !== 'tous') {
      params['module_code'] = value.module_code;
    }
    if (value.entity !== 'tous') {
      params['entity'] = value.entity;
    }
    if (value.action.trim()) {
      params['action'] = value.action.trim();
    }
    if (value.date_debut) {
      params['date_debut'] = value.date_debut;
    }
    if (value.date_fin) {
      params['date_fin'] = value.date_fin;
    }
    this.api.get<CoreAdminAuditPage>('/plateforme/admin/audit', params).subscribe({
      next: (data) => {
        this.rows.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.page.set(data.page ?? 1);
        this.kpis.set(data.kpis ?? null);
        this.modules.set(
          [...new Set([...this.modules(), ...(data.modules ?? [])])].sort((a, b) => a.localeCompare(b)),
        );
        this.entities.set(
          [...new Set([...this.entities(), ...(data.entities ?? [])])].sort((a, b) => a.localeCompare(b)),
        );
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminAuditError(err, 'Impossible de charger l’audit.'));
      },
    });
  }
}
