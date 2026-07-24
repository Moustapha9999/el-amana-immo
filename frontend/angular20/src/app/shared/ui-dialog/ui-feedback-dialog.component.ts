import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { UiFeedbackData } from './ui-dialog.types';

@Component({
  selector: 'app-ui-feedback-dialog',
  imports: [MatDialogModule, MatButtonModule, MatIconModule],
  templateUrl: './ui-feedback-dialog.component.html',
  styleUrl: './ui-dialog.shared.css',
})
export class UiFeedbackDialogComponent {
  readonly data = inject<UiFeedbackData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<UiFeedbackDialogComponent, void>);

  get tone(): string {
    return this.data.tone ?? 'success';
  }

  close(): void {
    this.ref.close();
  }
}
