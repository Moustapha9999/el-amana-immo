import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CoreAdminPermissionPage,
  CoreAdminPermissionRow,
  CoreAdminRbacKpis,
  coreAdminRbacError,
} from './core-admin-rbac.models';

@Component({
  selector: 'bea-core-admin-permissions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Permissions</h1>
          <p>Codes <code>{{ '{' }}module{{ '}' }}.{{ '{' }}action{{ '}' }}</code>. <code>{{ '{' }}module{{ '}' }}.admin</code> couvre <code>{{ '{' }}module{{ '}' }}.*</code>.</p>
        </div>
        <a class="bea-admin-btn" routerLink="/admin/permissions/nouveau">Nouvelle permission</a>
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
          <input type="search" formControlName="search" placeholder="Code, libellé, module…" />
        </label>
        <label class="bea-admin-field">
          <span>Module</span>
          <select formControlName="module">
            <option value="tous">Tous</option>
            @for (mod of modules(); track mod) {
              <option [value]="mod">{{ mod }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Type</span>
          <select formControlName="kind">
            <option value="tous">Tous</option>
            <option value="systeme">Catalogue</option>
            <option value="custom">Personnalisées</option>
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
        <p class="bea-admin-dash__loading">Chargement des permissions…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-users__list">
          <div class="bea-admin-users__list-head">
            <h2>Liste des permissions</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          @if (rows().length === 0) {
            <p class="bea-admin-panel__empty">Aucune permission pour ces critères.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Libellé</th>
                    <th>Module</th>
                    <th>Rôles</th>
                    <th>Type</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        <a class="bea-admin-table__link" [routerLink]="['/admin/permissions', row.id]">
                          <code>{{ row.code }}</code>
                        </a>
                        @if (row.locked) {
                          <span class="bea-admin-pill">Catalogue</span>
                        }
                      </td>
                      <td>{{ row.label }}</td>
                      <td>{{ row.module }}</td>
                      <td>{{ row.roles_count }}</td>
                      <td>
                        <span
                          class="bea-badge"
                          [class.bea-badge--actif]="row.locked"
                          [class.bea-badge--bientot]="!row.locked"
                        >
                          {{ kindLabel(row) }}
                        </span>
                      </td>
                      <td class="bea-admin-table__actions">
                        <div class="bea-admin-row-actions">
                          <a
                            class="bea-admin-icon-btn"
                            [routerLink]="['/admin/permissions', row.id]"
                            title="Voir"
                            aria-label="Voir"
                          >
                            <bea-admin-icon name="visibility" />
                          </a>
                          <a
                            class="bea-admin-icon-btn"
                            [routerLink]="['/admin/permissions', row.id, 'modifier']"
                            title="Éditer"
                            aria-label="Éditer"
                          >
                            <bea-admin-icon name="edit" />
                          </a>
                          @if (!row.locked) {
                            <button
                              type="button"
                              class="bea-admin-icon-btn bea-admin-icon-btn--danger"
                              [disabled]="saving()"
                              (click)="askDelete(row)"
                              title="Supprimer"
                              aria-label="Supprimer"
                            >
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
            <div class="bea-admin-pager">
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} permission(s)</span>
              <div>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="go(page() - 1)">
                  Précédent
                </button>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages()" (click)="go(page() + 1)">
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
export class CoreAdminPermissionsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<CoreAdminPermissionRow[]>([]);
  readonly modules = signal<string[]>([]);
  readonly kpis = signal<CoreAdminRbacKpis | null>(null);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly size = 20;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly filters = this.fb.nonNullable.group({ search: '', kind: 'tous', module: 'tous' });

  ngOnInit(): void {
    this.api.get<{ modules: string[] }>('/plateforme/admin/permissions/options').subscribe({
      next: (res) => this.modules.set(res.modules ?? []),
      error: () => this.modules.set([]),
    });
    this.load();
  }

  kindLabel(row: CoreAdminPermissionRow): string {
    return row.locked ? 'Catalogue' : 'Personnalisée';
  }

  kpiCards(k: CoreAdminRbacKpis) {
    const kind = this.filters.controls.kind.value;
    return [
      { key: 'tous', label: 'Total', value: this.fmt(k.total), icon: 'vpn_key', tone: 'modules', on: kind === 'tous' },
      { key: 'systeme', label: 'Catalogue', value: this.fmt(k.systeme), icon: 'security', tone: 'org', on: kind === 'systeme' },
      { key: 'custom', label: 'Personnalisées', value: this.fmt(k.custom), icon: 'tune', tone: 'sessions', on: kind === 'custom' },
      {
        key: 'unused',
        label: 'Sans rôle',
        value: this.fmt(k.unused ?? 0),
        icon: 'warning',
        tone: 'alert',
        on: false,
      },
    ];
  }

  applyKpi(key: string): void {
    if (key === 'unused') {
      return;
    }
    this.filters.patchValue({
      search: this.filters.controls.search.value,
      module: this.filters.controls.module.value,
      kind: key,
    });
    this.search();
  }

  search(): void {
    this.page.set(1);
    this.load();
  }

  resetFilters(): void {
    this.filters.reset({ search: '', kind: 'tous', module: 'tous' });
    this.search();
  }

  go(page: number): void {
    if (page < 1 || page > this.totalPages() || page === this.page()) {
      return;
    }
    this.page.set(page);
    this.load();
  }

  async askDelete(row: CoreAdminPermissionRow): Promise<void> {
    if (this.saving()) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer la permission « ${row.code} » ? Impossible si un rôle la porte encore.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.api.delete(`/plateforme/admin/permissions/${row.id}`).subscribe({
      next: () => {
        this.saving.set(false);
        this.load();
        void this.dialogs.success(`« ${row.code} » a été supprimée.`, 'Suppression effectuée');
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminRbacError(err, 'Suppression impossible.'));
      },
    });
  }

  private fmt(n: number): string {
    return new Intl.NumberFormat('fr-FR').format(n);
  }

  private load(): void {
    this.loading.set(true);
    this.erreur.set(null);
    const value = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.size,
      kind: value.kind,
    };
    if (value.search.trim()) {
      params['search'] = value.search.trim();
    }
    if (value.module !== 'tous') {
      params['module'] = value.module;
    }
    this.api.get<CoreAdminPermissionPage>('/plateforme/admin/permissions', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.kpis.set(res.kpis);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.rows.set([]);
        this.erreur.set(coreAdminRbacError(err, 'Impossible de charger les permissions.'));
      },
    });
  }
}
