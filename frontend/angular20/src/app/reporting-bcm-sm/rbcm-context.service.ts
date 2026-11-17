import { Injectable, computed, inject, signal } from '@angular/core';
import { ApiService } from '../core/services/api.service';
import { RBCM_API, RbcmCampaign, RbcmCampaignList, periodLabel } from './rbcm.models';

const KEY = 'rbcm.selectedCampaignId';

@Injectable({ providedIn: 'root' })
export class RbcmContextService {
  private readonly api = inject(ApiService);

  readonly campaigns = signal<RbcmCampaign[]>([]);
  readonly selectedId = signal<string | null>(sessionStorage.getItem(KEY));
  readonly loading = signal(false);

  readonly selected = computed(() => {
    const id = this.selectedId();
    return this.campaigns().find((c) => c.id === id) ?? null;
  });

  readonly selectedLabel = computed(() => {
    const c = this.selected();
    return c ? periodLabel(c) : 'Aucune SM sélectionnée';
  });

  loadCampaigns(): void {
    this.loading.set(true);
    this.api
      .get<RbcmCampaignList>(`${RBCM_API}/campaigns`, { page: 1, page_size: 100, sort_by: 'period', sort_order: 'desc' })
      .subscribe({
        next: (r) => {
          this.campaigns.set(r.items);
          const id = this.selectedId();
          if (!id && r.items.length) {
            this.select(r.items[0]!.id);
          } else if (id && !r.items.some((c) => c.id === id)) {
            this.select(r.items[0]?.id ?? null);
          }
          this.loading.set(false);
        },
        error: () => this.loading.set(false),
      });
  }

  select(id: string | null): void {
    this.selectedId.set(id);
    if (id) sessionStorage.setItem(KEY, id);
    else sessionStorage.removeItem(KEY);
  }

  requireCampaignId(): string | null {
    return this.selectedId();
  }
}
