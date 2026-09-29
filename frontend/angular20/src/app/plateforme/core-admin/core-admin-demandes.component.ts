import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminEspaceOption } from './core-admin-catalogue.models';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { feedbackSignal } from '../../core/feedback/feedback-signal';

interface RequestType {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  icon?: string | null;
  form_schema?: Record<string, unknown> | null;
  active: boolean;
  owner_espace_code: string;
  target_espace_code: string;
  source_espaces?: string[] | null;
  requires_stock_check: boolean;
  requires_purchase: boolean;
  can_create_purchase?: boolean;
  requires_attachment?: boolean;
  sort_order: number;
}

interface TypeForm {
  code: string;
  name: string;
  description: string;
  owner_espace_code: string;
  target_espace_code: string;
  source_espaces: string;
  requires_stock_check: boolean;
  requires_purchase: boolean;
  active: boolean;
  sort_order: number;
}

interface TypeExtra {
  icon: string | null;
  form_schema: Record<string, unknown> | null;
  can_create_purchase: boolean;
  requires_attachment: boolean;
}

function blankForm(): TypeForm {
  return {
    code: '',
    name: '',
    description: '',
    owner_espace_code: 'moyens-generaux',
    target_espace_code: 'moyens-generaux',
    source_espaces: '*',
    requires_stock_check: false,
    requires_purchase: true,
    active: true,
    sort_order: 10,
  };
}

function blankExtra(): TypeExtra {
  return {
    icon: null,
    form_schema: null,
    can_create_purchase: true,
    requires_attachment: false,
  };
}

