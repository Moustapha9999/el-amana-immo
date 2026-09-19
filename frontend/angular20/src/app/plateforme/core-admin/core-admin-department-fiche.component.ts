import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import {
  CoreAdminEspaceFiche,
  CoreAdminModuleSummary,
  catalogueStatut,
  catalogueStatutLabel,
  coreAdminCatalogueError,
} from './core-admin-catalogue.models';

@Component({
  selector: 'bea-core-admin-department-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/departments">Départements</a></p>
          <h1>
            @if (isCreate()) {
              Nouveau département
            } @else if (isView()) {
              {{ form.controls.label.value || 'Fiche département' }}
            } @else {
              Modifier {{ form.controls.label.value || 'le département' }}
            }
          </h1>
          <p>Espace BEA DIGITAL — pas le référentiel org Immobilisations.</p>
        </div>
        @if (!isCreate()) {
          <div class="bea-admin-users__head-actions">
            <span
              class="bea-badge"
              [class.bea-badge--actif]="statutOf() === 'actif'"
              [class.bea-badge--bientot]="statutOf() === 'bientot'"
              [class.bea-badge--inactif]="statutOf() === 'inactif'"
            >
              {{ statutLabel() }}
            </span>
            @if (isView() && espaceId(); as id) {
              <a class="bea-admin-btn" [routerLink]="['/admin/departments', id, 'modifier']">Éditer</a>
            }
          </div>
        }
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (locked()) {
        <p class="bea-admin-note">Département système : code et route figés, suppression et désactivation impossibles.</p>
      }

      @if (!isCreate()) {
        <div class="bea-admin-kpis">
          <article class="bea-admin-kpi" data-tone="modules">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Modules</p>
              <p class="bea-admin-kpi__value">{{ modules().length }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="org">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Statut</p>
              <p class="bea-admin-kpi__value" style="font-size:1.15rem">{{ statutLabel() }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="actions">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Ordre</p>
              <p class="bea-admin-kpi__value">{{ form.controls.sort_order.value }}</p>
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
              <input type="text" formControlName="code" placeholder="ex. credit" />
            </label>
            <label class="bea-admin-field">
              <span>Libellé</span>
              <input type="text" formControlName="label" />
            </label>
            <label class="bea-admin-field">
              <span>Route</span>
              <input type="text" formControlName="route" placeholder="/comptabilite" />
            </label>
            <label class="bea-admin-field">
              <span>Statut</span>
              <select formControlName="statut">
                <option value="actif">Actif</option>
                <option value="bientot">Bientôt</option>
                <option value="inactif">Inactif</option>
              </select>
            </label>
            <label class="bea-admin-field">
              <span>Ordre</span>
              <input type="number" formControlName="sort_order" min="0" />
            </label>
            <label class="bea-admin-field bea-admin-toolbar__search">
              <span>Description</span>
              <textarea formControlName="description" rows="3"></textarea>
            </label>
          </div>
        </section>
        <div class="bea-admin-form__actions">
          @if (!isView()) {
            <button type="submit" class="bea-admin-btn" [disabled]="saving()">
              {{ saving() ? 'Enregistrement…' : isCreate() ? 'Créer' : 'Enregistrer' }}
            </button>
          }
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/departments">Retour à la liste</a>
        </div>
      </form>

      @if (!isCreate()) {
        <div class="bea-admin-actions">
          @if (isActive() && !locked()) {
            <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="saving()" (click)="setActive(false)">Désactiver</button>
          }
          @if (!isActive() && !locked()) {
            <button type="button" class="bea-admin-btn" [disabled]="saving()" (click)="setActive(true)">Réactiver</button>
          }
          @if (!locked()) {
            <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="saving()" (click)="askDelete()">Supprimer</button>
          }
        </div>
        <section class="bea-admin-panel">
          <h2>Modules rattachés</h2>
          @if (modules().length === 0) {
            <p class="bea-admin-panel__empty">Aucun module dans ce département.</p>
          } @else {
            <div class="bea-admin-tiles">
              @for (mod of modules(); track mod.id) {
                <a class="bea-admin-tile" [routerLink]="['/admin/modules', mod.id]">
                  <strong>{{ mod.label }}</strong>
                  <span>{{ mod.code }}</span>
                </a>
              }
            </div>
          }
        </section>
      }
    </section>
  `,
})
export class CoreAdminDepartmentFicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly isCreate = signal(true);
  readonly isView = signal(false);
  readonly saving = signal(false);
  readonly locked = signal(false);
  readonly isActive = signal(true);
  readonly espaceId = signal<string | null>(null);
  readonly modules = signal<CoreAdminModuleSummary[]>([]);
  readonly erreur = signal<string | null>(null);
  readonly statut = signal('bientot');

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.minLength(2)]],
    label: ['', Validators.required],
    description: [''],
    route: [''],
    statut: ['bientot'],
    sort_order: [0],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const url = this.router.url;
    this.isCreate.set(!id);
    this.isView.set(!!id && !url.includes('/modifier'));
    this.espaceId.set(id);
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
    if (id) {
      this.api.get<CoreAdminEspaceFiche>(`/plateforme/admin/departments/${id}`).subscribe({
        next: (row) => this.fill(row),
        error: (err) => this.erreur.set(coreAdminCatalogueError(err, 'Département introuvable.')),
      });
    }
  }

  statutOf(): string {
    return catalogueStatut({ is_active: this.isActive(), statut: this.statut() });
  }

  statutLabel(): string {
    return catalogueStatutLabel(this.statutOf());
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
        ? `Créer le département « ${value.label} » (${value.code}) ?`
        : `Enregistrer les modifications de « ${value.label} » ?`,
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
      route: value.route.trim() || null,
      statut: value.statut,
      sort_order: Number(value.sort_order) || 0,
    };
    if (this.isCreate()) {
      this.api
        .post<CoreAdminEspaceFiche>('/plateforme/admin/departments', { ...body, code: value.code.trim().toLowerCase() })
        .subscribe({
          next: (created) => {
            this.saving.set(false);
            void this.dialogs.success(`« ${created.label} » a été créé.`).then(() => {
              void this.router.navigate(['/admin/departments', created.id]);
            });
          },
          error: (err) => {
            this.saving.set(false);
            void this.dialogs.error(coreAdminCatalogueError(err, 'Création impossible.'));
          },
        });
      return;
    }
    const id = this.espaceId();
    if (!id) {
      return;
    }
    this.api.patch<CoreAdminEspaceFiche>(`/plateforme/admin/departments/${id}`, body).subscribe({
      next: (row) => {
        this.saving.set(false);
        this.fill(row);
        void this.dialogs.success(`« ${row.label} » a été enregistré.`).then(() => {
          void this.router.navigate(['/admin/departments', id]);
        });
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Enregistrement impossible.'));
      },
    });
  }

  async setActive(active: boolean): Promise<void> {
    const id = this.espaceId();
    if (!id || this.saving()) {
      return;
    }
    const label = this.form.controls.label.value;
    const ok = await this.dialogs.confirm({
      title: active ? 'Confirmer la réactivation' : 'Confirmer la désactivation',
      message: active ? `Réactiver « ${label} » ?` : `Désactiver « ${label} » ?`,
      confirmLabel: active ? 'Réactiver' : 'Désactiver',
      tone: active ? 'primary' : 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    const path = active ? 'activate' : 'deactivate';
    this.api.post<CoreAdminEspaceFiche>(`/plateforme/admin/departments/${id}/${path}`, {}).subscribe({
      next: (row) => {
        this.saving.set(false);
        this.fill(row);
        void this.dialogs.success(active ? `« ${label} » a été réactivé.` : `« ${label} » a été désactivé.`);
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Action impossible.'));
      },
    });
  }

  async askDelete(): Promise<void> {
    const id = this.espaceId();
    if (!id || this.saving()) {
      return;
    }
    const label = this.form.controls.label.value;
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer « ${label} » ? Impossible s’il reste des modules ou des accès.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.api.delete(`/plateforme/admin/departments/${id}`).subscribe({
      next: () => {
        this.saving.set(false);
        void this.dialogs.success(`« ${label} » a été supprimé.`).then(() => {
          void this.router.navigate(['/admin/departments']);
        });
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Suppression impossible.'));
      },
    });
  }

  private fill(row: CoreAdminEspaceFiche): void {
    this.locked.set(row.locked);
    this.isActive.set(row.is_active);
    this.statut.set(row.statut);
    this.modules.set(row.modules ?? []);
    this.form.patchValue({
      code: row.code,
      label: row.label,
      description: row.description || '',
      route: row.route || '',
      statut: row.statut,
      sort_order: row.sort_order,
    });
    this.form.controls.code.disable({ emitEvent: false });
    if (row.locked) {
      this.form.controls.route.disable({ emitEvent: false });
      this.form.controls.statut.disable({ emitEvent: false });
    }
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
  }
}
