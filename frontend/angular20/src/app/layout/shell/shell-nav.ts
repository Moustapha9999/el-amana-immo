export interface ShellNavItem {
  label: string;
  path: string;
  icon: string;
  section: string;
  /** Si true, routerLinkActive exact (écrans « racine » du module). */
  exact?: boolean;
  /** Au moins une de ces permissions (superuser / * = tout). Vide = visible si module accessible. */
  permissions?: string[];
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
      section: 'Achats',
      label: 'Bons de commande',
      path: '/achats-appro/bons',
      icon: 'request_quote',
      exact: true,
      permissions: ['mg.purchase.view'],
    },
    {
      section: 'Achats',
      label: 'Nouveau BC',
      path: '/achats-appro/nouveau',
      icon: 'add_circle',
      permissions: ['mg.purchase.create'],
    },
  ],
  'notes-frais': [
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
  ],
  'contrats-echeances': [
    {
      section: 'Contrats',
      label: 'Liste',
      path: '/contrats-echeances/liste',
      icon: 'description',
      exact: true,
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Contrats',
      label: 'Alertes',
      path: '/contrats-echeances/alertes',
      icon: 'notification_important',
      permissions: ['mg.contrats.view'],
    },
    {
      section: 'Contrats',
      label: 'Nouveau',
      path: '/contrats-echeances/nouveau',
      icon: 'add_circle',
      permissions: ['mg.contrats.create'],
    },
  ],
  'archives-mg': [
    {
      section: 'Archives',
      label: 'Registre',
      path: '/archives-mg/registre',
      icon: 'folder_open',
      exact: true,
      permissions: ['mg.archives.view'],
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
