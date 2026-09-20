import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map, startWith } from 'rxjs/operators';
import { labelPageModuleImmo } from '../espaces-metiers';
import { PlateformeContextService } from '../plateforme-context.service';

export interface FilArianeCrumb {
  label: string;
  path: string | null;
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
  private readonly nav = inject(PlateformeContextService);

  readonly crumbs = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => this.crumbsForUrl(event.urlAfterRedirects)),
      startWith(this.crumbsForUrl(this.router.url)),
    ),
    { initialValue: this.crumbsForUrl('/') },
  );

  private crumbsForUrl(url: string): FilArianeCrumb[] {
    const path = url.split('?')[0];
    if (path === '/accueil' || path === '/') {
      return [{ label: 'Accueil', path: null }];
    }

    const ctx = this.nav.ensureLegacyImmoDefaults();
    const accueil: FilArianeCrumb = { label: 'Accueil', path: '/accueil' };
    const espace: FilArianeCrumb = {
      label: ctx.espaceTitre,
      path: ctx.espaceRoute,
    };
    const moduleCrumb: FilArianeCrumb = {
      label: ctx.moduleTitre,
      path: ctx.entryPath,
    };

    const page = labelPageModuleImmo(path);
    if (page && path !== ctx.entryPath) {
      return [accueil, espace, moduleCrumb, { label: page, path: null }];
    }
    return [accueil, espace, { ...moduleCrumb, path: null }];
  }
}
