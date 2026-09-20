import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { ApiService } from '../../core/services/api.service';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { PlateformeContextService } from '../plateforme-context.service';
import { LEGACY_ROOT_MODULE_CODE, resolveEspacePathForModule, resolveModuleEntryPath } from '../module-routing.contract';

interface ModuleInfo {
  id: string;
  titre: string;
  description: string;
  entry_path: string | null;
  accessible: boolean;
  access_allowed?: boolean | null;
  block_reason?: string | null;
  status_message?: string;
  statut?: string;
  version?: string | null;
  maintenance_ends_at?: string | null;
  espace_id?: string | null;
  espace_titre?: string | null;
  espace_route?: string | null;
}

@Component({
  selector: 'bea-module-acces',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, BeaChromeComponent],
  template: `
    <div class="bea-plateforme">
      <bea-chrome />
      <main class="bea-module-acces">
        @if (blocked()) {
          <div class="bea-module-block" role="dialog" aria-modal="true" aria-labelledby="bea-block-title">
            <div class="bea-module-block__backdrop"></div>
            <div class="bea-module-block__panel">
              <p class="bea-module-block__kicker">{{ espaceTitre() || 'BEA DIGITAL' }}</p>
              <p class="bea-module-block__badge">{{ statutLabel() }}</p>
              <h1 id="bea-block-title" class="bea-module-block__title">{{ titre() }}</h1>
              <p class="bea-module-block__message">{{ blockMessage() }}</p>
              @if (maintenanceEnds()) {
                <p class="bea-module-block__meta">Fin prévue : {{ maintenanceEnds() }}</p>
              }
              <div class="bea-module-block__actions">
                <a class="bea-module-block__cta" [routerLink]="espaceRoute()">
                  Retour aux modules — {{ espaceTitre() || 'département' }}
                </a>
              </div>
            </div>
          </div>
        } @else if (shellPending()) {
          <section class="bea-module-acces__card">
            <p class="bea-module-acces__kicker">{{ espaceTitre() || 'BEA DIGITAL' }}</p>
            <h1 class="bea-module-acces__title">{{ titre() }}</h1>
            <p class="bea-module-acces__error" style="color: inherit">
              Connexion module réussie. Le métier n’est pas encore branché sur BEA DIGITAL
              (ateliers départements en cours). Le catalogue et les droits sont déjà actifs.
            </p>
            <a class="bea-module-acces__back" [routerLink]="espaceRoute()">Retour aux modules</a>
          </section>
        } @else {
          <section class="bea-module-acces__card">
            <p class="bea-module-acces__kicker">Accès sécurisé au module</p>
            <h1 class="bea-module-acces__title">{{ titre() }}</h1>
            <form [formGroup]="form" (ngSubmit)="submit()" class="bea-module-acces__form">
              <label class="bea-module-acces__field">
                <span>Identifiant</span>
                <input type="email" formControlName="email" autocomplete="username" />
              </label>
              <label class="bea-module-acces__field">
                <span>Mot de passe</span>
                <input type="password" formControlName="password" autocomplete="current-password" />
              </label>
              @if (error()) {
                <p class="bea-module-acces__error">{{ error() }}</p>
              }
              <button type="submit" class="bea-module-acces__submit" [disabled]="loading()">
                {{ loading() ? 'Connexion…' : 'Se connecter' }}
              </button>
            </form>
            <a class="bea-module-acces__back" [routerLink]="espaceRoute()">Retour aux modules</a>
          </section>
        }
      </main>
    </div>
  `,
})
export class ModuleAccesComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly nav = inject(PlateformeContextService);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly titre = signal('Module');
  readonly entryPath = signal<string | null>(null);
  readonly espaceRoute = signal('/accueil');
  readonly espaceTitre = signal('BEA DIGITAL');
  readonly blocked = signal(false);
  readonly shellPending = signal(false);
  readonly blockMessage = signal('');
  readonly statutLabel = signal('');
  readonly maintenanceEnds = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  ngOnInit(): void {
    const moduleCode = this.moduleCode;
    if (this.auth.hasModuleSession(moduleCode)) {
      this.enterModuleOrPending();
      return;
    }
    const user = this.auth.user();
    if (user?.email) {
      this.form.patchValue({ email: user.email });
    } else if (this.auth.isAuthenticated()) {
      this.auth.loadProfile().subscribe({
        next: (profile) => this.form.patchValue({ email: profile.email }),
        error: () => undefined,
      });
    }
    this.api.get<ModuleInfo>(`/plateforme/modules/${moduleCode}`).subscribe({
      next: (info) => {
        this.titre.set(info.titre);
        this.entryPath.set(
          (info.entry_path || '').trim() || resolveModuleEntryPath(moduleCode),
        );
        if (info.espace_route) {
          this.espaceRoute.set(info.espace_route);
        } else {
          this.espaceRoute.set(resolveEspacePathForModule(moduleCode));
        }
        if (info.espace_titre) {
          this.espaceTitre.set(info.espace_titre);
        }
        this.nav.setFromModuleInfo({
          moduleCode,
          titre: info.titre,
          entry_path: info.entry_path,
          espace_route: info.espace_route,
          espace_titre: info.espace_titre,
        });
        const loginOk = info.access_allowed === true || (info.access_allowed == null && info.accessible);
        if (!loginOk && info.statut && info.statut !== 'actif') {
          this.applyBlock(info.statut, info.status_message, info.maintenance_ends_at);
        }
      },
      error: () => undefined,
    });
  }

  submit(): void {
    if (this.form.invalid || this.loading()) {
      this.form.markAllAsTouched();
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    const { email, password } = this.form.getRawValue();
    this.auth.loginModule(this.moduleCode, email, password).subscribe({
      next: () => {
        this.loading.set(false);
        this.enterModuleOrPending();
      },
      error: (err: unknown) => {
        this.loading.set(false);
        if (err instanceof HttpErrorResponse) {
          const detail = err.error?.detail;
          if (detail?.code === 'MODULE_UNAVAILABLE') {
            this.applyBlock(detail.statut || 'maintenance', detail.message, null);
            return;
          }
        }
        this.error.set('Identifiants invalides ou accès refusé.');
      },
    });
  }

  /** Shell métier branché uniquement pour Immobilisations tant que les ateliers n’ont pas abouti. */
  private moduleHasMetierShell(code: string): boolean {
    return code === LEGACY_ROOT_MODULE_CODE;
  }

  private enterModuleOrPending(): void {
    if (this.moduleHasMetierShell(this.moduleCode)) {
      void this.router.navigateByUrl(this.returnUrl);
      return;
    }
    this.shellPending.set(true);
  }

  private applyBlock(
    statut: string,
    message: string | null | undefined,
    ends: string | null | undefined,
  ): void {
    this.blocked.set(true);
    this.blockMessage.set(
      (message && message.trim()) ||
        'Ce module est temporairement indisponible. Merci de réessayer ultérieurement.',
    );
    this.statutLabel.set(this.labelFor(statut));
    this.maintenanceEnds.set(ends ?? null);
  }

  private labelFor(statut: string): string {
    const map: Record<string, string> = {
      maintenance: 'Maintenance',
      mise_a_jour: 'Mise à jour en cours',
      developpement: 'Module en développement',
      bientot: 'Bientôt disponible',
      suspendu: 'Module suspendu',
      bloque: 'Module bloqué',
      archive: 'Module archivé',
      inactif: 'Module inactif',
    };
    return map[statut] || statut;
  }

  private get moduleCode(): string {
    return this.route.snapshot.paramMap.get('moduleCode') || 'immobilisations';
  }

  private get returnUrl(): string {
    return this.route.snapshot.queryParamMap.get('returnUrl') || this.entryPath() || '/accueil';
  }
}
