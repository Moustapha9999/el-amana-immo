import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';

export const DEMANDES_MODULE_CODES = [
  'demandes-comptabilite',
  'demandes-credit',
  'demandes-rh',
  'demandes-informatique',
  'demandes-mg',
] as const;

export const ESPACE_BY_DEMANDES_MODULE: Record<string, string> = {
  'demandes-comptabilite': 'comptabilite',
  'demandes-credit': 'credit',
  'demandes-rh': 'rh',
  'demandes-informatique': 'informatique',
  'demandes-mg': 'moyens-generaux',
};

export const ESPACE_LABEL: Record<string, string> = {
  comptabilite: 'Comptabilité',
  credit: 'Crédit',
  rh: 'RH',
  informatique: 'Informatique',
  'moyens-generaux': 'Moyens Généraux',
};

@Injectable({ providedIn: 'root' })
export class DemandesContext {
  private readonly router = inject(Router);

  moduleCode(): string {
    const first = this.router.url.split('?')[0].split('/').filter(Boolean)[0] || '';
    return DEMANDES_MODULE_CODES.includes(first as (typeof DEMANDES_MODULE_CODES)[number])
      ? first
      : 'demandes-mg';
  }

  base(): string {
    return `/${this.moduleCode()}`;
  }

  espaceCode(): string {
    return ESPACE_BY_DEMANDES_MODULE[this.moduleCode()] || 'moyens-generaux';
  }

  kicker(): string {
    return ESPACE_LABEL[this.espaceCode()] || 'Demandes';
  }

  isProcessor(): boolean {
    return this.moduleCode() === 'demandes-mg';
  }
}
