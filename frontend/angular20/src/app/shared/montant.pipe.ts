import { Pipe, PipeTransform } from '@angular/core';

/**
 * Format monétaire français : séparateur de milliers (espace) + virgule décimale.
 * Ex. 165185262.94 → « 165 185 262,94 »
 */
export function formatMontant(
  value: number | string | null | undefined,
  fractionDigits: number | string | boolean = 2,
  currency?: string | boolean,
): string {
  let digits = 2;
  let devise = '';
  if (typeof fractionDigits === 'number') {
    digits = fractionDigits;
  } else if (fractionDigits === true || fractionDigits === 'MRU') {
    devise = 'MRU';
  } else if (typeof fractionDigits === 'string' && fractionDigits.length > 0) {
    devise = fractionDigits;
  }
  if (currency === true || currency === 'MRU') {
    devise = 'MRU';
  } else if (typeof currency === 'string' && currency.length > 0) {
    devise = currency;
  }

  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const n = typeof value === 'number' ? value : parseMontant(value);
  if (n === null || !Number.isFinite(n)) {
    return '—';
  }
  const fixed = n.toFixed(digits);
  const neg = fixed.startsWith('-');
  const abs = neg ? fixed.slice(1) : fixed;
  const [intPart, decPart] = abs.split('.');
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const body = decPart !== undefined ? `${grouped},${decPart}` : grouped;
  const formatted = neg ? `-${body}` : body;
  return devise ? `${formatted} ${devise}` : formatted;
}

/** Parse une saisie FR/EN vers number (``1 234,56`` / ``1234.56``). */
export function parseMontant(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  let s = String(value).trim().replace(/\u00a0/g, ' ').replace(/\s/g, '');
  if (!s || s === '-' || s === ',' || s === '.') {
    return null;
  }
  // Si virgule et point : le dernier séparateur est décimal
  const lastComma = s.lastIndexOf(',');
  const lastDot = s.lastIndexOf('.');
  if (lastComma >= 0 && lastDot >= 0) {
    if (lastComma > lastDot) {
      s = s.replace(/\./g, '').replace(',', '.');
    } else {
      s = s.replace(/,/g, '');
    }
  } else if (lastComma >= 0) {
    s = s.replace(',', '.');
  }
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

@Pipe({
  name: 'montant',
  standalone: true,
  pure: true,
})
export class MontantPipe implements PipeTransform {
  /**
   * ``{{ x | montant }}`` → 1 234,56
   * ``{{ x | montant:'MRU' }}`` → 1 234,56 MRU
   * ``{{ x | montant:0 }}`` → 1 235
   * ``{{ x | montant:2:'MRU' }}`` → 1 234,56 MRU
   */
  transform(
    value: number | string | null | undefined,
    digitsOrCurrency: number | string | boolean = 2,
    currency?: string | boolean,
  ): string {
    return formatMontant(value, digitsOrCurrency, currency);
  }
}
