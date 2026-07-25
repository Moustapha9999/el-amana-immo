import { DatePipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

export interface PieceComptable {
  id: string;
  immobilisation_id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
  is_photo: boolean;
  type_piece: string;
  date_journee: string;
  reference: string | null;
  libelle: string | null;
  created_at: string | null;
  code_inventaire: string | null;
  designation: string | null;
}

interface PieceType {
  value: string;
  label: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
}

interface ImmoOption {
  id: string;
  code_inventaire: string;
  designation: string;
}

@Component({
  selector: 'app-pieces-comptables',
  imports: [ReactiveFormsModule, DatePipe, MatButtonModule, MatIconModule, RouterLink],
  templateUrl: './pieces-comptables.component.html',
  styleUrl: './pieces-comptables.component.css',
})
export class PiecesComptablesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly pieces = signal<PieceComptable[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly uploading = signal(false);
  readonly types = signal<PieceType[]>([]);
  readonly immobilisations = signal<ImmoOption[]>([]);

  readonly filterForm = this.fb.nonNullable.group({
    date_journee: [new Date().toISOString().slice(0, 10)],
    type_piece: [''],
    search: [''],
  });

  readonly uploadForm = this.fb.nonNullable.group({
    immobilisation_id: [''],
    type_piece: ['facture'],
    date_journee: [new Date().toISOString().slice(0, 10)],
    reference: [''],
    libelle: [''],
  });

  selectedFile: File | null = null;

  readonly typeLabels: Record<string, string> = {
    facture: 'Facture',
    pv: 'PV',
    bon_commande: 'Bon de commande',
    bon_livraison: 'Bon de livraison',
    contrat: 'Contrat',
    protocole_accord: "Protocole d'accord",
    autre: 'Autre',
  };

  private readonly defaultTypes: PieceType[] = [
    { value: 'facture', label: 'Facture' },
    { value: 'pv', label: 'PV' },
    { value: 'bon_commande', label: 'Bon de commande' },
    { value: 'bon_livraison', label: 'Bon de livraison' },
    { value: 'contrat', label: 'Contrat' },
    { value: 'protocole_accord', label: "Protocole d'accord" },
    { value: 'autre', label: 'Autre' },
  ];

  ngOnInit(): void {
    this.types.set(this.defaultTypes);
    this.api.get<PieceType[]>('/archives/pieces-comptables/types').subscribe({
      next: (rows) => {
        if (rows.length) {
          this.types.set(rows);
        }
      },
    });
    this.loadImmobilisations();
    this.load();
  }

  private loadImmobilisations(): void {
    // L'API limite size à 100 — on charge plusieurs pages si besoin
    const pageSize = 100;
    const collect = (page: number, acc: ImmoOption[]): void => {
      this.api
        .get<Paginated<ImmoOption>>('/immobilisations', { page, size: pageSize })
        .subscribe({
          next: (res) => {
            const next = acc.concat(res.items);
            if (next.length < res.total && res.items.length === pageSize) {
              collect(page + 1, next);
            } else {
              this.immobilisations.set(next);
            }
          },
          error: () => {
            this.immobilisations.set(acc);
            void this.dialogs
              .error('Impossible de charger les immobilisations')
              .subscribe();
          },
        });
    };
    collect(1, []);
  }

  private apiErrorMessage(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }

  load(): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string | number> = { page: 1, size: 100 };
    if (f.date_journee) {
      params['date_journee'] = f.date_journee;
    }
    if (f.type_piece) {
      params['type_piece'] = f.type_piece;
    }
    if (f.search.trim()) {
      params['search'] = f.search.trim();
    }
    this.loading.set(true);
    this.api.get<Paginated<PieceComptable>>('/archives/pieces-comptables', params).subscribe({
      next: (res) => {
        this.pieces.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        void this.dialogs.error(this.apiErrorMessage(err, 'Impossible de charger l’archive')).subscribe();
      },
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    this.selectedFile = files && files.length > 0 ? files[0] : null;
  }

  upload(): void {
    const raw = this.uploadForm.getRawValue();
    if (!raw.immobilisation_id) {
      void this.dialogs.error('Sélectionnez une immobilisation').subscribe();
      return;
    }
    if (!this.selectedFile) {
      void this.dialogs.error('Sélectionnez un fichier (PDF ou image)').subscribe();
      return;
    }
    this.uploading.set(true);
    this.api
      .upload<PieceComptable>(`/immobilisations/${raw.immobilisation_id}/pieces`, this.selectedFile, {
        type_piece: raw.type_piece,
        date_journee: raw.date_journee,
        reference: raw.reference,
        libelle: raw.libelle,
      })
      .subscribe({
        next: () => {
          this.uploading.set(false);
          this.selectedFile = null;
          this.uploadForm.patchValue({ reference: '', libelle: '' });
          if (this.filterForm.controls.date_journee.value !== raw.date_journee) {
            this.filterForm.controls.date_journee.setValue(raw.date_journee);
          }
          this.load();
          void this.dialogs.successAction('enregistrement', 'Pièce archivée pour la journée comptable.').subscribe();
        },
        error: (err) => {
          this.uploading.set(false);
          void this.dialogs.error(this.apiErrorMessage(err, 'Upload impossible')).subscribe();
        },
      });
  }

  download(row: PieceComptable): void {
    this.api.download(`/pieces/${row.id}/download`).subscribe({
      next: (blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = row.filename;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      error: () => void this.dialogs.error('Téléchargement impossible').subscribe(),
    });
  }

  remove(row: PieceComptable): void {
    this.dialogs
      .confirmAction('suppression', `Supprimer la pièce « ${row.filename} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.api.delete(`/pieces/${row.id}`).subscribe({
          next: () => this.load(),
          error: () => void this.dialogs.error('Suppression impossible').subscribe(),
        });
      });
  }

  typeLabel(value: string): string {
    return this.typeLabels[value] || value;
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
}
