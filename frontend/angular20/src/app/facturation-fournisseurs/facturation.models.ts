/** Types et libellés — Moyens Généraux › Facturation Fournisseurs. */

import { aujourdhui } from '../contrats-echeances/contrats.models';

export { aujourdhui, dateFr, dateHeureFr, joursLabel, telechargerBlob } from '../contrats-echeances/contrats.models';

export const FX_BASE = '/facturation-fournisseurs';

export interface Libelle {
  code: string;
  libelle: string;
}

export interface FxCapacites {
  view: boolean;
  create: boolean;
  update: boolean;
  delete: boolean;
  validate: boolean;
  archive: boolean;
  export: boolean;
  payment_view: boolean;
  payment_create: boolean;
  payment_update: boolean;
  payment_delete: boolean;
  documents_view: boolean;
  documents_create: boolean;
  documents_delete: boolean;
  analytics: boolean;
  reports: boolean;
  manage: boolean;
}

export interface FxConfig {
  statuts: Libelle[];
  statuts_paiement: Libelle[];
  types_point: Libelle[];
  types_facture: Libelle[];
  types_document: Libelle[];
  periodicites: string[];
  modes_paiement: string[];
  moyens_paiement: Record<string, ChampPaiement[]>;
  champs_profil: Libelle[];
  profils: FxProfil[];
  devises: string[];
  devise: string;
  mois: string[];
  seuils: { delai_paiement_jours: number; alerte_echeance_jours: number; seuil_hausse_pct: number; delai_reception_jours: number };
  ged_taille_max_mo: number;
  capacites: FxCapacites;
  agence_scope: { id: string; libelle: string | null } | null;
}

export type EtatChamp = 'obligatoire' | 'facultatif' | 'masque';

export type ChampProfil =
  | 'numero_fournisseur' | 'reference_fournisseur' | 'periode' | 'periode_debut' | 'periode_fin'
  | 'montant_ht' | 'montant_tva' | 'autres_taxes' | 'remise' | 'montant_ttc' | 'arrieres' | 'reglage'
  | 'montant_a_payer' | 'date_echeance';

/** Profil de facturation (SOMELEC, MATTEL SMS…) : champs applicables et libellés, sans code par fournisseur. */
export interface FxProfil {
  id: string;
  code: string;
  libelle: string;
  fournisseur_id: string;
  fournisseur: string | null;
  type_facture: string | null;
  /** Taux en vigueur aujourd’hui (null = non configuré : aucun calcul ni contrôle de TVA). */
  taux_tva: number | null;
  taux_tva_liste: FxTva[];
  champs: Record<ChampProfil, EtatChamp>;
  libelles: Record<ChampProfil, string>;
  description: string | null;
  actif: boolean;
  ordre: number;
}

/** Taux de TVA daté d’un profil (bornes incluses ; null = sans limite). */
export interface FxTva {
  id: string;
  profil_id: string;
  taux: number;
  date_debut: string | null;
  date_fin: string | null;
  observation: string | null;
  etat: 'EN_VIGUEUR' | 'A_VENIR' | 'EXPIRE';
}

/** Taux applicable à une date (ISO) parmi les taux datés d’un profil — même règle que le backend. */
export function fxTauxALaDate(liste: FxTva[] | undefined, jour: string | null | undefined): number | null {
  const j = jour || aujourdhui();
  const retenus = (liste ?? []).filter((t) => (!t.date_debut || t.date_debut <= j) && (!t.date_fin || j <= t.date_fin));
  if (!retenus.length) return null;
  return retenus.reduce((a, b) => ((b.date_debut ?? '') > (a.date_debut ?? '') ? b : a)).taux;
}

export interface ChampPaiement {
  champ: 'compte' | 'banque' | 'numero_cheque' | 'carte_derniers_chiffres' | 'reference_paiement';
  libelle: string;
  obligatoire: boolean;
}

export interface FxControle {
  code: string;
  niveau: 'bloquant' | 'attention';
  message: string;
}

export interface FxRefPoint {
  id: string;
  code: string;
  nom: string;
  type_point: string;
  fournisseur_id: string;
  agence_id: string | null;
  contrat_id: string | null;
  reference_fournisseur: string;
  type_facture: string | null;
  profil_id: string | null;
  periodicite: string;
  statut: string;
}

