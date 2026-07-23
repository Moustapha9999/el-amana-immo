import { Component, input } from '@angular/core';

@Component({
  selector: 'app-module-placeholder',
  template: `
    <h2 class="text-xl font-semibold mb-2">{{ title() }}</h2>
    <p class="text-slate-600">Module prévu au cahier des charges — implémentation en cours (phase suivante).</p>
  `,
})
export class ModulePlaceholderComponent {
  readonly title = input('Module');
}
