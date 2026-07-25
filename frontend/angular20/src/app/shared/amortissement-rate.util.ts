/** Taux banque par durée (aligné Types El Amana — pas 100/3 brut). */
const BANK_TAUX_BY_DUREE: Record<number, number> = {
  3: 33.33,
  4: 25,
  5: 20,
  10: 10,
  25: 4,
};

/** Taux linéaire annuel (%) à partir de la durée en années. */
export function tauxLineaireFromDuree(annees: number | null | undefined): number | null {
  if (annees == null || annees <= 0) {
    return null;
  }
  if (BANK_TAUX_BY_DUREE[annees] != null) {
    return BANK_TAUX_BY_DUREE[annees];
  }
  return Math.round((100 / annees) * 10000) / 10000;
}

/**
 * Affichage taux : `10%`, `4%`, `33,3333%` (sans zéros inutiles).
 */
export function formatTauxPercent(taux: string | number | null | undefined): string {
  if (taux === null || taux === undefined || taux === '') {
    return '—';
  }
  const n =
    typeof taux === 'number' ? taux : Number(String(taux).replace(/\s/g, '').replace(',', '.'));
  if (!Number.isFinite(n)) {
    return '—';
  }
  const trimmed = n.toFixed(4).replace(/\.?0+$/, '').replace('.', ',');
  return `${trimmed}%`;
}

/**
 * Affichage lisible d'une période technique.
 * - `2026-Q1` → `Trimestre 1 — 2026`
 * - `2026-03` → `Mars 2026`
 * - `2026` → `Exercice 2026`
 */
export function formatPeriodeAmortissement(periode: string | null | undefined): string {
  if (!periode) {
    return '—';
  }
  const raw = periode.trim();
  if (/^\d{4}$/.test(raw)) {
    return `Exercice ${raw}`;
  }
  const quarter = /^(\d{4})-Q([1-4])$/i.exec(raw);
  if (quarter) {
    return `Trimestre ${quarter[2]} — ${quarter[1]}`;
  }
  const month = /^(\d{4})-(\d{2})$/.exec(raw);
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
