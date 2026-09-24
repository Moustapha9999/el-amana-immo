import { Pipe, PipeTransform } from '@angular/core';

/**
 * Règles BEA DIGITAL :
 * - Montant : 2 décimales, virgule, espace milliers (1 250,00)
 * - Quantité : entier, espace milliers (1 000)
 * - Taux : 2 décimales + « % » (18,00 %)
 * - Null / vide : 0,00 (montant) ou 0 (quantité)
 */

function groupInt(absInt: string): string {
  return absInt.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

function asNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  return parseMontant(value);
}

/** Arrondi standard au centime (half-up). */
export function montantArrondi(value: number | string | null | undefined): number {
  const n = asNumber(value);
  if (n === null) return 0;
  return Math.round(n * 100) / 100;
}

/** Quantité entière (half-up). */
export function quantiteEntiere(value: number | string | null | undefined): number {
  const n = asNumber(value);
  if (n === null) return 0;
  return Math.round(n);
}

/** Total ligne = quantité (entier) × prix unitaire (2 décimales), arrondi à 2 décimales. */
export function montantLigne(
  quantite: number | string | null | undefined,
  prixUnitaire: number | string | null | undefined,
): number {
  return montantArrondi(quantiteEntiere(quantite) * montantArrondi(prixUnitaire));
}

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

  const n = asNumber(value);
  const raw = n === null ? 0 : n;
  const fixed = raw.toFixed(Math.max(0, digits));
  const neg = fixed.startsWith('-');
  const abs = neg ? fixed.slice(1) : fixed;
  const [intPart, decPart] = abs.split('.');
  const grouped = groupInt(intPart);
  const body = decPart !== undefined ? `${grouped},${decPart}` : grouped;
  const formatted = neg ? `-${body}` : body;
  return devise ? `${formatted} ${devise}` : formatted;
}

export function formatQuantite(value: number | string | null | undefined): string {
  const q = quantiteEntiere(value);
  const neg = q < 0;
  const grouped = groupInt(String(Math.abs(q)));
  return neg ? `-${grouped}` : grouped;
}

export function formatTaux(value: number | string | null | undefined): string {
  return `${formatMontant(value, 2)} %`;
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

@Pipe({
  name: 'quantite',
  standalone: true,
  pure: true,
})
export class QuantitePipe implements PipeTransform {
  transform(value: number | string | null | undefined): string {
    return formatQuantite(value);
  }
}

@Pipe({
  name: 'taux',
  standalone: true,
  pure: true,
})
export class TauxPipe implements PipeTransform {
  transform(value: number | string | null | undefined): string {
    return formatTaux(value);
  }
}
