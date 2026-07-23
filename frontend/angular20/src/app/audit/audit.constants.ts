/** Libellés d'entités pour le journal d'audit. */
export const AUDIT_ENTITY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'Toutes les entités' },
  { value: 'categorie_immobilisation', label: 'Catégories / types' },
  { value: 'immobilisation', label: 'Immobilisations' },
  { value: 'ecriture_comptable', label: 'Écritures comptables' },
  { value: 'inventaire_scan', label: 'Scans inventaire' },
  { value: 'user', label: 'Utilisateurs (connexion, 2FA)' },
];

export function auditEntityLabel(code: string): string {
  return AUDIT_ENTITY_OPTIONS.find((o) => o.value === code)?.label ?? code;
}