export interface FxReferentiels {
  agences: { id: string; code: string; libelle: string }[];
  fournisseurs: { id: string; code: string; libelle: string }[];
  profils: FxProfil[];
  points: FxRefPoint[];
  contrats: { id: string; reference: string; titre: string; fournisseur_id: string | null }[];
}

export interface FactureRow {
  id: string;
  reference: string;
  numero_fournisseur: string | null;
  fournisseur_id: string | null;
  fournisseur: string | null;
  profil_id: string | null;
  profil: string | null;
  point_facturation_id: string | null;
  point_code: string | null;
  point_nom: string | null;
  type_point: string | null;
  agence_id: string | null;
  agence: string | null;
  contrat_id: string | null;
  type_facture: string | null;
  reference_fournisseur: string | null;
  date_facture: string;
  date_reception: string | null;
  periode_debut: string | null;
  periode_fin: string | null;
  mois: number | null;
  annee: number | null;
  periode_label: string | null;
  date_echeance: string | null;
  jours_echeance: number | null;
  etat_echeance: string | null;
  montant_ht: number | null;
  montant_tva: number | null;
  autres_taxes: number | null;
  remise: number | null;
  montant_ttc: number | null;
  arrieres: number | null;
  reglage: number | null;
  montant_a_payer: number | null;
  montant_paye: number | null;
  reste: number | null;
  devise: string;
  statut: string;
  statut_paiement: string | null;
  statut_affiche: string;
  observation: string | null;
  nb_documents: number | null;
  created_at: string | null;
  updated_at: string | null;
  tranche?: string;
}

export interface FactureLigne {
  id?: string;
  description: string;
  quantite: number | null;
  unite: string | null;
  prix_unitaire: number | null;
  montant: number | null;
  type_ligne: string | null;
}

export interface FxPaiement {
  id: string;
  reference: string;
  date_paiement: string | null;
  montant: number;
  mode_paiement: string | null;
  reference_paiement: string | null;
  compte: string | null;
  banque: string | null;
  numero_cheque: string | null;
  carte_masquee: string | null;
  observation: string | null;
  statut: string;
  justificatif_document_id: string | null;
  created_by: string | null;
  created_at: string | null;
  annule_at: string | null;
}

export interface FxDocument {
  id: string;
  title: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
  doc_type: string | null;
  doc_type_label: string | null;
  reference: string | null;
  date_document: string | null;
  uploaded_by: string | null;
  created_at: string | null;
}

export interface FxEvenement {
  id: string;
  action: string;
  message: string | null;
  user_nom: string | null;
  created_at: string | null;
}

export interface FactureDetail extends FactureRow {
  lignes: FactureLigne[];
  paiements: FxPaiement[];
  documents: FxDocument[];
  historique: FxEvenement[];
  point: {
    id: string;
    code: string;
    nom: string;
    type_point: string;
    reference_fournisseur: string;
    compteur: string | null;
    periodicite: string;
    statut: string;
  } | null;
  contrat: { id: string; reference: string; titre: string; statut: string } | null;
  profil_config: FxProfil | null;
  controles: FxControle[];
  piece_obligatoire: boolean;
  created_by_nom: string | null;
  valide_at: string | null;
  valide_by_nom: string | null;
  motif: string | null;
  annule_at: string | null;
  archived_at: string | null;
  actions: string[];
  modifiable: boolean;
  montants_modifiables: boolean;
  supprimable: boolean;
  capacites: FxCapacites;
}

export interface FacturePage {
  items: FactureRow[];
  total: number;
  page: number;
  page_size: number;
  montant_total: number;
  reste_total: number;
}

export interface PointRow {
  id: string;
  code: string;
  type_point: string;
  type_point_label: string;
  nom: string;
  agence_id: string | null;
  agence: string | null;
  fournisseur_id: string;
  fournisseur: string | null;
  profil_id: string | null;
  contrat_id: string | null;
  reference_fournisseur: string;
  reference_normalisee: string;
  compteur: string | null;
  type_facture: string | null;
  periodicite: string;
  adresse: string | null;
  telephone: string | null;
  date_debut: string | null;
  date_fin: string | null;
  statut: string;
  description: string | null;
  nb_factures: number;
  total_annee: number;
  derniere_periode: number | null;
  derniere_periode_label: string | null;
  created_at: string | null;
}

