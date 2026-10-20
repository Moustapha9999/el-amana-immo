import { ChangeDetectionStrategy, Component, ViewEncapsulation } from '@angular/core';

@Component({
  selector: 'bea-cl-styles',
  template: '',
  styleUrls: ['./clientele-ui.css', './clientele-motion.css', './clientele-listes.css'],
  encapsulation: ViewEncapsulation.None,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { style: 'display:none' },
})
export class ClienteleUiComponent {}
