import { Component, inject, OnInit } from '@angular/core';
import { Router } from '@angular/router';

/** Reset public désactivé — redirection Login 1. */
@Component({
  selector: 'app-forgot-password',
  template: `<p class="login-panel__error">Réinitialisation publique désactivée. Contactez un administrateur.</p>`,
})
export class ForgotPasswordComponent implements OnInit {
  private readonly router = inject(Router);

  ngOnInit(): void {
    void this.router.navigate(['/login']);
  }
}
