import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Accès refusé explicite : affiché sans appel réseau quand la session ne porte pas la permission requise. */
@Component({
  selector: 'bea-integ-acces-refuse',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-admin-panel" role="alert">
      <h2>Accès refusé</h2>
      <p class="bea-admin-panel__hint">
        {{ section() }} exige une session BEA DIGITAL (Login 1) et
        {{ permissions().length > 1 ? 'l’une des permissions suivantes' : 'la permission' }} :
      </p>
      <ul>
        @for (p of permissions(); track p) {
          <li><code>{{ p }}</code></li>
        }
      </ul>
      <p class="bea-admin-panel__hint">
        Ces permissions ne sont attribuées à aucun rôle par défaut. Un administrateur autorisé doit les ajouter à un rôle
        (CORE ADMIN → Rôles), puis l’utilisateur doit se reconnecter. Un jeton de module (Login 2) n’est jamais accepté.
      </p>
    </div>
  `,
})
export class CoreAdminIntegrationAccesComponent {
  readonly section = input('Cette section du Studio d’intégration API');
  readonly permissions = input.required<readonly string[]>();
}
