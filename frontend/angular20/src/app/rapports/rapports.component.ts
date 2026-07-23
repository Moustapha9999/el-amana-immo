import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ApiService } from '../core/services/api.service';

import { PageHeaderComponent } from '../shared/page-header.component';

@Component({
  selector: 'app-rapports',
  imports: [MatCardModule, MatButtonModule, RouterLink, PageHeaderComponent],
  templateUrl: './rapports.component.html',
})
export class RapportsComponent {
  private readonly api = inject(ApiService);
  private readonly snack = inject(MatSnackBar);

  readonly importBusy = signal(false);
  readonly importResult = signal<string | null>(null);

  download(path: string, filename: string, params?: Record<string, string>): void {
    this.api.download(path, params).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  exportEcritures(format: 'xlsx' | 'pdf'): void {
    const ext = format === 'pdf' ? 'pdf' : 'xlsx';
    this.download('/reporting/ecritures/export', `ecritures-el-amana.${ext}`, { format });
  }

  exportImmobilisations(): void {
    this.download('/reporting/immobilisations/export', 'immobilisations-el-amana.xlsx');
  }

  downloadImportTemplate(): void {
    this.download('/reporting/immobilisations/import-template', 'modele-import-immobilisations.xlsx');
  }

  onImportFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    this.importBusy.set(true);
    this.importResult.set(null);
    this.api.upload<{ created: number; errors: string[] }>('/immobilisations/import', file).subscribe({
      next: (res) => {
        this.importBusy.set(false);
        const errPart = res.errors.length ? ` — ${res.errors.length} erreur(s)` : '';
        this.importResult.set(`${res.created} immobilisation(s) créée(s)${errPart}`);
        if (res.errors.length) {
          this.snack.open(res.errors.slice(0, 3).join(' · '), 'Fermer', { duration: 8000 });
        }
      },
      error: (err) => {
        this.importBusy.set(false);
        this.snack.open(err.error?.detail ?? 'Import impossible', 'Fermer', { duration: 5000 });
      },
    });
  }
}
