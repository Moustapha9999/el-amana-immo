/** Libellés d'entités pour le journal d'audit. */
export const AUDIT_ENTITY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Toutes les entités' },
  { value: 'user', label: 'Utilisateurs' },
  { value: 'immobilisation', label: 'Immobilisations' },
  { value: 'categorie_immobilisation', label: 'Catégories / types' },
  { value: 'ecriture_comptable', label: 'Écritures' },
  { value: 'inventaire_scan', label: 'Inventaire' },
];

/** Libellés d'actions métier. */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  login: 'Connexion',
  '2fa_enable': 'Activation 2FA',
  '2fa_disable': 'Désactivation 2FA',
  create: 'Création',
  update: 'Modification',
  delete: 'Suppression',
  mettre_en_service: 'Mise en service',
  transfert_agence: 'Transfert agence',
  scan_inventaire: 'Scan inventaire',
  comptabiliser_amortissement: 'Comptabilisation amort.',
  cession: 'Cession',
  rebut: 'Rebut',
  reevaluation: 'Réévaluation',
  ajustement: 'Ajustement',
};

export function auditEntityLabel(code: string): string {
  return AUDIT_ENTITY_OPTIONS.find((o) => o.value === code)?.label ?? code;
}

export function auditActionLabel(code: string): string {
  return AUDIT_ACTION_LABELS[code] ?? code;
}
