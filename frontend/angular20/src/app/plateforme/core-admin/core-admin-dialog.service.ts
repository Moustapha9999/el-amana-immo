import { Injectable, signal } from '@angular/core';

export type BeaAdminDialogTone = 'primary' | 'danger' | 'success' | 'warn' | 'info';

export interface BeaAdminDialogField {
  key: string;
  label: string;
  type?: 'text' | 'password';
  autocomplete?: string;
}

export interface BeaAdminConfirmOptions {
  title: string;
  message: string;
  tone?: BeaAdminDialogTone;
  confirmLabel?: string;
  cancelLabel?: string;
  fields?: BeaAdminDialogField[];
  validate?: (values: Record<string, string>) => string | null;
}

export interface BeaAdminFeedbackOptions {
  title: string;
  message: string;
  tone?: BeaAdminDialogTone;
  okLabel?: string;
}

export interface BeaAdminDialogState {
  kind: 'confirm' | 'feedback';
  title: string;
  message: string;
  tone: BeaAdminDialogTone;
  confirmLabel?: string;
  cancelLabel?: string;
  okLabel?: string;
  fields?: BeaAdminDialogField[];
  validate?: (values: Record<string, string>) => string | null;
}

@Injectable({ providedIn: 'root' })
export class BeaAdminDialogService {
  readonly state = signal<BeaAdminDialogState | null>(null);
  private pending: ((value: boolean | Record<string, string>) => void) | null = null;

  confirm(options: BeaAdminConfirmOptions): Promise<boolean> {
    return this.open({
      kind: 'confirm',
      title: options.title,
      message: options.message,
      tone: options.tone ?? 'primary',
      confirmLabel: options.confirmLabel ?? 'Confirmer',
      cancelLabel: options.cancelLabel ?? 'Annuler',
    }).then((value) => value === true);
  }

  prompt(options: BeaAdminConfirmOptions): Promise<Record<string, string> | null> {
    return this.open({
      kind: 'confirm',
      title: options.title,
      message: options.message,
      tone: options.tone ?? 'primary',
      confirmLabel: options.confirmLabel ?? 'Confirmer',
      cancelLabel: options.cancelLabel ?? 'Annuler',
      fields: options.fields ?? [],
      validate: options.validate,
    }).then((value) => (value && typeof value === 'object' ? value : null));
  }

  success(message: string, title = 'Action effectuée'): Promise<void> {
    return this.feedback({ title, message, tone: 'success', okLabel: 'OK' });
  }

  error(message: string, title = 'Erreur'): Promise<void> {
    return this.feedback({ title, message, tone: 'danger', okLabel: 'Fermer' });
  }

  info(message: string, title = 'Information'): Promise<void> {
    return this.feedback({ title, message, tone: 'info', okLabel: 'OK' });
  }

  feedback(options: BeaAdminFeedbackOptions): Promise<void> {
    return this.open({
      kind: 'feedback',
      title: options.title,
      message: options.message,
      tone: options.tone ?? 'info',
      okLabel: options.okLabel ?? 'OK',
    }).then(() => undefined);
  }

  close(value: boolean | Record<string, string> = false): void {
    this.state.set(null);
    const resolve = this.pending;
    this.pending = null;
    resolve?.(value);
  }

  dismiss(): void {
    this.close(false);
  }

  private open(state: BeaAdminDialogState): Promise<boolean | Record<string, string>> {
    if (this.pending) {
      this.pending(false);
      this.pending = null;
    }
    this.state.set(state);
    return new Promise((resolve) => {
      this.pending = resolve;
    });
  }
}
