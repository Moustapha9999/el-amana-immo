import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../core/services/auth.service';
import { AuthScreenComponent } from '../auth-screen.component';

@Component({
  selector: 'app-forgot-password',
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, AuthScreenComponent],
  templateUrl: './forgot-password.component.html',
})
export class ForgotPasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);

  readonly loading = signal(false);
  readonly message = signal<string | null>(null);
  readonly devToken = signal<string | null>(null);
  readonly error = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
  });

  submit(): void {
    if (this.form.invalid) {
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.message.set(null);
    this.devToken.set(null);
    const { email } = this.form.getRawValue();
    this.auth.forgotPassword(email).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.message.set(res.message);
        if (res.reset_token) {
          this.devToken.set(res.reset_token);
        }
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err.error?.detail ?? 'Erreur');
      },
    });
  }
}
