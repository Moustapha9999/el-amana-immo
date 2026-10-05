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
type Periode = 7 | 30 | 90;

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

interface HubSummary {
  vue: HubVue;
  user_full_name?: string | null;
  notifications_non_lues: number;
  etat_plateforme?: {
    ok: boolean;
    verifie_at: string;
    components: HubComponentEtat[];
  } | null;
  activite_jours?: number;
  activite_serie?: HubSeriePoint[];
}

@Component({
  selector: 'bea-accueil',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, NgTemplateOutlet, BeaChromeComponent, DatePipe],
  template: `
    <div class="bea-plateforme">
      <bea-chrome />
      <main class="bea-plateforme__body bea-home">
        <header class="bea-home__head">
          <div>
            <p class="bea-home__date">{{ aujourdhui }}</p>
            <h1 class="bea-home__title">Bonjour{{ prenom() ? ', ' + prenom() : '' }}</h1>
          </div>
          @if (canAdmin()) {
            <a class="bea-home__core" routerLink="/admin">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.7" />
                <path
                  d="M12 2.8v2.4M12 18.8v2.4M4.2 7.5l2.1 1.2M17.7 15.3l2.1 1.2M4.2 16.5l2.1-1.2M17.7 8.7l2.1-1.2"
                  stroke="currentColor"
                  stroke-width="1.7"
                  stroke-linecap="round"
                />
              </svg>
              Core admin
            </a>
          }
        </header>

        @if (notifications() > 0) {
          <div class="bea-home__alert" role="status">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15l1.5-2Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
              <path d="M10 20.5a2 2 0 0 0 4 0" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
            </svg>
            <span>{{ notifications() }} notification{{ notifications() > 1 ? 's' : '' }} prioritaire{{ notifications() > 1 ? 's' : '' }} non lue{{ notifications() > 1 ? 's' : '' }}</span>
            @if (canAdmin()) {
              <a routerLink="/admin/notifications">Voir <span aria-hidden="true">›</span></a>
            }
          </div>
        }

        <section class="bea-home__section" aria-labelledby="bea-home-dep">
          <h2 id="bea-home-dep" class="bea-home__h2">Départements</h2>
          <div class="bea-home__grid">
            @for (espace of espaces(); track espace.id; let i = $index) {
              @if (ouvert(espace)) {
                <a class="bea-home__dep" [style.--bea-i]="i" [routerLink]="espace.route" [title]="moduleTitles(espace)">
                  <ng-container *ngTemplateOutlet="card; context: { $implicit: espace }" />
                </a>
              } @else {
                <div class="bea-home__dep is-off" [style.--bea-i]="i" [title]="espace.statut === 'actif' ? 'Accès non accordé' : 'Bientôt disponible'">
                  <ng-container *ngTemplateOutlet="card; context: { $implicit: espace }" />
                </div>
              }
            }
          </div>
        </section>

        <div class="bea-home__cols" [class.is-solo]="!etat()">
          <section class="bea-home__panel" aria-labelledby="bea-home-act">
            <div class="bea-home__panel-head">
              <h2 id="bea-home-act" class="bea-home__h2">Activité</h2>
              <select class="bea-home__periode" [value]="jours()" (change)="setJours(+$any($event.target).value)" aria-label="Période d'activité">
                @for (p of periodes; track p) {
                  <option [value]="p">{{ p }} derniers jours</option>
                }
              </select>
            </div>
            @if (serie().length === 0) {
              <p class="bea-home__empty">Aucune activité sur cette période.</p>
            } @else {
              <div class="bea-home__chart" [class.is-dense]="serie().length > 14">
                @for (pt of serie(); track pt.date) {
                  <div class="bea-home__bar" [class.is-max]="pt.count > 0 && pt.count === max()" [title]="pt.label + ' · ' + pt.count">
                    @if (serie().length <= 14) {
                      <span class="bea-home__bar-val">{{ pt.count }}</span>
                    }
                    <span class="bea-home__bar-fill" [style.height.%]="barHeight(pt.count)"></span>
                  </div>
                }
              </div>
            }
          </section>

          @if (etat(); as e) {
            <section class="bea-home__panel" aria-labelledby="bea-home-etat">
              <div class="bea-home__panel-head">
                <h2 id="bea-home-etat" class="bea-home__h2">État de la plateforme</h2>
                <span class="bea-home__pill" [class.is-warn]="!e.ok">{{ e.ok ? 'Opérationnelle' : 'Dégradée' }}</span>
              </div>
              <dl class="bea-home__etat">
                @for (c of e.components; track c.key) {
                  <div>
                    <dt>{{ c.label }}</dt>
                    <dd [attr.data-ok]="c.ok"><span class="bea-home__dot" aria-hidden="true"></span>{{ c.status_label }}</dd>
                  </div>
                }
                <div>
                  <dt>Dernière vérification</dt>
                  <dd class="is-plain">{{ e.verifie_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}</dd>
                </div>
              </dl>
            </section>
          }
        </div>
      </main>
    </div>

    <ng-template #card let-espace>
      <span class="bea-home__dep-icon" aria-hidden="true">
        @switch (espace.id) {
          @case ('comptabilite') {
            <svg viewBox="0 0 24 24" fill="none">
              <rect x="3.5" y="13" width="4" height="7.5" rx="1" fill="currentColor" opacity=".45" />
              <rect x="10" y="8.5" width="4" height="12" rx="1" fill="currentColor" opacity=".75" />
              <rect x="16.5" y="4" width="4" height="16.5" rx="1" fill="currentColor" />
            </svg>
          }
          @case ('moyens-generaux') {
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 3.4 20.2 7.6v8.6L12 20.6 3.8 16.2V7.6L12 3.4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
              <path d="M12 12.1 20.2 7.6M12 12.1 3.8 7.6M12 12.1v8.5" stroke="currentColor" stroke-width="1.6" />
            </svg>
          }
          @case ('archives') {
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M3.2 5.4h17.6v3.4H3.2V5.4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
              <path d="M4.2 8.8h15.6v9.4a1.7 1.7 0 0 1-1.7 1.7H5.9a1.7 1.7 0 0 1-1.7-1.7V8.8Z" stroke="currentColor" stroke-width="1.6" />
              <path d="M9.4 13.2h5.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          }
          @case ('informatique') {
            <svg viewBox="0 0 24 24" fill="none">
              <rect x="3.5" y="5" width="17" height="11.5" rx="1.6" stroke="currentColor" stroke-width="1.6" />
              <path d="M9 19.5h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          }
          @case ('audit-controle-conformite') {
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 3.2 19 6v5.4c0 4.3-2.9 7.6-7 9.4-4.1-1.8-7-5.1-7-9.4V6l7-2.8Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
              <path d="m8.8 12 2.2 2.2 4.2-4.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          }
          @case ('achats') {
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M4 6.5h2.4l1.7 9.2a1.6 1.6 0 0 0 1.6 1.3h7.4a1.6 1.6 0 0 0 1.55-1.2L20.2 8.2H7.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          }
          @default {
            <svg viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="8" r="3.2" stroke="currentColor" stroke-width="1.6" />
              <path d="M5.5 19.2c.8-3.6 3.2-5.4 6.5-5.4s5.7 1.8 6.5 5.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          }
        }
      </span>
      <span class="bea-home__dep-go" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M8 16 16 8M9.5 8H16v6.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
      <strong class="bea-home__dep-title">{{ espace.titre }}</strong>
      <span class="bea-home__dep-mods">
        @if (espace.statut !== 'actif') {
          Bientôt
        } @else if (espace.modules?.length) {
          {{ espace.modules.length }} module{{ espace.modules.length > 1 ? 's' : '' }}
        } @else {
          Aucun module
        }
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
  readonly periodes: Periode[] = [7, 30, 90];
  readonly aujourdhui = capitaliser(
    new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Africa/Nouakchott' }).format(new Date()),
  );

  readonly espaces = signal<EspaceAccueil[]>([]);
  readonly hub = signal<HubSummary | null>(null);
  readonly serie = signal<HubSeriePoint[]>([]);
  readonly jours = signal<Periode>(7);

  readonly prenom = computed(() => {
    const name = this.hub()?.user_full_name || this.auth.user()?.full_name || '';
    return name.trim().split(/\s+/)[0] || '';
  });
  readonly notifications = computed(() => this.hub()?.notifications_non_lues ?? 0);
  readonly etat = computed(() => (this.hub()?.vue === 'admin' ? this.hub()?.etat_plateforme ?? null : null));
  readonly max = computed(() => Math.max(0, ...this.serie().map((p) => p.count)));

  ngOnInit(): void {
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.loadProfile().subscribe({ error: () => undefined });
    }
    this.reloadCatalogue();
    this.reloadHub(7);
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

  private reloadHub(jours: Periode): void {
    this.api.get<HubSummary>('/plateforme/me/hub', { jours }).subscribe({
      next: (data) => {
        this.hub.set(data);
        this.serie.set(data.activite_serie ?? []);
        this.jours.set((data.activite_jours as Periode) || jours);
      },
      error: () => undefined,
    });
  }

  setJours(jours: number): void {
    const j = (this.periodes.includes(jours as Periode) ? jours : 7) as Periode;
    if (this.jours() === j) return;
    this.jours.set(j);
    this.api.get<HubSeriePoint[]>('/plateforme/me/usage', { jours: j }).subscribe({
      next: (rows) => this.serie.set(rows),
      error: () => undefined,
    });
  }

  barHeight(count: number): number {
    const max = Math.max(1, this.max());
    return Math.max(count > 0 ? 6 : 2, Math.round((count / max) * 100));
  }

  ouvert(espace: EspaceAccueil): boolean {
    return espace.statut === 'actif' && !!espace.route && espace.accessible !== false;
  }

  moduleTitles(espace: EspaceAccueil): string {
    return (espace.modules || []).map((m) => m.titre).join(', ');
  }
}

function capitaliser(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
