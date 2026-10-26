import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService, CHANGE_PASSWORD_PATH } from '../services/auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }
  // Profil non chargé (rechargement de page) : l'intercepteur redirige sur le 403 backend.
  if (auth.user()?.must_change_password) {
    return router.createUrlTree([CHANGE_PASSWORD_PATH]);
  }
  return true;
};

/** Écran de changement : réservé aux sessions encore soumises à l'obligation. */
export const mustChangePasswordGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }
  const decide = () =>
    auth.user()?.must_change_password ? true : router.createUrlTree(['/accueil']);
  if (auth.user()) {
    return decide();
  }
  return auth.loadProfile().pipe(
    map(() => decide()),
    catchError(() => of(router.createUrlTree(['/login']))),
  );
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
    const acces = router.createUrlTree(['/modules', moduleCode, 'acces'], {
      queryParams: { returnUrl: state.url },
    });
    // Nouvel onglet ou autre module : session reprise via le cookie HttpOnly de ce module.
    return auth.refreshModuleTokens(moduleCode).pipe(
      map(() => true as const),
      catchError(() => of(acces)),
    );
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
