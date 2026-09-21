import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ApiService } from '../core/services/api.service';

interface Article {
  id: string;
  code: string;
  designation: string;
}
interface Mouvement {
  id: string;
  reference: string;
  date_mouvement: string;
  type_mouvement: string;
  article_id: string;
  quantite: number;
  motif: string | null;
}

@Component({
  selector: 'bea-stock-mouvements',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, DatePipe],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <h1>Mouvements de stock</h1>
          <p>Journal des entrées, sorties, ajustements et inventaires.</p>
        </div>
      </header>

      <form class="bea-stock-form bea-stock-panel" [formGroup]="form" (ngSubmit)="submit()">
        <label>
          Article
          <select formControlName="article_id">
            @for (a of articles(); track a.id) {
              <option [value]="a.id">{{ a.code }} — {{ a.designation }}</option>
            }
          </select>
        </label>
        <label>
          Type
          <select formControlName="type_mouvement">
            <option value="ENTREE">Entrée</option>
            <option value="SORTIE">Sortie</option>
            <option value="AJUSTEMENT">Ajustement (+)</option>
            <option value="INVENTAIRE">Inventaire (stock constaté)</option>
          </select>
        </label>
        <label>Quantité <input type="number" formControlName="quantite" min="0.001" step="0.001" /></label>
        <label>Motif <input formControlName="motif" /></label>
        <button type="submit" class="bea-admin-btn" [disabled]="form.invalid || saving()">Enregistrer</button>
      </form>
      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      <div class="bea-stock-panel">
        <table class="bea-stock-table">
          <thead>
            <tr>
              <th>Réf.</th>
              <th>Date</th>
              <th>Type</th>
              <th>Qté</th>
              <th>Motif</th>
            </tr>
          </thead>
          <tbody>
            @for (m of mouvements(); track m.id) {
              <tr>
                <td>{{ m.reference }}</td>
                <td>{{ m.date_mouvement | date: 'short' }}</td>
                <td>{{ m.type_mouvement }}</td>
                <td>{{ m.quantite }}</td>
                <td>{{ m.motif }}</td>
              </tr>
            } @empty {
              <tr>
                <td colspan="5">Aucun mouvement.</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>
  `,
})
export class StockMouvementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly articles = signal<Article[]>([]);
  readonly mouvements = signal<Mouvement[]>([]);
  readonly saving = signal(false);
  readonly erreur = signal('');

  readonly form = this.fb.nonNullable.group({
    article_id: ['', Validators.required],
    type_mouvement: ['ENTREE', Validators.required],
    quantite: [1, Validators.required],
    motif: [''],
  });

  ngOnInit(): void {
    this.api.get<Article[]>('/mg/stock/articles').subscribe((rows) => {
      this.articles.set(rows);
      if (rows[0]) this.form.patchValue({ article_id: rows[0].id });
    });
    this.reload();
  }

  reload(): void {
    this.api.get<Mouvement[]>('/mg/stock/mouvements').subscribe((rows) => this.mouvements.set(rows));
  }

  submit(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.erreur.set('');
    this.api.post('/mg/stock/mouvements', this.form.getRawValue()).subscribe({
      next: () => {
        this.saving.set(false);
        this.reload();
      },
      error: (err) => {
        this.erreur.set(err?.error?.detail || 'Mouvement refusé');
        this.saving.set(false);
      },
    });
  }
}
