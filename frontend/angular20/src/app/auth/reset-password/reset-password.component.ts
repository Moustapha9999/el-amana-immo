import { Component, DestroyRef, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../core/services/auth.service';
import { AuthScreenComponent } from '../auth-screen.component';

@Component({
  selector: 'app-reset-password',
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, AuthScreenComponent],
  templateUrl: './reset-password.component.html',
})
export class ResetPasswordComponent implements OnInit, OnDestroy {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly secondsLeft = signal<number | null>(null);
  readonly showPassword = signal(false);
  readonly showConfirm = signal(false);

  private countdownId: ReturnType<typeof setInterval> | null = null;

  readonly form = this.fb.nonNullable.group({
    token: ['', Validators.required],
    new_password: ['', [Validators.required, Validators.minLength(8)]],
    confirm: ['', Validators.required],
  });

  ngOnInit(): void {
    const token = this.route.snapshot.queryParamMap.get('token');
    if (token) {
      this.form.patchValue({ token });
      const remaining = this.secondsUntilJwtExpiry(token);
      if (remaining <= 0) {
        void this.router.navigate(['/login'], { queryParams: { reset: 'expired' } });
        return;
      }
      this.startCountdown(remaining);
    }
  }

  ngOnDestroy(): void {
    this.clearCountdown();
  }

  togglePassword(): void {
    this.showPassword.update((v) => !v);
  }

  toggleConfirm(): void {
    this.showConfirm.update((v) => !v);
  }

  submit(): void {
    if (this.form.invalid) {
      return;
    }
    const { token, new_password, confirm } = this.form.getRawValue();
    if (new_password !== confirm) {
      this.error.set('Les mots de passe ne correspondent pas');
      return;
    }
    if ((this.secondsLeft() ?? 1) <= 0) {
      void this.router.navigate(['/login'], { queryParams: { reset: 'expired' } });
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.auth.resetPassword(token, new_password).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.loading.set(false);
        this.clearCountdown();
        void this.router.navigate(['/login'], { queryParams: { reset: 'ok' } });
      },
      error: (err) => {
        this.loading.set(false);
        const detail = err.error?.detail ?? 'Réinitialisation impossible';
        this.error.set(detail);
        if (typeof detail === 'string' && detail.toLowerCase().includes('expir')) {
          setTimeout(() => {
            void this.router.navigate(['/login'], { queryParams: { reset: 'expired' } });
          }, 1200);
        }
      },
    });
  }

  private secondsUntilJwtExpiry(token: string): number {
    try {
      const part = token.split('.')[1];
      if (!part) {
        return 0;
      }
      const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'));
      const payload = JSON.parse(json) as { exp?: number };
      if (!payload.exp) {
        return 0;
      }
      return Math.max(0, Math.floor(payload.exp - Date.now() / 1000));
    } catch {
      return 0;
    }
  }

  private startCountdown(seconds: number): void {
    this.clearCountdown();
    this.secondsLeft.set(seconds);
    this.countdownId = setInterval(() => {
      const left = (this.secondsLeft() ?? 0) - 1;
      if (left <= 0) {
        this.clearCountdown();
        this.secondsLeft.set(0);
        void this.router.navigate(['/login'], { queryParams: { reset: 'expired' } });
        return;
      }
      this.secondsLeft.set(left);
    }, 1000);
  }

  private clearCountdown(): void {
    if (this.countdownId !== null) {
      clearInterval(this.countdownId);
      this.countdownId = null;
    }
  }
}
