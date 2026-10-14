import { ChangeDetectionStrategy, Component, ViewEncapsulation } from '@angular/core';

/** Porte la feuille de style du module (non encapsulée, donc reprise par le générateur du thème sombre). */
@Component({
  selector: 'bea-rc-styles',
  template: '',
  styleUrls: ['./reclamations-ui.css', './reclamations-ui-blocs.css'],
  encapsulation: ViewEncapsulation.None,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display:none' },
})
export class ReclamationsUiComponent {}
