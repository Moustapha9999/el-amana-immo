import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import {
  AnalyseSpec,
  FournisseurFiche,
  FournisseurFiltres,
  FournisseurPage,
  FournisseurSaisie,
  FournisseurStatut,
  fournisseursParams,
  HistoriqueFournisseur,
  OperationDetail,
  OperationListe,
  OperationManuelleSaisie,
  SpecDetail,
  SpecListe,
} from './core-admin-integration-fournisseurs.models';
import type { BilanSuppression } from './core-admin-integration-ui';

const BASE = '/plateforme/admin/integrations/fournisseurs';

/** Fournisseurs d'API externes — configuration seulement : aucune de ces routes n'appelle le fournisseur. */
@Injectable({ providedIn: 'root' })
export class CoreAdminIntegrationFournisseursService {
  private readonly api = inject(ApiService);

  private url(id: string, suite = ''): string {
    return `${BASE}/${encodeURIComponent(id)}${suite}`;
  }

  lister(filtres: FournisseurFiltres, page = 1, size = 25): Observable<FournisseurPage> {
    return this.api.get<FournisseurPage>(BASE, fournisseursParams(filtres, page, size));
  }

  fiche(id: string): Observable<FournisseurFiche> {
    return this.api.get<FournisseurFiche>(this.url(id));
  }

  creer(saisie: FournisseurSaisie): Observable<FournisseurFiche> {
    return this.api.post<FournisseurFiche>(BASE, saisie);
  }

  modifier(id: string, revision: number, champs: Partial<FournisseurSaisie>): Observable<FournisseurFiche> {
    return this.api.patch<FournisseurFiche>(this.url(id), { ...champs, revision });
  }

  changerStatut(id: string, revision: number, statut: FournisseurStatut, motif: string | null): Observable<FournisseurFiche> {
    return this.api.post<FournisseurFiche>(this.url(id, '/statut'), { revision, statut, motif });
  }

  archiver(id: string, revision: number, motif: string): Observable<FournisseurFiche> {
    return this.api.post<FournisseurFiche>(this.url(id, '/archive'), { revision, motif });
  }

  historique(id: string, page = 1, size = 50): Observable<HistoriqueFournisseur> {
    return this.api.get<HistoriqueFournisseur>(this.url(id, '/historique'), { page, size });
  }

  analyser(id: string, fichier: File): Observable<AnalyseSpec> {
    return this.api.upload<AnalyseSpec>(this.url(id, '/specs/analyse'), fichier);
  }

  importer(id: string, fichier: File, empreinte: string, versionCourante: number | null, accepterConflits: boolean): Observable<SpecDetail> {
    const champs: Record<string, string> = { empreinte, accepter_conflits: String(accepterConflits) };
    if (versionCourante != null) champs['version_courante'] = String(versionCourante);
    return this.api.upload<SpecDetail>(this.url(id, '/specs'), fichier, champs);
  }

  specs(id: string): Observable<SpecListe> {
    return this.api.get<SpecListe>(this.url(id, '/specs'));
  }

  spec(id: string, specId: string): Observable<SpecDetail> {
    return this.api.get<SpecDetail>(this.url(id, `/specs/${encodeURIComponent(specId)}`));
  }

  operations(
    id: string,
    filtres: { q?: string; methode?: string; origine?: string },
    page = 1,
    size = 50,
  ): Observable<OperationListe> {
    const params: Record<string, string | number> = { page, size };
    if (filtres.q?.trim()) params['q'] = filtres.q.trim();
    if (filtres.methode) params['methode'] = filtres.methode;
    if (filtres.origine) params['origine'] = filtres.origine;
    return this.api.get<OperationListe>(this.url(id, '/operations'), params);
  }

  operation(id: string, opId: string): Observable<OperationDetail> {
    return this.api.get<OperationDetail>(this.url(id, `/operations/${encodeURIComponent(opId)}`));
  }

  creerOperation(id: string, saisie: OperationManuelleSaisie): Observable<OperationDetail> {
    return this.api.post<OperationDetail>(this.url(id, '/operations'), saisie);
  }

  modifierOperation(id: string, opId: string, revision: number, saisie: OperationManuelleSaisie): Observable<OperationDetail> {
    return this.api.patch<OperationDetail>(this.url(id, `/operations/${encodeURIComponent(opId)}`), { ...saisie, revision });
  }

  archiverOperation(id: string, opId: string, revision: number): Observable<OperationDetail> {
    return this.api.post<OperationDetail>(this.url(id, `/operations/${encodeURIComponent(opId)}/archive`), { revision });
  }

  dependances(id: string): Observable<BilanSuppression> {
    return this.api.get<BilanSuppression>(this.url(id, '/dependances'));
  }

  supprimer(id: string, revision: number): Observable<void> {
    return this.api.delete<void>(this.url(id, `?revision=${revision}`));
  }

  dependancesOperation(id: string, opId: string): Observable<BilanSuppression> {
    return this.api.get<BilanSuppression>(this.url(id, `/operations/${encodeURIComponent(opId)}/dependances`));
  }

  supprimerOperation(id: string, opId: string, revision: number): Observable<void> {
    return this.api.delete<void>(this.url(id, `/operations/${encodeURIComponent(opId)}?revision=${revision}`));
  }
}
