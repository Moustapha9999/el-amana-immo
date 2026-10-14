/** Référentiel organisationnel central (organigramme BEA) — contrat partagé par tous les modules. */

export type OrgTypeEntite =
  | 'CONSEIL'
  | 'COMITE'
  | 'DIRECTION_GENERALE'
  | 'DIRECTION'
  | 'DEPARTEMENT'
  | 'SERVICE'
  | 'SECTION'
  | 'CELLULE';

export type OrgPerimetre = 'PERSONNEL' | 'ENTITE' | 'ENTITE_ET_SOUS_ENTITES';
export type OrgTypeAffectation = 'PRINCIPALE' | 'SECONDAIRE' | 'INTERIM';

export const ORG_TYPE_LIBELLES: Record<OrgTypeEntite, string> = {
  CONSEIL: 'Conseil',
  COMITE: 'Comité',
  DIRECTION_GENERALE: 'Direction générale',
  DIRECTION: 'Direction',
  DEPARTEMENT: 'Département',
  SERVICE: 'Service',
  SECTION: 'Section',
  CELLULE: 'Cellule / unité rattachée',
};

export const ORG_PERIMETRE_LIBELLES: Record<OrgPerimetre, string> = {
  PERSONNEL: 'Personnel (ses propres dossiers)',
  ENTITE: 'Entité',
  ENTITE_ET_SOUS_ENTITES: 'Entité et sous-entités',
};

export const ORG_AFFECTATION_LIBELLES: Record<OrgTypeAffectation, string> = {
  PRINCIPALE: 'Principale',
  SECONDAIRE: 'Secondaire',
  INTERIM: 'Intérim',
};

/** Entité telle que renvoyée par `/api/v1/organisation/entites` (sélecteurs des modules). */
export interface OrgEntiteOption {
  id: string;
  code: string;
  libelle: string;
  sigle: string | null;
  type_entite: OrgTypeEntite;
  type_libelle: string;
  parent_id: string | null;
  actif: boolean;
  a_confirmer: boolean;
  chemin: string | null;
  profondeur: number;
}

export interface OrgAgenceOption {
  id: string;
  code: string;
  libelle: string;
  org_entite_id: string | null;
  rattachement: string | null;
}

export interface OrgAffectation {
  id: string;
  user_id: string;
  utilisateur: string | null;
  email: string | null;
  compte_actif: boolean | null;
  entite_id: string;
  entite: string | null;
  entite_type: string | null;
  entite_active: boolean;
  chemin: string | null;
  poste_id: string | null;
  poste: string | null;
  type_affectation: OrgTypeAffectation;
  type_libelle: string;
  perimetre: OrgPerimetre;
  perimetre_libelle: string;
  date_debut: string | null;
  date_fin: string | null;
  actif: boolean;
  commentaire: string | null;
}

export interface OrgMonPerimetre {
  niveau: 'GLOBAL' | 'ENTITES' | 'PERSONNEL';
  global: boolean;
  entites: string[];
  entite_principale_id: string | null;
  affectations: OrgAffectation[];
}
