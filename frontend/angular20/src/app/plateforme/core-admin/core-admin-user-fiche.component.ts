import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import {
  CoreAdminCatalogueEspace,
  CoreAdminRole,
  CoreAdminUserFiche,
  coreAdminApiError,
} from './core-admin-users.models';

@Component({
  selector: 'bea-core-admin-user-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/users">Utilisateurs</a></p>
          <h1>
            @if (isCreate()) {
              Nouvel utilisateur
            } @else if (isView()) {
              {{ form.controls.full_name.value || 'Fiche utilisateur' }}
            } @else {
              Modifier {{ form.controls.full_name.value || "l'utilisateur" }}
            }
          </h1>
          <p>
            @if (isCreate()) {
              Compte plateforme : identité, départements, modules et rôles.
            } @else if (isView()) {
              Détail complet : identité, accès, rôles, permissions, sessions et activité.
            } @else {
              Modification de l’identité, des départements, modules et rôles.
            }
          </p>
        </div>
        @if (!isCreate()) {
          <div class="bea-admin-users__head-actions">
            <span
              class="bea-badge"
              [class.bea-badge--actif]="isActive()"
              [class.bea-badge--inactif]="!isActive()"
            >
              {{ isActive() ? 'Actif' : 'Inactif' }}
            </span>
            @if (isView() && userId(); as id) {
              <a class="bea-admin-btn" [routerLink]="['/admin/users', id, 'modifier']">Éditer</a>
            }
          </div>
        }
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }

      @if (!isCreate()) {
        <div class="bea-admin-kpis">
          <article class="bea-admin-kpi" data-tone="org">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Départements</p>
              <p class="bea-admin-kpi__value">{{ selectedEspaces().length }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="modules">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Modules</p>
              <p class="bea-admin-kpi__value">{{ selectedModules().length }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="actions">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Rôles</p>
              <p class="bea-admin-kpi__value">{{ selectedRoles().length }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="sessions">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Sessions actives</p>
              <p class="bea-admin-kpi__value">{{ sessionsActives() }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="alert">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Permissions</p>
              <p class="bea-admin-kpi__value">{{ permissions().length }}</p>
            </div>
          </article>
        </div>
      }

      <form class="bea-admin-form" [formGroup]="form" (ngSubmit)="save()">
        <section class="bea-admin-panel">
          <h2>Identité</h2>
          <div class="bea-admin-grid">
            <label class="bea-admin-field">
              <span>Nom complet</span>
              <input type="text" formControlName="full_name" autocomplete="name" />
            </label>
            <label class="bea-admin-field">
              <span>E-mail</span>
              <input type="email" formControlName="email" autocomplete="email" />
            </label>
            <label class="bea-admin-field">
              <span>Téléphone</span>
              <input type="tel" formControlName="phone" autocomplete="tel" />
            </label>
            @if (isCreate()) {
              <label class="bea-admin-field">
                <span>Mot de passe</span>
                <input type="password" formControlName="password" autocomplete="new-password" />
              </label>
              <label class="bea-admin-field">
                <span>Confirmation</span>
                <input type="password" formControlName="password2" autocomplete="new-password" />
              </label>
            }
            @if (canGrantSuperuser()) {
              <label class="bea-admin-check" [class.bea-admin-check--on]="form.controls.is_superuser.value">
                <input type="checkbox" formControlName="is_superuser" />
                Superutilisateur
              </label>
            }
          </div>
        </section>

        <section class="bea-admin-panel">
          <h2>Départements et modules</h2>
          <div class="bea-admin-grants">
            @for (espace of catalogue(); track espace.id) {
              <fieldset class="bea-admin-grant" [class.bea-admin-grant--on]="espaceSelected(espace.id)">
                <legend>
                  <label class="bea-admin-check" [class.bea-admin-check--on]="espaceSelected(espace.id)">
                    <input
                      type="checkbox"
                      [checked]="espaceSelected(espace.id)"
                      [disabled]="isView()"
                      (change)="toggleEspace(espace, isChecked($event))"
                    />
                    {{ espace.titre }}
                  </label>
                </legend>
                @if (espace.modules.length) {
                  <div class="bea-admin-grant__meter">
                    <div class="bea-admin-grant__meter-track">
                      <div
                        class="bea-admin-grant__meter-fill"
                        [style.width.%]="espaceModulePct(espace)"
                      ></div>
                    </div>
                    <span class="bea-admin-grant__meter-label">
                      {{ espaceModuleCount(espace) }}/{{ espace.modules.length }}
                    </span>
                  </div>
                }
                @for (mod of espace.modules; track mod.id) {
                  <label
                    class="bea-admin-check bea-admin-check--nested"
                    [class.bea-admin-check--on]="moduleSelected(mod.id)"
                  >
                    <input
                      type="checkbox"
                      [checked]="moduleSelected(mod.id)"
                      [disabled]="isView()"
                      (change)="toggleModule(espace.id, mod.id, isChecked($event))"
                    />
                    {{ mod.titre }}
                  </label>
                }
              </fieldset>
            }
          </div>
        </section>

        <section class="bea-admin-panel">
          <h2>Rôles</h2>
          <div class="bea-admin-checks">
            @for (role of roles(); track role.id) {
              <label class="bea-admin-check" [class.bea-admin-check--on]="roleSelected(role.code)">
                <input
                  type="checkbox"
                  [checked]="roleSelected(role.code)"
                  [disabled]="isView()"
                  (change)="toggleRole(role.code, isChecked($event))"
                />
                {{ role.label }}
              </label>
            }
          </div>
        </section>

        <div class="bea-admin-form__actions">
          @if (!isView()) {
            <button type="submit" class="bea-admin-btn" [disabled]="saving()">
              {{ saving() ? 'Enregistrement…' : isCreate() ? 'Créer' : 'Enregistrer' }}
            </button>
          }
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/users">Retour à la liste</a>
        </div>
      </form>

      @if (!isCreate()) {
        <section class="bea-admin-panel">
          <h2>Mot de passe</h2>
          <div class="bea-admin-password-card">
            <div>
              <p class="bea-admin-panel__hint">
                Remplacez le mot de passe du compte plateforme. Toutes les sessions actives seront
                révoquées.
              </p>
              <button type="button" class="bea-admin-btn" [disabled]="saving()" (click)="resetAccess()">
                Changer le mot de passe
              </button>
            </div>
            <div class="bea-admin-password-card__viz" aria-hidden="true">
              <span></span><span></span><span></span><span></span><span></span><span></span>
            </div>
          </div>
        </section>

        <div class="bea-admin-actions">
          @if (isActive() && !isSelf()) {
            <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="saving()" (click)="deactivate()">
              Désactiver
            </button>
          }
          @if (!isActive() && !isSelf()) {
            <button type="button" class="bea-admin-btn" [disabled]="saving()" (click)="activate()">
              Réactiver
            </button>
          }
          @if (!isSelf()) {
            <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="saving()" (click)="askDelete()">
              Supprimer
            </button>
          }
        </div>

        <section class="bea-admin-panel">
          <h2>Permissions (lecture)</h2>
          @if (permissions().length === 0) {
            <p class="bea-admin-panel__empty">Aucune permission directe listée.</p>
          } @else {
            <ul class="bea-admin-perms">
              @for (code of permissions(); track code) {
                <li>{{ code }}</li>
              }
            </ul>
          }
        </section>

        <div class="bea-admin-panels bea-admin-panels--equal">
          <section class="bea-admin-panel bea-admin-panel--list">
            <h2>Sessions</h2>
            @if (fiche()?.sessions?.length) {
              <div class="bea-admin-panel__scroll">
                <table class="bea-admin-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Module</th>
                      <th>IP</th>
                      <th>Début</th>
                      <th>État</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (row of fiche()!.sessions; track row.id) {
                      <tr>
                        <td>{{ row.kind === 'module' ? 'Module' : 'BEA DIGITAL' }}</td>
                        <td>{{ row.module_code || '—' }}</td>
                        <td>{{ row.ip_address || '—' }}</td>
                        <td>
                          @if (row.created_at) {
                            {{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                          } @else {
                            —
                          }
                        </td>
                        <td>{{ row.active ? 'Active' : 'Révoquée / expirée' }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <p class="bea-admin-panel__empty">Aucune session enregistrée.</p>
            }
          </section>

          <section class="bea-admin-panel bea-admin-panel--list">
            <h2>Activité</h2>
            @if (fiche()?.activite?.length) {
              <div class="bea-admin-panel__scroll">
                <table class="bea-admin-table">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Entité</th>
                      <th>Module</th>
                      <th>Quand</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (row of fiche()!.activite; track row.id) {
                      <tr>
                        <td>{{ row.action }}</td>
                        <td class="bea-admin-table__clip" [title]="row.entity + (row.entity_id ? ' · ' + row.entity_id : '')">
                          {{ row.entity }}{{ row.entity_id ? ' · ' + row.entity_id : '' }}
                        </td>
                        <td>{{ row.module || '—' }}</td>
                        <td>
                          @if (row.created_at) {
                            {{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                          } @else {
                            —
                          }
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <p class="bea-admin-panel__empty">Aucune action journalisée pour ce compte.</p>
            }
          </section>
        </div>
      }
    </section>
  `,
})
export class CoreAdminUserFicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly isCreate = signal(true);
  readonly isView = signal(false);
  readonly userId = signal<string | null>(null);
  readonly fiche = signal<CoreAdminUserFiche | null>(null);
  readonly roles = signal<CoreAdminRole[]>([]);
  readonly catalogue = signal<CoreAdminCatalogueEspace[]>([]);
  readonly selectedRoles = signal<string[]>([]);
  readonly selectedEspaces = signal<string[]>([]);
  readonly selectedModules = signal<string[]>([]);
  readonly saving = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly isActive = computed(() => this.fiche()?.is_active !== false);
  readonly isSelf = computed(() => {
    const id = this.userId();
    return !!id && id === this.auth.user()?.id;
  });
  readonly canGrantSuperuser = computed(() => this.auth.user()?.is_superuser === true);
  readonly permissions = computed(() => this.fiche()?.permission_codes ?? []);
  readonly sessionsActives = computed(
    () => (this.fiche()?.sessions ?? []).filter((s) => s.active).length,
  );

  readonly form = this.fb.nonNullable.group({
    full_name: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    phone: [''],
    password: [''],
    password2: [''],
    is_superuser: [false],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const url = this.router.url;
    this.isCreate.set(!id);
    this.isView.set(!!id && !url.includes('/modifier'));
    this.userId.set(id);
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
    if (id) {
      this.form.controls.password.clearValidators();
      this.form.controls.password2.clearValidators();
    } else {
      this.form.controls.password.setValidators([Validators.required, Validators.minLength(8)]);
      this.form.controls.password2.setValidators([Validators.required]);
    }
    this.form.controls.password.updateValueAndValidity();
    this.form.controls.password2.updateValueAndValidity();
    this.loadRoles();
    this.loadCatalogue();
    if (id) {
      this.loadFiche(id);
    }
  }

  espaceModuleCount(espace: CoreAdminCatalogueEspace): number {
    return espace.modules.filter((mod) => this.moduleSelected(mod.id)).length;
  }

  espaceModulePct(espace: CoreAdminCatalogueEspace): number {
    if (!espace.modules.length) {
      return 0;
    }
    return Math.round((this.espaceModuleCount(espace) / espace.modules.length) * 100);
  }

  espaceSelected(code: string): boolean {
    return this.selectedEspaces().includes(code);
  }

  moduleSelected(code: string): boolean {
    return this.selectedModules().includes(code);
  }

  roleSelected(code: string): boolean {
    return this.selectedRoles().includes(code);
  }

  isChecked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }

  toggleEspace(espace: CoreAdminCatalogueEspace, checked: boolean): void {
    const espaces = new Set(this.selectedEspaces());
    const modules = new Set(this.selectedModules());
    if (checked) {
      espaces.add(espace.id);
    } else {
      espaces.delete(espace.id);
      for (const mod of espace.modules) {
        modules.delete(mod.id);
      }
    }
    this.selectedEspaces.set([...espaces]);
    this.selectedModules.set([...modules]);
  }

  toggleModule(espaceId: string, moduleId: string, checked: boolean): void {
    const modules = new Set(this.selectedModules());
    const espaces = new Set(this.selectedEspaces());
    if (checked) {
      modules.add(moduleId);
      espaces.add(espaceId);
    } else {
      modules.delete(moduleId);
    }
    this.selectedModules.set([...modules]);
    this.selectedEspaces.set([...espaces]);
  }

  toggleRole(code: string, checked: boolean): void {
    const roles = new Set(this.selectedRoles());
    if (checked) {
      roles.add(code);
    } else {
      roles.delete(code);
    }
    this.selectedRoles.set([...roles]);
  }

  async save(): Promise<void> {
    this.erreur.set(null);
    if (this.isView() || this.saving()) {
      return;
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      await this.dialogs.error('Complétez les champs obligatoires.', 'Validation');
      return;
    }
    const value = this.form.getRawValue();
    if (this.isCreate() && value.password !== value.password2) {
      await this.dialogs.error('Les mots de passe ne correspondent pas.', 'Validation');
      return;
    }
    const name = value.full_name.trim();
    const ok = await this.dialogs.confirm({
      title: this.isCreate() ? 'Confirmer la création' : 'Confirmer la modification',
      message: this.isCreate()
        ? `Créer le compte ${name} (${value.email.trim()}) avec les départements, modules et rôles sélectionnés ?`
        : `Enregistrer les modifications de ${name} (${value.email.trim()}) ?`,
      confirmLabel: this.isCreate() ? 'Créer' : 'Enregistrer',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    const body: Record<string, unknown> = {
      full_name: name,
      email: value.email.trim(),
      phone: value.phone.trim() || null,
      role_codes: this.selectedRoles(),
      espace_codes: this.selectedEspaces(),
      module_codes: this.selectedModules(),
    };
    if (this.canGrantSuperuser()) {
      body['is_superuser'] = value.is_superuser;
    }
    if (this.isCreate()) {
      body['password'] = value.password;
      this.api.post<CoreAdminUserFiche>('/plateforme/admin/users', body).subscribe({
        next: (created) => {
          this.saving.set(false);
          void this.dialogs
            .success(`${created.full_name} a été ajouté.`, 'Utilisateur créé')
            .then(() => this.router.navigate(['/admin/users', created.id]));
        },
        error: (err) => this.fail(err, "Impossible de créer l'utilisateur."),
      });
      return;
    }
    const id = this.userId();
    if (!id) {
      this.saving.set(false);
      return;
    }
    this.api.patch<CoreAdminUserFiche>(`/plateforme/admin/users/${id}`, body).subscribe({
      next: () => {
        this.saving.set(false);
        void this.dialogs
          .success(`Les informations de ${name} ont été enregistrées.`, 'Modification enregistrée')
          .then(() => this.router.navigate(['/admin/users', id]));
      },
      error: (err) => this.fail(err, "Impossible d'enregistrer l'utilisateur."),
    });
  }

  async deactivate(): Promise<void> {
    const fiche = this.fiche();
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la désactivation',
      message: `Désactiver ${fiche?.full_name ?? 'ce compte'} ? Il ne pourra plus se connecter. L’action est réversible.`,
      confirmLabel: 'Désactiver',
      tone: 'danger',
    });
    if (ok) {
      this.act('deactivate', 'Compte désactivé.', `${fiche?.full_name ?? 'Le compte'} a été désactivé.`);
    }
  }

  async activate(): Promise<void> {
    const fiche = this.fiche();
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la réactivation',
      message: `Réactiver ${fiche?.full_name ?? 'ce compte'} ? Il pourra de nouveau se connecter à BEA DIGITAL.`,
      confirmLabel: 'Réactiver',
    });
    if (ok) {
      this.act('activate', 'Compte réactivé.', `${fiche?.full_name ?? 'Le compte'} a été réactivé.`);
    }
  }

  async askDelete(): Promise<void> {
    const fiche = this.fiche();
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Archiver ${fiche?.full_name ?? 'ce compte'} (${fiche?.email ?? ''}) ? Il disparaîtra de la liste et toutes ses sessions seront révoquées.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    const id = this.userId();
    if (!id) {
      return;
    }
    this.saving.set(true);
    this.erreur.set(null);
    this.api.delete(`/plateforme/admin/users/${id}`).subscribe({
      next: () => {
        this.saving.set(false);
        void this.dialogs
          .success(`${fiche?.full_name ?? 'Le compte'} a été supprimé.`, 'Suppression effectuée')
          .then(() => this.router.navigate(['/admin/users']));
      },
      error: (err) => this.fail(err, 'Suppression impossible.'),
    });
  }

  async resetAccess(): Promise<void> {
    if (this.saving()) {
      return;
    }
    const fiche = this.fiche();
    const values = await this.dialogs.prompt({
      title: 'Changer le mot de passe',
      message: `Remplacer le mot de passe de ${fiche?.full_name ?? 'ce compte'} et révoquer toutes ses sessions ?`,
      confirmLabel: 'Changer le mot de passe',
      tone: 'warn',
      fields: [
        { key: 'password', label: 'Nouveau mot de passe', type: 'password', autocomplete: 'new-password' },
        { key: 'password2', label: 'Confirmation', type: 'password', autocomplete: 'new-password' },
      ],
      validate: (input) => {
        if (!input['password'] || input['password'].length < 8) {
          return 'Le mot de passe doit faire au moins 8 caractères.';
        }
        if (input['password'] !== input['password2']) {
          return 'Les mots de passe ne correspondent pas.';
        }
        return null;
      },
    });
    if (!values) {
      return;
    }
    const id = this.userId();
    if (!id) {
      return;
    }
    this.saving.set(true);
    this.erreur.set(null);
    this.api.post(`/plateforme/admin/users/${id}/reset-access`, { password: values['password'] }).subscribe({
      next: () => {
        this.saving.set(false);
        this.loadFiche(id);
        void this.dialogs.success(
          'Le mot de passe a été remplacé et toutes les sessions ont été révoquées.',
          'Accès réinitialisé',
        );
      },
      error: (err) => this.fail(err, "Impossible de réinitialiser l'accès."),
    });
  }

  private act(action: 'activate' | 'deactivate', title: string, ok: string): void {
    const id = this.userId();
    if (!id) {
      return;
    }
    this.saving.set(true);
    this.erreur.set(null);
    this.api.post(`/plateforme/admin/users/${id}/${action}`, {}).subscribe({
      next: () => {
        this.saving.set(false);
        this.loadFiche(id);
        void this.dialogs.success(ok, title);
      },
      error: (err) => this.fail(err, 'Action impossible.'),
    });
  }

  private loadRoles(): void {
    this.api.get<CoreAdminRole[]>('/plateforme/admin/users/roles').subscribe({
      next: (roles) => this.roles.set(roles),
      error: () => this.roles.set([]),
    });
  }

  private loadCatalogue(): void {
    this.api.get<CoreAdminCatalogueEspace[]>('/plateforme/catalogue').subscribe({
      next: (items) => this.catalogue.set(items),
      error: () => this.catalogue.set([]),
    });
  }

  private loadFiche(id: string): void {
    this.api.get<CoreAdminUserFiche>(`/plateforme/admin/users/${id}`).subscribe({
      next: (fiche) => {
        this.fiche.set(fiche);
        this.form.patchValue({
          full_name: fiche.full_name,
          email: fiche.email,
          phone: fiche.phone ?? '',
          is_superuser: fiche.is_superuser,
        });
        this.selectedRoles.set(fiche.roles.map((role) => role.code));
        this.selectedEspaces.set(fiche.espace_codes ?? []);
        this.selectedModules.set(fiche.module_codes ?? []);
        if (this.isView()) {
          this.form.disable({ emitEvent: false });
        }
      },
      error: (err) => {
        this.erreur.set(coreAdminApiError(err, 'Utilisateur introuvable.'));
      },
    });
  }

  private fail(err: HttpErrorResponse | unknown, fallback: string): void {
    this.saving.set(false);
    const message = coreAdminApiError(err, fallback);
    this.erreur.set(message);
    void this.dialogs.error(message);
  }
}
