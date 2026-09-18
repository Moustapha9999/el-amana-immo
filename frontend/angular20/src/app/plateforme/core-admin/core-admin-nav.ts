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
    label: 'Organisation',
    items: [
      { label: 'Départements', path: '/admin/departments', icon: 'domain' },
      { label: 'Modules', path: '/admin/modules', icon: 'apps' },
      { label: 'Utilisateurs', path: '/admin/users', icon: 'group' },
    ],
  },
  {
    label: 'Accès',
    items: [
      { label: 'Rôles', path: '/admin/roles', icon: 'badge' },
      { label: 'Permissions', path: '/admin/permissions', icon: 'vpn_key' },
      { label: 'Matrice', path: '/admin/matrix', icon: 'grid_view' },
      { label: 'Sessions', path: '/admin/sessions', icon: 'devices' },
    ],
  },
  {
    label: 'Supervision',
    items: [
      { label: 'Audit', path: '/admin/audit', icon: 'policy' },
      { label: 'Activité', path: '/admin/activity', icon: 'history' },
      { label: 'Alertes', path: '/admin/alerts', icon: 'warning' },
    ],
  },
  {
    label: 'Services',
    items: [
      { label: 'Notifications', path: '/admin/notifications', icon: 'notifications' },
      { label: 'GED', path: '/admin/ged', icon: 'folder' },
    ],
  },
  {
    label: 'Configuration',
    items: [
      { label: 'Général', path: '/admin/general', icon: 'tune' },
      { label: 'Sécurité', path: '/admin/security', icon: 'security' },
      { label: 'Maintenance', path: '/admin/maintenance', icon: 'build' },
    ],
  },
];
