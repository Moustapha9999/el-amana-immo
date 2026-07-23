/** Taux linéaire annuel (%) à partir de la durée en années. */
export function tauxLineaireFromDuree(annees: number | null | undefined): number | null {
  if (annees == null || annees <= 0) {
    return null;
  }
  return Math.round((100 / annees) * 10000) / 10000;
}
