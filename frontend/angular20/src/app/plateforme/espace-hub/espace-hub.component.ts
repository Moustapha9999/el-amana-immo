import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter } from 'rxjs/operators';
import { ApiService } from '../../core/services/api.service';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { EspaceMetier, ModuleMetier } from '../espaces-metiers';

const STATUT_BADGE: Record<string, { label: string; tone: string }> = {
  actif: { label: 'Disponible', tone: 'actif' },
  mise_a_jour: { label: 'Mise à jour', tone: 'warn' },
  maintenance: { label: 'Maintenance', tone: 'warn' },
  developpement: { label: 'En développement', tone: 'info' },
  suspendu: { label: 'Suspendu', tone: 'warn' },
  bloque: { label: 'Bloqué', tone: 'inactif' },
  bientot: { label: 'Bientôt disponible', tone: 'bientot' },
  archive: { label: 'Archivé', tone: 'inactif' },
  inactif: { label: 'Inactif', tone: 'inactif' },
};

/** Statuts visibles et ouverts (Login 2 ou message d’indisponibilité). */
const OPENABLE = new Set([
  'actif',
  'mise_a_jour',
  'maintenance',
  'developpement',
  'suspendu',
  'bloque',
]);

@Component({
  selector: 'bea-espace-hub',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, BeaChromeComponent],
  template: `
    <div class="bea-plateforme">
      <bea-chrome />
      <main class="bea-plateforme__body bea-hub bea-hub--dept">
        @if (missing()) {
          <header class="bea-hub__welcome">
            <div>
              <p class="bea-plateforme__kicker">Département</p>
              <h1 class="bea-plateforme__title">Introuvable ou non accessible</h1>
              <p class="bea-card__text">
                Ce département n’apparaît pas pour votre compte (statut, route ou droits d’accès).
              </p>
            </div>
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/accueil">← BEA DIGITAL</a>
          </header>
        } @else {
          <header class="bea-hub__welcome">
            <div>
              <p class="bea-plateforme__kicker">Département</p>
              <h1 class="bea-plateforme__title">{{ espace().titre }}</h1>
            </div>
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/accueil">← BEA DIGITAL</a>
          </header>

          <section class="bea-hub__section bea-hub__section--fill">
            <div class="bea-hub__section-head">
              <h2>Modules</h2>
              <p>Choisissez un module pour continuer.</p>
            </div>
            @if (espace().modules.length === 0) {
              <p class="bea-card__text">
                Aucun module visible. Créez-en un dans CORE ADMIN — il apparaîtra ici après
                actualisation (statut « bientôt » = vitrine ; « actif » + droit d’accès =
                ouverture Login 2).
              </p>
            }
            <div class="bea-card-grid bea-card-grid--modules">
              @for (mod of espace().modules; track mod.id) {
                @if (isOpenable(mod)) {
                  <a
                    class="bea-card"
                    [class.bea-card--actif]="mod.statut === 'actif'"
                    [class.bea-card--restreint]="mod.statut !== 'actif'"
                    [routerLink]="mod.route!"
                  >
                    <div class="bea-card__head">
                      <h2 class="bea-card__title">{{ mod.titre }}</h2>
                      <span class="bea-badge" [class]="'bea-badge--' + badgeTone(mod.statut)">
                        {{ badgeLabel(mod.statut) }}
                      </span>
                    </div>
                    <p class="bea-card__text">{{ mod.description }}</p>
                    @if (mod.statut !== 'actif' && mod.status_message) {
                      <p class="bea-card__hint">{{ mod.status_message }}</p>
                    } @else if (mod.statut === 'actif') {
                      <p class="bea-card__meta">Accès sécurisé</p>
                    }
                    <p class="bea-card__cta">
                      {{ mod.statut === 'actif' ? 'Ouvrir le module' : 'Voir le message' }}
                    </p>
                    <div class="bea-card__viz" aria-hidden="true">
                      <div class="bea-card__bars">
                        <span></span><span></span><span></span><span></span>
                        <span></span><span></span><span></span><span></span>
                      </div>
                      <div class="bea-card__donut"></div>
                    </div>
                  </a>
                } @else {
                  <div class="bea-card bea-card--bientot">
                    <div class="bea-card__head">
                      <h2 class="bea-card__title">{{ mod.titre }}</h2>
                      <span class="bea-badge" [class]="'bea-badge--' + badgeTone(mod.statut)">
                        {{ badgeLabel(mod.statut) }}
                      </span>
                    </div>
                    <p class="bea-card__text">{{ mod.description }}</p>
                    <p class="bea-card__meta">En préparation — bientôt sur BEA DIGITAL</p>
                    <div class="bea-card__viz" aria-hidden="true">
                      <div class="bea-card__bars">
                        <span></span><span></span><span></span><span></span>
                        <span></span><span></span><span></span><span></span>
                      </div>
                      <div class="bea-card__donut"></div>
                    </div>
                  </div>
                }
              }
            </div>
          </section>
        }
      </main>
    </div>
  `,
})
export class EspaceHubComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly espace = signal<EspaceMetier>({
    id: '',
    titre: '',
    description: '',
    route: null,
    statut: 'bientot',
    modules: [],
  });
  readonly missing = signal(false);

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.loadForCurrentRoute();
    });
    // Retour depuis CORE ADMIN (même URL) → recharger le catalogue DB.
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((e) => {
        const path = e.urlAfterRedirects.split('?')[0].replace(/^\//, '');
        const code = this.currentEspaceCode();
        if (path === code || path === `comptabilite`) {
          this.loadForCurrentRoute();
        }
      });
  }

  private currentEspaceCode(): string {
    return (
      this.route.snapshot.paramMap.get('espaceCode') ||
      this.route.snapshot.data['espaceCode'] ||
      'comptabilite'
    );
  }

  private loadForCurrentRoute(): void {
    const code = this.currentEspaceCode();
    this.api.get<EspaceMetier[]>('/plateforme/espaces').subscribe({
      next: (items) => {
        const found = items.find(
          (item) =>
            item.id === code ||
            item.route === `/${code}` ||
            (item.route || '').replace(/^\//, '') === code,
        );
        if (found) {
          this.espace.set(found);
          this.missing.set(false);
        } else {
          this.missing.set(true);
        }
      },
      error: () => this.missing.set(true),
    });
  }

  isOpenable(mod: ModuleMetier): boolean {
    return !!mod.route && OPENABLE.has(String(mod.statut));
  }

  badgeLabel(statut: string): string {
    return STATUT_BADGE[statut]?.label ?? statut;
  }

  badgeTone(statut: string): string {
    return STATUT_BADGE[statut]?.tone ?? 'bientot';
  }
}
