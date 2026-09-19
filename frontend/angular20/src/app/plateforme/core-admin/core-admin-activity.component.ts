import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CoreAdminActivityPage, coreAdminOpsError } from './core-admin-ops.models';

@Component({
  selector: 'bea-core-admin-activity',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Activité</h1>
          <p>Flux récent <code>audit_logs</code> — vue live distincte du journal Audit complet.</p>
        </div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/audit">Journal Audit</a>
      </header>

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of [
            { label: 'Fenêtre', value: k.total, icon: 'history', tone: 'blue' },
            { label: 'Dernière heure', value: k.derniere_heure, icon: 'schedule', tone: 'teal' },
            { label: 'Aujourd’hui', value: k.aujourd_hui, icon: 'today', tone: 'green' },
            { label: 'Modules', value: k.modules, icon: 'apps', tone: 'amber' },
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
      }

      <form class="bea-admin-toolbar" [formGroup]="filters" (ngSubmit)="search()">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche</span>
          <input type="search" formControlName="search" placeholder="Qui, action, entité…" />
        </label>
        <label class="bea-admin-field">
          <span>Fenêtre</span>
          <select formControlName="hours">
            <option value="24">24 h</option>
            <option value="48">48 h</option>
            <option value="168">7 jours</option>
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
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reset()">Réinitialiser</button>
        </div>
      </form>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement de l’activité…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-panel--list">
          <div class="bea-admin-users__list-head">
            <h2>Flux</h2>
            <p>{{ total() }} événement(s).</p>
          </div>
          <div class="bea-admin-panel__scroll bea-admin-ops__scroll">
            @if (rows().length === 0) {
              <p class="bea-admin-panel__empty">Aucune activité sur cette fenêtre.</p>
            } @else {
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Quand</th>
                    <th>Qui</th>
                    <th>Action</th>
                    <th>Entité</th>
                    <th>Module</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of rows(); track row.id) {
                    <tr>
                      <td>{{ row.created_at | date: 'dd/MM HH:mm' : 'Africa/Nouakchott' }}</td>
                      <td>
                        @if (row.user_id) {
                          <a class="bea-admin-table__link" [routerLink]="['/admin/users', row.user_id]">
                            {{ row.user_full_name || row.user_email }}
                          </a>
                        } @else {
                          Système
                        }
                      </td>
                      <td>{{ row.action }}</td>
                      <td class="bea-admin-table__clip" [title]="row.entity + (row.entity_id ? ' · ' + row.entity_id : '')">
                        {{ row.entity }}{{ row.entity_id ? ' · ' + row.entity_id : '' }}
                      </td>
                      <td>{{ row.module_code || '—' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </div>
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
export class CoreAdminActivityComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly rows = signal<CoreAdminActivityPage['items']>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 30;
  readonly kpis = signal<CoreAdminActivityPage['kpis'] | null>(null);
  readonly filters = this.fb.nonNullable.group({ search: '', hours: '48' });
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  ngOnInit(): void {
    this.reload();
  }

  search(): void {
    this.page.set(1);
    this.reload();
  }

  reset(): void {
    this.filters.reset({ search: '', hours: '48' });
    this.page.set(1);
    this.reload();
  }

  go(page: number): void {
    this.page.set(page);
    this.reload();
  }

  private reload(): void {
    this.loading.set(true);
    this.erreur.set('');
    const v = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.size,
      hours: Number(v.hours) || 48,
    };
    if (v.search.trim()) {
      params['search'] = v.search.trim();
    }
    this.api.get<CoreAdminActivityPage>('/plateforme/admin/activity', params).subscribe({
      next: (data) => {
        this.rows.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.kpis.set(data.kpis ?? null);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger l’activité.'));
      },
    });
  }
}
