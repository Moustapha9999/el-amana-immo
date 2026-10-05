import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../core/services/api.service';
import {
  EerAnomalie,
  EerAudit,
  EerChecklist,
  EerComplement,
  EerConformite,
  EerControle,
  EerConstat,
  EerDecision,
  EerDocument,
  EerDossier,
  EerDossierLigne,
  EerFicheChamp,
  EerHistorique,
  EerKpiEtatsCompte,
  EerKpiGlobal,
  EerKpiRepartition,
  EerKpiSerie,
  EerMutation,
  EerPage,
  EerPerimetre,
  EerTableauDeBord,
  EerVersion,
  EerVersionLigne,
  EerVisa,
} from './eer.models';

export interface EerAgence {
  id: string;
  code: string;
  libelle: string;
}

export interface EerReferentiel {
  domaine: string;
  code: string;
  libelle: string;
  parent_code: string | null;
  ordre: number;
  meta: Record<string, unknown>;
}

export interface EerAnalyste {
  id: string;
  nom: string;
}

export type EerFiltres = Partial<{
  statut: string | string[];
  agence_id: string;
  type_client: string;
  profil: string;
  risque: string;
  decision: string;
  avis_requis: boolean;
  mes_dossiers: boolean;
  q: string;
  date_debut: string;
  date_fin: string;
  sous_profil: string;
  ppe: string;
  fatca: string;
  analyste_id: string;
  etat_compte: string;
  residence: string;
  conformite_excel: string;
  page: number;
  size: number;
  tri: string;
  ordre: 'asc' | 'desc';
}>;

export type EerKpiFiltres = Partial<{
  agence_id: string;
  type_client: string;
  date_debut: string;
  date_fin: string;
}>;

export type EerGranularite = 'jour' | 'semaine' | 'mois' | 'annee';
export type EerDimension = 'risque' | 'ppe' | 'fatca' | 'residence' | 'analyste' | 'profil' | 'sous_profil';

function nettoyer(filtres: Record<string, unknown>): Record<string, string> {
  const params: Record<string, string> = {};
  for (const [k, v] of Object.entries(filtres)) {
    if (v !== undefined && v !== null && v !== '') params[k] = String(v);
  }
  return params;
}

/** Accès HTTP du module EER. Toute mutation transmet la `revision` connue (409 si périmée). */
@Injectable({ providedIn: 'root' })
export class EerService {
  private readonly api = inject(ApiService);
  private readonly base = '/eer';

  perimetre(): Observable<EerPerimetre> {
    return this.api.get(`${this.base}/perimetre`);
  }

  tableauDeBord(agenceId?: string): Observable<EerTableauDeBord> {
    return this.api.get(`${this.base}/dashboard`, agenceId ? { agence_id: agenceId } : undefined);
  }

  kpis(filtres: EerKpiFiltres = {}): Observable<EerKpiGlobal> {
    return this.api.get(`${this.base}/kpis`, nettoyer(filtres));
  }

  kpisAgences(filtres: EerKpiFiltres = {}): Observable<EerKpiRepartition> {
    return this.api.get(`${this.base}/kpis/agencies`, nettoyer(filtres));
  }

  kpisProfils(filtres: EerKpiFiltres = {}): Observable<EerKpiRepartition> {
    return this.api.get(`${this.base}/kpis/profiles`, nettoyer(filtres));
  }

  kpisEtatsCompte(filtres: EerKpiFiltres = {}): Observable<EerKpiEtatsCompte> {
    return this.api.get(`${this.base}/kpis/account-statuses`, nettoyer(filtres));
  }

  kpisSerie(granularite: EerGranularite, filtres: EerKpiFiltres = {}): Observable<EerKpiSerie> {
    return this.api.get(`${this.base}/kpis/timeseries`, { ...nettoyer(filtres), granularite });
  }

  kpisDimension(dimension: EerDimension, filtres: EerKpiFiltres = {}): Observable<EerKpiRepartition> {
    return this.api.get(`${this.base}/kpis/dimensions/${dimension}`, nettoyer(filtres));
  }

