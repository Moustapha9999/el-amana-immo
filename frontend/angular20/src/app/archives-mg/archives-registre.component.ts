import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/services/api.service';

interface Doc {
  id: string;
  filename: string | null;
  module_code: string | null;
  entity: string | null;
  created_at: string | null;
  size_bytes: number | null;
}

@Component({
  selector: 'bea-archives-registre',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Archives</p>
          <h1>Registre documentaire MG</h1>
          <p>Documents GED de l’espace Moyens Généraux.</p>
        </div>
      </header>
      <div class="bea-stock-form__grid">
        <label>Module
          <select [(ngModel)]="moduleFilter" (ngModelChange)="load()">
            <option value="">Tous</option>
            <option value="stock-fournitures">Stock</option>
            <option value="achats-appro">Achats</option>
            <option value="notes-frais">Notes de frais</option>
            <option value="contrats-echeances">Contrats</option>
          </select>
        </label>
        <label>Recherche <input [(ngModel)]="q" (keyup.enter)="load()" /></label>
        <button type="button" class="bea-admin-btn" (click)="load()">Filtrer</button>
      </div>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      <table class="bea-stock-table">
        <thead><tr><th>Fichier</th><th>Module</th><th>Entité</th><th>Date</th><th>Taille</th></tr></thead>
        <tbody>
          @for (d of docs(); track d.id) {
            <tr>
              <td>{{ d.filename }}</td>
              <td>{{ d.module_code }}</td>
              <td>{{ d.entity }}</td>
              <td>{{ d.created_at }}</td>
              <td>{{ d.size_bytes }}</td>
            </tr>
          } @empty {
            <tr><td colspan="5">Aucun document.</td></tr>
          }
        </tbody>
      </table>
    </section>
  `,
})
export class ArchivesRegistreComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly docs = signal<Doc[]>([]);
  readonly erreur = signal<string | null>(null);
  moduleFilter = '';
  q = '';

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const params = new URLSearchParams();
    if (this.moduleFilter) params.set('module_code', this.moduleFilter);
    if (this.q.trim()) params.set('q', this.q.trim());
    const qs = params.toString();
    this.api.get<Doc[]>(`/mg/archives/documents${qs ? '?' + qs : ''}`).subscribe({
      next: (rows) => this.docs.set(rows),
      error: () => this.erreur.set('Chargement archives impossible.'),
    });
  }
}
