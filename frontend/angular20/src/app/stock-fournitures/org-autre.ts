import { AUTRE_LIBELLE, nettoyerLibelle, orgCle } from '../core/org/org-entite-libelle-select.component';
import { OrgEntiteOption } from '../core/org/org-referentiel.models';

export { nettoyerLibelle };

/** Valeur sentinelle des listes Département / Service : « Autre (préciser) ». */
export const AUTRE = AUTRE_LIBELLE;
export const AUTRE_MAX = 120;

/** Entité du référentiel portant ce libellé (ou alias), comme le contrôle serveur. */
export function entiteExistante(texte: string, entites: OrgEntiteOption[]): OrgEntiteOption | null {
  const cle = orgCle(texte);
  if (!cle) return null;
  return entites.find((e) => orgCle(e.libelle) === cle || (e.alias ?? []).includes(cle)) ?? null;
}

/** Message d'erreur du libellé saisi pour « Autre », ou null s'il est valide. */
export function erreurAutre(
  texte: string,
  champ: 'département' | 'service',
  entites: OrgEntiteOption[],
): string | null {
  const v = nettoyerLibelle(texte);
  if (!v) return `Saisissez le nom du ${champ}.`;
  if (v.length > AUTRE_MAX) return `${AUTRE_MAX} caractères au plus.`;
  const existante = entiteExistante(v, entites);
  if (existante) return `« ${existante.libelle} » existe déjà dans la liste : sélectionnez-le au lieu de « Autre ».`;
  return null;
}

export interface ValeursOrg {
  departement_id: string;
  departement_autre: string;
  service_id: string;
  service_autre: string;
}

/** Champs envoyés à l'API : identifiant du référentiel OU libellé « Autre », jamais les deux. */
export function corpsOrg(v: ValeursOrg): Record<string, string> {
  const body: Record<string, string> = {};
  if (v.departement_id === AUTRE) body['departement_autre'] = nettoyerLibelle(v.departement_autre);
  else body['departement_id'] = v.departement_id;
  if (v.service_id === AUTRE) body['service_autre'] = nettoyerLibelle(v.service_autre);
  else if (v.service_id) body['service_id'] = v.service_id;
  return body;
}

/** Libellé lisible « Département › Service » (référentiel ou saisie). */
export function libelleOrg(v: ValeursOrg, entites: OrgEntiteOption[], defaut: string): string {
  const dep =
    v.departement_id === AUTRE
      ? nettoyerLibelle(v.departement_autre)
      : entites.find((e) => e.id === v.departement_id)?.libelle;
  const srv =
    v.service_id === AUTRE ? nettoyerLibelle(v.service_autre) : entites.find((e) => e.id === v.service_id)?.libelle;
  const base = dep || defaut;
  return srv ? `${base} › ${srv}` : base;
}

/** Erreurs serveur « Autre » → champ du formulaire. */
export const CHAMP_AUTRE_PAR_CODE = {
  DEPARTEMENT_AUTRE_VIDE: 'departement_autre',
  DEPARTEMENT_EXISTANT: 'departement_autre',
  DEPARTEMENT_AUTRE_AMBIGU: 'departement_id',
  SERVICE_AUTRE_VIDE: 'service_autre',
  SERVICE_EXISTANT: 'service_autre',
  SERVICE_AUTRE_AMBIGU: 'service_id',
} as const;
