/** Module Gestion des réclamations — types d'échange avec `/api/v1/reclamations` et utilitaires d'affichage. */

import { formatMontantOuTiret, parseMontant } from '../shared/montant.pipe';

export const RC_BASE = '/reclamations';

export type Domaine = 'TYPE' | 'MOTIF' | 'SOUS_MOTIF' | 'CANAL' | 'CANAL_REPONSE';
export type TypeUnite = 'DIRECTION' | 'DEPARTEMENT' | 'SERVICE' | 'AGENCE' | 'CELLULE';

export interface CodeLibelle {
  code: string;
  libelle: string;
}

export interface RefItem {
  id: string;
  domaine: Domaine;
  code: string | null;
  libelle: string;
  parent_id: string | null;
  description: string | null;
  ordre: number;
  actif: boolean;
  usage: number;
  /** Types, motifs, sous-motifs : valeur proposée ou validée par la Conformité. */
  a_valider?: boolean;
  statut_validation?: 'PROPOSEE' | 'VALIDEE' | null;
  statut_validation_libelle?: string | null;
  valide_le?: string | null;
}

export interface Unite {
  id: string;
  type_unite: TypeUnite;
  type_libelle: string;
  code: string | null;
  libelle: string;
  parent_id: string | null;
  agence_id: string | null;
  agence: string | null;
  /** Entité de l'organigramme BEA (référentiel CORE) correspondant à l'unité. */
  org_entite_id: string | null;
  org_entite: string | null;
  est_service_reclamations: boolean;
  email: string | null;
  description: string | null;
  ordre: number;
  actif: boolean;
  nb_membres: number;
  nb_dossiers: number;
}

export interface Membre {
  id: string;
  unite_id: string;
  user_id: string;
  nom: string;
  email: string;
  role_membre: 'RESPONSABLE' | 'AGENT';
  actif: boolean;
  compte_actif: boolean;
  depuis: string | null;
}

export interface UtilisateurTrouve {
  id: string;
  nom: string;
  email: string;
  acces_module: boolean;
}

export interface Agence {
  id: string;
  code: string;
  libelle: string;
}

export type Capacite =
  | 'voir' | 'tout_voir' | 'creer' | 'modifier' | 'qualifier' | 'affecter' | 'traiter' | 'gerer_service'
  | 'examiner_retour' | 'envoyer_reponse' | 'refuser'
  | 'annuler' | 'cloturer' | 'rouvrir' | 'archiver' | 'supprimer' | 'documents_voir' | 'documents_deposer'
  | 'documents_telecharger' | 'documents_retirer' | 'reporting_voir' | 'reporting_exporter'
  | 'referentiels_voir' | 'referentiels_gerer' | 'referentiels_valider' | 'unites_gerer' | 'admin';

export interface Acces {
  user_id: string;
  perimetre: 'TOUS' | 'UNITES' | 'PERSONNEL';
  unites: string[];
  unites_responsable: string[];
  membre_service_central: boolean;
  capacites: Record<Capacite, boolean>;
}

export interface RcConfig {
  acces: Acces;
  referentiels: Record<Domaine, RefItem[]>;
  unites: Unite[];
  agences: Agence[];
  libelles: {
    statuts: CodeLibelle[];
    etapes: CodeLibelle[];
    groupes: CodeLibelle[];
    statut_groupes: Record<string, string>;
    etape_du_statut: Record<string, string>;
    priorites: CodeLibelle[];
    resultats: CodeLibelle[];
    categories_client: CodeLibelle[];
    categories_document: CodeLibelle[];
    types_unite: CodeLibelle[];
    domaines: CodeLibelle[];
    statuts_rappel: CodeLibelle[];
    statuts_affectation: CodeLibelle[];
    statuts_reponse: CodeLibelle[];
    evaluations: CodeLibelle[];
    validations_referentiel: CodeLibelle[];
  };
  parametres: { enregistrement_appels_autorise: boolean };
  aujourdhui: string;
  utilisateur: string;
}

export interface DossierLigne {
  id: string;
  reference: string;
  objet: string;
  client_nom: string | null;
  client_racine: string | null;
  client_categorie: string | null;
  canal: string | null;
  type: string | null;
  motif: string | null;
  sous_motif: string | null;
  priorite: string;
  priorite_libelle: string;
  statut: string;
  statut_libelle: string;
  groupe: string;
  groupe_libelle: string;
  etape: string;
  etape_libelle: string;
  termine: boolean;
  unite_reception: string | null;
  unite_concernee: string | null;
  unite_traitement: string | null;
  agence: string | null;
  date_reclamation: string | null;
  date_premiere_reception: string;
  date_reception_sr: string | null;
  date_cloture: string | null;
  nb_operations: number;
  montant_total: string | null;
  devise: string;
  nb_documents: number;
  revision: number;
  updated_at: string | null;
  supprimee_le: string | null;
  motif_suppression: string | null;
  /** Présent seulement pour les profils habilités à supprimer. */
  suppression?: { possible: boolean; restaurable: boolean };
}

