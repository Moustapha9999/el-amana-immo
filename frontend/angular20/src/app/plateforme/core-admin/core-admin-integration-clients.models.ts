import { HttpErrorResponse } from '@angular/common/http';
import { computed, inject } from '@angular/core';
import { AbstractControl, ValidationErrors } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';
import { IntegrationExemple } from './core-admin-integrations.models';

export type IntegrationEnvironnement = 'DEV' | 'TEST';
export type IntegrationClientStatut = 'brouillon' | 'en_preparation' | 'active' | 'suspendue' | 'archivee';
export type IntegrationGrantStatut = 'demandee' | 'en_attente' | 'approuvee' | 'refusee' | 'revoquee' | 'retiree';

export interface IntegrationPersonne {
  id: string;
  nom?: string | null;
}

export interface IntegrationEntite {
  id: string;
  code?: string | null;
  libelle?: string | null;
  actif: boolean;
}

export interface IntegrationClientResume {
  id: string;
  code: string;
  nom: string;
  description?: string | null;
  entite?: IntegrationEntite | null;
  environnement: IntegrationEnvironnement;
  statut: IntegrationClientStatut;
  nb_operations: number;
  nb_approuvees: number;
  created_at: string;
  updated_at: string;
  cree_par?: IntegrationPersonne | null;
  modifie_par?: IntegrationPersonne | null;
}

export interface IntegrationClientPage {
  items: IntegrationClientResume[];
  total: number;
  page: number;
  size: number;
  avertissement: string;
}

export interface IntegrationClientFiche extends IntegrationClientResume {
  contact_technique?: string | null;
  finalite?: string | null;
  notes?: string | null;
  revision: number;
  archived_at?: string | null;
  archive_par?: IntegrationPersonne | null;
  motif_archivage?: string | null;
  transitions: IntegrationClientStatut[];
  avertissement: string;
}

export interface IntegrationClientSaisie {
  nom: string;
  description: string | null;
  org_entite_id: string | null;
  contact_technique: string | null;
  environnement: IntegrationEnvironnement;
  finalite: string | null;
  notes: string | null;
  statut?: IntegrationClientStatut;
}

export interface IntegrationGrant {
  id: string;
  operation_id: string;
  methode: string;
  chemin: string;
  module?: string | null;
  permissions: string[];
  exigence_permissions?: string | null;
  statut: IntegrationGrantStatut;
  justification?: string | null;
  motif?: string | null;
  demande_par?: IntegrationPersonne | null;
  decide_par?: IntegrationPersonne | null;
  decide_le?: string | null;
  created_at: string;
  updated_at: string;
  catalogue_present: boolean;
  admissible: boolean;
  motif_inadmissible?: string | null;
}

export interface IntegrationGrantListe {
  items: IntegrationGrant[];
  compteurs: Partial<Record<IntegrationGrantStatut, number>>;
  avertissement: string;
}

export interface IntegrationGrantEvenement {
  id: string;
  grant_id: string;
  operation_id: string;
  ancien_statut?: IntegrationGrantStatut | null;
  nouveau_statut: IntegrationGrantStatut;
  motif?: string | null;
  acteur?: IntegrationPersonne | null;
  created_at: string;
}

export interface IntegrationHistorique {
  items: IntegrationGrantEvenement[];
  total: number;
  page: number;
  size: number;
}

export interface IntegrationOperationAdmissible {
  operation_id: string;
  nom: string;
  methode: string;
  chemin: string;
  module: string;
  module_code?: string | null;
  resume?: string | null;
  permissions: string[];
  exigence_permissions?: string | null;
  authentification: string;
  admissible: boolean;
  motif_inadmissible?: string | null;
  deja_demandee?: IntegrationGrantStatut | null;
}

export interface IntegrationOperationsAdmissibles {
  items: IntegrationOperationAdmissible[];
  total: number;
  page: number;
  size: number;
  avertissement: string;
}

export interface IntegrationDocOperation {
  operation_id: string;
  methode: string;
  chemin: string;
  module?: string | null;
  resume?: string | null;
  permissions: string[];
  exigence_permissions?: string | null;
  statut: IntegrationGrantStatut;
  decide_le?: string | null;
  prerequis: string[];
  exemples: IntegrationExemple[];
  exemples_motif?: string | null;
}

