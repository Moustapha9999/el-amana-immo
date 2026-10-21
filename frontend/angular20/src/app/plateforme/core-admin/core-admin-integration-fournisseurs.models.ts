import { computed, inject } from '@angular/core';
import { AbstractControl, ValidationErrors } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';
import { IntegrationEntite, IntegrationEnvironnement, IntegrationPersonne } from './core-admin-integration-clients.models';
import { IntegrationExemple } from './core-admin-integrations.models';

export type FournisseurStatut = 'brouillon' | 'a_valider' | 'valide' | 'suspendu' | 'archive';
export type OperationOrigine = 'openapi' | 'manuelle';
export type MethodeHttp = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS';
export type MecanismeAuth =
  | 'aucun'
  | 'api_key_header'
  | 'api_key_query'
  | 'http_basic'
  | 'http_bearer'
  | 'oauth2_client_credentials'
  | 'oauth2_autre'
  | 'mtls'
  | 'autre'
  | 'non_precise';

export const AUCUN_APPEL = 'Configuration enregistrée — aucun appel externe effectué.';

export interface FournisseurResume {
  id: string;
  code: string;
  nom: string;
  description?: string | null;
  entite?: IntegrationEntite | null;
  environnement: IntegrationEnvironnement;
  statut: FournisseurStatut;
  url_base?: string | null;
  version_courante?: number | null;
  nb_operations: number;
  created_at: string;
  updated_at: string;
  cree_par?: IntegrationPersonne | null;
  modifie_par?: IntegrationPersonne | null;
}

export interface FournisseurPage {
  items: FournisseurResume[];
  total: number;
  page: number;
  size: number;
  avertissement: string;
}

export interface FournisseurFiche extends FournisseurResume {
  responsable_interne?: string | null;
  contact_technique?: string | null;
  documentation?: string | null;
  notes?: string | null;
  motif_statut?: string | null;
  revision: number;
  valide_par?: IntegrationPersonne | null;
  valide_le?: string | null;
  archived_at?: string | null;
  archive_par?: IntegrationPersonne | null;
  motif_archivage?: string | null;
  modifiable: boolean;
  transitions: FournisseurStatut[];
  avertissement: string;
}

export interface FournisseurSaisie {
  nom: string;
  description: string | null;
  org_entite_id: string | null;
  responsable_interne: string | null;
  contact_technique: string | null;
  environnement: IntegrationEnvironnement;
  url_base: string | null;
  documentation: string | null;
  notes: string | null;
}

export interface FournisseurFiltres {
  q?: string;
  statut?: string;
  environnement?: string;
  inclure_archives?: boolean;
  tri?: string;
  ordre?: string;
}

export interface MessageAnalyse {
  niveau: 'erreur' | 'avertissement';
  code: string;
  message: string;
  emplacement?: string | null;
}

export interface OperationApercu {
  cle: string;
  methode: string;
  chemin: string;
  operation_id?: string | null;
  nom?: string | null;
  deprecie: boolean;
}

export interface DiffVersion {
  ajoutees: string[];
  supprimees: string[];
  modifiees: string[];
  inchangees: number;
}

export interface ServeurDeclare {
  url: string;
  description?: string | null;
}

export interface MecanismeDeclare {
  nom: string;
  type?: string | null;
  emplacement?: string | null;
  nom_parametre?: string | null;
  schema_http?: string | null;
  format_jeton?: string | null;
  flux?: { flux: string; scopes?: string[] }[];
  description?: string | null;
}

export function mecanismeLabel(m: MecanismeDeclare): string {
  if (m.type === 'apiKey') return `Clé d’API (${m.emplacement ?? '?'} « ${m.nom_parametre ?? '?'} »)`;
  if (m.type === 'http') return `HTTP ${m.schema_http ?? ''}`.trim();
  if (m.type === 'oauth2') return `OAuth 2.0${m.flux?.length ? ' — ' + m.flux.map((f) => f.flux).join(', ') : ''}`;
  if (m.type === 'mutualTLS') return 'TLS mutuel';
  if (m.type === 'openIdConnect') return 'OpenID Connect';
  if (m.type === 'non_precise') return 'Non précisé';
  return m.type ?? 'Autre';
}

export interface AnalyseSpec {
  valide: boolean;
  nom_fichier: string;
  taille: number;
  empreinte: string;
  format?: string | null;
  openapi_version?: string | null;
  titre?: string | null;
  version_api?: string | null;
  serveurs: ServeurDeclare[];
  securite: MecanismeDeclare[];
  nb_operations: number;
  operations: OperationApercu[];
  erreurs: MessageAnalyse[];
  avertissements: MessageAnalyse[];
  version_courante?: number | null;
  deja_importee?: number | null;
  diff?: DiffVersion | null;
  conflits: string[];
  avertissement: string;
}