export interface RefCourt {
  id: string;
  code?: string | null;
  libelle: string;
  actif: boolean;
}

export interface UniteCourte {
  id: string;
  libelle: string;
  type_unite: TypeUnite;
  actif: boolean;
}

export interface Appel {
  id: string;
  appel_le: string;
  numero_appelant: string | null;
  agent: string | null;
  identite_verifiee: boolean;
  mode_verification: string | null;
  reference_appel: string | null;
  enregistrement_autorise: boolean;
  reference_enregistrement: string | null;
  rappel_statut: string;
  rappel_statut_libelle: string;
  rappel_prevu_le: string | null;
  rappel_effectue_le: string | null;
  commentaire: string | null;
}

export interface Dossier extends Omit<DossierLigne, 'suppression'> {
  description: string;
  source: string;
  type_ref: RefCourt | null;
  motif_ref: RefCourt | null;
  sous_motif_ref: RefCourt | null;
  motif_autre: string | null;
  sous_motif_autre: string | null;
  operations: Operation[];
  canal_ref: RefCourt | null;
  canal_telephone: boolean;
  unite_reception_ref: UniteCourte | null;
  unite_suivi_ref: UniteCourte | null;
  unite_concernee_ref: UniteCourte | null;
  unite_traitement_ref: UniteCourte | null;
  client: {
    racine: string | null;
    categorie: string | null;
    categorie_libelle: string | null;
    nom: string | null;
    telephone: string | null;
    email: string | null;
    adresse: string | null;
    agence: Agence | null;
  };
  compte_reference: string | null;
  carte_masquee: string | null;
  reclamation_liee: { id: string; reference: string | null } | null;
  doublon_de: { id: string; reference: string | null } | null;
  dates: Record<string, string | null>;
  gestionnaire: string | null;
  responsable_traitement: string | null;
  motif_refus: string | null;
  motif_annulation: string | null;
  resultat: string | null;
  resultat_libelle: string | null;
  motif_resolution: string | null;
  nb_reouvertures: number;
  nb_renvois: number;
  archivee_le: string | null;
  appels: Appel[];
  cree_par: string | null;
  created_at: string | null;
  modifie_par: string | null;
  affectations: Affectation[];
  affectation_courante: Affectation | null;
  reponses: ReponseClient[];
  reponse_courante: ReponseClient | null;
  preuve_envoi: boolean;
  cloture_par: string | null;
  actions: Record<string, boolean>;
  suppression: {
    supprimee_le: string | null;
    motif: string | null;
    supprimee_par: string | null;
  };
}

export interface SuppressionResultat {
  id: string;
  reference: string;
  operations_supprimees: number;
  documents_supprimes: number;
}

export interface Operation {
  id: string;
  ordre: number;
  reference: string;
  montant: string | null;
  devise: string;
}

/** Ligne en saisie : montant gardé en texte tant qu'il n'est pas validé. */
export interface OperationSaisie {
  reference: string;
  montant: string;
}

export interface Affectation {
  id: string;
  numero: number;
  statut: string;
  statut_libelle: string;
  unite: string | null;
  unite_id: string;
  emetteur: string | null;
  transmis_le: string | null;
  transmis_par: string | null;
  motif_transfert: string | null;
  instructions: string | null;
  recu_le: string | null;
  recu_par: string | null;
  responsable: string | null;
  analyse: string | null;
  actions_menees: string | null;
  conclusion: string | null;
  decision_proposee: string | null;
  decision_proposee_libelle: string | null;
  retour_le: string | null;
  retour_par: string | null;
  evaluation: string | null;
  evaluation_libelle: string | null;
  evaluation_commentaire: string | null;
  evalue_le: string | null;
  evalue_par: string | null;
  revision: number;
}

export interface ReponseClient {
  id: string;
  numero: number;
  statut: string;
  statut_libelle: string;
  objet: string | null;
  contenu: string;
  resultat: string | null;
  resultat_libelle: string | null;
  canal_envoi: string | null;
  canal_envoi_id: string | null;
  destinataire: string | null;
  redige_par: string | null;
  envoye_le: string | null;
  envoye_par: string | null;
  reference_envoi: string | null;
  revision: number;
}

export interface Compteur {
  code?: string;
  id?: string;
  libelle: string;
  n: number;
  nb_operations?: number;
  montant?: string;
}

export interface TableauBord {
  total: number;
  ouvertes: number;
  volume_30j: number;
  volume_30j_precedent: number;
  cloturees_30j: number;
  performance: {
    cloturees: number;
    delai_moyen_jours: number | null;
    delai_cloture_jours: number | null;
    delai_cloture_n: number;
  };
  /** Paramètres de liste reproduisant chaque KPI cliquable. */
  liens: Record<string, Record<string, string | null>>;
  filtres: { client_agence_id: string | null; date_debut: string | null; date_fin: string | null };
  anciennete: Compteur[];
  tendance: { mois: string; libelle: string; recues: number; cloturees: number }[];
  resultats: Compteur[];
  clients_recurrents: { racine: string; nom: string | null; n: number; ouvertes: number }[];
  nb_operations: number;
  dossiers_avec_operations: number;
  montant_total: string;
  devise: string;
  statuts: Compteur[];
  etapes: Compteur[];
  priorites: Compteur[];
  types: Compteur[];
  motifs: Compteur[];
  canaux: Compteur[];
  agences: Compteur[];
  services: Compteur[];
  unites_reception: Compteur[];
  recents: DossierLigne[];
}