export interface IntegrationDocumentation {
  client_code: string;
  nom: string;
  environnement: IntegrationEnvironnement;
  statut: IntegrationClientStatut;
  genere_le: string;
  operations: IntegrationDocOperation[];
  en_attente: number;
  avertissements: string[];
  markdown: string;
}

export interface IntegrationClientFiltres {
  q?: string;
  statut?: string;
  environnement?: string;
  inclure_archivees?: boolean;
  tri?: string;
  ordre?: string;
}

export const PERMISSIONS_CLIENTS = {
  clientsView: 'core.admin.integrations.clients.view',
  clientsManage: 'core.admin.integrations.clients.manage',
  grantsView: 'core.admin.integrations.grants.view',
  grantsManage: 'core.admin.integrations.grants.manage',
  grantsApprove: 'core.admin.integrations.grants.approve',
  export: 'core.admin.integrations.export',
} as const;

/** Masquage UI seulement : chaque endpoint revérifie la permission côté serveur. */
export function integrationClientsPermissions() {
  const auth = inject(AuthService);
  const has = (code: string) =>
    computed(() => {
      const p = auth.user();
      if (!p) return false;
      const codes = p.permission_codes ?? [];
      return p.is_superuser || codes.includes('*') || codes.includes(code);
    });
  return {
    clientsView: has(PERMISSIONS_CLIENTS.clientsView),
    clientsManage: has(PERMISSIONS_CLIENTS.clientsManage),
    grantsView: has(PERMISSIONS_CLIENTS.grantsView),
    grantsManage: has(PERMISSIONS_CLIENTS.grantsManage),
    grantsApprove: has(PERMISSIONS_CLIENTS.grantsApprove),
    export: has(PERMISSIONS_CLIENTS.export),
  };
}

const CLIENT_STATUTS: Record<IntegrationClientStatut, string> = {
  brouillon: 'Brouillon',
  en_preparation: 'En préparation',
  active: 'Active (configuration)',
  suspendue: 'Suspendue',
  archivee: 'Archivée',
};

const CLIENT_TRANSITIONS: Record<IntegrationClientStatut, string> = {
  brouillon: 'Revenir en brouillon',
  en_preparation: 'Passer en préparation',
  active: 'Activer la fiche',
  suspendue: 'Suspendre',
  archivee: 'Archiver',
};

const GRANT_STATUTS: Record<IntegrationGrantStatut, string> = {
  demandee: 'Demandée',
  en_attente: 'En attente de validation',
  approuvee: 'Approuvée (configuration)',
  refusee: 'Refusée',
  revoquee: 'Révoquée',
  retiree: 'Retirée',
};

export function clientStatutLabel(s: string): string {
  return CLIENT_STATUTS[s as IntegrationClientStatut] ?? s;
}

export function clientTransitionLabel(s: string): string {
  return CLIENT_TRANSITIONS[s as IntegrationClientStatut] ?? s;
}

export function clientStatutTone(s: string): string {
  if (s === 'active') return 'bea-badge bea-badge--actif';
  if (s === 'brouillon' || s === 'en_preparation') return 'bea-badge bea-badge--bientot';
  return 'bea-badge bea-badge--inactif';
}

export function grantStatutLabel(s: string | null | undefined): string {
  if (!s) return '—';
  return GRANT_STATUTS[s as IntegrationGrantStatut] ?? s;
}

export function grantStatutTone(s: string): string {
  if (s === 'approuvee') return 'bea-badge bea-badge--actif';
  if (s === 'demandee' || s === 'en_attente') return 'bea-badge bea-badge--bientot';
  return 'bea-badge bea-badge--inactif';
}

export interface GrantAction {
  cible: IntegrationGrantStatut;
  libelle: string;
  droit: 'grantsManage' | 'grantsApprove';
  motif: 'obligatoire' | 'optionnel' | 'aucun';
  tone: 'primary' | 'danger';
}

