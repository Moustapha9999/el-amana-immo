import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CoreAdminCatalogueKpis,
  CoreAdminEspaceOption,
  CoreAdminModulePage,
  CoreAdminModuleRow,
  catalogueStatut,
  catalogueStatutLabel,
  coreAdminCatalogueError,
} from './core-admin-catalogue.models';

@Component({
  selector: 'bea-core-admin-modules',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Modules</h1>
          <p>Modules métier rattachés à un département BEA DIGITAL. Immobilisations reste protégé.</p>
        </div>
        <a class="bea-admin-btn" routerLink="/admin/modules/nouveau">Nouveau module</a>
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
          <span>Département</span>
          <select formControlName="espace_id">
            <option value="tous">Tous</option>
            @for (espace of espaces(); track espace.id) {
              <option [value]="espace.id">{{ espace.label }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Statut</span>
          <select formControlName="statut">
            <option value="tous">Tous</option>
            <option value="actif">Actifs</option>
            <option value="bientot">Bientôt</option>
            <option value="inactif">Inactifs</option>
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
        <p class="bea-admin-dash__loading">Chargement des modules…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-users__list">
          <div class="bea-admin-users__list-head">
            <h2>Liste des modules</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          @if (rows().length === 0) {
            <p class="bea-admin-panel__empty">Aucun module pour ces critères.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Libellé</th>
                    <th>Code</th>
                    <th>Département</th>
                    <th>Entrée</th>
                    <th>Utilisateurs</th>
                    <th>Statut</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>
                        <a class="bea-admin-table__link" [routerLink]="['/admin/modules', row.id]">{{ row.label }}</a>
                        @if (row.locked) {
                          <span class="bea-admin-pill">Système</span>
                        }
                      </td>
                      <td><code>{{ row.code }}</code></td>
                      <td>{{ row.espace_label }}</td>
                      <td>{{ row.entry_path || '—' }}</td>
                      <td>{{ row.users_count }}</td>
                      <td>
                        <span
                          class="bea-badge"
                          [class.bea-badge--actif]="statutOf(row) === 'actif'"
                          [class.bea-badge--bientot]="statutOf(row) === 'bientot'"
                          [class.bea-badge--inactif]="statutOf(row) === 'inactif'"
                        >
                          {{ statutLabel(row) }}
                        </span>
                      </td>
                      <td class="bea-admin-table__actions">
                        <div class="bea-admin-row-actions">
                          <a class="bea-admin-icon-btn" [routerLink]="['/admin/modules', row.id]" title="Voir" aria-label="Voir">
                            <bea-admin-icon name="visibility" />
                          </a>
                          <a class="bea-admin-icon-btn" [routerLink]="['/admin/modules', row.id, 'modifier']" title="Éditer" aria-label="Éditer">
                            <bea-admin-icon name="edit" />
                          </a>
                          @if (!row.locked) {
                            @if (row.is_active) {
                              <button type="button" class="bea-admin-icon-btn" [disabled]="saving()" (click)="setActive(row, false)" title="Désactiver" aria-label="Désactiver">
                                <bea-admin-icon name="block" />
                              </button>
                            } @else {
                              <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--ok" [disabled]="saving()" (click)="setActive(row, true)" title="Réactiver" aria-label="Réactiver">
                                <bea-admin-icon name="check_circle" />
                              </button>
                            }
                            <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--danger" [disabled]="saving()" (click)="askDelete(row)" title="Supprimer" aria-label="Supprimer">
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
              <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} module(s)</span>
              <div>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="go(page() - 1)">Précédent</button>
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages()" (click)="go(page() + 1)">Suivant</button>
              </div>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class CoreAdminModulesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<CoreAdminModuleRow[]>([]);
  readonly espaces = signal<CoreAdminEspaceOption[]>([]);
  readonly kpis = signal<CoreAdminCatalogueKpis | null>(null);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly size = 20;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly filters = this.fb.nonNullable.group({ search: '', statut: 'tous', espace_id: 'tous' });

  ngOnInit(): void {
    this.api.get<{ espaces: CoreAdminEspaceOption[] }>('/plateforme/admin/modules/options').subscribe({
      next: (res) => this.espaces.set(res.espaces ?? []),
      error: () => this.espaces.set([]),
    });
    this.load();
  }

  statutOf = catalogueStatut;
  statutLabel(row: CoreAdminModuleRow): string {
    return catalogueStatutLabel(catalogueStatut(row));
  }

  kpiCards(k: CoreAdminCatalogueKpis) {
    const statut = this.filters.controls.statut.value;
    return [
      { key: 'tous', label: 'Total', value: this.fmt(k.total), icon: 'apps', tone: 'modules', on: statut === 'tous' },
      { key: 'actif', label: 'Actifs', value: this.fmt(k.actifs), icon: 'bolt', tone: 'actions', on: statut === 'actif' },
      { key: 'bientot', label: 'Bientôt', value: this.fmt(k.bientot), icon: 'history', tone: 'sessions', on: statut === 'bientot' },
      { key: 'inactif', label: 'Inactifs', value: this.fmt(k.inactifs), icon: 'block', tone: 'alert', on: statut === 'inactif' },
    ];
  }

  applyKpi(key: string): void {
    this.filters.patchValue({
      search: this.filters.controls.search.value,
      espace_id: this.filters.controls.espace_id.value,
      statut: key,
    });
    this.search();
  }

  search(): void {
    this.page.set(1);
    this.load();
  }

  resetFilters(): void {
    this.filters.reset({ search: '', statut: 'tous', espace_id: 'tous' });
    this.search();
  }

  go(page: number): void {
    if (page < 1 || page > this.totalPages() || page === this.page()) {
      return;
    }
    this.page.set(page);
    this.load();
  }

  async setActive(row: CoreAdminModuleRow, active: boolean): Promise<void> {
    if (this.saving()) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: active ? 'Confirmer la réactivation' : 'Confirmer la désactivation',
      message: active
        ? `Réactiver le module « ${row.label} » ?`
        : `Désactiver « ${row.label} » ? Il ne sera plus proposé à l’entrée module. L’action est réversible.`,
      confirmLabel: active ? 'Réactiver' : 'Désactiver',
      tone: active ? 'primary' : 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    const path = active ? 'activate' : 'deactivate';
    this.api.post(`/plateforme/admin/modules/${row.id}/${path}`, {}).subscribe({
      next: () => {
        this.saving.set(false);
        this.load();
        void this.dialogs.success(
          active ? `« ${row.label} » a été réactivé.` : `« ${row.label} » a été désactivé.`,
        );
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Action impossible.'));
      },
    });
  }

  async askDelete(row: CoreAdminModuleRow): Promise<void> {
    if (this.saving()) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer le module « ${row.label} » (${row.code}) ? Impossible s’il reste des accès utilisateurs.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.api.delete(`/plateforme/admin/modules/${row.id}`).subscribe({
      next: () => {
        this.saving.set(false);
        this.load();
        void this.dialogs.success(`« ${row.label} » a été supprimé.`, 'Suppression effectuée');
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Suppression impossible.'));
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
    const params: Record<string, string | number> = { page: this.page(), size: this.size, statut: value.statut };
    if (value.search.trim()) {
      params['search'] = value.search.trim();
    }
    if (value.espace_id !== 'tous') {
      params['espace_id'] = value.espace_id;
    }
    this.api.get<CoreAdminModulePage>('/plateforme/admin/modules', params).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.total.set(res.total);
        this.kpis.set(res.kpis);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.rows.set([]);
        this.erreur.set(coreAdminCatalogueError(err, 'Impossible de charger les modules.'));
      },
    });
  }
}
