import { DatePipe } from '@angular/common';
import { MontantPipe } from '../shared/montant.pipe';
import { Component, inject, input, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import {
  isCompteNonAmortissable,
  MESSAGE_NON_AMORTISSABLE_EL_AMANA,
  statutLabel,
} from '../immobilisations/immobilisation.constants';
import {
  formatPeriodeAmortissement,
  formatTauxPercent,
} from '../shared/amortissement-rate.util';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface ImmoDetail {
  id: string;
  code_inventaire: string;
  designation: string;
  statut: string;
  valeur_brute: string;
  valeur_residuelle: string;
  date_acquisition: string;
  date_mise_en_service: string | null;
  taux: string | null;
  duree_annees: number | null;
  compte_immobilisation: string | null;
  compte_amortissement: string | null;
  compte_dotation: string | null;
  categorie?: { famille: string; code: string; amortissable: boolean } | null;
}

interface AmortRow {
  id: string;
  periode: string;
  montant: string;
  cumul: string;
  vnc: string;
  valide: boolean;
  annule: boolean;
  simule: boolean;
}

@Component({
  selector: 'app-amortissement-detail',
  imports: [RouterLink, DatePipe, MontantPipe, MatButtonModule, MatIconModule, MatTableModule],
  templateUrl: './amortissement-detail.component.html',
  styleUrl: './amortissement-detail.component.css',
})
export class AmortissementDetailComponent implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);

  readonly immo = signal<ImmoDetail | null>(null);
  readonly lignes = signal<AmortRow[]>([]);
  readonly situation = signal<{ cumul_amortissement: string; vnc: string } | null>(null);
  readonly anneeExercice = signal(new Date().getFullYear());
  readonly loading = signal(true);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);
  readonly formatPeriode = formatPeriodeAmortissement;
  readonly formatTaux = formatTauxPercent;
  readonly statutLabel = statutLabel;
  readonly messageNonAmortissable = MESSAGE_NON_AMORTISSABLE_EL_AMANA;
  readonly columns = ['periode', 'montant', 'cumul', 'vnc', 'statut'];

  isNonAmortissable(): boolean {
    const i = this.immo();
    if (!i) {
      return false;
    }
    if (isCompteNonAmortissable(i.compte_immobilisation)) {
      return true;
    }
    return i.categorie != null && !i.categorie.amortissable;
  }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const immoId = this.id();
    this.loading.set(true);
    this.api.get<ImmoDetail>(`/immobilisations/${immoId}`).subscribe({
      next: (row) => {
        this.immo.set(row);
        this.loadPlan(immoId);
        this.loadSituation(immoId);
      },
      error: (err) => {
        this.loading.set(false);
        void this.dialogs.error(err.error?.detail ?? 'Immobilisation introuvable').subscribe();
      },
    });
  }

  private loadPlan(immoId: string): void {
    this.api.get<AmortRow[]>(`/amortissements/immobilisation/${immoId}`).subscribe({
      next: (rows) => {
        const year = this.anneeExercice();
        const prefix = `${year}-`;
        this.lignes.set(
          rows.filter((r) => !r.simule && !r.annule && r.periode.startsWith(prefix)),
        );
        this.loading.set(false);
      },
      error: () => {
        this.lignes.set([]);
        this.loading.set(false);
      },
    });
  }

  private loadSituation(immoId: string): void {
    this.api
      .get<{ cumul_amortissement: string; vnc: string }>(`/immobilisations/${immoId}/situation-comptable`)
      .subscribe({
        next: (sit) => this.situation.set(sit),
        error: () => this.situation.set(null),
      });
  }

  export(format: 'xlsx' | 'pdf'): void {
    const immo = this.immo();
    if (!immo) {
      return;
    }
    this.exporting.set(format);
    this.api
      .download(`/amortissements/immobilisation/${immo.id}/export`, {
        format,
        annee: String(this.anneeExercice()),
      })
      .subscribe({
        next: (blob) => {
          this.exporting.set(null);
          const ext = format === 'pdf' ? 'pdf' : 'xlsx';
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `fiche-amortissement-${immo.code_inventaire}-${this.anneeExercice()}.${ext}`;
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
