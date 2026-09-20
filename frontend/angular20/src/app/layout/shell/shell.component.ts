import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { AuthService, UserProfile } from '../../core/services/auth.service';
import { ApiService } from '../../core/services/api.service';
import { SystemClockService } from '../../core/services/system-clock.service';
import { PlateformeContextService } from '../../plateforme/plateforme-context.service';
import { LEGACY_ROOT_MODULE_CODE } from '../../plateforme/module-routing.contract';
import { SHELL_NAV, shellNavSections } from './shell-nav';

interface ModuleInfo {
  titre: string;
  entry_path: string | null;
  espace_route: string | null;
  espace_titre: string | null;
}

@Component({
  selector: 'app-shell',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatSidenavModule,
    MatToolbarModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  readonly auth = inject(AuthService);
  readonly clock = inject(SystemClockService);
  private readonly api = inject(ApiService);
  private readonly nav = inject(PlateformeContextService);

  readonly navSections = shellNavSections(SHELL_NAV);
  readonly notificationUnread = signal(0);
  readonly brandSubtitle = computed(() => `BEA DIGITAL — ${this.nav.espaceTitre()}`);
  readonly moduleTitle = computed(() => this.nav.moduleTitre());

  ngOnInit(): void {
    this.nav.ensureLegacyImmoDefaults();
    if (this.auth.isAuthenticated() && !this.auth.user()) {
      this.auth.loadProfile().subscribe({ error: () => undefined });
    }
    this.hydrateModuleContext();
    this.loadNotificationCount();
  }

  logout(): void {
    this.auth.logoutModule();
  }

  private hydrateModuleContext(): void {
    const code = this.auth.moduleCode || LEGACY_ROOT_MODULE_CODE;
    this.api.get<ModuleInfo>(`/plateforme/modules/${code}`).subscribe({
      next: (info) =>
        this.nav.setFromModuleInfo({
          moduleCode: code,
          titre: info.titre,
          entry_path: info.entry_path,
          espace_route: info.espace_route,
          espace_titre: info.espace_titre,
        }),
      error: () => undefined,
    });
  }

  loadNotificationCount(): void {
    this.api
      .get<{ items: { lu: boolean }[] }>('/notifications', { page: 1, size: 50, unread_only: 'true' })
      .subscribe({
        next: (res) => this.notificationUnread.set(res.items.filter((n) => !n.lu).length),
        error: () => this.notificationUnread.set(0),
      });
  }

  unreadForPath(path: string): number | null {
    if (path !== '/notifications') {
      return null;
    }
    const n = this.notificationUnread();
    return n > 0 ? n : null;
  }

  primaryRoleLabel(user: UserProfile): string {
    const first = user.roles[0];
    return first ? first.label : 'Utilisateur';
  }
}
