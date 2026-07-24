import { Component, DestroyRef, inject, OnDestroy, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../core/services/auth.service';
import { AuthScreenComponent } from '../auth-screen.component';

@Component({
  selector: 'app-forgot-password',
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, AuthScreenComponent],
  templateUrl: './forgot-password.component.html',
})
export class ForgotPasswordComponent implements OnDestroy {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly message = signal<string | null>(null);
  readonly devToken = signal<string | null>(null);
  readonly accountFound = signal<boolean | null>(null);
  readonly error = signal<string | null>(null);
  readonly secondsLeft = signal<number | null>(null);

  private countdownId: ReturnType<typeof setInterval> | null = null;

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
  });

  ngOnDestroy(): void {
    this.clearCountdown();
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.message.set(null);
    this.devToken.set(null);
    this.accountFound.set(null);
    this.clearCountdown();
    const { email } = this.form.getRawValue();
    this.auth.forgotPassword(email.trim()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.message.set(res.message);
        this.accountFound.set(res.account_found ?? null);
        if (res.reset_token) {
          this.devToken.set(res.reset_token);
          this.startCountdown(res.expires_in_seconds ?? 45);
        }
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err.error?.detail ?? 'Erreur');
      },
    });
  }

  private startCountdown(seconds: number): void {
    this.clearCountdown();
    this.secondsLeft.set(seconds);
    this.countdownId = setInterval(() => {
      const left = (this.secondsLeft() ?? 0) - 1;
      if (left <= 0) {
        this.clearCountdown();
        this.devToken.set(null);
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
    this.secondsLeft.set(null);
  }
}
