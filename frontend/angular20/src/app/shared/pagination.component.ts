import { Component, computed, input, output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

/** Pied de liste : « Page X / Y — N élément(s) » + boutons Précédent / Suivant. */
@Component({
  selector: 'app-pagination',
  imports: [MatButtonModule, MatIconModule],
  template: `
    <footer class="app-pagination">
      <span class="app-pagination__info">
        Page {{ page() }} / {{ totalPages() }} — {{ total() }} {{ label() }}
      </span>
      <div class="app-pagination__actions">
        <button
          mat-stroked-button
          type="button"
          [disabled]="page() === 1"
          (click)="go(page() - 1)"
        >
          <mat-icon aria-hidden="true">chevron_left</mat-icon>
          Précédent
        </button>
        <button
          mat-stroked-button
          type="button"
          [disabled]="page() >= totalPages()"
          (click)="go(page() + 1)"
        >
          Suivant
          <mat-icon aria-hidden="true" iconPositionEnd>chevron_right</mat-icon>
        </button>
      </div>
    </footer>
  `,
  styles: [
    `
      .app-pagination {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        padding: 0.75rem 1rem;
        border-top: 1px solid var(--app-border, #e2e8f0);
      }

      .app-pagination__info {
        font-size: 0.8125rem;
        color: #475569;
        font-variant-numeric: tabular-nums;
      }

      .app-pagination__actions {
        display: flex;
        gap: 0.5rem;
      }
    `,
  ],
})
export class PaginationComponent {
  readonly page = input.required<number>();
  readonly total = input.required<number>();
  readonly pageSize = input(50);
  readonly label = input('élément(s)');
  readonly pageChange = output<number>();

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.pageSize())));

  go(page: number): void {
    if (page < 1 || page > this.totalPages() || page === this.page()) {
      return;
    }
    this.pageChange.emit(page);
  }
}
