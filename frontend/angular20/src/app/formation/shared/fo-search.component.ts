import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, HostListener, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { Subject, debounceTime, distinctUntilChanged, of, switchMap, catchError } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { FO_BASE, ResultatRecherche } from '../formation.models';

interface Item {
  icon: string;
  libelle: string;
  sous: string;
  groupe: string;
  lien: string;
  params?: Record<string, string>;
}

/** Recherche globale : employés, formations, référentiels, entités. */
@Component({
  selector: 'bea-fo-search',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    <div class="bea-fo-search">
      <label class="bea-mg__field">
        <mat-icon>search</mat-icon>
        <input type="search" placeholder="Rechercher un employé, une formation, un thème, une entité…" autocomplete="off"
          [value]="q()" (input)="saisir($any($event.target).value)" (focus)="ouvert.set(true)" (keydown)="clavier($event)" />
        @if (charge()) { <mat-icon class="bea-fo-spin">progress_activity</mat-icon> }
      </label>
      @if (ouvert() && q().trim().length >= 2) {
        <div class="bea-fo-search__drop" role="listbox">
          @if (items().length) {
            @for (it of items(); track it.groupe + it.lien + it.libelle; let i = $index) {
              @if (i === 0 || items()[i - 1].groupe !== it.groupe) {
                <p class="bea-fo-search__grp">{{ it.groupe }}</p>
              }
              <button type="button" class="bea-fo-search__item" [class.is-on]="i === curseur()" (mousedown)="aller(it)">
                <mat-icon>{{ it.icon }}</mat-icon>
                <span><strong>{{ it.libelle }}</strong><small>{{ it.sous }}</small></span>
              </button>
            }
          } @else if (!charge()) {
            <p class="bea-fo-search__none">Aucun résultat pour « {{ q() }} »</p>
          }
        </div>
      }
    </div>
  `,
})
export class FoSearchComponent {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly el = inject(ElementRef<HTMLElement>);
  private readonly saisie$ = new Subject<string>();

  readonly q = signal('');
  readonly ouvert = signal(false);
  readonly charge = signal(false);
  readonly curseur = signal(0);
  private readonly resultat = signal<ResultatRecherche | null>(null);

  readonly items = computed<Item[]>(() => {
    const r = this.resultat();
    if (!r) return [];
    return [
      ...r.employes.map((e) => ({ icon: 'person', libelle: e.libelle, sous: (e.sous || 'Entité non renseignée') + (e.actif ? '' : ' · désactivé'), groupe: 'Employés', lien: `${FO_BASE}/employes/${e.id}` })),
      ...r.formations.map((f) => ({ icon: 'school', libelle: f.libelle, sous: f.sous, groupe: 'Formations', lien: `${FO_BASE}/sessions/${f.id}` })),
      ...r.referentiels.map((x) => ({ icon: 'label', libelle: x.libelle, sous: x.sous, groupe: 'Référentiels', lien: `${FO_BASE}/referentiels`, params: { onglet: x.domaine } })),
      ...r.entites.map((x) => ({ icon: 'account_tree', libelle: x.libelle, sous: x.sous, groupe: 'Entités', lien: `${FO_BASE}/employes`, params: { entite_id: x.id } })),
    ];
  });

  constructor() {
    this.saisie$
      .pipe(
        debounceTime(250),
        distinctUntilChanged(),
        switchMap((q) => {
          if (q.trim().length < 2) {
            this.charge.set(false);
            return of(null);
          }
          this.charge.set(true);
          return this.api.get<ResultatRecherche>(`${FO_BASE}/recherche`, { q: q.trim() }).pipe(catchError(() => of(null)));
        }),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe((r) => {
        this.charge.set(false);
        this.resultat.set(r);
        this.curseur.set(0);
      });
  }

  saisir(v: string): void {
    this.q.set(v);
    this.ouvert.set(true);
    this.saisie$.next(v);
  }

  clavier(e: KeyboardEvent): void {
    const n = this.items().length;
    if (e.key === 'ArrowDown' && n) {
      e.preventDefault();
      this.curseur.set((this.curseur() + 1) % n);
    } else if (e.key === 'ArrowUp' && n) {
      e.preventDefault();
      this.curseur.set((this.curseur() - 1 + n) % n);
    } else if (e.key === 'Enter' && n) {
      e.preventDefault();
      this.aller(this.items()[this.curseur()]!);
    } else if (e.key === 'Escape') {
      this.ouvert.set(false);
    }
  }

  aller(it: Item): void {
    this.ouvert.set(false);
    void this.router.navigate([it.lien], { queryParams: it.params });
  }

  @HostListener('document:click', ['$event'])
  dehors(e: MouseEvent): void {
    if (!this.el.nativeElement.contains(e.target as Node)) this.ouvert.set(false);
  }
}
