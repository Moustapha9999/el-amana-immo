import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import type { ArchiveDossier } from './archive.models';

export type { ArchiveDossier };

interface ClotureResponse {
  annee: number;
  natures_creees: number;
  lignes: number;
  ouvertures_seed: number;
  dossier_id: string;
  message: string;
  annee_ouverture: number;
}

@Component({
  selector: 'app-archives',
  imports: [ReactiveFormsModule, RouterLink, MatButtonModule, MatIconModule],
  templateUrl: './archives.component.html',
  styleUrl: './archives.component.css',
})
export class ArchivesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);

  readonly dossiers = signal<ArchiveDossier[]>([]);
  readonly loading = signal(false);
  readonly creating = signal(false);
  readonly cloturing = signal(false);
  readonly deletingAnnee = signal<number | null>(null);

  readonly createForm = this.fb.nonNullable.group({
    annee: [new Date().getFullYear() - 1],
    libelle: [''],
  });

  readonly clotureForm = this.fb.nonNullable.group({
    annee: [new Date().getFullYear() - 1],
    force: [false],
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<ArchiveDossier[]>('/archives/dossiers').subscribe({
      next: (rows) => {
        this.dossiers.set(rows);
        this.loading.set(false);
      },
      error: (err: { error?: { detail?: unknown } }) => {
        this.loading.set(false);
        const detail = err.error?.detail;
        void this.dialogs
          .error(typeof detail === 'string' ? detail : 'Impossible de charger les archives')
          .subscribe();
      },
    });
  }

  create(): void {
    const annee = Number(this.createForm.controls.annee.value);
    const libelle = (this.createForm.controls.libelle.value || '').trim();
    if (!annee || annee < 1990 || annee > 2100) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    this.creating.set(true);
    this.api
      .post<ArchiveDossier>('/archives/dossiers', {
        annee,
        libelle: libelle || null,
      })
      .subscribe({
        next: () => {
          this.creating.set(false);
          this.createForm.patchValue({ libelle: '' });
          this.load();
        },
        error: (err: { error?: { detail?: unknown } }) => {
          this.creating.set(false);
          const detail = err.error?.detail;
          void this.dialogs
            .error(typeof detail === 'string' ? detail : 'Création impossible')
            .subscribe();
        },
      });
  }

  cloturer(): void {
    const annee = Number(this.clotureForm.controls.annee.value);
    const force = !!this.clotureForm.controls.force.value;
    if (!annee || annee < 1990 || annee > 2100) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    const msg = force
      ? `Régénérer la clôture 31/12/${annee} (écrase le snapshot système) et reporter les soldes 148 pour ${annee + 1} ?`
      : `Générer le dossier Archives 31/12/${annee} et préparer l’ouverture ${annee + 1} (soldes 142/148, sans les 68) ?`;
    this.dialogs.confirmAction('cloture', msg).subscribe((ok) => {
      if (!ok) {
        return;
      }
      this.cloturing.set(true);
      this.api.post<ClotureResponse>('/archives/cloture', { annee, force }).subscribe({
        next: (res) => {
          this.cloturing.set(false);
          this.load();
          void this.dialogs.successAction('cloture', res.message).subscribe({
            next: () => void this.router.navigate(['/archives', res.annee]),
          });
        },
        error: (err: { error?: { detail?: unknown } }) => {
          this.cloturing.set(false);
          const detail = err.error?.detail;
          void this.dialogs
            .error(typeof detail === 'string' ? detail : 'Clôture impossible')
            .subscribe();
        },
      });
    });
  }

  remove(d: ArchiveDossier, event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    const n = d.nb_fichiers;
    const msg =
      n > 0
        ? `Supprimer le dossier ${d.annee} et ses ${n} fichier(s) scannés ?`
        : `Supprimer le dossier ${d.annee} ?`;
    this.dialogs.confirmAction('suppression', msg).subscribe((ok) => {
      if (!ok) return;
      this.deletingAnnee.set(d.annee);
      this.api.delete(`/archives/dossiers/${d.annee}`).subscribe({
        next: () => {
          this.deletingAnnee.set(null);
          this.load();
        },
        error: (err: { error?: { detail?: unknown } }) => {
          this.deletingAnnee.set(null);
          const detail = err.error?.detail;
          void this.dialogs
            .error(typeof detail === 'string' ? detail : 'Suppression impossible')
            .subscribe();
        },
      });
    });
  }
}
