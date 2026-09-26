import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

interface ReportJson {
  key: string;
  title: string;
  headers: string[];
  rows: (string | number)[][];
  count: number;
}

@Component({
  selector: 'bea-contrats-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting</p>
          <h1>Rapports contrats</h1>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/contrats-echeances/dashboard">Dashboard</a>
      </header>

      <form class="bea-mg__search" [formGroup]="filters">
        <label class="bea-mg__field">
          <select formControlName="key" (change)="load()">
            <option value="liste">Liste des contrats</option>
            <option value="actifs">Contrats actifs</option>
            <option value="expires">Contrats expirés</option>
            <option value="echeances">Échéances à 90 jours</option>
          </select>
        </label>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="download('xlsx')">Excel</button>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="download('pdf')">PDF</button>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="download('csv')">CSV</button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
      @if (report(); as r) {
        @if (r.count === 0) {
          <div class="bea-ct-empty"><mat-icon>assessment</mat-icon><p>Aucune donnée pour ce rapport.</p></div>
        } @else {
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table">
              <thead>
                <tr>
                  @for (h of r.headers; track h) { <th>{{ h }}</th> }
                </tr>
              </thead>
              <tbody>
                @for (row of r.rows; track $index; let i = $index) {
                  <tr class="bea-ct-row" [style.animation-delay.ms]="i * 30">
                    @for (cell of row; track $index) { <td>{{ cell }}</td> }
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      }
    </section>
  `,
})
export class ContratsRapportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly filters = this.fb.nonNullable.group({ key: ['liste'] });
  readonly report = signal<ReportJson | null>(null);
  readonly erreur = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const key = this.filters.getRawValue().key;
    this.erreur.set(null);
    this.api.get<ReportJson>(`/mg/contrats/rapports/${key}`, { fmt: 'json' }).subscribe({
      next: (r) => this.report.set(r),
      error: () => this.erreur.set('Rapport indisponible.'),
    });
  }

  download(fmt: 'xlsx' | 'pdf' | 'csv'): void {
    const key = this.filters.getRawValue().key;
    this.api.download(`/mg/contrats/rapports/${key}`, { fmt }).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `contrats-${key}.${fmt === 'xlsx' ? 'xlsx' : fmt}`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Export impossible. Vérifiez le droit d’export ou l’absence de données.'),
    });
  }
}
