import { DatePipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';

interface NotificationRow {
  id: string;
  type_notification: string;
  titre: string;
  message: string;
  lu: boolean;
  created_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

import { PageHeaderComponent } from '../shared/page-header.component';

@Component({
  selector: 'app-notifications',
  imports: [DatePipe, RouterLink, MatButtonModule, MatTableModule, PageHeaderComponent],
  templateUrl: './notifications.component.html',
})
export class NotificationsComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly rows = signal<NotificationRow[]>([]);
  readonly unread = signal(0);
  readonly columns = ['created_at', 'type', 'titre', 'message', 'actions'];

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.get<Paginated<NotificationRow>>('/notifications', { page: 1, size: 100 }).subscribe((res) => {
      this.rows.set(res.items);
      this.unread.set(res.items.filter((n) => !n.lu).length);
    });
  }

  markRead(row: NotificationRow): void {
    if (row.lu) {
      return;
    }
    this.api.patch<NotificationRow>(`/notifications/${row.id}/read`, {}).subscribe(() => {
      row.lu = true;
      this.rows.set([...this.rows()]);
      this.unread.set(this.rows().filter((n) => !n.lu).length);
    });
  }

  markAllRead(): void {
    this.api.post<{ message: string }>('/notifications/read-all', {}).subscribe(() => this.load());
  }
}
