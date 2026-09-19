import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import {
  CoreAdminPermissionSummary,
  CoreAdminRoleFiche,
  CoreAdminRoleOptions,
  coreAdminRbacError,
} from './core-admin-rbac.models';

@Component({
  selector: 'bea-core-admin-role-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/roles">Rôles</a></p>
          <h1>
            @if (isCreate()) {
              Nouveau rôle
            } @else if (isView()) {
              {{ form.controls.label.value || 'Fiche rôle' }}
            } @else {
              Modifier {{ form.controls.label.value || 'le rôle' }}
            }
          </h1>
          <p>Grants effectifs lus depuis la base — pas le plancher Python.</p>
        </div>
        @if (!isCreate()) {
          <div class="bea-admin-users__head-actions">
            @if (locked()) {
              <span class="bea-admin-pill">Système</span>
            }
            @if (isView() && roleId(); as id) {
              <a class="bea-admin-btn" [routerLink]="['/admin/roles', id, 'modifier']">Éditer</a>
            }
          </div>
        }
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (locked()) {
        <p class="bea-admin-note">
          Rôle système Immobilisations : code figé, suppression impossible. Les grants restent éditables (sauf
          <code>core.admin.*</code> sur le rôle administrateur immo).
        </p>
      }

      @if (!isCreate()) {
        <div class="bea-admin-kpis">
          <article class="bea-admin-kpi" data-tone="modules">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Permissions</p>
              <p class="bea-admin-kpi__value">{{ selected().size }}</p>
              <p class="bea-admin-kpi__hint">sur {{ catalogue().length }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="org">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Modules couverts</p>
              <p class="bea-admin-kpi__value">{{ modulesCouverts() }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="actions">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Couverture</p>
              <p class="bea-admin-kpi__value">{{ couverturePct() }}%</p>
            </div>
          </article>
        </div>
      }

      <form class="bea-admin-form" [formGroup]="form" (ngSubmit)="save()">
        <section class="bea-admin-panel">
          <h2>Identité</h2>
          <div class="bea-admin-grid">
            <label class="bea-admin-field">
              <span>Code</span>
              <input type="text" formControlName="code" placeholder="ex. credit_lecteur" />
            </label>
            <label class="bea-admin-field">
              <span>Libellé</span>
              <input type="text" formControlName="label" />
            </label>
            <label class="bea-admin-field bea-admin-toolbar__search">
              <span>Description</span>
              <textarea formControlName="description" rows="3"></textarea>
            </label>
          </div>
        </section>

        <section class="bea-admin-panel">
          <h2>Permissions</h2>
          @if (permissionGroups().length === 0) {
            <p class="bea-admin-panel__empty">Aucune permission catalogue disponible.</p>
          } @else {
            <div class="bea-admin-grants">
              @for (group of permissionGroups(); track group.module) {
                <fieldset
                  class="bea-admin-grant"
                  [class.bea-admin-grant--on]="groupSelectedCount(group) > 0"
                >
                  <legend>{{ group.module }}</legend>
                  <div class="bea-admin-grant__meter">
                    <div class="bea-admin-grant__meter-track">
                      <div
                        class="bea-admin-grant__meter-fill"
                        [style.width.%]="groupSelectedPct(group)"
                      ></div>
                    </div>
                    <span class="bea-admin-grant__meter-label">
                      {{ groupSelectedCount(group) }}/{{ group.items.length }}
                    </span>
                  </div>
                  @for (perm of group.items; track perm.id) {
                    <label
                      class="bea-admin-check bea-admin-check--nested"
                      [class.bea-admin-check--on]="selected().has(perm.code)"
                    >
                      <input
                        type="checkbox"
                        [checked]="selected().has(perm.code)"
                        [disabled]="isView()"
                        (change)="togglePermission(perm.code, isChecked($event))"
                      />
                      <span><code>{{ perm.code }}</code> — {{ perm.label }}</span>
                    </label>
                  }
                </fieldset>
              }
            </div>
          }
        </section>

        <div class="bea-admin-form__actions">
          @if (!isView()) {
            <button type="submit" class="bea-admin-btn" [disabled]="saving()">
              {{ saving() ? 'Enregistrement…' : isCreate() ? 'Créer' : 'Enregistrer' }}
            </button>
          }
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/roles">Retour à la liste</a>
        </div>
      </form>

      @if (!isCreate() && !locked()) {
        <div class="bea-admin-actions">
          <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="saving()" (click)="askDelete()">
            Supprimer
          </button>
        </div>
      }
    </section>
  `,
})
export class CoreAdminRoleFicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly isCreate = signal(true);
  readonly isView = signal(false);
  readonly saving = signal(false);
  readonly locked = signal(false);
  readonly roleId = signal<string | null>(null);
  readonly catalogue = signal<CoreAdminPermissionSummary[]>([]);
  readonly selected = signal<Set<string>>(new Set());
  readonly erreur = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.minLength(2)]],
    label: ['', Validators.required],
    description: [''],
  });

  readonly permissionGroups = computed(() => {
    const map = new Map<string, CoreAdminPermissionSummary[]>();
    for (const perm of this.catalogue()) {
      const list = map.get(perm.module) ?? [];
      list.push(perm);
      map.set(perm.module, list);
    }
    return [...map.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([module, items]) => ({ module, items }));
  });

  readonly modulesCouverts = computed(() => {
    const mods = new Set<string>();
    for (const perm of this.catalogue()) {
      if (this.selected().has(perm.code)) {
        mods.add(perm.module);
      }
    }
    return mods.size;
  });

  readonly couverturePct = computed(() => {
    const total = this.catalogue().length;
    if (!total) {
      return 0;
    }
    return Math.round((this.selected().size / total) * 100);
  });

  groupSelectedCount(group: { items: CoreAdminPermissionSummary[] }): number {
    return group.items.filter((perm) => this.selected().has(perm.code)).length;
  }

  groupSelectedPct(group: { items: CoreAdminPermissionSummary[] }): number {
    if (!group.items.length) {
      return 0;
    }
    return Math.round((this.groupSelectedCount(group) / group.items.length) * 100);
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const url = this.router.url;
    this.isCreate.set(!id);
    this.isView.set(!!id && !url.includes('/modifier'));
    this.roleId.set(id);
    this.api.get<CoreAdminRoleOptions>('/plateforme/admin/roles/options').subscribe({
      next: (res) => this.catalogue.set(res.permissions ?? []),
      error: () => this.catalogue.set([]),
    });
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
    if (id) {
      this.api.get<CoreAdminRoleFiche>(`/plateforme/admin/roles/${id}`).subscribe({
        next: (row) => this.fill(row),
        error: (err) => this.erreur.set(coreAdminRbacError(err, 'Rôle introuvable.')),
      });
    }
  }

  isChecked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  togglePermission(code: string, on: boolean): void {
    const next = new Set(this.selected());
    if (on) {
      next.add(code);
    } else {
      next.delete(code);
    }
    this.selected.set(next);
  }

  async save(): Promise<void> {
    if (this.isView() || this.saving() || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    const codes = [...this.selected()].sort();
    const ok = await this.dialogs.confirm({
      title: this.isCreate() ? 'Confirmer la création' : 'Confirmer la modification',
      message: this.isCreate()
        ? `Créer le rôle « ${value.label} » (${value.code}) avec ${codes.length} permission(s) ?`
        : `Enregistrer « ${value.label} » avec ${codes.length} permission(s) ?`,
      confirmLabel: this.isCreate() ? 'Créer' : 'Enregistrer',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.erreur.set(null);
    const body = {
      label: value.label.trim(),
      description: value.description.trim(),
      permission_codes: codes,
    };
    if (this.isCreate()) {
      this.api
        .post<CoreAdminRoleFiche>('/plateforme/admin/roles', {
          ...body,
          code: value.code.trim().toLowerCase(),
        })
        .subscribe({
          next: (created) => {
            this.saving.set(false);
            void this.dialogs.success(`« ${created.label} » a été créé.`).then(() => {
              void this.router.navigate(['/admin/roles', created.id]);
            });
          },
          error: (err) => {
            this.saving.set(false);
            void this.dialogs.error(coreAdminRbacError(err, 'Création impossible.'));
          },
        });
      return;
    }
    const id = this.roleId();
    if (!id) {
      return;
    }
    this.api.patch<CoreAdminRoleFiche>(`/plateforme/admin/roles/${id}`, body).subscribe({
      next: (row) => {
        this.saving.set(false);
        this.fill(row);
        void this.dialogs.success(`« ${row.label} » a été enregistré.`).then(() => {
          void this.router.navigate(['/admin/roles', id]);
        });
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminRbacError(err, 'Enregistrement impossible.'));
      },
    });
  }

  async askDelete(): Promise<void> {
    const id = this.roleId();
    if (!id || this.saving() || this.locked()) {
      return;
    }
    const label = this.form.controls.label.value;
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer « ${label} » ? Impossible s’il reste des utilisateurs.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.api.delete(`/plateforme/admin/roles/${id}`).subscribe({
      next: () => {
        this.saving.set(false);
        void this.dialogs.success(`« ${label} » a été supprimé.`).then(() => {
          void this.router.navigate(['/admin/roles']);
        });
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminRbacError(err, 'Suppression impossible.'));
      },
    });
  }

  private fill(row: CoreAdminRoleFiche): void {
    this.locked.set(row.locked);
    this.selected.set(new Set(row.permission_codes ?? []));
    this.form.patchValue({
      code: row.code,
      label: row.label,
      description: row.description || '',
    });
    this.form.controls.code.disable({ emitEvent: false });
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
  }
}
