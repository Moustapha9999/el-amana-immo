import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, of, throwError } from 'rxjs';
import { catchError, finalize, shareReplay, tap } from 'rxjs/operators';
import { ApiService } from './api.service';
import { PlateformeContextService } from '../../plateforme/plateforme-context.service';
import { resolveEspacePathForModule } from '../../plateforme/module-routing.contract';

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
  must_change_password?: boolean;
  roles: { code: string; label: string }[];
  espace_codes?: string[];
  module_codes?: string[];
  permission_codes?: string[];
}

/** Écran imposé tant qu'un mot de passe fixé par un administrateur n'a pas été changé. */
export const CHANGE_PASSWORD_PATH = '/changer-mot-de-passe';

/**
 * Jetons d'accès en mémoire uniquement ; refresh tokens en cookies HttpOnly posés par le backend
 * (en-tête X-BEA-Auth: cookie ajouté par l'intercepteur sur /auth/*). Le localStorage ne garde que
 * des indicateurs non secrets.
 */
const SESSION_HINT_KEY = 'bea_session';
const MODULE_CODE_KEY = 'bea_mod_code';
const LEGACY_PLATFORM_REFRESH_KEYS = ['bea_refresh', 'immo_refresh'];
const LEGACY_TOKEN_KEYS = ['bea_access', 'bea_refresh', 'bea_mod_access', 'bea_mod_refresh', 'immo_access', 'immo_refresh'];
const REFRESH_LOCK = 'bea-auth-refresh';

