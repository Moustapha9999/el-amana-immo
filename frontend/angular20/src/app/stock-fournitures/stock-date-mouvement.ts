/** Date réelle d'un mouvement (≠ date d'enregistrement, toujours fixée par le serveur). */

export interface PeriodeSaisie {
  id: string;
  libelle: string;
  statut: 'OUVERTE' | 'ROUVERTE';
  date_debut: string;
  date_fin: string;
}

/** Bloc commun des référentiels `/sorties/referentiels` et `/entrees/referentiels`. */
export interface DatesSaisie {
  periodes_saisie?: PeriodeSaisie[];
  peut_regulariser?: boolean;
  date_du_jour?: string;
}

export function dateMin(ref: DatesSaisie | null): string | null {
  const debuts = (ref?.periodes_saisie ?? []).map((p) => p.date_debut).sort();
  return debuts[0] ?? null;
}

export function periodePourDate(ref: DatesSaisie | null, jour: string): PeriodeSaisie | null {
  return (ref?.periodes_saisie ?? []).find((p) => p.date_debut <= jour && jour <= p.date_fin) ?? null;
}

export function estRetroactive(ref: DatesSaisie | null, jour: string): boolean {
  return !!jour && !!ref?.date_du_jour && jour < ref.date_du_jour;
}

export function erreurDate(ref: DatesSaisie | null, jour: string): string | null {
  if (!jour || !ref?.date_du_jour) return null;
  if (jour > ref.date_du_jour) return 'La date du mouvement ne peut pas être postérieure à aujourd’hui.';
  if (!periodePourDate(ref, jour)) {
    return ref.peut_regulariser
      ? 'Cette date tombe dans une période clôturée : rouvrez-la (Paramètres → Périodes) pour régulariser.'
      : 'Cette date tombe dans une période clôturée : seul un administrateur du stock peut la rouvrir pour régulariser.';
  }
  return null;
}

/** Valeur envoyée au serveur : null = maintenant ; un jour passé est daté à midi UTC (heure de Nouakchott). */
export function corpsDate(ref: DatesSaisie | null, jour: string): string | null {
  return estRetroactive(ref, jour) ? `${jour}T12:00:00Z` : null;
}

export function jourFr(jour: string): string {
  const [a, m, j] = jour.split('-');
  return `${j}/${m}/${a}`;
}
