/** Types catalogue plateforme + libellés d’écrans immo (fil d’Ariane).
 *
 * Source de vérité des espaces / modules = API `/plateforme/espaces`
 * (seed backend `plateforme_catalogue.py`). Pas de doublon front.
 */

export type StatutEspace = 'actif' | 'bientot';

/** Statuts module renvoyés par l’API (catalogue + ops CORE ADMIN). */
export type StatutModule =
  | 'actif'
  | 'bientot'
  | 'inactif'
  | 'developpement'
  | 'mise_a_jour'
  | 'maintenance'
  | 'suspendu'
  | 'bloque'
  | 'archive';

export interface ModuleMetier {
  id: string;
  titre: string;
  description: string;
  route: string | null;
  statut: StatutModule | StatutEspace;
  accessible?: boolean;
  entry_path?: string | null;
  status_message?: string;
  version?: string | null;
}

export interface EspaceMetier {
  id: string;
  titre: string;
  description: string;
  route: string | null;
  statut: StatutEspace | string;
  modules: ModuleMetier[];
  accessible?: boolean;
}

export interface PageModuleImmo {
  prefix: string;
  label: string;
}

/**
 * Libellés d’écran du module immo (chemins d’URL figés — contrat legacy-root).
 * Hors catalogue API : pure UI fil d’Ariane.
 */
export const PAGES_MODULE_IMMO: PageModuleImmo[] = [
  { prefix: '/dashboard', label: 'Tableau de bord' },
  { prefix: '/notifications', label: 'Notifications' },
  { prefix: '/immobilisations', label: 'Immobilisations' },
  { prefix: '/inventaire', label: 'Inventaire' },
  { prefix: '/amortissements/calculer', label: 'Calcul des amortissements' },
  { prefix: '/amortissements', label: 'Amortissements' },
  { prefix: '/recap-immobilisations', label: 'Récap. immobilisations' },
  { prefix: '/recap-amortissement', label: 'Récap. amortissement' },
  { prefix: '/amortissements-agence', label: 'Amortissements par agence' },
  { prefix: '/comptes/soldes-148-68', label: 'Soldes 142 / 148 / 68' },
  { prefix: '/comptes', label: 'Comptes' },
  { prefix: '/archives', label: 'Archives' },
  { prefix: '/pieces-comptables', label: 'Pièces comptables' },
  { prefix: '/ecritures', label: 'Écritures' },
  { prefix: '/cessions', label: 'Cessions' },
  { prefix: '/rebuts', label: 'Rebuts' },
  { prefix: '/reevaluations', label: 'Réévaluations' },
  { prefix: '/rapports', label: 'Rapports' },
  { prefix: '/utilisateurs', label: 'Utilisateurs' },
  { prefix: '/audit', label: 'Audit' },
  { prefix: '/parametres', label: 'Paramètres' },
];

export function labelPageModuleImmo(url: string): string | null {
  const path = url.split('?')[0];
  const matches = PAGES_MODULE_IMMO.filter((p) => path === p.prefix || path.startsWith(`${p.prefix}/`));
  if (matches.length === 0) {
    return null;
  }
  matches.sort((a, b) => b.prefix.length - a.prefix.length);
  return matches[0].label;
}
