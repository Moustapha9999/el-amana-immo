export interface CoreAdminNavItem {
  label: string;
  icon: string;
  path?: string;
  soon?: boolean;
  exact?: boolean;
  /** Entrée masquée sans cette permission (confort d'affichage : le serveur revérifie). */
  permission?: string;
  /** Entrée masquée si aucune de ces permissions n'est détenue. */
  anyPermission?: readonly string[];
}

export interface CoreAdminNavGroup {
  label?: string;
  items: CoreAdminNavItem[];
}

/** Groupes et entrées visibles pour ces permissions ; une entrée sans `permission` ni `anyPermission` reste toujours visible. */
export function coreAdminNavVisible(
  nav: CoreAdminNavGroup[],
  codes: readonly string[],
  superuser: boolean,
): CoreAdminNavGroup[] {
  const tout = superuser || codes.includes('*');
  const visible = (i: CoreAdminNavItem) =>
    tout ||
    ((!i.permission || codes.includes(i.permission)) && (!i.anyPermission || i.anyPermission.some((p) => codes.includes(p))));
  return nav
    .map((group) => ({ ...group, items: group.items.filter(visible) }))
    .filter((group) => group.items.length > 0);
}

const STUDIO_ENTREE = [
  'core.admin.integrations.view',
  'core.admin.integrations.clients.view',
  'core.admin.integrations.fournisseurs.view',
  'core.admin.integrations.destinations.view',
  'core.admin.integrations.tests.view',
  'core.admin.integrations.tests.execute',
  'core.admin.integrations.supervision.view',
] as const;

export const CORE_ADMIN_NAV: CoreAdminNavGroup[] = [
  {
    items: [{ label: 'Dashboard', path: '/admin/dashboard', icon: 'dashboard' }],
  },
  {
    label: 'Comptes & accès',
    items: [
      { label: 'Utilisateurs', path: '/admin/users', icon: 'group' },
      { label: 'Rôles', path: '/admin/roles', icon: 'badge' },
      { label: 'Permissions', path: '/admin/permissions', icon: 'vpn_key' },
      { label: 'Matrice', path: '/admin/matrix', icon: 'grid_view' },
      { label: 'Sessions', path: '/admin/sessions', icon: 'devices' },
    ],
  },
  {
    label: 'Organisation',
    items: [
      { label: 'Organigramme BEA', path: '/admin/organigramme', icon: 'account_tree' },
      { label: 'Départements', path: '/admin/departments', icon: 'domain' },
      { label: 'Modules', path: '/admin/modules', icon: 'apps' },
      { label: 'Demandes', path: '/admin/demandes', icon: 'assignment' },
    ],
  },
  {
    label: 'Supervision',
    items: [
      { label: 'Vue générale', path: '/admin/supervision', icon: 'monitor' },
      { label: 'Journal d’audit', path: '/admin/audit', icon: 'policy' },
      { label: 'Erreurs API', path: '/admin/erreurs', icon: 'report' },
      { label: 'Activité', path: '/admin/activity', icon: 'history' },
      { label: 'Alertes', path: '/admin/alerts', icon: 'warning' },
    ],
  },
  {
    label: 'CORE QUERY',
    items: [
      { label: 'Assistant', path: '/admin/core-query', icon: 'manage_search', exact: true },
      { label: 'Query Builder', path: '/admin/core-query/builder', icon: 'account_tree' },
      { label: 'SQL', path: '/admin/core-query/sql', icon: 'code' },
      { label: 'Requêtes favorites', path: '/admin/core-query/favoris', icon: 'star' },
      { label: 'Historique', path: '/admin/core-query/historique', icon: 'history' },
    ],
  },
  {
    label: 'Studio d’intégration API',
    items: [
      { label: 'Vue d’ensemble', path: '/admin/integrations', icon: 'hub', exact: true, anyPermission: STUDIO_ENTREE },
      { label: 'Catalogue API', path: '/admin/integrations/catalogue', icon: 'menu_book', permission: 'core.admin.integrations.view' },
      { label: 'Console (lecture)', path: '/admin/integrations/console', icon: 'terminal', permission: 'core.admin.integrations.view' },
      {
        label: 'Applications clientes',
        path: '/admin/integrations/clients',
        icon: 'apps',
        permission: 'core.admin.integrations.clients.view',
      },
      {
        label: 'Fournisseurs externes',
        path: '/admin/integrations/fournisseurs',
        icon: 'cloud',
        permission: 'core.admin.integrations.fournisseurs.view',
      },
      {
        label: 'Destinations TEST',
        path: '/admin/integrations/destinations',
        icon: 'public',
        permission: 'core.admin.integrations.destinations.view',
      },
      {
        label: 'Tests d’intégration',
        path: '/admin/integrations/tests',
        icon: 'science',
        anyPermission: ['core.admin.integrations.tests.execute', 'core.admin.integrations.tests.view'],
      },
      {
        label: 'Historique des exécutions',
        path: '/admin/integrations/executions',
        icon: 'history',
        permission: 'core.admin.integrations.tests.view',
      },
      {
        label: 'Supervision',
        path: '/admin/integrations/supervision',
        icon: 'timeline',
        permission: 'core.admin.integrations.supervision.view',
      },
      {
        label: 'Alertes',
        path: '/admin/integrations/alertes',
        icon: 'notifications_active',
        permission: 'core.admin.integrations.supervision.view',
      },
    ],
  },
  {
    label: 'Sauvegardes & Recovery',
    items: [
      { label: 'Vue générale', path: '/admin/sauvegardes', icon: 'insights', exact: true },
      { label: 'Sauvegarde', path: '/admin/sauvegardes/sauvegarde', icon: 'backup' },
      { label: 'Recovery', path: '/admin/sauvegardes/recovery', icon: 'settings_backup_restore' },
      { label: 'Historique', path: '/admin/sauvegardes/historique', icon: 'manage_history' },
    ],
  },
  {
    label: 'Continuité',
    items: [
      { label: 'Maintenance', path: '/admin/maintenance', icon: 'build' },
      { label: 'État des modules', path: '/admin/module-states', icon: 'tune' },
      { label: 'Versions', path: '/admin/versions', icon: 'history' },
    ],
  },
  {
    label: 'Documentaire / GED',
    items: [
      { label: 'Dashboard GED', path: '/admin/ged', icon: 'dashboard' },
      { label: 'Documents', path: '/admin/ged/documents', icon: 'description' },
      { label: 'Dossiers', path: '/admin/ged/dossiers', icon: 'folder' },
      { label: 'OCR', path: '/admin/ged/ocr', icon: 'document_scanner' },
      { label: 'Recherche', path: '/admin/ged/recherche', icon: 'search' },
      { label: 'Stockage', path: '/admin/ged/stockage', icon: 'hard_drive' },
      { label: 'Documents manquants', path: '/admin/ged/manquants', icon: 'folder_off' },
      { label: 'Corbeille', path: '/admin/ged/corbeille', icon: 'delete' },
      { label: 'Audit documentaire', path: '/admin/ged/audit', icon: 'policy' },
      { label: 'Paramètres GED', path: '/admin/ged/parametres', icon: 'tune' },
    ],
  },
  {
    label: 'Services',
    items: [
      { label: 'Centre notifications', path: '/admin/notifications', icon: 'notifications' },
    ],
  },
  {
    label: 'Paramètres',
    items: [
      { label: 'Général', path: '/admin/general', icon: 'tune' },
      { label: 'Sécurité', path: '/admin/security', icon: 'security' },
    ],
  },
];
