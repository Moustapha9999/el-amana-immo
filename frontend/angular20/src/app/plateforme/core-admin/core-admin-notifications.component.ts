import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CoreAdminNotificationPage, coreAdminOpsError } from './core-admin-ops.models';

@Component({
  selector: 'bea-core-admin-notifications',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Notifications</h1>
          <p>Vue plateforme de la table <code>notifications</code> — distincte de la cloche utilisateur.</p>
        </div>
      </header>

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of [
            { label: 'Total', value: k.total, icon: 'notifications', tone: 'blue' },
            { label: 'Non lues', value: k.non_lues, icon: 'mark_email_unread', tone: 'amber' },
            { label: 'Lues', value: k.lues, icon: 'mark_email_read', tone: 'green' },
            { label: 'Système', value: k.systeme, icon: 'settings', tone: 'teal' },
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
          <input type="search" formControlName="search" placeholder="Titre, message, destinataire…" />
        </label>
        <label class="bea-admin-field">
          <span>Statut</span>
          <select formControlName="statut">
            <option value="tous">Tous</option>
            <option value="non_lues">Non lues</option>
            <option value="lues">Lues</option>
          </select>
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
        <p class="bea-admin-dash__loading">Chargement des notifications…</p>
      } @else {
        <div class="bea-admin-panel">
          <div class="bea-admin-users__list-head">
            <h2>Liste</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          <div class="bea-admin-table-wrap">
            <table class="bea-admin-table">
              <thead>
                <tr>
                  <th>Quand</th>
                  <th>Destinataire</th>
                  <th>Titre</th>
                  <th>Type</th>
                  <th>Module</th>
                  <th>État</th>
                </tr>
              </thead>
              <tbody>
                @for (row of rows(); track row.id) {
                  <tr>
                    <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}</td>
                    <td>
                      <a class="bea-admin-table__link" [routerLink]="['/admin/users', row.user_id]">
                        {{ row.user_full_name || row.user_email || row.user_id }}
                      </a>
                    </td>
                    <td>
                      <strong>{{ row.titre }}</strong>
                      <div class="bea-admin-sessions__meta">{{ row.message }}</div>
                    </td>
                    <td>{{ row.type_notification }}</td>
                    <td>{{ row.module_code || '—' }}</td>
                    <td>
                      <span class="bea-badge" [class.bea-badge--actif]="!row.lu" [class.bea-badge--bientot]="row.lu">
                        {{ row.lu ? 'Lue' : 'Non lue' }}
                      </span>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
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
export class CoreAdminNotificationsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly rows = signal<CoreAdminNotificationPage['items']>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 20;
  readonly kpis = signal<CoreAdminNotificationPage['kpis'] | null>(null);
  readonly filters = this.fb.nonNullable.group({ search: '', statut: 'tous' });
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  ngOnInit(): void {
    this.reload();
  }

  search(): void {
    this.page.set(1);
    this.reload();
  }

  reset(): void {
    this.filters.reset({ search: '', statut: 'tous' });
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
    const params: Record<string, string | number> = { page: this.page(), size: this.size, statut: v.statut };
    if (v.search.trim()) {
      params['search'] = v.search.trim();
    }
    this.api.get<CoreAdminNotificationPage>('/plateforme/admin/notifications', params).subscribe({
      next: (data) => {
        this.rows.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.kpis.set(data.kpis ?? null);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger les notifications.'));
      },
    });
  }
}
