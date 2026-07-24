import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface RoleOption {
  id: string;
  code: string;
  label: string;
}

/** Libellés courts affichés (codes techniques inchangés côté API). */
const ROLE_LABELS: Record<string, string> = {
  administrateur: 'Admin',
  comptable: 'Comptable',
  auditeur: 'Auditeur',
  lecture_seule: 'Lecture seule',
};

interface UserRow {
  id: string;
  email: string;
  full_name: string;
  is_superuser: boolean;
  is_active: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  roles: RoleOption[];
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-utilisateurs',
  imports: [ReactiveFormsModule, MatTableModule, MatButtonModule, MatIconModule],
  templateUrl: './utilisateurs.component.html',
  styleUrl: './utilisateurs.component.css',
})
export class UtilisateursComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly rows = signal<UserRow[]>([]);
  readonly roles = signal<RoleOption[]>([]);
  readonly total = signal(0);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly formOpen = signal(false);
  readonly editingId = signal<string | null>(null);
  readonly selectedRoles = signal<string[]>([]);

  readonly columns = ['full_name', 'email', 'roles', 'flags', 'actions'];

  readonly currentUserId = computed(() => this.auth.user()?.id ?? null);

  readonly kpi = computed(() => {
    const items = this.rows();
    return {
      total: this.total(),
      superusers: items.filter((u) => u.is_superuser).length,
      with2fa: items.filter((u) => u.totp_enabled).length,
    };
  });

  readonly isEdit = computed(() => this.editingId() !== null);

  readonly filterForm = this.fb.nonNullable.group({
    search: '',
  });

  readonly userForm = this.fb.nonNullable.group({
    full_name: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.minLength(8)]],
    is_superuser: [false],
  });

  ngOnInit(): void {
    this.loadRoles();
    this.load();
  }

  loadRoles(): void {
    this.api.get<RoleOption[]>('/users/roles').subscribe({
      next: (roles) => this.roles.set(roles),
      error: () => this.roles.set([]),
    });
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    const search = this.filterForm.getRawValue().search.trim();
    const params: Record<string, string | number> = { page: 1, size: 100 };
    if (search) {
      params['search'] = search;
    }
    this.api.get<Paginated<UserRow>>('/users', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.rows.set([]);
        this.total.set(0);
        this.error.set(err.error?.detail ?? 'Accès réservé aux administrateurs.');
      },
    });
  }

  resetFilters(): void {
    this.filterForm.reset({ search: '' });
    this.load();
  }

  openCreate(): void {
    this.editingId.set(null);
    this.selectedRoles.set([]);
    this.userForm.reset({
      full_name: '',
      email: '',
      password: '',
      is_superuser: false,
    });
    this.userForm.controls.password.setValidators([Validators.required, Validators.minLength(8)]);
    this.userForm.controls.password.updateValueAndValidity();
    this.formOpen.set(true);
  }

  openEdit(row: UserRow): void {
    this.editingId.set(row.id);
    this.selectedRoles.set(row.roles.map((r) => r.code));
    this.userForm.reset({
      full_name: row.full_name,
      email: row.email,
      password: '',
      is_superuser: row.is_superuser,
    });
    this.userForm.controls.password.setValidators([Validators.minLength(8)]);
    this.userForm.controls.password.updateValueAndValidity();
    this.formOpen.set(true);
  }

  cancelForm(): void {
    this.formOpen.set(false);
    this.editingId.set(null);
  }

  toggleRole(code: string, checked: boolean): void {
    const current = new Set(this.selectedRoles());
    if (checked) {
      current.add(code);
    } else {
      current.delete(code);
    }
    this.selectedRoles.set([...current]);
  }

  isRoleSelected(code: string): boolean {
    return this.selectedRoles().includes(code);
  }

  roleLabel(role: { code: string; label: string }): string {
    return ROLE_LABELS[role.code] ?? role.label;
  }

  save(): void {
    if (this.userForm.invalid) {
      this.userForm.markAllAsTouched();
      void this.dialogs.error('Complétez les champs obligatoires', 'Validation').subscribe();
      return;
    }
    const v = this.userForm.getRawValue();
    const id = this.editingId();
    const action = id ? 'modification' : 'ajout';
    const label = v.full_name.trim() || v.email.trim();

    this.dialogs
      .confirmAction(action, id ? `Modifier l'utilisateur « ${label} » ?` : `Ajouter l'utilisateur « ${label} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.saving.set(true);

        if (id) {
          const body: Record<string, unknown> = {
            full_name: v.full_name.trim(),
            email: v.email.trim(),
            is_superuser: v.is_superuser,
            role_codes: this.selectedRoles(),
          };
          if (v.password.trim()) {
            body['password'] = v.password;
          }
          this.api.patch<UserRow>(`/users/${id}`, body).subscribe({
            next: () => {
              this.saving.set(false);
              this.formOpen.set(false);
              this.dialogs
                .successAction('modification', `« ${label} » a été mis à jour.`)
                .subscribe(() => this.load());
            },
            error: (err) => {
              this.saving.set(false);
              void this.dialogs.error(err.error?.detail ?? 'Mise à jour impossible').subscribe();
            },
          });
          return;
        }

        this.api
          .post<UserRow>('/users', {
            full_name: v.full_name.trim(),
            email: v.email.trim(),
            password: v.password,
            role_codes: this.selectedRoles(),
            is_superuser: v.is_superuser,
          })
          .subscribe({
            next: () => {
              this.saving.set(false);
              this.formOpen.set(false);
              this.dialogs
                .successAction('ajout', `« ${label} » a été créé.`)
                .subscribe(() => this.load());
            },
            error: (err) => {
              this.saving.set(false);
              void this.dialogs.error(err.error?.detail ?? 'Création impossible').subscribe();
            },
          });
      });
  }

  remove(row: UserRow): void {
    if (row.id === this.currentUserId()) {
      void this.dialogs.error('Impossible de supprimer votre propre compte').subscribe();
      return;
    }
    this.dialogs
      .confirmAction('suppression', `Voulez-vous vraiment supprimer l'utilisateur « ${row.full_name} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.api.delete<{ message: string }>(`/users/${row.id}`).subscribe({
          next: () => {
            if (this.editingId() === row.id) {
              this.cancelForm();
            }
            this.dialogs
              .successAction('suppression', `« ${row.full_name} » a été supprimé.`)
              .subscribe(() => this.load());
          },
          error: (err) => {
            void this.dialogs.error(err.error?.detail ?? 'Suppression impossible').subscribe();
          },
        });
      });
  }
}
