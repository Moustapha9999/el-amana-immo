import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Même glyphes que le shell Immobilisations (`mat-icon` + Material Icons),
 * sans importer Angular Material dans `src/app/plateforme/`.
 * La police est déjà chargée dans `index.html`.
 */
@Component({
  selector: 'bea-admin-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'material-icons',
    'aria-hidden': 'true',
  },
  template: `{{ name() }}`,
})
export class CoreAdminIconComponent {
  readonly name = input.required<string>();
}
