import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

export interface RowMenuItem {
  icone: string;
  label: string;
  danger?: boolean;
  action: () => void;
}

export interface RowMenuAnchor {
  top: number;
  bottom: number;
  right: number;
}

/** Place un menu sous le bouton, ou au-dessus s'il n'y a pas la place, sans sortir de l'écran. */
export function placeRowMenu(
  anchor: RowMenuAnchor,
  height: number,
  width: number,
  viewport: { width: number; height: number },
): { top: number; left: number } {
  const margin = 8;
  const spaceBelow = viewport.height - anchor.bottom - margin;
  const spaceAbove = anchor.top - margin;
  const openUp = spaceBelow < height && spaceAbove > spaceBelow;
  const top = openUp
    ? Math.max(margin, anchor.top - height - 4)
    : Math.max(margin, Math.min(anchor.bottom + 4, viewport.height - height - margin));
  const left = Math.max(margin, Math.min(anchor.right - width, viewport.width - width - margin));
  return { top, left };
}

/** État d'un menu « ⋮ » de ligne, positionné en `fixed` pour échapper au défilement du tableau. */
export class RowMenu {
  readonly ouvert = signal<{ top: number; left: number; items: RowMenuItem[] } | null>(null);
  private anchor: RowMenuAnchor | null = null;
  private trigger: HTMLElement | null = null;
  private openedAt = 0;

  ouvrir(ev: MouseEvent, items: RowMenuItem[]): void {
    ev.stopPropagation();
    if (!items.length) return;
    const trigger = ev.currentTarget as HTMLElement;
    const rect = trigger.getBoundingClientRect();
    this.trigger = trigger;
    this.anchor = { top: rect.top, bottom: rect.bottom, right: rect.right };
    this.openedAt = performance.now();
    const viewport = {
      width: window.visualViewport?.width ?? window.innerWidth,
      height: window.visualViewport?.height ?? window.innerHeight,
    };
    const guess = placeRowMenu(this.anchor, items.length * 44 + 24, 280, viewport);
    this.ouvert.set({ ...guess, items });
  }

  /** Recale le menu une fois sa largeur réelle connue. */
  ajuster(width: number, height: number): void {
    const opened = this.ouvert();
    const anchor = this.anchor;
    if (!opened || !anchor || width <= 0 || height <= 0) return;
    const pos = placeRowMenu(anchor, height, width, {
      width: window.visualViewport?.width ?? window.innerWidth,
      height: window.visualViewport?.height ?? window.innerHeight,
    });
    if (Math.round(pos.top) === Math.round(opened.top) && Math.round(pos.left) === Math.round(opened.left)) return;
    this.ouvert.set({ ...opened, top: pos.top, left: pos.left });
  }

  fermer(opts?: { focusTrigger?: boolean }): void {
    const trigger = this.trigger;
    const was = this.ouvert() !== null;
    this.ouvert.set(null);
    this.anchor = null;
    if (was && opts?.focusTrigger) queueMicrotask(() => trigger?.focus({ preventScroll: true }));
  }

  /** Ignore le scroll parasite juste après l'ouverture. */
  scrollRecent(): boolean {
    return performance.now() - this.openedAt < 180;
  }
}

@Component({
  selector: 'bea-row-menu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (menu().ouvert(); as mn) {
      <div class="bea-row-menu__veil" (click)="menu().fermer({ focusTrigger: true })"></div>
      <ul
        #liste
        class="bea-row-menu"
        role="menu"
        aria-label="Actions"
        [style.top.px]="mn.top"
        [style.left.px]="mn.left"
      >
        @for (it of mn.items; track it.label) {
          <li role="none">
            <button type="button" role="menuitem" [class.is-danger]="it.danger" (click)="menu().fermer(); it.action()">
              <mat-icon>{{ it.icone }}</mat-icon> {{ it.label }}
            </button>
          </li>
        }
      </ul>
    }
  `,
})
export class RowMenuComponent {
  readonly menu = input.required<RowMenu>();
  private readonly liste = viewChild<ElementRef<HTMLElement>>('liste');

  constructor() {
    const onScroll = () => {
      if (!this.menu().ouvert() || this.menu().scrollRecent()) return;
      this.menu().fermer();
    };
    document.addEventListener('scroll', onScroll, true);
    inject(DestroyRef).onDestroy(() => document.removeEventListener('scroll', onScroll, true));

    effect(() => {
      if (!this.menu().ouvert()) return;
      setTimeout(() => {
        const el = this.liste()?.nativeElement;
        if (!el || !this.menu().ouvert()) return;
        this.menu().ajuster(el.offsetWidth, el.offsetHeight);
        if (!el.contains(document.activeElement)) {
          el.querySelector<HTMLElement>('[role="menuitem"]')?.focus({ preventScroll: true });
        }
      }, 0);
    });
  }

  @HostListener('document:keydown', ['$event'])
  onKey(event: KeyboardEvent): void {
    if (!this.menu().ouvert()) return;
    const items = Array.from(this.liste()?.nativeElement.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    if (event.key === 'Escape') {
      event.preventDefault();
      this.menu().fermer({ focusTrigger: true });
      return;
    }
    if (!items.length) return;
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      items[(index + 1) % items.length]?.focus({ preventScroll: true });
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      items[index <= 0 ? items.length - 1 : index - 1]?.focus({ preventScroll: true });
    } else if (event.key === 'Home') {
      event.preventDefault();
      items[0]?.focus({ preventScroll: true });
    } else if (event.key === 'End') {
      event.preventDefault();
      items[items.length - 1]?.focus({ preventScroll: true });
    }
  }

  @HostListener('window:resize')
  onResize(): void {
    if (this.menu().ouvert()) this.menu().fermer();
  }
}
