import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

function isModuleLoginUrl(url: string): boolean {
  return /\/auth\/modules\/[^/]+\/login/.test(url);
}

function isAuthPublicUrl(url: string): boolean {
  return (
    /\/auth\/login(?:\?|$)/.test(url) ||
    url.includes('/auth/refresh') ||
    url.includes('/auth/forgot-password') ||
    url.includes('/auth/reset-password') ||
    url.includes('/auth/modules/refresh')
  );
}

function isPlatformApi(url: string): boolean {
  if (url.includes('/auth/modules/logout') || url.includes('/auth/modules/refresh')) {
    return false;
  }
  if (isModuleLoginUrl(url)) {
    return true;
  }
  return (
    url.includes('/auth/me') ||
    url.includes('/auth/2fa') ||
    url.includes('/auth/logout') ||
    url.includes('/plateforme/')
  );
}

function isModuleLogoutUrl(url: string): boolean {
  return url.includes('/auth/modules/logout');
}

function authErrorCode(err: HttpErrorResponse): string | null {
  const detail = err.error?.detail;
  if (detail && typeof detail === 'object' && typeof detail.code === 'string') {
    return detail.code;
  }
  return null;
}

function attachBearer(req: HttpRequest<unknown>, token: string | null): HttpRequest<unknown> {
  if (!token) {
    return req;
  }
  return req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  let authedReq = req;
  if (!isAuthPublicUrl(req.url)) {
    if (isPlatformApi(req.url)) {
      authedReq = attachBearer(req, auth.platformAccessToken);
    } else if (isModuleLogoutUrl(req.url)) {
      authedReq = attachBearer(req, auth.moduleAccessToken);
    } else {
      authedReq = attachBearer(req, auth.moduleAccessToken ?? auth.platformAccessToken);
    }
  }

  return next(authedReq).pipe(
    catchError((err: unknown) => {
      if (!(err instanceof HttpErrorResponse) || err.status !== 401) {
        return throwError(() => err);
      }
      if (isAuthPublicUrl(req.url)) {
        return throwError(() => err);
      }

      const code = authErrorCode(err);
      if (isModuleLoginUrl(req.url)) {
        const platformLost =
          code === 'PLATFORM_SESSION_EXPIRED' ||
          code === 'TOKEN_INVALID' ||
          code === 'UNAUTHENTICATED';
        if (!platformLost) {
          return throwError(() => err);
        }
      }
      const usedModule =
        !isPlatformApi(req.url) || code === 'MODULE_AUTH_REQUIRED' || code === 'MODULE_SESSION_EXPIRED';

      if (code === 'MODULE_AUTH_REQUIRED' || (usedModule && !auth.moduleRefreshToken)) {
        const moduleCode = auth.moduleCode ?? 'immobilisations';
        auth.clearModuleSession();
        const returnUrl = router.url?.startsWith('/modules/') ? '/dashboard' : router.url;
        void router.navigate(['/modules', moduleCode, 'acces'], {
          queryParams: { returnUrl },
        });
        return throwError(() => err);
      }

      if (usedModule && (code === 'MODULE_SESSION_EXPIRED' || !isPlatformApi(req.url))) {
        if (!auth.moduleRefreshToken) {
          const moduleCode = auth.moduleCode ?? 'immobilisations';
          auth.clearModuleSession();
          void router.navigate(['/modules', moduleCode, 'acces'], {
            queryParams: { returnUrl: router.url },
          });
          return throwError(() => err);
        }
        return auth.refreshModuleTokens().pipe(
          switchMap(() => {
            const nextToken = auth.moduleAccessToken;
            if (!nextToken) {
              const moduleCode = auth.moduleCode ?? 'immobilisations';
              auth.clearModuleSession();
              void router.navigate(['/modules', moduleCode, 'acces'], {
                queryParams: { returnUrl: router.url },
              });
              return throwError(() => err);
            }
            return next(attachBearer(req, nextToken));
          }),
          catchError((refreshErr: unknown) => {
            const refreshCode =
              refreshErr instanceof HttpErrorResponse ? authErrorCode(refreshErr) : null;
            if (refreshCode === 'PLATFORM_SESSION_EXPIRED') {
              auth.logoutPlatform({ reason: 'session' });
            } else {
              const moduleCode = auth.moduleCode ?? 'immobilisations';
              auth.clearModuleSession();
              void router.navigate(['/modules', moduleCode, 'acces'], {
                queryParams: { returnUrl: router.url },
              });
            }
            return throwError(() => err);
          }),
        );
      }

      if (!auth.platformRefreshToken) {
        auth.logoutPlatform({ reason: 'session' });
        return throwError(() => err);
      }

      return auth.refreshPlatformTokens().pipe(
        switchMap(() => {
          const nextToken = auth.platformAccessToken;
          if (!nextToken) {
            auth.logoutPlatform({ reason: 'session' });
            return throwError(() => err);
          }
          return next(attachBearer(req, nextToken));
        }),
        catchError((refreshErr: unknown) => {
          if (isModuleLoginUrl(req.url) && refreshErr instanceof HttpErrorResponse) {
            const retryCode = authErrorCode(refreshErr);
            const stillPlatformLost =
              retryCode === 'PLATFORM_SESSION_EXPIRED' ||
              retryCode === 'TOKEN_INVALID' ||
              retryCode === 'UNAUTHENTICATED';
            if (!stillPlatformLost) {
              return throwError(() => refreshErr);
            }
          }
          auth.logoutPlatform({ reason: 'session' });
          return throwError(() => err);
        }),
      );
    }),
  );
};
