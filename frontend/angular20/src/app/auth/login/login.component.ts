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

  private static readonly REMEMBER_KEY = 'el_amana_login_email';

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
    const saved = localStorage.getItem(LoginComponent.REMEMBER_KEY);
    if (saved) {
      this.form.patchValue({ email: saved, remember_me: true });
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
    } else {
      localStorage.removeItem(LoginComponent.REMEMBER_KEY);
    }
    this.auth.login(email, password, totp).subscribe({
      next: () => {
        this.auth.loadProfile().subscribe({
          next: () => {
            this.loading.set(false);
            void this.router.navigate(['/dashboard']);
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
            this.error.set(err.error?.detail ?? 'Erreur de connexion');
          }
        } else {
          this.error.set('Identifiants invalides');
        }
      },
    });
  }
}
