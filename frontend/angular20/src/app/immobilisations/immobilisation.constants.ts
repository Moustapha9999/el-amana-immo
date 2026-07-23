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
