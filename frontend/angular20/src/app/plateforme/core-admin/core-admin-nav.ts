export interface CoreAdminNavItem {
  label: string;
  path?: string;
  soon?: boolean;
}

export interface CoreAdminNavGroup {
  label?: string;
  items: CoreAdminNavItem[];
}

export const CORE_ADMIN_NAV: CoreAdminNavGroup[] = [
  {
    items: [{ label: 'Dashboard', path: '/admin/dashboard' }],
  },
  {
    label: 'Organisation',
    items: [
      { label: 'Départements', soon: true },
      { label: 'Modules', soon: true },
      { label: 'Utilisateurs', path: '/admin/users' },
    ],
  },
  {
    label: 'Accès',
    items: [
      { label: 'Rôles', soon: true },
      { label: 'Permissions', soon: true },
      { label: 'Matrice', soon: true },
      { label: 'Sessions', soon: true },
    ],
  },
  {
    label: 'Supervision',
    items: [
      { label: 'Audit', soon: true },
      { label: 'Activité', soon: true },
      { label: 'Alertes', soon: true },
    ],
  },
  {
    label: 'Services',
    items: [
      { label: 'Notifications', soon: true },
      { label: 'GED', soon: true },
    ],
  },
  {
    label: 'Configuration',
    items: [
      { label: 'Général', soon: true },
      { label: 'Sécurité', soon: true },
      { label: 'Maintenance', soon: true },
    ],
  },
];
