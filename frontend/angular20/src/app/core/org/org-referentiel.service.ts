import { Injectable, inject } from '@angular/core';
import { Observable, map, shareReplay } from 'rxjs';
import { ApiService } from '../services/api.service';
import { OrgAgenceOption, OrgEntiteOption, OrgMonPerimetre, OrgTypeEntite } from './org-referentiel.models';

/**
 * Lecture du référentiel organisationnel central, pour tous les modules (Login 1 ou Login 2).
 * L'administration (création, rattachements, affectations) reste dans CORE ADMIN.
 */
@Injectable({ providedIn: 'root' })
export class OrgReferentielService {
  private readonly api = inject(ApiService);
  private actives$?: Observable<OrgEntiteOption[]>;

  /** Entités actives, ordre de l'organigramme (parent puis enfants). Mises en cache pour la session. */
  entitesActives(): Observable<OrgEntiteOption[]> {
    this.actives$ ??= this.entites().pipe(shareReplay({ bufferSize: 1, refCount: false }));
    return this.actives$;
  }

  entites(options: { types?: OrgTypeEntite[]; racineId?: string; inclureInactives?: boolean } = {}): Observable<OrgEntiteOption[]> {
    const params: Record<string, string | boolean> = {};
    if (options.racineId) params['racine_id'] = options.racineId;
    if (options.inclureInactives) params['inclure_inactives'] = true;
    let path = '/organisation/entites';
    if (options.types?.length) {
      path += '?' + options.types.map((t) => `type_entite=${encodeURIComponent(t)}`).join('&');
    }
    return this.api.get<{ items: OrgEntiteOption[] }>(path, params).pipe(map((r) => r.items ?? []));
  }

  agences(): Observable<OrgAgenceOption[]> {
    return this.api.get<{ items: OrgAgenceOption[] }>('/organisation/agences').pipe(map((r) => r.items ?? []));
  }

  monPerimetre(): Observable<OrgMonPerimetre> {
    return this.api.get<OrgMonPerimetre>('/organisation/mon-perimetre');
  }

  /** À appeler après une modification de l'organigramme dans CORE ADMIN. */
  invalider(): void {
    this.actives$ = undefined;
  }
}