export interface SpecResume {
  id: string;
  numero: number;
  courante: boolean;
  format: string;
  nom_fichier: string;
  taille: number;
  empreinte: string;
  openapi_version: string;
  titre: string;
  version_api: string;
  nb_operations: number;
  nb_avertissements: number;
  importe_par?: IntegrationPersonne | null;
  created_at: string;
}

export interface SpecListe {
  items: SpecResume[];
  avertissement: string;
}

export interface SpecDetail extends SpecResume {
  serveurs: ServeurDeclare[];
  securite: MecanismeDeclare[];
  description?: string | null;
  avertissements: MessageAnalyse[];
  avertissement: string;
}

export interface OperationResume {
  id: string;
  origine: OperationOrigine;
  statut: 'active' | 'archivee';
  methode: string;
  chemin: string;
  operation_id?: string | null;
  nom?: string | null;
  tags: string[];
  deprecie: boolean;
  spec_numero?: number | null;
  conflit: boolean;
  updated_at: string;
}

export interface OperationListe {
  items: OperationResume[];
  total: number;
  page: number;
  size: number;
  version_courante?: number | null;
  avertissement: string;
}

export interface ParametreDeclare {
  nom: string;
  emplacement: string;
  requis: boolean;
  description?: string | null;
  schema?: unknown;
  deprecie?: boolean;
}

export interface EnteteDeclare {
  nom: string;
  requis: boolean;
  description?: string | null;
}

export interface ContenuDeclare {
  type_contenu: string;
  schema?: unknown;
}

export interface CorpsDeclare {
  requis: boolean;
  description?: string | null;
  contenus: ContenuDeclare[];
}

export interface ReponseDeclaree {
  code: string;
  description?: string | null;
  contenus: ContenuDeclare[];
}

export interface OperationManuelleSaisie {
  nom: string;
  description: string | null;
  methode: MethodeHttp;
  chemin: string;
  parametres: { nom: string; emplacement: 'path' | 'query'; requis: boolean; type: string; description: string | null }[];
  entetes: { nom: string; requis: boolean; description: string | null }[];
  corps_schema: Record<string, unknown> | null;
  reponse_schema: Record<string, unknown> | null;
  mecanisme_auth: MecanismeAuth;
  nom_cle_api: string | null;
  codes_reponse: number[];
  notes: string | null;
}

export interface OperationDetail extends OperationResume {
  description?: string | null;
  parametres: ParametreDeclare[];
  entetes: EnteteDeclare[];
  corps?: CorpsDeclare | null;
  reponses: ReponseDeclaree[];
  authentification: { mecanismes: string[] }[];
  mecanismes: MecanismeDeclare[];
  configuration?: (Partial<OperationManuelleSaisie> & { securite?: MecanismeDeclare[] }) | null;
  notes?: string | null;
  revision: number;
  source: string;
  avertissements: string[];
  elements_declares: string[];
  elements_verifies: string[];
  exemples: IntegrationExemple[];
  cree_par?: IntegrationPersonne | null;
  modifie_par?: IntegrationPersonne | null;
  created_at: string;
}

export interface EvenementFournisseur {
  id: string;
  action: string;
  libelle: string;
  acteur?: IntegrationPersonne | null;
  details: Record<string, unknown>;
  request_id?: string | null;
  created_at: string;
}

export interface HistoriqueFournisseur {
  items: EvenementFournisseur[];
  total: number;
  page: number;
  size: number;
}

export const PERMISSIONS_FOURNISSEURS = {
  view: 'core.admin.integrations.fournisseurs.view',
  manage: 'core.admin.integrations.fournisseurs.manage',
  validate: 'core.admin.integrations.fournisseurs.validate',
} as const;

/** Masquage UI seulement : chaque endpoint revérifie la permission côté serveur. */
export function integrationFournisseursPermissions() {
  const auth = inject(AuthService);
  const has = (code: string) =>
    computed(() => {
      const p = auth.user();
      if (!p) return false;
      const codes = p.permission_codes ?? [];
      return p.is_superuser || codes.includes('*') || codes.includes(code);
    });
  return {
    view: has(PERMISSIONS_FOURNISSEURS.view),
    manage: has(PERMISSIONS_FOURNISSEURS.manage),
    validate: has(PERMISSIONS_FOURNISSEURS.validate),
  };
}

const STATUTS: Record<FournisseurStatut, string> = {
  brouillon: 'Brouillon',
  a_valider: 'À valider',
  valide: 'Validé (configuration)',
  suspendu: 'Suspendu',
  archive: 'Archivé',
};

export interface TransitionFournisseur {
  libelle: string;
  droit: 'manage' | 'validate';
  motif: 'obligatoire' | 'optionnel';
  tone: 'primary' | 'danger';
}

