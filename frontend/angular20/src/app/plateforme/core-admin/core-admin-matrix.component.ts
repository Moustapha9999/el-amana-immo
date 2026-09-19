import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import {
  CoreAdminMatrixKpis,
  CoreAdminMatrixRead,
  CoreAdminPermissionSummary,
  CoreAdminRoleSummary,
  coreAdminRbacError,
} from './core-admin-rbac.models';
import { CoreAdminIconComponent } from './core-admin-icon.component';

@Component({
  selector: 'bea-core-admin-matrix',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Matrice d’accès</h1>
          <p>
            Grants effectifs <code>role_permissions</code> — lecture base uniquement. Cases figées :
            <code>administrateur</code> immo ne reçoit pas <code>core.admin.*</code>.
          </p>
        </div>
        <div class="bea-admin-users__head-actions">
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/roles">Rôles</a>
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/permissions">Permissions</a>
        </div>
      </header>

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of kpiCards(k); track card.key; let i = $index) {
            <div class="bea-admin-kpi" [attr.data-tone]="card.tone" [style.animation-delay]="i * 60 + 'ms'">
              <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="card.icon" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">{{ card.label }}</p>
                <p class="bea-admin-kpi__value">{{ card.value }}</p>
              </div>
            </div>
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
        <p class="bea-admin-dash__loading">Chargement de la matrice…</p>
      } @else if (roles().length === 0 || permissions().length === 0) {
        <p class="bea-admin-panel__empty">Aucun rôle ou permission pour ces critères.</p>
      } @else {
        <div class="bea-admin-panel bea-admin-matrix">
          <div class="bea-admin-users__list-head">
            <h2>Rôles × permissions</h2>
            <p>{{ permissions().length }} permission(s) × {{ roles().length }} rôle(s).</p>
          </div>
          <div class="bea-admin-table-wrap bea-admin-matrix__wrap">
            <table class="bea-admin-table bea-admin-matrix__table">
              <colgroup>
                <col class="bea-admin-matrix__col-perm" />
                @for (role of roles(); track role.id) {
                  <col class="bea-admin-matrix__col-role" />
                }
              </colgroup>
              <thead>
                <tr>
                  <th class="bea-admin-matrix__sticky">Permission</th>
                  @for (role of roles(); track role.id) {
                    <th
                      class="bea-admin-matrix__role-head"
                      [title]="role.code + (role.locked ? ' (système)' : '')"
                    >
                      <span class="bea-admin-matrix__role">{{ role.label }}</span>
                    </th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (group of permissionGroups(); track group.module) {
                  <tr class="bea-admin-matrix__module">
                    <td class="bea-admin-matrix__sticky">Module {{ group.module }}</td>
                    @for (role of roles(); track role.id) {
                      <td class="bea-admin-matrix__module-fill" aria-hidden="true"></td>
                    }
                  </tr>
                  @for (perm of group.items; track perm.id) {
                    <tr>
                      <th scope="row" class="bea-admin-matrix__sticky bea-admin-matrix__perm">
                        <code>{{ perm.code }}</code>
                        <span>{{ perm.label }}</span>
                      </th>
                      @for (role of roles(); track role.id) {
                        <td class="bea-admin-matrix__cell">
                          <label class="bea-admin-matrix__check">
                            <input
                              type="checkbox"
                              [checked]="isGranted(role.id, perm.code)"
                              [disabled]="isBlocked(role, perm) || busyKey() === cellKey(role.id, perm.code)"
                              (change)="toggle(role, perm, isChecked($event))"
                            />
                            <span class="bea-admin-sr">
                              {{ role.label }} — {{ perm.code }}
                            </span>
                          </label>
                        </td>
                      }
                    </tr>
                  }
                }
              </tbody>
            </table>
          </div>
        </div>
      }
    </section>
  `,
})
export class CoreAdminMatrixComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly roles = signal<CoreAdminRoleSummary[]>([]);
  readonly permissions = signal<CoreAdminPermissionSummary[]>([]);
  readonly grants = signal<Record<string, Set<string>>>({});
  readonly modules = signal<string[]>([]);
  readonly kpis = signal<CoreAdminMatrixKpis | null>(null);
  readonly busyKey = signal<string | null>(null);

  readonly filters = this.fb.nonNullable.group({
    search: '',
    module: 'tous',
  });

  readonly permissionGroups = computed(() => {
    const map = new Map<string, CoreAdminPermissionSummary[]>();
    for (const perm of this.permissions()) {
      const list = map.get(perm.module) ?? [];
      list.push(perm);
      map.set(perm.module, list);
    }
    return [...map.entries()].map(([module, items]) => ({ module, items }));
  });

  ngOnInit(): void {
    this.reload();
  }

  kpiCards(k: CoreAdminMatrixKpis) {
    return [
      { key: 'roles', label: 'Rôles', value: k.roles, icon: 'badge', tone: 'blue' },
      { key: 'permissions', label: 'Permissions', value: k.permissions, icon: 'vpn_key', tone: 'green' },
      { key: 'grants', label: 'Grants', value: k.grants, icon: 'grid_view', tone: 'teal' },
      { key: 'modules', label: 'Modules', value: k.modules, icon: 'apps', tone: 'amber' },
    ];
  }

  search(): void {
    this.reload();
  }

  resetFilters(): void {
    this.filters.reset({ search: '', module: 'tous' });
    this.reload();
  }

  cellKey(roleId: string, permissionCode: string): string {
    return `${roleId}:${permissionCode}`;
  }

  isGranted(roleId: string, permissionCode: string): boolean {
    return this.grants()[roleId]?.has(permissionCode) ?? false;
  }

  isBlocked(role: CoreAdminRoleSummary, perm: CoreAdminPermissionSummary): boolean {
    return role.code === 'administrateur' && perm.code.startsWith('core.admin.');
  }

  isChecked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  toggle(role: CoreAdminRoleSummary, perm: CoreAdminPermissionSummary, granted: boolean): void {
    if (this.isBlocked(role, perm)) {
      return;
    }
    const key = this.cellKey(role.id, perm.code);
    const previous = this.isGranted(role.id, perm.code);
    this.applyLocal(role.id, perm.code, granted);
    this.busyKey.set(key);
    this.erreur.set('');
    this.api.patch<unknown>('/plateforme/admin/matrix', {
      role_id: role.id,
      permission_code: perm.code,
      granted,
    }).subscribe({
      next: () => {
        this.busyKey.set(null);
        this.refreshKpis();
      },
      error: (err) => {
        this.applyLocal(role.id, perm.code, previous);
        this.busyKey.set(null);
        this.erreur.set(coreAdminRbacError(err, 'Impossible de mettre à jour le grant.'));
      },
    });
  }

  private applyLocal(roleId: string, permissionCode: string, granted: boolean): void {
    const next: Record<string, Set<string>> = { ...this.grants() };
    const set = new Set(next[roleId] ?? []);
    if (granted) {
      set.add(permissionCode);
    } else {
      set.delete(permissionCode);
    }
    next[roleId] = set;
    this.grants.set(next);
  }

  private refreshKpis(): void {
    const current = this.kpis();
    if (!current) {
      return;
    }
    let grants = 0;
    for (const set of Object.values(this.grants())) {
      grants += set.size;
    }
    this.kpis.set({ ...current, grants });
  }

  private reload(): void {
    this.loading.set(true);
    this.erreur.set('');
    const value = this.filters.getRawValue();
    const params: Record<string, string> = {};
    if (value.search.trim()) {
      params['search'] = value.search.trim();
    }
    if (value.module !== 'tous') {
      params['module'] = value.module;
    }
    this.api.get<CoreAdminMatrixRead>('/plateforme/admin/matrix', params).subscribe({
      next: (data) => {
        this.roles.set(data.roles ?? []);
        this.permissions.set(data.permissions ?? []);
        this.modules.set(
          [...new Set([...this.modules(), ...(data.modules ?? [])])].sort((a, b) => a.localeCompare(b)),
        );
        this.kpis.set(data.kpis ?? null);
        const grants: Record<string, Set<string>> = {};
        for (const [roleId, codes] of Object.entries(data.grants ?? {})) {
          grants[roleId] = new Set(codes);
        }
        this.grants.set(grants);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminRbacError(err, 'Impossible de charger la matrice.'));
      },
    });
  }
}
