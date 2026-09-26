import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';

interface Missing {
  code: string;
  label: string;
  module_code: string;
  source_type: string;
  source_id: string;
  reference: string | null;
  detail: string | null;
}

@Component({
  selector: 'bea-archives-missing',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    <section class="bea-mg">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Suivi</p>
          <h1>Documents manquants</h1>
        </div>
        <span class="bea-mg__count">{{ rows().length }} a verifier</span>
      </header>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      <div class="bea-mg__panel">
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr><th>Controle</th><th>Module</th><th>Reference</th><th>Detail</th><th></th></tr>
            </thead>
            <tbody>
              @for (r of rows(); track r.source_id + r.code) {
                <tr>
                  <td>{{ r.label }}</td>
                  <td>{{ r.module_code }}</td>
                  <td><code class="bea-mg__code">{{ r.reference || r.source_id }}</code></td>
                  <td>{{ r.detail || '—' }}</td>
                  <td>
                    <a class="bea-mg__icon-btn" [routerLink]="['/archives-mg/dossiers', r.module_code, r.source_type, r.source_id]" title="Dossier">
                      <mat-icon>account_tree</mat-icon>
                    </a>
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="5"><div class="bea-mg__empty"><mat-icon>check_circle</mat-icon><p>Aucun ecart a verifier.</p></div></td></tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `,
})
export class ArchivesMissingComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly rows = signal<Missing[]>([]);
  readonly erreur = signal('');

  ngOnInit(): void {
    this.api.get<Missing[]>('/mg/archives/missing').subscribe({
      next: (rows) => this.rows.set(rows),
      error: () => this.erreur.set('Controle indisponible.'),
    });
  }
}
