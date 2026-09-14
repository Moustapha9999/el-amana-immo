import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import type { ArchiveDossier } from './archive.models';

export type { ArchiveDossier };

interface ExerciceRead {
  id: string;
  annee: number;
  statut: string;
  archive_dossier_id: string | null;
  cloture_at: string | null;
  ouverture_at: string | null;
  total_valeur_brute: number;
  total_amortissement: number;
  total_vnc: number;
  total_dotation_68: number;
  nb_immobilisations: number;
  message: string | null;
}

interface ExerciceSituation {
  dernier_cloture: number | null;
  exercice_ouvert: number | null;
  annee_ouverture_proposee: number | null;
  peut_ouvrir: boolean;
  exercices: ExerciceRead[];
}

interface ClotureResponse {
  annee: number;
  natures_creees: number;
  lignes: number;
  dossier_id: string;
  message: string;
  annee_ouverture_proposee: number;
  total_valeur_brute: number;
  total_amortissement: number;
  total_vnc: number;
  total_dotation_68: number;
  nb_immobilisations: number;
}

interface OuvertureResponse {
  annee_source: number;
  annee_ouverture: number;
  ouvertures_seed: number;
  total_valeur_brute: number;
  total_amortissement: number;
  total_vnc: number;
  message: string;
}

interface SoldeOrionLigne {
  annee: number;
  compte_immobilisation: string;
  nature_code: string;
  libelle: string;
  valeur_brute: number;
  source: string;
}

interface SoldeOrionResponse {
  annee: number;
  verrouille: boolean;
  lignes: SoldeOrionLigne[];
}

