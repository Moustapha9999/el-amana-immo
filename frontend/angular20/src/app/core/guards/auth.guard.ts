import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isAuthenticated()) {
    return true;
  }
  return router.createUrlTree(['/login']);
};

export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isAuthenticated()) {
    return true;
  }
  return router.createUrlTree(['/accueil']);
};

export function moduleGuard(moduleCode: string): CanActivateFn {
  return (route, state) => {
    const auth = inject(AuthService);
    const router = inject(Router);
    if (!auth.isAuthenticated()) {
      return router.createUrlTree(['/login']);
    }
    if (auth.hasModuleSession(moduleCode)) {
      return true;
    }
    return router.createUrlTree(['/modules', moduleCode, 'acces'], {
      queryParams: { returnUrl: state.url },
    });
  };
}

export const coreAdminGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }
  const allowed = () =>
    auth.canAccessCoreAdmin() ? true : router.createUrlTree(['/accueil']);
  if (auth.user()) {
    return allowed();
  }
  return auth.loadProfile().pipe(
    map(() => allowed()),
    catchError(() => of(router.createUrlTree(['/login']))),
  );
};
