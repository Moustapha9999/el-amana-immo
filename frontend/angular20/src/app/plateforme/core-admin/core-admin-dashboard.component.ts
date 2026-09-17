import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

export interface CoreAdminKpis {
  utilisateurs: number;
  utilisateurs_actifs: number;
  departements: number;
  modules: number;
  modules_actifs: number;
  sessions_actives: number;
  alertes_securite: number;
  actions_aujourd_hui: number;
}

export interface CoreAdminActivity {
  id: string;
  who: string;
  email?: string | null;
  action: string;
  entity: string;
  entity_id?: string | null;
  module?: string | null;
  espace?: string | null;
  created_at?: string | null;
}

export interface CoreAdminHealth {
  ok: boolean;
  label: string;
}

export interface CoreAdminDashboard {
  kpis: CoreAdminKpis;
  activite: CoreAdminActivity[];
  etat: Record<string, CoreAdminHealth>;
  fuseau: string;
}

@Component({
  selector: 'bea-core-admin-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <h1>Dashboard</h1>
        <p>Compteurs réels de la plateforme. Fuseau {{ fuseau() }}.</p>
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of kpiCards(k); track card.label) {
            @if (card.path) {
              <a class="bea-admin-kpi bea-admin-kpi--link" [routerLink]="card.path">
                <p class="bea-admin-kpi__label">{{ card.label }}</p>
                <p class="bea-admin-kpi__value">{{ card.value }}</p>
                @if (card.hint) {
                  <p class="bea-admin-kpi__hint">{{ card.hint }}</p>
                }
              </a>
            } @else {
              <article class="bea-admin-kpi">
                <p class="bea-admin-kpi__label">{{ card.label }}</p>
                <p class="bea-admin-kpi__value">{{ card.value }}</p>
                @if (card.hint) {
                  <p class="bea-admin-kpi__hint">{{ card.hint }}</p>
                }
              </article>
            }
          }
        </div>
      } @else if (!erreur()) {
        <p class="bea-admin-dash__loading">Chargement des indicateurs…</p>
      }

      <div class="bea-admin-panels">
        <section class="bea-admin-panel">
          <h2>Activité récente</h2>
          @if (activite().length === 0) {
            <p class="bea-admin-panel__empty">Aucune action journalisée pour le moment.</p>
          } @else {
            <table class="bea-admin-table">
              <thead>
                <tr>
                  <th>Qui</th>
                  <th>Action</th>
                  <th>Entité</th>
                  <th>Module</th>
                  <th>Quand</th>
                </tr>
              </thead>
              <tbody>
                @for (row of activite(); track row.id) {
                  <tr>
                    <td>{{ row.who }}</td>
                    <td>{{ row.action }}</td>
                    <td>{{ row.entity }}{{ row.entity_id ? ' · ' + row.entity_id : '' }}</td>
                    <td>{{ row.module || '—' }}</td>
                    <td>
                      @if (row.created_at) {
                        {{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                      } @else {
                        —
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </section>

        <section class="bea-admin-panel">
          <h2>État de la plateforme</h2>
          <ul class="bea-admin-health">
            @for (item of etatList(); track item.key) {
              <li>
                <span
                  class="bea-admin-health__dot"
                  [class.bea-admin-health__dot--ok]="item.ok"
                  [class.bea-admin-health__dot--ko]="!item.ok"
                ></span>
                <span>{{ item.label }}</span>
                <strong>{{ item.ok ? 'OK' : 'KO' }}</strong>
              </li>
            }
          </ul>
        </section>
      </div>
    </section>
  `,
})
export class CoreAdminDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly kpis = signal<CoreAdminKpis | null>(null);
  readonly activite = signal<CoreAdminActivity[]>([]);
  readonly etatList = signal<{ key: string; label: string; ok: boolean }[]>([]);
  readonly fuseau = signal('Africa/Nouakchott');
  readonly erreur = signal<string | null>(null);

  ngOnInit(): void {
    this.api.get<CoreAdminDashboard>('/plateforme/admin/dashboard').subscribe({
      next: (data) => {
        this.kpis.set(data.kpis);
        this.activite.set(data.activite ?? []);
        this.fuseau.set(data.fuseau || 'Africa/Nouakchott');
        const order = ['core', 'api', 'auth', 'db', 'modules'];
        const entries = Object.entries(data.etat ?? {});
        entries.sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
        this.etatList.set(
          entries.map(([key, value]) => ({
            key,
            label: value.label,
            ok: value.ok,
          })),
        );
        this.erreur.set(null);
      },
      error: () => this.erreur.set('Impossible de charger le dashboard CORE ADMIN.'),
    });
  }

  kpiCards(k: CoreAdminKpis): { label: string; value: string; hint?: string; path?: string }[] {
    return [
      {
        label: 'Utilisateurs',
        value: this.fmt(k.utilisateurs),
        hint: `${this.fmt(k.utilisateurs_actifs)} actifs`,
        path: '/admin/users',
      },
      { label: 'Départements', value: this.fmt(k.departements) },
      { label: 'Modules', value: this.fmt(k.modules), hint: `${this.fmt(k.modules_actifs)} actifs` },
      { label: 'Sessions actives', value: this.fmt(k.sessions_actives) },
      { label: 'Alertes sécurité', value: this.fmt(k.alertes_securite) },
      { label: "Actions aujourd'hui", value: this.fmt(k.actions_aujourd_hui) },
    ];
  }

  private fmt(n: number): string {
    return new Intl.NumberFormat('fr-FR').format(n);
  }
}
