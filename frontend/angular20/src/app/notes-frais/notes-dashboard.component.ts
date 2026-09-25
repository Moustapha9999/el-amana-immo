import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';

interface Dashboard {
  total: number;
  brouillons: number;
  soumises: number;
  en_controle: number;
  en_visa: number;
  validees: number;
  a_payer: number;
  partiellement_payees: number;
  payees: number;
  rejetees: number;
  montant_total: number;
  montant_a_payer: number;
  montant_paye: number;
}

interface Alerte {
  type: string;
  titre: string;
  message: string;
  note_id: string;
  reference: string;
  statut: string;
}

@Component({
  selector: 'bea-notes-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, MontantPipe],
  template: `
    <section class="bea-mg bea-nf">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>Notes de frais</h1>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/notes-frais/notes">Registre</a>
          <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/notes-frais/nouvelle">
            <mat-icon>add</mat-icon> Nouvelle note
          </a>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (dash(); as d) {
        <div class="bea-nf-kpi">
          <article class="bea-nf-kpi__card">
            <p>Notes</p>
            <strong>{{ d.total }}</strong>
          </article>
          <article class="bea-nf-kpi__card">
            <p>Montant total</p>
            <strong>{{ d.montant_total | montant }}</strong>
          </article>
          <article class="bea-nf-kpi__card">
            <p>À payer</p>
            <strong>{{ d.montant_a_payer | montant }}</strong>
          </article>
          <article class="bea-nf-kpi__card">
            <p>Payé</p>
            <strong>{{ d.montant_paye | montant }}</strong>
          </article>
        </div>

        <div class="bea-mg__panel" style="animation: beaMgRise 0.45s ease both; animation-delay: 0.22s">
          <div class="bea-mg__panel-top"><h2>Répartition du workflow</h2></div>
          <div class="bea-mg__modal-body">
            <div class="bea-nf-split">
              <div class="bea-nf-split__item" style="animation-delay:0.05s"><strong>{{ d.brouillons }}</strong><span>Brouillons</span></div>
              <div class="bea-nf-split__item" style="animation-delay:0.08s"><strong>{{ d.soumises }}</strong><span>Soumises</span></div>
              <div class="bea-nf-split__item" style="animation-delay:0.11s"><strong>{{ d.en_controle }}</strong><span>Contrôle</span></div>
              <div class="bea-nf-split__item" style="animation-delay:0.14s"><strong>{{ d.en_visa }}</strong><span>Visas</span></div>
              <div class="bea-nf-split__item" style="animation-delay:0.17s"><strong>{{ d.validees }}</strong><span>Validées</span></div>
              <div class="bea-nf-split__item" style="animation-delay:0.2s"><strong>{{ d.a_payer }}</strong><span>À payer</span></div>
              <div class="bea-nf-split__item" style="animation-delay:0.23s"><strong>{{ d.payees }}</strong><span>Payées</span></div>
              <div class="bea-nf-split__item" style="animation-delay:0.26s"><strong>{{ d.rejetees }}</strong><span>Rejetées</span></div>
            </div>
          </div>
        </div>
      }

      <div class="bea-mg__panel" style="margin-top:1rem;animation: beaMgRise 0.45s ease both; animation-delay: 0.28s">
        <div class="bea-mg__panel-top">
          <h2>Alertes</h2>
          <span class="bea-mg__count">{{ alertes().length }}</span>
        </div>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr><th>Type</th><th>Réf.</th><th>Message</th><th></th></tr>
            </thead>
            <tbody>
              @for (a of alertes(); track a.note_id + a.type; let i = $index) {
                <tr class="bea-nf-alert-row" [style.animation-delay.ms]="i * 40">
                  <td>{{ a.titre }}</td>
                  <td><code class="bea-mg__code">{{ a.reference }}</code></td>
                  <td>{{ a.message }}</td>
                  <td class="bea-mg__actions-cell">
                    <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/notes-frais/notes', a.note_id]">Ouvrir</a>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="4">
                    <div class="bea-mg__empty">
                      <mat-icon>notifications_none</mat-icon>
                      <p>Aucune alerte.</p>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `,
})
export class NotesDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly dash = signal<Dashboard | null>(null);
  readonly alertes = signal<Alerte[]>([]);
  readonly erreur = signal('');

  ngOnInit(): void {
    this.api.get<Dashboard>('/mg/notes-frais/dashboard').subscribe({
      next: (d) => this.dash.set(d),
      error: () => this.erreur.set('Dashboard indisponible'),
    });
    this.api.get<Alerte[]>('/mg/notes-frais/alertes').subscribe({
      next: (a) => this.alertes.set(a),
      error: () => undefined,
    });
  }
}
