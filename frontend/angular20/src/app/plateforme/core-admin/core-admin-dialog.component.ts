import { ChangeDetectionStrategy, Component, HostListener, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationStart, Router } from '@angular/router';
import { BeaAdminDialogService, BeaAdminDialogState } from './core-admin-dialog.service';

@Component({
  selector: 'bea-core-admin-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (dialog.state(); as d) {
      <div
        class="bea-admin-dlg"
        role="presentation"
        (click)="onBackdrop(d)"
      >
        <div
          class="bea-admin-dlg__card"
          role="dialog"
          aria-modal="true"
          aria-labelledby="bea-admin-dlg-title"
          [attr.data-tone]="d.tone"
          (click)="$event.stopPropagation()"
        >
          <div class="bea-admin-dlg__accent"></div>
          <form novalidate (submit)="onSubmit($event, d)">
          <div class="bea-admin-dlg__icon" aria-hidden="true">
            @switch (d.tone) {
              @case ('danger') {
                <svg viewBox="0 0 24 24" fill="none">
                  <path
                    d="M12 8.2v5.1M12 16.7h.01"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                  />
                  <path
                    d="M10.3 4.9 3.4 17.1c-.8 1.3.2 3 1.7 3h13.8c1.5 0 2.5-1.7 1.7-3L13.7 4.9c-.7-1.3-2.7-1.3-3.4 0Z"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linejoin="round"
                  />
                </svg>
              }
              @case ('success') {
                <svg viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="8.2" stroke="currentColor" stroke-width="1.6" />
                  <path
                    d="m8.4 12.2 2.4 2.5 4.8-5.2"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              }
              @case ('warn') {
                <svg viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="8.2" stroke="currentColor" stroke-width="1.6" />
                  <path d="M12 8.1v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
                  <circle cx="12" cy="16.1" r="0.9" fill="currentColor" />
                </svg>
              }
              @default {
                <svg viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="8.2" stroke="currentColor" stroke-width="1.6" />
                  <path d="M12 11.2V16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
                  <circle cx="12" cy="8.4" r="0.9" fill="currentColor" />
                </svg>
              }
            }
          </div>
          <h2 id="bea-admin-dlg-title" class="bea-admin-dlg__title">{{ d.title }}</h2>
          <p class="bea-admin-dlg__message">{{ d.message }}</p>
          @if (d.fields?.length) {
            <div class="bea-admin-dlg__fields">
              @for (field of d.fields; track field.key) {
                <label class="bea-admin-field">
                  <span>{{ field.label }}</span>
                  <input
                    [type]="field.type || 'text'"
                    [attr.autocomplete]="field.autocomplete || null"
                    [value]="fieldValues()[field.key] || ''"
                    (input)="setField(field.key, $event)"
                  />
                </label>
              }
            </div>
          }
          @if (fieldError()) {
            <p class="bea-admin-dlg__error">{{ fieldError() }}</p>
          }
          <div class="bea-admin-dlg__actions" [class.bea-admin-dlg__actions--single]="d.kind === 'feedback'">
            @if (d.kind === 'confirm') {
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="dismiss()">
                {{ d.cancelLabel || 'Annuler' }}
              </button>
              <button
                type="submit"
                class="bea-admin-btn"
                [class.bea-admin-btn--danger]="d.tone === 'danger'"
              >
                {{ d.confirmLabel || 'Confirmer' }}
              </button>
            } @else {
              <button type="submit" class="bea-admin-btn" [class.bea-admin-btn--danger]="d.tone === 'danger'">
                {{ d.okLabel || 'OK' }}
              </button>
            }
          </div>
          </form>
        </div>
      </div>
    }
  `,
})
export class CoreAdminDialogComponent {
  readonly dialog = inject(BeaAdminDialogService);
  readonly fieldValues = signal<Record<string, string>>({});
  readonly fieldError = signal<string | null>(null);

  constructor() {
    const router = inject(Router);
    router.events.pipe(takeUntilDestroyed()).subscribe((event) => {
      if (event instanceof NavigationStart && this.dialog.state()?.kind === 'confirm') {
        this.dialog.dismiss();
      }
    });
    effect(() => {
      const open = !!this.dialog.state();
      document.body.style.overflow = open ? 'hidden' : '';
    });
    effect(() => {
      const current = this.dialog.state();
      untracked(() => {
        this.fieldError.set(null);
        const values: Record<string, string> = {};
        for (const field of current?.fields ?? []) {
          values[field.key] = '';
        }
        this.fieldValues.set(values);
      });
    }, { allowSignalWrites: true });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.dialog.state()) {
      this.dismiss();
    }
  }

  onSubmit(event: Event, state: BeaAdminDialogState): void {
    event.preventDefault();
    event.stopPropagation();
    if (state.kind === 'confirm') {
      this.confirm(state);
      return;
    }
    this.dismiss();
  }

  setField(key: string, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.fieldValues.update((current) => ({ ...current, [key]: value }));
    this.fieldError.set(null);
  }

  onBackdrop(state: BeaAdminDialogState): void {
    if (state.kind === 'feedback') {
      this.dismiss();
    }
  }

  confirm(state: BeaAdminDialogState): void {
    if (state.fields?.length) {
      const values = this.fieldValues();
      const error = state.validate?.(values) ?? null;
      if (error) {
        this.fieldError.set(error);
        return;
      }
      this.dialog.close(values);
      return;
    }
    this.dialog.close(true);
  }

  dismiss(): void {
    this.dialog.dismiss();
  }
}
