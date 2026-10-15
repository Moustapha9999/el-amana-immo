export const CL_BASE = '/clientele';

export const MATRICE_LBC = 'Matrice des risques LBC/FT BEA';
export const FICHE_SCORING = 'Fiche de scoring';

export const SOURCES_LBC: Record<string, string> = {
  MATRICE_V1: MATRICE_LBC,
  SCORING_V4: FICHE_SCORING,
  SCORING_V4_LISTE: `${FICHE_SCORING} (listes)`,
  SCORING_V4_PAYS_ENG_FR: `${FICHE_SCORING} (pays)`,
  PROPOSITION_BEA_DIGITAL: 'Proposition BEA DIGITAL',
};

export const STATUTS_REGLE: Record<string, string> = {
  ALIGNEE: 'Alignée',
  SOURCE_V1: 'Matrice seule',
  SOURCE_V4: 'Fiche seule',
  A_ARBITRER: 'À arbitrer',
  A_CONFIGURER: 'À configurer',
  A_VERIFIER: 'À vérifier',
  SUSPENDU: 'Suspendu',
  VALIDEE_CDC: 'Validée CDC',
  VALIDEE_METIER: 'Validée métier',
};

export const MODES_DECISION: Record<string, string> = {
  MOTEUR: 'Moteur',
  FICHIER: 'Fichier',
  MANUEL: 'Décision manuelle',
};

/** Traçabilité d'une classification retenue (champs séparés : calcul, fichier, décision). */
export interface TraceClassification {
  score_calcule: number | null;
  niveau_propose: string | null;
  classe_source_fichier: string | null;
  niveau_retenu?: string | null;
  mode_decision: string | null;
  motif_moteur: string | null;
  motif_source: string | null;
  motif_decision_manuelle: string | null;
  evaluation_id: string | null;
  lot_id: string | null;
  ligne_source: number | null;
  date_maj_metier: string | null;
  analyste_kyc: string | null;
  date_reference: string | null;
  version_moteur: string | null;
  version_regles: string | null;
  force: boolean | null;
  blocage_leve: boolean | null;
}

export function libSource(code: string | null | undefined): string {
  if (!code) return '—';
  return code.split('+').map((c) => SOURCES_LBC[c] ?? c).join(' + ');
}

export interface Capacites {
  voir: boolean;
  imports_voir: boolean;
  imports_executer: boolean;
  rapprochement_voir: boolean;
  rapprochement_executer: boolean;
  classif_voir: boolean;
  classif_executer: boolean;
  classif_admin: boolean;
  classif_forcer?: boolean;
  classif_arbitrer?: boolean;
  filtrage_voir: boolean;
  filtrage_executer: boolean;
  filtrage_decider: boolean;
  reporting_voir: boolean;
  bcm_voir: boolean;
  bcm_preparer: boolean;
  bcm_valider: boolean;
  bcm_cloturer: boolean;
  exporter: boolean;
  admin: boolean;
}

export interface SourceColonne {
  colonne: string;
  source: string;
  champ: string | null;
  detail: string;
  etat?: string;
  colonne_orion?: string | null;
  version_regle?: string;
  verifie_le?: string | null;
}

export interface AgenceRef {
  code: string;
  libelle: string;
}

export interface ClConfig {
  capacites: Capacites;
  sources: SourceColonne[];
  agences: AgenceRef[];
  classement_masse?: { actif: boolean; reference_validation: string | null; message: string | null };
}

export interface TableauBord {
  nb_clients: number;
  nb_comptes: number;
  nb_rib?: number;
  pp: number;
  pm: number;
  non_identifies: number;
  constructions_juridiques?: number | null;
  ouverts: number;
  clotures: number;
  date_extraction?: string | null;
  periode_libelle?: string;
  dernier_import?: {
    id: string;
    fichier_nom: string;
    statut: string;
    importe_le: string | null;
    cree_le: string | null;
    date_extraction: string | null;
    nb_clients: number;
    nb_comptes: number;
    nb_rejets: number;
    nb_anomalies: number;
  } | null;
  anomalies?: {
    a_traiter: number;
    sans_identifiant: number;
    agence_inconnue: number;
    alertes_ouvertes: number;
    rejets_dernier_import: number;
    anomalies_dernier_import: number;
    multi_agences: number;
    secteur_vide: number;
    nationalite_vide: number;
  };
  risques?: { niveau: string; libelle: string; clients: number }[];
  non_classes?: number;
  agences?: { code: string; libelle: string; clients: number }[];
  evolution?: { mois: string; libelle: string; nouveaux: number }[];
  activite?: { type: string; id: string; libelle: string; statut: string; le: string | null; detail: string | null }[];
  sources: SourceColonne[];
}

