import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import {
  clientsParams,
  IntegrationClientFiche,
  IntegrationClientFiltres,
  IntegrationClientPage,
  IntegrationClientSaisie,
  IntegrationDocumentation,
  IntegrationGrant,
  IntegrationGrantListe,
  IntegrationGrantStatut,
  IntegrationHistorique,
  IntegrationOperationsAdmissibles,
} from './core-admin-integration-clients.models';
import type { BilanSuppression } from './core-admin-integration-ui';

const BASE = '/plateforme/admin/integrations/clients';

/** Applications clientes du Studio d'intégration API — chaque route revérifie ses permissions côté serveur. */
@Injectable({ providedIn: 'root' })
export class CoreAdminIntegrationClientsService {
  private readonly api = inject(ApiService);

  lister(filtres: IntegrationClientFiltres, page = 1, size = 25): Observable<IntegrationClientPage> {
    return this.api.get<IntegrationClientPage>(BASE, clientsParams(filtres, page, size));
  }

  fiche(id: string): Observable<IntegrationClientFiche> {
    return this.api.get<IntegrationClientFiche>(`${BASE}/${encodeURIComponent(id)}`);
  }

  creer(saisie: IntegrationClientSaisie): Observable<IntegrationClientFiche> {
    return this.api.post<IntegrationClientFiche>(BASE, saisie);
  }

  modifier(id: string, revision: number, champs: Partial<IntegrationClientSaisie>): Observable<IntegrationClientFiche> {
    return this.api.patch<IntegrationClientFiche>(`${BASE}/${encodeURIComponent(id)}`, { ...champs, revision });
  }

  archiver(id: string, revision: number, motif: string): Observable<IntegrationClientFiche> {
    return this.api.post<IntegrationClientFiche>(`${BASE}/${encodeURIComponent(id)}/archive`, { revision, motif });
  }

  dependances(id: string): Observable<BilanSuppression> {
    return this.api.get<BilanSuppression>(`${BASE}/${encodeURIComponent(id)}/dependances`);
  }

  supprimer(id: string, revision: number): Observable<void> {
    return this.api.delete<void>(`${BASE}/${encodeURIComponent(id)}?revision=${revision}`);
  }

  grants(id: string): Observable<IntegrationGrantListe> {
    return this.api.get<IntegrationGrantListe>(`${BASE}/${encodeURIComponent(id)}/grants`);
  }

  demander(id: string, operationIds: string[], justification: string | null): Observable<IntegrationGrantListe> {
    return this.api.post<IntegrationGrantListe>(`${BASE}/${encodeURIComponent(id)}/grants`, {
      operation_ids: operationIds,
      justification,
    });
  }

  decider(id: string, grantId: string, statut: IntegrationGrantStatut, motif: string | null): Observable<IntegrationGrant> {
    return this.api.patch<IntegrationGrant>(`${BASE}/${encodeURIComponent(id)}/grants/${encodeURIComponent(grantId)}`, {
      statut,
      motif,
    });
  }

  historique(id: string, page = 1, size = 50): Observable<IntegrationHistorique> {
    return this.api.get<IntegrationHistorique>(`${BASE}/${encodeURIComponent(id)}/historique`, { page, size });
  }

  admissibles(
    id: string,
    filtres: { q?: string; module?: string; methode?: string; admissibles_seulement?: boolean },
    page = 1,
    size = 25,
  ): Observable<IntegrationOperationsAdmissibles> {
    const params = clientsParams({}, page, size);
    if (filtres.q?.trim()) params['q'] = filtres.q.trim();
    if (filtres.module?.trim()) params['module'] = filtres.module.trim();
    if (filtres.methode) params['methode'] = filtres.methode;
    params['admissibles_seulement'] = filtres.admissibles_seulement !== false;
    return this.api.get<IntegrationOperationsAdmissibles>(`${BASE}/${encodeURIComponent(id)}/operations-admissibles`, params);
  }

  documentation(id: string): Observable<IntegrationDocumentation> {
    return this.api.get<IntegrationDocumentation>(`${BASE}/${encodeURIComponent(id)}/documentation`);
  }
}
