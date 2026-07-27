import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { AuthService, UserProfile } from '../../core/services/auth.service';
import { ApiService } from '../../core/services/api.service';
import { IdleSessionService } from '../../core/services/idle-session.service';
import { SHELL_NAV, shellNavSections } from './shell-nav';

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
export class ShellComponent implements OnInit, OnDestroy {
  readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly idle = inject(IdleSessionService);

  readonly navSections = shellNavSections(SHELL_NAV);
  readonly notificationUnread = signal(0);

  ngOnInit(): void {
    this.idle.start();
    this.loadNotificationCount();
  }

  ngOnDestroy(): void {
    this.idle.stop();
  }

  logout(): void {
    this.idle.stop();
    this.auth.logout({ reason: 'manual' });
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
