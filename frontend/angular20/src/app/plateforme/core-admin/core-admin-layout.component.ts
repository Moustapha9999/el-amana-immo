import { ChangeDetectionStrategy, Component, inject, OnDestroy, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { CoreAdminDialogComponent } from './core-admin-dialog.component';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CORE_ADMIN_NAV } from './core-admin-nav';

@Component({
  selector: 'bea-core-admin-layout',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, CoreAdminDialogComponent],
  template: `
    <div class="bea-admin">
      <header class="bea-admin__top">
        <a routerLink="/admin" class="bea-admin__brand">
          <img
            class="bea-admin__logo"
            src="/brand/icon-bea-white.png"
            width="36"
            height="36"
            alt=""
          />
          <div>
            <div class="bea-admin__name">BEA DIGITAL CORE ADMIN</div>
            <div class="bea-admin__sub">Banque El Amana · pilotage plateforme</div>
          </div>
        </a>
        <div class="bea-admin__top-actions">
          <a routerLink="/accueil" class="bea-admin__home">Accueil</a>
          @if (auth.user(); as u) {
            <span class="bea-admin__user">{{ u.full_name }}</span>
          }
          <button type="button" class="bea-admin__logout" (click)="logout()">Déconnexion</button>
        </div>
      </header>
      <div class="bea-admin__frame">
        <aside class="bea-admin__side" aria-label="Navigation CORE ADMIN">
          @for (group of nav; track group.label ?? 'dashboard') {
            <div class="bea-admin__group">
              @if (group.label) {
                <p class="bea-admin__group-label">{{ group.label }}</p>
              }
              <ul class="bea-admin__list">
                @for (item of group.items; track item.label) {
                  <li>
                    @if (item.path && !item.soon) {
                      <a
                        class="bea-admin__link"
                        [routerLink]="item.path"
                        routerLinkActive="bea-admin__link--on"
                      >
                        {{ item.label }}
                      </a>
                    } @else {
                      <span class="bea-admin__soon">
                        {{ item.label }}
                        <span class="bea-badge bea-badge--bientot">Bientôt</span>
                      </span>
                    }
                  </li>
                }
              </ul>
            </div>
          }
        </aside>
        <main class="bea-admin__main">
          <router-outlet />
        </main>
      </div>
    </div>
    <bea-core-admin-dialog />
  `,
})
export class CoreAdminLayoutComponent implements OnInit, OnDestroy {
  readonly auth = inject(AuthService);
  readonly nav = CORE_ADMIN_NAV;
  private readonly dialogs = inject(BeaAdminDialogService);

  ngOnInit(): void {
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.loadProfile().subscribe({ error: () => undefined });
    }
  }

  ngOnDestroy(): void {
    this.dialogs.dismiss();
    document.body.style.overflow = '';
  }

  async logout(): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Se déconnecter',
      message: 'Fermer la session CORE ADMIN et revenir à l’écran de connexion BEA DIGITAL ?',
      confirmLabel: 'Déconnexion',
      tone: 'warn',
    });
    if (ok) {
      this.auth.logoutPlatform({ reason: 'manual' });
    }
  }
}
