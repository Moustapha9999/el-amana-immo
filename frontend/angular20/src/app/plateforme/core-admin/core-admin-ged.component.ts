import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CoreAdminGedPage, coreAdminOpsError } from './core-admin-ops.models';

@Component({
  selector: 'bea-core-admin-ged',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>GED</h1>
          <p>
            Table <code>ged_documents</code> réservée — pas encore branchée aux modules. Les pièces immo restent hors
            GED.
          </p>
        </div>
      </header>

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of [
            { label: 'Documents', value: k.total, icon: 'folder', tone: 'blue' },
            { label: 'Modules', value: k.modules, icon: 'apps', tone: 'teal' },
            { label: 'Volume (Ko)', value: Math.round(k.taille_octets / 1024), icon: 'hard_drive', tone: 'amber' },
          ]; track card.label; let i = $index) {
            <div class="bea-admin-kpi" [attr.data-tone]="card.tone" [style.animation-delay]="i * 60 + 'ms'">
              <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="card.icon" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">{{ card.label }}</p>
                <p class="bea-admin-kpi__value">{{ card.value }}</p>
              </div>
            </div>
          }
        </div>
        @if (k.reservee) {
          <p class="bea-admin-note">GED en lecture seule pour l’instant — upload métier à brancher module par module.</p>
        }
      }

      <form class="bea-admin-toolbar" [formGroup]="filters" (ngSubmit)="search()">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input type="search" formControlName="search" placeholder="Fichier, entité, module…" />
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="submit" class="bea-admin-btn">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reset()">Réinitialiser</button>
        </div>
      </form>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement GED…</p>
      } @else {
        <div class="bea-admin-panel">
          <div class="bea-admin-users__list-head">
            <h2>Documents</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          @if (rows().length === 0) {
            <p class="bea-admin-panel__empty">Aucun document GED enregistré.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Fichier</th>
                    <th>Espace</th>
                    <th>Module</th>
                    <th>Entité</th>
                    <th>Taille</th>
                    <th>Créé</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>{{ row.filename }}</td>
                      <td>{{ row.espace_code }}</td>
                      <td>{{ row.module_code }}</td>
                      <td class="bea-admin-table__clip">{{ row.entity }} · {{ row.entity_id }}</td>
                      <td>{{ row.size_bytes }} o</td>
                      <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
          <div class="bea-admin-pager">
            <span>Page {{ page() }} / {{ totalPages() }}</span>
            <div>
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="go(page() - 1)">
                Précédent
              </button>
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages()" (click)="go(page() + 1)">
                Suivant
              </button>
            </div>
          </div>
        </div>
      }
    </section>
  `,
})
export class CoreAdminGedComponent implements OnInit {
  readonly Math = Math;
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly rows = signal<CoreAdminGedPage['items']>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 20;
  readonly kpis = signal<CoreAdminGedPage['kpis'] | null>(null);
  readonly filters = this.fb.nonNullable.group({ search: '' });
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  ngOnInit(): void {
    this.reload();
  }

  search(): void {
    this.page.set(1);
    this.reload();
  }

  reset(): void {
    this.filters.reset({ search: '' });
    this.page.set(1);
    this.reload();
  }

  go(page: number): void {
    this.page.set(page);
    this.reload();
  }

  private reload(): void {
    this.loading.set(true);
    const v = this.filters.getRawValue();
    const params: Record<string, string | number> = { page: this.page(), size: this.size };
    if (v.search.trim()) {
      params['search'] = v.search.trim();
    }
    this.api.get<CoreAdminGedPage>('/plateforme/admin/ged', params).subscribe({
      next: (data) => {
        this.rows.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.kpis.set(data.kpis ?? null);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger la GED.'));
      },
    });
  }
}