export interface PointSynthese extends PointRow {
  annee: number;
  mensuel: number[];
  mensuel_n1: number[];
  total_n1: number;
  variation_n1_pct: number | null;
  moyenne_6: number | null;
  reste_a_payer: number;
  factures: FactureRow[];
  contrat: { id: string; reference: string; titre: string } | null;
  historique: FxEvenement[];
  capacites: FxCapacites;
}

export interface Groupe {
  id: string;
  label: string;
  montant: number;
  nb: number;
  reste: number;
  n1?: number;
  variation_pct?: number | null;
  moyenne_mensuelle?: number;
  mensuel?: number[];
  part_pct?: number;
}

export interface FxAlerte {
  type: string;
  niveau: string;
  titre: string;
  message: string;
  facture_id: string | null;
  reference: string | null;
  point_id: string | null;
  point_nom: string | null;
  agence: string | null;
  fournisseur: string | null;
  periode_label: string | null;
  periodes?: { annee: number; mois: number }[];
  montant: number | null;
  date: string | null;
  lien: string;
}

export interface Bucket {
  nb: number;
  montant: number;
}

export interface FxDashboard {
  annee: number;
  mois: number | null;
  periode_label: string | null;
  kpis: {
    nb_factures: number;
    total: number;
    total_reference: number;
    variation_pct: number | null;
    paye: number;
    a_payer: number;
    nb_a_payer: number;
    en_retard: number;
    montant_retard: number;
    a_valider: number;
    sans_piece: number;
    moyenne_mensuelle: number;
    nb_alertes: number;
  };
  monthly_evolution: { mois: number; label: string; montant: number; nb: number; paye: number; n1: number }[];
  by_agency: Groupe[];
  by_pdv: Groupe[];
  by_supplier: Groupe[];
  by_type: Groupe[];
  by_type_point: Groupe[];
  by_status: { code: string; label: string; nb: number; montant: number }[];
  echeances: { retard: Bucket; j7: Bucket; j30: Bucket; plus30: Bucket; sans_echeance: Bucket };
  top_points: Groupe[];
  recentes: FactureRow[];
  alerts: FxAlerte[];
  alerts_count: Record<string, number>;
}

export const STATUT_LABELS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  RECUE: 'Reçue',
  VALIDEE: 'Validée',
  CONTESTEE: 'Contestée',
  ANNULEE: 'Annulée',
  ARCHIVEE: 'Archivée',
  A_PAYER: 'À payer',
  PARTIELLEMENT_PAYEE: 'Partiellement payée',
  PAYEE: 'Payée',
  EN_RETARD: 'En retard',
  PROCHE: 'Échéance proche',
  A_VENIR: 'À venir',
  SOLDEE: 'Soldée',
  ACTIF: 'Actif',
  INACTIF: 'Inactif',
  PAYE: 'Payé',
  ANNULE: 'Annulé',
  NOUVEAU: 'Nouveau',
  EXISTANT: 'Déjà existant',
  DOUBLON_FICHIER: 'Doublon (fichier)',
};

/** Correspondance statut → teinte des badges existants `bea-ct-badge[data-tone]`. */
export const STATUT_TONES: Record<string, string> = {
  BROUILLON: 'BROUILLON',
  RECUE: 'INFO',
  VALIDEE: 'ACTIF',
  CONTESTEE: 'URGENT',
  ANNULEE: 'EXPIRE',
  ARCHIVEE: 'EXPIRE',
  A_PAYER: 'ATTENTION',
  PARTIELLEMENT_PAYEE: 'PARTIELLEMENT_PAYE',
  PAYEE: 'PAYE',
  EN_RETARD: 'EN_RETARD',
  PROCHE: 'ATTENTION',
  A_VENIR: 'A_VENIR',
  SOLDEE: 'PAYE',
  ACTIF: 'ACTIF',
  INACTIF: 'EXPIRE',
  PAYE: 'PAYE',
  ANNULE: 'EXPIRE',
  NOUVEAU: 'ACTIF',
  EXISTANT: 'INFO',
  DOUBLON_FICHIER: 'ATTENTION',
  critique: 'CRITIQUE',
  attention: 'ATTENTION',
  info: 'INFO',
};

