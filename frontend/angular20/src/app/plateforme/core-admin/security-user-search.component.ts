import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  input,
  OnInit,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime, distinctUntilChanged, Subject, switchMap, of, catchError, tap } from 'rxjs';
import { ApiService } from '../../core/services/api.service';

export interface SecurityUserHit {
  id: string;
  full_name: string;
  prenom?: string;
  nom?: string;
  email: string;
  phone?: string | null;
  login?: string;
  is_active?: boolean;
  totp_enabled?: boolean;
  espaces?: Array<{ code: string; label: string }>;
  modules?: Array<{ code: string; label: string }>;
}

@Component({
  selector: 'bea-security-user-search',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-sec-search">
      <label class="bea-admin-field">
        <span>{{ label() }}</span>
        <input
          type="search"
          [placeholder]="placeholder()"
          [value]="query()"
          (input)="onInput($event)"
          (focus)="onFocus()"
          autocomplete="off"
        />
      </label>

      @if (selected(); as sel) {
        <div class="bea-sec-search__selected">
          <div>
            <strong>{{ sel.full_name }}</strong>
            <span>{{ sel.email }}</span>
            @if (sel.phone) {
              <span>{{ sel.phone }}</span>
            }
          </div>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="clear()">
            Changer
          </button>
        </div>
      } @else {
        <div class="bea-sec-search__panel" role="listbox">
          @if (erreur()) {
            <p class="bea-sec-search__empty bea-sec-search__empty--err">{{ erreur() }}</p>
          } @else if (loading()) {
            <p class="bea-sec-search__empty">Recherche…</p>
          } @else if (!hits().length) {
            <p class="bea-sec-search__empty">Aucun utilisateur trouvé.</p>
          } @else {
            <p class="bea-sec-search__hint">
              {{ query().trim() ? 'Résultats' : 'Utilisateurs récents' }} — cliquez pour ouvrir le
              dossier
            </p>
            <ul class="bea-sec-search__list">
              @for (hit of hits(); track hit.id) {
                <li>
                  <button type="button" (click)="pick(hit)">
                    <strong>{{ hit.full_name }}</strong>
                    <span>{{ hit.email }}</span>
                    @if (hit.phone) {
                      <span>{{ hit.phone }}</span>
                    }
                    @if (hit.espaces?.length) {
                      <em>Département : {{ hit.espaces![0].label }}</em>
                    }
                  </button>
                </li>
              }
            </ul>
          }
        </div>
      }
    </div>
  `,
})
export class SecurityUserSearchComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly query$ = new Subject<string>();

  readonly label = input('Rechercher un utilisateur…');
  readonly placeholder = input('Nom, prénom, e-mail, téléphone, login…');
  readonly selectedChange = output<SecurityUserHit | null>();

  readonly query = signal('');
  readonly hits = signal<SecurityUserHit[]>([]);
  readonly loading = signal(false);
  readonly erreur = signal('');
  readonly selected = signal<SecurityUserHit | null>(null);

  constructor() {
    this.query$
      .pipe(
        debounceTime(220),
        distinctUntilChanged(),
        tap(() => {
          this.loading.set(true);
          this.erreur.set('');
        }),
        switchMap((q) =>
          this.api
            .get<{ items: SecurityUserHit[] }>('/plateforme/admin/settings/security/users/search', {
              q: q.trim(),
              limit: 15,
            })
            .pipe(
              catchError((err) => {
                const detail =
                  typeof err?.error?.detail === 'string'
                    ? err.error.detail
                    : 'Recherche impossible (vérifiez vos droits sécurité).';
                this.erreur.set(detail);
                return of({ items: [] as SecurityUserHit[] });
              }),
            ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        this.hits.set(res.items || []);
        this.loading.set(false);
      });
  }

  ngOnInit(): void {
    this.query$.next('');
  }

  onFocus(): void {
    if (!this.selected() && !this.hits().length && !this.loading()) {
      this.query$.next(this.query());
    }
  }

  onInput(ev: Event): void {
    const v = (ev.target as HTMLInputElement).value;
    this.query.set(v);
    this.query$.next(v);
  }

  pick(hit: SecurityUserHit): void {
    this.selected.set(hit);
    this.query.set(hit.full_name);
    this.hits.set([]);
    this.selectedChange.emit(hit);
  }

  clear(): void {
    this.selected.set(null);
    this.query.set('');
    this.selectedChange.emit(null);
    this.query$.next('');
  }
}
