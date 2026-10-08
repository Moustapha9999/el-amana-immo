import { Injectable, computed, inject, signal } from '@angular/core';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { AgenceRef, CL_BASE, Capacites, ClConfig } from './clientele.models';

const AUCUNE: Capacites = {
  voir: false, imports_voir: false, imports_executer: false,
  rapprochement_voir: false, rapprochement_executer: false,
  classif_voir: false, classif_executer: false, classif_admin: false,
  filtrage_voir: false, filtrage_executer: false, filtrage_decider: false,
  reporting_voir: false, bcm_voir: false, bcm_preparer: false, bcm_valider: false,
  bcm_cloturer: false, exporter: false, admin: false,
};

@Injectable({ providedIn: 'root' })
export class ClienteleStore {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private enCours = false;

  readonly config = signal<ClConfig | null>(null);
  readonly cap = computed<Capacites>(() => this.config()?.capacites ?? AUCUNE);
  readonly agences = computed<AgenceRef[]>(() => this.config()?.agences ?? []);

  charger(force = false): void {
    if ((this.config() && !force) || this.enCours) return;
    this.enCours = true;
    this.api.get<ClConfig>(`${CL_BASE}/config`).subscribe({
      next: (c) => {
        this.config.set(c);
        this.enCours = false;
      },
      error: (e) => {
        this.enCours = false;
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Configuration Clientèle indisponible'));
      },
    });
  }
}
