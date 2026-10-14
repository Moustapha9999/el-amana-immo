import { WritableSignal } from '@angular/core';
import { RunOptions, RunWithReasonOptions } from '../../core/feedback/feedback.service';
import { Dossier, SuppressionResultat } from '../reclamations.models';

/** Suppression définitive, quel que soit le statut : confirmation explicite, irréversible. */
export function optionsSuppression(reference: string, busy: WritableSignal<boolean>): RunOptions<SuppressionResultat> {
  return {
    confirm: {
      title: `Supprimer la réclamation ${reference}`,
      message: 'Êtes-vous sûr de vouloir supprimer définitivement cette réclamation ? Cette action est irréversible.',
      hint: 'Le dossier, ses opérations, ses pièces jointes, ses fiches de traitement et son historique sont effacés de la base. Seule la trace de la suppression reste dans le journal d’audit.',
      confirmLabel: 'Supprimer définitivement',
      cancelLabel: 'Annuler',
      tone: 'danger',
      icon: 'delete_forever',
    },
    busy,
    loading: 'Suppression…',
    success: (r) => ({
      title: 'Réclamation supprimée définitivement',
      details: [
        { label: 'Référence', value: r.reference },
        { label: 'Opérations supprimées', value: String(r.operations_supprimees) },
        { label: 'Pièces supprimées', value: String(r.documents_supprimes) },
      ],
    }),
    errorTitle: 'Suppression refusée',
    retry: false,
  };
}

export function optionsRestauration(reference: string, busy: WritableSignal<boolean>): RunWithReasonOptions<Dossier> {
  return {
    reason: {
      title: `Restaurer la réclamation ${reference}`,
      message: 'Le dossier revient dans les listes avec son statut, ses opérations, ses pièces et son historique d’avant la suppression.',
      confirmLabel: 'Restaurer',
      cancelLabel: 'Retour',
      tone: 'primary',
      icon: 'restore_from_trash',
      reasonLabel: 'Motif de la restauration',
      maxLength: 4000,
    },
    busy,
    loading: 'Restauration…',
    success: (d) => ({ title: 'Réclamation restaurée', details: [
      { label: 'Référence', value: d.reference }, { label: 'Statut', value: d.statut_libelle },
    ] }),
    errorTitle: 'Restauration refusée',
    retry: false,
  };
}
