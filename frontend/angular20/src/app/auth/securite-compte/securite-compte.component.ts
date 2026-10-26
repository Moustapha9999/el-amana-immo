import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AuthScreenComponent } from '../auth-screen.component';

interface TotpSetup {
  secret: string;
  otpauth_url: string;
  qr_image_base64: string;
}

/** Activation de la double authentification (Login 1 seul, sans session module). */
@Component({
  selector: 'app-securite-compte',
  imports: [ReactiveFormsModule, MatIconModule, AuthScreenComponent],
  templateUrl: './securite-compte.component.html',
})
export class SecuriteCompteComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly feedback = inject(FeedbackService);

  readonly mfaExigee = this.route.snapshot.queryParamMap.get('raison') === 'mfa';
  readonly enabled = signal<boolean | null>(null);
  readonly setup = signal<TotpSetup | null>(null);
  readonly busy = signal(false);

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.pattern(/^\d{6,8}$/)]],
  });

  readonly desactivation = this.fb.nonNullable.group({
    password: ['', [Validators.required, Validators.minLength(8)]],
    code: ['', [Validators.required, Validators.pattern(/^\d{6,8}$/)]],
  });

  ngOnInit(): void {
    this.api.get<{ enabled: boolean }>('/auth/2fa/status').subscribe({
      next: (s) => this.enabled.set(s.enabled),
      error: () => this.enabled.set(false),
    });
  }

  demarrer(): void {
    this.feedback
      .run(() => this.api.post<TotpSetup>('/auth/2fa/setup', {}), {
        success: () => null,
        errorTitle: 'Configuration impossible',
        busy: this.busy,
        retry: false,
      })
      .subscribe((res) => this.setup.set(res));
  }

  activer(): void {
    if (this.form.invalid || this.busy()) {
      this.form.markAllAsTouched();
      return;
    }
    const code = this.form.getRawValue().code.trim();
    this.feedback
      .run(() => this.api.post<{ message: string }>('/auth/2fa/enable', { code }), {
        loading: 'Vérification du code…',
        success: { title: 'Double authentification activée', message: 'Le code vous sera demandé à chaque connexion.' },
        errorTitle: 'Code refusé',
        busy: this.busy,
        retry: false,
      })
      .subscribe(() => {
        this.form.reset();
        this.setup.set(null);
        this.enabled.set(true);
      });
  }

  desactiver(): void {
    if (this.desactivation.invalid || this.busy()) {
      this.desactivation.markAllAsTouched();
      return;
    }
    const { code, password } = this.desactivation.getRawValue();
    this.feedback
      .run(() => this.api.post<{ message: string }>('/auth/2fa/disable', { code: code.trim(), password }), {
        confirm: {
          title: 'Désactiver la double authentification',
          message: 'Votre compte ne sera plus protégé que par le mot de passe. Continuer ?',
          confirmLabel: 'Désactiver',
          tone: 'warn',
        },
        loading: 'Désactivation…',
        success: { title: 'Double authentification désactivée' },
        errorTitle: 'Désactivation refusée',
        busy: this.busy,
        retry: false,
      })
      .subscribe(() => {
        this.desactivation.reset();
        this.enabled.set(false);
      });
  }

  continuer(): void {
    void this.router.navigate([this.mfaExigee && this.enabled() ? '/admin' : '/accueil']);
  }
}
