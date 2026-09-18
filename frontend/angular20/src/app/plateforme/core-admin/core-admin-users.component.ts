import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CoreAdminCatalogueEspace,
  CoreAdminRole,
  CoreAdminUserKpis,
  CoreAdminUserPage,
  CoreAdminUserRow,
  coreAdminApiError,
} from './core-admin-users.models';

@Component({
  selector: 'bea-core-admin-users',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Utilisateurs</h1>
          <p>Pilotage des comptes BEA DIGITAL — indépendant du module Immobilisations.</p>
        </div>
        <a class="bea-admin-btn" routerLink="/admin/users/nouveau">Nouvel utilisateur</a>
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
                @if (card.hint) {
                  <p class="bea-admin-kpi__hint">{{ card.hint }}</p>
                }
              </div>
            </button>
          }
        </div>
      }

      <form class="bea-admin-toolbar bea-admin-toolbar--users" [formGroup]="filters" (ngSubmit)="search()">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input
            type="search"
            formControlName="search"
            placeholder="Nom, e-mail, téléphone, rôle, département, module…"
          />
        </label>
        <label class="bea-admin-field">
          <span>Statut</span>
          <select formControlName="statut">
            <option value="tous">Tous</option>
            <option value="actif">Actifs</option>
            <option value="inactif">Inactifs</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Rôle</span>
          <select formControlName="role_code">
            <option value="tous">Tous</option>
            @for (role of roles(); track role.id) {
              <option [value]="role.code">{{ role.label }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Département</span>
          <select formControlName="espace_code">
            <option value="tous">Tous</option>
            @for (espace of catalogue(); track espace.id) {
              <option [value]="espace.id">{{ espace.titre }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Module</span>
          <select formControlName="module_code">
            <option value="tous">Tous</option>
            @for (mod of modules(); track mod.id) {
              <option [value]="mod.id">{{ mod.titre }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Profil</span>
          <select formControlName="profil">
            <option value="tous">Tous</option>
            <option value="superuser">Superutilisateurs</option>
            <option value="standard">Standard</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>2FA</span>
          <select formControlName="totp">
            <option value="tous">Tous</option>
            <option value="oui">Activée</option>
            <option value="non">Non activée</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Connexion</span>
          <select formControlName="connexion">
            <option value="tous">Tous</option>
            <option value="connecte">Déjà connecté</option>
            <option value="jamais">Jamais connecté</option>
          </select>
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="submit" class="bea-admin-btn">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="resetFilters()">
            Réinitialiser
          </button>
        </div>
      </form>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }

      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement des utilisateurs…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-users__list">
          <div class="bea-admin-users__list-head">
            <h2>Liste des utilisateurs</h2>
            <p>{{ total() }} résultat(s) pour les critères courants.</p>
          </div>
          @if (rows().length === 0) {
            <p class="bea-admin-panel__empty">Aucun utilisateur pour ces critères.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Nom</th>
                    <th>E-mail</th>
                    <th>Téléphone</th>
                    <th>Rôles</th>
                    <th>Départements</th>
                    <th>Statut</th>
                    <th>Dernière connexion</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        <a class="bea-admin-table__link" [routerLink]="['/admin/users', row.id]">
                          {{ row.full_name }}
                        </a>
                        @if (row.is_superuser) {
                          <span class="bea-admin-pill">Superuser</span>
                        }
                        @if (row.totp_enabled) {
                          <span class="bea-admin-pill">2FA</span>
                        }
                      </td>
                      <td>{{ row.email }}</td>
                      <td>{{ row.phone || '—' }}</td>
                      <td>{{ roleLabel(row) }}</td>
                      <td>{{ row.espace_codes.join(', ') || '—' }}</td>
                      <td>
                        <span
                          class="bea-badge"
                          [class.bea-badge--actif]="row.is_active"
                          [class.bea-badge--inactif]="!row.is_active"
                        >
                          {{ row.is_active ? 'Actif' : 'Inactif' }}
                        </span>
                      </td>
                      <td>
                        @if (row.last_login_at) {
                          {{ row.last_login_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                        } @else {
                          —
                        }
                      </td>
                      <td class="bea-admin-table__actions">
                        <div class="bea-admin-row-actions">
                          <a
                            class="bea-admin-icon-btn"
                            [routerLink]="['/admin/users', row.id]"
                            title="Voir"
                            aria-label="Voir"
                          >
                            <bea-admin-icon name="visibility" />
                          </a>
                          <a
                            class="bea-admin-icon-btn"
                            [routerLink]="['/admin/users', row.id, 'modifier']"
                            title="Éditer"
                            aria-label="Éditer"
                          >
                            <bea-admin-icon name="edit" />
                          </a>
                          @if (!isSelf(row)) {
                            @if (row.is_active) {
                              <button
                                type="button"
                                class="bea-admin-icon-btn"
                                [disabled]="saving()"
                                (click)="setActive(row, false)"
                                title="Désactiver"
                                aria-label="Désactiver"
                              >
                                <bea-admin-icon name="block" />
                              </button>
                            } @else {
                              <button
                                type="button"
                                class="bea-admin-icon-btn bea-admin-icon-btn--ok"
                                [disabled]="saving()"
                                (click)="setActive(row, true)"
                                title="Réactiver"
                                aria-label="Réactiver"
                              >
                                <bea-admin-icon name="check_circle" />
                              </button>
                            }
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
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} utilisateur(s)</span>
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
export class CoreAdminUsersComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<CoreAdminUserRow[]>([]);
  readonly kpis = signal<CoreAdminUserKpis | null>(null);
  readonly roles = signal<CoreAdminRole[]>([]);
  readonly catalogue = signal<CoreAdminCatalogueEspace[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly size = 20;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly modules = computed(() =>
    this.catalogue().flatMap((espace) => espace.modules.map((mod) => ({ id: mod.id, titre: `${espace.titre} · ${mod.titre}` }))),
  );

  readonly filters = this.fb.nonNullable.group({
    search: '',
    statut: 'tous',
    role_code: 'tous',
    espace_code: 'tous',
    module_code: 'tous',
    profil: 'tous',
    totp: 'tous',
    connexion: 'tous',
  });

  ngOnInit(): void {
    this.loadRoles();
    this.loadCatalogue();
    this.load();
  }

  kpiCards(
    k: CoreAdminUserKpis,
  ): { key: string; label: string; value: string; hint?: string; on: boolean; icon: string; tone: string }[] {
    const f = this.filters.getRawValue();
    return [
      {
        key: 'tous',
        label: 'Total',
        value: this.fmt(k.total),
        hint: 'Tous les comptes',
        icon: 'group',
        tone: 'users',
        on:
          f.statut === 'tous' &&
          f.profil === 'tous' &&
          f.totp === 'tous' &&
          f.connexion === 'tous' &&
          f.role_code === 'tous' &&
          f.espace_code === 'tous' &&
          f.module_code === 'tous' &&
          !f.search.trim(),
      },
      { key: 'actif', label: 'Actifs', value: this.fmt(k.actifs), icon: 'bolt', tone: 'actions', on: f.statut === 'actif' },
      { key: 'inactif', label: 'Inactifs', value: this.fmt(k.inactifs), icon: 'history', tone: 'sessions', on: f.statut === 'inactif' },
      { key: 'superuser', label: 'Superusers', value: this.fmt(k.superusers), icon: 'security', tone: 'modules', on: f.profil === 'superuser' },
      { key: 'totp', label: '2FA', value: this.fmt(k.totp), hint: 'Double authentification', icon: 'vpn_key', tone: 'org', on: f.totp === 'oui' },
      { key: 'jamais', label: 'Jamais connectés', value: this.fmt(k.jamais_connectes), icon: 'devices', tone: 'alert', on: f.connexion === 'jamais' },
    ];
  }

  applyKpi(key: string): void {
    const reset = {
      search: this.filters.controls.search.value,
      statut: 'tous',
      role_code: 'tous',
      espace_code: 'tous',
      module_code: 'tous',
      profil: 'tous',
      totp: 'tous',
      connexion: 'tous',
    };
    if (key === 'actif' || key === 'inactif') {
      reset.statut = key;
    } else if (key === 'superuser') {
      reset.profil = 'superuser';
    } else if (key === 'totp') {
      reset.totp = 'oui';
    } else if (key === 'jamais') {
      reset.connexion = 'jamais';
    }
    this.filters.patchValue(reset);
    this.search();
  }

  search(): void {
    this.page.set(1);
    this.load();
  }

  resetFilters(): void {
    this.filters.reset({
      search: '',
      statut: 'tous',
      role_code: 'tous',
      espace_code: 'tous',
      module_code: 'tous',
      profil: 'tous',
      totp: 'tous',
      connexion: 'tous',
    });
    this.search();
  }

  go(page: number): void {
    if (page < 1 || page > this.totalPages() || page === this.page()) {
      return;
    }
    this.page.set(page);
    this.load();
  }

  roleLabel(row: CoreAdminUserRow): string {
    return row.roles.map((role) => role.label).join(', ') || '—';
  }

  isSelf(row: CoreAdminUserRow): boolean {
    return row.id === this.auth.user()?.id;
  }

  async setActive(row: CoreAdminUserRow, active: boolean): Promise<void> {
    if (this.saving()) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: active ? 'Confirmer la réactivation' : 'Confirmer la désactivation',
      message: active
        ? `Réactiver ${row.full_name} (${row.email}) ? Le compte pourra de nouveau se connecter à BEA DIGITAL.`
        : `Désactiver ${row.full_name} (${row.email}) ? Le compte ne pourra plus se connecter. L’action est réversible.`,
      confirmLabel: active ? 'Réactiver' : 'Désactiver',
      tone: active ? 'primary' : 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.erreur.set(null);
    const path = active ? 'activate' : 'deactivate';
    this.api.post(`/plateforme/admin/users/${row.id}/${path}`, {}).subscribe({
      next: () => {
        this.saving.set(false);
        this.load();
        void this.dialogs.success(
          active
            ? `${row.full_name} a été réactivé.`
            : `${row.full_name} a été désactivé.`,
          active ? 'Compte réactivé' : 'Compte désactivé',
        );
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminApiError(err, 'Action impossible.'));
      },
    });
  }

  async askDelete(row: CoreAdminUserRow): Promise<void> {
    if (this.saving()) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer ${row.full_name} (${row.email}) ? Le compte est archivé, ses sessions sont révoquées et il disparaît de la liste.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.erreur.set(null);
    this.api.delete(`/plateforme/admin/users/${row.id}`).subscribe({
      next: () => {
        this.saving.set(false);
        this.load();
        void this.dialogs.success(`${row.full_name} a été supprimé.`, 'Suppression effectuée');
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminApiError(err, 'Suppression impossible.'));
      },
    });
  }

  private fmt(n: number): string {
    return new Intl.NumberFormat('fr-FR').format(n);
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

  private load(): void {
    this.loading.set(true);
    this.erreur.set(null);
    const value = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.size,
      statut: value.statut,
      profil: value.profil,
      totp: value.totp,
      connexion: value.connexion,
    };
    if (value.search.trim()) {
      params['search'] = value.search.trim();
    }
    if (value.role_code !== 'tous') {
      params['role_code'] = value.role_code;
    }
    if (value.espace_code !== 'tous') {
      params['espace_code'] = value.espace_code;
    }
    if (value.module_code !== 'tous') {
      params['module_code'] = value.module_code;
    }
    this.api.get<CoreAdminUserPage>('/plateforme/admin/users', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.kpis.set(res.kpis);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.rows.set([]);
        this.total.set(0);
        this.erreur.set(coreAdminApiError(err, 'Impossible de charger les utilisateurs.'));
      },
    });
  }
}