/** Miroir des transitions serveur, pour l'affichage des boutons ; le serveur reste seul juge. */
export const TRANSITIONS_FOURNISSEUR: Partial<Record<FournisseurStatut, TransitionFournisseur>> = {
  brouillon: { libelle: 'Revenir en brouillon', droit: 'manage', motif: 'optionnel', tone: 'primary' },
  a_valider: { libelle: 'Soumettre à validation', droit: 'manage', motif: 'optionnel', tone: 'primary' },
  valide: { libelle: 'Valider la configuration', droit: 'validate', motif: 'optionnel', tone: 'primary' },
  suspendu: { libelle: 'Suspendre', droit: 'validate', motif: 'obligatoire', tone: 'danger' },
};

export function fournisseurStatutLabel(s: string): string {
  return STATUTS[s as FournisseurStatut] ?? s;
}

export function fournisseurStatutTone(s: string): string {
  if (s === 'valide') return 'bea-badge bea-badge--actif';
  if (s === 'brouillon' || s === 'a_valider') return 'bea-badge bea-badge--bientot';
  return 'bea-badge bea-badge--inactif';
}

export const MECANISMES_AUTH: { code: MecanismeAuth; libelle: string }[] = [
  { code: 'non_precise', libelle: 'Non précisé' },
  { code: 'aucun', libelle: 'Aucune authentification' },
  { code: 'api_key_header', libelle: 'Clé d’API (en-tête)' },
  { code: 'api_key_query', libelle: 'Clé d’API (paramètre de requête)' },
  { code: 'http_basic', libelle: 'HTTP Basic' },
  { code: 'http_bearer', libelle: 'HTTP Bearer' },
  { code: 'oauth2_client_credentials', libelle: 'OAuth 2.0 Client Credentials' },
  { code: 'oauth2_autre', libelle: 'OAuth 2.0 (autre flux)' },
  { code: 'mtls', libelle: 'TLS mutuel (mTLS)' },
  { code: 'autre', libelle: 'Autre' },
];

export function fournisseursParams(f: FournisseurFiltres, page: number, size: number): Record<string, string | number | boolean> {
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

/** Forme seulement, comme le serveur : l'URL n'est jamais contactée. */
export function urlBaseValide(control: AbstractControl<string | null>): ValidationErrors | null {
  const v = (control.value ?? '').trim();
  if (!v) return null;
  if (v.length > 300 || /\s/.test(v)) return { url: true };
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    return { url: true };
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return { url: true };
  if (u.username || u.password || v.includes('@')) return { urlIdentifiants: true };
  if (u.search || u.hash || v.includes('?') || v.includes('#')) return { url: true };
  return null;
}

/** Chemin relatif d'opération : commence par /, sans espace, ? ni #. */
export function cheminValide(control: AbstractControl<string | null>): ValidationErrors | null {
  const v = control.value ?? '';
  if (!v) return null;
  if (!v.startsWith('/') || /[\s?#"'`\\$!]/.test(v) || v.includes('//') || /\/\.\.?(\/|$)/.test(v)) return { chemin: true };
  return null;
}

export function placeholders(chemin: string): string[] {
  return Array.from(chemin.matchAll(/\{([A-Za-z0-9_.-]+)\}/g), (m) => m[1]);
}

/** Schéma JSON saisi à la main : objet JSON, sans $ref. Retourne l'objet ou un message d'erreur. */
export function lireSchema(texte: string): { valeur: Record<string, unknown> | null; erreur: string | null } {
  const t = texte.trim();
  if (!t) return { valeur: null, erreur: null };
  let v: unknown;
  try {
    v = JSON.parse(t);
  } catch {
    return { valeur: null, erreur: 'JSON invalide.' };
  }
  if (!v || typeof v !== 'object' || Array.isArray(v)) return { valeur: null, erreur: 'Un objet JSON est attendu.' };
  if (t.length > 64 * 1024) return { valeur: null, erreur: 'Schéma trop volumineux (64 Ko maximum).' };
  if (/"\$ref"\s*:/.test(t)) return { valeur: null, erreur: 'Références $ref non prises en charge.' };
  return { valeur: v as Record<string, unknown>, erreur: null };
}

export function schemaJson(control: AbstractControl<string | null>): ValidationErrors | null {
  const { erreur } = lireSchema(control.value ?? '');
  return erreur ? { schema: erreur } : null;
}

export function codesReponse(texte: string): number[] | null {
  const morceaux = texte.split(/[\s,;]+/).filter(Boolean);
  if (!morceaux.length) return null;
  const codes = morceaux.map((m) => (/^\d{3}$/.test(m) ? Number(m) : NaN));
  if (codes.some((c) => !(c >= 100 && c <= 599))) return null;
  return [...new Set(codes)].sort((a, b) => a - b);
}

export function extensionAcceptee(nom: string): boolean {
  return /\.(json|ya?ml)$/i.test(nom);
}

export const TAILLE_MAX_SPEC = 2 * 1024 * 1024;
