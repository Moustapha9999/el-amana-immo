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
          <span class="bea-chrome__user">{{ u.full_name }}</span>
        }
        <button type="button" class="bea-chrome__logout" (click)="logout()">Déconnexion</button>
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
    this.auth.logout({ reason: 'manual' });
  }
}
