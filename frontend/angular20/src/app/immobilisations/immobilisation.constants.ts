export const STATUT_IMMOBILISATION_LABELS: Record<string, string> = {
  brouillon: 'Brouillon',
  en_cours_acquisition: "En cours d'acquisition",
  en_service: 'En service',
  suspendue: 'Suspendue',
  cedee: 'Cédée',
  mise_au_rebut: 'Mise au rebut',
  transferee: 'Transférée',
  reclassee: 'Reclassée',
  archivee: 'Archivée',
  cession: 'Cédée (legacy)',
  rebut: 'Rebut (legacy)',
  en_cours: 'En cours',
  sortie: 'Sortie',
};

export function statutLabel(code: string): string {
  return STATUT_IMMOBILISATION_LABELS[code] ?? code;
}

export const PERIODICITE_OPTIONS = [
  { value: 'annuel', label: 'Annuel' },
  { value: 'trimestriel', label: 'Trimestriel' },
  { value: 'mensuel', label: 'Mensuel' },
] as const;

export const MODE_AMORTISSEMENT_OPTIONS = [
  { value: 'lineaire', label: 'Linéaire' },
  { value: 'degressif', label: 'Dégressif' },
] as const;

/**
 * Référentiel officiel Banque El Amana — Nature IMMO.
 * Durée dérivée du taux métier (durée ≈ 100 ÷ taux).
 */
export const NATURE_IMMO_OFFICIELLE = [
  { code: 'TY-142010', libelle: 'AAI', compte: '142010', amort: '148211', dotation: '681211', taux: 10, duree_annees: 10, prefix: 'AAI' },
  { code: 'TY-147530', libelle: 'Logiciel', compte: '147530', amort: '148700', dotation: '681700', taux: 10, duree_annees: 10, prefix: 'Log' },
  { code: 'TY-147050', libelle: 'Frais immobilisés', compte: '147050', amort: '148050', dotation: '681050', taux: 33.33, duree_annees: 3, prefix: 'Frais' },
  { code: 'TY-147030', libelle: 'Frais émission emprunt', compte: '147030', amort: '148030', dotation: '681030', taux: 33.33, duree_annees: 3, prefix: 'FraisEmp' },
  { code: 'TY-142060', libelle: 'Matériel de bureau', compte: '142060', amort: '148299', dotation: '681299', taux: 10, duree_annees: 10, prefix: 'MatBur' },
  { code: 'TY-142041', libelle: 'Matériel informatique', compte: '142041', amort: '148240', dotation: '681240', taux: 20, duree_annees: 5, prefix: 'MatInfo' },
  { code: 'TY-142050', libelle: 'Matériel transport', compte: '142050', amort: '148250', dotation: '681250', taux: 25, duree_annees: 4, prefix: 'MatTrans' },
  { code: 'TY-142020', libelle: 'Construction', compte: '142020', amort: '148220', dotation: '681220', taux: 4, duree_annees: 25, prefix: 'Const' },
  { code: 'TY-142097', libelle: "Matériel d'exploitation historique", compte: '142097', amort: '148230', dotation: '681230', taux: 10, duree_annees: 10, prefix: 'MatExp' },
  { code: 'TY-142080', libelle: 'Autres immobilisation', compte: '142080', amort: '148298', dotation: '681298', taux: 4, duree_annees: 25, prefix: 'Autres' },
  { code: 'TY-142160', libelle: 'Autres immobilisations corporelles', compte: '142160', amort: '148270', dotation: '681270', taux: 10, duree_annees: 10, prefix: 'AutCorp' },
] as const;

export type NatureImmoOfficielle = (typeof NATURE_IMMO_OFFICIELLE)[number];

/** Codes TY autorisés dans le formulaire (ordre de la liste déroulante). */
export const NATURE_IMMO_CODES_OFFICIELS: readonly string[] = NATURE_IMMO_OFFICIELLE.map((n) => n.code);

export function findNatureImmoOfficielle(code: string): NatureImmoOfficielle | undefined {
  return NATURE_IMMO_OFFICIELLE.find((n) => n.code === code);
}

/** Paire 148/681 officielle pour un compte immobilisation. */
export function pairedAccountsForImmo(compteImmo: string): { amort: string; dotation: string } | null {
  const ref = NATURE_IMMO_OFFICIELLE.find((n) => n.compte === compteImmo.trim());
  if (!ref) {
    return null;
  }
  return { amort: ref.amort, dotation: ref.dotation };
}

export function natureImmoOptionLabel(cat: {
  code: string;
  famille: string;
  compte_immobilisation: string;
}): string {
  const ref = findNatureImmoOfficielle(cat.code);
  if (ref) {
    return `${ref.libelle} (${ref.compte})`;
  }
  return `${cat.famille} (${cat.compte_immobilisation})`;
}

export function sortCategoriesNatureImmo<T extends { code: string }>(items: T[]): T[] {
  const order = new Map<string, number>(NATURE_IMMO_CODES_OFFICIELS.map((code, i) => [code, i]));
  return items
    .filter((c) => order.has(c.code))
    .sort((a, b) => (order.get(a.code) ?? 0) - (order.get(b.code) ?? 0));
}
