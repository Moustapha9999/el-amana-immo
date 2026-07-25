import { DatePipe } from '@angular/common';
import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface CompteNatureLigne {
  immobilisation_id: string;
  code_inventaire: string;
  date_acquisition: string | null;
  quantite: number;
  designation: string;
  valeur_acquisition: number;
  taux: number | null;
  amorts_cumules_n1: number;
  dotations_annee: number;
  amorts_cumules_n: number;
  vnc: number;
  agence_code: string | null;
  agence_libelle: string | null;
}

interface CompteNatureGroupe {
  compte_immobilisation: string;
  intitule: string;
  lignes: CompteNatureLigne[];
  totaux: CompteNatureLigne;
}

interface CompteOption {
  numero: string;
  libelle: string;
}

interface ComptesParNatureResponse {
  annee: number;
  date_arrete: string;
  groupes: CompteNatureGroupe[];
  totaux: CompteNatureLigne;
  compte_filtre: string | null;
  comptes_disponibles: CompteOption[];
}

@Component({
  selector: 'app-comptes',
  imports: [ReactiveFormsModule, MontantPipe, DatePipe, MatButtonModule, MatIconModule, RouterLink],
  templateUrl: './comptes.component.html',
  styleUrl: './comptes.component.css',
})
export class ComptesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<ComptesParNatureResponse | null>(null);
  readonly loading = signal(false);
  readonly exporting = signal<'xlsx' | 'pdf' | null>(null);

  readonly filterForm = this.fb.nonNullable.group({
    annee: [new Date().getFullYear()],
    compte: [''],
  });

  readonly comptesOptions = computed(() => this.data()?.comptes_disponibles ?? []);
  readonly singleCompte = computed(() => !!this.data()?.compte_filtre);
  readonly hasLignes = computed(() =>
    (this.data()?.groupes ?? []).some((g) => g.lignes.length > 0),
  );

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee || annee < 2000 || annee > 2100) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    const compte = (this.filterForm.controls.compte.value || '').trim();
    const params: Record<string, string | number> = { annee };
    if (compte) {
      params['compte'] = compte;
    }
    this.loading.set(true);
    this.api.get<ComptesParNatureResponse>('/reporting/comptes-par-nature', params).subscribe({
      next: (res) => {
        this.data.set(res);
        this.loading.set(false);
      },
      error: (err: { error?: { detail?: unknown } }) => {
        this.loading.set(false);
        const detail = err.error?.detail;
        void this.dialogs
          .error(typeof detail === 'string' ? detail : 'Impossible de charger les comptes')
          .subscribe();
      },
    });
  }

  agenceLabel(row: CompteNatureLigne): string {
    return row.agence_libelle || row.agence_code || '—';
  }

  export(format: 'xlsx' | 'pdf'): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee) {
      return;
    }
    const compte = (this.filterForm.controls.compte.value || '').trim();
    const params: Record<string, string> = {
      annee: String(annee),
      format,
    };
    if (compte) {
      params['compte'] = compte;
    }
    this.exporting.set(format);
    this.api.download('/reporting/comptes-par-nature/export', params).subscribe({
      next: (blob) => {
        this.exporting.set(null);
        const suffix = compte ? `-${compte}` : '';
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `comptes-par-nature-${annee}${suffix}.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
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