export interface LigneComparaison {
  code: string;
  libelle: string;
  unite: string;
  a: number | string | null;
  b: number | string | null;
  ecart: number | null;
  variation: number | null;
  favorable: boolean | null;
  sens: 'hausse_favorable' | 'baisse_favorable' | null;
  indicateur: string | null;
}

export interface Comparaison {
  a: { debut: string; fin: string; jours: number; valeurs: Record<string, unknown> };
  b: { debut: string; fin: string; jours: number; valeurs: Record<string, unknown> };
  lignes: LigneComparaison[];
  avertissements: string[];
}

export interface ColonneCircuit {
  etape: string;
  libelle: string;
  items: DossierLigne[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  taille: number;
  totaux?: { nb_operations: number; dossiers_avec_operations: number; montant_total: string; devise: string };
}

export interface Evenement {
  id: string;
  type: string;
  libelle: string;
  statut_avant: string | null;
  statut_apres: string | null;
  code_statut_avant: string | null;
  code_statut_apres: string | null;
  etape_avant: string | null;
  etape_apres: string | null;
  date_effet: string;
  enregistre_le: string;
  auteur: string | null;
  unite: string | null;
  commentaire: string | null;
  donnees: Record<string, unknown>;
}

export interface Piece {
  id: string;
  titre: string | null;
  date_document: string | null;
  filename: string;
  mime_type: string | null;
  size_bytes: number | null;
  nature: 'pdf' | 'image' | 'excel' | 'word' | 'autre';
  categorie: string;
  categorie_libelle: string;
  commentaire: string | null;
  created_at: string | null;
  depose_par: string | null;
}

export interface Pieces {
  items: Piece[];
  actions: { deposer: boolean; telecharger: boolean; retirer: boolean };
}

export interface ApercuClient {
  racine: string;
  nom: string;
  categorie: 'PP' | 'PM';
  comptes: Array<{ compte: string; etat: string; devise: string; agence_id: string; agence: string }>;
}

export function montantFr(valeur: string | number | null | undefined, devise = 'MRU'): string {
  return formatMontantOuTiret(valeur, devise);
}

/** Montant saisi (« 1 234,56 », « 1234.56 »…) : nombre > 0 à deux décimales au plus, sinon `null`. */
export function lireMontant(saisie: string): number | null {
  if (!/^[\d\s.,]+$/.test(saisie.trim())) return null;
  const n = parseMontant(saisie);
  if (n === null || n <= 0 || Math.abs(n * 100 - Math.round(n * 100)) > 1e-6) return null;
  return n;
}

/** Sentinelle des listes Motif / Sous-motif pour la saisie libre « Autre ». */
export const AUTRE = '__autre__';

const FMT_DATE = new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
const FMT_DATE_HEURE = new Intl.DateTimeFormat('fr-FR', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
});

export function dateFr(iso: string | null | undefined, heure = false): string {
  if (!iso) return '—';
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return '—';
  return (heure ? FMT_DATE_HEURE : FMT_DATE).format(d);
}

/** Valeur `datetime-local` (heure locale du poste) ↔ ISO 8601 avec fuseau. */
export function versSaisieLocale(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function depuisSaisieLocale(valeur: string | null | undefined): string | null {
  if (!valeur) return null;
  const d = new Date(valeur);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function maintenantLocal(): string {
  return versSaisieLocale(new Date().toISOString());
}

export function taille(octets: number | null | undefined): string {
  if (!octets) return '—';
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${(octets / 1024).toFixed(0)} Ko`;
  return `${(octets / 1024 / 1024).toFixed(1)} Mo`;
}

/** Teinte des badges globaux `bea-ct-badge[data-tone]`. */
export function toneStatut(statut: string): string {
  switch (statut) {
    case 'A_QUALIFIER':
    case 'A_AFFECTER':
      return 'INFO';
    case 'REOUVERTE':
    case 'RETOUR_RECU':
    case 'A_CLOTURER':
      return 'ATTENTION';
    case 'EN_TRAITEMENT':
      return 'EN_PREPARATION';
    case 'REJETEE':
      return 'REJETE';
    case 'CLOTUREE':
      return 'ACTIF';
    case 'ANNULEE':
      return 'ANNULEE';
    default:
      return 'INFO';
  }
}

export function tonePriorite(priorite: string): string {
  return priorite === 'URGENTE' ? 'URGENT' : priorite === 'HAUTE' ? 'ATTENTION' : 'BROUILLON';
}

export function telechargerBlob(blob: Blob, nom: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nom;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ouvrirBlob(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank', 'noopener');
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
