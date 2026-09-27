import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter } from 'rxjs/operators';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { EspaceMetier } from '../espaces-metiers';

type EspaceAccueil = EspaceMetier & { accessible?: boolean };
type HubVue = 'admin' | 'responsable' | 'utilisateur';

interface HubKpi {
  key: string;
  label: string;
  value: number;
  hint?: string | null;
}

interface HubSeriePoint {
  date: string;
  label: string;
  count: number;
}

interface HubComponentEtat {
  key: string;
  label: string;
  ok: boolean | null;
  status: string;
  status_label: string;
}

interface HubModule {
  id: string;
  titre: string;
  route?: string | null;
  statut: string;
  espace_titre?: string | null;
}

interface HubSummary {
  vue: HubVue;
  user_full_name?: string | null;
  departements_accessibles: number;
  modules_accessibles: number;
  modules_ouverts: number;
  notifications_non_lues: number;
  sessions_actives: number;
  kpis: HubKpi[];
  etat_plateforme?: {
    ok: boolean;
    verifie_at: string;
    components: HubComponentEtat[];
  } | null;
  activite_jours?: number;
  activite_serie?: HubSeriePoint[];
  modules_recents?: HubModule[];
}

interface HubActivity {
  id: string;
  label: string;
  created_at?: string | null;
  module_code?: string | null;
  espace_code?: string | null;
  who?: string | null;
}

