/**
 * Contrat de routage des modules métier BEA DIGITAL.
 *
 * Immobilisations = exception figée (URLs racine historiques).
 * Tout nouveau module (Crédit, RH, …) = arbre préfixé /{moduleCode}/...
 *
 * Ne jamais préfixer l’immo sous /comptabilite/immobilisations/ :
 * ~60 liens absolus + liens de notification backend (navigateByUrl).
 */
export type ModuleRouteStrategy = 'legacy-root' | 'prefixed';

export interface ModuleRouteContract {
  code: string;
  strategy: ModuleRouteStrategy;
  /** Écran d’entrée après Login 2 (doit matcher plateforme_modules.entry_path). */
  entryPath: string;
  /** Retour déconnexion module (Login 1 / espace) — jamais /login. */
  espacePath: string;
  /**
   * Préfixe URL pour strategy=prefixed (ex. /credit).
   * null pour legacy-root (chemins à la racine de l’app).
   */
  urlPrefix: string | null;
}

/** Module historique : shell + paths à la racine (AGENTS.md). */
export const LEGACY_ROOT_MODULE_CODE = 'immobilisations';

/**
 * Segments d’URL réservés au module Immobilisations.
 * Un nouveau module ne doit jamais réutiliser ces segments à la racine.
 */
export const LEGACY_ROOT_PATH_SEGMENTS = [
  'dashboard',
  'immobilisations',
  'inventaire',
  'amortissements',
  'amortissements-agence',
  'recap-amortissement',
  'recap-immobilisations',
  'comptes',
  'archives',
  'pieces-comptables',
  'ecritures',
  'cessions',
  'rebuts',
  'reevaluations',
  'notifications',
  'rapports',
  'utilisateurs',
  'audit',
  'parametres',
] as const;

export const MODULE_ROUTE_CONTRACTS: Readonly<Record<string, ModuleRouteContract>> = {
  immobilisations: {
    code: 'immobilisations',
    strategy: 'legacy-root',
    entryPath: '/dashboard',
    espacePath: '/comptabilite',
    urlPrefix: null,
  },
  // Exemples figés pour les futurs modules (pas encore de shell métier) :
  // credit: { code: 'credit', strategy: 'prefixed', entryPath: '/credit', espacePath: '/credit-espace', urlPrefix: '/credit' },
};

export function getModuleRouteContract(moduleCode: string): ModuleRouteContract | null {
  return MODULE_ROUTE_CONTRACTS[moduleCode] ?? null;
}

export function isLegacyRootModule(moduleCode: string): boolean {
  return moduleCode === LEGACY_ROOT_MODULE_CODE;
}

/** Point d’entrée après Login 2. */
export function resolveModuleEntryPath(moduleCode: string): string {
  const contract = getModuleRouteContract(moduleCode);
  if (contract) {
    return contract.entryPath;
  }
  // Convention par défaut pour un module pas encore déclaré ici.
  return `/${moduleCode}`;
}

/**
 * Retour après déconnexion module (Login 2) → espace métier, jamais Login 1.
 */
export function resolveEspacePathForModule(moduleCode: string | null): string {
  if (!moduleCode) {
    return '/accueil';
  }
  const contract = getModuleRouteContract(moduleCode);
  if (contract) {
    return contract.espacePath;
  }
  return '/accueil';
}

/**
 * Préfixe à utiliser pour enregistrer les routes Angular d’un nouveau module.
 * null = legacy root (immo uniquement).
 */
export function resolveModuleUrlPrefix(moduleCode: string): string | null {
  const contract = getModuleRouteContract(moduleCode);
  if (contract) {
    return contract.urlPrefix;
  }
  return `/${moduleCode}`;
}
