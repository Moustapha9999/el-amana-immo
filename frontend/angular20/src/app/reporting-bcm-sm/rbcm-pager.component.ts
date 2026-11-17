import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

export function rbcmPageWindow(
  page: number,
  pageSize: number,
  total: number,
): { start: number; end: number; pages: number } {
  const size = Math.max(1, pageSize);
  const pages = Math.max(1, Math.ceil(Math.max(0, total) / size));
  const current = Math.min(Math.max(1, page), pages);
  if (total <= 0) return { start: 0, end: 0, pages };
  const start = (current - 1) * size + 1;
  const end = Math.min(total, start + size - 1);
  return { start, end, pages };
}

@Component({
  selector: 'bea-rbcm-pager',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <nav class="bea-rbcm-pager" [attr.aria-label]="label()">
      <p class="bea-rbcm-pager__meta">{{ rangeText() }}</p>
      <div class="bea-rbcm-pager__nav">
        <button type="button" class="bea-mg__icon-btn" aria-label="Première page" [disabled]="page() <= 1" (click)="go.emit(1)">
          <mat-icon>first_page</mat-icon>
        </button>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="go.emit(page() - 1)">
          Précédent
        </button>
        <span class="bea-rbcm-pager__page">{{ page() }} / {{ window().pages }}</span>
        <button
          type="button"
          class="bea-mg__btn bea-mg__btn--ghost"
          [disabled]="page() >= window().pages"
          (click)="go.emit(page() + 1)"
        >
          Suivant
        </button>
        <button
          type="button"
          class="bea-mg__icon-btn"
          aria-label="Dernière page"
          [disabled]="page() >= window().pages"
          (click)="go.emit(window().pages)"
        >
          <mat-icon>last_page</mat-icon>
        </button>
      </div>
    </nav>
  `,
})
export class RbcmPagerComponent {
  readonly page = input.required<number>();
  readonly pageSize = input.required<number>();
  readonly total = input.required<number>();
  readonly label = input('Pagination');
  readonly noun = input('résultats');
  readonly go = output<number>();

  readonly window = computed(() => rbcmPageWindow(this.page(), this.pageSize(), this.total()));

  rangeText(): string {
    const { start, end } = this.window();
    const total = this.total();
    if (total <= 0) return `0 ${this.noun()}`;
    return `${start}\u2013${end} sur ${total} ${this.noun()}`;
  }
}