export function etatMapping(s: SourceColonne): string {
  if (s.etat) return s.etat;
  if (s.source === 'ABSENT') return 'ABSENT';
  if (s.source === 'PARTIEL') return 'PARTIEL';
  if (s.source === 'DERIVE_ORION') return 'DERIVE';
  if (s.source === 'CLASSIFICATION') return 'A_VALIDER';
  return 'CONFIRME';
}

export const ETAT_MAPPING: Record<string, string> = {
  CONFIRME: 'Confirmé',
  PARTIEL: 'Partiel',
  DERIVE: 'Dérivé',
  ABSENT: 'Absent',
  A_VALIDER: 'À valider',
};

export interface SituationLigne {
  racine_client: string;
  nom_client: string;
  prenoms: string | null;
  nationalite: string | null;
  statut_resident: string | null;
  nni: string | null;
  nif: string | null;
  categorie_juridique: string | null;
  agent_economique: string | null;
  profil_derive: string;
  etat_client: string;
  date_ouverture: string | null;
  code_agence: string | null;
  agence: string | null;
  nb_comptes: number;
  nb_comptes_ouverts: number;
  nb_agences: number;
}

export interface PageSituation {
  total: number;
  page: number;
  taille: number;
  items: SituationLigne[];
}

export interface CompteFiche {
  compte: string;
  rib: string;
  etat_compte: string;
  devise: string;
  ncg: string | null;
  code_agence: string | null;
  agence: string | null;
  date_ouverture: string | null;
  ddc: string | null;
  ddd: string | null;
  conformite_compte: string | null;
}

export interface FicheClient {
  client: Record<string, string | null>;
  situation: SituationLigne | null;
  comptes: CompteFiche[];
  dernier_import: { id: string; fichier_nom: string; importe_le: string | null } | null;
  classification: {
    niveau: string; source: string; motif_risque: string | null; motif_classement: string | null;
    motifs: { critere?: string; libelle?: string; motif?: string }[]; classifie_le: string | null;
  } & Partial<TraceClassification> | null;
  alertes_ouvertes: { id: string; statut: string; motif: string; precedent_faux_positif: boolean }[];
  sources: SourceColonne[];
  kyc: DonneesKyc | null;
}

export interface DonneesKyc {
  date_eer: string | null; profil: string | null; sous_profil: string | null; statut_gel: string | null;
  date_maj_client: string | null; analyste_kyc: string | null; date_creation_entreprise: string | null;
  source: string; lot_id: string | null; ligne_source: number | null; maj_le: string | null;
}

export const SOURCE_IMPORT_HEBDO = 'IMPORT_HEBDO';

export const LIBELLES_ACTION: Record<string, string> = {
  CREATION: 'Création de la fiche', MAJ_DONNEES: 'Mise à jour de données', PROPOSITION: 'Proposition',
  ACCEPTATION: 'Acceptation', MODIFICATION: 'Modification', REJET: 'Rejet', VERIFICATION: 'Vérification manuelle',
};

export interface EntreeJournal {
  id: string; racine_client: string; nom_client: string | null; type_action: string; libelle_action: string;
  champ: string | null; ancienne_valeur: string | null; nouvelle_valeur: string | null; motif: string | null;
  analyste_kyc: string | null; origine: 'SAISIE' | 'IMPORT'; lot_id: string | null; ligne_source: number | null;
  groupe_id: string | null; utilisateur: string | null; date: string | null;
}

export interface PageJournal { total: number; page: number; taille: number; items: EntreeJournal[]; }

