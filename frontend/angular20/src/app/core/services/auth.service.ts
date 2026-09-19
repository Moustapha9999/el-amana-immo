import { Injectable, computed, inject, signal } from '@angular/core';
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
  espace_codes?: string[];
  module_codes?: string[];
  permission_codes?: string[];
}

const PLATFORM_ACCESS_KEY = 'bea_access';
const PLATFORM_REFRESH_KEY = 'bea_refresh';
const MODULE_ACCESS_KEY = 'bea_mod_access';
const MODULE_REFRESH_KEY = 'bea_mod_refresh';
const MODULE_CODE_KEY = 'bea_mod_code';
const LEGACY_ACCESS_KEY = 'immo_access';
const LEGACY_REFRESH_KEY = 'immo_refresh';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly user = signal<UserProfile | null>(null);
  readonly canAccessCoreAdmin = computed(() => {
    const profile = this.user();
    if (!profile) {
      return false;
    }
    if (profile.is_superuser) {
      return true;
    }
    const codes = profile.permission_codes ?? [];
    return codes.includes('core.admin.access') || codes.includes('*');
  });

  private platformRefreshInFlight$: Observable<TokenPair> | null = null;
  private moduleRefreshInFlight$: Observable<TokenPair> | null = null;

  constructor() {
    this.migrateLegacyTokens();
  }

  private migrateLegacyTokens(): void {
    const oldAccess = localStorage.getItem(LEGACY_ACCESS_KEY);
    const oldRefresh = localStorage.getItem(LEGACY_REFRESH_KEY);
    if (oldAccess && !localStorage.getItem(PLATFORM_ACCESS_KEY)) {
      localStorage.setItem(PLATFORM_ACCESS_KEY, oldAccess);
      if (oldRefresh) {
        localStorage.setItem(PLATFORM_REFRESH_KEY, oldRefresh);
      }
    }
    localStorage.removeItem(LEGACY_ACCESS_KEY);
    localStorage.removeItem(LEGACY_REFRESH_KEY);
  }

  get accessToken(): string | null {
    return this.platformAccessToken;
  }

  get refreshToken(): string | null {
    return this.platformRefreshToken;
  }

  get platformAccessToken(): string | null {
    return localStorage.getItem(PLATFORM_ACCESS_KEY);
  }

  get platformRefreshToken(): string | null {
    return localStorage.getItem(PLATFORM_REFRESH_KEY);
  }

  get moduleAccessToken(): string | null {
    return localStorage.getItem(MODULE_ACCESS_KEY);
  }

  get moduleRefreshToken(): string | null {
    return localStorage.getItem(MODULE_REFRESH_KEY);
  }

  get moduleCode(): string | null {
    return localStorage.getItem(MODULE_CODE_KEY);
  }

  private storePlatformTokens(tokens: TokenPair): void {
    localStorage.setItem(PLATFORM_ACCESS_KEY, tokens.access_token);
    localStorage.setItem(PLATFORM_REFRESH_KEY, tokens.refresh_token);
  }

  private storeModuleTokens(tokens: TokenPair, moduleCode: string): void {
    localStorage.setItem(MODULE_ACCESS_KEY, tokens.access_token);
    localStorage.setItem(MODULE_REFRESH_KEY, tokens.refresh_token);
    localStorage.setItem(MODULE_CODE_KEY, moduleCode);
  }

  clearModuleSession(): void {
    localStorage.removeItem(MODULE_ACCESS_KEY);
    localStorage.removeItem(MODULE_REFRESH_KEY);
    localStorage.removeItem(MODULE_CODE_KEY);
    this.moduleRefreshInFlight$ = null;
  }

  clearLocalSession(): void {
    localStorage.removeItem(PLATFORM_ACCESS_KEY);
    localStorage.removeItem(PLATFORM_REFRESH_KEY);
    this.user.set(null);
    this.platformRefreshInFlight$ = null;
    this.clearModuleSession();
  }

  login(email: string, password: string, totpCode?: string) {
    this.clearModuleSession();
    return this.api
      .post<TokenPair>('/auth/login', { email, password, totp_code: totpCode ?? null })
      .pipe(tap((tokens) => this.storePlatformTokens(tokens)));
  }

  loginModule(moduleCode: string, email: string, password: string) {
    return this.api
      .post<TokenPair>(`/auth/modules/${moduleCode}/login`, { email, password })
      .pipe(tap((tokens) => this.storeModuleTokens(tokens, moduleCode)));
  }

  loadProfile() {
    return this.api.get<UserProfile>('/auth/me').pipe(tap((profile) => this.user.set(profile)));
  }

  refreshTokens(): Observable<TokenPair> {
    return this.refreshPlatformTokens();
  }

  refreshPlatformTokens(): Observable<TokenPair> {
    const refresh = this.platformRefreshToken;
    if (!refresh) {
      return throwError(() => new Error('Aucun refresh token plateforme'));
    }
    if (!this.platformRefreshInFlight$) {
      this.platformRefreshInFlight$ = this.api
        .post<TokenPair>('/auth/refresh', { refresh_token: refresh })
        .pipe(
          tap((tokens) => this.storePlatformTokens(tokens)),
          finalize(() => {
            this.platformRefreshInFlight$ = null;
          }),
          shareReplay(1),
        );
    }
    return this.platformRefreshInFlight$;
  }

  refreshModuleTokens(): Observable<TokenPair> {
    const refresh = this.moduleRefreshToken;
    const code = this.moduleCode;
    if (!refresh || !code) {
      return throwError(() => new Error('Aucun refresh token module'));
    }
    if (!this.moduleRefreshInFlight$) {
      this.moduleRefreshInFlight$ = this.api
        .post<TokenPair>('/auth/modules/refresh', { refresh_token: refresh })
        .pipe(
          tap((tokens) => this.storeModuleTokens(tokens, code)),
          finalize(() => {
            this.moduleRefreshInFlight$ = null;
          }),
          shareReplay(1),
        );
    }
    return this.moduleRefreshInFlight$;
  }

  logout(options?: { reason?: 'manual' | 'session' }): void {
    this.logoutPlatform(options);
  }

  logoutPlatform(options?: { reason?: 'manual' | 'session' }): void {
    const refresh = this.platformRefreshToken;
    const hadSession = !!(this.platformAccessToken || refresh);
    if (hadSession) {
      this.api
        .post<{ message: string }>('/auth/logout', { refresh_token: refresh })
        .pipe(catchError(() => of(null)))
        .subscribe();
    }
    this.clearLocalSession();
    const queryParams = options?.reason === 'session' ? { reason: 'session' } : undefined;
    void this.router.navigate(['/login'], queryParams ? { queryParams } : undefined);
  }

  logoutModule(options?: { redirectTo?: string }): void {
    const refresh = this.moduleRefreshToken;
    const code = this.moduleCode;
    if (this.moduleAccessToken || refresh) {
      this.api
        .post<{ message: string }>('/auth/modules/logout', { refresh_token: refresh })
        .pipe(catchError(() => of(null)))
        .subscribe();
    }
    this.clearModuleSession();
    // Retour au département — jamais Login 1.
    const dest = options?.redirectTo ?? this.espaceRouteForModule(code);
    void this.router.navigateByUrl(dest);
  }

  private espaceRouteForModule(moduleCode: string | null): string {
    if (moduleCode === 'immobilisations' || !moduleCode) {
      return '/comptabilite';
    }
    return '/accueil';
  }

  isAuthenticated(): boolean {
    return !!this.platformAccessToken;
  }

  hasModuleSession(moduleCode: string): boolean {
    return this.moduleCode === moduleCode && !!this.moduleAccessToken;
  }
}
