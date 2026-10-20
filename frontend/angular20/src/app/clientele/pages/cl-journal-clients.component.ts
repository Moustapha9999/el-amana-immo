import { ChangeDetectionStrategy, Component, effect, input, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, EntreeJournal, LIBELLES_ACTION, PageJournal, dateHeureFr, n } from '../clientele.models';

const TAILLE = 50;

@Component({
  selector: 'bea-cl-journal-clients',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top"><div><h2>{{ racine() ? 'Journal du client' : 'Journal des actions clients' }}</h2>
        <p class="bea-cl-hint">Créations, mises à jour de données, propositions, acceptations, modifications et rejets. Journal non modifiable.</p></div>
        <span class="bea-mg__count">{{ n(total()) }}</span>
      </div>
      @if (!racine()) {
        <div class="bea-cl-filters">
          <label>Action
            <select [(ngModel)]="type" (ngModelChange)="charger(1)">
              <option value="">Toutes</option>
              @for (a of actions; track a[0]) { <option [value]="a[0]">{{ a[1] }}</option> }
            </select>
          </label>
          <label>Source
            <select [(ngModel)]="origine" (ngModelChange)="charger(1)">
              <option value="">Toutes</option><option value="SAISIE">Saisie manuelle</option><option value="IMPORT">Import</option>
            </select>
          </label>
          <label>Racine <input [(ngModel)]="filtreRacine" maxlength="6" inputmode="numeric" (keyup.enter)="charger(1)" placeholder="000001" /></label>
        </div>
      }
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table">
          <thead><tr><th class="c-date">Date</th>@if (!racine()) {<th class="c-lg">Client</th>}<th class="c-md">Action</th><th class="c-sm">Champ</th><th class="c-lg">Ancienne → nouvelle</th><th class="c-xl">Motif</th><th class="c-md">Analyste KYC</th><th class="c-sm">Source</th><th class="c-md">Utilisateur</th></tr></thead>
          <tbody>
            @for (j of items(); track j.id) {
              <tr>
                <td>{{ dh(j.date) }}</td>
                @if (!racine()) {
                  <td><a [routerLink]="['/clientele/clients', j.racine_client]"><code>{{ j.racine_client }}</code></a> {{ j.nom_client || '' }}</td>
                }
                <td><span class="bea-cl-badge" [attr.data-s]="j.type_action">{{ j.libelle_action }}</span></td>
                <td>{{ j.champ || '—' }}</td>
                <td>{{ j.ancienne_valeur || '—' }} → <strong>{{ j.nouvelle_valeur || '—' }}</strong></td>
                <td>{{ j.motif || '—' }}</td>
                <td>{{ j.analyste_kyc || '—' }}</td>
                <td>{{ j.origine === 'IMPORT' ? 'Import' + (j.ligne_source ? ' · L' + j.ligne_source : '') : 'Saisie' }}@if (j.groupe_id) { <small class="bea-cl-hint"> · groupe</small> }</td>
                <td>{{ j.utilisateur || '—' }}</td>
              </tr>
            } @empty {
              <tr><td [attr.colspan]="racine() ? 8 : 9"><div class="bea-cl-empty">Aucune action journalisée.</div></td></tr>
            }
          </tbody>
        </table>
      </div>
      @if (total() > taille) {
        <div class="bea-cl-pager">
          <span>Page {{ page() }} · {{ n(total()) }} action(s)</span>
          <span class="bea-cl-pager__btns">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="charger(page() - 1)"><mat-icon>chevron_left</mat-icon></button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() * taille >= total()" (click)="charger(page() + 1)"><mat-icon>chevron_right</mat-icon></button>
          </span>
        </div>
      }
    </section>
  `,
})
export class ClJournalClientsComponent {
  private readonly api = inject(ApiService);
  readonly racine = input<string | null>(null);
  /** Incrémentée par le parent après une décision : recharge le journal. */
  readonly version = input(0);
  readonly items = signal<EntreeJournal[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly actions = Object.entries(LIBELLES_ACTION);
  readonly taille = TAILLE;
  readonly n = n;
  readonly dh = dateHeureFr;
  type = '';
  origine = '';
  filtreRacine = '';

  constructor() {
    effect(() => {
      this.racine();
      this.version();
      untracked(() => this.charger(1));
    });
  }

  charger(page: number): void {
    const r = this.racine();
    const params: Record<string, string | number> = { page, taille: TAILLE };
    if (!r) {
      if (this.type) params['type_action'] = this.type;
      if (this.origine) params['origine'] = this.origine;
      if (this.filtreRacine.trim()) params['racine'] = this.filtreRacine.trim().padStart(6, '0');
    }
    const url = r ? `${CL_BASE}/clients/${r}/journal` : `${CL_BASE}/classification/journal`;
    this.api.get<PageJournal>(url, params).subscribe({
      next: (p) => { this.items.set(p.items); this.total.set(p.total); this.page.set(page); },
      error: () => { this.items.set([]); this.total.set(0); },
    });
  }
}
