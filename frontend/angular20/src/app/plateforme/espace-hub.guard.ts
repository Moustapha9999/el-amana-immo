/**
 * Segments d’URL réservés — ne doivent pas être pris par le hub département dynamique.
 * (Login, CORE ADMIN, Accueil, Login 2, shell Immobilisations legacy-root.)
 */
import { CanMatchFn } from '@angular/router';
import { LEGACY_ROOT_PATH_SEGMENTS } from './module-routing.contract';

const PLATEFORME_FIXED = [
  'login',
  'forgot-password',
  'reset-password',
  'accueil',
  'admin',
  'modules',
  // Modules préfixés (ne pas confondre avec un code espace)
  'stock-fournitures',
  'achats-appro',
  'notes-frais',
  'contrats-echeances',
  'archives-mg',
  'archives-generales',
  'archive-generale',
  'credit',
  'rh',
  'tickets-si',
  'demandes-achat',
] as const;

export const ESPACE_HUB_RESERVED_SEGMENTS: ReadonlySet<string> = new Set([
  ...PLATEFORME_FIXED,
  ...LEGACY_ROOT_PATH_SEGMENTS,
]);

/** true = cette URL peut être un hub département (`/:espaceCode`). */
export function isEspaceHubPathSegment(segment: string | null | undefined): boolean {
  if (!segment) {
    return false;
  }
  return !ESPACE_HUB_RESERVED_SEGMENTS.has(segment);
}

/**
 * canMatch : laisse passer dashboard / immobilisations / … vers le shell immo.
 */
export const espaceHubCanMatch: CanMatchFn = (_route, segments) => {
  return isEspaceHubPathSegment(segments[0]?.path);
};
