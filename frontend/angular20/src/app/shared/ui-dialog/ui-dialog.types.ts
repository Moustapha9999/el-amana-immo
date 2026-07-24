export type UiDialogTone = 'primary' | 'danger' | 'success' | 'warn' | 'info';

export type UiDialogAction =
  | 'ajout'
  | 'modification'
  | 'suppression'
  | 'enregistrement'
  | 'validation'
  | 'comptabilisation'
  | 'cloture'
  | 'ouverture';

export interface UiConfirmData {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: UiDialogTone;
  icon?: string;
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
};
