import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';

interface RequestType {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  active: boolean;
  owner_espace_code: string;
  target_espace_code: string;
  source_espaces?: string[] | null;
  requires_stock_check: boolean;
  requires_purchase: boolean;
  sort_order: number;
}

@Component({
  selector: 'bea-core-admin-demandes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Demandes</h1>
          <p>Types du moteur central : département propriétaire, destinataire et espaces sources.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-admin-error">{{ erreur() }}</p> }
      @if (ok()) { <p class="bea-admin-ok">{{ ok() }}</p> }

      <div class="bea-admin-panel">
        <table class="bea-admin-table">
          <thead>
            <tr>
              <th>Code</th><th>Nom</th><th>Propriétaire</th><th>Destinataire</th><th>Stock</th><th>Actif</th>
            </tr>
          </thead>
          <tbody>
            @for (t of types(); track t.id) {
              <tr>
                <td>{{ t.code }}</td>
                <td>{{ t.name }}</td>
                <td>{{ t.owner_espace_code }}</td>
                <td>{{ t.target_espace_code }}</td>
                <td>{{ t.requires_stock_check ? 'Oui' : 'Non' }}</td>
                <td>{{ t.active ? 'Oui' : 'Non' }}</td>
              </tr>
            }
          </tbody>
        </table>
        @if (!types().length) { <p>Aucun type configuré.</p> }
      </div>

      <form class="bea-admin-panel" (ngSubmit)="save()">
        <h2>Créer / mettre à jour un type</h2>
        <label>Code <input name="code" [(ngModel)]="form.code" required /></label>
        <label>Nom <input name="name" [(ngModel)]="form.name" required /></label>
        <label>Description <input name="description" [(ngModel)]="form.description" /></label>
        <label>Espace propriétaire <input name="owner" [(ngModel)]="form.owner_espace_code" /></label>
        <label>Espace destinataire <input name="target" [(ngModel)]="form.target_espace_code" /></label>
        <label><input type="checkbox" name="stock" [(ngModel)]="form.requires_stock_check" /> Contrôle stock</label>
        <label><input type="checkbox" name="purchase" [(ngModel)]="form.requires_purchase" /> Peut déclencher un achat</label>
        <label><input type="checkbox" name="active" [(ngModel)]="form.active" /> Actif</label>
        <button type="submit" class="bea-admin-btn" [disabled]="saving()">Enregistrer</button>
      </form>
    </section>
  `,
})
export class CoreAdminDemandesComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly types = signal<RequestType[]>([]);
  readonly erreur = signal('');
  readonly ok = signal('');
  readonly saving = signal(false);
  form = {
    code: '',
    name: '',
    description: '',
    owner_espace_code: 'moyens-generaux',
    target_espace_code: 'moyens-generaux',
    requires_stock_check: false,
    requires_purchase: true,
    active: true,
  };

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.get<RequestType[]>('/plateforme/admin/request-types').subscribe({
      next: (rows) => this.types.set(rows || []),
      error: (e) => this.erreur.set(e?.error?.detail || 'Chargement impossible'),
    });
  }

  save(): void {
    this.saving.set(true);
    this.erreur.set('');
    this.api.post<RequestType>('/plateforme/admin/request-types', {
      ...this.form,
      source_espaces: ['*'],
      sort_order: 10,
    }).subscribe({
      next: () => {
        this.ok.set('Type enregistré.');
        this.saving.set(false);
        this.load();
      },
      error: (e) => {
        this.erreur.set(e?.error?.detail || 'Enregistrement impossible');
        this.saving.set(false);
      },
    });
  }
}
