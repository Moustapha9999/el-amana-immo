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
            <a class="bea-admin-btn" routerLink="/admin">CORE ADMIN</a>
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
          <div class="bea-card-grid">
            @for (espace of espaces(); track espace.id; let i = $index) {
              @if (ouvert(espace)) {
                <a
                  class="bea-espace bea-espace--actif"
                  [style.--bea-i]="i"
                  [routerLink]="espace.route"
                >
                  <ng-container *ngTemplateOutlet="card; context: { $implicit: espace }" />
                </a>
              } @else {
                <div class="bea-espace bea-espace--bientot" [style.--bea-i]="i">
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
      <div class="bea-espace__top">
        <span class="bea-espace__icon" aria-hidden="true">
          @switch (espace.id) {
            @case ('comptabilite') {
              <svg viewBox="0 0 48 48" fill="none">
                <rect x="8" y="28" width="8" height="12" rx="2" fill="currentColor" opacity=".4" />
                <rect x="20" y="18" width="8" height="22" rx="2" fill="currentColor" opacity=".7" />
                <rect x="32" y="10" width="8" height="30" rx="2" fill="currentColor" />
              </svg>
            }
            @case ('credit') {
              <svg viewBox="0 0 48 48" fill="none">
                <circle cx="22" cy="16" r="7" fill="currentColor" opacity=".85" />
                <path d="M10 38c1.5-8 7-12 12-12s10.5 4 12 12" fill="currentColor" opacity=".55" />
              </svg>
            }
            @case ('rh') {
              <svg viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="18" r="7" fill="currentColor" />
                <path d="M13 40c1.2-8 6-12 11-12s9.8 4 11 12" fill="currentColor" opacity=".7" />
              </svg>
            }
            @case ('informatique') {
              <svg viewBox="0 0 48 48" fill="none">
                <rect x="9" y="14" width="22" height="12" rx="1.5" fill="currentColor" />
                <path d="M14 34h12" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
              </svg>
            }
            @case ('achats') {
              <svg viewBox="0 0 48 48" fill="none">
                <path
                  d="M8 14h6l3.2 16.5A3 3 0 0 0 20.1 33h13.2a3 3 0 0 0 2.9-2.2L40 18H16"
                  stroke="currentColor"
                  stroke-width="2.4"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            }
            @default {
              <svg viewBox="0 0 48 48" fill="none">
                <rect x="10" y="10" width="28" height="28" rx="8" fill="currentColor" opacity=".2" />
              </svg>
            }
          }
        </span>
        <div class="bea-espace__copy">
          <div class="bea-espace__title-row">
            <h2 class="bea-espace__title">{{ espace.titre }}</h2>
            @if (espace.statut === 'actif') {
              <span class="bea-badge bea-badge--actif">Disponible</span>
            } @else {
              <span class="bea-badge bea-badge--bientot">Bientôt</span>
            }
          </div>
          <p class="bea-espace__text">{{ espace.description }}</p>
          <p class="bea-espace__mods">
            @if (espace.modules?.length) {
              {{ espace.modules.length }} module{{ espace.modules.length > 1 ? 's' : '' }}
              ·
              {{ moduleTitles(espace) }}
            } @else {
              Aucun module
            }
          </p>
        </div>
      </div>
      <span class="bea-espace__go" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path
            d="M5 12h14M13 6l6 6-6 6"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </span>
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
