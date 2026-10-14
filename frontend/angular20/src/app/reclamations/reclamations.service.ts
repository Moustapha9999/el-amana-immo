import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import {
  ApercuClient,
  Capacite,
  ColonneCircuit,
  Domaine,
  Dossier,
  DossierLigne,
  Evenement,
  LigneAudit,
  Membre,
  Page,
  Pieces,
  RC_BASE,
  RcConfig,
  RefItem,
  RegleDelai,
  TableauBord,
  Unite,
  UtilisateurTrouve,
} from './reclamations.models';

export type Filtres = Record<string, string | number | boolean | string[] | null | undefined>;

function parametres(filtres: Filtres): Record<string, string> {
  const params: Record<string, string> = {};
  for (const [k, v] of Object.entries(filtres)) {
    if (v === undefined || v === null || v === '' || v === false) continue;
    params[k] = Array.isArray(v) ? (v as unknown as string) : String(v);
  }
  return params;
}

/** Accès HTTP du module. Les droits affichés sont indicatifs : le backend revérifie tout. */
@Injectable({ providedIn: 'root' })
export class ReclamationsService {
  private readonly api = inject(ApiService);

  config(): Observable<RcConfig> {
    return this.api.get(`${RC_BASE}/config`);
  }

  lister(filtres: Filtres): Observable<Page<DossierLigne>> {
    return this.api.get(`${RC_BASE}/dossiers`, parametres(filtres));
  }

  lire(id: string): Observable<Dossier> {
    return this.api.get(`${RC_BASE}/dossiers/${id}`);
  }

  creer(corps: unknown): Observable<Dossier> {
    return this.api.post(`${RC_BASE}/dossiers`, corps);
  }

  modifier(id: string, corps: unknown): Observable<Dossier> {
    return this.api.patch(`${RC_BASE}/dossiers/${id}`, corps);
  }

  ajouterAppel(id: string, corps: unknown): Observable<Dossier> {
    return this.api.post(`${RC_BASE}/dossiers/${id}/appels`, corps);
  }

  chronologie(id: string): Observable<Evenement[]> {
    return this.api.get(`${RC_BASE}/dossiers/${id}/chronologie`);
  }

  audit(id: string): Observable<LigneAudit[]> {
    return this.api.get(`${RC_BASE}/dossiers/${id}/audit`);
  }

  apercuClient(racine: string): Observable<ApercuClient> {
    return this.api.get(`${RC_BASE}/clients/${racine}`);
  }

  pieces(id: string): Observable<Pieces> {
    return this.api.get(`${RC_BASE}/dossiers/${id}/documents`);
  }

  deposer(id: string, fichier: File, categorie: string, commentaire: string): Observable<Pieces> {
    return this.api.upload(`${RC_BASE}/dossiers/${id}/documents`, fichier, { categorie, commentaire });
  }

  retirer(id: string, pieceId: string, motif: string): Observable<Pieces> {
    return this.api.post(`${RC_BASE}/dossiers/${id}/documents/${pieceId}/retrait`, { motif });
  }

  fichier(id: string, pieceId: string, apercu = false): Observable<Blob> {
    return this.api.download(`${RC_BASE}/dossiers/${id}/documents/${pieceId}/fichier`, apercu ? { apercu: 'true' } : undefined);
  }

  referentiels(): Observable<RefItem[]> {
    return this.api.get(`${RC_BASE}/referentiels`);
  }

  creerReferentiel(corps: unknown): Observable<RefItem> {
    return this.api.post(`${RC_BASE}/referentiels`, corps);
  }

  modifierReferentiel(id: string, corps: unknown): Observable<RefItem> {
    return this.api.patch(`${RC_BASE}/referentiels/${id}`, corps);
  }

  supprimerReferentiel(id: string): Observable<void> {
    return this.api.delete(`${RC_BASE}/referentiels/${id}`);
  }

  unites(): Observable<Unite[]> {
    return this.api.get(`${RC_BASE}/unites`);
  }

  creerUnite(corps: unknown): Observable<Unite> {
    return this.api.post(`${RC_BASE}/unites`, corps);
  }

  modifierUnite(id: string, corps: unknown): Observable<Unite> {
    return this.api.patch(`${RC_BASE}/unites/${id}`, corps);
  }

  membres(uniteId: string): Observable<Membre[]> {
    return this.api.get(`${RC_BASE}/unites/${uniteId}/membres`);
  }

  ajouterMembre(uniteId: string, userId: string, role: string): Observable<Membre[]> {
    return this.api.post(`${RC_BASE}/unites/${uniteId}/membres`, { user_id: userId, role_membre: role });
  }

  modifierMembre(uniteId: string, membreId: string, corps: unknown): Observable<Membre[]> {
    return this.api.patch(`${RC_BASE}/unites/${uniteId}/membres/${membreId}`, corps);
  }

