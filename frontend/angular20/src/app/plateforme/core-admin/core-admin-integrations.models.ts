import { HttpErrorResponse } from '@angular/common/http';

export type IntegrationDisponibilite = 'documentee' | 'restreinte' | 'exclue';
export type IntegrationAuth = 'login1' | 'login2' | 'login1_ou_login2' | 'indeterminee' | 'aucune_detectee';
export type IntegrationPermissionStatut = 'identifiee' | 'non_determinee' | 'non_verifiee';
export type IntegrationSchemaStatut = 'explicite' | 'generique' | 'absent';

export interface IntegrationParametre {
  nom: string;
  emplacement: string;
  requis: boolean;
  type: string;
  description?: string | null;
  defaut?: string | number | boolean | null;
  valeurs: string[];
}

export interface IntegrationChamp {
  nom: string;
  type: string;
  requis: boolean;
  description?: string | null;
}

export interface IntegrationCorps {
  type_contenu: string;
  requis: boolean;
  schema_nom?: string | null;
  champs: IntegrationChamp[];
}

export interface IntegrationReponse {
  code: string;
  description?: string | null;
  schema_nom?: string | null;
  champs: IntegrationChamp[];
}

export interface IntegrationOperationResume {
  operation_id: string;
  nom: string;
  methode: string;
  chemin: string;
  module: string;
  module_code?: string | null;
  module_etat: string;
  authentification: IntegrationAuth;
  permissions: string[];
  exigence_permissions?: string | null;
  permission_statut: IntegrationPermissionStatut;
  schema_reponse_statut: IntegrationSchemaStatut;
  disponibilite: IntegrationDisponibilite;
  categorie_exclusion?: string | null;
  motifs: string[];
  exemples_disponibles: boolean;
  console: boolean;
  console_motif?: string | null;
}

export interface IntegrationOperationFiche extends IntegrationOperationResume {
  resume?: string | null;
  description?: string | null;
  dans_openapi: boolean;
  dependances_non_analysees: string[];
  parametres: IntegrationParametre[];
  corps?: IntegrationCorps | null;
  reponses: IntegrationReponse[];
  avertissement: string;
}

export interface IntegrationCatalogueKpis {
  total: number;
  documentees: number;
  restreintes: number;
  exclues: number;
  console: number;
  par_methode: Record<string, number>;
  par_authentification: Record<string, number>;
  par_permission_statut: Record<string, number>;
  par_schema_reponse: Record<string, number>;
}

export interface IntegrationCatalogueFiltres {
  modules: string[];
  methodes: string[];
  authentifications: string[];
}

export interface IntegrationCataloguePage {
  items: IntegrationOperationResume[];
  total: number;
  page: number;
  size: number;
  kpis: IntegrationCatalogueKpis;
  filtres: IntegrationCatalogueFiltres;
  avertissement: string;
}

export interface IntegrationExemple {
  langage: 'curl' | 'python' | 'typescript';
  libelle: string;
  code: string;
}

export interface IntegrationExemples {
  operation_id: string;
  disponible: boolean;
  motif?: string | null;
  authentification: IntegrationAuth;
  prerequis: string[];
  exemples: IntegrationExemple[];
}

export interface IntegrationConsoleLimites {
  methodes: string[];
  taille_max_octets: number;
  delai_max_secondes: number;
}

export interface IntegrationConsoleOperation {
  operation_id: string;
  nom: string;
  methode: string;
  chemin: string;
  module: string;
  permissions: string[];
  justification: string;
  parametres: IntegrationParametre[];
}

export interface IntegrationConsoleOperations {
  items: IntegrationConsoleOperation[];
  environnement: string;
  limites: IntegrationConsoleLimites;
  avertissement: string;
}

export type IntegrationConsoleValeur = string | number | boolean;

export interface IntegrationConsoleRequete {
  operation_id: string;
  parametres_chemin: Record<string, string>;
  parametres_requete: Record<string, IntegrationConsoleValeur>;
}

export interface IntegrationConsoleResultat {
  operation_id: string;
  methode: string;
  chemin: string;
  statut_http: number;
  duree_ms: number;
  taille_octets: number;
  tronquee: boolean;
  corps?: unknown;
  champs_masques: number;
  request_id?: string | null;
  environnement: string;
  message?: string | null;
}

