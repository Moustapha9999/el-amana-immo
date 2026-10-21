import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import {
  catalogueParams,
  IntegrationCatalogueFiltreValeurs,
  IntegrationCataloguePage,
  IntegrationConsoleOperations,
  IntegrationConsoleRequete,
  IntegrationConsoleResultat,
  IntegrationExemples,
  IntegrationOperationFiche,
} from './core-admin-integrations.models';

const BASE = '/plateforme/admin/integrations';

/** Studio d'intégration API — chaque endpoint revérifie `core.admin.integrations.view` côté serveur. */
@Injectable({ providedIn: 'root' })
export class CoreAdminIntegrationsService {
  private readonly api = inject(ApiService);

  catalogue(filtres: IntegrationCatalogueFiltreValeurs, page = 1, size = 25): Observable<IntegrationCataloguePage> {
    return this.api.get<IntegrationCataloguePage>(`${BASE}/catalogue`, catalogueParams(filtres, page, size));
  }

  fiche(operationId: string): Observable<IntegrationOperationFiche> {
    return this.api.get<IntegrationOperationFiche>(`${BASE}/catalogue/${encodeURIComponent(operationId)}`);
  }

  exemples(operationId: string): Observable<IntegrationExemples> {
    return this.api.get<IntegrationExemples>(`${BASE}/catalogue/${encodeURIComponent(operationId)}/exemples`);
  }

  operationsConsole(): Observable<IntegrationConsoleOperations> {
    return this.api.get<IntegrationConsoleOperations>(`${BASE}/console/operations`);
  }

  executer(requete: IntegrationConsoleRequete): Observable<IntegrationConsoleResultat> {
    return this.api.post<IntegrationConsoleResultat>(`${BASE}/console/executer`, requete);
  }
}