export const ETATS_PROPOSITION: Record<string, string> = {
  PROPOSE: 'Proposé', A_VERIFIER: 'À vérifier', NON_CLASSIFIABLE: 'Non classifiable', A_EVALUER: 'À évaluer',
};

export const STATUTS_DECISION: Record<string, string> = {
  EN_ATTENTE: 'En attente', ACCEPTEE: 'Acceptée', MODIFIEE: 'Modifiée', REJETEE: 'Rejetée', ANCIEN_CIRCUIT: 'Ancien circuit',
};

export const STATUTS_CLIENT: Record<string, string> = {
  EXISTANT: 'Existant', NOUVEAU: 'Nouveau', AMBIGU: 'Identité ambiguë', DOUBLON: 'Doublon', INVALIDE: 'Racine invalide',
};

export interface Proposition {
  etat: string; niveau: string | null; origine: 'FICHIER' | 'MOTEUR' | null; categorie: string | null;
  categorie_libelle: string | null; raison: string | null; niveau_moteur: string | null; statut_moteur: string | null;
  ecart_moteur: boolean;
}

export interface LigneHebdo {
  ligne: number; racine: string | null; brut: string | null; statut: string; statut_client: string; nom: string | null;
  niveau_fichier: string | null; niveau_fichier_brut: string | null; analyste: string | null; anomalies: string[];
  classe_actuelle: string | null; source_actuelle: string | null; proposition: Proposition;
  verification: string[]; identite: string[]; statut_decision: string; exclusion_groupe: string | null;
  decision_ligne: {
    decision: string; niveau: string | null; motif: string | null; analyste_kyc: string | null;
    client_cree: boolean; groupe_id: string | null; par_nom: string | null; le: string | null;
  } | null;
}

export interface LotHebdo {
  id: string; fichier_nom: string; type: string; statut_lot: string; periode_reference: string | null;
  stats: Record<string, number>; evaluation: Record<string, unknown> | null; message: string | null;
  total_filtre: number; page: number; taille: number; lignes: LigneHebdo[]; created_at: string | null;
  fichier_disponible: boolean; limite_evaluation: number;
}

export interface ColonneMapping {
  champ: string;
  libelle: string;
  entete: string;
  obligatoire: boolean;
}

export interface AnalyseImport {
  feuille: string;
  ligne_entete: number;
  mapping: Record<string, string>;
  colonnes: ColonneMapping[];
  colonnes_ignorees: string[];
  colonnes_manquantes: string[];
  champs_disponibles: string[];
  apercu: Record<string, string | number>[];
  stats: Record<string, number | Record<string, number>>;
  apercu_ecriture: {
    clients_a_creer: number;
    clients_a_mettre_a_jour: number;
    comptes_a_creer: number;
    comptes_a_mettre_a_jour: number;
    comptes_absents_du_fichier: number;
  };
  deja_importe: { id: string; le: string | null } | null;
}

export interface ImportClientele {
  id: string;
  fichier_nom: string;
  statut: string;
  nb_lignes: number;
  nb_clients: number;
  nb_comptes: number;
  nb_rejets: number;
  nb_anomalies: number;
  clients_crees: number | null;
  clients_maj: number | null;
  comptes_crees: number | null;
  comptes_maj: number | null;
  created_at: string | null;
  importe_le: string | null;
  auteur: string | null;
  resultat: Record<string, number> | null;
  stats: Record<string, number> | null;
  analyse?: AnalyseImport;
}

export interface AnomaliePage {
  total: number;
  page: number;
  taille: number;
  items: { numero: number; racine_client: string | null; code: string; message: string; bloquante: boolean }[];
}

export function dateFr(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

export function dateHeureFr(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.toLocaleDateString('fr-FR')} ${d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;
}

export function n(v: number | null | undefined): string {
  return (v ?? 0).toLocaleString('fr-FR');
}

export function valeurIndic(statut: string, valeur: number | null | undefined): string {
  if (statut === 'A_CONFIGURER' || valeur === null || valeur === undefined) return 'À CONFIGURER';
  return n(valeur);
}

export function telecharger(blob: Blob, nom: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nom;
  a.click();
  URL.revokeObjectURL(url);
}
