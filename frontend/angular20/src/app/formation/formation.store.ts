import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { Capacites, Domaine, Entite, FO_BASE, FoConfig, RefItem } from './formation.models';

const AUCUNE: Capacites = {
  voir: false, creer: false, modifier: false, annuler: false, cloturer: false, employes_voir: false,
  employes_gerer: false, presences_voir: false, presences_gerer: false, referentiels_voir: false,
  referentiels_gerer: false, imports_voir: false, imports_executer: false, reporting_voir: false,
  reporting_exporter: false, admin: false,
};

/** Configuration du module (capacités + référentiels), chargée une fois et rafraîchie après modification. */
@Injectable({ providedIn: 'root' })
export class FormationStore {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private enCours = false;

  readonly config = signal<FoConfig | null>(null);
  readonly cap = computed<Capacites>(() => this.config()?.capacites ?? AUCUNE);
  readonly entites = computed<Entite[]>(() => this.config()?.entites ?? []);
  readonly entitesActives = computed(() => this.entites().filter((e) => e.actif));

  charger(force = false): void {
    if ((this.config() && !force) || this.enCours) return;
    this.enCours = true;
    this.api.get<FoConfig>(`${FO_BASE}/config`).subscribe({
      next: (c) => {
        this.config.set(c);
        this.enCours = false;
      },
      error: (e) => {
        this.enCours = false;
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Configuration Formation indisponible'));
      },
    });
  }

  recharger$(): Observable<FoConfig> {
    return this.api.get<FoConfig>(`${FO_BASE}/config`).pipe(tap((c) => this.config.set(c)));
  }

  refs(domaine: Domaine, inclureInactifs = false): RefItem[] {
    const liste = this.config()?.referentiels[domaine] ?? [];
    return inclureInactifs ? liste : liste.filter((r) => r.actif);
  }

  libelle(domaine: Domaine, id: string | null | undefined): string {
    if (!id) return '';
    return this.config()?.referentiels[domaine]?.find((r) => r.id === id)?.libelle ?? '';
  }

  entite(id: string | null | undefined): Entite | undefined {
    return id ? this.entites().find((e) => e.id === id) : undefined;
  }
}