@Component({
  selector: 'bea-accueil',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, NgTemplateOutlet, BeaChromeComponent, DatePipe],
  template: `
    <div class="bea-plateforme">
      <bea-chrome />
      <main class="bea-plateforme__body bea-hub">
        <header class="bea-hub__welcome">
          <div>
            <p class="bea-plateforme__kicker">BEA DIGITAL</p>
            <h1 class="bea-plateforme__title">Bonjour{{ prenom() ? ', ' + prenom() : '' }}</h1>
            <p class="bea-plateforme__lead">{{ lead() }}</p>
          </div>
          @if (canAdmin()) {
            <a class="bea-hub__core" routerLink="/admin">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"
                  stroke="currentColor"
                  stroke-width="1.7"
                />
                <path
                  d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"
                  stroke="currentColor"
                  stroke-width="1.7"
                  stroke-linejoin="round"
                />
              </svg>
              CORE ADMIN
            </a>
          }
        </header>

        <div class="bea-hub__kpis" [attr.data-count]="kpis().length">
          @for (kpi of kpis(); track kpi.key) {
            <article class="bea-hub__kpi">
              <span>{{ kpi.label }}</span>
              <strong>{{ kpi.value }}</strong>
              @if (kpi.hint) {
                <em>{{ kpi.hint }}</em>
              }
            </article>
          }
        </div>

        <section class="bea-hub__section">
          <div class="bea-hub__section-head">
            <h2>Départements accessibles</h2>
            <p>Ouvrez un département pour voir ses modules.</p>
          </div>
          <div class="bea-card-grid bea-card-grid--espaces">
            @for (espace of espaces(); track espace.id; let i = $index) {
              @if (ouvert(espace)) {
                <a
                  class="bea-espace bea-espace--actif"
                  [attr.data-espace]="espace.id"
                  [style.--bea-i]="i"
                  [routerLink]="espace.route"
                >
                  <ng-container *ngTemplateOutlet="card; context: { $implicit: espace }" />
                </a>
              } @else {
                <div
                  class="bea-espace bea-espace--bientot"
                  [attr.data-espace]="espace.id"
                  [style.--bea-i]="i"
                >
                  <ng-container *ngTemplateOutlet="card; context: { $implicit: espace }" />
                </div>
              }
            }
          </div>
        </section>

        @if (vue() === 'utilisateur' && modulesRecents().length) {
          <section class="bea-hub__section">
            <div class="bea-hub__section-head">
              <h2>Modules récents</h2>
              <p>Derniers modules que vous avez utilisés.</p>
            </div>
            <ul class="bea-hub__recents">
              @for (m of modulesRecents(); track m.id) {
                <li>
                  @if (m.route) {
                    <a [routerLink]="m.route">
                      <strong>{{ m.titre }}</strong>
                      <span>{{ m.espace_titre || 'Module' }}</span>
                    </a>
                  } @else {
                    <div>
                      <strong>{{ m.titre }}</strong>
                      <span>{{ m.espace_titre || 'Module' }}</span>
                    </div>
                  }
                </li>
              }
            </ul>
          </section>
        }

        <div
          class="bea-hub__columns bea-hub__columns--dash"
          [class.bea-hub__columns--solo]="vue() !== 'admin'"
        >
          <section class="bea-hub__panel">
            <div class="bea-hub__section-head bea-hub__section-head--row">
              <div>
                <h2>Activité / Utilisation</h2>
                <p>{{ usageLead() }}</p>
              </div>
              <div class="bea-hub__period" role="group" aria-label="Période">
                @for (p of periodes; track p) {
                  <button
                    type="button"
                    class="bea-hub__period-btn"
                    [class.bea-hub__period-btn--on]="jours() === p"
                    (click)="setJours(p)"
                  >
                    {{ p }} j
                  </button>
                }
              </div>
            </div>
            @if (serie().length === 0) {
              <p class="bea-hub__empty">Aucune activité sur cette période.</p>
            } @else {
              <div class="bea-hub__chart" [attr.data-jours]="jours()">
                @for (pt of serie(); track pt.date) {
                  <div class="bea-hub__chart-col" [title]="pt.date + ' · ' + pt.count">
                    <span class="bea-hub__chart-val">{{ pt.count }}</span>
                    <div class="bea-hub__chart-track">
                      <div class="bea-hub__chart-fill" [style.height.%]="barHeight(pt.count)"></div>
                    </div>
                    <span class="bea-hub__chart-label">{{ pt.label }}</span>
                  </div>
                }
              </div>
            }
          </section>

          @if (vue() === 'admin') {
            <section class="bea-hub__panel">
              <div class="bea-hub__section-head">
                <h2>État de la plateforme</h2>
                <p>
                  Dernière vérification :
                  @if (etat()?.verifie_at; as at) {
                    {{ at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                  } @else {
                    —
                  }
                </p>
              </div>
              @if (etat(); as e) {
                <p
                  class="bea-hub__status"
                  [class.bea-hub__status--ok]="e.ok"
                  [class.bea-hub__status--warn]="!e.ok"
                >
                  {{ e.ok ? 'Plateforme opérationnelle' : 'Attention — composant dégradé' }}
                </p>
                <dl class="bea-hub__etat">
                  @for (c of e.components; track c.key) {
                    <div>
                      <dt>{{ c.label }}</dt>
                      <dd [attr.data-status]="c.status">{{ c.status_label }}</dd>
                    </div>
                  }
                </dl>
              } @else {
                <p class="bea-hub__empty">État non disponible.</p>
              }
            </section>
          }
        </div>

        <section class="bea-hub__panel bea-hub__activity">
          <div class="bea-hub__section-head">
            <h2>Activité récente</h2>
            <p>{{ activityLead() }}</p>
          </div>
          @if (activity().length === 0) {
            <p class="bea-hub__empty">Pas encore d’activité enregistrée.</p>
          } @else {
            <ul class="bea-hub__list bea-hub__list--scroll">
              @for (a of activity(); track a.id) {
                <li>
                  <strong>{{ a.label }}</strong>
                  <time>{{ a.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}</time>
                </li>
              }
            </ul>
            @if (activityHasMore()) {
              <button
                type="button"
                class="bea-hub__more"
                [disabled]="activityLoading()"
                (click)="loadMoreActivity()"
              >
                {{ activityLoading() ? 'Chargement…' : 'Voir plus' }}
              </button>
            }
          }
        </section>
      </main>
    </div>

    <ng-template #card let-espace>
      <span class="bea-espace__icon" aria-hidden="true">
        @switch (espace.id) {
          @case ('comptabilite') {
            <svg viewBox="0 0 24 24" fill="none">
              <rect x="3" y="13" width="4.2" height="8" rx="1.1" fill="currentColor" opacity=".4" />
              <rect x="9.9" y="8" width="4.2" height="13" rx="1.1" fill="currentColor" opacity=".7" />
              <rect x="16.8" y="3.2" width="4.2" height="17.8" rx="1.1" fill="currentColor" />
            </svg>
          }
          @case ('moyens-generaux') {
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 3.4 20.2 7.6v8.6L12 20.6 3.8 16.2V7.6L12 3.4Z" fill="currentColor" opacity=".18" />
              <path
                d="M12 3.4 20.2 7.6v8.6L12 20.6 3.8 16.2V7.6L12 3.4Z"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linejoin="round"
              />
              <path d="M12 12.1 20.2 7.6M12 12.1 3.8 7.6M12 12.1v8.5" stroke="currentColor" stroke-width="1.5" />
            </svg>
          }
          @case ('archives') {
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M4.2 8.6h15.6v9.6a1.7 1.7 0 0 1-1.7 1.7H5.9a1.7 1.7 0 0 1-1.7-1.7V8.6Z" fill="currentColor" opacity=".18" />
              <path
                d="M3.2 5.4h17.6v3.4H3.2V5.4Z"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linejoin="round"
              />
              <path
                d="M4.2 8.8h15.6v9.4a1.7 1.7 0 0 1-1.7 1.7H5.9a1.7 1.7 0 0 1-1.7-1.7V8.8Z"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <path d="M9.4 13.2h5.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          }
          @case ('credit') {
            <svg viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="8" r="3.2" fill="currentColor" />
              <path d="M5.5 19.2c.8-3.6 3.2-5.4 6.5-5.4s5.7 1.8 6.5 5.4" fill="currentColor" opacity=".55" />
            </svg>
          }
          @case ('rh') {
            <svg viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="8" r="3.1" fill="currentColor" />
              <path d="M6 19c.6-3.4 2.8-5.2 6-5.2s5.4 1.8 6 5.2" fill="currentColor" opacity=".7" />
            </svg>
          }
          @case ('informatique') {
            <svg viewBox="0 0 24 24" fill="none">
              <rect x="3.5" y="5.5" width="17" height="11" rx="1.6" fill="currentColor" opacity=".2" />
              <rect x="3.5" y="5.5" width="17" height="11" rx="1.6" stroke="currentColor" stroke-width="1.5" />
              <path d="M9 19.5h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          }
          @case ('achats') {
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M4 6.5h2.4l1.7 9.2a1.6 1.6 0 0 0 1.6 1.3h7.4a1.6 1.6 0 0 0 1.55-1.2L20.2 8.2H7.2"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          }
          @default {
            <svg viewBox="0 0 24 24" fill="none">
              <rect x="4" y="4" width="16" height="16" rx="4" fill="currentColor" opacity=".25" />
            </svg>
          }
        }
      </span>
      <h2 class="bea-espace__title">{{ espace.titre }}</h2>
      <p class="bea-espace__mods">
        @if (espace.modules?.length) {
          {{ espace.modules.length }} module{{ espace.modules.length > 1 ? 's' : '' }}
          ·
          {{ moduleTitles(espace) }}
        } @else {
          Aucun module
        }
      </p>
      <div class="bea-espace__foot">
        @if (espace.statut === 'actif') {
          <span class="bea-badge bea-badge--actif">Disponible</span>
        } @else {
          <span class="bea-badge bea-badge--bientot">Bientôt</span>
        }
        <span class="bea-espace__go" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path
              d="M5 12h12M13 7l5 5-5 5"
              stroke="currentColor"
              stroke-width="1.7"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </span>
      </div>
    </ng-template>
  `,
})
export class AccueilComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly auth = inject(AuthService);
  readonly canAdmin = this.auth.canAccessCoreAdmin;
  readonly periodes = [7, 30, 90] as const;

  readonly espaces = signal<EspaceAccueil[]>([]);
  readonly hub = signal<HubSummary | null>(null);
  readonly serie = signal<HubSeriePoint[]>([]);
  readonly jours = signal<7 | 30 | 90>(7);
  readonly activity = signal<HubActivity[]>([]);
  readonly activityLoading = signal(false);
  readonly activityHasMore = signal(false);
  private activityOffset = 0;
  private readonly activityPage = 20;

  readonly prenom = computed(() => {
    const name = this.hub()?.user_full_name || this.auth.user()?.full_name || '';
    const part = name.trim().split(/\s+/)[0];
    return part || '';
  });

  readonly vue = computed<HubVue>(() => this.hub()?.vue || 'utilisateur');
  readonly kpis = computed(() => this.hub()?.kpis ?? []);
  readonly etat = computed(() => this.hub()?.etat_plateforme ?? null);
  readonly modulesRecents = computed(() => this.hub()?.modules_recents ?? []);

  readonly lead = computed(() => {
    switch (this.vue()) {
      case 'admin':
        return 'Vue globale de la plateforme BEA DIGITAL.';
      case 'responsable':
        return 'Vue de vos départements et de leur activité.';
      default:
        return 'Bienvenue sur BEA DIGITAL.';
    }
  });

  ngOnInit(): void {
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.loadProfile().subscribe({ error: () => undefined });
    }
    this.reloadCatalogue();
    this.reloadHub(7);
    this.reloadActivity();
    // Recharge après un CRUD CORE ADMIN (retour Accueil sans F5).
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        filter((e) => {
          const path = e.urlAfterRedirects.split('?')[0];
          return path === '/accueil' || path === '/';
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.reloadCatalogue();
        this.reloadHub(this.jours());
      });
  }

  private reloadCatalogue(): void {
    this.api.get<EspaceAccueil[]>('/plateforme/espaces').subscribe({
      next: (items) => this.espaces.set(items),
      error: () => undefined,
    });
  }

  private reloadHub(jours: 7 | 30 | 90): void {
    this.api.get<HubSummary>('/plateforme/me/hub', { jours }).subscribe({
      next: (data) => {
        this.hub.set(data);
        this.serie.set(data.activite_serie ?? []);
        this.jours.set((data.activite_jours as 7 | 30 | 90) || jours);
      },
      error: () => undefined,
    });
  }

  usageLead(): string {
    switch (this.vue()) {
      case 'admin':
        return 'Actions enregistrées sur toute la plateforme.';
      case 'responsable':
        return 'Activité de vos départements.';
      default:
        return 'Votre activité sur la période.';
    }
  }

  activityLead(): string {
    switch (this.vue()) {
      case 'admin':
        return 'Dernières actions globales (audit).';
      case 'responsable':
        return 'Actions liées à vos départements.';
      default:
        return 'Vos dernières actions tracées.';
    }
  }

  setJours(jours: 7 | 30 | 90): void {
    if (this.jours() === jours) {
      return;
    }
    this.jours.set(jours);
    this.api.get<HubSeriePoint[]>('/plateforme/me/usage', { jours }).subscribe({
      next: (rows) => this.serie.set(rows),
      error: () => undefined,
    });
  }

  barHeight(count: number): number {
    const max = Math.max(1, ...this.serie().map((p) => p.count));
    return Math.max(count > 0 ? 8 : 0, Math.round((count / max) * 100));
  }

  reloadActivity(): void {
    this.activityOffset = 0;
    this.activityLoading.set(true);
    this.api
      .get<HubActivity[]>('/plateforme/me/activity', {
        limit: this.activityPage,
        offset: 0,
      })
      .subscribe({
        next: (rows) => {
          this.activity.set(rows);
          this.activityOffset = rows.length;
          this.activityHasMore.set(rows.length >= this.activityPage);
          this.activityLoading.set(false);
        },
        error: () => {
          this.activityLoading.set(false);
        },
      });
  }

  loadMoreActivity(): void {
    if (this.activityLoading() || !this.activityHasMore()) {
      return;
    }
    this.activityLoading.set(true);
    this.api
      .get<HubActivity[]>('/plateforme/me/activity', {
        limit: this.activityPage,
        offset: this.activityOffset,
      })
      .subscribe({
        next: (rows) => {
          this.activity.update((cur) => [...cur, ...rows]);
          this.activityOffset += rows.length;
          this.activityHasMore.set(rows.length >= this.activityPage);
          this.activityLoading.set(false);
        },
        error: () => this.activityLoading.set(false),
      });
  }

  ouvert(espace: EspaceAccueil): boolean {
    return espace.statut === 'actif' && !!espace.route && espace.accessible !== false;
  }

  moduleTitles(espace: EspaceAccueil): string {
    const titles = (espace.modules || []).map((m) => m.titre);
    if (titles.length <= 2) {
      return titles.join(', ');
    }
    return `${titles.slice(0, 2).join(', ')}…`;
  }
}
