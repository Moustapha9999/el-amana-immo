import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter } from 'rxjs/operators';
import { ApiService } from '../../core/services/api.service';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { CoreAdminIconComponent } from '../core-admin/core-admin-icon.component';
import { DomaineMetier, EspaceMetier, ModuleMetier } from '../espaces-metiers';

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

interface SousDomaineVue {
  domaine: DomaineMetier;
  modules: ModuleMetier[];
}

interface DomaineVue {
  domaine: DomaineMetier;
  modules: ModuleMetier[];
  sousDomaines: SousDomaineVue[];
  /** Au moins un module rattaché (directement ou via un sous-domaine). */
  peuple: boolean;
}

@Component({
  selector: 'bea-espace-hub',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, BeaChromeComponent, CoreAdminIconComponent, NgTemplateOutlet],
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
          <header class="bea-hub__welcome" [class.bea-dept-head]="!!espace().icon">
            @if (espace().icon; as icon) {
              <span class="bea-dept-head__emblem" aria-hidden="true">
                <bea-admin-icon [name]="icon" />
              </span>
            }
            <div class="bea-dept-head__copy">
              <p class="bea-plateforme__kicker">Département</p>
              <h1 class="bea-plateforme__title">{{ espace().titre }}</h1>
              @if (domainesVue().length && espace().description) {
                <p class="bea-dept-head__text">{{ espace().description }}</p>
              }
            </div>
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/accueil">← BEA DIGITAL</a>
          </header>

          @if (domainesVue().length) {
            <section class="bea-hub__section bea-hub__section--fill">
              <div class="bea-hub__section-head">
                <h2>Domaines</h2>
                <p>Chaque domaine affiche son statut réel. Seuls les modules disponibles s’ouvrent.</p>
              </div>
              <div class="bea-dom-grid">
                @for (vue of domainesVue(); track vue.domaine.id) {
                  <article
                    class="bea-dom"
                    [class.bea-dom--peuple]="vue.peuple"
                    [class.bea-dom--attente]="!vue.peuple"
                  >
                    <header class="bea-dom__head">
                      <span class="bea-dom__icon" aria-hidden="true">
                        <bea-admin-icon [name]="vue.domaine.icon || 'folder'" />
                      </span>
                      <div class="bea-dom__titles">
                        <h3 class="bea-dom__title">{{ vue.domaine.titre }}</h3>
                        @if (vue.domaine.description) {
                          <p class="bea-dom__text">{{ vue.domaine.description }}</p>
                        }
                      </div>
                      <span class="bea-badge" [class]="'bea-badge--' + badgeTone(vue.domaine.statut)">
                        {{ badgeLabel(vue.domaine.statut) }}
                      </span>
                    </header>

                    @if (!vue.peuple) {
                      <p class="bea-dom__wait">
                        {{ vue.domaine.status_message || attenteLabel(vue.domaine.statut) }}
                      </p>
                    }

                    @if (vue.modules.length) {
                      <div class="bea-card-grid bea-card-grid--modules bea-dom__modules">
                        @for (mod of vue.modules; track mod.id) {
                          <ng-container *ngTemplateOutlet="moduleCard; context: { $implicit: mod }" />
                        }
                      </div>
                    }

                    @for (sous of vue.sousDomaines; track sous.domaine.id) {
                      @if (sous.modules.length || !vue.peuple) {
                      <section class="bea-dom__sub">
                        <header class="bea-dom__sub-head">
                          <span class="bea-dom__sub-icon" aria-hidden="true">
                            <bea-admin-icon [name]="sous.domaine.icon || 'folder_open'" />
                          </span>
                          <div class="bea-dom__titles">
                            <p class="bea-card__kicker">Sous-domaine</p>
                            <h4 class="bea-dom__sub-title">{{ sous.domaine.titre }}</h4>
                            @if (sous.domaine.description) {
                              <p class="bea-dom__text">{{ sous.domaine.description }}</p>
                            }
                          </div>
                          <span class="bea-badge" [class]="'bea-badge--' + badgeTone(sous.domaine.statut)">
                            {{ badgeLabel(sous.domaine.statut) }}
                          </span>
                        </header>
                        @if (sous.modules.length) {
                          <div class="bea-card-grid bea-card-grid--modules bea-dom__modules">
                            @for (mod of sous.modules; track mod.id) {
                              <ng-container *ngTemplateOutlet="moduleCard; context: { $implicit: mod }" />
                            }
                          </div>
                        } @else {
                          <p class="bea-dom__wait">
                            {{ sous.domaine.status_message || attenteLabel(sous.domaine.statut) }}
                          </p>
                        }
                      </section>
                      }
                    }

                    @if (vue.peuple && sousDomainesEnAttente(vue).length) {
                      <div class="bea-dom__later">
                        <p class="bea-card__kicker">Prochainement</p>
                        <ul class="bea-dom__later-list">
                          @for (sous of sousDomainesEnAttente(vue); track sous.domaine.id) {
                            <li class="bea-dom__later-item" [title]="sous.domaine.description || sous.domaine.titre">
                              <bea-admin-icon [name]="sous.domaine.icon || 'folder_open'" />
                              <span>{{ sous.domaine.titre }}</span>
                              <span class="bea-badge" [class]="'bea-badge--' + badgeTone(sous.domaine.statut)">
                                {{ badgeLabel(sous.domaine.statut) }}
                              </span>
                            </li>
                          }
                        </ul>
                      </div>
                    }
                  </article>
                }
              </div>
            </section>

            @if (modulesHorsDomaine().length) {
              <section class="bea-hub__section">
                <div class="bea-hub__section-head">
                  <h2>Autres modules</h2>
                </div>
                <div class="bea-card-grid bea-card-grid--modules">
                  @for (mod of modulesHorsDomaine(); track mod.id) {
                    <ng-container *ngTemplateOutlet="moduleCard; context: { $implicit: mod }" />
                  }
                </div>
              </section>
            }
          } @else {
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
                  <ng-container *ngTemplateOutlet="moduleCard; context: { $implicit: mod }" />
                }
              </div>
            </section>
          }
        }
      </main>
    </div>

    <ng-template #moduleCard let-mod>
      @if (isOpenable(mod)) {
        <a
          class="bea-card"
          [class.bea-card--actif]="mod.statut === 'actif'"
          [class.bea-card--restreint]="mod.statut !== 'actif'"
          [routerLink]="mod.route!"
        >
          <div class="bea-card__head">
            @if (mod.icon) {
              <span class="bea-card__icon" aria-hidden="true"><bea-admin-icon [name]="mod.icon" /></span>
            }
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
            @if (mod.icon) {
              <span class="bea-card__icon" aria-hidden="true"><bea-admin-icon [name]="mod.icon" /></span>
            }
            <h2 class="bea-card__title">{{ mod.titre }}</h2>
            <span class="bea-badge" [class]="'bea-badge--' + badgeTone(mod.statut)">
              {{ badgeLabel(mod.statut) }}
            </span>
          </div>
          <p class="bea-card__text">{{ mod.description }}</p>
          @if (mod.status_message) {
            <p class="bea-card__hint">{{ mod.status_message }}</p>
          } @else {
            <p class="bea-card__meta">En préparation — bientôt sur BEA DIGITAL</p>
          }
          <div class="bea-card__viz" aria-hidden="true">
            <div class="bea-card__bars">
              <span></span><span></span><span></span><span></span>
              <span></span><span></span><span></span><span></span>
            </div>
            <div class="bea-card__donut"></div>
          </div>
        </div>
      }
    </ng-template>
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

  /** Arbre domaine → sous-domaine → modules (ordre API conservé). */
  readonly domainesVue = computed<DomaineVue[]>(() => {
    const espace = this.espace();
    const domaines = espace.domaines ?? [];
    const modulesDe = (code: string) => espace.modules.filter((m) => m.domaine_id === code);
    return domaines
      .filter((d) => !d.parent_id)
      .map((d) => {
        const sousDomaines = domaines
          .filter((s) => s.parent_id === d.id)
          .map((s) => ({ domaine: s, modules: modulesDe(s.id) }));
        const modules = modulesDe(d.id);
        return {
          domaine: d,
          modules,
          sousDomaines,
          peuple: modules.length > 0 || sousDomaines.some((s) => s.modules.length > 0),
        };
      });
  });

  readonly modulesHorsDomaine = computed(() => {
    const codes = new Set((this.espace().domaines ?? []).map((d) => d.id));
    return this.espace().modules.filter((m) => !m.domaine_id || !codes.has(m.domaine_id));
  });

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

  attenteLabel(statut: string): string {
    if (statut === 'developpement') {
      return 'En développement — aucun module ouvert pour l’instant.';
    }
    if (statut === 'actif') {
      return 'Aucun module visible pour votre compte dans ce domaine.';
    }
    return 'Bientôt disponible — aucune fonctionnalité ouverte pour l’instant.';
  }

  /** Dans un domaine qui porte déjà des modules, les sous-domaines vides restent compacts. */
  sousDomainesEnAttente(vue: DomaineVue): SousDomaineVue[] {
    return vue.sousDomaines.filter((s) => !s.modules.length);
  }
}
