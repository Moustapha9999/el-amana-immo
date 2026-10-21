import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import type { BilanSuppression } from './core-admin-integration-ui';
import {
  AlerteHistorique,
  AlerteItem,
  AlertePage,
  AlerteStatut,
  DestinationFiche,
  DestinationPage,
  DestinationSaisie,
  DestinationStatut,
  ExecutionDetail,
  ExecutionPage,
  TableauSupervision,
  TestApercu,
} from './core-admin-integration-execution.models';

const DEST = '/plateforme/admin/integrations/destinations';
const INTEG = '/plateforme/admin/integrations';

@Injectable({ providedIn: 'root' })
export class CoreAdminIntegrationExecutionService {
  private readonly api = inject(ApiService);

  listerDestinations(
    filtres: { q?: string; statut?: string; fournisseur_id?: string; inclure_archivees?: boolean; tri?: string; ordre?: string },
    page = 1,
    size = 25,
  ): Observable<DestinationPage> {
    const params: Record<string, string | number | boolean> = { page, size };
    for (const [k, v] of Object.entries(filtres)) {
      if (v !== undefined && v !== null && v !== '' && v !== false) params[k] = v as string | number | boolean;
    }
    return this.api.get<DestinationPage>(DEST, params);
  }

  ficheDestination(id: string): Observable<DestinationFiche> {
    return this.api.get<DestinationFiche>(`${DEST}/${encodeURIComponent(id)}`);
  }

  creerDestination(saisie: DestinationSaisie): Observable<DestinationFiche> {
    return this.api.post<DestinationFiche>(DEST, saisie);
  }

  modifierDestination(id: string, revision: number, champs: Partial<DestinationSaisie>): Observable<DestinationFiche> {
    return this.api.patch<DestinationFiche>(`${DEST}/${encodeURIComponent(id)}`, { ...champs, revision });
  }

  changerStatutDestination(id: string, revision: number, statut: DestinationStatut, motif: string | null): Observable<DestinationFiche> {
    return this.api.post<DestinationFiche>(`${DEST}/${encodeURIComponent(id)}/statut`, { revision, statut, motif });
  }

  archiverDestination(id: string, revision: number, motif: string): Observable<DestinationFiche> {
    return this.api.post<DestinationFiche>(`${DEST}/${encodeURIComponent(id)}/archive`, { revision, motif });
  }

  dependancesDestination(id: string): Observable<BilanSuppression> {
    return this.api.get<BilanSuppression>(`${DEST}/${encodeURIComponent(id)}/dependances`);
  }

  supprimerDestination(id: string, revision: number): Observable<void> {
    return this.api.delete<void>(`${DEST}/${encodeURIComponent(id)}?revision=${revision}`);
  }

  historiqueDestination(id: string, page = 1, size = 50) {
    return this.api.get<{ items: { id: string; action: string; libelle: string; created_at: string }[]; total: number }>(
      `${DEST}/${encodeURIComponent(id)}/historique`,
      { page, size },
    );
  }

  apercu(corps: { fournisseur_id: string; operation_id: string; destination_id: string; parametres_chemin: Record<string, string>; parametres_requete: Record<string, string> }): Observable<TestApercu> {
    return this.api.post<TestApercu>(`${INTEG}/tests/apercu`, corps);
  }

  executer(corps: { fournisseur_id: string; operation_id: string; destination_id: string; parametres_chemin: Record<string, string>; parametres_requete: Record<string, string> }): Observable<ExecutionDetail> {
    return this.api.post<ExecutionDetail>(`${INTEG}/tests/executer`, { ...corps, confirmation: true });
  }

  executions(filtres: Record<string, string>, page = 1, size = 25): Observable<ExecutionPage> {
    return this.api.get<ExecutionPage>(`${INTEG}/executions`, { ...filtres, page, size });
  }

  execution(id: string): Observable<ExecutionDetail> {
    return this.api.get<ExecutionDetail>(`${INTEG}/executions/${encodeURIComponent(id)}`);
  }

  tableau(filtres: Record<string, string>): Observable<TableauSupervision> {
    return this.api.get<TableauSupervision>(`${INTEG}/supervision`, filtres);
  }

  alertes(filtres: Record<string, string>, page = 1, size = 25): Observable<AlertePage> {
    return this.api.get<AlertePage>(`${INTEG}/supervision/alertes`, { ...filtres, page, size });
  }

  changerAlerte(id: string, statut: AlerteStatut) {
    return this.api.patch<AlerteItem>(`${INTEG}/supervision/alertes/${encodeURIComponent(id)}`, { statut });
  }

  historiqueAlerte(id: string): Observable<{ items: AlerteHistorique[] }> {
    return this.api.get<{ items: AlerteHistorique[] }>(`${INTEG}/supervision/alertes/${encodeURIComponent(id)}/historique`);
  }

  exporter(filtres: Record<string, string>): Observable<Blob> {
    return this.api.download(`${INTEG}/supervision/export`, filtres);
  }
}
