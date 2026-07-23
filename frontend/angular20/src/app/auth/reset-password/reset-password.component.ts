import { Component, inject, OnInit, signal } from '@angular/core';
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
export class ResetPasswordComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    token: ['', Validators.required],
    new_password: ['', [Validators.required, Validators.minLength(8)]],
    confirm: ['', Validators.required],
  });

  ngOnInit(): void {
    const token = this.route.snapshot.queryParamMap.get('token');
    if (token) {
      this.form.patchValue({ token });
    }
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
    this.loading.set(true);
    this.error.set(null);
    this.auth.resetPassword(token, new_password).subscribe({
      next: () => {
        this.loading.set(false);
        void this.router.navigate(['/login'], { queryParams: { reset: 'ok' } });
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err.error?.detail ?? 'Réinitialisation impossible');
      },
    });
  }
}
