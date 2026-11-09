import { HttpClient, HttpContext } from '@angular/common/http';
import { Component, DestroyRef, inject, signal, ViewEncapsulation } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SKIP_ERROR_TOAST } from '../core/feedback/http-feedback';

@Component({
  selector: 'app-auth-screen',
  templateUrl: './auth-screen.component.html',
  styleUrl: './auth-screen.component.scss',
  encapsulation: ViewEncapsulation.None,
})
export class AuthScreenComponent {
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  /** Numéro servi par GET /version (APP_VERSION), jamais écrit dans le modèle. */
  readonly version = signal<string | null>(null);

  constructor() {
    this.http
      .get<{ version?: string }>('/version', {
        context: new HttpContext().set(SKIP_ERROR_TOAST, true),
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (body) => {
          const version = typeof body?.version === 'string' ? body.version.trim() : '';
          if (version) this.version.set(version);
        },
        error: () => undefined,
      });
  }
}
