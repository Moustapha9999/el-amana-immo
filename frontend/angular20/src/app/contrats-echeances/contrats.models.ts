/** Types et libellés partagés du module Contrats & échéances. Les montants Decimal arrivent en chaîne. */

export type Num = number | string | null;

export interface Contrat {
  id: string;
  reference: string;
  titre: string;
  numero_contrat: string | null;
  description: string | null;
  type_contrat: string;
  fournisseur_id: string | null;
  fournisseur_snapshot: string | null;
  agence_id: string | null;
  agence_libelle_snapshot: string | null;
  responsable_id: string | null;
  responsable_nom: string | null;
  date_signature: string | null;
  date_debut: string;
  date_fin: string | null;
  prochain_echeance: string | null;
  montant: Num;
  montant_ht: Num;
  taux_tva: Num;
  devise: string;
  periodicite: string;
  mode_paiement: string | null;
  ref_paiement: string | null;
  alerte_jours: number;
  observation: string | null;
  statut: string;
  etat: string;
  jours_restants: number | null;
  date_preavis: string | null;
  reconduction: string;
  preavis_jours: number | null;
  version: number;
  contrat_precedent_id: string | null;
  echeances?: Echeance[];
  paiements?: Paiement[];
  historique?: Hist[];
  avenants?: Avenant[];
}

export interface Echeance {
  id: string;
  type_echeance: string;
  date_prevue: string;
  date_reelle?: string | null;
  montant: Num;
  montant_paye: Num;
  statut: string;
  commentaire: string | null;
}

export interface Paiement {
  id: string;
  echeance_id: string | null;
  reference: string | null;
  date_prevue: string;
  date_reelle: string | null;
  montant_prevu: Num;
  montant_paye: Num;
  statut: string;
  mode: string | null;
  commentaire: string | null;
}

export interface Hist {
  id: string;
  action: string;
  from_statut: string | null;
  to_statut: string | null;
  user_nom: string | null;
  commentaire: string | null;
  created_at: string;
}

export interface Avenant {
  id: string;
  numero: number;
  type_avenant: string;
  objet: string;
  date_effet: string;
  montant_ht_avant: Num;
  montant_ht_apres: Num;
  montant_ttc_avant: Num;
  montant_ttc_apres: Num;
  date_fin_avant: string | null;
  date_fin_apres: string | null;
  clauses: string | null;
  version_contrat: number;
  user_nom: string | null;
  created_at: string;
}

export interface EcheanceRow {
  id: string;
  contrat_id: string;
  reference: string;
  titre: string;
  type_echeance: string;
  date_prevue: string;
  date_reelle: string | null;
  jours: number;
  statut: string;
  commentaire: string | null;
  montant: number | null;
  montant_paye: number;
  reste: number;
  devise: string;
  agence: string | null;
  fournisseur: string | null;
  contrat_statut: string;
  responsable: string | null;
}

export interface PaiementRow {
  id: string;
  contrat_id: string;
  reference: string;
  titre: string;
  contrat_statut: string;
  paiement_ref: string | null;
  echeance_id: string | null;
  echeance_date: string | null;
  date_prevue: string;
  date_reelle: string | null;
  montant_prevu: number;
  montant_paye: number;
  reste: number;
  ecart: number;
  statut: string;
  mode: string | null;
  commentaire: string | null;
  devise: string;
  fournisseur: string | null;
  agence: string | null;
}

export interface Alerte {
  type: string;
  contrat_id: string;
  reference: string;
  titre: string;
  fournisseur: string | null;
  agence: string | null;
  responsable: string | null;
  echeance: string | null;
  jours: number | null;
  niveau: string;
  statut: string;
  message: string;
}

export interface ARenouveler {
  id: string;
  reference: string;
  titre: string;
  fournisseur: string | null;
  agence: string | null;
  date_fin: string;
  date_preavis: string | null;
  jours: number;
  reconduction: string;
  montant: number;
  devise: string;
  statut: string;
  etat: string;
}

export interface RefItem {
  id: string;
  libelle?: string;
  raison_sociale?: string;
  code?: string;
  full_name?: string;
}

export interface ContratsConfig {
  taux_tva: number;
  devise: string;
  devises: string[];
  periodicites: string[];
  modes_paiement: string[];
  alerte_jours: number[];
  echeance_due_jours: number;
  ged_taille_max_mo: number;
  types_document: { code: string; libelle: string }[];
  capacites: { create: boolean; manage: boolean; validate: boolean; settings: boolean; export: boolean; ged_write: boolean };
  agence_scope: { id: string; libelle: string | null } | null;
}

