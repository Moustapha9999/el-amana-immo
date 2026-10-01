import { UserProfile } from '../core/services/auth.service';

export interface NoteHist {
  id: string;
  action: string;
  from_statut: string | null;
  to_statut: string | null;
  user_nom: string | null;
  commentaire: string | null;
  created_at: string | null;
}

export interface NoteLigne {
  id?: string;
  date_depense: string;
  description: string;
  motif: string | null;
  montant: number;
  mode_reglement: string | null;
  categorie_id: string | null;
  categorie_libelle_snapshot: string | null;
}

export interface Note {
  id: string;
  reference: string;
  date_demande: string;
  agence_id: string | null;
  agence_libelle_snapshot: string | null;
  demandeur_id: string | null;
  demandeur_nom: string | null;
  departement: string | null;
  fonction: string | null;
  objet: string | null;
  periode_debut: string | null;
  periode_fin: string | null;
  devise: string;
  statut: string;
  statut_paiement?: string;
  total_mru: number;
  montant_paye: number;
  motif_rejet: string | null;
  motif_correction: string | null;
  observation: string | null;
  pdf_version: number;
  lignes: NoteLigne[];
  historique: NoteHist[];
}

export const NOTE_STATUTS = [
  'BROUILLON',
  'SOUMIS',
  'EN_CONTROLE',
  'CORRECTION_REQUISE',
  'VISA_MG',
  'VISA_DR',
  'VALIDEE',
  'MISE_EN_PAIEMENT',
  'PARTIELLEMENT_PAYEE',
  'PAYEE',
  'CLOTUREE',
  'ARCHIVEE',
  'REJETEE',
  'ANNULEE',
] as const;

const STATUT_LABELS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  SOUMIS: 'Soumise',
  EN_CONTROLE: 'En contrôle',
  CORRECTION_REQUISE: 'Correction requise',
  VISA_MG: 'Visa MG',
  VISA_DR: 'Visa DR',
  VALIDEE: 'Validée',
  MISE_EN_PAIEMENT: 'Mise en paiement',
  PARTIELLEMENT_PAYEE: 'Partiellement payée',
  PAYEE: 'Payée',
  CLOTUREE: 'Clôturée',
  ARCHIVEE: 'Archivée',
  REJETEE: 'Rejetée',
  ANNULEE: 'Annulée',
};

export function noteStatutLabel(s: string | null | undefined): string {
  if (!s) return '—';
  return STATUT_LABELS[s] || s;
}

/** Tonalité visuelle du badge (`data-tone` de `.bea-nf-badge`). */
export function noteStatutTone(s: string | null | undefined): string {
  switch (s) {
    case 'BROUILLON':
      return 'draft';
    case 'SOUMIS':
    case 'EN_CONTROLE':
    case 'VISA_MG':
    case 'VISA_DR':
      return 'progress';
    case 'CORRECTION_REQUISE':
    case 'MISE_EN_PAIEMENT':
    case 'PARTIELLEMENT_PAYEE':
      return 'warn';
    case 'VALIDEE':
    case 'PAYEE':
    case 'CLOTUREE':
      return 'ok';
    case 'REJETEE':
    case 'ANNULEE':
      return 'danger';
    default:
      return 'muted';
  }
}

const MUTATION_LOCKED = new Set(['MISE_EN_PAIEMENT', 'PARTIELLEMENT_PAYEE', 'PAYEE', 'CLOTUREE', 'ARCHIVEE']);

const SUPERVISE_CODES = [
  'mg.notes.control',
  'mg.notes.approve',
  'mg.notes.payment',
  'mg.notes.archive',
  'mg.notes.reject',
  'mg.notes.settings',
];

function hasCode(user: UserProfile | null, code: string): boolean {
  if (!user) return false;
  if (user.is_superuser) return true;
  return (user.permission_codes ?? []).includes(code);
}

export function canCreateNote(user: UserProfile | null): boolean {
  return hasCode(user, 'mg.notes.create');
}

export function canSuperviseNotes(user: UserProfile | null): boolean {
  return !!user && (user.is_superuser || SUPERVISE_CODES.some((c) => (user.permission_codes ?? []).includes(c)));
}

export function canEditNote(user: UserProfile | null, note: Pick<Note, 'statut'>): boolean {
  if (!canCreateNote(user) || MUTATION_LOCKED.has(note.statut)) return false;
  if (canSuperviseNotes(user)) return true;
  return note.statut === 'BROUILLON' || note.statut === 'CORRECTION_REQUISE';
}

/** Administrateur du module : suppression autorisée quel que soit le statut. */
export function isNotesAdmin(user: UserProfile | null): boolean {
  return hasCode(user, 'mg.notes.settings');
}

export function canDeleteNote(user: UserProfile | null, note: Pick<Note, 'statut' | 'demandeur_id'>): boolean {
  if (isNotesAdmin(user)) return true;
  if (!user || !canCreateNote(user) || MUTATION_LOCKED.has(note.statut)) return false;
  if (canSuperviseNotes(user)) return true;
  return note.statut === 'BROUILLON' && note.demandeur_id === user.id;
}

