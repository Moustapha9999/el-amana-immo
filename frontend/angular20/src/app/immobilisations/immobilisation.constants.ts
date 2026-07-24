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
  { code: 'TY-142010', libelle: 'AAI', compte: '142010', taux: 10, duree_annees: 10 },
  { code: 'TY-147530', libelle: 'Logiciel', compte: '147530', taux: 10, duree_annees: 10 },
  { code: 'TY-147050', libelle: 'Frais immobilisés', compte: '147050', taux: 33, duree_annees: 3 },
  { code: 'TY-147030', libelle: 'Frais émission emprunt', compte: '147030', taux: 33, duree_annees: 3 },
  { code: 'TY-142060', libelle: 'Matériel de bureau', compte: '142060', taux: 10, duree_annees: 10 },
  { code: 'TY-142041', libelle: 'Matériel informatique', compte: '142041', taux: 20, duree_annees: 5 },
  { code: 'TY-142050', libelle: 'Matériel transport', compte: '142050', taux: 25, duree_annees: 4 },
  { code: 'TY-142020', libelle: 'Construction', compte: '142020', taux: 4, duree_annees: 25 },
  { code: 'TY-142097', libelle: "Matériel d'exploitation historique", compte: '142097', taux: 10, duree_annees: 10 },
  { code: 'TY-142080', libelle: 'Autres immobilisation', compte: '142080', taux: 4, duree_annees: 25 },
  { code: 'TY-142160', libelle: 'Autres immobilisations corporelles', compte: '142160', taux: 10, duree_annees: 10 },
] as const;

export type NatureImmoOfficielle = (typeof NATURE_IMMO_OFFICIELLE)[number];

/** Codes TY autorisés dans le formulaire (ordre de la liste déroulante). */
export const NATURE_IMMO_CODES_OFFICIELS: readonly string[] = NATURE_IMMO_OFFICIELLE.map((n) => n.code);

export function findNatureImmoOfficielle(code: string): NatureImmoOfficielle | undefined {
  return NATURE_IMMO_OFFICIELLE.find((n) => n.code === code);
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
