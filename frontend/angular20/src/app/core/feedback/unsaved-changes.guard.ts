import { DestroyRef, Injectable, inject } from '@angular/core';
import { AbstractControl } from '@angular/forms';
import { CanDeactivateFn, Route, Routes } from '@angular/router';
import { UiDialogService } from '../../shared/ui-dialog/ui-dialog.service';
import { HttpOutcomeTracker } from './http-feedback';

/** Implémenté par tout composant de formulaire routé (via `unsavedChanges(...)`). */
export interface HasUnsavedChanges {
  hasUnsavedChanges(): boolean;
}

/** Vérifications actives, consultées à la fermeture / au rechargement de l'onglet. */
@Injectable({ providedIn: 'root' })
export class UnsavedChangesRegistry {
  private readonly checks = new Set<() => boolean>();

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', (event) => warnBeforeUnload(event, this.anyDirty()));
    }
  }

  add(check: () => boolean): () => void {
    this.checks.add(check);
    return () => this.checks.delete(check);
  }

  private anyDirty(): boolean {
    for (const check of this.checks) {
      try {
        if (check()) return true;
      } catch {
        /* composant détruit */
      }
    }
    return false;
  }
}

/**
 * Déclare l'état « modifications non enregistrées » d'un composant (contexte d'injection) :
 * `readonly hasUnsavedChanges = unsavedChanges(() => this.form.dirty && !this.saving(), () => this.form);`
 * Couvre la navigation interne (garde global) et la fermeture d'onglet. Si `form` est fourni,
 * il repasse « pristine » dès qu'une écriture est confirmée par le backend (enregistrer et rester).
 */
export function unsavedChanges(check: () => boolean, form?: () => AbstractControl | null | undefined): () => boolean {
  const remove = inject(UnsavedChangesRegistry).add(check);
  const destroyRef = inject(DestroyRef);
  destroyRef.onDestroy(remove);
  if (form) {
    const sub = inject(HttpOutcomeTracker).mutationSuccess$.subscribe(() => form()?.markAsPristine());
    destroyRef.onDestroy(() => sub.unsubscribe());
  }
  return check;
}

export const unsavedChangesGuard: CanDeactivateFn<unknown> = (component) => {
  const c = component as Partial<HasUnsavedChanges> | null;
  if (typeof c?.hasUnsavedChanges !== 'function' || !c.hasUnsavedChanges()) return true;
  // Navigation déclenchée juste après un enregistrement confirmé par le backend.
  if (inject(HttpOutcomeTracker).mutationJustSucceeded()) return true;
  return inject(UiDialogService).confirmAction(
    'depart',
    'Vous avez des modifications qui n’ont pas été enregistrées.',
    undefined,
    'Si vous quittez maintenant, ces modifications seront perdues.',
  );
};

/** Branche le garde sur toutes les routes à composant (sans effet si le composant ne l'implémente pas). */
export function withUnsavedChangesGuard(routes: Routes): Routes {
  return routes.map((route): Route => {
    const next: Route = { ...route };
    if ((route.component || route.loadComponent) && !route.canDeactivate?.includes(unsavedChangesGuard)) {
      next.canDeactivate = [...(route.canDeactivate ?? []), unsavedChangesGuard];
    }
    if (route.children) next.children = withUnsavedChangesGuard(route.children);
    return next;
  });
}

export function warnBeforeUnload(event: BeforeUnloadEvent, dirty: boolean): void {
  if (!dirty) return;
  event.preventDefault();
  event.returnValue = '';
}