export interface IntegrationCatalogueFiltreValeurs {
  q?: string;
  module?: string;
  methode?: string;
  authentification?: string;
  permission_statut?: string;
  schema?: string;
  permission?: string;
  disponibilite?: string;
  console?: boolean | null;
}

export const PERMISSION_STUDIO = 'core.admin.integrations.view';

const AUTH_LABELS: Record<string, string> = {
  login1: 'Login 1 (plateforme)',
  login2: 'Login 2 (module)',
  login1_ou_login2: 'Session Login 1 ou Login 2',
  indeterminee: 'Authentification indéterminée',
  aucune_detectee: 'Aucune authentification détectée',
};

const PERMISSION_LABELS: Record<string, string> = {
  identifiee: 'Permission identifiée (dépendances)',
  non_determinee: 'Permission non déterminée',
  non_verifiee: 'Accès non vérifié',
};

const SCHEMA_LABELS: Record<string, string> = {
  explicite: 'Schéma explicite',
  generique: 'Schéma générique',
  absent: 'Schéma absent',
};

const DISPO_LABELS: Record<string, string> = {
  documentee: 'Documentée',
  restreinte: 'Restreinte',
  exclue: 'Exclue',
};

export function authLabel(code: string): string {
  return AUTH_LABELS[code] ?? code;
}

export function permissionStatutLabel(code: string): string {
  return PERMISSION_LABELS[code] ?? code;
}

export function schemaStatutLabel(code: string): string {
  return SCHEMA_LABELS[code] ?? code;
}

export function disponibiliteLabel(code: string): string {
  return DISPO_LABELS[code] ?? code;
}

export function disponibiliteTone(code: string): string {
  if (code === 'documentee') return 'bea-badge--actif';
  if (code === 'restreinte') return 'bea-badge--bientot';
  return 'bea-badge--inactif';
}

export function moduleEtatLabel(etat: string): string {
  if (etat === 'desactive') return 'Module désactivé';
  if (etat === 'introuvable') return 'Hors catalogue modules';
  if (etat === 'non_applicable') return 'Plateforme (hors module)';
  return etat;
}

/** Paramètres HTTP du catalogue : valeurs vides ignorées. */
export function catalogueParams(
  filtres: IntegrationCatalogueFiltreValeurs,
  page: number,
  size: number,
): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = { page, size };
  for (const [cle, valeur] of Object.entries(filtres)) {
    if (valeur === null || valeur === undefined) continue;
    if (typeof valeur === 'string') {
      const v = valeur.trim();
      if (v) params[cle] = v;
    } else {
      params[cle] = valeur;
    }
  }
  return params;
}

/** Valeurs saisies dans la console → corps de requête ; seules les valeurs non vides partent. */
export function consoleRequete(
  op: IntegrationConsoleOperation,
  valeurs: Partial<Record<string, string>>,
): IntegrationConsoleRequete {
  const chemin: Record<string, string> = {};
  const requete: Record<string, IntegrationConsoleValeur> = {};
  for (const p of op.parametres) {
    const brut = (valeurs[p.nom] ?? '').trim();
    if (!brut) continue;
    if (p.emplacement === 'path') {
      chemin[p.nom] = brut;
    } else if (p.emplacement === 'query') {
      requete[p.nom] = brut;
    }
  }
  return { operation_id: op.operation_id, parametres_chemin: chemin, parametres_requete: requete };
}

export function formatOctets(n: number): string {
  if (n < 1024) return `${n} o`;
  return `${(n / 1024).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Kio`;
}

export interface IntegrationErreur {
  statut: number;
  message: string;
  accesRefuse: boolean;
}

export function integrationErreur(err: unknown, fallback: string): IntegrationErreur {
  if (!(err instanceof HttpErrorResponse)) {
    return { statut: 0, message: fallback, accesRefuse: false };
  }
  const detail = err.error?.detail;
  let message = fallback;
  if (typeof detail === 'string' && detail.trim()) {
    message = detail;
  } else if (detail && typeof detail === 'object' && typeof (detail as { message?: string }).message === 'string') {
    message = (detail as { message: string }).message;
  } else if (typeof err.error?.message === 'string' && err.error.message.trim()) {
    message = err.error.message;
  }
  const code = String(err.error?.code ?? (detail as { code?: string } | null)?.code ?? '');
  const accesRefuse = err.status === 401 || (err.status === 403 && !code.startsWith('CONSOLE_'));
  return { statut: err.status, message, accesRefuse };
}