  conformite(id: string): Observable<EerConformite> {
    return this.api.get(this.url(id, 'compliance'));
  }

  agences(): Observable<EerAgence[]> {
    return this.api.get(`${this.base}/agences`);
  }

  referentiels(domaine: string): Observable<EerReferentiel[]> {
    return this.api.get(`${this.base}/referentiels`, { domaine });
  }

  lister(filtres: EerFiltres): Observable<EerPage<EerDossierLigne>> {
    const params: Record<string, string | number | boolean | string[]> = {};
    for (const [k, v] of Object.entries(filtres)) {
      if (v !== undefined && v !== null && v !== '') params[k] = v;
    }
    return this.api.get(`${this.base}/dossiers`, params as Record<string, string>);
  }

  creer(payload: unknown): Observable<EerDossier> {
    return this.api.post(`${this.base}/dossiers`, payload);
  }

  lire(id: string): Observable<EerDossier> {
    return this.api.get(`${this.base}/dossiers/${id}`);
  }

  private url(id: string, suffixe: string): string {
    return `${this.base}/dossiers/${id}/${suffixe}`;
  }

  modifier(id: string, revision: number, champs: Array<{ chemin: string; valeur: unknown; dossier_partie_id?: string | null }>): Observable<EerMutation> {
    return this.api.patch(`${this.base}/dossiers/${id}`, { revision, champs });
  }

  /** Actions POST simples : submit, start-control, request-avis, validate, close, archive, abandon, resubmit, … */
  action(id: string, chemin: string, revision: number, corps: Record<string, unknown> = {}): Observable<EerMutation> {
    return this.api.post(this.url(id, chemin), { revision, ...corps });
  }

  analystes(id: string): Observable<EerAnalyste[]> {
    return this.api.get(this.url(id, 'analystes'));
  }

  checklist(id: string): Observable<EerChecklist> {
    return this.api.get(this.url(id, 'checklist'));
  }

  pointer(id: string, itemId: string, revision: number, presence: string, motif?: string | null): Observable<EerMutation> {
    return this.api.patch(this.url(id, `checklist/items/${itemId}`), { revision, presence, motif: motif || null });
  }

  controler(id: string, itemId: string, revision: number, conforme: boolean, motif?: string | null): Observable<EerMutation> {
    return this.api.patch(this.url(id, `controls/${itemId}`), { revision, conforme, motif: motif || null });
  }

  fiches(id: string): Observable<Record<string, EerFicheChamp[]>> {
    return this.api.get(this.url(id, 'fiches'));
  }

  controles(id: string): Observable<{ controles: EerControle[]; decisions: EerDecision[] }> {
    return this.api.get(this.url(id, 'controls'));
  }

  controlesAuto(id: string, revision: number): Observable<{ revision: number; constats: EerConstat[] }> {
    return this.api.post(this.url(id, 'controls'), { revision });
  }

  anomalies(id: string): Observable<EerAnomalie[]> {
    return this.api.get(this.url(id, 'anomalies'));
  }

  modifierAnomalie(id: string, anomalieId: string, revision: number, corps: Record<string, unknown>): Observable<EerMutation> {
    return this.api.patch(this.url(id, `anomalies/${anomalieId}`), { revision, ...corps });
  }

  complements(id: string): Observable<EerComplement[]> {
    return this.api.get(this.url(id, 'complements'));
  }

  avis(id: string): Observable<EerVisa[]> {
    return this.api.get(this.url(id, 'avis'));
  }

  versions(id: string): Observable<EerVersionLigne[]> {
    return this.api.get(this.url(id, 'versions'));
  }

  version(id: string, versionId: string): Observable<EerVersion> {
    return this.api.get(this.url(id, `versions/${versionId}`));
  }

  historique(id: string): Observable<EerHistorique[]> {
    return this.api.get(this.url(id, 'history'));
  }

  documents(id: string): Observable<EerDocument[]> {
    return this.api.get(this.url(id, 'documents'));
  }

  audit(id: string): Observable<EerAudit[]> {
    return this.api.get(this.url(id, 'audit'));
  }
}
