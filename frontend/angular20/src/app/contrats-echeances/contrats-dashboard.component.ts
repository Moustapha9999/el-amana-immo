import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';

interface Dashboard {
  total: number;
  actifs: number;
  brouillons: number;
  en_validation: number;
  suspendus: number;
  expires: number;
  date_depassee: number;
  archives: number;
  annules: number;
  montant_actifs: number;
  paiements_a_venir: number;
  paiements_en_retard: number;
  alertes: number;
  echeance_30: number;
}

@Component({
  selector: 'bea-contrats-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, MontantPipe],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux</p>
          <h1>Contrats &amp; échéances</h1>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }

      @if (dash(); as d) {
        @if (d.total === 0) {
          <div class="bea-ct-empty">
            <mat-icon>description</mat-icon>
            <p>Aucun contrat enregistré.</p>
          </div>
        }
        <div class="bea-nf-kpi">
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/liste" [queryParams]="{ statut: 'ACTIF' }">
            <p>Contrats actifs</p><strong>{{ d.actifs }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/liste" [queryParams]="{ statut: 'BROUILLON' }">
            <p>Brouillons</p><strong>{{ d.brouillons }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/liste" [queryParams]="{ statut: 'EN_VALIDATION' }">
            <p>En validation</p><strong>{{ d.en_validation }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/liste" [queryParams]="{ horizon: '30', statut: 'ACTIF' }">
            <p>Échéance ≤ 30 jours</p><strong>{{ d.echeance_30 }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/liste" [queryParams]="{ statut: 'EXPIRE' }">
            <p>Expirés</p><strong>{{ d.expires }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/liste" [queryParams]="{ horizon: 'retard', statut: 'ACTIF' }">
            <p>Date dépassée, encore actifs</p><strong>{{ d.date_depassee }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/liste" [queryParams]="{ statut: 'SUSPENDU' }">
            <p>Suspendus</p><strong>{{ d.suspendus }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/liste" [queryParams]="{ statut: 'ANNULE' }">
            <p>Annulés</p><strong>{{ d.annules }}</strong>
          </a>
          <article class="bea-nf-kpi__card">
            <p>Montant des actifs</p><strong>{{ d.montant_actifs | montant }}</strong>
          </article>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/paiements" [queryParams]="{ statut: 'A_VENIR' }">
            <p>Paiements à venir</p><strong>{{ d.paiements_a_venir | montant }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/paiements" [queryParams]="{ statut: 'EN_RETARD' }">
            <p>Paiements en retard</p><strong>{{ d.paiements_en_retard | montant }}</strong>
          </a>
          <a class="bea-nf-kpi__card" routerLink="/contrats-echeances/alertes">
            <p>Alertes</p><strong>{{ d.alertes }}</strong>
          </a>
        </div>
      }
    </section>
  `,
})
export class ContratsDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly dash = signal<Dashboard | null>(null);
  readonly erreur = signal<string | null>(null);

  ngOnInit(): void {
    this.api.get<Dashboard>('/mg/contrats/dashboard').subscribe({
      next: (d) => this.dash.set(d),
      error: () => this.erreur.set('Tableau de bord indisponible.'),
    });
  }
}
