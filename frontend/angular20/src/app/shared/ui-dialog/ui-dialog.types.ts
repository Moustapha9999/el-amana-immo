export type UiDialogTone = 'primary' | 'danger' | 'success' | 'warn' | 'info';

export type UiDialogAction =
  | 'ajout'
  | 'modification'
  | 'suppression'
  | 'enregistrement'
  | 'validation'
  | 'comptabilisation'
  | 'cloture'
  | 'ouverture'
  | 'soumission'
  | 'rejet'
  | 'annulation'
  | 'archivage'
  | 'restauration'
  | 'suspension'
  | 'reprise'
  | 'renouvellement'
  | 'expiration'
  | 'depart';

export interface UiConfirmData {
  title: string;
  message: string;
  /** Précision affichée sous le message (conséquence de l'action). */
  hint?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: UiDialogTone;
  icon?: string;
}

export interface UiReasonData extends UiConfirmData {
  reasonLabel?: string;
  reasonPlaceholder?: string;
  /** Défaut : true. */
  required?: boolean;
  maxLength?: number;
}

export interface UiFeedbackData {
  title: string;
  message: string;
  tone?: UiDialogTone;
  icon?: string;
  okLabel?: string;
}

export const UI_DIALOG_PRESETS: Record<
  UiDialogAction,
  { title: string; confirmLabel: string; successTitle: string; icon: string; tone: UiDialogTone }
> = {
  ajout: {
    title: 'Confirmer l’ajout',
    confirmLabel: 'Ajouter',
    successTitle: 'Ajout effectué',
    icon: 'add_circle',
    tone: 'primary',
  },
  modification: {
    title: 'Confirmer la modification',
    confirmLabel: 'Modifier',
    successTitle: 'Modification enregistrée',
    icon: 'edit',
    tone: 'primary',
  },
  suppression: {
    title: 'Confirmer la suppression',
    confirmLabel: 'Supprimer',
    successTitle: 'Suppression effectuée',
    icon: 'delete',
    tone: 'danger',
  },
  enregistrement: {
    title: 'Confirmer l’enregistrement',
    confirmLabel: 'Enregistrer',
    successTitle: 'Enregistrement effectué',
    icon: 'save',
    tone: 'primary',
  },
  validation: {
    title: 'Confirmer la validation',
    confirmLabel: 'Valider',
    successTitle: 'Validation effectuée',
    icon: 'check_circle',
    tone: 'success',
  },
  comptabilisation: {
    title: 'Confirmer la comptabilisation',
    confirmLabel: 'Comptabiliser',
    successTitle: 'Comptabilisation effectuée',
    icon: 'account_balance',
    tone: 'success',
  },
  cloture: {
    title: 'Confirmer la clôture',
    confirmLabel: 'Clôturer',
    successTitle: 'Clôture effectuée',
    icon: 'lock',
    tone: 'warn',
  },
  ouverture: {
    title: 'Confirmer l’ouverture',
    confirmLabel: 'Ouvrir',
    successTitle: 'Ouverture effectuée',
    icon: 'lock_open',
    tone: 'primary',
  },
  soumission: {
    title: 'Confirmer la soumission',
    confirmLabel: 'Soumettre',
    successTitle: 'Soumission effectuée',
    icon: 'send',
    tone: 'primary',
  },
  rejet: {
    title: 'Rejeter',
    confirmLabel: 'Rejeter',
    successTitle: 'Rejet enregistré',
    icon: 'block',
    tone: 'danger',
  },
  annulation: {
    title: 'Confirmer l’annulation',
    confirmLabel: 'Annuler l’élément',
    successTitle: 'Annulation effectuée',
    icon: 'cancel',
    tone: 'danger',
  },
  archivage: {
    title: 'Confirmer l’archivage',
    confirmLabel: 'Archiver',
    successTitle: 'Archivage effectué',
    icon: 'inventory_2',
    tone: 'warn',
  },
  restauration: {
    title: 'Confirmer la restauration',
    confirmLabel: 'Restaurer',
    successTitle: 'Restauration effectuée',
    icon: 'restore',
    tone: 'primary',
  },
  suspension: {
    title: 'Confirmer la suspension',
    confirmLabel: 'Suspendre',
    successTitle: 'Suspension effectuée',
    icon: 'pause_circle',
    tone: 'warn',
  },
  reprise: {
    title: 'Confirmer la reprise',
    confirmLabel: 'Reprendre',
    successTitle: 'Reprise effectuée',
    icon: 'play_circle',
    tone: 'primary',
  },
  renouvellement: {
    title: 'Confirmer le renouvellement',
    confirmLabel: 'Renouveler',
    successTitle: 'Renouvellement préparé',
    icon: 'autorenew',
    tone: 'primary',
  },
  expiration: {
    title: 'Marquer comme expiré',
    confirmLabel: 'Marquer expiré',
    successTitle: 'Statut mis à jour',
    icon: 'event_busy',
    tone: 'warn',
  },
  depart: {
    title: 'Modifications non enregistrées',
    confirmLabel: 'Quitter sans enregistrer',
    successTitle: '',
    icon: 'edit_off',
    tone: 'warn',
  },
};
