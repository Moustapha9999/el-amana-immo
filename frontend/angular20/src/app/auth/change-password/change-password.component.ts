import { Component, inject, signal } from '@angular/core';
import { AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { AuthService } from '../../core/services/auth.service';
import { AuthScreenComponent } from '../auth-screen.component';

function confirmationIdentique(group: AbstractControl): ValidationErrors | null {
  const { new_password, confirm_password } = group.value as Record<string, string>;
  return new_password && confirm_password && new_password !== confirm_password ? { mismatch: true } : null;
}

/** Premier login ou réinitialisation par CORE ADMIN : choix d'un mot de passe personnel. */
@Component({
  selector: 'app-change-password',
  imports: [ReactiveFormsModule, MatIconModule, AuthScreenComponent],
  templateUrl: './change-password.component.html',
})
export class ChangePasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly feedback = inject(FeedbackService);

  readonly busy = signal(false);
  readonly showPassword = signal(false);

  readonly form = this.fb.nonNullable.group(
    {
      current_password: ['', [Validators.required]],
      new_password: ['', [Validators.required, Validators.minLength(8)]],
      confirm_password: ['', [Validators.required]],
    },
    { validators: confirmationIdentique },
  );

  togglePasswordVisibility(): void {
    this.showPassword.update((v) => !v);
  }

  submit(): void {
    if (this.form.invalid || this.busy()) {
      this.form.markAllAsTouched();
      return;
    }
    const { current_password, new_password } = this.form.getRawValue();
    this.feedback
      .run(() => this.auth.changePassword(current_password, new_password), {
        loading: 'Enregistrement du mot de passe…',
        success: { title: 'Mot de passe modifié', message: 'Bienvenue sur BEA DIGITAL.' },
        errorTitle: 'Mot de passe non modifié',
        busy: this.busy,
        retry: false,
      })
      .subscribe(() => {
        this.form.reset();
        void this.router.navigate(['/accueil']);
      });
  }

  logout(): void {
    this.auth.logoutPlatform();
  }
}
