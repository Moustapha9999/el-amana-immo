import { ChangeDetectionStrategy, Component, HostListener, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

export interface RowMenuItem {
  icone: string;
  label: string;
  danger?: boolean;
  action: () => void;
}

/** État d'un menu « ⋮ » de ligne, positionné en `fixed` pour échapper au défilement du tableau. */
export class RowMenu {
  readonly ouvert = signal<{ top: number; left: number; items: RowMenuItem[] } | null>(null);

  ouvrir(ev: MouseEvent, items: RowMenuItem[]): void {
    ev.stopPropagation();
    if (!items.length) return;
    const r = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const hauteur = items.length * 38 + 12;
    const top = r.bottom + hauteur > window.innerHeight ? Math.max(8, r.top - hauteur) : r.bottom + 4;
    this.ouvert.set({ top, left: Math.max(8, Math.min(r.right - 220, window.innerWidth - 228)), items });
  }

  fermer(): void {
    this.ouvert.set(null);
  }
}

@Component({
  selector: 'bea-row-menu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (menu().ouvert(); as mn) {
      <div class="bea-row-menu__veil" (click)="menu().fermer()"></div>
      <ul class="bea-row-menu" role="menu" [style.top.px]="mn.top" [style.left.px]="mn.left">
        @for (it of mn.items; track it.label) {
          <li role="none">
            <button type="button" role="menuitem" [class.is-danger]="it.danger" (click)="menu().fermer(); it.action()"><mat-icon>{{ it.icone }}</mat-icon> {{ it.label }}</button>
          </li>
        }
      </ul>
    }
  `,
})
export class RowMenuComponent {
  readonly menu = input.required<RowMenu>();

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.menu().fermer();
  }

  @HostListener('window:scroll')
  @HostListener('window:resize')
  onMove(): void {
    this.menu().fermer();
  }
}
