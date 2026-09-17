import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map, startWith } from 'rxjs/operators';
import { labelPageModuleImmo } from '../espaces-metiers';

export interface FilArianeCrumb {
  label: string;
  path: string | null;
}

function crumbsForUrl(url: string): FilArianeCrumb[] {
  const path = url.split('?')[0];
  const accueil: FilArianeCrumb = { label: 'Accueil', path: '/accueil' };
  const compta: FilArianeCrumb = { label: 'Comptabilité', path: '/comptabilite' };
  const immo: FilArianeCrumb = {
    label: 'Immobilisations & Amortissements',
    path: '/dashboard',
  };

  if (path === '/accueil' || path === '/') {
    return [{ label: 'Accueil', path: null }];
  }
  if (path === '/comptabilite' || path.startsWith('/comptabilite/')) {
    return [accueil, { label: 'Comptabilité', path: null }];
  }

  const page = labelPageModuleImmo(path);
  const crumbs: FilArianeCrumb[] = [accueil, compta, immo];
  if (page && path !== '/dashboard') {
    crumbs.push({ label: page, path: null });
    crumbs[2] = { ...immo, path: '/dashboard' };
  } else {
    crumbs[2] = { ...immo, path: null };
  }
  return crumbs;
}

@Component({
  selector: 'bea-fil-ariane',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <nav class="bea-fil-ariane" aria-label="Fil d'Ariane">
      <ol class="bea-fil-ariane__list">
        @for (crumb of crumbs(); track crumb.label; let last = $last) {
          <li class="bea-fil-ariane__item">
            @if (!last && crumb.path) {
              <a [routerLink]="crumb.path">{{ crumb.label }}</a>
            } @else {
              <span aria-current="page">{{ crumb.label }}</span>
            }
            @if (!last) {
              <span class="bea-fil-ariane__sep" aria-hidden="true">→</span>
            }
          </li>
        }
      </ol>
    </nav>
  `,
})
export class FilArianeComponent {
  private readonly router = inject(Router);

  readonly crumbs = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => crumbsForUrl(event.urlAfterRedirects)),
      startWith(crumbsForUrl(this.router.url)),
    ),
    { initialValue: crumbsForUrl('/') },
  );
}
