import { WritableSignal } from '@angular/core';
import { RunWithReasonOptions } from '../../core/feedback/feedback.service';
import { Dossier, SuppressionResultat, dateFr } from '../reclamations.models';

/** Suppression = mise à la corbeille : motif obligatoire et référence recopiée (confirmation explicite). */
export function optionsSuppression(reference: string, busy: WritableSignal<boolean>): RunWithReasonOptions<SuppressionResultat> {
  return {
    reason: {
      title: `Supprimer la réclamation ${reference}`,
      message: 'Le dossier disparaîtra des listes, indicateurs et exports. Ses opérations bancaires (simples références, rien n’est modifié dans ORION), ses pièces jointes et son historique sont conservés.',
      hint: 'Un profil habilité peut le restaurer depuis la corbeille. Les dossiers clôturés, rejetés, archivés ou portant une réponse au client ne se suppriment pas.',
      confirmLabel: 'Supprimer',
      cancelLabel: 'Retour',
      tone: 'danger',
      icon: 'delete',
      reasonLabel: 'Motif de la suppression',
      reasonPlaceholder: 'Saisie en double, dossier de test, erreur de saisie…',
      maxLength: 4000,
      confirmPhrase: reference,
    },
    busy,
    loading: 'Suppression…',
    success: (r) => ({
      title: 'Réclamation supprimée',
      details: [
        { label: 'Référence', value: r.reference },
        { label: 'Supprimée le', value: dateFr(r.supprimee_le, true) },
        { label: 'Opérations conservées', value: String(r.operations_conservees) },
        { label: 'Pièces conservées', value: String(r.documents_conserves) },
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