/** Sérialise les renouvellements entre onglets : le cookie tourne à chaque refresh. */
function withRefreshLock<T>(source: Observable<T>): Observable<T> {
  const locks = (navigator as Navigator & { locks?: LockManager }).locks;
  if (!locks) {
    return source;
  }
  return new Observable<T>((subscriber) => {
    let inner: { unsubscribe(): void } | null = null;
    let release: () => void = () => undefined;
    let closed = false;
    void locks.request(REFRESH_LOCK, () =>
      new Promise<void>((resolve) => {
        release = resolve;
        if (closed) {
          resolve();
          return;
        }
        inner = source.subscribe({
          next: (v) => subscriber.next(v),
          error: (e) => {
            resolve();
            subscriber.error(e);
          },
          complete: () => {
            resolve();
            subscriber.complete();
          },
        });
      }),
    );
    return () => {
      closed = true;
      inner?.unsubscribe();
      release();
    };
  });
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly plateformeContext = inject(PlateformeContextService);

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
  /** Suppression administrateur du stock (périodes clôturées, workflows) — contrôlée aussi côté backend. */
  readonly canForceStockDelete = computed(() => {
    const profile = this.user();
    if (!profile) return false;
    if (profile.is_superuser) return true;
    const codes = profile.permission_codes ?? [];
    return codes.includes('*') || codes.includes('mg.stock.period.reopen') || codes.includes('mg.admin');
  });
  /** Joindre / détacher des pièces GED — contrôlé aussi côté backend (`ged.write`). */
  readonly canWriteGed = computed(() => {
    const profile = this.user();
    if (!profile) return false;
    if (profile.is_superuser) return true;
    const codes = profile.permission_codes ?? [];
    return codes.includes('*') || codes.includes('ged.write');
  });

  private platformRefreshInFlight$: Observable<TokenPair> | null = null;
  private moduleRefreshInFlight$: Observable<TokenPair> | null = null;
  private moduleRefreshInFlightCode: string | null = null;
  private platformAccess: string | null = null;
  private moduleAccess: string | null = null;
  private currentModuleCode: string | null = null;

  get platformAccessToken(): string | null {
    return this.platformAccess;
  }

  get moduleAccessToken(): string | null {
    return this.moduleAccess;
  }

  get moduleCode(): string | null {
    return this.currentModuleCode;
  }

  /** Session plateforme probablement ouverte (cookie HttpOnly illisible) : un refresh vaut la peine. */
  get hasPlatformSessionHint(): boolean {
    return !!this.platformAccess || localStorage.getItem(SESSION_HINT_KEY) === '1';
  }

  /** Dernier module ouvert dans ce navigateur (indicateur non secret). */
  get lastModuleCode(): string | null {
    return this.currentModuleCode ?? localStorage.getItem(MODULE_CODE_KEY);
  }

  private storePlatformTokens(tokens: TokenPair): void {
    this.platformAccess = tokens.access_token;
    localStorage.setItem(SESSION_HINT_KEY, '1');
  }

  private storeModuleTokens(tokens: TokenPair, moduleCode: string): void {
    this.moduleAccess = tokens.access_token;
    this.currentModuleCode = moduleCode;
    localStorage.setItem(MODULE_CODE_KEY, moduleCode);
  }

  /**
   * Au démarrage : reprend la session plateforme (puis module) via les cookies HttpOnly.
   * Une session de l'ancien stockage localStorage est migrée une fois vers le cookie.
   */
  restoreSession(): Promise<void> {
    const legacyRefresh = LEGACY_PLATFORM_REFRESH_KEYS.map((k) => localStorage.getItem(k)).find((v) => !!v) ?? null;
    LEGACY_TOKEN_KEYS.forEach((k) => localStorage.removeItem(k));
    if (!legacyRefresh && localStorage.getItem(SESSION_HINT_KEY) !== '1') {
      return Promise.resolve();
    }
    return new Promise<void>((resolve) => {
      this.refreshPlatformTokens(legacyRefresh).subscribe({
        next: () => {
          const code = localStorage.getItem(MODULE_CODE_KEY);
          if (!code) {
            resolve();
            return;
          }
          this.refreshModuleTokens(code).subscribe({ next: () => resolve(), error: () => resolve() });
        },
        error: () => {
          localStorage.removeItem(SESSION_HINT_KEY);
          resolve();
        },
      });
    });
  }

  clearModuleSession(): void {
    this.moduleAccess = null;
    this.currentModuleCode = null;
    localStorage.removeItem(MODULE_CODE_KEY);
    this.moduleRefreshInFlight$ = null;
    this.plateformeContext.clear();
  }

  clearLocalSession(): void {
    this.platformAccess = null;
    localStorage.removeItem(SESSION_HINT_KEY);
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

  changePassword(currentPassword: string, newPassword: string) {
    return this.api
      .post<{ message: string }>('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .pipe(
        tap(() => {
          const profile = this.user();
          if (profile) {
            this.user.set({ ...profile, must_change_password: false });
          }
        }),
      );
  }

  refreshTokens(): Observable<TokenPair> {
    return this.refreshPlatformTokens();
  }

  /** `legacyRefresh` : jeton de l'ancien stockage, échangé une seule fois contre le cookie. */
  refreshPlatformTokens(legacyRefresh?: string | null): Observable<TokenPair> {
    if (!this.platformRefreshInFlight$) {
      const body = legacyRefresh ? { refresh_token: legacyRefresh } : {};
      this.platformRefreshInFlight$ = withRefreshLock(this.api.post<TokenPair>('/auth/refresh', body)).pipe(
        tap((tokens) => this.storePlatformTokens(tokens)),
        finalize(() => {
          this.platformRefreshInFlight$ = null;
        }),
        shareReplay(1),
      );
    }
    return this.platformRefreshInFlight$;
  }

  refreshModuleTokens(moduleCode?: string | null): Observable<TokenPair> {
    const code = moduleCode ?? this.lastModuleCode;
    if (!code) {
      return throwError(() => new Error('Aucune session module'));
    }
    if (!this.moduleRefreshInFlight$ || this.moduleRefreshInFlightCode !== code) {
      this.moduleRefreshInFlightCode = code;
      this.moduleRefreshInFlight$ = withRefreshLock(
        this.api.post<TokenPair>('/auth/modules/refresh', { module_code: code }),
      ).pipe(
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
    if (this.hasPlatformSessionHint) {
      this.api
        .post<{ message: string }>('/auth/logout', {})
        .pipe(catchError(() => of(null)))
        .subscribe();
    }
    this.clearLocalSession();
    const queryParams = options?.reason === 'session' ? { reason: 'session' } : undefined;
    void this.router.navigate(['/login'], queryParams ? { queryParams } : undefined);
  }

  logoutModule(options?: { redirectTo?: string }): void {
    const code = this.lastModuleCode;
    // Capturer la route espace AVANT clear (contexte session).
    const dest = options?.redirectTo ?? this.espaceRouteForModule(code);
    if (code) {
      this.api
        .post<{ message: string }>('/auth/modules/logout', { module_code: code })
        .pipe(catchError(() => of(null)))
        .subscribe();
    }
    this.clearModuleSession();
    // Retour au département — jamais Login 1.
    void this.router.navigateByUrl(dest);
  }

  private espaceRouteForModule(moduleCode: string | null): string {
    return this.plateformeContext.espacePathFor(moduleCode) || resolveEspacePathForModule(moduleCode);
  }

  isAuthenticated(): boolean {
    return !!this.platformAccessToken;
  }

  hasModuleSession(moduleCode: string): boolean {
    return this.moduleCode === moduleCode && !!this.moduleAccessToken;
  }
}