@Component({
  selector: 'app-archives',
  imports: [ReactiveFormsModule, RouterLink, MatButtonModule, MatIconModule],
  templateUrl: './archives.component.html',
  styleUrl: './archives.component.css',
})
export class ArchivesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);

  readonly dossiers = signal<ArchiveDossier[]>([]);
  readonly situation = signal<ExerciceSituation | null>(null);
  readonly loading = signal(false);
  readonly cloturing = signal(false);
  readonly opening = signal(false);
  readonly savingOrion = signal(false);
  readonly deletingAnnee = signal<number | null>(null);
  readonly orionLignes = signal<SoldeOrionLigne[]>([]);
  readonly orionVerrouille = signal(false);

  readonly orionComptes = ['140000', '142000', '145300'] as const;

  readonly canManageExercices = computed(() => {
    const u = this.auth.user();
    if (!u) {
      return false;
    }
    if (u.is_superuser) {
      return true;
    }
    return u.roles.some((r) => r.code === 'administrateur');
  });

  readonly anneeOuvertureProposee = computed(
    () => this.situation()?.annee_ouverture_proposee ?? null,
  );
  readonly dernierCloture = computed(() => this.situation()?.dernier_cloture ?? null);
  readonly peutOuvrir = computed(() => !!this.situation()?.peut_ouvrir);
  /** Année cible des soldes Orion = exercice ouvert, sinon ouverture proposée. */
  readonly anneeOrion = computed(
    () => this.situation()?.exercice_ouvert ?? this.situation()?.annee_ouverture_proposee ?? null,
  );

  readonly clotureForm = this.fb.nonNullable.group({
    annee: [new Date().getFullYear() - 1],
  });

  readonly orionForm = this.fb.nonNullable.group({
    '140000': [0 as number],
    '142000': [0 as number],
    '145300': [0 as number],
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
    this.api.get<ExerciceSituation>('/exercices/situation').subscribe({
      next: (s) => {
        this.situation.set(s);
        this.loadOrion(s.exercice_ouvert ?? s.annee_ouverture_proposee);
      },
      error: () => this.situation.set(null),
    });
  }

  loadOrion(annee: number | null | undefined): void {
    if (!annee || annee < 2000 || annee > 2100) {
      this.orionVerrouille.set(false);
      this.orionLignes.set([]);
      return;
    }
    this.api.get<SoldeOrionResponse>('/reporting/soldes-orion', { annee }).subscribe({
      next: (res) => {
        this.orionVerrouille.set(!!res.verrouille);
        this.orionLignes.set(res.lignes ?? []);
        const patch: Record<string, number> = {
          '140000': 0,
          '142000': 0,
          '145300': 0,
        };
        for (const row of res.lignes ?? []) {
          if (row.compte_immobilisation in patch) {
            patch[row.compte_immobilisation] = Number(row.valeur_brute) || 0;
          }
        }
        this.orionForm.patchValue(patch, { emitEvent: false });
      },
      error: () => {
        this.orionVerrouille.set(false);
        this.orionLignes.set([]);
      },
    });
  }

  orionLibelle(compte: string): string {
    const row = this.orionLignes().find((l) => l.compte_immobilisation === compte);
    if (row?.libelle) {
      return row.libelle;
    }
    if (compte === '140000') return 'Titres de participations';
    if (compte === '142000') return 'Terrain';
    if (compte === '145300') return 'Immo en cours';
    return compte;
  }

  saveOrion(): void {
    if (!this.canManageExercices()) {
      void this.dialogs.error('Seuls les administrateurs peuvent saisir les soldes Orion.').subscribe();
      return;
    }
    const annee = this.anneeOrion();
    if (!annee) {
      void this.dialogs.error('Aucun exercice ouvert pour rattacher les soldes Orion.').subscribe();
      return;
    }
    this.dialogs
      .confirmAction(
        'validation',
        `Enregistrer définitivement les soldes Orion pour ${annee} ?\n\nAprès validation, ils ne pourront plus être modifiés.`,
      )
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        const raw = this.orionForm.getRawValue();
        const lignes = this.orionComptes.map((compte) => ({
          compte_immobilisation: compte,
          valeur_brute: Number(raw[compte]) || 0,
        }));
        this.savingOrion.set(true);
        this.api.put<SoldeOrionResponse>('/reporting/soldes-orion', { annee, lignes }).subscribe({
          next: (res) => {
            this.savingOrion.set(false);
            this.orionVerrouille.set(true);
            this.orionLignes.set(res.lignes ?? []);
            void this.dialogs
              .successAction(
                'validation',
                `Soldes Orion ${annee} verrouillés — pris en compte dans Soldes 142.`,
              )
              .subscribe();
          },
          error: (err: { error?: { detail?: unknown } }) => {
            this.savingOrion.set(false);
            const detail = err.error?.detail;
            void this.dialogs
              .error(typeof detail === 'string' ? detail : 'Enregistrement Orion impossible')
              .subscribe();
          },
        });
      });
  }

  statutExercice(annee: number): string | null {
    const exo = this.situation()?.exercices.find((e) => e.annee === annee);
    return exo?.statut ?? null;
  }

  cloturer(): void {
    if (!this.canManageExercices()) {
      void this.dialogs.error('Seuls les administrateurs peuvent clôturer un exercice.').subscribe();
      return;
    }
    const annee = Number(this.clotureForm.controls.annee.value);
    if (!annee || annee < 1990 || annee > 2100) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    const msg =
      `Clôturer définitivement l’exercice ${annee} ?\n\n` +
      `• Le dossier Archives ${annee} sera créé / complété\n` +
      `• Aucune modification ultérieure ne sera possible sur ${annee}\n` +
      `• L’ouverture de ${annee + 1} se fera ensuite via « Ouvrir un exercice »`;
    this.dialogs.confirmAction('cloture', msg).subscribe((ok) => {
      if (!ok) {
        return;
      }
      this.cloturing.set(true);
      this.api.post<ClotureResponse>('/exercices/cloturer', { annee }).subscribe({
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

  ouvrirSuivant(): void {
    if (!this.canManageExercices()) {
      void this.dialogs.error('Seuls les administrateurs peuvent ouvrir un exercice.').subscribe();
      return;
    }
    const n1 = this.anneeOuvertureProposee();
    const n = this.dernierCloture();
    if (!n1 || !n) {
      void this.dialogs.error('Aucun exercice clôturé à ouvrir.').subscribe();
      return;
    }
    const msg =
      `Ouvrir automatiquement l’exercice ${n1} ?\n\n` +
      `Dernier exercice clôturé : ${n}\n` +
      `• Reprise des soldes 142 (immobilisations + stock Orion Titres/Terrain/Immo en cours)\n` +
      `• Reprise des soldes 148 (amortissements cumulés)\n` +
      `• Conservation de la VNC\n` +
      `• Compte 68 remis à 0`;
    this.dialogs.confirmAction('ouverture', msg).subscribe((ok) => {
      if (!ok) {
        return;
      }
      this.opening.set(true);
      this.api.post<OuvertureResponse>('/exercices/ouvrir-suivant', {}).subscribe({
        next: (res) => {
          this.opening.set(false);
          this.load();
          void this.dialogs.successAction('ouverture', res.message).subscribe();
        },
        error: (err: { error?: { detail?: unknown } }) => {
          this.opening.set(false);
          const detail = err.error?.detail;
          void this.dialogs
            .error(typeof detail === 'string' ? detail : 'Ouverture impossible')
            .subscribe();
        },
      });
    });
  }

  remove(d: ArchiveDossier, event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    if (!this.canManageExercices()) {
      return;
    }
    if (this.statutExercice(d.annee) === 'cloture') {
      void this.dialogs
        .error(`Le dossier ${d.annee} est lié à une clôture définitive et ne peut pas être supprimé.`)
        .subscribe();
      return;
    }
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
