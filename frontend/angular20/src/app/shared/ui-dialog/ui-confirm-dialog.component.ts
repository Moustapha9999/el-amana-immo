import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { UiConfirmData } from './ui-dialog.types';

@Component({
  selector: 'app-ui-confirm-dialog',
  imports: [MatDialogModule, MatButtonModule, MatIconModule],
  templateUrl: './ui-confirm-dialog.component.html',
  styleUrl: './ui-dialog.shared.css',
})
export class UiConfirmDialogComponent {
  readonly data = inject<UiConfirmData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<UiConfirmDialogComponent, boolean>);

  get tone(): string {
    return this.data.tone ?? 'primary';
  }

  cancel(): void {
    this.ref.close(false);
  }

  confirm(): void {
    this.ref.close(true);
  }
}
