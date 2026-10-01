import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { UiReasonData } from './ui-dialog.types';

@Component({
  selector: 'app-ui-reason-dialog',
  imports: [MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <form class="ui-dlg" [attr.data-tone]="tone" (submit)="$event.preventDefault(); confirm()">
      <div class="ui-dlg__icon" aria-hidden="true">
        <mat-icon>{{ data.icon || 'edit_note' }}</mat-icon>
      </div>
      <h2 class="ui-dlg__title" mat-dialog-title>{{ data.title }}</h2>
      <div mat-dialog-content class="ui-dlg__body">
        <p class="ui-dlg__message">{{ data.message }}</p>
        @if (data.hint) { <p class="ui-dlg__hint">{{ data.hint }}</p> }
        <label class="ui-dlg__reason">
          {{ data.reasonLabel || 'Motif' }}{{ required ? ' *' : '' }}
          <textarea
            [value]="reason()"
            (input)="onInput($event)"
            [attr.maxlength]="max"
            [placeholder]="data.reasonPlaceholder || 'Expliquez brièvement la raison'"
            [attr.aria-invalid]="touched() && invalid()"
            cdkFocusInitial
          ></textarea>
          @if (touched() && invalid()) {
            <small class="ui-dlg__reason-error" role="alert">Le motif est obligatoire.</small>
          } @else {
            <small>{{ reason().length }} / {{ max }}</small>
          }
        </label>
      </div>
      <div mat-dialog-actions class="ui-dlg__actions">
        <button mat-stroked-button type="button" (click)="cancel()">{{ data.cancelLabel || 'Annuler' }}</button>
        <button mat-flat-button type="submit" [color]="tone === 'danger' ? 'warn' : 'primary'">
          {{ data.confirmLabel || 'Confirmer' }}
        </button>
      </div>
    </form>
  `,
  styleUrl: './ui-dialog.shared.css',
})
export class UiReasonDialogComponent {
  readonly data = inject<UiReasonData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<UiReasonDialogComponent, string | null>);
  readonly reason = signal('');
  readonly touched = signal(false);
  readonly required = this.data.required !== false;
  readonly max = this.data.maxLength ?? 500;

  get tone(): string {
    return this.data.tone ?? 'primary';
  }

  invalid(): boolean {
    return this.required && !this.reason().trim();
  }

  onInput(event: Event): void {
    this.reason.set((event.target as HTMLTextAreaElement).value);
  }

  cancel(): void {
    this.ref.close(null);
  }

  confirm(): void {
    this.touched.set(true);
    if (this.invalid()) return;
    this.ref.close(this.reason().trim());
  }
}
