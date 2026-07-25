import { DatePipe } from '@angular/common';
import { MontantPipe } from '../shared/montant.pipe';
import { Component, inject, input, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

export interface RebutDetail {
  id: string;
  immobilisation_id: string;
  date_rebut: string;
  vnc: string;
  motif: string | null;
  ecriture_id: string | null;
  code_inventaire: string | null;
  designation: string | null;
  valeur_brute: string | null;
  date_acquisition: string | null;
  compte_immobilisation: string | null;
  statut_immobilisation: string | null;
  cumul_amortissement: string | null;
}

@Component({
  selector: 'app-rebut-detail',
  standalone: true,
  imports: [MontantPipe, DatePipe, RouterLink, MatButtonModule, MatIconModule],
  templateUrl: './rebut-detail.component.html',
  styleUrl: './rebut-detail.component.css',
})
export class RebutDetailComponent implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);

  readonly detail = signal<RebutDetail | null>(null);
  readonly loading = signal(true);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<RebutDetail>(`/rebuts/${this.id()}`).subscribe({
      next: (row) => {
        this.detail.set(row);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        void this.dialogs.error(err.error?.detail ?? 'Fiche rebut introuvable').subscribe();
      },
    });
  }

  export(format: 'xlsx' | 'pdf'): void {
    const d = this.detail();
    if (!d) {
      return;
    }
    this.exporting.set(format);
    this.api.download(`/rebuts/${d.id}/export`, { format }).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        const ext = format === 'pdf' ? 'pdf' : 'xlsx';
        const code = (d.code_inventaire || d.id.slice(0, 8)).replace(/\s+/g, '_');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `fiche-rebut-${code}.${ext}`;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      error: () => {
        this.exporting.set(null);
        void this.dialogs.error('Export impossible').subscribe();
      },
    });
  }
}
