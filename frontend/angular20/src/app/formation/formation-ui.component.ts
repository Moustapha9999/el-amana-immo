import { ChangeDetectionStrategy, Component, ViewEncapsulation } from '@angular/core';

/** Porte la feuille de style du module (non encapsulée, donc reprise par le générateur du thème sombre). */
@Component({
  selector: 'bea-fo-styles',
  template: '',
  styleUrls: ['./formation-ui.css', './formation-forms.css', './formation-docs.css'],
  encapsulation: ViewEncapsulation.None,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display:none' },
})
export class FormationUiComponent {}
