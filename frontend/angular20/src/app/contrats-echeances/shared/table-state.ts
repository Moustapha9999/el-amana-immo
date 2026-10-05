import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

type Cle = string | number | null | undefined;

/** Tri + pagination d'une liste déjà chargée (signaux) ; la page est bornée quand la source rétrécit. */
export class TableState<T> {
  readonly page = signal(1);
  readonly taille = signal(25);
  readonly tri = signal<{ cle: string; sens: 1 | -1 } | null>(null);

  readonly triees = computed(() => {
    const rows = this.source();
    const t = this.tri();
    const acc = t ? this.cles[t.cle] : undefined;
    if (!t || !acc) return rows;
    return [...rows].sort((a, b) => comparer(acc(a), acc(b)) * t.sens);
  });
  readonly total = computed(() => this.triees().length);
  readonly pages = computed(() => Math.max(1, Math.ceil(this.total() / this.taille())));
  readonly pageCourante = computed(() => Math.min(this.page(), this.pages()));
  readonly debut = computed(() => (this.total() ? (this.pageCourante() - 1) * this.taille() + 1 : 0));
  readonly fin = computed(() => Math.min(this.pageCourante() * this.taille(), this.total()));
  readonly lignes = computed(() => this.triees().slice(this.debut() ? this.debut() - 1 : 0, this.fin()));

  constructor(
    private readonly source: () => T[],
    private readonly cles: Record<string, (r: T) => Cle>,
  ) {}

  trier(cle: string): void {
    const t = this.tri();
    this.tri.set(!t || t.cle !== cle ? { cle, sens: 1 } : t.sens === 1 ? { cle, sens: -1 } : null);
  }

  aria(cle: string): 'ascending' | 'descending' | 'none' {
    const t = this.tri();
    return t?.cle === cle ? (t.sens === 1 ? 'ascending' : 'descending') : 'none';
  }

  icone(cle: string): string {
    const t = this.tri();
    return t?.cle === cle ? (t.sens === 1 ? 'arrow_upward' : 'arrow_downward') : 'unfold_more';
  }

  reinit(): void {
    this.page.set(1);
  }
}

function comparer(a: Cle, b: Cle): number {
  if (a === b) return 0;
  if (a === null || a === undefined || a === '') return 1;
  if (b === null || b === undefined || b === '') return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'fr', { numeric: true, sensitivity: 'base' });
}

/** Barre de pagination : « 1–25 sur 132 », taille de page, précédent / suivant. */
@Component({
  selector: 'bea-pager',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @let t = etat();
    <nav class="bea-pager" aria-label="Pagination">
      <span class="bea-pager__count">
        @if (t.total()) { <strong>{{ t.debut() }}–{{ t.fin() }}</strong> sur {{ t.total() }} } @else { Aucun élément }
      </span>
      <label class="bea-pager__size">Par page
        <select [value]="t.taille()" (change)="taille(t, $event)">
          @for (n of tailles; track n) { <option [value]="n" [selected]="n === t.taille()">{{ n }}</option> }
        </select>
      </label>
      <span class="bea-pager__nav">
        <button type="button" class="bea-mg__icon-btn" aria-label="Première page" [disabled]="t.pageCourante() <= 1" (click)="t.page.set(1)"><mat-icon>first_page</mat-icon></button>
        <button type="button" class="bea-mg__icon-btn" aria-label="Page précédente" [disabled]="t.pageCourante() <= 1" (click)="t.page.set(t.pageCourante() - 1)"><mat-icon>chevron_left</mat-icon></button>
        <span>Page {{ t.pageCourante() }} / {{ t.pages() }}</span>
        <button type="button" class="bea-mg__icon-btn" aria-label="Page suivante" [disabled]="t.pageCourante() >= t.pages()" (click)="t.page.set(t.pageCourante() + 1)"><mat-icon>chevron_right</mat-icon></button>
        <button type="button" class="bea-mg__icon-btn" aria-label="Dernière page" [disabled]="t.pageCourante() >= t.pages()" (click)="t.page.set(t.pages())"><mat-icon>last_page</mat-icon></button>
      </span>
    </nav>
  `,
})
export class PagerComponent {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  readonly etat = input.required<TableState<any>>();
  readonly tailles = [10, 25, 50, 100];

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  taille(t: TableState<any>, ev: Event): void {
    t.taille.set(Number((ev.target as HTMLSelectElement).value) || 25);
    t.page.set(1);
  }
}
