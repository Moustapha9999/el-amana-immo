export interface ShellNavItem {
  label: string;
  path: string;
  icon: string;
  section: string;
}

export const SHELL_NAV: ShellNavItem[] = [
  { section: 'Pilotage', label: 'Dashboard', path: '/dashboard', icon: 'dashboard' },
  { section: 'Pilotage', label: 'Notifications', path: '/notifications', icon: 'notifications' },
  { section: 'Patrimoine', label: 'Immobilisations', path: '/immobilisations', icon: 'apartment' },
  { section: 'Patrimoine', label: 'Inventaire', path: '/inventaire', icon: 'qr_code_scanner' },
  { section: 'Patrimoine', label: 'Amortissements', path: '/amortissements', icon: 'timeline' },
  {
    section: 'Patrimoine',
    label: 'Récap. amortissement',
    path: '/recap-amortissement',
    icon: 'table_chart',
  },
  { section: 'Patrimoine', label: 'Comptes', path: '/comptes', icon: 'account_balance_wallet' },
  {
    section: 'Patrimoine',
    label: 'Soldes 148 / 68',
    path: '/comptes/soldes-148-68',
    icon: 'account_balance',
  },
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
