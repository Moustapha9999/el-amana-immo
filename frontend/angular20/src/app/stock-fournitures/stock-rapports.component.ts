import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
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
  imports: [ReactiveFormsModule, MatIconModule, DecimalPipe],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting</p>
          <h1>Rapports de consommation</h1>
        </div>
        <div class="bea-mg__actions">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('xlsx')" title="Excel">
            <mat-icon>table_view</mat-icon> Excel
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('pdf')" title="PDF">
            <mat-icon>picture_as_pdf</mat-icon> PDF
          </button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exportFile('csv')" title="CSV">
            <mat-icon>description</mat-icon> CSV
          </button>
        </div>
      </header>

      <form class="bea-mg__search" [formGroup]="form" (ngSubmit)="load()">
        <label class="bea-mg__field">
          <mat-icon>calendar_today</mat-icon>
          <input type="number" formControlName="year" placeholder="Année" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>date_range</mat-icon>
          <select formControlName="month">
            <option value="">Année entière</option>
            @for (m of months; track m) {
              <option [value]="m">{{ monthLabel(m) }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>store</mat-icon>
          <select formControlName="agence_id">
            <option value="">Toutes les agences</option>
            @for (a of agences(); track a.id) {
              <option [value]="a.id">{{ a.libelle }}</option>
            }
          </select>
        </label>
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary">
          <mat-icon>query_stats</mat-icon> Afficher
        </button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (rapport(); as r) {
        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Période {{ r.periode }}</h2>
            <span class="bea-mg__count">{{ r.granularity }} · {{ r.lignes.length }} ligne(s)</span>
          </div>
          <div style="overflow-x:auto">
            <table class="bea-mg__table">
              <thead>
                <tr>
                  <th>Famille</th>
                  <th>Code</th>
                  <th>Désignation</th>
                  <th>Quantité sortie</th>
                </tr>
              </thead>
              <tbody>
                @for (l of r.lignes; track l.code + l.designation; let i = $index) {
                  <tr [style.--i]="i">
                    <td>{{ l.famille || '—' }}</td>
                    <td><code class="bea-mg__code">{{ l.code }}</code></td>
                    <td>{{ l.designation }}</td>
                    <td>{{ l.quantite | number: '1.0-3' }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="4">
                      <div class="bea-mg__empty">
                        <mat-icon>bar_chart</mat-icon>
                        <p>Aucune consommation sur la période.</p>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      } @else if (!erreur()) {
        <div class="bea-mg__panel">
          <div class="bea-mg__empty">
            <mat-icon>insights</mat-icon>
            <p>Choisissez une période puis cliquez sur Afficher.</p>
          </div>
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

  monthLabel(m: number): string {
    const names = [
      'Janvier',
      'Février',
      'Mars',
      'Avril',
      'Mai',
      'Juin',
      'Juillet',
      'Août',
      'Septembre',
      'Octobre',
      'Novembre',
      'Décembre',
    ];
    return names[m - 1] || String(m);
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
