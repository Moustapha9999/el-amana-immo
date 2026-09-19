import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CoreAdminAlertPage, coreAdminOpsError } from './core-admin-ops.models';

@Component({
  selector: 'bea-core-admin-alerts',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Alertes</h1>
          <p>
            Tentatives de connexion (<code>auth_login_attempts</code>) — fenêtre de lockout
            {{ lockoutWindow() }} min / {{ lockoutMax() }} échecs.
          </p>
        </div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/security">Sécurité</a>
      </header>

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of [
            { label: 'Échecs fenêtre', value: k.echecs_fenetre, icon: 'warning', tone: 'rose' },
            { label: 'Succès fenêtre', value: k.succes_fenetre, icon: 'check_circle', tone: 'green' },
            { label: 'E-mails suspects', value: k.emails_suspects, icon: 'person_off', tone: 'amber' },
            { label: 'Total journal', value: k.total, icon: 'history', tone: 'blue' },
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
          <input type="search" formControlName="search" placeholder="E-mail, IP, module…" />
        </label>
        <label class="bea-admin-field">
          <span>Type</span>
          <select formControlName="kind">
            <option value="echecs">Échecs</option>
            <option value="succes">Succès</option>
            <option value="fenetre">Fenêtre lockout</option>
            <option value="tous">Tous</option>
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
        <p class="bea-admin-dash__loading">Chargement des alertes…</p>
      } @else {
        <div class="bea-admin-panel">
          <div class="bea-admin-users__list-head">
            <h2>Tentatives</h2>
            <p>{{ total() }} résultat(s).</p>
          </div>
          <div class="bea-admin-table-wrap">
            <table class="bea-admin-table">
              <thead>
                <tr>
                  <th>Quand</th>
                  <th>E-mail</th>
                  <th>Type</th>
                  <th>Module</th>
                  <th>IP</th>
                  <th>Résultat</th>
                </tr>
              </thead>
              <tbody>
                @for (row of rows(); track row.id) {
                  <tr>
                    <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}</td>
                    <td>{{ row.email }}</td>
                    <td>{{ row.login_kind === 'module' ? 'Module' : 'BEA DIGITAL' }}</td>
                    <td>{{ row.module_code || '—' }}</td>
                    <td><code>{{ row.ip_address || '—' }}</code></td>
                    <td>
                      <span class="bea-badge" [class.bea-badge--actif]="row.success" [class.bea-badge--inactif]="!row.success">
                        {{ row.success ? 'Succès' : 'Échec' }}
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
export class CoreAdminAlertsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly rows = signal<CoreAdminAlertPage['items']>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 20;
  readonly kpis = signal<CoreAdminAlertPage['kpis'] | null>(null);
  readonly lockoutWindow = signal(15);
  readonly lockoutMax = signal(5);
  readonly filters = this.fb.nonNullable.group({ search: '', kind: 'echecs' });
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  ngOnInit(): void {
    this.reload();
  }

  search(): void {
    this.page.set(1);
    this.reload();
  }

  reset(): void {
    this.filters.reset({ search: '', kind: 'echecs' });
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
    const params: Record<string, string | number> = { page: this.page(), size: this.size, kind: v.kind };
    if (v.search.trim()) {
      params['search'] = v.search.trim();
    }
    this.api.get<CoreAdminAlertPage>('/plateforme/admin/alerts', params).subscribe({
      next: (data) => {
        this.rows.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.kpis.set(data.kpis ?? null);
        this.lockoutWindow.set(data.lockout_window_minutes ?? 15);
        this.lockoutMax.set(data.lockout_max_failures ?? 5);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger les alertes.'));
      },
    });
  }
}
