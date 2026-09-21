import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { PaginationComponent } from '../shared/pagination.component';

interface Doc {
  id: string;
  filename: string | null;
  module_code: string | null;
  entity: string | null;
  entity_id: string | null;
  created_at: string | null;
  size_bytes: number | null;
}
interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

@Component({
  selector: 'bea-archives-registre',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, DatePipe, RouterLink, PaginationComponent],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Archives</p>
          <h1>Registre documentaire MG</h1>
        </div>
        <div class="bea-mg__actions">
          <span class="bea-mg__count">{{ total() }} document(s)</span>
        </div>
      </header>

      <form class="bea-mg__search" (ngSubmit)="$event.preventDefault(); applyFilters()">
        <label class="bea-mg__field">
          <mat-icon>folder</mat-icon>
          <select [(ngModel)]="moduleFilter" name="module" (ngModelChange)="applyFilters()">
            <option value="">Tous les modules</option>
            <option value="stock-fournitures">Stock</option>
            <option value="achats-appro">Achats</option>
            <option value="notes-frais">Notes de frais</option>
            <option value="contrats-echeances">Contrats</option>
          </select>
        </label>
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input
            [(ngModel)]="q"
            name="q"
            placeholder="Rechercher fichier, module, entité…"
            (keyup.enter)="applyFilters()"
          />
        </label>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="applyFilters()">
          <mat-icon>filter_list</mat-icon> Filtrer
        </button>
      </form>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Documents GED</h2>
          <span class="bea-mg__count">Espace Moyens Généraux</span>
        </div>
        <div style="overflow-x:auto">
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Fichier</th>
                <th>Module</th>
                <th>Entité</th>
                <th>Date</th>
                <th>Taille</th>
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (d of docs(); track d.id; let i = $index) {
                <tr [style.--i]="i">
                  <td>{{ d.filename || '—' }}</td>
                  <td>{{ moduleLabel(d.module_code) }}</td>
                  <td>{{ entityLabel(d.entity) }}</td>
                  <td>{{ d.created_at ? (d.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                  <td>{{ sizeLabel(d.size_bytes) }}</td>
                  <td class="bea-mg__actions-cell">
                    <button
                      type="button"
                      class="bea-mg__icon-btn"
                      title="Télécharger"
                      (click)="download(d)"
                    >
                      <mat-icon>download</mat-icon>
                    </button>
                    @if (entityLink(d); as link) {
                      <a class="bea-mg__icon-btn" [routerLink]="link" title="Ouvrir la fiche">
                        <mat-icon>open_in_new</mat-icon>
                      </a>
                    }
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6">
                    <div class="bea-mg__empty">
                      <mat-icon>folder_open</mat-icon>
                      <p>Aucun document pour ces critères.</p>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (total() > 0) {
          <app-pagination
            [page]="page()"
            [total]="total()"
            [pageSize]="pageSize"
            label="document(s)"
            (pageChange)="goToPage($event)"
          />
        }
      </div>
    </section>
  `,
  styles: `
    a.bea-mg__icon-btn {
      text-decoration: none;
      color: inherit;
    }
  `,
})
export class ArchivesRegistreComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly docs = signal<Doc[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 50;
  readonly erreur = signal<string | null>(null);
  moduleFilter = '';
  q = '';

  ngOnInit(): void {
    this.load();
  }

  moduleLabel(code: string | null): string {
    const map: Record<string, string> = {
      'stock-fournitures': 'Stock',
      'achats-appro': 'Achats',
      'notes-frais': 'Notes de frais',
      'contrats-echeances': 'Contrats',
    };
    return (code && map[code]) || code || '—';
  }

  entityLabel(entity: string | null): string {
    const map: Record<string, string> = {
      article: 'Article',
      demande_fourniture: 'Demande',
      inventaire: 'Inventaire',
      bon_commande: 'Bon de commande',
      note_frais: 'Note de frais',
      contrat: 'Contrat',
    };
    return (entity && map[entity]) || entity || '—';
  }

  sizeLabel(bytes: number | null): string {
    if (bytes == null) return '—';
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  }

  entityLink(d: Doc): string[] | null {
    if (!d.module_code || !d.entity || !d.entity_id) return null;
    const id = d.entity_id;
    if (d.module_code === 'stock-fournitures') {
      if (d.entity === 'article') return ['/stock-fournitures/articles', id];
      if (d.entity === 'demande_fourniture') return ['/stock-fournitures/demandes', id];
      if (d.entity === 'inventaire') return ['/stock-fournitures/inventaires'];
    }
    if (d.module_code === 'achats-appro' && d.entity === 'bon_commande') {
      return ['/achats-appro/bons', id];
    }
    if (d.module_code === 'notes-frais' && d.entity === 'note_frais') {
      return ['/notes-frais/notes', id];
    }
    if (d.module_code === 'contrats-echeances' && d.entity === 'contrat') {
      return ['/contrats-echeances', id];
    }
    return null;
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  load(): void {
    this.erreur.set(null);
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.pageSize,
    };
    if (this.moduleFilter) params['module_code'] = this.moduleFilter;
    if (this.q.trim()) params['q'] = this.q.trim();
    this.api.get<Paginated<Doc>>('/mg/archives/documents', params).subscribe({
      next: (res) => {
        this.docs.set(res.items);
        this.total.set(res.total);
      },
      error: () => {
        this.docs.set([]);
        this.total.set(0);
        this.erreur.set('Chargement archives impossible.');
      },
    });
  }

  download(d: Doc): void {
    this.api.download(`/ged/documents/${d.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = d.filename || 'document';
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Téléchargement impossible (permission ged.read ?).'),
    });
  }
}
