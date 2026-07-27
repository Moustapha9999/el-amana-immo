import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

function isAuthPublicUrl(url: string): boolean {
  return (
    url.includes('/auth/login') ||
    url.includes('/auth/refresh') ||
    url.includes('/auth/logout') ||
    url.includes('/auth/forgot-password') ||
    url.includes('/auth/reset-password')
  );
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.accessToken;
  const authedReq = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authedReq).pipe(
    catchError((err: unknown) => {
      if (!(err instanceof HttpErrorResponse) || err.status !== 401) {
        return throwError(() => err);
      }
      if (isAuthPublicUrl(req.url)) {
        return throwError(() => err);
      }
      if (!auth.refreshToken) {
        auth.logout({ reason: 'session' });
        return throwError(() => err);
      }

      return auth.refreshTokens().pipe(
        switchMap(() => {
          const nextToken = auth.accessToken;
          if (!nextToken) {
            auth.logout({ reason: 'session' });
            return throwError(() => err);
          }
          return next(req.clone({ setHeaders: { Authorization: `Bearer ${nextToken}` } }));
        }),
        catchError(() => {
          auth.logout({ reason: 'session' });
          return throwError(() => err);
        }),
      );
    }),
  );
};
