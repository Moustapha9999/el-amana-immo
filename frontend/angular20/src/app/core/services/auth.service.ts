import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, of, throwError } from 'rxjs';
import { catchError, finalize, shareReplay, tap } from 'rxjs/operators';
import { ApiService } from './api.service';

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  is_superuser: boolean;
  roles: { code: string; label: string }[];
}

const ACCESS_KEY = 'immo_access';
const REFRESH_KEY = 'immo_refresh';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly user = signal<UserProfile | null>(null);

  /** Évite les refresh concurrents (plusieurs 401 en parallèle). */
  private refreshInFlight$: Observable<TokenPair> | null = null;

  get accessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  get refreshToken(): string | null {
    return localStorage.getItem(REFRESH_KEY);
  }

  private storeTokens(tokens: TokenPair): void {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }

  clearLocalSession(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    this.user.set(null);
    this.refreshInFlight$ = null;
  }

  login(email: string, password: string, totpCode?: string) {
    return this.api
      .post<TokenPair>('/auth/login', { email, password, totp_code: totpCode ?? null })
      .pipe(tap((tokens) => this.storeTokens(tokens)));
  }

  loadProfile() {
    return this.api.get<UserProfile>('/auth/me').pipe(tap((profile) => this.user.set(profile)));
  }

  /** Renouvelle la paire JWT via refresh token. */
  refreshTokens(): Observable<TokenPair> {
    const refresh = this.refreshToken;
    if (!refresh) {
      return throwError(() => new Error('Aucun refresh token'));
    }
    if (!this.refreshInFlight$) {
      this.refreshInFlight$ = this.api.post<TokenPair>('/auth/refresh', { refresh_token: refresh }).pipe(
        tap((tokens) => this.storeTokens(tokens)),
        finalize(() => {
          this.refreshInFlight$ = null;
        }),
        shareReplay(1),
      );
    }
    return this.refreshInFlight$;
  }

  /**
   * Déconnexion : révoque la session côté serveur puis purge locale.
   * @param reason `idle` = inactivité 5 min
   */
  logout(options?: { reason?: 'idle' | 'manual' | 'session' }): void {
    const refresh = this.refreshToken;
    const hadSession = !!(this.accessToken || refresh);

    if (hadSession) {
      this.api
        .post<{ message: string }>('/auth/logout', { refresh_token: refresh })
        .pipe(catchError(() => of(null)))
        .subscribe();
    }

    this.clearLocalSession();
    const queryParams =
      options?.reason === 'idle'
        ? { reason: 'idle' }
        : options?.reason === 'session'
          ? { reason: 'session' }
          : undefined;
    void this.router.navigate(['/login'], queryParams ? { queryParams } : undefined);
  }

  isAuthenticated(): boolean {
    return !!this.accessToken;
  }

  forgotPassword(email: string) {
    return this.api.post<{
      message: string;
      reset_token?: string | null;
      account_found?: boolean;
      dev_mode?: boolean;
      expires_in_seconds?: number | null;
    }>('/auth/forgot-password', { email });
  }

  resetPassword(token: string, new_password: string) {
    return this.api.post<{ message: string }>('/auth/reset-password', { token, new_password });
  }
}
