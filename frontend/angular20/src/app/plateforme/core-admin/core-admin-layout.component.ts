import { ChangeDetectionStrategy, Component, inject, OnDestroy, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { CoreAdminDialogComponent } from './core-admin-dialog.component';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CORE_ADMIN_NAV } from './core-admin-nav';

@Component({
  selector: 'bea-core-admin-layout',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, CoreAdminDialogComponent, CoreAdminIconComponent],
  template: `
    <div class="bea-admin">
      <aside class="bea-admin__side" aria-label="Navigation CORE ADMIN">
        <a routerLink="/admin" class="bea-admin__brand" title="Dashboard CORE ADMIN">
          <img
            class="bea-admin__logo"
            src="/brand/icon-bea-white.png"
            width="100"
            height="100"
            alt=""
          />
          <div class="bea-admin__brand-text">
            <div class="bea-admin__brand-sub">BEA DIGITAL — CORE ADMIN</div>
          </div>
        </a>
        <nav class="bea-admin__nav">
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
                        [routerLinkActiveOptions]="{ exact: item.path === '/admin/dashboard' }"
                      >
                        <bea-admin-icon class="bea-admin__link-icon" [name]="item.icon" />
                        <span class="bea-admin__link-label">{{ item.label }}</span>
                      </a>
                    } @else {
                      <span class="bea-admin__soon">
                        <bea-admin-icon class="bea-admin__link-icon" [name]="item.icon" />
                        <span class="bea-admin__link-label">{{ item.label }}</span>
                        <span class="bea-badge bea-badge--bientot">Bientôt</span>
                      </span>
                    }
                  </li>
                }
              </ul>
            </div>
          }
        </nav>
        <div class="bea-admin__footer">
          <span>BEA DIGITAL — Banque El Amana</span>
        </div>
      </aside>
      <div class="bea-admin__content">
        <header class="bea-admin__top">
          <div class="bea-admin__top-title">Pilotage plateforme</div>
          <div class="bea-admin__top-actions">
            @if (auth.user(); as u) {
              <div class="bea-admin__userchip">
                <span class="bea-admin__avatar" aria-hidden="true">{{ u.full_name.charAt(0) }}</span>
                <span class="bea-admin__user">{{ u.full_name }}</span>
              </div>
            }
            <a routerLink="/accueil" class="bea-admin__home">Accueil</a>
            <button type="button" class="bea-admin__logout" (click)="logout()">Déconnexion</button>
          </div>
        </header>
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
