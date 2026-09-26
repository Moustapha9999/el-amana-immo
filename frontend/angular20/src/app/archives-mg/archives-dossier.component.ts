import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { DatePipe } from '@angular/common';
import { ApiService } from '../core/services/api.service';

interface Doc {
  id: string;
  filename: string;
  module_code: string;
  entity: string;
  entity_id: string;
  created_at: string | null;
}

interface Dossier {
  source_module: string;
  source_type: string;
  source_id: string;
  nodes: { module_code: string; entity: string; entity_id: string }[];
  documents: Doc[];
  count: number;
}

@Component({
  selector: 'bea-archives-dossier',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, DatePipe],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Dossier documentaire</p>
          <h1>{{ title() }}</h1>
        </div>
        <a class="bea-mg__btn" routerLink="/archives-mg/documents"><mat-icon>arrow_back</mat-icon> Retour</a>
      </header>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (d(); as dossier) {
        <div class="bea-mg__panel" style="margin-bottom:1rem">
          <div class="bea-mg__panel-top"><h2>Objets lies</h2><span class="bea-mg__count">{{ dossier.nodes.length }}</span></div>
          <ul>
            @for (n of dossier.nodes; track n.entity_id + n.entity) {
              <li><code>{{ n.entity }}</code> — {{ n.entity_id }}</li>
            }
          </ul>
        </div>
        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Documents</h2><span class="bea-mg__count">{{ dossier.count }}</span></div>
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table">
              <thead><tr><th>Fichier</th><th>Entite</th><th>Date</th><th></th></tr></thead>
              <tbody>
                @for (doc of dossier.documents; track doc.id) {
                  <tr>
                    <td>{{ doc.filename }}</td>
                    <td>{{ doc.entity }}</td>
                    <td>{{ doc.created_at ? (doc.created_at | date: 'dd/MM/yyyy') : '—' }}</td>
                    <td>
                      <button type="button" class="bea-mg__icon-btn" (click)="download(doc)"><mat-icon>download</mat-icon></button>
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="4"><div class="bea-mg__empty"><p>Aucun document dans ce dossier.</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }
    </section>
  `,
})
export class ArchivesDossierComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  readonly d = signal<Dossier | null>(null);
  readonly erreur = signal('');
  readonly title = signal('Dossier');

  ngOnInit(): void {
    const p = this.route.snapshot.paramMap;
    const mod = p.get('module') || '';
    const type = p.get('type') || '';
    const id = p.get('id') || '';
    this.title.set(`Dossier ${type} ${id.slice(0, 8)}…`);
    this.api.get<Dossier>(`/mg/archives/dossiers/${mod}/${type}/${id}`).subscribe({
      next: (row) => {
        this.d.set(row);
        this.title.set(`Dossier ${row.source_type}`);
      },
      error: () => this.erreur.set('Dossier indisponible.'),
    });
  }

  download(doc: Doc): void {
    this.api.download(`/mg/archives/documents/${doc.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = doc.filename || 'document';
        a.click();
        URL.revokeObjectURL(url);
      },
    });
  }
}
