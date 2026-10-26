import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { describeApiError } from '../../core/feedback/api-error';
import { AuthService, CHANGE_PASSWORD_PATH } from '../../core/services/auth.service';
import { AuthScreenComponent } from '../auth-screen.component';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, MatCheckboxModule, MatIconModule, AuthScreenComponent],
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
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
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
          next: (profile) => {
            this.loading.set(false);
            void this.router.navigate([profile.must_change_password ? CHANGE_PASSWORD_PATH : '/accueil']);
          },
          error: () => {
            this.loading.set(false);
            this.error.set('Connexion réussie, mais votre profil n’a pas pu être chargé. Réessayez dans quelques instants.');
          },
        });
      },
      error: (err: unknown) => {
        this.loading.set(false);
        const info = describeApiError(err);
        if (info.code === 'TOTP_REQUIRED' || info.code === 'TOTP_INVALID') {
          this.totpRequired.set(true);
        }
        this.error.set(info.status === 422 ? 'Vérifiez le format de l’adresse e-mail et du mot de passe.' : info.message);
      },
    });
  }
}
