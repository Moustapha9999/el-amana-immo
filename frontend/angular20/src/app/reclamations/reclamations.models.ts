/** Module Gestion des réclamations — types d'échange avec `/api/v1/reclamations` et utilitaires d'affichage. */

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
  | 'examiner_retour' | 'rediger_reponse' | 'valider_reponse' | 'envoyer_reponse' | 'suspendre' | 'refuser'
  | 'annuler' | 'cloturer' | 'rouvrir' | 'archiver' | 'documents_voir' | 'documents_deposer'
  | 'documents_telecharger' | 'documents_retirer' | 'reporting_voir' | 'reporting_exporter'
  | 'referentiels_voir' | 'referentiels_gerer' | 'unites_gerer' | 'delais_gerer' | 'delais_valider'
  | 'audit_voir' | 'admin';

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
    validations_regle: CodeLibelle[];
    unites_duree: CodeLibelle[];
    points_depart: CodeLibelle[];
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
  unite_traitement: string | null;
  date_premiere_reception: string;
  date_reception_sr: string | null;
  date_cloture: string | null;
  echeance: string | null;
  en_retard: boolean;
  nb_documents: number;
  revision: number;
  updated_at: string | null;
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

export interface Dossier extends DossierLigne {
  description: string;
  source: string;
  type_ref: RefCourt | null;
  motif_ref: RefCourt | null;
  sous_motif_ref: RefCourt | null;
  canal_ref: RefCourt | null;
  canal_telephone: boolean;
  unite_reception_ref: UniteCourte | null;
  unite_suivi_ref: UniteCourte | null;
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
  operation: {
    compte_reference: string | null;
    carte_masquee: string | null;
    reference: string | null;
    date: string | null;
    montant_conteste: string | null;
    devise: string | null;
  };
  reclamation_liee: { id: string; reference: string | null } | null;
  doublon_de: { id: string; reference: string | null } | null;
  dates: Record<string, string | null>;
  echeance_initiale: string | null;
  regle_delai_id: string | null;
  gestionnaire: string | null;
  responsable_traitement: string | null;
  motif_suspension: string | null;
  conditions_reprise: string | null;
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
  actions: Record<string, boolean>;
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
  echeance_service: string | null;
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
  soumis_le: string | null;
  valide_par: string | null;
  valide_le: string | null;
  commentaire_validation: string | null;
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
}

export interface TableauBord {
  total: number;
  ouvertes: number;
  retards: number;
  sans_echeance: number;
  volume_30j: number;
  cloturees_30j: number;
  groupes: Compteur[];
  etapes: Compteur[];
  priorites: Compteur[];
  types: Compteur[];
  canaux: Compteur[];
  unites_reception: Compteur[];
  unites_traitement: Compteur[];
  recents: DossierLigne[];
  dossiers_retard: DossierLigne[];
}

export interface ColonneCircuit {
  etape: string;
  libelle: string;
  items: DossierLigne[];
}

export interface RegleDelai {
  id: string;
  libelle: string;
  type_id: string | null;
  type: string | null;
  motif_id: string | null;
  motif: string | null;
  priorite: string | null;
  priorite_libelle: string | null;
  duree: number;
  unite_duree: string;
  unite_duree_libelle: string;
  point_depart: string;
  point_depart_libelle: string;
  seuil_alerte: number | null;
  delai_service: number | null;
  neutraliser_suspension: boolean;
  date_effet: string | null;
  date_fin: string | null;
  statut_validation: string;
  statut_validation_libelle: string;
  reglementaire: boolean;
  commentaire: string | null;
  actif: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  taille: number;
}

export interface Evenement {
  id: string;
  type: string;
  libelle: string;
  statut_avant: string | null;
  statut_apres: string | null;
  etape_avant: string | null;
  etape_apres: string | null;
  date_effet: string;
  enregistre_le: string;
  auteur: string | null;
  unite: string | null;
  commentaire: string | null;
  donnees: Record<string, unknown>;
}

export interface LigneAudit {
  id: string;
  action: string;
  entity: string;
  utilisateur: string | null;
  date: string;
  avant: Record<string, unknown> | null;
  apres: Record<string, unknown> | null;
  ip: string | null;
  request_id: string | null;
}

export interface Piece {
  id: string;
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
    case 'RECUE':
    case 'RECUE_SR':
      return 'INFO';
    case 'A_QUALIFIER':
    case 'REOUVERTE':
    case 'RETOUR_RECU':
      return 'ATTENTION';
    case 'AFFECTEE':
    case 'EN_TRAITEMENT':
    case 'REPONSE_A_PREPARER':
    case 'REPONSE_ENVOYEE':
      return 'EN_PREPARATION';
    case 'ATTENTE_INFO':
    case 'SUSPENDUE':
      return 'SUSPENDU';
    case 'REFUSEE':
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
