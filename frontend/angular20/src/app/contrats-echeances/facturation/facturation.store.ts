import { Injectable, computed, inject, signal } from '@angular/core';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FxCapacites, FxConfig, FxReferentiels } from './facturation.models';

const AUCUNE: FxCapacites = {
  view: false, create: false, update: false, delete: false, validate: false, archive: false, export: false,
  payment_view: false, payment_create: false, payment_update: false, payment_delete: false,
  documents_view: false, documents_create: false, documents_delete: false, analytics: false, reports: false, manage: false,
};

/** Configuration et référentiels du module factures, partagés entre les écrans. */
@Injectable({ providedIn: 'root' })
export class FacturationStore {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);

  readonly config = signal<FxConfig | null>(null);
  readonly ref = signal<FxReferentiels | null>(null);
  readonly cap = computed<FxCapacites>(() => this.config()?.capacites ?? AUCUNE);

  charger(force = false): void {
    if (!this.config() || force) {
      this.api.get<FxConfig>('/mg/factures/config').subscribe({
        next: (c) => this.config.set(c),
        error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Configuration indisponible')),
      });
    }
    if (!this.ref() || force) this.rechargerRef();
  }

  rechargerRef(): void {
    this.api.get<FxReferentiels>('/mg/factures/referentiels').subscribe({ next: (r) => this.ref.set(r), error: () => undefined });
  }

  typeFacture(code: string | null | undefined): string {
    if (!code) return '—';
    return this.config()?.types_facture.find((t) => t.code === code)?.libelle ?? code;
  }
}
