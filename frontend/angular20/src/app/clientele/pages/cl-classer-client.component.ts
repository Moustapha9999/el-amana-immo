import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, MODES_DECISION, SOURCE_IMPORT_HEBDO, dateHeureFr, n } from '../clientele.models';

interface Resultat {
  racine_client: string; raison_sociale: string; prenoms: string | null; nni: string | null; nif: string | null;
  source_fiche: string; nb_comptes: number;
  classification: { niveau: string; source: string; mode_decision: string | null; classifie_le: string | null } | null;
}

@Component({
  selector: 'bea-cl-classer-client',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top"><div><h2>Classer un client</h2>
        <p class="bea-cl-hint">Recherche par identifiant stable (racine, compte, RIB, NNI, NIF) ou par nom. La décision se prend sur la fiche : niveau, motif et analyste KYC obligatoires, historique conservé.</p></div>
      </div>
      <div class="bea-cl-filters" style="align-items:flex-end">
        <label style="flex:1;min-width:18rem">Client
          <input [(ngModel)]="q" (keyup.enter)="chercher(1)" maxlength="60" placeholder="Racine, compte, RIB, NNI, NIF ou nom" />
        </label>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="chercher(1)" [disabled]="busy() || q.trim().length < 2"><mat-icon>search</mat-icon> Rechercher</button>
      </div>
      @if (cherche()) {
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Racine</th><th>Nom</th><th>NNI / NIF</th><th>Comptes</th><th>Classification</th><th>Décision</th><th></th></tr></thead>
            <tbody>
              @for (r of resultats(); track r.racine_client) {
                <tr>
                  <td><code>{{ r.racine_client }}</code></td>
                  <td>{{ r.raison_sociale }} {{ r.prenoms || '' }}
                    @if (r.source_fiche === hebdo) { <span class="bea-cl-badge" data-s="A_VERIFIER" title="Fiche créée par l’import hebdomadaire, sans compte ORION">import hebdo</span> }
                  </td>
                  <td>{{ r.nni || '—' }} / {{ r.nif || '—' }}</td>
                  <td>{{ n(r.nb_comptes) }}</td>
                  <td>@if (r.classification; as k) { <span class="bea-cl-badge" [attr.data-s]="k.niveau">{{ k.niveau }}</span> } @else { Non classé }</td>
                  <td>@if (r.classification; as k) { {{ modes[k.mode_decision || ''] || k.source }} <small class="bea-cl-hint">{{ dh(k.classifie_le) }}</small> } @else { — }</td>
                  <td><a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/clientele/clients', r.racine_client]"><mat-icon>gavel</mat-icon> Fiche et décision</a></td>
                </tr>
              } @empty {
                <tr><td colspan="7"><div class="bea-cl-empty">Aucun client trouvé. Un client absent du référentiel arrive par l’import ORION ou, après décision, par l’import hebdomadaire.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
        @if (total() > 25) {
          <div class="bea-cl-pager">
            <span>{{ n(total()) }} résultat(s) · page {{ page() }}</span>
            <span class="bea-cl-pager__btns">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="chercher(page() - 1)"><mat-icon>chevron_left</mat-icon></button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() * 25 >= total()" (click)="chercher(page() + 1)"><mat-icon>chevron_right</mat-icon></button>
            </span>
          </div>
        }
      }
    </section>
  `,
})
export class ClClasserClientComponent {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly resultats = signal<Resultat[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly busy = signal(false);
  readonly cherche = signal(false);
  readonly modes = MODES_DECISION;
  readonly hebdo = SOURCE_IMPORT_HEBDO;
  readonly n = n;
  readonly dh = dateHeureFr;
  q = '';

  chercher(page: number): void {
    const q = this.q.trim();
    if (q.length < 2) return;
    this.busy.set(true);
    this.api.get<{ total: number; items: Resultat[] }>(`${CL_BASE}/classification/recherche`, { q, page, taille: 25 }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.resultats.set(r.items);
        this.total.set(r.total);
        this.page.set(page);
        this.cherche.set(true);
      },
      error: (e) => {
        this.busy.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Recherche impossible'));
      },
    });
  }
}
