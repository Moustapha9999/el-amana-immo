import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ParcChartsPanelComponent } from '../../dashboard/parc-charts-panel.component';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { ESPACES_METIERS } from '../espaces-metiers';

@Component({
  selector: 'bea-accueil',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, BeaChromeComponent, ParcChartsPanelComponent],
  template: `
    <div class="bea-plateforme">
      <bea-chrome />
      <main class="bea-plateforme__body bea-plateforme__body--wide">
        <p class="bea-plateforme__kicker">Banque El Amana</p>
        <h1 class="bea-plateforme__title">Espaces métiers</h1>
        <p class="bea-plateforme__lead">
          BEA DIGITAL digitalise les processus internes autour d’ORION. Ouvrez un espace pour
          accéder à ses modules.
        </p>
        <div class="bea-card-grid">
          @for (espace of espaces; track espace.id) {
            @if (espace.statut === 'actif' && espace.route) {
              <a class="bea-card bea-card--actif" [routerLink]="espace.route">
                <span class="bea-badge bea-badge--actif">Actif</span>
                <h2 class="bea-card__title">{{ espace.titre }}</h2>
                <p class="bea-card__text">{{ espace.description }}</p>
              </a>
            } @else {
              <div class="bea-card bea-card--bientot">
                <span class="bea-badge bea-badge--bientot">Bientôt</span>
                <h2 class="bea-card__title">{{ espace.titre }}</h2>
                <p class="bea-card__text">{{ espace.description }}</p>
              </div>
            }
          }
        </div>

        <section class="bea-accueil-parc" aria-labelledby="parc-charts-title">
          <div class="bea-accueil-parc__head">
            <div>
              <p class="bea-plateforme__kicker">Comptabilité · Immobilisations</p>
              <h2 id="parc-charts-title" class="bea-accueil-parc__title">Pilotage du parc</h2>
              <p class="bea-accueil-parc__lead">
                Indicateurs et graphiques du module Immobilisations &amp; Amortissements (bleus BEA).
              </p>
            </div>
            <a class="bea-accueil-parc__link" routerLink="/dashboard">Ouvrir le module</a>
          </div>
          <app-parc-charts-panel areaFillId="vncAreaFillAccueil" />
        </section>

        <p class="bea-orion">
          ORION reste le core banking (source de vérité). BEA DIGITAL ne le remplace pas : Excel,
          contrôles, workflows, reporting et GED.
        </p>
      </main>
    </div>
  `,
})
export class AccueilComponent {
  readonly espaces = ESPACES_METIERS;
}
