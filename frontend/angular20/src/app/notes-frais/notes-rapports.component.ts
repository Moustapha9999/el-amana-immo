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
  selector: 'bea-notes-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting</p>
          <h1>Rapports notes de frais</h1>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/notes-frais">Dashboard</a>
      </header>

      <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="load()">
        <label class="bea-mg__field">
          <select formControlName="key" (change)="load()">
            <option value="periode">Par période</option>
            <option value="agence">Par intitulé</option>
            <option value="demandeur">Par demandeur</option>
            <option value="categorie">Par catégorie</option>
            <option value="paiement">Paiements</option>
            <option value="attente">En attente</option>
            <option value="annuel">Annuel</option>
          </select>
        </label>
        <label class="bea-mg__field">
          <input type="number" formControlName="annee" placeholder="Année" (change)="load()" />
        </label>
        <label class="bea-mg__field">
          <input type="number" formControlName="mois" placeholder="Mois" min="1" max="12" (change)="load()" />
        </label>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="download('xlsx')">Excel</button>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="download('pdf')">PDF</button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (report(); as r) {
        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>{{ r.title }}</h2>
            <span class="bea-mg__count">{{ r.count }} ligne(s)</span>
          </div>
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table">
              <thead>
                <tr>
                  @for (h of r.headers; track h) {
                    <th>{{ h }}</th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of r.rows; track $index) {
                  <tr>
                    @for (cell of row; track $index) {
                      <td>{{ cell }}</td>
                    }
                  </tr>
                } @empty {
                  <tr>
                    <td [attr.colspan]="r.headers.length">
                      <div class="bea-mg__empty"><p>Aucune donnée disponible.</p></div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }
    </section>
  `,
})
export class NotesRapportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly report = signal<ReportJson | null>(null);
  readonly erreur = signal('');

  readonly filters = this.fb.nonNullable.group({
    key: 'periode',
    annee: String(new Date().getFullYear()),
    mois: '',
  });

  ngOnInit(): void {
    this.load();
  }

  params(): Record<string, string | number> {
    const v = this.filters.getRawValue();
    const p: Record<string, string | number> = { format: 'json' };
    if (v.annee) p['annee'] = Number(v.annee);
    if (v.mois) p['mois'] = Number(v.mois);
    return p;
  }

  load(): void {
    this.erreur.set('');
    const key = this.filters.value.key || 'periode';
    this.api.get<ReportJson>(`/mg/notes-frais/rapports/${key}`, this.params()).subscribe({
      next: (r) => this.report.set(r),
      error: (err) => {
        this.report.set(null);
        this.erreur.set(err?.error?.detail || 'Rapport indisponible');
      },
    });
  }

  download(format: 'xlsx' | 'pdf'): void {
    const key = this.filters.value.key || 'periode';
    const params = { ...this.params(), format };
    this.api.download(`/mg/notes-frais/rapports/${key}`, params).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `notes-${key}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set(`Export ${format.toUpperCase()} impossible`),
    });
  }
}
