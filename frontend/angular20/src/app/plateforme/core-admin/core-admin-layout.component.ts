import { ChangeDetectionStrategy, Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { CoreAdminDialogComponent } from './core-admin-dialog.component';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CORE_ADMIN_NAV } from './core-admin-nav';

const SIDEBAR_COLLAPSED_KEY = 'bea.coreAdmin.sidebarCollapsed';

interface SidebarTooltip {
  label: string;
  top: number;
  left: number;
}

@Component({
  selector: 'bea-core-admin-layout',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, CoreAdminDialogComponent, CoreAdminIconComponent],
  template: `
    <div class="bea-admin" [class.bea-admin--collapsed]="collapsed()">
      <aside class="bea-admin__side" aria-label="Navigation CORE ADMIN">
        <div class="bea-admin__side-top">
          <button
            type="button"
            class="bea-admin__collapse"
            (click)="toggleSidebar()"
            [attr.aria-expanded]="!collapsed()"
            [attr.aria-label]="collapsed() ? 'Développer le menu' : 'Réduire le menu'"
            [title]="collapsed() ? 'Développer le menu' : 'Réduire le menu'"
          >
            <bea-admin-icon [name]="collapsed() ? 'chevron_right' : 'chevron_left'" />
          </button>
        </div>
        <a
          routerLink="/admin"
          class="bea-admin__brand"
          title="Dashboard CORE ADMIN"
          [attr.aria-label]="'Dashboard CORE ADMIN'"
        >
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
        <nav class="bea-admin__nav" (scroll)="hideTooltip()">
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
                        [attr.aria-label]="item.label"
                        (mouseenter)="showTooltip($event, item.label)"
                        (mouseleave)="hideTooltip()"
                        (focus)="showTooltip($event, item.label)"
                        (blur)="hideTooltip()"
                      >
                        <bea-admin-icon class="bea-admin__link-icon" [name]="item.icon" />
                        <span class="bea-admin__link-label">{{ item.label }}</span>
                      </a>
                    } @else {
                      <span
                        class="bea-admin__soon"
                        [attr.aria-label]="item.label"
                        (mouseenter)="showTooltip($event, item.label)"
                        (mouseleave)="hideTooltip()"
                      >
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
      @if (collapsed()) {
        @if (tooltip(); as tip) {
          <div
            class="bea-admin__tooltip"
            role="tooltip"
            [style.top.px]="tip.top"
            [style.left.px]="tip.left"
          >
            {{ tip.label }}
          </div>
        }
      }
    </div>
    <bea-core-admin-dialog />
  `,
})
export class CoreAdminLayoutComponent implements OnInit, OnDestroy {
  readonly auth = inject(AuthService);
  readonly nav = CORE_ADMIN_NAV;
  readonly collapsed = signal(false);
  readonly tooltip = signal<SidebarTooltip | null>(null);
  private readonly dialogs = inject(BeaAdminDialogService);

  ngOnInit(): void {
    this.collapsed.set(this.readCollapsedPreference());
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.loadProfile().subscribe({ error: () => undefined });
    }
  }

  ngOnDestroy(): void {
    this.dialogs.dismiss();
    document.body.style.overflow = '';
  }

  toggleSidebar(): void {
    const next = !this.collapsed();
    this.collapsed.set(next);
    this.writeCollapsedPreference(next);
    this.hideTooltip();
  }

  showTooltip(event: Event, label: string): void {
    if (!this.collapsed()) {
      return;
    }
    const el = event.currentTarget as HTMLElement | null;
    if (!el) {
      return;
    }
    const rect = el.getBoundingClientRect();
    this.tooltip.set({
      label,
      top: rect.top + rect.height / 2,
      left: rect.right + 10,
    });
  }

  hideTooltip(): void {
    this.tooltip.set(null);
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

  private readCollapsedPreference(): boolean {
    try {
      return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
    } catch {
      return false;
    }
  }

  private writeCollapsedPreference(collapsed: boolean): void {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0');
    } catch {
      /* ignore quota / private mode */
    }
  }
}
