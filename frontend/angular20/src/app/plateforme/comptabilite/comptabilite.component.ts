import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { FilArianeComponent } from '../fil-ariane/fil-ariane.component';
import { ESPACE_COMPTABILITE } from '../espaces-metiers';

@Component({
  selector: 'bea-comptabilite',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, BeaChromeComponent, FilArianeComponent],
  template: `
    <div class="bea-plateforme">
      <bea-chrome />
      <bea-fil-ariane />
      <main class="bea-plateforme__body">
        <p class="bea-plateforme__kicker">Espace métier</p>
        <h1 class="bea-plateforme__title">Comptabilité</h1>
        <p class="bea-plateforme__lead">
          Premier module intégré : Immobilisations &amp; Amortissements. Les autres briques de
          l’espace arriveront ensuite, sur le même socle.
        </p>
        <div class="bea-card-grid">
          @for (mod of espace.modules; track mod.id) {
            @if (mod.statut === 'actif' && mod.route) {
              <a class="bea-card bea-card--actif" [routerLink]="mod.route">
                <span class="bea-badge bea-badge--actif">Actif</span>
                <h2 class="bea-card__title">{{ mod.titre }}</h2>
                <p class="bea-card__text">{{ mod.description }}</p>
              </a>
            } @else {
              <div class="bea-card bea-card--bientot">
                <span class="bea-badge bea-badge--bientot">Bientôt</span>
                <h2 class="bea-card__title">{{ mod.titre }}</h2>
                <p class="bea-card__text">{{ mod.description }}</p>
              </div>
            }
          }
        </div>
      </main>
    </div>
  `,
})
export class ComptabiliteComponent {
  readonly espace = ESPACE_COMPTABILITE;
}
