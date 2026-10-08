export interface CoreAdminNavItem {
  label: string;
  icon: string;
  path?: string;
  soon?: boolean;
  exact?: boolean;
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
