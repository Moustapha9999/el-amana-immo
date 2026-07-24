import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, input, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

export interface CessionDetail {
  id: string;
  immobilisation_id: string;
  date_cession: string;
  prix_cession: string;
  vnc: string;
  plus_value: string;
  moins_value: string;
  resultat: string;
  cas: string;
  reference: string | null;
  observations: string | null;
  libelle: string | null;
  code_inventaire: string | null;
  designation: string | null;
  valeur_brute: string | null;
  date_acquisition: string | null;
  compte_immobilisation: string | null;
  statut_immobilisation: string | null;
}

@Component({
  selector: 'app-cession-detail',
  imports: [RouterLink, DatePipe, DecimalPipe, MatButtonModule, MatIconModule],
  templateUrl: './cession-detail.component.html',
  styleUrl: './cession-detail.component.css',
})
export class CessionDetailComponent implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);

  readonly detail = signal<CessionDetail | null>(null);
  readonly loading = signal(true);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<CessionDetail>(`/cessions/${this.id()}`).subscribe({
      next: (row) => {
        this.detail.set(row);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        void this.dialogs.error(err.error?.detail ?? 'Fiche cession introuvable').subscribe();
      },
    });
  }

  casLabel(cas: string): string {
    if (cas === 'plus_value') {
      return 'Plus-value';
    }
    if (cas === 'moins_value') {
      return 'Moins-value';
    }
    return 'Équilibre';
  }

  export(format: 'xlsx' | 'pdf'): void {
    const d = this.detail();
    if (!d) {
      return;
    }
    this.exporting.set(format);
    this.api.download(`/cessions/${d.id}/export`, { format }).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        const ext = format === 'pdf' ? 'pdf' : 'xlsx';
        const ref = (d.reference || d.id.slice(0, 8)).replace(/\s+/g, '_');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `fiche-cession-${ref}.${ext}`;
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
