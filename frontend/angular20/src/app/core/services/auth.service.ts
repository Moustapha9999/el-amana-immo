import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';
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

  get accessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  login(email: string, password: string, totpCode?: string) {
    return this.api
      .post<TokenPair>('/auth/login', { email, password, totp_code: totpCode ?? null })
      .pipe(
      tap((tokens) => {
        localStorage.setItem(ACCESS_KEY, tokens.access_token);
        localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
      }),
    );
  }

  loadProfile() {
    return this.api.get<UserProfile>('/auth/me').pipe(tap((profile) => this.user.set(profile)));
  }

  logout(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    this.user.set(null);
    void this.router.navigate(['/login']);
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
