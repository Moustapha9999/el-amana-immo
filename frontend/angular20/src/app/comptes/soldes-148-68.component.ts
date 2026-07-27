import { MontantPipe } from '../shared/montant.pipe';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface SoldeNatureLigne {
  nature_code: string;
  nature: string;
  compte_immobilisation: string;
  compte_amortissement: string | null;
  libelle_amortissement: string | null;
  solde_148: number;
  solde_148_n1: number;
  compte_dotation: string | null;
  libelle_dotation: string | null;
  solde_68: number;
  valeur_brute: number;
  vnc: number;
  nb_biens: number;
}

interface Soldes14868Response {
  annee: number;
  date_arrete: string;
  lignes: SoldeNatureLigne[];
  total_148: number;
  total_148_n1: number;
  total_68: number;
  total_valeur_brute: number;
  total_vnc: number;
  nb_biens: number;
}

@Component({
  selector: 'app-soldes-148-68',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MontantPipe,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
  ],
  templateUrl: './soldes-148-68.component.html',
  styleUrl: './soldes-148-68.component.css',
})
export class Soldes14868Component implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly data = signal<Soldes14868Response | null>(null);
  readonly loading = signal(false);

  readonly columns = [
    'nature',
    'compte_immo',
    'compte_148',
    'vb',
    'solde_148_n1',
    'solde_68',
    'solde_148',
    'compte_68',
    'vnc',
    'nb',
  ];

  readonly filterForm = this.fb.nonNullable.group({
    annee: [new Date().getFullYear()],
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const annee = Number(this.filterForm.controls.annee.value);
    if (!annee || annee < 2000 || annee > 2100) {
      void this.dialogs.error('Année invalide').subscribe();
      return;
    }
    this.loading.set(true);
    this.api.get<Soldes14868Response>('/reporting/soldes-148-68', { annee }).subscribe({
      next: (res) => {
        this.data.set(res);
        this.loading.set(false);
      },
      error: (err: { error?: { detail?: unknown } }) => {
        this.loading.set(false);
        const detail = err.error?.detail;
        void this.dialogs
          .error(typeof detail === 'string' ? detail : 'Impossible de charger les soldes 148 / 68')
          .subscribe();
      },
    });
  }
}
