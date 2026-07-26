import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import {
  NATURE_IMMO_OFFICIELLE,
  findNatureImmoOfficielle,
} from '../immobilisations/immobilisation.constants';
import { MontantPipe } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import type {
  ArchiveAcquisitions,
  ArchiveDossierDetail,
  ArchiveNatureFolder,
} from './archive.models';

@Component({
  selector: 'app-archive-detail',
  imports: [RouterLink, MontantPipe, MatButtonModule, MatIconModule],
  templateUrl: './archive-detail.component.html',
  styleUrl: './archive-detail.component.css',
})
export class ArchiveDetailComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly route = inject(ActivatedRoute);

  readonly annee = signal(0);
  readonly dossier = signal<ArchiveDossierDetail | null>(null);
  readonly acquisitions = signal<ArchiveAcquisitions | null>(null);
  readonly loading = signal(false);

  readonly natureFolders = computed<ArchiveNatureFolder[]>(() => {
    const d = this.dossier();
    const acq = this.acquisitions();
    const fichiers = d?.fichiers ?? [];
    const groupes = acq?.groupes ?? [];

    return NATURE_IMMO_OFFICIELLE.map((n) => {
      const files = fichiers.filter((f) => f.nature_code === n.code);
      const groupe = groupes.find((g) => g.nature_code === n.code);
      const nbFichiers = files.length;
      const nbLignes = groupe?.totaux.nb_lignes ?? files.reduce((s, f) => s + (f.lines_count || 0), 0);
      const valeurBrute = groupe?.totaux.valeur_brute ?? 0;
      return {
        code: n.code,
        libelle: n.libelle,
        nb_fichiers: nbFichiers,
        nb_lignes: nbLignes,
        valeur_brute: valeurBrute,
        has_data: nbFichiers > 0 || nbLignes > 0,
      };
    });
  });

  ngOnInit(): void {
    const annee = Number(this.route.snapshot.paramMap.get('annee'));
    if (!annee) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    this.annee.set(annee);
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.get<ArchiveDossierDetail>(`/archives/dossiers/${this.annee()}`).subscribe({
      next: (d) => {
        this.dossier.set(d);
        this.api
          .get<ArchiveAcquisitions>(`/archives/dossiers/${this.annee()}/acquisitions`)
          .subscribe({
            next: (acq) => {
              this.acquisitions.set(acq);
              this.loading.set(false);
            },
            error: () => {
              this.acquisitions.set(null);
              this.loading.set(false);
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

  natureTitle(folder: ArchiveNatureFolder): string {
    return `${folder.libelle} ${this.annee()}`;
  }

  natureLibelle(code: string): string {
    return findNatureImmoOfficielle(code)?.libelle ?? code;
  }
}
