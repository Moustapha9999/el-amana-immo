import { Pipe, PipeTransform } from '@angular/core';

/**
 * Format monétaire français : séparateur de milliers (espace) + virgule décimale.
 * Ex. 165185262.94 → « 165 185 262,94 »
 */
export function formatMontant(
  value: number | string | null | undefined,
  fractionDigits = 2,
): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const n =
    typeof value === 'number' ? value : Number(String(value).replace(/\s/g, '').replace(',', '.'));
  if (!Number.isFinite(n)) {
    return '—';
  }
  const fixed = n.toFixed(fractionDigits);
  const neg = fixed.startsWith('-');
  const abs = neg ? fixed.slice(1) : fixed;
  const [intPart, decPart] = abs.split('.');
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const body = decPart !== undefined ? `${grouped},${decPart}` : grouped;
  return neg ? `-${body}` : body;
}

@Pipe({
  name: 'montant',
  standalone: true,
  pure: true,
})
export class MontantPipe implements PipeTransform {
  transform(value: number | string | null | undefined, digits = 2): string {
    return formatMontant(value, digits);
  }
}
