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

/** Comptes Banque El Amana exclus de tout calcul de dotation. */
export const COMPTES_NON_AMORTISSABLES_EL_AMANA = ['140000', '142000', '145300'] as const;

export const MESSAGE_NON_AMORTISSABLE_EL_AMANA =
  'Cette immobilisation appartient à une catégorie non amortissable pour Banque El Amana. Aucune dotation aux amortissements ne peut être calculée.';

/**
 * Référentiel officiel Banque El Amana — Nature IMMO.
 * Durée dérivée du taux métier (durée ≈ 100 ÷ taux) pour les natures amortissables.
 */
export const NATURE_IMMO_OFFICIELLE = [
  { code: 'TY-142010', libelle: 'AAI', compte: '142010', amort: '148211', dotation: '681211', taux: 10, duree_annees: 10, prefix: 'AAI', amortissable: true },
  { code: 'TY-147530', libelle: 'Logiciel', compte: '147530', amort: '148700', dotation: '681700', taux: 10, duree_annees: 10, prefix: 'Log', amortissable: true },
  { code: 'TY-147050', libelle: 'Frais immobilisés', compte: '147050', amort: '148050', dotation: '681050', taux: 33.33, duree_annees: 3, prefix: 'Frais', amortissable: true },
  { code: 'TY-147030', libelle: 'Frais émission emprunt', compte: '147030', amort: '148030', dotation: '681030', taux: 33.33, duree_annees: 3, prefix: 'FraisEmp', amortissable: true },
  { code: 'TY-142060', libelle: 'Matériel de bureau', compte: '142060', amort: '148299', dotation: '681299', taux: 10, duree_annees: 10, prefix: 'MatBur', amortissable: true },
  { code: 'TY-142041', libelle: 'Matériel informatique', compte: '142041', amort: '148240', dotation: '681240', taux: 20, duree_annees: 5, prefix: 'MatInfo', amortissable: true },
  { code: 'TY-142050', libelle: 'Matériel transport', compte: '142050', amort: '148250', dotation: '681250', taux: 25, duree_annees: 4, prefix: 'MatTrans', amortissable: true },
  { code: 'TY-142020', libelle: 'Construction', compte: '142020', amort: '148220', dotation: '681220', taux: 4, duree_annees: 25, prefix: 'Const', amortissable: true },
  { code: 'TY-142097', libelle: "Matériel d'exploitation historique", compte: '142097', amort: '148230', dotation: '681230', taux: 10, duree_annees: 10, prefix: 'MatExp', amortissable: true },
  { code: 'TY-142080', libelle: 'Autres immobilisation', compte: '142080', amort: '148298', dotation: '681298', taux: 4, duree_annees: 25, prefix: 'Autres', amortissable: true },
  { code: 'TY-142160', libelle: 'Autres immobilisations corporelles', compte: '142160', amort: '148270', dotation: '681270', taux: 10, duree_annees: 10, prefix: 'AutCorp', amortissable: true },
  { code: 'TY-140000', libelle: 'Titres de participations', compte: '140000', amort: '', dotation: '', taux: null, duree_annees: null, prefix: 'Titres', amortissable: false },
  { code: 'TY-142000', libelle: 'Terrain', compte: '142000', amort: '', dotation: '', taux: null, duree_annees: null, prefix: 'Terrain', amortissable: false },
  { code: 'TY-145300', libelle: 'Immo en cours', compte: '145300', amort: '', dotation: '', taux: null, duree_annees: null, prefix: 'ImmoCours', amortissable: false },
] as const;

export type NatureImmoOfficielle = (typeof NATURE_IMMO_OFFICIELLE)[number];

/** Codes TY autorisés dans le formulaire (ordre de la liste déroulante). */
export const NATURE_IMMO_CODES_OFFICIELS: readonly string[] = NATURE_IMMO_OFFICIELLE.map((n) => n.code);

export function findNatureImmoOfficielle(code: string): NatureImmoOfficielle | undefined {
  return NATURE_IMMO_OFFICIELLE.find((n) => n.code === code);
}

export function isCompteNonAmortissable(compte: string | null | undefined): boolean {
  const c = (compte ?? '').trim();
  return (COMPTES_NON_AMORTISSABLES_EL_AMANA as readonly string[]).includes(c);
}

export function isNatureImmoAmortissable(nature: { amortissable?: boolean; compte?: string } | null | undefined): boolean {
  if (!nature) {
    return false;
  }
  if (nature.compte && isCompteNonAmortissable(nature.compte)) {
    return false;
  }
  return nature.amortissable !== false;
}

/** Paire 148/681 officielle pour un compte immobilisation. */
export function pairedAccountsForImmo(compteImmo: string): { amort: string; dotation: string } | null {
  const ref = NATURE_IMMO_OFFICIELLE.find((n) => n.compte === compteImmo.trim());
  if (!ref || !ref.amortissable || !ref.amort || !ref.dotation) {
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
