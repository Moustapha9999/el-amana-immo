export type StatutEspace = 'actif' | 'bientot';

export interface ModuleMetier {
  id: string;
  titre: string;
  description: string;
  route: string | null;
  statut: StatutEspace;
}

export interface EspaceMetier {
  id: string;
  titre: string;
  description: string;
  route: string | null;
  statut: StatutEspace;
  modules: ModuleMetier[];
}

/** Catalogue des espaces BEA DIGITAL. Un seul espace actif : Comptabilité. */
export const ESPACES_METIERS: EspaceMetier[] = [
  {
    id: 'comptabilite',
    titre: 'Comptabilité',
    description:
      'Immobilisations, amortissements, pièces et contrôles autour d’ORION — sans remplacer le core banking.',
    route: '/comptabilite',
    statut: 'actif',
    modules: [
      {
        id: 'immobilisations',
        titre: 'Immobilisations & Amortissements',
        description:
          'Parc, dotations, cessions, rebuts, réévaluations, inventaire, écritures, archives et rapports.',
        route: '/dashboard',
        statut: 'actif',
      },
      {
        id: 'rapprochements',
        titre: 'Rapprochements',
        description: 'Rapprochements Excel / ORION et contrôles de cohérence.',
        route: null,
        statut: 'bientot',
      },
      {
        id: 'controles',
        titre: 'Contrôles comptables',
        description: 'Contrôles périodiques et anomalies.',
        route: null,
        statut: 'bientot',
      },
      {
        id: 'cloture',
        titre: 'Clôture comptable',
        description: 'Préparation et suivi de clôture.',
        route: null,
        statut: 'bientot',
      },
      {
        id: 'reporting-compta',
        titre: 'Reporting comptable',
        description: 'Tableaux de bord et exports transverses.',
        route: null,
        statut: 'bientot',
      },
    ],
  },
  {
    id: 'credit',
    titre: 'Crédit',
    description: 'Processus crédit autour d’ORION (dossiers, contrôles, workflows).',
    route: null,
    statut: 'bientot',
    modules: [],
  },
  {
    id: 'rh',
    titre: 'RH',
    description: 'Processus ressources humaines internes.',
    route: null,
    statut: 'bientot',
    modules: [],
  },
  {
    id: 'informatique',
    titre: 'Informatique',
    description: 'Demandes, suivi et outils internes DSI.',
    route: null,
    statut: 'bientot',
    modules: [],
  },
  {
    id: 'achats',
    titre: 'Achats',
    description: 'Demandes d’achat, validations et suivi documentaire.',
    route: null,
    statut: 'bientot',
    modules: [],
  },
];

export const ESPACE_COMPTABILITE = ESPACES_METIERS.find((e) => e.id === 'comptabilite')!;

export interface PageModuleImmo {
  prefix: string;
  label: string;
}

/** Libellés d’écran du module immo (chemins d’URL inchangés). */
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
