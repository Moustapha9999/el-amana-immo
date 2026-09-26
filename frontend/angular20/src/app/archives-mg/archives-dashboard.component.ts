import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';

interface DashDoc {
  id: string;
  filename: string;
  module_code: string;
  entity: string;
  created_at: string | null;
}

interface Dashboard {
  total: number;
  ce_mois: number;
  cette_annee: number;
  achats: number;
  stock: number;
  notes: number;
  contrats: number;
  manquants: number;
  corbeille: number;
  par_module: { module_code: string; label: string; count: number }[];
  par_type: { type: string; count: number }[];
  recents: DashDoc[];
}

@Component({
  selector: 'bea-archives-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, DatePipe],
  template: `
    <section class="bea-mg bea-nf">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Generaux</p>
          <h1>Archives — Tableau de bord</h1>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/archives-mg/documents">
            <mat-icon>folder_open</mat-icon> Tous les documents
          </a>
          <a class="bea-mg__btn" routerLink="/archives-mg/documents" [queryParams]="{ upload: 1 }">
            <mat-icon>upload_file</mat-icon> Ajouter
          </a>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (d(); as dash) {
        <div class="bea-nf-kpi">
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents">
            <p>Documents archives</p><strong>{{ dash.total }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ recent_days: 31 }">
            <p>Ce mois</p><strong>{{ dash.ce_mois }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ year: currentYear }">
            <p>Cette annee</p><strong>{{ dash.cette_annee }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ module_code: 'achats-appro' }">
            <p>Achats</p><strong>{{ dash.achats }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ module_code: 'stock-fournitures' }">
            <p>Stock</p><strong>{{ dash.stock }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ module_code: 'notes-frais' }">
            <p>Notes de frais</p><strong>{{ dash.notes }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/documents" [queryParams]="{ module_code: 'contrats-echeances' }">
            <p>Contrats</p><strong>{{ dash.contrats }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/manquants">
            <p>Documents manquants</p><strong>{{ dash.manquants }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/archives-mg/corbeille">
            <p>Corbeille</p><strong>{{ dash.corbeille }}</strong>
          </a>
        </div>

        <div class="bea-mg__panel" style="margin-top:1rem">
          <div class="bea-mg__panel-top">
            <h2>Documents recents</h2>
            <span class="bea-mg__count">{{ dash.recents.length }}</span>
          </div>
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table">
              <thead>
                <tr><th>Fichier</th><th>Module</th><th>Entite</th><th>Date</th></tr>
              </thead>
              <tbody>
                @for (r of dash.recents; track r.id) {
                  <tr>
                    <td>
                      <a [routerLink]="['/archives-mg/documents', r.id]">{{ r.filename }}</a>
                    </td>
                    <td>{{ r.module_code }}</td>
                    <td>{{ r.entity }}</td>
                    <td>{{ r.created_at ? (r.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                  </tr>
                } @empty {
                  <tr><td colspan="4"><div class="bea-mg__empty"><p>Aucun document archive.</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }
    </section>
  `,
})
export class ArchivesDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly d = signal<Dashboard | null>(null);
  readonly erreur = signal<string | null>(null);
  readonly currentYear = new Date().getFullYear();

  ngOnInit(): void {
    this.api.get<Dashboard>('/mg/archives/dashboard').subscribe({
      next: (row) => this.d.set(row),
      error: () => this.erreur.set('Tableau de bord archives indisponible.'),
    });
  }
}
