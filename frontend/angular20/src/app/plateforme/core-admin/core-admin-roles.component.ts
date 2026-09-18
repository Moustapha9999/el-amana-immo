import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CoreAdminRbacKpis,
  CoreAdminRolePage,
  CoreAdminRoleRow,
  coreAdminRbacError,
  rbacKindLabel,
} from './core-admin-rbac.models';

@Component({
  selector: 'bea-core-admin-roles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Rôles</h1>
          <p>Profils d’accès BEA DIGITAL — grants via <code>role_permissions</code>, distincts de CORE ADMIN.</p>
        </div>
        <a class="bea-admin-btn" routerLink="/admin/roles/nouveau">Nouveau rôle</a>
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
          <input type="search" formControlName="search" placeholder="Code, libellé, description…" />
        </label>
        <label class="bea-admin-field">
          <span>Type</span>
          <select formControlName="kind">
            <option value="tous">Tous</option>
            <option value="systeme">Système</option>
            <option value="custom">Personnalisés</option>
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
        <p class="bea-admin-dash__loading">Chargement des rôles…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-users__list">
          <div class="bea-admin-users__list-head">
            <h2>Liste des rôles</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          @if (rows().length === 0) {
            <p class="bea-admin-panel__empty">Aucun rôle pour ces critères.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Libellé</th>
                    <th>Code</th>
                    <th>Permissions</th>
                    <th>Utilisateurs</th>
                    <th>Type</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        <a class="bea-admin-table__link" [routerLink]="['/admin/roles', row.id]">{{ row.label }}</a>
                        @if (row.locked) {
                          <span class="bea-admin-pill">Système</span>
                        }
                      </td>
                      <td><code>{{ row.code }}</code></td>
                      <td>{{ row.permissions_count }}</td>
                      <td>{{ row.users_count }}</td>
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
                          <a class="bea-admin-icon-btn" [routerLink]="['/admin/roles', row.id]" title="Voir" aria-label="Voir">
                            <bea-admin-icon name="visibility" />
                          </a>
                          <a class="bea-admin-icon-btn" [routerLink]="['/admin/roles', row.id, 'modifier']" title="Éditer" aria-label="Éditer">
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
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} rôle(s)</span>
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
export class CoreAdminRolesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<CoreAdminRoleRow[]>([]);
  readonly kpis = signal<CoreAdminRbacKpis | null>(null);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly size = 20;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly filters = this.fb.nonNullable.group({ search: '', kind: 'tous' });

  ngOnInit(): void {
    this.load();
  }

  kindLabel(row: CoreAdminRoleRow): string {
    return rbacKindLabel(row.locked);
  }

  kpiCards(k: CoreAdminRbacKpis) {
    const kind = this.filters.controls.kind.value;
    return [
      { key: 'tous', label: 'Total', value: this.fmt(k.total), icon: 'badge', tone: 'modules', on: kind === 'tous' },
      { key: 'systeme', label: 'Système', value: this.fmt(k.systeme), icon: 'security', tone: 'org', on: kind === 'systeme' },
      { key: 'custom', label: 'Personnalisés', value: this.fmt(k.custom), icon: 'tune', tone: 'sessions', on: kind === 'custom' },
      {
        key: 'with_users',
        label: 'Avec utilisateurs',
        value: this.fmt(k.with_users ?? 0),
        icon: 'group',
        tone: 'actions',
        on: false,
      },
    ];
  }

  applyKpi(key: string): void {
    if (key === 'with_users') {
      return;
    }
    this.filters.patchValue({ search: this.filters.controls.search.value, kind: key });
    this.search();
  }

  search(): void {
    this.page.set(1);
    this.load();
  }

  resetFilters(): void {
    this.filters.reset({ search: '', kind: 'tous' });
    this.search();
  }

  go(page: number): void {
    if (page < 1 || page > this.totalPages() || page === this.page()) {
      return;
    }
    this.page.set(page);
    this.load();
  }

  async askDelete(row: CoreAdminRoleRow): Promise<void> {
    if (this.saving()) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer le rôle « ${row.label} » (${row.code}) ? Impossible s’il reste des utilisateurs.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.api.delete(`/plateforme/admin/roles/${row.id}`).subscribe({
      next: () => {
        this.saving.set(false);
        this.load();
        void this.dialogs.success(`« ${row.label} » a été supprimé.`, 'Suppression effectuée');
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
    this.api.get<CoreAdminRolePage>('/plateforme/admin/roles', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.kpis.set(res.kpis);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.rows.set([]);
        this.erreur.set(coreAdminRbacError(err, 'Impossible de charger les rôles.'));
      },
    });
  }
}