export function editNoteHint(user: UserProfile | null, note: Pick<Note, 'statut'>): string {
  if (canEditNote(user, note)) return 'Modifier';
  if (MUTATION_LOCKED.has(note.statut)) return 'Modification impossible après la mise en paiement';
  return 'Modification réservée à l’administrateur';
}

export function deleteNoteHint(user: UserProfile | null, note: Pick<Note, 'statut' | 'demandeur_id'>): string {
  if (canDeleteNote(user, note)) return 'Supprimer';
  if (MUTATION_LOCKED.has(note.statut)) return 'Suppression après mise en paiement réservée à l’administrateur';
  return 'Suppression réservée à l’administrateur';
}

/** Registre concerné : lu sur la note, jamais recopié dans le paiement. */
export interface NoteRegistre {
  id: string;
  reference: string;
  date_demande: string;
  beneficiaire: string | null;
  departement: string | null;
  fonction: string | null;
  motif: string | null;
  intitule: string | null;
  statut: string;
  statut_paiement: string;
  montant_initial: number;
  montant_paye: number;
  solde: number;
  devise: string;
  nb_paiements: number;
}

export interface NotePaiement {
  id: string;
  numero: string;
  note_id: string;
  date_paiement: string;
  montant: number;
  mode_paiement: string;
  reference: string | null;
  numero_cheque: string | null;
  banque: string | null;
  compte: string | null;
  observation: string | null;
  statut: 'VALIDE' | 'ANNULE';
  motif_annulation: string | null;
  annule_at: string | null;
  annule_par_nom: string | null;
  created_by_nom: string | null;
  updated_by_nom: string | null;
  created_at: string | null;
  updated_at: string | null;
  registre: NoteRegistre;
}

export const MODES_PAIEMENT = ['Espèces', 'Virement', 'Chèque', 'Carte', 'Amanty'] as const;

const STATUT_PAIEMENT_LABELS: Record<string, string> = {
  NON_PAYE: 'Non payé',
  PARTIEL: 'Partiellement payé',
  PAYE: 'Payé',
  ANNULE: 'Annulé',
};

export function statutPaiementLabel(s: string | null | undefined): string {
  return (s && STATUT_PAIEMENT_LABELS[s]) || '—';
}

export function statutPaiementTone(s: string | null | undefined): string {
  switch (s) {
    case 'PAYE':
      return 'ok';
    case 'PARTIEL':
      return 'warn';
    case 'ANNULE':
      return 'danger';
    default:
      return 'draft';
  }
}

export function paiementStatutLabel(s: string): string {
  return s === 'ANNULE' ? 'Annulé' : 'Validé';
}

export function paiementStatutTone(s: string): string {
  return s === 'ANNULE' ? 'danger' : 'ok';
}

/** Référence affichée selon le mode : n° de chèque, sinon référence transaction / virement. */
export function paiementReference(p: Pick<NotePaiement, 'mode_paiement' | 'reference' | 'numero_cheque'>): string {
  if (p.mode_paiement === 'Chèque') return p.numero_cheque ? `Chèque n° ${p.numero_cheque}` : '—';
  return p.reference || '—';
}

const NOTE_FIGEE = new Set(['CLOTUREE', 'ARCHIVEE']);

export function canPayNotes(user: UserProfile | null): boolean {
  return hasCode(user, 'mg.notes.payment');
}

/** Note encore payable : validée ou en paiement, avec un solde positif. */
export function isNotePayable(note: { statut: string; total_mru: number; montant_paye: number }): boolean {
  return (
    ['VALIDEE', 'MISE_EN_PAIEMENT', 'PARTIELLEMENT_PAYEE'].includes(note.statut) &&
    Number(note.total_mru) - Number(note.montant_paye || 0) > 0.001
  );
}

export function canEditPaiement(user: UserProfile | null, p: NotePaiement): boolean {
  return canPayNotes(user) && p.statut === 'VALIDE' && !NOTE_FIGEE.has(p.registre.statut);
}

export function canDeletePaiement(user: UserProfile | null, p: NotePaiement): boolean {
  return isNotesAdmin(user) && !NOTE_FIGEE.has(p.registre.statut);
}

export function paiementLockHint(p: NotePaiement): string | null {
  if (NOTE_FIGEE.has(p.registre.statut)) return 'Note clôturée ou archivée : paiement figé';
  if (p.statut === 'ANNULE') return 'Paiement annulé';
  return null;
}

export function formatNoteApiError(err: unknown, fallback: string): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (typeof d === 'string') return d;
        if (d && typeof d === 'object' && 'msg' in d) return String((d as { msg: string }).msg);
        return '';
      })
      .filter(Boolean);
    if (msgs.length) return msgs.join(' · ');
  }
  return fallback;
}
