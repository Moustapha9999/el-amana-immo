import { signal } from '@angular/core';
import type { ApiService } from '../core/services/api.service';
import { montantArrondi, montantLigne } from '../shared/montant.pipe';

/**
 * Circuit Achat → Réception → Facture → Paiement, côté affichage.
 * Le backend (mg_achats_regles.py) fait foi : ces helpers ne servent qu'à
 * masquer les actions impossibles et à prévisualiser les montants.
 */

export const BC_STATUT_LABELS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  SOUMIS: 'Soumis',
  VALIDE: 'Validé',
  ENVOYE: 'Envoyé',
  PARTIEL: 'Reçu partiel',
  RECU: 'Reçu',
  CLOTURE: 'Clôturé',
  REJETEE: 'Rejeté',
  ANNULEE: 'Annulé',
};

export const FACTURE_STATUT_LABELS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  RECUE: 'Reçue',
  ANOMALIE: 'Anomalie',
  VALIDEE: 'Validée',
  A_PAYER: 'À payer',
  PARTIELLEMENT_PAYEE: 'Partiellement payée',
  PAYEE: 'Payée',
  ANNULEE: 'Annulée',
};

const BC_FIGES = ['CLOTURE', 'ANNULEE', 'REJETEE'];

export type BcAction = 'soumettre' | 'retour_brouillon' | 'valider' | 'rejeter' | 'envoyer' | 'cloturer';

export interface BcActionDef {
  action: BcAction;
  label: string;
  icon: string;
  /** Motif obligatoire (UiDialogService.confirmWithReason). */
  motif?: boolean;
  ghost?: boolean;
}

export const BC_ACTIONS: Record<string, BcActionDef[]> = {
  BROUILLON: [{ action: 'soumettre', label: 'Soumettre', icon: 'send' }],
  SOUMIS: [
    { action: 'valider', label: 'Valider', icon: 'verified' },
    { action: 'retour_brouillon', label: 'Retour brouillon', icon: 'undo', ghost: true },
    { action: 'rejeter', label: 'Rejeter', icon: 'block', motif: true, ghost: true },
  ],
  VALIDE: [{ action: 'envoyer', label: 'Envoyer au fournisseur', icon: 'outgoing_mail' }],
  RECU: [{ action: 'cloturer', label: 'Clôturer', icon: 'task_alt' }],
};

/** Hors brouillon : seuls ces champs restent modifiables (miroir de BC_CHAMPS_LOGISTIQUES). */
export const BC_CHAMPS_LOGISTIQUES = [
  'date_livraison_prevue',
  'agence_livraison_id',
  'adresse_livraison',
  'agence_facturation_id',
  'adresse_facturation',
  'acheteur_nom',
  'acheteur_tel',
  'conditions',
  'incoterm',
  'conditions_paiement',
  'moyen_paiement_liste',
  'moyen_paiement_autre',
  'ref_paiement',
  'montant_paiement',
  'observation',
];

/** Moyens de paiement proposés dans le BC et repris dans le suivi des paiements. */
export const MOYENS_PAIEMENT = ['Amanty', 'Virement', 'Cash'] as const;
export const MOYEN_AUTRE = '__autre__';

/** Anciennes valeurs du suivi des paiements (avant alignement sur le BC). */
const MOYENS_HERITES: Record<string, string> = { VIREMENT: 'Virement', ESPECES: 'Cash', CHEQUE: 'Chèque', AUTRE: '' };

/** Valeur stockée → (choix de la liste, texte « Autre »). */
export function decomposerMoyen(valeur: string | null | undefined): { liste: string; autre: string } {
  const v = (valeur ?? '').trim();
  const norm = v in MOYENS_HERITES ? MOYENS_HERITES[v] : v;
  if (!norm) return { liste: '', autre: '' };
  if ((MOYENS_PAIEMENT as readonly string[]).includes(norm)) return { liste: norm, autre: '' };
  return { liste: MOYEN_AUTRE, autre: norm };
}

/** ACHATS_MODE_TEST=1 côté backend : verrous de statut levés, suppression en cascade. */
export const modeTestAchats = signal(false);
let modeTestCharge = false;

export function chargerModeTest(api: ApiService): void {
  if (modeTestCharge) return;
  modeTestCharge = true;
  api.get<{ mode_test: boolean }>('/mg/achats/config').subscribe({
    next: (r) => modeTestAchats.set(!!r.mode_test),
    error: () => (modeTestCharge = false),
  });
}

export const bcEditable = (statut: string | null | undefined): boolean =>
  !!statut && (modeTestAchats() || !BC_FIGES.includes(statut));
export const bcLignesEditables = (statut: string | null | undefined): boolean =>
  !statut || statut === 'BROUILLON' || modeTestAchats();
export const bcAnnulable = (statut: string): boolean => ['BROUILLON', 'SOUMIS', 'VALIDE', 'ENVOYE'].includes(statut);
export const bcSupprimable = (statut: string): boolean => statut === 'BROUILLON' || modeTestAchats();
export const bcRecevable = (statut: string): boolean => ['VALIDE', 'ENVOYE', 'PARTIEL'].includes(statut);
export const bcFacturable = (statut: string): boolean => ['VALIDE', 'ENVOYE', 'PARTIEL', 'RECU', 'CLOTURE'].includes(statut);

export const factureModifiable = (statut: string): boolean =>
  ['BROUILLON', 'RECUE', 'ANOMALIE'].includes(statut) || (modeTestAchats() && statut !== 'ANNULEE');
export const facturePayable = (statut: string): boolean => ['VALIDEE', 'A_PAYER', 'PARTIELLEMENT_PAYEE'].includes(statut);

export interface Montants {
  ht: number;
  tva: number;
  ttc: number;
}

/** HT = qté × PU × (1 − remise) ; TVA arrondie par ligne ; TTC = HT + TVA. */
export function calculerLigne(
  quantite: number | string | null | undefined,
  prixUnitaire: number | string | null | undefined,
  tauxTva: number | string | null | undefined = 0,
  remisePct: number | string | null | undefined = 0,
): Montants {
  const brut = montantLigne(quantite, prixUnitaire);
  const ht = montantArrondi(brut - (brut * (Number(remisePct) || 0)) / 100);
  const tva = montantArrondi((ht * (Number(tauxTva) || 0)) / 100);
  return { ht, tva, ttc: montantArrondi(ht + tva) };
}

export function totaliser(lignes: Montants[]): Montants {
  const ht = montantArrondi(lignes.reduce((s, l) => s + l.ht, 0));
  const tva = montantArrondi(lignes.reduce((s, l) => s + l.tva, 0));
  return { ht, tva, ttc: montantArrondi(ht + tva) };
}
