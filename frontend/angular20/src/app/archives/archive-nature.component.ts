import { DatePipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { findNatureImmoOfficielle } from '../immobilisations/immobilisation.constants';
import { MontantPipe } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import type {
  ArchiveAcquisitions,
  ArchiveDossierDetail,
  ArchiveFichier,
  ArchiveNatureGroupe,
} from './archive.models';

@Component({
  selector: 'app-archive-nature',
  imports: [RouterLink, DatePipe, MontantPipe, MatButtonModule, MatIconModule, MatTableModule],
  templateUrl: './archive-nature.component.html',
  styleUrl: './archive-nature.component.css',
})
export class ArchiveNatureComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly route = inject(ActivatedRoute);

  readonly annee = signal(0);
  readonly natureCode = signal('');
  readonly dossier = signal<ArchiveDossierDetail | null>(null);
  readonly groupe = signal<ArchiveNatureGroupe | null>(null);
  readonly loading = signal(false);
  readonly uploading = signal(false);
  readonly busyId = signal<string | null>(null);
  readonly search = signal('');

  readonly columns = [
    'date',
    'designation',
    'qte',
    'vb',
    'taux',
    'amt_n1',
    'dotation',
    'amt_fin',
    'vnc',
    'agence',
  ];

  private selectedFile: File | null = null;

  readonly natureLibelle = computed(
    () => findNatureImmoOfficielle(this.natureCode())?.libelle ?? this.natureCode(),
  );

  readonly natureTitle = computed(() => `${this.natureLibelle()} ${this.annee()}`);

  readonly fichiers = computed(() => {
    const code = this.natureCode();
    return (this.dossier()?.fichiers ?? []).filter((f) => f.nature_code === code);
  });

  readonly lignesFiltrees = computed(() => {
    const g = this.groupe();
    if (!g) return [];
    const q = this.search().trim().toLowerCase();
    if (!q) return g.lignes;
    return g.lignes.filter((l) => l.designation.toLowerCase().includes(q));
  });

  ngOnInit(): void {
    const annee = Number(this.route.snapshot.paramMap.get('annee'));
    const nature = (this.route.snapshot.paramMap.get('natureCode') || '').trim();
    if (!annee || !nature || !findNatureImmoOfficielle(nature)) {
      void this.dialogs.error('Dossier nature invalide').subscribe();
      return;
    }
    this.annee.set(annee);
    this.natureCode.set(nature);
    this.reload();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
  }

  onSearch(event: Event): void {
    this.search.set((event.target as HTMLInputElement).value);
  }

  reload(): void {
    this.loading.set(true);
    const annee = this.annee();
    const nature = this.natureCode();
    this.api.get<ArchiveDossierDetail>(`/archives/dossiers/${annee}`).subscribe({
      next: (d) => {
        this.dossier.set(d);
        this.api
          .get<ArchiveAcquisitions>(`/archives/dossiers/${annee}/acquisitions`, {
            nature_code: nature,
          })
          .subscribe({
            next: (acq) => {
              this.groupe.set(acq.groupes[0] ?? null);
              this.loading.set(false);
            },
            error: (err: { error?: { detail?: unknown } }) => {
              this.loading.set(false);
              const detail = err.error?.detail;
              void this.dialogs
                .error(typeof detail === 'string' ? detail : 'Impossible de charger les lignes')
                .subscribe();
            },
          });
      },
      error: (err: { error?: { detail?: unknown } }) => {
        this.loading.set(false);
        const detail = err.error?.detail;
        void this.dialogs
          .error(typeof detail === 'string' ? detail : 'Dossier introuvable')
          .subscribe();
      },
    });
  }

  upload(): void {
    if (!this.selectedFile) {
      void this.dialogs.error('Choisissez un fichier Excel ou PDF').subscribe();
      return;
    }
    const nature = this.natureCode();
    if (!nature) {
      void this.dialogs.error('Nature manquante — rouvrez AAI 2008 depuis le dossier').subscribe();
      return;
    }
    this.uploading.set(true);
    this.api
      .upload<ArchiveFichier>(`/archives/dossiers/${this.annee()}/fichiers`, this.selectedFile, {
        nature_code: nature,
      })
      .subscribe({
        next: (f) => {
          this.uploading.set(false);
          this.selectedFile = null;
          const input = document.getElementById('arn-file') as HTMLInputElement | null;
          if (input) input.value = '';
          if (f.parse_status === 'error') {
            void this.dialogs
              .error(f.parse_error || 'Scan en erreur — fichier conservé')
              .subscribe();
          }
          this.reload();
        },
        error: (err: { error?: { detail?: unknown } }) => {
          this.uploading.set(false);
          const detail = err.error?.detail;
          let msg = 'Upload impossible';
          if (typeof detail === 'string') {
            msg = detail;
          } else if (Array.isArray(detail) && detail[0]?.msg) {
            msg = String(detail[0].msg);
          }
          void this.dialogs.error(msg).subscribe();
        },
      });
  }

  rescan(f: ArchiveFichier): void {
    this.busyId.set(f.id);
    this.api
      .post<ArchiveFichier>(`/archives/dossiers/${this.annee()}/fichiers/${f.id}/rescan`, {})
      .subscribe({
        next: () => {
          this.busyId.set(null);
          this.reload();
        },
        error: (err: { error?: { detail?: unknown } }) => {
          this.busyId.set(null);
          const detail = err.error?.detail;
          void this.dialogs
            .error(typeof detail === 'string' ? detail : 'Rescan impossible')
            .subscribe();
        },
      });
  }

  download(f: ArchiveFichier): void {
    this.api.download(`/archives/dossiers/${this.annee()}/fichiers/${f.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = f.filename;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => void this.dialogs.error('Téléchargement impossible').subscribe(),
    });
  }

  remove(f: ArchiveFichier): void {
    this.dialogs
      .confirmAction('suppression', `Supprimer « ${f.filename} » et ses lignes extraites ?`)
      .subscribe((ok) => {
        if (!ok) return;
        this.busyId.set(f.id);
        this.api.delete(`/archives/dossiers/${this.annee()}/fichiers/${f.id}`).subscribe({
          next: () => {
            this.busyId.set(null);
            this.reload();
          },
          error: (err: { error?: { detail?: unknown } }) => {
            this.busyId.set(null);
            const detail = err.error?.detail;
            void this.dialogs
              .error(typeof detail === 'string' ? detail : 'Suppression impossible')
              .subscribe();
          },
        });
      });
  }

  statusLabel(status: string): string {
    switch (status) {
      case 'ok':
        return 'OK';
      case 'error':
        return 'Erreur';
      case 'partial':
        return 'Partiel';
      default:
        return 'En attente';
    }
  }

  formatTaux(taux: number | null): string {
    if (taux == null || Number.isNaN(Number(taux))) {
      return '—';
    }
    const n = Number(taux);
    const compact = Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, '');
    return `${compact} %`;
  }
}
