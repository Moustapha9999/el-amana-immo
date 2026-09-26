export interface ShellNavItem {
  label: string;
  path: string;
  icon: string;
  section: string;
  /** Si true, routerLinkActive exact (écrans « racine » du module). */
  exact?: boolean;
  /** Au moins une de ces permissions (superuser / * = tout). Vide = visible si module accessible. */
  permissions?: string[];
  /** Query params optionnels (filtres Archives MG, etc.). */
  queryParams?: Record<string, string>;
}

export const SHELL_NAV: ShellNavItem[] = [
  { section: 'Pilotage', label: 'Dashboard', path: '/dashboard', icon: 'dashboard', exact: true },
  { section: 'Pilotage', label: 'Notifications', path: '/notifications', icon: 'notifications' },
  { section: 'Patrimoine', label: 'Immobilisations', path: '/immobilisations', icon: 'apartment' },
  { section: 'Patrimoine', label: 'Inventaire', path: '/inventaire', icon: 'qr_code_scanner' },
  { section: 'Patrimoine', label: 'Amortissements', path: '/amortissements', icon: 'timeline' },
  {
    section: 'Patrimoine',
    label: 'Récap. immobilisations',
    path: '/recap-immobilisations',
    icon: 'summarize',
  },
  {
    section: 'Patrimoine',
    label: 'Récap. amortissement',
    path: '/recap-amortissement',
    icon: 'table_chart',
  },
  {
    section: 'Patrimoine',
    label: 'Soldes 142 / 148 / 68',
    path: '/comptes/soldes-148-68',
    icon: 'account_balance',
  },
  {
    section: 'Patrimoine',
    label: 'Amort. par agence',
    path: '/amortissements-agence',
    icon: 'domain',
  },
  { section: 'Patrimoine', label: 'Comptes', path: '/comptes', icon: 'account_balance_wallet' },
  { section: 'Patrimoine', label: 'Archives', path: '/archives', icon: 'inventory_2' },
  {
    section: 'Comptabilité',
    label: 'Pièces comptables',
    path: '/pieces-comptables',
    icon: 'document_scanner',
  },
  { section: 'Comptabilité', label: 'Écritures', path: '/ecritures', icon: 'receipt_long' },
  { section: 'Comptabilité', label: 'Cessions', path: '/cessions', icon: 'swap_horiz' },
  { section: 'Comptabilité', label: 'Rebuts', path: '/rebuts', icon: 'delete_outline' },
  { section: 'Comptabilité', label: 'Réévaluations', path: '/reevaluations', icon: 'trending_up' },
  { section: 'Administration', label: 'Rapports', path: '/rapports', icon: 'summarize' },
  { section: 'Administration', label: 'Utilisateurs', path: '/utilisateurs', icon: 'group' },
  { section: 'Administration', label: 'Audit', path: '/audit', icon: 'policy' },
  { section: 'Administration', label: 'Paramètres', path: '/parametres', icon: 'tune' },
];

