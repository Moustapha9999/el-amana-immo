export interface CoreAdminNavItem {
  label: string;
  icon: string;
  path?: string;
  soon?: boolean;
}

export interface CoreAdminNavGroup {
  label?: string;
  items: CoreAdminNavItem[];
}

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
      { label: 'Départements', path: '/admin/departments', icon: 'domain' },
      { label: 'Modules', path: '/admin/modules', icon: 'apps' },
    ],
  },
  {
    label: 'Supervision',
    items: [
      { label: 'Vue générale', path: '/admin/supervision', icon: 'monitor' },
      { label: 'Journal d’audit', path: '/admin/audit', icon: 'policy' },
      { label: 'Activité', path: '/admin/activity', icon: 'history' },
      { label: 'Alertes', path: '/admin/alerts', icon: 'warning' },
    ],
  },
  {
    label: 'Continuité',
    items: [
      { label: 'Sauvegardes', path: '/admin/backups', icon: 'backup' },
      { label: 'Recovery', path: '/admin/recovery', icon: 'restore' },
      { label: 'Maintenance', path: '/admin/maintenance', icon: 'build' },
      { label: 'État des modules', path: '/admin/module-states', icon: 'tune' },
      { label: 'Versions', path: '/admin/versions', icon: 'history' },
    ],
  },
  {
    label: 'Services',
    items: [
      { label: 'Centre notifications', path: '/admin/notifications', icon: 'notifications' },
      { label: 'GED', path: '/admin/ged', icon: 'folder' },
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