export const STATUT_LABELS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  EN_PREPARATION: 'En préparation',
  EN_VALIDATION: 'En validation',
  ACTIF: 'Actif',
  ECHEANCE_30: 'Échéance ≤ 30 j',
  DATE_DEPASSEE: 'Date dépassée, encore actif',
  SUSPENDU: 'Suspendu',
  EXPIRE: 'Expiré',
  ARCHIVE: 'Archivé',
  REJETE: 'Rejeté',
  ANNULE: 'Annulé',
  A_VENIR: 'À venir',
  DUE: 'Due (à payer)',
  PAYEE: 'Payée',
  FAITE: 'Réalisée',
  ANNULEE: 'Annulée',
  EN_RETARD: 'En retard',
  PAYE: 'Payé',
  PARTIELLEMENT_PAYE: 'Partiellement payé',
  CRITIQUE: 'Critique',
  URGENT: 'Urgent',
  ATTENTION: 'Attention',
  INFO: 'Info',
};

export const STATUTS_CONTRAT = ['BROUILLON', 'EN_VALIDATION', 'ACTIF', 'SUSPENDU', 'EXPIRE', 'REJETE', 'ARCHIVE', 'ANNULE'];

export const ETATS_FILTRE = [
  { code: 'ECHEANCE_30', label: 'Échéance ≤ 30 jours' },
  { code: 'DATE_DEPASSEE', label: 'Date dépassée, encore actif' },
];

export const TYPES_ECHEANCE = [
  { code: 'PAIEMENT', label: 'Paiement' },
  { code: 'REVISION', label: 'Révision de prix' },
  { code: 'PREAVIS', label: 'Préavis de résiliation' },
  { code: 'RENOUVELLEMENT', label: 'Renouvellement' },
  { code: 'FIN_CONTRAT', label: 'Fin de contrat' },
  { code: 'AUTRE', label: 'Autre' },
] as const;

export const PERIODICITE_LABELS: Record<string, string> = {
  MENSUEL: 'Mensuel',
  TRIMESTRIEL: 'Trimestriel',
  SEMESTRIEL: 'Semestriel',
  ANNUEL: 'Annuel',
  UNIQUE: 'Paiement unique',
};

export const RECONDUCTION_LABELS: Record<string, string> = {
  AUCUNE: 'Aucune (fin ferme)',
  TACITE: 'Reconduction tacite',
  EXPRESSE: 'Reconduction expresse',
};

export const TYPE_AVENANT_LABELS: Record<string, string> = {
  MONTANT: 'Modification du montant',
  DUREE: 'Extension de durée',
  CLAUSES: 'Mise à jour des clauses',
  MIXTE: 'Avenant mixte',
  RECONDUCTION: 'Reconduction tacite',
};

export const ALERTE_TYPE_LABELS: Record<string, string> = {
  expiration: 'Fin de contrat',
  preavis: 'Préavis',
  paiement: 'Paiement',
  echeance: 'Échéance',
  sans_responsable: 'Sans responsable',
  sans_fournisseur: 'Sans fournisseur',
};

export const ACTION_LABELS: Record<string, string> = {
  creer: 'Création',
  modifier: 'Modification',
  supprimer: 'Suppression',
  soumettre: 'Soumis pour validation',
  valider: 'Validé',
  rejeter: 'Rejeté',
  suspendre: 'Suspendu',
  reprendre: 'Repris',
  expirer: 'Marqué expiré',
  annuler: 'Annulé',
  archiver: 'Archivé',
  renouveler: 'Renouvellement (expresse)',
  reconduire: 'Reconduction tacite',
  avenant: 'Avenant',
  echeancier: 'Échéancier',
  echeance: 'Échéance ajoutée',
  echeance_modifier: 'Échéance modifiée',
  echeance_supprimer: 'Échéance supprimée',
  paiement: 'Paiement enregistré',
  paiement_modifier: 'Paiement modifié',
  paiement_supprimer: 'Paiement supprimé',
};

export function num(v: Num | undefined): number {
  if (v === null || v === undefined || v === '') return 0;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function statutLabel(code: string | null | undefined): string {
  return (code && STATUT_LABELS[code]) || code || '—';
}

export function typeEcheanceLabel(code: string): string {
  return TYPES_ECHEANCE.find((t) => t.code === code)?.label ?? code;
}

export function dateFr(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

export function dateHeureFr(iso: string): string {
  const dt = new Date(iso);
  return Number.isNaN(dt.getTime()) ? iso : dt.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

export function joursLabel(jours: number | null | undefined): string {
  if (jours === null || jours === undefined) return '';
  if (jours === 0) return 'Aujourd’hui';
  return jours > 0 ? `Dans ${jours} j` : `Retard ${-jours} j`;
}

export function aujourdhui(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function telechargerBlob(blob: Blob, nom: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nom;
  a.click();
  URL.revokeObjectURL(url);
}