  utilisateurs(q: string): Observable<UtilisateurTrouve[]> {
    return this.api.get(`${RC_BASE}/utilisateurs`, { q });
  }

  action(id: string, verbe: string, corps: unknown): Observable<Dossier> {
    return this.api.post(`${RC_BASE}/dossiers/${id}/${verbe}`, corps);
  }

  enregistrerReponse(id: string, corps: unknown): Observable<Dossier> {
    return this.api.post(`${RC_BASE}/dossiers/${id}/reponse`, corps);
  }

  actionReponse(id: string, verbe: string, corps: unknown): Observable<Dossier> {
    return this.api.post(`${RC_BASE}/dossiers/${id}/reponse/${verbe}`, corps);
  }

  tableauDeBord(): Observable<TableauBord> {
    return this.api.get(`${RC_BASE}/tableau-de-bord`);
  }

  circuit(): Observable<{ colonnes: ColonneCircuit[]; total: number }> {
    return this.api.get(`${RC_BASE}/circuit`);
  }

  alertes(): Observable<{ retards: DossierLigne[]; alertes: DossierLigne[]; nb_retards: number; nb_alertes: number }> {
    return this.api.get(`${RC_BASE}/alertes`);
  }

  exportUrl(filtres: Filtres = {}): string {
    const q = new URLSearchParams(parametres(filtres)).toString();
    return `/api/v1${RC_BASE}/export${q ? '?' + q : ''}`;
  }

  exporter(filtres: Filtres = {}): Observable<Blob> {
    return this.api.download(`${RC_BASE}/export`, parametres(filtres));
  }

  regles(): Observable<RegleDelai[]> {
    return this.api.get(`${RC_BASE}/regles-delai`);
  }

  creerRegle(corps: unknown): Observable<RegleDelai> {
    return this.api.post(`${RC_BASE}/regles-delai`, corps);
  }

  modifierRegle(id: string, corps: unknown): Observable<RegleDelai> {
    return this.api.patch(`${RC_BASE}/regles-delai/${id}`, corps);
  }

  validerRegle(id: string, corps: unknown): Observable<RegleDelai> {
    return this.api.post(`${RC_BASE}/regles-delai/${id}/validation`, corps);
  }

  feries(): Observable<Array<{ jour: string; libelle: string }>> {
    return this.api.get(`${RC_BASE}/jours-feries`);
  }

  ajouterFerie(jour: string, libelle: string): Observable<Array<{ jour: string; libelle: string }>> {
    return this.api.post(`${RC_BASE}/jours-feries`, { jour, libelle });
  }

  retirerFerie(jour: string): Observable<void> {
    return this.api.delete(`${RC_BASE}/jours-feries/${jour}`);
  }
}

/** Configuration du module (accès, référentiels, unités), chargée une fois puis rafraîchie après modification. */
@Injectable({ providedIn: 'root' })
export class ReclamationsStore {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  private enCours = false;

  readonly config = signal<RcConfig | null>(null);
  readonly unites = computed(() => this.config()?.unites ?? []);
  readonly unitesActives = computed(() => this.unites().filter((u) => u.actif));

  charger(force = false): void {
    if ((this.config() && !force) || this.enCours) return;
    this.enCours = true;
    this.rc.config().subscribe({
      next: (c) => {
        this.config.set(c);
        this.enCours = false;
      },
      error: (e) => {
        this.enCours = false;
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Configuration du module indisponible'));
      },
    });
  }

  recharger$(): Observable<RcConfig> {
    return this.rc.config().pipe(tap((c) => this.config.set(c)));
  }

  cap(c: Capacite): boolean {
    return !!this.config()?.acces.capacites[c];
  }

  refs(domaine: Domaine, inclureInactifs = false): RefItem[] {
    const liste = this.config()?.referentiels[domaine] ?? [];
    return inclureInactifs ? liste : liste.filter((r) => r.actif);
  }

  enfants(domaine: Domaine, parentId: string | null | undefined): RefItem[] {
    if (!parentId) return [];
    return this.refs(domaine).filter((r) => r.parent_id === parentId);
  }

  libelles(cle: keyof RcConfig['libelles']): Array<{ code: string; libelle: string }> {
    const l = this.config()?.libelles[cle];
    return Array.isArray(l) ? l : [];
  }

  /** Unités proposées comme point de réception : toutes (périmètre global) ou celles de l'agent. */
  unitesReception(): Unite[] {
    const c = this.config();
    if (!c) return [];
    if (c.acces.perimetre === 'TOUS') return this.unitesActives();
    return this.unitesActives().filter((u) => c.acces.unites.includes(u.id));
  }
}
