import { DatePipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { statutLabel } from '../immobilisations/immobilisation.constants';
import { MontantPipe } from '../shared/montant.pipe';
import { PieceComptable } from './piece-comptable.model';

export interface PieceDetailDialogData {
  piece: PieceComptable;
  typeLabel: string;
}

interface ImmobilisationDetail {
  id: string;
  code_inventaire: string;
  designation: string;
  statut: string;
  valeur_brute: string;
  date_acquisition: string;
  date_mise_en_service: string | null;
  compte_immobilisation: string | null;
  localisation: string | null;
  numero_facture: string | null;
  categorie?: { libelle?: string; code?: string } | null;
}

@Component({
  selector: 'app-piece-detail-dialog',
  imports: [DatePipe, MontantPipe, MatDialogModule, MatButtonModule, MatIconModule, RouterLink],
  templateUrl: './piece-detail-dialog.component.html',
  styleUrl: './piece-detail-dialog.component.css',
})
export class PieceDetailDialogComponent implements OnInit {
  readonly data = inject<PieceDetailDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<PieceDetailDialogComponent>);
  private readonly api = inject(ApiService);

  readonly piece = this.data.piece;
  readonly typeLabel = this.data.typeLabel;
  readonly immo = signal<ImmobilisationDetail | null>(null);
  readonly loadingImmo = signal(true);
  readonly downloading = signal(false);
  readonly loadError = signal<string | null>(null);

  readonly statutLabel = statutLabel;

  ngOnInit(): void {
    this.api.get<ImmobilisationDetail>(`/immobilisations/${this.piece.immobilisation_id}`).subscribe({
      next: (row) => {
        this.immo.set(row);
        this.loadingImmo.set(false);
      },
      error: () => {
        this.loadError.set('Impossible de charger la fiche immobilisation.');
        this.loadingImmo.set(false);
      },
    });
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) {
      return `${bytes} o`;
    }
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} Ko`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  }

  download(): void {
    this.downloading.set(true);
    this.api.download(`/pieces/${this.piece.id}/download`).subscribe({
      next: (blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = this.piece.filename;
        a.click();
        URL.revokeObjectURL(a.href);
        this.downloading.set(false);
      },
      error: () => this.downloading.set(false),
    });
  }

  close(): void {
    this.ref.close();
  }
}
