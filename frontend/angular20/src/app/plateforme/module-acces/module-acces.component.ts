import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { ApiService } from '../../core/services/api.service';
import { BeaChromeComponent } from '../chrome/bea-chrome.component';
import { FilArianeComponent } from '../fil-ariane/fil-ariane.component';

interface ModuleInfo {
  id: string;
  titre: string;
  description: string;
  entry_path: string | null;
  accessible: boolean;
  espace_id?: string | null;
  espace_titre?: string | null;
  espace_route?: string | null;
}

@Component({
  selector: 'bea-module-acces',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, BeaChromeComponent, FilArianeComponent],
  template: `
    <div class="bea-plateforme">
      <bea-chrome />
      <bea-fil-ariane />
      <main class="bea-module-acces">
        <section class="bea-module-acces__card">
          <p class="bea-module-acces__kicker">Accès sécurisé au module</p>
          <h1 class="bea-module-acces__title">{{ titre() }}</h1>
          <p class="bea-module-acces__lead">
            Cette authentification protège les fonctions internes du module. Elle est distincte de
            la connexion BEA DIGITAL.
          </p>
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

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly titre = signal('Module');
  readonly entryPath = signal('/dashboard');
  readonly espaceRoute = signal('/comptabilite');

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  ngOnInit(): void {
    const moduleCode = this.moduleCode;
    if (this.auth.hasModuleSession(moduleCode)) {
      void this.router.navigateByUrl(this.returnUrl);
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
        if (info.entry_path) {
          this.entryPath.set(info.entry_path);
        }
        if (info.espace_route) {
          this.espaceRoute.set(info.espace_route);
        }
        if (!info.accessible) {
          this.error.set("Vous n'êtes pas autorisé à accéder à ce module.");
        }
      },
      error: () => {
        this.error.set('Module introuvable.');
      },
    });
  }

  private get moduleCode(): string {
    return this.route.snapshot.paramMap.get('moduleCode') ?? 'immobilisations';
  }

  private get returnUrl(): string {
    return this.route.snapshot.queryParamMap.get('returnUrl') || this.entryPath();
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    const { email, password } = this.form.getRawValue();
    this.auth.loginModule(this.moduleCode, email, password).subscribe({
      next: () => {
        this.loading.set(false);
        void this.router.navigateByUrl(this.returnUrl);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        if (err instanceof HttpErrorResponse) {
          if (err.status === 429) {
            const detail = err.error?.detail;
            this.error.set(
              typeof detail === 'object' ? (detail.message ?? 'Trop de tentatives.') : 'Trop de tentatives.',
            );
            return;
          }
          if (err.status === 403) {
            this.error.set("Vous n'êtes pas autorisé à accéder à ce module.");
            return;
          }
          const detail = err.error?.detail;
          this.error.set(typeof detail === 'string' ? detail : 'Identifiants invalides');
          return;
        }
        this.error.set('Identifiants invalides');
      },
    });
  }
}