export const TYPE_POINT_LABELS: Record<string, string> = {
  AGENCE: 'Agence',
  SIEGE: 'Siège',
  PDV: 'PDV Amanty',
  AUTRE: 'Autre site',
};

export const TYPE_POINT_ICONS: Record<string, string> = {
  AGENCE: 'account_balance',
  SIEGE: 'domain',
  PDV: 'storefront',
  AUTRE: 'place',
};

export const ACTION_LABELS: Record<string, { label: string; icon: string }> = {
  enregistrer: { label: 'Marquer reçue', icon: 'inbox' },
  valider: { label: 'Valider', icon: 'verified' },
  contester: { label: 'Contester', icon: 'report' },
  annuler: { label: 'Annuler', icon: 'block' },
  archiver: { label: 'Archiver', icon: 'inventory_2' },
};

/** Miroir de `TRANSITIONS` / `CAPACITE_ACTION` (backend) pour les menus de ligne ; le backend reste juge. */
const TRANSITIONS_FX: Record<WorkflowFacture, { sources: string[]; cap: keyof FxCapacites }> = {
  enregistrer: { sources: ['BROUILLON'], cap: 'update' },
  valider: { sources: ['RECUE', 'CONTESTEE'], cap: 'validate' },
  contester: { sources: ['RECUE', 'VALIDEE'], cap: 'validate' },
  annuler: { sources: ['BROUILLON', 'RECUE', 'VALIDEE', 'CONTESTEE'], cap: 'delete' },
  archiver: { sources: ['VALIDEE', 'ANNULEE'], cap: 'archive' },
};

export type WorkflowFacture = 'enregistrer' | 'valider' | 'contester' | 'annuler' | 'archiver';

export function actionsFacture(r: FactureRow, cap: Partial<FxCapacites>): WorkflowFacture[] {
  const paye = (r.montant_paye ?? 0) > 0;
  return (Object.keys(TRANSITIONS_FX) as WorkflowFacture[]).filter((a) => {
    const t = TRANSITIONS_FX[a];
    if (!t.sources.includes(r.statut) || !cap[t.cap]) return false;
    if ((a === 'contester' || a === 'annuler') && paye) return false;
    if (a === 'archiver' && r.statut === 'VALIDEE' && r.statut_paiement !== 'PAYEE') return false;
    return true;
  });
}

export function factureModifiable(r: FactureRow, cap: Partial<FxCapacites>): boolean {
  return !!cap.update && !['ANNULEE', 'ARCHIVEE'].includes(r.statut);
}

export function facturePayable(r: FactureRow, cap: Partial<FxCapacites>): boolean {
  return !!cap.payment_create && r.statut === 'VALIDEE' && (r.reste ?? 0) > 0;
}

export function factureSupprimable(r: FactureRow, cap: Partial<FxCapacites>): boolean {
  return !!cap.delete && ['BROUILLON', 'RECUE'].includes(r.statut) && !(r.montant_paye ?? 0);
}

export const ALERTE_LABELS: Record<string, { label: string; icon: string }> = {
  manquante: { label: 'Factures manquantes', icon: 'event_busy' },
  retard: { label: 'Retards', icon: 'running_with_errors' },
  proche: { label: 'Échéances proches', icon: 'alarm' },
  hausse: { label: 'Hausses importantes', icon: 'trending_up' },
  doublon: { label: 'Doublons', icon: 'content_copy' },
};

export const VUES: { code: string; label: string; icon: string }[] = [
  { code: 'toutes', label: 'Toutes', icon: 'receipt_long' },
  { code: 'agences', label: 'Agences & sièges', icon: 'account_balance' },
  { code: 'pdv', label: 'PDV Amanty', icon: 'storefront' },
  { code: 'a_valider', label: 'À valider', icon: 'pending_actions' },
  { code: 'a_payer', label: 'À payer', icon: 'payments' },
  { code: 'payees', label: 'Payées', icon: 'task_alt' },
  { code: 'retard', label: 'En retard', icon: 'running_with_errors' },
  { code: 'historique', label: 'Historique', icon: 'history' },
];