/** Miroir des transitions serveur, pour l'affichage des boutons ; le serveur reste seul juge. */
export const GRANT_ACTIONS: Record<IntegrationGrantStatut, GrantAction[]> = {
  demandee: [
    { cible: 'en_attente', libelle: 'Soumettre pour validation', droit: 'grantsManage', motif: 'aucun', tone: 'primary' },
    { cible: 'retiree', libelle: 'Retirer', droit: 'grantsManage', motif: 'optionnel', tone: 'danger' },
  ],
  en_attente: [
    { cible: 'approuvee', libelle: 'Approuver', droit: 'grantsApprove', motif: 'optionnel', tone: 'primary' },
    { cible: 'refusee', libelle: 'Refuser', droit: 'grantsApprove', motif: 'obligatoire', tone: 'danger' },
    { cible: 'retiree', libelle: 'Retirer', droit: 'grantsManage', motif: 'optionnel', tone: 'danger' },
  ],
  approuvee: [{ cible: 'revoquee', libelle: 'Révoquer', droit: 'grantsApprove', motif: 'obligatoire', tone: 'danger' }],
  refusee: [{ cible: 'demandee', libelle: 'Redemander', droit: 'grantsManage', motif: 'aucun', tone: 'primary' }],
  revoquee: [{ cible: 'demandee', libelle: 'Redemander', droit: 'grantsManage', motif: 'aucun', tone: 'primary' }],
  retiree: [{ cible: 'demandee', libelle: 'Redemander', droit: 'grantsManage', motif: 'aucun', tone: 'primary' }],
};

export const STATUTS_OUVERTS: readonly IntegrationGrantStatut[] = ['demandee', 'en_attente', 'approuvee'];

export function clientsParams(f: IntegrationClientFiltres, page: number, size: number): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = { page, size };
  for (const [cle, valeur] of Object.entries(f)) {
    if (valeur === undefined || valeur === null || valeur === false) continue;
    if (typeof valeur === 'string') {
      const v = valeur.trim();
      if (v) params[cle] = v;
    } else {
      params[cle] = valeur;
    }
  }
  return params;
}

const SECRET_SUSPECT =
  /\bbearer\s+[a-z0-9._~+/=-]{12,}|\b(?:password|passwd|pwd|mot\s+de\s+passe|secret|client[_ -]?secret|api[_ -]?key|token|jeton)\s*[:=]\s*\S+|\beyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----/i;

/** Même règle que le serveur : aucun secret dans une fiche d'application. */
export function sansSecret(control: AbstractControl<string | null>): ValidationErrors | null {
  const v = control.value ?? '';
  return v && SECRET_SUSPECT.test(v) ? { secret: true } : null;
}

export function uneLigne(control: AbstractControl<string | null>): ValidationErrors | null {
  const v = control.value ?? '';
  return /[\r\n]/.test(v) ? { multiligne: true } : null;
}

export function texteOuNull(v: string | null | undefined): string | null {
  const t = (v ?? '').trim();
  return t ? t : null;
}

/** Message d'erreur serveur (format standard), avec la référence de requête quand elle existe. */
export function messageErreur(err: unknown, fallback: string): string {
  if (!(err instanceof HttpErrorResponse)) return fallback;
  const corps = err.error ?? {};
  let message = fallback;
  if (typeof corps.user_message === 'string' && corps.user_message.trim()) {
    message = corps.user_message;
  } else if (typeof corps.message === 'string' && corps.message.trim()) {
    message = corps.message;
  } else if (typeof corps.detail === 'string' && corps.detail.trim()) {
    message = corps.detail;
  }
  if (err.status === 422 && Array.isArray(corps.errors) && corps.errors.length) {
    const premiers = corps.errors
      .slice(0, 3)
      .map((e: { message?: string; msg?: string }) => e?.message ?? e?.msg)
      .filter(Boolean);
    if (premiers.length) message = `${message} — ${premiers.join(' ; ')}`;
  }
  return typeof corps.request_id === 'string' ? `${message} (réf. ${corps.request_id})` : message;
}

export function estAccesRefuse(err: unknown): boolean {
  return err instanceof HttpErrorResponse && (err.status === 401 || err.status === 403);
}

export function telechargerTexte(nomFichier: string, contenu: string, type = 'text/markdown;charset=utf-8'): void {
  const url = URL.createObjectURL(new Blob([contenu], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = nomFichier;
  a.click();
  URL.revokeObjectURL(url);
}
