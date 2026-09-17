import { ChangeDetectionStrategy, Component, inject, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'bea-chrome',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <header class="bea-chrome">
      <a routerLink="/accueil" class="bea-chrome__brand">
        <img
          class="bea-chrome__logo"
          src="/brand/icon-bea-white.png"
          width="40"
          height="40"
          alt=""
        />
        <div>
          <div class="bea-chrome__name">BEA DIGITAL</div>
          <div class="bea-chrome__sub">Banque El Amana · plateforme interne</div>
        </div>
      </a>
      <div class="bea-chrome__actions">
        @if (auth.user(); as u) {
          <div class="bea-chrome__userchip">
            <span class="bea-chrome__avatar" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="8" r="3.2" stroke="currentColor" stroke-width="1.7" />
                <path
                  d="M5.5 18.5c1.2-3.2 3.6-4.8 6.5-4.8s5.3 1.6 6.5 4.8"
                  stroke="currentColor"
                  stroke-width="1.7"
                  stroke-linecap="round"
                />
              </svg>
            </span>
            <span class="bea-chrome__user">{{ u.full_name }}</span>
          </div>
        }
        <button type="button" class="bea-chrome__logout" (click)="logout()">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M10 7V5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-2"
              stroke="currentColor"
              stroke-width="1.7"
              stroke-linecap="round"
            />
            <path
              d="M4 12h10M11 8l4 4-4 4"
              stroke="currentColor"
              stroke-width="1.7"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          Déconnexion
        </button>
      </div>
    </header>
  `,
})
export class BeaChromeComponent implements OnInit {
  readonly auth = inject(AuthService);

  ngOnInit(): void {
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.loadProfile().subscribe({ error: () => undefined });
    }
  }

  logout(): void {
    this.auth.logoutPlatform({ reason: 'manual' });
  }
}
