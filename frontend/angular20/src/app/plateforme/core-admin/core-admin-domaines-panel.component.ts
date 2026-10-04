import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CoreAdminDomaineRow,
  ICON_NAME_PATTERN,
  catalogueStatutLabel,
  coreAdminCatalogueError,
} from './core-admin-catalogue.models';

/**
 * Domaines / sous-domaines d'un département (organisation de la page hub, 2 niveaux).
 * L'accès reste porté par les modules (grants) — un domaine ne donne aucun droit.
 */
@Component({
  selector: 'bea-core-admin-domaines-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-panel">
      <div class="bea-admin-users__list-head">
        <h2>Domaines</h2>
        @if (editing() === null) {
          <button type="button" class="bea-admin-btn" [disabled]="saving()" (click)="startCreate()">Ajouter un domaine</button>
        }
      </div>
      <p class="bea-admin-note">
        Regroupement visuel sur la page du département (domaine → sous-domaine → modules).
        Aucun droit n’est attaché à un domaine : l’accès reste géré par module.
        Un domaine inactif masque ses sous-domaines et ses modules du hub.
      </p>

      @if (editing() !== null) {
        <form class="bea-admin-form" [formGroup]="form" (ngSubmit)="save()">
          <div class="bea-admin-grid">
            <label class="bea-admin-field">
              <span>Code</span>
              <input type="text" formControlName="code" placeholder="ex. kyc" />
            </label>
            <label class="bea-admin-field">
              <span>Libellé</span>
              <input type="text" formControlName="label" />
            </label>
            <label class="bea-admin-field">
              <span>Domaine parent</span>
              <select formControlName="parent_id">
                <option value="">— Premier niveau —</option>
                @for (opt of parentOptions(); track opt.id) {
                  <option [value]="opt.id">{{ opt.label }}</option>
                }
              </select>
            </label>
            <label class="bea-admin-field">
              <span>Statut</span>
              <select formControlName="statut">
                <option value="actif">Actif</option>
                <option value="bientot">Bientôt</option>
                <option value="developpement">En développement</option>
                <option value="inactif">Inactif</option>
              </select>
            </label>
            <label class="bea-admin-field">
              <span>Icône (Material Icons)</span>
              <input type="text" formControlName="icon" placeholder="ex. shield" />
              @if (form.controls.icon.invalid) {
                <span class="bea-admin-note">Minuscules, chiffres et « _ » uniquement.</span>
              }
            </label>
            <label class="bea-admin-field">
              <span>Ordre</span>
              <input type="number" formControlName="sort_order" min="0" />
            </label>
            <label class="bea-admin-field bea-admin-toolbar__search">
              <span>Description</span>
              <textarea formControlName="description" rows="2"></textarea>
            </label>
            <label class="bea-admin-field bea-admin-toolbar__search">
              <span>Message d’attente (si non actif)</span>
              <input type="text" formControlName="status_message" placeholder="ex. Domaine en cours de cadrage." />
            </label>
          </div>
          <div class="bea-admin-form__actions">
            <button type="submit" class="bea-admin-btn" [disabled]="saving()">
              {{ saving() ? 'Enregistrement…' : editing() === 'new' ? 'Créer le domaine' : 'Enregistrer le domaine' }}
            </button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="saving()" (click)="cancel()">Annuler</button>
          </div>
        </form>
      }

      @if (ordered().length === 0) {
        <p class="bea-admin-panel__empty">Aucun domaine : le hub affiche directement la grille des modules.</p>
      } @else {
        <div class="bea-admin-table-wrap">
          <table class="bea-admin-table">
            <thead>
              <tr>
                <th>Domaine</th>
                <th>Code</th>
                <th>Ordre</th>
                <th>Modules</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (row of ordered(); track row.id) {
                <tr>
                  <td>
                    <span [style.padding-left.rem]="row.parent_id ? 1.5 : 0" style="display:inline-flex;align-items:center;gap:.45rem">
                      @if (row.icon) {
                        <bea-admin-icon [name]="row.icon" />
                      }
                      {{ row.label }}
                    </span>
                  </td>
                  <td><code>{{ row.code }}</code></td>
                  <td>{{ row.sort_order }}</td>
                  <td>{{ row.modules_count }}</td>
                  <td>
                    <span
                      class="bea-badge"
                      [class.bea-badge--actif]="row.statut === 'actif'"
                      [class.bea-badge--bientot]="row.statut === 'bientot'"
                      [class.bea-badge--info]="row.statut === 'developpement'"
                      [class.bea-badge--inactif]="row.statut === 'inactif'"
                    >
                      {{ statutLabel(row.statut) }}
                    </span>
                  </td>
                  <td class="bea-admin-table__actions">
                    <div class="bea-admin-row-actions">
                      <button type="button" class="bea-admin-icon-btn" [disabled]="saving()" (click)="startEdit(row)" title="Éditer" aria-label="Éditer">
                        <bea-admin-icon name="edit" />
                      </button>
                      @if (row.is_active) {
                        <button type="button" class="bea-admin-icon-btn" [disabled]="saving()" (click)="setActive(row, false)" title="Désactiver" aria-label="Désactiver">
                          <bea-admin-icon name="block" />
                        </button>
                      } @else {
                        <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--ok" [disabled]="saving()" (click)="setActive(row, true)" title="Réactiver" aria-label="Réactiver">
                          <bea-admin-icon name="check_circle" />
                        </button>
                      }
                      <button type="button" class="bea-admin-icon-btn" [disabled]="saving()" (click)="askDelete(row)" title="Supprimer" aria-label="Supprimer">
                        <bea-admin-icon name="delete" />
                      </button>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>
  `,
})
export class CoreAdminDomainesPanelComponent {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  private readonly fb = inject(FormBuilder);

  readonly espaceId = input.required<string>();
  readonly domaines = input<CoreAdminDomaineRow[]>([]);
  /** Émis après chaque écriture confirmée par le backend (le parent recharge sa fiche). */
  readonly changed = output<void>();

  /** `null` = pas de formulaire, `'new'` = création, sinon id du domaine édité. */
  readonly editing = signal<string | null>(null);
  readonly saving = signal(false);

  readonly isDirty = unsavedChanges(() => this.editing() !== null && this.form.dirty && !this.saving(), () => this.form);

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.minLength(2), Validators.pattern(/^[a-z0-9][a-z0-9_-]*$/)]],
    label: ['', Validators.required],
    parent_id: [''],
    statut: ['bientot'],
    icon: ['', Validators.pattern(ICON_NAME_PATTERN)],
    sort_order: [0],
    description: [''],
    status_message: [''],
  });

  /** Parents d'abord, chaque parent suivi de ses sous-domaines. */
  readonly ordered = computed(() => {
    const all = this.domaines();
    const byOrder = (a: CoreAdminDomaineRow, b: CoreAdminDomaineRow) =>
      a.sort_order - b.sort_order || a.label.localeCompare(b.label);
    const roots = all.filter((d) => !d.parent_id).sort(byOrder);
    const out: CoreAdminDomaineRow[] = [];
    for (const root of roots) {
      out.push(root);
      out.push(...all.filter((d) => d.parent_id === root.id).sort(byOrder));
    }
    const orphans = all.filter((d) => !out.includes(d));
    return [...out, ...orphans];
  });

  /** Seuls les domaines de premier niveau (≠ domaine édité) peuvent être parents. */
  readonly parentOptions = computed(() => {
    const current = this.editing();
    return this.domaines().filter((d) => !d.parent_id && d.id !== current);
  });

  statutLabel(statut: string): string {
    return catalogueStatutLabel(statut);
  }

  startCreate(): void {
    this.form.reset({
      code: '',
      label: '',
      parent_id: '',
      statut: 'bientot',
      icon: '',
      sort_order: this.domaines().length + 1,
      description: '',
      status_message: '',
    });
    this.form.controls.code.enable({ emitEvent: false });
    this.editing.set('new');
  }

  startEdit(row: CoreAdminDomaineRow): void {
    this.form.reset({
      code: row.code,
      label: row.label,
      parent_id: row.parent_id ?? '',
      statut: row.statut,
      icon: row.icon ?? '',
      sort_order: row.sort_order,
      description: row.description || '',
      status_message: row.status_message || '',
    });
    this.form.controls.code.disable({ emitEvent: false });
    if (row.children_count > 0) {
      this.form.controls.parent_id.disable({ emitEvent: false });
    } else {
      this.form.controls.parent_id.enable({ emitEvent: false });
    }
    this.editing.set(row.id);
  }

  async cancel(): Promise<void> {
    if (this.form.dirty) {
      const ok = await this.dialogs.confirm({
        title: 'Abandonner les modifications',
        message: 'Les modifications du domaine ne seront pas enregistrées.',
        confirmLabel: 'Abandonner',
        tone: 'danger',
      });
      if (!ok) {
        return;
      }
    }
    this.form.markAsPristine();
    this.editing.set(null);
  }

  async save(): Promise<void> {
    const editing = this.editing();
    if (editing === null || this.saving() || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    const isNew = editing === 'new';
    const ok = await this.dialogs.confirm({
      title: isNew ? 'Confirmer la création' : 'Confirmer la modification',
      message: isNew
        ? `Créer le domaine « ${value.label} » (${value.code}) ?`
        : `Enregistrer les modifications du domaine « ${value.label} » ?`,
      confirmLabel: isNew ? 'Créer' : 'Enregistrer',
    });
    if (!ok) {
      return;
    }
    const body: Record<string, unknown> = {
      label: value.label.trim(),
      description: value.description.trim(),
      statut: value.statut,
      icon: value.icon.trim() || null,
      sort_order: Number(value.sort_order) || 0,
      status_message: value.status_message.trim(),
    };
    if (isNew || this.form.controls.parent_id.enabled) {
      body['parent_id'] = value.parent_id || null;
    }
    this.saving.set(true);
    const request$ = isNew
      ? this.api.post<CoreAdminDomaineRow>('/plateforme/admin/domaines', {
          ...body,
          code: value.code.trim().toLowerCase(),
          espace_id: this.espaceId(),
        })
      : this.api.patch<CoreAdminDomaineRow>(`/plateforme/admin/domaines/${editing}`, body);
    request$.subscribe({
      next: (row) => {
        this.saving.set(false);
        this.form.markAsPristine();
        this.editing.set(null);
        this.changed.emit();
        void this.dialogs.success(isNew ? `Le domaine « ${row.label} » a été créé.` : `Le domaine « ${row.label} » a été enregistré.`);
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, isNew ? 'Création impossible.' : 'Enregistrement impossible.'));
      },
    });
  }

  async setActive(row: CoreAdminDomaineRow, active: boolean): Promise<void> {
    if (this.saving()) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: active ? 'Confirmer la réactivation' : 'Confirmer la désactivation',
      message: active
        ? `Réactiver le domaine « ${row.label} » ?`
        : `Désactiver le domaine « ${row.label} » ? Ses sous-domaines et modules disparaîtront du hub (les accès sont conservés).`,
      confirmLabel: active ? 'Réactiver' : 'Désactiver',
      tone: active ? 'primary' : 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    const action = active ? 'activate' : 'deactivate';
    this.api.post<CoreAdminDomaineRow>(`/plateforme/admin/domaines/${row.id}/${action}`, {}).subscribe({
      next: () => {
        this.saving.set(false);
        this.changed.emit();
        void this.dialogs.success(active ? `« ${row.label} » a été réactivé.` : `« ${row.label} » a été désactivé.`);
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Action impossible.'));
      },
    });
  }

  async askDelete(row: CoreAdminDomaineRow): Promise<void> {
    if (this.saving()) {
      return;
    }
    const ok = await this.dialogs.confirm({
      title: 'Confirmer la suppression',
      message: `Supprimer le domaine « ${row.label} » ? Impossible s’il reste des sous-domaines ou des modules rattachés.`,
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) {
      return;
    }
    this.saving.set(true);
    this.api.delete(`/plateforme/admin/domaines/${row.id}`).subscribe({
      next: () => {
        this.saving.set(false);
        if (this.editing() === row.id) {
          this.editing.set(null);
        }
        this.changed.emit();
        void this.dialogs.success(`Le domaine « ${row.label} » a été supprimé.`);
      },
      error: (err) => {
        this.saving.set(false);
        void this.dialogs.error(coreAdminCatalogueError(err, 'Suppression impossible.'));
      },
    });
  }
}
