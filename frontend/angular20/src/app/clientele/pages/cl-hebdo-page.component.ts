import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { ClienteleStore } from '../clientele.store';
import { ClHebdoComponent, ModeHebdo } from './cl-hebdo.component';

const ENTETES: Record<ModeHebdo, { kicker: string; titre: string; sous: string }> = {
  import: {
    kicker: 'Base Clientèle',
    titre: 'Import hebdomadaire',
    sous: 'Contrôler la liste de la semaine, vérifier l’aperçu (nouveaux, existants, doublons, identités, champs manquants, conflits), puis intégrer. Aucun client absent du fichier n’est supprimé.',
  },
  historique: {
    kicker: 'Base Clientèle',
    titre: 'Historique des imports',
    sous: 'Tous les fichiers hebdomadaires déposés, avec leur intégration et leurs décisions de classification.',
  },
  lot: {
    kicker: 'Classification',
    titre: 'Classification par lot',
    sous: 'Exécuter le moteur, accepter la classe proposée, choisir une classe manuelle motivée ou laisser en attente, puis confirmer l’ensemble.',
  },
};

@Component({
  selector: 'bea-cl-hebdo-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ClienteleUiComponent, ClHebdoComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl bea-cl--large">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">{{ entete.kicker }}</p>
          <h1>{{ entete.titre }}</h1>
          <p class="bea-cl-head__sub">{{ entete.sous }}</p>
        </div>
      </header>
      <bea-cl-hebdo [mode]="mode" />
    </div>
  `,
})
export class ClHebdoPageComponent {
  private readonly store = inject(ClienteleStore);
  readonly mode: ModeHebdo = (inject(ActivatedRoute).snapshot.data['mode'] as ModeHebdo) || 'import';
  readonly entete = ENTETES[this.mode];

  constructor() {
    this.store.charger();
  }
}
