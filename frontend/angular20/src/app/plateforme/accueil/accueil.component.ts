import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { ESPACES_METIERS, EspaceMetier } from '../espaces-metiers';

type EspaceAccueil = EspaceMetier & { accessible?: boolean };

function withCatalogueText(items: EspaceAccueil[]): EspaceAccueil[] {
  const local = new Map(ESPACES_METIERS.map((espace) => [espace.id, espace]));
  return items.map((item) => {
    const src = local.get(item.id);
    if (!src) {
      return item;
    }
    const modulesLocal = new Map(src.modules.map((mod) => [mod.id, mod]));
    return {
      ...item,
      titre: src.titre,
      description: src.description,
      modules: (item.modules ?? []).map((mod) => {
        const fromSrc = modulesLocal.get(mod.id);
        return fromSrc ? { ...mod, titre: fromSrc.titre, description: fromSrc.description } : mod;
      }),
    };
  });
}

@Component({
  selector: 'bea-accueil',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, NgTemplateOutlet, BeaChromeComponent],
  template: `
    <div class="bea-plateforme">
      <bea-chrome />
      <main class="bea-plateforme__body">
        <p class="bea-plateforme__kicker">Banque El Amana</p>
        <h1 class="bea-plateforme__title">Espaces métiers</h1>
        <p class="bea-bandeau">
          BEA DIGITAL est la plateforme interne de la Banque El Amana : un espace unique pour
          piloter les métiers, les contrôles, les workflows, le reporting et la GED.
        </p>
        @if (canAdmin()) {
          <a class="bea-espace bea-espace--actif bea-espace--admin" routerLink="/admin">
            <div class="bea-espace__top">
              <span class="bea-espace__icon" aria-hidden="true">
                <svg viewBox="0 0 48 48" fill="none">
                  <path
                    d="M24 6 10 12v12c0 10 6.2 16.8 14 20 7.8-3.2 14-10 14-20V12L24 6Z"
                    fill="currentColor"
                    opacity=".18"
                  />
                  <path
                    d="M24 8.5 12.5 13.4V24c0 8.4 5.1 14.2 11.5 17.2C30.4 38.2 35.5 32.4 35.5 24V13.4L24 8.5Z"
                    stroke="currentColor"
                    stroke-width="2.2"
                    stroke-linejoin="round"
                  />
                  <path
                    d="M24 16v16M18 22h12"
                    stroke="currentColor"
                    stroke-width="2.2"
                    stroke-linecap="round"
                  />
                </svg>
              </span>
              <div class="bea-espace__copy">
                <div class="bea-espace__title-row">
                  <h2 class="bea-espace__title">Administration</h2>
                  <span class="bea-badge bea-badge--actif">Actif</span>
                </div>
                <p class="bea-espace__text">
                  BEA DIGITAL digitalise les processus internes de la Banque El Amana. Ouvrez un
                  espace pour accéder à ses modules.
                </p>
              </div>
            </div>
            <div class="bea-espace__art" aria-hidden="true">
              <svg class="bea-espace__scene" viewBox="0 0 360 84" fill="none">
                <rect x="18" y="22" width="54" height="48" rx="8" fill="currentColor" opacity=".16" />
                <rect x="28" y="32" width="34" height="6" rx="3" fill="currentColor" opacity=".35" />
                <rect x="28" y="44" width="24" height="5" rx="2.5" fill="currentColor" opacity=".28" />
                <rect x="92" y="18" width="70" height="52" rx="8" fill="currentColor" opacity=".2" />
                <path
                  d="M112 44.5 124 56.5l28-30"
                  stroke="currentColor"
                  stroke-width="4"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
                <rect x="180" y="28" width="46" height="10" rx="2" fill="currentColor" opacity=".22" />
                <rect x="180" y="44" width="46" height="10" rx="2" fill="currentColor" opacity=".3" />
                <rect x="180" y="60" width="46" height="10" rx="2" fill="currentColor" opacity=".4" />
              </svg>
              <span class="bea-espace__go">
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
            </div>
          </a>
        } @else {
          <p class="bea-plateforme__lead">
            BEA DIGITAL digitalise les processus internes de la Banque El Amana. Ouvrez un espace
            pour accéder à ses modules.
          </p>
        }
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
                <circle cx="36" cy="12" r="5" fill="#1a5278" opacity=".9" />
                <path
                  d="M9 22c6-7 11-4 16-9 4 2 7-1 14-6"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                />
              </svg>
            }
            @case ('credit') {
              <svg viewBox="0 0 48 48" fill="none">
                <circle cx="22" cy="16" r="7" fill="currentColor" opacity=".85" />
                <path
                  d="M10 38c1.5-8 7-12 12-12s10.5 4 12 12"
                  fill="currentColor"
                  opacity=".55"
                />
                <circle cx="34" cy="30" r="9" fill="#1a5278" />
                <path
                  d="M30.5 30.2 33 32.7l5-5.2"
                  stroke="#fff"
                  stroke-width="2.2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            }
            @case ('rh') {
              <svg viewBox="0 0 48 48" fill="none">
                <circle cx="16" cy="16" r="6" fill="currentColor" opacity=".45" />
                <circle cx="32" cy="16" r="6" fill="currentColor" opacity=".45" />
                <circle cx="24" cy="18" r="7" fill="currentColor" />
                <path d="M6 38c1-8 6-12 10-12" fill="currentColor" opacity=".35" />
                <path d="M42 38c-1-8-6-12-10-12" fill="currentColor" opacity=".35" />
                <path d="M13 40c1.2-8 6-12 11-12s9.8 4 11 12" fill="currentColor" opacity=".7" />
              </svg>
            }
            @case ('informatique') {
              <svg viewBox="0 0 48 48" fill="none">
                <rect x="7" y="12" width="26" height="18" rx="3" fill="currentColor" opacity=".2" />
                <rect x="9" y="14" width="22" height="12" rx="1.5" fill="currentColor" />
                <path d="M14 34h12" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
                <circle cx="34" cy="32" r="8" fill="currentColor" opacity=".18" />
                <path
                  d="M34 27.5v9M30.2 29.6l7.6 4.8M30.2 34.4l7.6-4.8"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                />
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
                <circle cx="21" cy="38" r="2.6" fill="currentColor" />
                <circle cx="34" cy="38" r="2.6" fill="currentColor" />
                <rect x="28" y="8" width="11" height="14" rx="2" fill="currentColor" opacity=".25" />
                <path d="M31 12h5M31 16h5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
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
              <span class="bea-badge bea-badge--actif">Actif</span>
            } @else {
              <span class="bea-badge bea-badge--bientot">Bientôt</span>
            }
          </div>
          <p class="bea-espace__text">{{ espace.description }}</p>
        </div>
      </div>
      <div class="bea-espace__art" aria-hidden="true">
        @switch (espace.id) {
          @case ('comptabilite') {
            <svg class="bea-espace__scene" viewBox="0 0 360 84" fill="none">
              <path d="M0 84h360V46C280 18 220 58 140 34 80 16 40 38 0 28v56Z" fill="currentColor" opacity=".12" />
              <rect x="18" y="48" width="16" height="24" rx="4" fill="currentColor" opacity=".35" />
              <rect x="40" y="36" width="16" height="36" rx="4" fill="currentColor" opacity=".5" />
              <rect x="62" y="42" width="16" height="30" rx="4" fill="currentColor" opacity=".4" />
              <rect x="84" y="26" width="16" height="46" rx="4" fill="currentColor" opacity=".65" />
              <rect x="106" y="32" width="16" height="40" rx="4" fill="currentColor" opacity=".5" />
              <rect x="128" y="16" width="16" height="56" rx="4" fill="currentColor" />
              <rect x="150" y="22" width="16" height="50" rx="4" fill="currentColor" opacity=".8" />
              <path
                d="M20 54c42-18 70 6 118-22 36-20 70-8 110 4"
                stroke="currentColor"
                stroke-width="3"
                stroke-linecap="round"
              />
            </svg>
          }
          @case ('credit') {
            <svg class="bea-espace__scene" viewBox="0 0 360 84" fill="none">
              <rect x="24" y="18" width="70" height="52" rx="8" fill="currentColor" opacity=".16" />
              <rect x="34" y="28" width="50" height="6" rx="3" fill="currentColor" opacity=".35" />
              <rect x="34" y="40" width="38" height="5" rx="2.5" fill="currentColor" opacity=".28" />
              <rect x="34" y="50" width="44" height="5" rx="2.5" fill="currentColor" opacity=".22" />
              <path
                d="M150 22h52c6 0 10 4 10 10v36c0 8-8 14-18 10l-18-8-18 8c-10 4-18-2-18-10V32c0-6 4-10 10-10Z"
                fill="currentColor"
                opacity=".22"
              />
              <path
                d="M168 44.5 176 52.5l16-18"
                stroke="currentColor"
                stroke-width="4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          }
          @case ('rh') {
            <svg class="bea-espace__scene" viewBox="0 0 360 84" fill="none">
              <circle cx="118" cy="28" r="12" fill="currentColor" opacity=".28" />
              <path d="M90 74c2-16 12-24 28-24s26 8 28 24" fill="currentColor" opacity=".2" />
              <circle cx="168" cy="24" r="14" fill="currentColor" opacity=".55" />
              <path d="M136 74c3-18 14-28 32-28s29 10 32 28" fill="currentColor" opacity=".38" />
              <circle cx="218" cy="28" r="12" fill="currentColor" opacity=".28" />
              <path d="M190 74c2-16 12-24 28-24s26 8 28 24" fill="currentColor" opacity=".2" />
            </svg>
          }
          @case ('informatique') {
            <svg class="bea-espace__scene" viewBox="0 0 360 84" fill="none">
              <rect x="28" y="28" width="92" height="36" rx="8" fill="currentColor" opacity=".18" />
              <rect x="36" y="34" width="76" height="20" rx="4" fill="currentColor" opacity=".4" />
              <path d="M56 72h36" stroke="currentColor" stroke-width="4" stroke-linecap="round" />
              <circle cx="150" cy="30" r="10" fill="currentColor" opacity=".16" />
              <circle cx="178" cy="24" r="14" fill="currentColor" opacity=".12" />
              <rect x="214" y="34" width="36" height="10" rx="2" fill="currentColor" opacity=".22" />
              <rect x="214" y="48" width="36" height="10" rx="2" fill="currentColor" opacity=".3" />
              <rect x="214" y="62" width="36" height="10" rx="2" fill="currentColor" opacity=".4" />
              <circle cx="132" cy="58" r="12" fill="currentColor" opacity=".14" />
              <path
                d="M132 52v12M126.5 54.8l11 6.4M126.5 61.2l11-6.4"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              />
            </svg>
          }
          @case ('achats') {
            <svg class="bea-espace__scene" viewBox="0 0 360 84" fill="none">
              <path
                d="M40 28h18l10 32h70l12-24H70"
                stroke="currentColor"
                stroke-width="4"
                stroke-linecap="round"
                stroke-linejoin="round"
                opacity=".55"
              />
              <circle cx="92" cy="68" r="5" fill="currentColor" opacity=".55" />
              <circle cx="128" cy="68" r="5" fill="currentColor" opacity=".55" />
              <rect x="176" y="22" width="40" height="48" rx="6" fill="currentColor" opacity=".16" />
              <path
                d="M186 36h20M186 46h16M186 56h18"
                stroke="currentColor"
                stroke-width="3"
                stroke-linecap="round"
                opacity=".4"
              />
            </svg>
          }
          @default {
            <svg class="bea-espace__scene" viewBox="0 0 360 84" fill="none">
              <rect x="24" y="28" width="200" height="36" rx="12" fill="currentColor" opacity=".12" />
            </svg>
          }
        }
        <span class="bea-espace__go">
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
      </div>
    </ng-template>
  `,
})
export class AccueilComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly auth = inject(AuthService);
  readonly canAdmin = this.auth.canAccessCoreAdmin;
  readonly espaces = signal<EspaceAccueil[]>(ESPACES_METIERS);

  ngOnInit(): void {
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.loadProfile().subscribe({ error: () => undefined });
    }
    this.api.get<EspaceAccueil[]>('/plateforme/espaces').subscribe({
      next: (items) => this.espaces.set(withCatalogueText(items)),
      error: () => undefined,
    });
  }

  ouvert(espace: EspaceAccueil): boolean {
    return espace.statut === 'actif' && !!espace.route && espace.accessible !== false;
  }
}
