import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { FilArianeComponent } from '../fil-ariane/fil-ariane.component';
import { ESPACE_COMPTABILITE, ESPACES_METIERS, EspaceMetier } from '../espaces-metiers';

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
        <h1 class="bea-plateforme__title">{{ espace().titre }}</h1>
        <p class="bea-plateforme__lead">
          Premier module intégré : Immobilisations &amp; Amortissements. Les autres briques de
          l’espace arriveront ensuite, sur le même socle.
        </p>
        <div class="bea-card-grid">
          @for (mod of espace().modules; track mod.id) {
            @if (mod.statut === 'actif' && mod.route && mod.accessible !== false) {
              <a class="bea-card bea-card--actif" [routerLink]="mod.route">
                <div class="bea-card__head">
                  <div>
                    <p class="bea-card__kicker">Module</p>
                    <h2 class="bea-card__title">{{ mod.titre }}</h2>
                  </div>
                  <span class="bea-badge bea-badge--actif">Actif</span>
                </div>
                <p class="bea-card__text">{{ mod.description }}</p>
                <div class="bea-card__viz" aria-hidden="true">
                  <div class="bea-card__bars">
                    <span></span><span></span><span></span><span></span>
                    <span></span><span></span><span></span><span></span>
                  </div>
                  <div class="bea-card__donut"></div>
                </div>
              </a>
            } @else {
              <div class="bea-card bea-card--bientot">
                <div class="bea-card__head">
                  <div>
                    <p class="bea-card__kicker">Module</p>
                    <h2 class="bea-card__title">{{ mod.titre }}</h2>
                  </div>
                  <span class="bea-badge bea-badge--bientot">Bientôt</span>
                </div>
                <p class="bea-card__text">{{ mod.description }}</p>
                <div class="bea-card__viz" aria-hidden="true">
                  <div class="bea-card__bars">
                    <span></span><span></span><span></span><span></span>
                    <span></span><span></span><span></span><span></span>
                  </div>
                  <div class="bea-card__donut"></div>
                </div>
              </div>
            }
          }
        </div>
      </main>
    </div>
  `,
})
export class ComptabiliteComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly espace = signal<EspaceMetier>(ESPACE_COMPTABILITE);

  ngOnInit(): void {
    this.api.get<EspaceMetier[]>('/plateforme/espaces').subscribe({
      next: (items) => {
        const found = items.find((item) => item.id === 'comptabilite');
        if (found) {
          const src = ESPACES_METIERS.find((item) => item.id === 'comptabilite') ?? ESPACE_COMPTABILITE;
          this.espace.set({
            ...found,
            titre: src.titre,
            description: src.description,
            modules: found.modules.map((mod) => {
              const local = src.modules.find((item) => item.id === mod.id);
              return local ? { ...mod, titre: local.titre, description: local.description } : mod;
            }),
          });
        }
      },
      error: () => undefined,
    });
  }
}