export const MOIS_COURTS = ['Janv.', 'Févr.', 'Mars', 'Avr.', 'Mai', 'Juin', 'Juil.', 'Août', 'Sept.', 'Oct.', 'Nov.', 'Déc.'];
export const MOIS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

/** Libellés par défaut (miroir de `CHAMPS_PROFIL` backend) ; un profil peut les renommer. */
export const LIBELLES_CHAMPS: Record<ChampProfil, string> = {
  numero_fournisseur: 'N° facture',
  reference_fournisseur: 'Référence (compteur / abonnement)',
  periode: 'Période facturée',
  periode_debut: 'Début de période',
  periode_fin: 'Fin de période',
  montant_ht: 'Montant HT',
  montant_tva: 'TVA',
  autres_taxes: 'Autres taxes / redevances',
  remise: 'Remise',
  montant_ttc: 'Montant TTC',
  arrieres: 'Arriérés',
  reglage: 'Réglage',
  montant_a_payer: 'Total à payer',
  date_echeance: 'Échéance',
};

/** État d'un champ pour un profil ; sans profil, tout est facultatif (aucune règle supposée). */
export function etatChamp(profil: FxProfil | null | undefined, champ: ChampProfil): EtatChamp {
  return profil?.champs?.[champ] ?? 'facultatif';
}

/** Détail lisible d'un paiement selon son moyen (compte, chèque, carte masquée…). */
export function detailPaiement(p: Pick<FxPaiement, 'compte' | 'banque' | 'numero_cheque' | 'carte_masquee' | 'reference_paiement'>): string {
  return [
    p.carte_masquee ? `Carte ${p.carte_masquee}` : null,
    p.numero_cheque ? `Chèque n° ${p.numero_cheque}` : null,
    p.compte,
    p.banque,
    p.reference_paiement,
  ]
    .filter(Boolean)
    .join(' · ');
}

export function fxStatut(code: string | null | undefined): string {
  return (code && STATUT_LABELS[code]) || code || '—';
}

export function fxTone(code: string | null | undefined): string {
  return (code && STATUT_TONES[code]) || 'INFO';
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${v > 0 ? '+' : ''}${v.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;
}

export function annees(): number[] {
  const y = new Date().getFullYear();
  return [y + 1, y, y - 1, y - 2, y - 3, y - 4];
}

export function tailleFichier(octets: number): string {
  if (octets < 1024) return `${octets} o`;
  if (octets < 1024 * 1024) return `${Math.round(octets / 1024)} Ko`;
  return `${(octets / 1024 / 1024).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} Mo`;
}

export interface FxFournisseurStat {
  cle: string;
  profil_id: string | null;
  fournisseur_id: string | null;
  profil: FxProfil | null;
  libelle: string;
  fournisseur: string | null;
  fournisseur_code: string | null;
  fournisseur_actif: boolean;
  telephone: string | null;
  email: string | null;
  nb: number;
  montant: number;
  mensuel: number[];
  reste: number;
  nb_ouvertes: number;
  a_valider: number;
  points: number;
  derniere_facture: string | null;
  part_pct: number;
  actif: boolean;
}

export interface FxFournisseursStats {
  annee: number;
  items: FxFournisseurStat[];
  total: number;
  reste: number;
  nb_profils: number;
}

export interface FxControleRow extends FactureRow {
  controles: FxControle[];
  niveau_controle: 'bloquant' | 'attention' | 'ok';
  nb_bloquants: number;
  nb_attention: number;
}

export interface FxControles {
  items: FxControleRow[];
  compteurs: { a_valider: number; bloquant: number; attention: number; pret: number };
}

export interface FxLotResultat {
  resultats: { id: string; ok: boolean; reference?: string; message?: string }[];
  succes: number;
  echecs: number;
}

export interface FxJournalItem {
  id: string;
  entite: 'facture' | 'point_facturation';
  entity_id: string;
  action: string;
  action_label: string;
  message: string | null;
  user_nom: string | null;
  reference: string | null;
  created_at: string;
}

export interface FxJournal {
  items: FxJournalItem[];
  total: number;
  page: number;
  size: number;
}

/** Retire les valeurs vides avant envoi en query string. */
export function nettoyer(params: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '' && v !== false) out[k] = String(v);
  }
  return out;
}
