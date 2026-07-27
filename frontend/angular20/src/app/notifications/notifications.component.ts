import { DatePipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface NotificationRow {
  id: string;
  type_notification: string;
  titre: string;
  message: string;
  lu: boolean;
  entity: string | null;
  entity_id: string | null;
  created_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

@Component({
  selector: 'app-notifications',
  imports: [DatePipe, RouterLink, MatButtonModule, MatIconModule, MatTableModule],
  templateUrl: './notifications.component.html',
  styleUrl: './notifications.component.css',
})
export class NotificationsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly dialogs = inject(UiDialogService);

  readonly rows = signal<NotificationRow[]>([]);
  readonly unread = signal(0);
  readonly loading = signal(false);
  readonly columns = ['consulter', 'created_at', 'type', 'titre', 'message', 'actions'];

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<Paginated<NotificationRow>>('/notifications', { page: 1, size: 100 }).subscribe({
      next: (res) => {
        this.rows.set(res.items);
        this.unread.set(res.items.filter((n) => !n.lu).length);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        void this.dialogs.error('Impossible de charger les notifications').subscribe();
      },
    });
  }

  typeLabel(type: string): string {
    switch (type) {
      case 'fin_amortissement':
        return 'Fin d’amortissement';
      case 'inventaire':
        return 'Inventaire';
      case 'maintenance':
        return 'Maintenance';
      case 'assurance':
        return 'Assurance';
      case 'systeme':
        return 'Système';
      default:
        return type;
    }
  }

  detailLink(row: NotificationRow): string | null {
    if (row.entity === 'immobilisation' && row.entity_id) {
      return `/immobilisations/${row.entity_id}`;
    }
    if (row.type_notification === 'inventaire') {
      return '/inventaire';
    }
    if (row.type_notification === 'fin_amortissement') {
      return '/amortissements';
    }
    return null;
  }

  consulter(row: NotificationRow): void {
    const link = this.detailLink(row);
    if (!link) {
      void this.dialogs.info(row.message, row.titre).subscribe();
      return;
    }
    if (!row.lu) {
      this.markRead(row);
    }
    void this.router.navigateByUrl(link);
  }

  markRead(row: NotificationRow): void {
    if (row.lu) {
      return;
    }
    this.api.patch<NotificationRow>(`/notifications/${row.id}/read`, {}).subscribe({
      next: () => {
        row.lu = true;
        this.rows.set([...this.rows()]);
        this.unread.set(this.rows().filter((n) => !n.lu).length);
      },
    });
  }

  markAllRead(): void {
    this.api.post<{ message: string }>('/notifications/read-all', {}).subscribe({
      next: () => this.load(),
    });
  }
}