@Component({
  selector: 'bea-core-admin-demandes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Demandes</h1>
          <p>Types du moteur central : département propriétaire, destinataire et espaces sources.</p>
        </div>
        <button type="button" class="bea-admin-btn" (click)="reset()">Nouveau type</button>
      </header>


      <div class="bea-demandes">
        <div class="bea-admin-panel bea-admin-users__list">
          <div class="bea-admin-users__list-head">
            <h2>Types configurés</h2>
            <p>{{ types().length }} type(s).</p>
          </div>
          @if (!types().length) {
            <p class="bea-admin-panel__empty">Aucun type configuré.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Nom</th>
                    <th>Propriétaire</th>
                    <th>Destinataire</th>
                    <th>Stock</th>
                    <th>Actif</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (t of types(); track t.id) {
                    <tr [class.bea-sec-page__row--on]="editingId() === t.id">
                      <td><code>{{ t.code }}</code></td>
                      <td>{{ t.name }}</td>
                      <td>{{ espaceLabel(t.owner_espace_code) }}</td>
                      <td>{{ espaceLabel(t.target_espace_code) }}</td>
                      <td>
                        <span class="bea-badge" [class.bea-badge--info]="t.requires_stock_check" [class.bea-badge--bientot]="!t.requires_stock_check">
                          {{ t.requires_stock_check ? 'Oui' : 'Non' }}
                        </span>
                      </td>
                      <td>
                        <span class="bea-badge" [class.bea-badge--actif]="t.active" [class.bea-badge--inactif]="!t.active">
                          {{ t.active ? 'Oui' : 'Non' }}
                        </span>
                      </td>
                      <td>
                        <button type="button" class="bea-admin-icon-btn" (click)="edit(t)" title="Modifier" aria-label="Modifier {{ t.name }}">
                          <bea-admin-icon name="edit" />
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </div>

        <form id="type-form" class="bea-admin-form" (ngSubmit)="save()">
          <section class="bea-admin-panel">
            <h2>{{ editingId() ? 'Mettre à jour le type' : 'Créer un type' }}</h2>
            <p class="bea-admin-panel__hint">
              Un code déjà existant pour le même propriétaire met à jour le type. Le bouton Modifier reprend les valeurs d’une ligne.
            </p>
            <div class="bea-admin-grid">
              <label class="bea-admin-field">
                <span>Code</span>
                <input name="code" [(ngModel)]="form.code" required maxlength="40" placeholder="FOURNITURES" autocomplete="off" />
              </label>
              <label class="bea-admin-field">
                <span>Nom</span>
                <input name="name" [(ngModel)]="form.name" required maxlength="120" />
              </label>
              <label class="bea-admin-field">
                <span>Ordre</span>
                <input name="sort" type="number" min="0" [(ngModel)]="form.sort_order" />
              </label>
              <label class="bea-admin-field">
                <span>Espace propriétaire</span>
                <select name="owner" [(ngModel)]="form.owner_espace_code">
                  @for (espace of choices(form.owner_espace_code); track espace.code) {
                    <option [value]="espace.code">{{ espace.label }}</option>
                  }
                </select>
              </label>
              <label class="bea-admin-field">
                <span>Espace destinataire</span>
                <select name="target" [(ngModel)]="form.target_espace_code">
                  @for (espace of choices(form.target_espace_code); track espace.code) {
                    <option [value]="espace.code">{{ espace.label }}</option>
                  }
                </select>
              </label>
              <label class="bea-admin-field bea-admin-toolbar__search">
                <span>Espaces sources</span>
                <input name="sources" [(ngModel)]="form.source_espaces" placeholder="* ou codes séparés par des virgules" />
              </label>
              <label class="bea-admin-field bea-admin-toolbar__search">
                <span>Description</span>
                <textarea name="description" rows="3" [(ngModel)]="form.description"></textarea>
              </label>
              <div class="bea-admin-toolbar__search bea-admin-checks">
                <label class="bea-admin-check" [class.bea-admin-check--on]="form.requires_stock_check">
                  <input type="checkbox" name="stock" [(ngModel)]="form.requires_stock_check" />
                  Contrôle stock
                </label>
                <label class="bea-admin-check" [class.bea-admin-check--on]="form.requires_purchase">
                  <input type="checkbox" name="purchase" [(ngModel)]="form.requires_purchase" />
                  Peut déclencher un achat
                </label>
                <label class="bea-admin-check" [class.bea-admin-check--on]="form.active">
                  <input type="checkbox" name="active" [(ngModel)]="form.active" />
                  Actif
                </label>
              </div>
            </div>
            <p class="bea-admin-panel__hint">* dans les espaces sources = tous les départements.</p>
          </section>
          <div class="bea-admin-form__actions">
            <button type="submit" class="bea-admin-btn" [disabled]="saving()">
              {{ saving() ? 'Enregistrement…' : 'Enregistrer' }}
            </button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reset()">Réinitialiser</button>
          </div>
        </form>
      </div>
    </section>
  `,
  styles: `
    .bea-demandes {
      display: grid;
      gap: 1rem;
      min-width: 0;
    }

    .bea-demandes > * {
      min-width: 0;
    }
  `,
})
export class CoreAdminDemandesComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly types = signal<RequestType[]>([]);
  readonly espaces = signal<CoreAdminEspaceOption[]>([]);
  readonly erreur = feedbackSignal('error', '');
  readonly ok = feedbackSignal('success', '');
  readonly saving = signal(false);
  readonly editingId = signal<string | null>(null);
  form: TypeForm = blankForm();
  private extra: TypeExtra = blankExtra();

  ngOnInit(): void {
    this.load();
    this.api.get<{ espaces: CoreAdminEspaceOption[] }>('/plateforme/admin/modules/options').subscribe({
      next: (res) => this.espaces.set(res.espaces ?? []),
      error: () => this.espaces.set([]),
    });
  }

  choices(current: string): Array<{ code: string; label: string }> {
    const rows = this.espaces().map((espace) => ({ code: espace.code, label: espace.label }));
    if (current && !rows.some((row) => row.code === current)) {
      rows.unshift({ code: current, label: current });
    }
    return rows;
  }

  espaceLabel(code: string): string {
    return this.espaces().find((espace) => espace.code === code)?.label || code;
  }

  edit(row: RequestType): void {
    this.editingId.set(row.id);
    this.erreur.set('');
    this.ok.set('');
    this.form = {
      code: row.code,
      name: row.name,
      description: row.description || '',
      owner_espace_code: row.owner_espace_code,
      target_espace_code: row.target_espace_code,
      source_espaces: (row.source_espaces?.length ? row.source_espaces : ['*']).join(', '),
      requires_stock_check: row.requires_stock_check,
      requires_purchase: row.requires_purchase,
      active: row.active,
      sort_order: row.sort_order,
    };
    this.extra = {
      icon: row.icon ?? null,
      form_schema: row.form_schema ?? null,
      can_create_purchase: row.can_create_purchase ?? true,
      requires_attachment: row.requires_attachment ?? false,
    };
    queueMicrotask(() => document.getElementById('type-form')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
  }

  reset(): void {
    this.editingId.set(null);
    this.form = blankForm();
    this.extra = blankExtra();
    this.erreur.set('');
    this.ok.set('');
  }

  load(): void {
    this.api.get<RequestType[]>('/plateforme/admin/request-types').subscribe({
      next: (rows) => this.types.set(rows || []),
      error: (e) => this.erreur.set(e?.error?.detail || 'Chargement impossible'),
    });
  }

  save(): void {
    const sources = this.form.source_espaces
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean);
    this.saving.set(true);
    this.erreur.set('');
    this.ok.set('');
    this.api.post<RequestType>('/plateforme/admin/request-types', {
      code: this.form.code.trim(),
      name: this.form.name.trim(),
      description: this.form.description.trim() || null,
      owner_espace_code: this.form.owner_espace_code,
      target_espace_code: this.form.target_espace_code,
      source_espaces: sources.length ? sources : ['*'],
      requires_stock_check: this.form.requires_stock_check,
      requires_purchase: this.form.requires_purchase,
      active: this.form.active,
      sort_order: Number(this.form.sort_order) || 0,
      ...this.extra,
    }).subscribe({
      next: () => {
        this.saving.set(false);
        this.reset();
        this.ok.set('Type enregistré.');
        this.load();
      },
      error: (e) => {
        this.erreur.set(typeof e?.error?.detail === 'string' ? e.error.detail : 'Enregistrement impossible');
        this.saving.set(false);
      },
    });
  }
}
