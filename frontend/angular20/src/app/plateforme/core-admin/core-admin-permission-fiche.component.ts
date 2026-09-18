import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import {
  CoreAdminPermissionFiche,
  CoreAdminRoleSummary,
  coreAdminRbacError,
} from './core-admin-rbac.models';

@Component({
  selector: 'bea-core-admin-permission-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/permissions">Permissions</a></p>
          <h1>
            @if (isCreate()) {
              Nouvelle permission
            } @else if (isView()) {
              {{ form.controls.code.value || 'Fiche permission' }}
            } @else {
              Modifier {{ form.controls.code.value || 'la permission' }}
            }
          </h1>
          <p>Code stable <code>{{ '{' }}module{{ '}' }}.{{ '{' }}action{{ '}' }}</code>.</p>
        </div>
        @if (!isCreate()) {
          <div class="bea-admin-users__head-actions">
            @if (locked()) {
              <span class="bea-admin-pill">Catalogue</span>
            }
            @if (isView() && permissionId(); as id) {
              <a class="bea-admin-btn" [routerLink]="['/admin/permissions', id, 'modifier']">Éditer</a>
            }
          </div>
        }
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (locked()) {
        <p class="bea-admin-note">Permission catalogue : code et module figés, suppression impossible.</p>
      }

      <form class="bea-admin-form" [formGroup]="form" (ngSubmit)="save()">
        <section class="bea-admin-panel">
          <h2>Identité</h2>
          <div class="bea-admin-grid">
            <label class="bea-admin-field">
              <span>Code</span>
              <input type="text" formControlName="code" placeholder="ex. credit.read" />
            </label>
            <label class="bea-admin-field">
              <span>Module</span>
              <input type="text" formControlName="module" placeholder="ex. credit" />
            </label>
            <label class="bea-admin-field bea-admin-toolbar__search">
              <span>Libellé</span>
              <input type="text" formControlName="label" />
            </label>
          </div>
        </section>

        <div class="bea-admin-form__actions">
          @if (!isView()) {
            <button type="submit" class="bea-admin-btn" [disabled]="saving()">
              {{ saving() ? 'Enregistrement…' : isCreate() ? 'Créer' : 'Enregistrer' }}
            </button>
          }
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/permissions">Retour à la liste</a>
        </div>
      </form>

      @if (!isCreate()) {
        @if (!locked()) {
          <div class="bea-admin-actions">
            <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="saving()" (click)="askDelete()">
              Supprimer
            </button>
          </div>
        }
        <section class="bea-admin-panel">
          <h2>Rôles qui portent cette permission</h2>
          @if (roles().length === 0) {
            <p class="bea-admin-panel__empty">Aucun rôle ne porte encore ce code.</p>
          } @else {
            <ul class="bea-admin-perms">
              @for (role of roles(); track role.id) {
                <li>
                  <a class="bea-admin-table__link" [routerLink]="['/admin/roles', role.id]">{{ role.label }}</a>
                </li>
              }
            </ul>
          }
        </section>
      }
    </section>
  `,
})
export class CoreAdminPermissionFicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly isCreate = signal(true);
  readonly isView = signal(false);
  readonly saving = signal(false);
  readonly locked = signal(false);
  readonly permissionId = signal<string | null>(null);
  readonly roles = signal<CoreAdminRoleSummary[]>([]);
  readonly erreur = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.minLength(3)]],
    label: ['', Validators.required],
    module: [''],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const url = this.router.url;
    this.isCreate.set(!id);
    this.isView.set(!!id && !url.includes('/modifier'));
    this.permissionId.set(id);
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
    if (id) {
      this.api.get<CoreAdminPermissionFiche>(`/plateforme/admin/permissions/${id}`).subscribe({
        next: (row) => this.fill(row),
        error: (err) => this.erreur.set(coreAdminRbacError(err, 'Permission introuvable.')),
      });
    }
  }

  async save(): Promise<void> {
    if (this.isView() || this.saving() || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    const ok = await this.dialogs.confirm({
      title: this.isCreate() ? 'Confirmer la création' : 'Confirmer la modification',
      message: this.isCreate()
        ? `Créer la permission « ${value.code} » ?`
        : `Enregistrer « ${value.code} » ?`,
      confirmLabel: this.isCreate() ? 'Créer' : 'Enregistrer',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.erreur.set(null);
    if (this.isCreate()) {
      this.api
        .post<CoreAdminPermissionFiche>('/plateforme/admin/permissions', {
          code: value.code.trim().toLowerCase(),
          label: value.label.trim(),
          module: value.module.trim() || null,
        })
        .subscribe({
          next: (created) => {
            this.saving.set(false);
            void this.dialogs.success(`« ${created.code} » a été créée.`).then(() => {
              void this.router.navigate(['/admin/permissions', created.id]);
            });
          },
          error: (err) => {
            this.saving.set(false);
            void this.dialogs.error(coreAdminRbacError(err, 'Création impossible.'));
          },
        });
      return;
    }
    const id = this.permissionId();
    if (!id) {
      return;
    }
    const body: { label: string; module?: string } = { label: value.label.trim() };
    if (!this.locked()) {
      body.module = value.module.trim();
    }
    this.api.patch<CoreAdminPermissionFiche>(`/plateforme/admin/permissions/${id}`, body).subscribe({
      next: (row) => {
        this.saving.set(false);
        this.fill(row);
        void this.dialogs.success(`« ${row.code} » a été enregistrée.`).then(() => {
          void this.router.navigate(['/admin/permissions', id]);
        });
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminRbacError(err, 'Enregistrement impossible.'));
      },
    });
  }

  async askDelete(): Promise<void> {
    const id = this.permissionId();
    if (!id || this.saving() || this.locked()) {
      return;
    }
    const code = this.form.controls.code.value;
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer « ${code} » ? Impossible si un rôle la porte encore.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.api.delete(`/plateforme/admin/permissions/${id}`).subscribe({
      next: () => {
        this.saving.set(false);
        void this.dialogs.success(`« ${code} » a été supprimée.`).then(() => {
          void this.router.navigate(['/admin/permissions']);
        });
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminRbacError(err, 'Suppression impossible.'));
      },
    });
  }

  private fill(row: CoreAdminPermissionFiche): void {
    this.locked.set(row.locked);
    this.roles.set(row.roles ?? []);
    this.form.patchValue({
      code: row.code,
      label: row.label,
      module: row.module,
    });
    this.form.controls.code.disable({ emitEvent: false });
    if (row.locked) {
      this.form.controls.module.disable({ emitEvent: false });
    }
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
  }
}
