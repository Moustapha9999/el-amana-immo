/** Taux linéaire annuel (%) à partir de la durée en années. */
export function tauxLineaireFromDuree(annees: number | null | undefined): number | null {
  if (annees == null || annees <= 0) {
    return null;
  }
  return Math.round((100 / annees) * 10000) / 10000;
}

/**
 * Affichage lisible d'une période technique.
 * - `2026-Q1` → `Trimestre 1 — 2026`
 * - `2026-03` → `Mars 2026`
 */
export function formatPeriodeAmortissement(periode: string | null | undefined): string {
  if (!periode) {
    return '—';
  }
  const quarter = /^(\d{4})-Q([1-4])$/i.exec(periode.trim());
  if (quarter) {
    return `Trimestre ${quarter[2]} — ${quarter[1]}`;
  }
  const month = /^(\d{4})-(\d{2})$/.exec(periode.trim());
  if (month) {
    const labels = [
      '',
      'Janvier',
      'Février',
      'Mars',
      'Avril',
      'Mai',
      'Juin',
      'Juillet',
      'Août',
      'Septembre',
      'Octobre',
      'Novembre',
      'Décembre',
    ];
    const m = Number(month[2]);
    return `${labels[m] ?? month[2]} ${month[1]}`;
  }
  return periode;
}