/** Navigation shell métier par code module (même chrome que Immobilisations). */
export const MODULE_SHELL_NAV: Readonly<Record<string, ShellNavItem[]>> = {
  immobilisations: SHELL_NAV,
  'stock-fournitures': [
    {
      section: 'Stock & Fournitures',
      label: 'Dashboard',
      path: '/stock-fournitures/dashboard',
      icon: 'dashboard',
      exact: true,
      permissions: ['mg.stock.view'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Articles & Référentiel',
      path: '/stock-fournitures/articles',
      icon: 'inventory_2',
      permissions: ['mg.stock.view'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Stock',
      path: '/stock-fournitures/stock',
      icon: 'warehouse',
      permissions: ['mg.stock.view'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Entrées',
      path: '/stock-fournitures/entrees',
      icon: 'south',
      permissions: ['mg.stock.view', 'mg.stock.entry'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Sorties',
      path: '/stock-fournitures/sorties',
      icon: 'north',
      permissions: ['mg.stock.view', 'mg.stock.exit'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Demandes de fournitures',
      path: '/stock-fournitures/demandes',
      icon: 'assignment',
      permissions: ['mg.stock.view', 'mg.stock.create', 'mg.stock.approve'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Inventaire',
      path: '/stock-fournitures/inventaires',
      icon: 'fact_check',
      permissions: ['mg.stock.view', 'mg.stock.inventory'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Journal des mouvements',
      path: '/stock-fournitures/journal',
      icon: 'receipt_long',
      permissions: ['mg.stock.view'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Alertes stock',
      path: '/stock-fournitures/alertes',
      icon: 'warning',
      permissions: ['mg.stock.view'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Rapports',
      path: '/stock-fournitures/rapports',
      icon: 'assessment',
      permissions: ['mg.stock.view', 'mg.stock.export'],
    },
    {
      section: 'Stock & Fournitures',
      label: 'Paramètres',
      path: '/stock-fournitures/parametres',
      icon: 'settings',
      permissions: ['mg.stock.create'],
    },
  ],
  'achats-appro': [
    {
      section: 'Pilotage',
      label: 'Dashboard',
      path: '/achats-appro/dashboard',
      icon: 'dashboard',
      exact: true,
      permissions: ['mg.purchase.view'],
    },
    {
      section: 'Pilotage',
      label: 'Alertes',
      path: '/achats-appro/alertes',
      icon: 'notification_important',
      permissions: ['mg.purchase.view'],
    },
    {
      section: 'Amont',
      label: 'Demandes d’achat',
      path: '/achats-appro/demandes',
      icon: 'assignment',
      permissions: ['mg.purchase.view', 'mg.purchase.demande'],
    },
    {
      section: 'Amont',
      label: 'Fournisseurs',
      path: '/achats-appro/fournisseurs',
      icon: 'store',
      permissions: ['mg.purchase.view'],
    },
    {
      section: 'Commande',
      label: 'Bons de commande',
      path: '/achats-appro/bons',
      icon: 'request_quote',
      permissions: ['mg.purchase.view'],
    },
    {
      section: 'Commande',
      label: 'Nouveau BC',
      path: '/achats-appro/nouveau',
      icon: 'add_circle',
      permissions: ['mg.purchase.create'],
    },
    {
      section: 'Aval',
      label: 'Réceptions',
      path: '/achats-appro/receptions',
      icon: 'inventory',
      permissions: ['mg.purchase.view', 'mg.purchase.receive'],
    },
    {
      section: 'Aval',
      label: 'Factures',
      path: '/achats-appro/factures',
      icon: 'receipt_long',
      permissions: ['mg.purchase.view', 'mg.purchase.invoice'],
    },
    {
      section: 'Aval',
      label: 'Paiements',
      path: '/achats-appro/paiements',
      icon: 'payments',
      permissions: ['mg.purchase.view', 'mg.purchase.pay'],
    },
    {
      section: 'Administration',
      label: 'Rapports',
      path: '/achats-appro/rapports',
      icon: 'assessment',
      permissions: ['mg.purchase.view', 'mg.purchase.export'],
    },
    {
      section: 'Administration',
      label: 'Paramètres',
      path: '/achats-appro/parametres',
      icon: 'settings',
      permissions: ['mg.purchase.view'],
    },
  ],
  'notes-frais': [
    {
      section: 'Notes de frais',
      label: 'Dashboard',
      path: '/notes-frais/dashboard',
      icon: 'dashboard',
      exact: true,
      permissions: ['mg.notes.view'],
    },
    {
      section: 'Notes de frais',
      label: 'Registre',
      path: '/notes-frais/notes',
      icon: 'receipt_long',
      exact: true,
      permissions: ['mg.notes.view'],
    },
    {
      section: 'Notes de frais',
      label: 'Nouvelle note',
      path: '/notes-frais/nouvelle',
      icon: 'add_circle',
      permissions: ['mg.notes.create'],
    },
    {
      section: 'Notes de frais',
      label: 'Rapports',
      path: '/notes-frais/rapports',
      icon: 'assessment',
      permissions: ['mg.notes.export'],
    },
    {
      section: 'Notes de frais',
      label: 'Paramètres',
      path: '/notes-frais/parametres',
      icon: 'settings',
      permissions: ['mg.notes.settings'],
    },
  ],
  'contrats-echeances': [
    {
      section: 'Pilotage',
      label: 'Dashboard',
      path: '/contrats-echeances/dashboard',
      icon: 'dashboard',
      exact: true,
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Pilotage',
      label: 'Alertes',
      path: '/contrats-echeances/alertes',
      icon: 'notification_important',
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Gestion',
      label: 'Contrats',
      path: '/contrats-echeances/liste',
      icon: 'description',
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Gestion',
      label: 'Nouveau contrat',
      path: '/contrats-echeances/nouveau',
      icon: 'add_circle',
      permissions: ['mg.contrats.create'],
    },
    {
      section: 'Gestion',
      label: 'Échéances',
      path: '/contrats-echeances/echeances',
      icon: 'event',
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Gestion',
      label: 'Paiements',
      path: '/contrats-echeances/paiements',
      icon: 'payments',
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Gestion',
      label: 'Renouvellements',
      path: '/contrats-echeances/renouvellements',
      icon: 'autorenew',
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Administration',
      label: 'Rapports',
      path: '/contrats-echeances/rapports',
      icon: 'assessment',
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Administration',
      label: 'Paramètres',
      path: '/contrats-echeances/parametres',
      icon: 'settings',
      permissions: ['mg.contrats.manage'],
    },
  ],
  'archives-mg': [
    {
      section: 'Pilotage',
      label: 'Dashboard',
      path: '/archives-mg/dashboard',
      icon: 'dashboard',
      exact: true,
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Pilotage',
      label: 'Recherche globale',
      path: '/archives-mg/recherche',
      icon: 'search',
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Pilotage',
      label: 'Archive Générale',
      path: '/modules/archives-generales/acces',
      icon: 'account_balance',
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Documents',
      label: 'Tous les documents',
      path: '/archives-mg/documents',
      icon: 'folder_open',
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Documents',
      label: 'Achats',
      path: '/archives-mg/documents',
      icon: 'shopping_cart',
      queryParams: { module_code: 'achats-appro' },
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Documents',
      label: 'Stock & Fournitures',
      path: '/archives-mg/documents',
      icon: 'inventory_2',
      queryParams: { module_code: 'stock-fournitures' },
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Documents',
      label: 'Notes de Frais',
      path: '/archives-mg/documents',
      icon: 'receipt_long',
      queryParams: { module_code: 'notes-frais' },
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Documents',
      label: 'Contrats & Échéances',
      path: '/archives-mg/documents',
      icon: 'description',
      queryParams: { module_code: 'contrats-echeances' },
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Suivi',
      label: 'Documents récents',
      path: '/archives-mg/documents',
      icon: 'history',
      queryParams: { recent_days: '14' },
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Suivi',
      label: 'Mes documents',
      path: '/archives-mg/documents',
      icon: 'person',
      queryParams: { mine: '1' },
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Suivi',
      label: 'Documents manquants',
      path: '/archives-mg/manquants',
      icon: 'warning',
      permissions: ['mg.archives.view'],
    },
    {
      section: 'Suivi',
      label: 'Corbeille',
      path: '/archives-mg/corbeille',
      icon: 'delete',
      permissions: ['mg.archives.view'],
    },
  ],
  'archives-generales': [
    {
      section: 'Archive Générale',
      label: 'Tous les documents',
      path: '/archives-generales',
      icon: 'inventory_2',
      exact: true,
      permissions: ['archives.general.view'],
    },
    {
      section: 'Archive Générale',
      label: 'Recherche avancée',
      path: '/archives-generales/recherche',
      icon: 'manage_search',
      permissions: ['archives.general.view'],
    },
  ],
};

export function navForModule(moduleCode: string | null | undefined): ShellNavItem[] {
  const code = (moduleCode || 'immobilisations').trim().toLowerCase();
  return MODULE_SHELL_NAV[code] ?? SHELL_NAV;
}

export function filterNavByPermissions(
  items: ShellNavItem[],
  opts: { isSuperuser: boolean; permissionCodes: string[] },
): ShellNavItem[] {
  if (opts.isSuperuser || opts.permissionCodes.includes('*')) {
    return items;
  }
  const have = new Set(opts.permissionCodes);
  return items.filter((item) => {
    if (!item.permissions?.length) {
      return true;
    }
    return item.permissions.some((p) => have.has(p));
  });
}

export function shellNavSections(items: ShellNavItem[]): { title: string; items: ShellNavItem[] }[] {
  const order: string[] = [];
  const map = new Map<string, ShellNavItem[]>();
  for (const item of items) {
    if (!map.has(item.section)) {
      map.set(item.section, []);
      order.push(item.section);
    }
    map.get(item.section)!.push(item);
  }
  return order.map((title) => ({ title, items: map.get(title)! }));
}
