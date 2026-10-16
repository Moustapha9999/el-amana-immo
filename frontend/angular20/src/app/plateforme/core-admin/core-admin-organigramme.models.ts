import { OrgAffectation, OrgEntiteOption } from '../../core/org/org-referentiel.models';
import { describeApiError } from '../../core/feedback/api-error';

/** Entité complète (CORE ADMIN `/plateforme/admin/organisation/entites`). */
export interface OrgEntiteAdmin extends OrgEntiteOption {
  description: string | null;
  ordre: number;
  alias: string[];
  note_confirmation: string | null;
  source: string | null;
  chemin_ids: string[];
  nb_enfants: number;
  nb_utilisateurs: number;
  nb_postes: number;
  metadonnees: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface OrgPoste {
  id: string;
  entite_id: string;
  intitule: string;
  est_responsable: boolean;
  effectif_prevu: number | null;
  titulaire_user_id: string | null;
  titulaire_nom: string | null;
  actif: boolean;
  a_confirmer: boolean;
  note_confirmation: string | null;
  ordre: number;
  source: string | null;
  entite?: string;
}

export interface OrgUsage {
  liaison: string;
  module: string;
  libelle: string;
  nombre: number;
}

export interface OrgFiche {
  entite: OrgEntiteAdmin;
  chemin: OrgEntiteOption[];
  enfants: OrgEntiteAdmin[];
  postes: OrgPoste[];
  affectations: OrgAffectation[];
  agences: { id: string; code: string; libelle: string }[];
  usages: OrgUsage[];
  usages_sous_arbre: OrgUsage[];
}

export interface OrgEntiteControle extends OrgEntiteOption {
  detail: string | null;
}

export interface OrgCorrespondanceResume {
  liaison: string;
  module: string;
  libelle: string;
  valeurs: number;
  lignes: number;
  lignes_rattachees: number;
}

export interface OrgControles {
  resume: {
    entites: number;
    actives: number;
    a_confirmer: number;
    postes_a_confirmer: number;
    doublons: number;
    non_rattachees: number;
    incoherences: number;
    utilisateurs_sans_affectation: number;
    agences_non_rattachees: number;
    responsables_vacants: number;
    correspondances_en_attente: number;
  };
  a_confirmer: OrgEntiteControle[];
  postes_a_confirmer: OrgPoste[];
  doublons: { libelle: string; entites: OrgEntiteControle[] }[];
  non_rattachees: OrgEntiteControle[];
  incoherences: OrgEntiteControle[];
  utilisateurs_sans_affectation: { id: string; nom: string; email: string }[];
  agences_non_rattachees: { id: string; code: string; libelle: string }[];
  responsables_vacants: OrgPoste[];
  correspondances: OrgCorrespondanceResume[];
}

export interface OrgCorrespondanceValeur {
  cle: string;
  lignes: number;
  exemples: string[];
  suggestions: OrgEntiteOption[];
}

export interface OrgCorrespondances {
  liaison: string;
  libelle: string;
  module: string;
  valeurs: OrgCorrespondanceValeur[];
}

export interface OrgAgenceAdmin {
  id: string;
  code: string;
  libelle: string;
  ville: string | null;
  actif: boolean;
  org_entite_id: string | null;
  rattachement: string | null;
}

export interface OrgHistoriqueLigne {
  id: string;
  action: string;
  entity: string;
  entity_id: string | null;
  utilisateur: string | null;
  avant: Record<string, unknown> | null;
  apres: Record<string, unknown> | null;
  request_id: string | null;
  created_at: string | null;
}

export const ORG_ACTION_LIBELLES: Record<string, string> = {
  'org.entite.create': 'Entité créée',
  'org.entite.update': 'Entité modifiée',
  'org.entite.move': 'Entité déplacée',
  'org.entite.deactivate': 'Entité désactivée',
  'org.entite.activate': 'Entité réactivée',
  'org.poste.create': 'Poste créé',
  'org.poste.update': 'Poste modifié',
  'org.affectation.create': 'Affectation créée',
  'org.affectation.update': 'Affectation modifiée',
  'org.affectation.close': 'Affectation clôturée',
  'org.correspondance.apply': 'Correspondance appliquée',
  'org.agence.attach': 'Agence rattachée',
  'org.entite.confirm': 'Entité confirmée (import)',
  'org.import.apply': 'Import Excel appliqué',
};

export type OrgImportStatut = 'CREER' | 'EXISTANT' | 'A_CONFIRMER' | 'AMBIGU' | 'ERREUR';

export interface OrgImportLigne {
  ligne: number;
  direction: string | null;
  departement: string | null;
  service: string | null;
  statut: OrgImportStatut;
  message: string | null;
  type_entite?: string | null;
  entite_id?: string | null;
  chemin?: string | null;
}

export interface OrgImportEntiteCourte {
  id: string;
  libelle: string;
  type_entite: string;
  chemin: string | null;
  a_confirmer?: boolean;
}

export interface OrgImportApercu {
  empreinte: string;
  lignes: OrgImportLigne[];
  entites: { a_creer: number; existantes: number; a_confirmer: number; ambigues: number; erreurs: number };
  nb_lignes: number;
  nb_lignes_bloquantes: number;
  applicable: boolean;
  absentes_du_fichier: OrgImportEntiteCourte[];
}

export interface OrgImportResultat {
  empreinte: string;
  creees: OrgImportEntiteCourte[];
  confirmees: OrgImportEntiteCourte[];
  absentes_du_fichier: OrgImportEntiteCourte[];
}

/** Message d'erreur API lisible, avec la référence support quand le backend la fournit. */
export function orgErreur(err: unknown, fallback: string): string {
  const info = describeApiError(err);
  const message = info.message || fallback;
  return info.requestId ? `${message} (réf. ${info.requestId})` : message;
}
