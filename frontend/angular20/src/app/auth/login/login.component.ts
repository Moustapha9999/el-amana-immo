import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../core/services/auth.service';
import { AuthScreenComponent } from '../auth-screen.component';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, MatCheckboxModule, MatIconModule, RouterLink, AuthScreenComponent],
  templateUrl: './login.component.html',
})
export class LoginComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private static readonly REMEMBER_KEY = 'bea_login_email';
  private static readonly LEGACY_REMEMBER_KEY = 'el_amana_login_email';

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly info = signal<string | null>(null);
  readonly totpRequired = signal(false);
  readonly showPassword = signal(false);

  togglePasswordVisibility(): void {
    this.showPassword.update((v) => !v);
  }

  readonly form = this.fb.nonNullable.group({
    email: ['admin@el-amana.mr', [Validators.required, Validators.email]],
    password: ['Admin@2026', [Validators.required, Validators.minLength(8)]],
    totp_code: [''],
    remember_me: [false],
  });

  ngOnInit(): void {
    const saved =
      localStorage.getItem(LoginComponent.REMEMBER_KEY) ??
      localStorage.getItem(LoginComponent.LEGACY_REMEMBER_KEY);
    if (saved) {
      this.form.patchValue({ email: saved, remember_me: true });
      localStorage.setItem(LoginComponent.REMEMBER_KEY, saved);
      localStorage.removeItem(LoginComponent.LEGACY_REMEMBER_KEY);
    }
    const reset = this.route.snapshot.queryParamMap.get('reset');
    if (reset === 'expired') {
      this.info.set('Lien de réinitialisation expiré — recommencez depuis Mot de passe oublié.');
    } else if (reset === 'ok') {
      this.info.set('Mot de passe mis à jour. Vous pouvez vous connecter.');
    }
    const reason = this.route.snapshot.queryParamMap.get('reason');
    if (reason === 'session') {
      this.info.set('Session expirée ou révoquée. Reconnectez-vous.');
    }
  }

  submit(): void {
    if (this.form.invalid) {
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    const { email, password, totp_code, remember_me } = this.form.getRawValue();
    const totp = totp_code.trim() || undefined;
    if (remember_me) {
      localStorage.setItem(LoginComponent.REMEMBER_KEY, email);
      localStorage.removeItem(LoginComponent.LEGACY_REMEMBER_KEY);
    } else {
      localStorage.removeItem(LoginComponent.REMEMBER_KEY);
      localStorage.removeItem(LoginComponent.LEGACY_REMEMBER_KEY);
    }
    this.auth.login(email, password, totp).subscribe({
      next: () => {
        this.auth.loadProfile().subscribe({
          next: () => {
            this.loading.set(false);
            void this.router.navigate(['/accueil']);
          },
          error: () => {
            this.loading.set(false);
            this.error.set('Profil inaccessible');
          },
        });
      },
      error: (err: unknown) => {
        this.loading.set(false);
        if (err instanceof HttpErrorResponse) {
          if (err.status === 0) {
            this.error.set('API inaccessible — vérifiez que le backend tourne sur le port 8000');
            } else if (err.status === 429) {
            const detail = err.error?.detail;
            this.error.set(
              typeof detail === 'object' && detail?.message
                ? detail.message
                : 'Trop de tentatives. Réessayez dans quelques minutes.',
            );
          } else if (err.status === 401) {
            const detail = err.error?.detail;
            if (typeof detail === 'object' && detail?.code === 'TOTP_REQUIRED') {
              this.totpRequired.set(true);
              this.error.set(detail.message ?? 'Code authenticator requis');
            } else if (typeof detail === 'string' && detail.includes('2FA')) {
              this.totpRequired.set(true);
              this.error.set(detail);
            } else {
              this.error.set(typeof detail === 'string' ? detail : 'Identifiants invalides');
            }
          } else {
            const message = typeof err.error?.detail === 'string' ? err.error.detail : 'Erreur de connexion';
            this.error.set(message);
          }
        } else {
          this.error.set('Identifiants invalides');
        }
      },
    });
  }
}
