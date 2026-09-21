import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../core/services/api.service';

interface Rapport {
  periode: string;
  granularity: string;
  lignes: { famille: string; code: string; designation: string; quantite: number }[];
}

interface Agence {
  id: string;
  libelle: string;
}

@Component({
  selector: 'bea-stock-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <h1>Rapports de consommation</h1>
          <p>Mensuel / annuel — exports Excel &amp; PDF (charte BEA, logo).</p>
        </div>
      </header>

      <form class="bea-stock-toolbar" [formGroup]="form" (ngSubmit)="load()">
        <label>Année <input type="number" formControlName="year" /></label>
        <label>
          Mois
          <select formControlName="month">
            <option value="">Année entière</option>
            @for (m of months; track m) {
              <option [value]="m">{{ m }}</option>
            }
          </select>
        </label>
        <label>
          Agence
          <select formControlName="agence_id">
            <option value="">Toutes</option>
            @for (a of agences(); track a.id) {
              <option [value]="a.id">{{ a.libelle }}</option>
            }
          </select>
        </label>
        <button type="submit" class="bea-admin-btn">Afficher</button>
        <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="exportFile('xlsx')">Excel</button>
        <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="exportFile('pdf')">PDF</button>
        <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="exportFile('csv')">CSV</button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (rapport(); as r) {
        <div class="bea-stock-panel">
          <h2>Période {{ r.periode }} ({{ r.granularity }})</h2>
          <table class="bea-stock-table">
            <thead>
              <tr>
                <th>Famille</th>
                <th>Code</th>
                <th>Désignation</th>
                <th>Quantité sortie</th>
              </tr>
            </thead>
            <tbody>
              @for (l of r.lignes; track l.code + l.designation) {
                <tr>
                  <td>{{ l.famille }}</td>
                  <td>{{ l.code }}</td>
                  <td>{{ l.designation }}</td>
                  <td>{{ l.quantite }}</td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="4">Aucune consommation sur la période.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>
  `,
})
export class StockRapportsComponent {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly months = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
  readonly agences = signal<Agence[]>([]);
  readonly rapport = signal<Rapport | null>(null);
  readonly erreur = signal('');

  readonly form = this.fb.nonNullable.group({
    year: [new Date().getFullYear(), Validators.required],
    month: [''],
    agence_id: [''],
  });

  constructor() {
    this.api.get<Agence[]>('/mg/stock/agences').subscribe((a) => this.agences.set(a));
  }

  private params(): Record<string, string> {
    const v = this.form.getRawValue();
    const p: Record<string, string> = { year: String(v.year) };
    if (v.month) p['month'] = String(v.month);
    if (v.agence_id) p['agence_id'] = v.agence_id;
    return p;
  }

  load(): void {
    this.erreur.set('');
    this.api.get<Rapport>('/mg/stock/rapports/consommation', this.params()).subscribe({
      next: (r) => this.rapport.set(r),
      error: () => this.erreur.set('Rapport indisponible (permission export ?)'),
    });
  }

  exportFile(format: 'csv' | 'xlsx' | 'pdf'): void {
    const p = { ...this.params(), format };
    this.api.download('/mg/stock/rapports/consommation', p).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `conso-${this.form.value.year}.${format === 'xlsx' ? 'xlsx' : format}`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible`),
    });
  }
}