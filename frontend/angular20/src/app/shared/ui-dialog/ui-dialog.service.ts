import { inject, Injectable } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { Observable, map } from 'rxjs';
import { UiConfirmDialogComponent } from './ui-confirm-dialog.component';
import { UiFeedbackDialogComponent } from './ui-feedback-dialog.component';
import {
  UI_DIALOG_PRESETS,
  UiConfirmData,
  UiDialogAction,
  UiFeedbackData,
} from './ui-dialog.types';

@Injectable({ providedIn: 'root' })
export class UiDialogService {
  private readonly dialog = inject(MatDialog);

  confirm(data: UiConfirmData): Observable<boolean> {
    return this.dialog
      .open(UiConfirmDialogComponent, {
        data,
        width: '28rem',
        maxWidth: '92vw',
        disableClose: true,
        autoFocus: 'first-tabbable',
      })
      .afterClosed()
      .pipe(map((v) => !!v));
  }

  feedback(data: UiFeedbackData): Observable<void> {
    return this.dialog
      .open(UiFeedbackDialogComponent, {
        data,
        width: '28rem',
        maxWidth: '92vw',
        autoFocus: 'first-tabbable',
      })
      .afterClosed()
      .pipe(map(() => undefined));
  }

  /** Confirmation typée (Ajout, Suppression, Comptabilisation…). */
  confirmAction(action: UiDialogAction, message: string, title?: string): Observable<boolean> {
    const preset = UI_DIALOG_PRESETS[action];
    return this.confirm({
      title: title ?? preset.title,
      message,
      confirmLabel: preset.confirmLabel,
      cancelLabel: 'Annuler',
      tone: preset.tone,
      icon: preset.icon,
    });
  }

  /** Popup de succès typée. */
  successAction(action: UiDialogAction, message: string, title?: string): Observable<void> {
    const preset = UI_DIALOG_PRESETS[action];
    return this.feedback({
      title: title ?? preset.successTitle,
      message,
      tone: action === 'suppression' ? 'success' : preset.tone === 'danger' ? 'success' : 'success',
      icon: action === 'suppression' ? 'check_circle' : preset.icon,
      okLabel: 'OK',
    });
  }

  error(message: string, title = 'Erreur'): Observable<void> {
    return this.feedback({
      title,
      message,
      tone: 'danger',
      icon: 'error',
      okLabel: 'Fermer',
    });
  }

  info(message: string, title = 'Information'): Observable<void> {
    return this.feedback({
      title,
      message,
      tone: 'info',
      icon: 'info',
      okLabel: 'OK',
    });
  }
}
