import { DatePipe } from '@angular/common';
import { MontantPipe } from '../shared/montant.pipe';
import { Component, inject, input, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

export interface EcritureDetail {
  id: string;
  journal_code: string;
  date_ecriture: string;
  libelle: string;
  compte_debit: string;
  compte_credit: string;
  montant: string;
  reference: string | null;
  immobilisation_id: string | null;
  generee_auto: boolean;
  validee: boolean;
  code_inventaire: string | null;
  designation: string | null;
  type_mouvement: string | null;
}

@Component({
  selector: 'app-ecriture-detail',
  imports: [RouterLink, DatePipe, MontantPipe, MatButtonModule, MatIconModule],
  templateUrl: './ecriture-detail.component.html',
  styleUrl: './ecriture-detail.component.css',
})
export class EcritureDetailComponent implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);

  readonly detail = signal<EcritureDetail | null>(null);
  readonly loading = signal(true);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<EcritureDetail>(`/ecritures/${this.id()}`).subscribe({
      next: (row) => {
        this.detail.set(row);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        void this.dialogs.error(err.error?.detail ?? 'Écriture introuvable').subscribe();
      },
    });
  }

  typeLabel(type: string | null): string {
    switch (type) {
      case 'amortissement':
        return 'Dotation / amortissement';
      case 'cession':
        return 'Cession';
      case 'rebut':
        return 'Mise au rebut';
      case 'reevaluation':
        return 'Réévaluation';
      case 'manuel':
        return 'Saisie manuelle';
      default:
        return 'Autre';
    }
  }

  export(format: 'xlsx' | 'pdf'): void {
    const d = this.detail();
    if (!d) {
      return;
    }
    this.exporting.set(format);
    this.api.download(`/ecritures/${d.id}/export`, { format }).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        const ext = format === 'pdf' ? 'pdf' : 'xlsx';
        const ref = (d.reference || d.id.slice(0, 8)).replace(/\s+/g, '_');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `fiche-ecriture-${ref}.${ext}`;
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
