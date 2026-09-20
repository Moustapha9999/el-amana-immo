import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import {
  CoreAdminEspaceOption,
  CoreAdminModuleRow,
  catalogueStatut,
  catalogueStatutLabel,
  coreAdminCatalogueError,
} from './core-admin-catalogue.models';

@Component({
  selector: 'bea-core-admin-module-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-kicker"><a routerLink="/admin/modules">Modules</a></p>
          <h1>
            @if (isCreate()) {
              Nouveau module
            } @else if (isView()) {
              {{ form.controls.label.value || 'Fiche module' }}
            } @else {
              Modifier {{ form.controls.label.value || 'le module' }}
            }
          </h1>
          <p>Module métier rattaché à un département BEA DIGITAL.</p>
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
            @if (isView() && moduleId(); as id) {
              <a class="bea-admin-btn" [routerLink]="['/admin/modules', id, 'modifier']">Éditer</a>
            }
          </div>
        }
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (locked()) {
        <p class="bea-admin-note">Module système Immobilisations : code, département et chemin d’entrée figés.</p>
      }

      @if (!isCreate()) {
        <div class="bea-admin-kpis">
          <article class="bea-admin-kpi" data-tone="org">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Statut</p>
              <p class="bea-admin-kpi__value" style="font-size:1.15rem">{{ statutLabel() }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="modules">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Ordre</p>
              <p class="bea-admin-kpi__value">{{ form.controls.sort_order.value }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="sessions">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Entrée</p>
              <p class="bea-admin-kpi__value" style="font-size:0.95rem">{{ form.controls.entry_path.value || '—' }}</p>
            </div>
          </article>
        </div>
        <section class="bea-admin-panel bea-admin-chart" style="margin-bottom:1rem">
          <div class="bea-admin-users__list-head">
            <h2>Empreinte visuelle</h2>
          </div>
          <div class="bea-admin-bars" aria-hidden="true">
            <div class="bea-admin-bars__col">
              <span class="bea-admin-bars__value">Parc</span>
              <div class="bea-admin-bars__track"><div class="bea-admin-bars__fill" style="height:62%"></div></div>
              <span class="bea-admin-bars__label">A</span>
            </div>
            <div class="bea-admin-bars__col">
              <span class="bea-admin-bars__value">Dot.</span>
              <div class="bea-admin-bars__track"><div class="bea-admin-bars__fill" style="height:78%"></div></div>
              <span class="bea-admin-bars__label">B</span>
            </div>
            <div class="bea-admin-bars__col">
              <span class="bea-admin-bars__value">Ctrl</span>
              <div class="bea-admin-bars__track"><div class="bea-admin-bars__fill" style="height:45%"></div></div>
              <span class="bea-admin-bars__label">C</span>
            </div>
            <div class="bea-admin-bars__col">
              <span class="bea-admin-bars__value">Rep.</span>
              <div class="bea-admin-bars__track"><div class="bea-admin-bars__fill" style="height:88%"></div></div>
              <span class="bea-admin-bars__label">D</span>
            </div>
          </div>
          <p class="bea-admin-chart__foot">Palette BEA — mêmes tons que le dashboard Immobilisations.</p>
        </section>
      }

      <form class="bea-admin-form" [formGroup]="form" (ngSubmit)="save()">
        <section class="bea-admin-panel">
          <h2>Identité</h2>
          <div class="bea-admin-grid">
            <label class="bea-admin-field">
              <span>Code</span>
              <input type="text" formControlName="code" placeholder="ex. rapprochements" />
            </label>
            <label class="bea-admin-field">
              <span>Département</span>
              <select formControlName="espace_id">
                <option value="">Choisir…</option>
                @for (espace of espaces(); track espace.id) {
                  <option [value]="espace.id">{{ espace.label }}</option>
                }
              </select>
            </label>
            <label class="bea-admin-field">
              <span>Libellé</span>
              <input type="text" formControlName="label" />
            </label>
            <label class="bea-admin-field">
              <span>Chemin d’entrée (après Login 2)</span>
              <input type="text" formControlName="entry_path" placeholder="vide = pas encore de shell métier" />
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
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/modules">Retour à la liste</a>
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
      }
    </section>
  `,
})
export class CoreAdminModuleFicheComponent implements OnInit {
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
  readonly moduleId = signal<string | null>(null);
  readonly espaces = signal<CoreAdminEspaceOption[]>([]);
  readonly erreur = signal<string | null>(null);
  readonly statut = signal('bientot');

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.minLength(2)]],
    espace_id: ['', Validators.required],
    label: ['', Validators.required],
    description: [''],
    entry_path: [''],
    statut: ['bientot'],
    sort_order: [0],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const url = this.router.url;
    this.isCreate.set(!id);
    this.isView.set(!!id && !url.includes('/modifier'));
    this.moduleId.set(id);
    this.api.get<{ espaces: CoreAdminEspaceOption[] }>('/plateforme/admin/modules/options').subscribe({
      next: (res) => this.espaces.set(res.espaces ?? []),
      error: () => this.espaces.set([]),
    });
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
    if (id) {
      this.api.get<CoreAdminModuleRow>(`/plateforme/admin/modules/${id}`).subscribe({
        next: (row) => this.fill(row),
        error: (err) => this.erreur.set(coreAdminCatalogueError(err, 'Module introuvable.')),
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
        ? `Créer le module « ${value.label} » (${value.code}) ?`
        : `Enregistrer les modifications de « ${value.label} » ?`,
      confirmLabel: this.isCreate() ? 'Créer' : 'Enregistrer',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    const body = {
      espace_id: value.espace_id,
      label: value.label.trim(),
      description: value.description.trim(),
      entry_path: value.entry_path.trim() || null,
      statut: value.statut,
      sort_order: Number(value.sort_order) || 0,
    };
    if (this.isCreate()) {
      this.api
        .post<CoreAdminModuleRow>('/plateforme/admin/modules', { ...body, code: value.code.trim().toLowerCase() })
        .subscribe({
          next: (created) => {
            this.saving.set(false);
            void this.dialogs.success(`« ${created.label} » a été créé.`).then(() => {
              void this.router.navigate(['/admin/modules', created.id]);
            });
          },
          error: (err) => {
            this.saving.set(false);
            void this.dialogs.error(coreAdminCatalogueError(err, 'Création impossible.'));
          },
        });
      return;
    }
    const id = this.moduleId();
    if (!id) {
      return;
    }
    this.api.patch<CoreAdminModuleRow>(`/plateforme/admin/modules/${id}`, body).subscribe({
      next: (row) => {
        this.saving.set(false);
        this.fill(row);
        void this.dialogs.success(`« ${row.label} » a été enregistré.`).then(() => {
          void this.router.navigate(['/admin/modules', id]);
        });
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Enregistrement impossible.'));
      },
    });
  }

  async setActive(active: boolean): Promise<void> {
    const id = this.moduleId();
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
    this.api.post<CoreAdminModuleRow>(`/plateforme/admin/modules/${id}/${path}`, {}).subscribe({
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
    const id = this.moduleId();
    if (!id || this.saving()) {
      return;
    }
    const label = this.form.controls.label.value;
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer « ${label} » ? Impossible s’il reste des accès utilisateurs.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.api.delete(`/plateforme/admin/modules/${id}`).subscribe({
      next: () => {
        this.saving.set(false);
        void this.dialogs.success(`« ${label} » a été supprimé.`).then(() => {
          void this.router.navigate(['/admin/modules']);
        });
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Suppression impossible.'));
      },
    });
  }

  private fill(row: CoreAdminModuleRow): void {
    this.locked.set(row.locked);
    this.isActive.set(row.is_active);
    this.statut.set(row.statut);
    this.form.patchValue({
      code: row.code,
      espace_id: row.espace_id,
      label: row.label,
      description: row.description || '',
      entry_path: row.entry_path || '',
      statut: row.statut,
      sort_order: row.sort_order,
    });
    this.form.controls.code.disable({ emitEvent: false });
    if (row.locked) {
      this.form.controls.espace_id.disable({ emitEvent: false });
      this.form.controls.entry_path.disable({ emitEvent: false });
      this.form.controls.statut.disable({ emitEvent: false });
    }
    if (this.isView()) {
      this.form.disable({ emitEvent: false });
    }
  }
}
