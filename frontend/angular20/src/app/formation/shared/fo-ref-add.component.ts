import { ChangeDetectionStrategy, Component, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { DOMAINES, Domaine, FO_BASE, RefItem } from '../formation.models';
import { FormationStore } from '../formation.store';

/** Ajout rapide d'une valeur de référentiel depuis un formulaire. */
@Component({
  selector: 'bea-fo-ref-add',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  template: `
    <div class="bea-mg__backdrop bea-fx-over" (click)="fermer.emit()"></div>
    <div class="bea-mg__modal bea-mg__modal--sm bea-ct-modal bea-fx-over" role="dialog" aria-modal="true">
      <header class="bea-ct-modal__head">
        <h2><mat-icon>add_circle</mat-icon> Nouveau {{ libelle().toLowerCase() }}</h2>
        <button type="button" class="bea-ct-view__close" (click)="fermer.emit()" aria-label="Fermer"><mat-icon>close</mat-icon></button>
      </header>
      <form class="bea-ct-modal__body bea-fo-form" (ngSubmit)="valider()">
        <label>{{ libelle() }} <em>*</em>
          <input name="libelle" [(ngModel)]="valeur" maxlength="200" required autofocus [class.is-invalid]="erreur()" />
        </label>
        @if (erreur()) { <span class="bea-fo-err">{{ erreur() }}</span> }
        <p class="bea-fo-hint">La valeur est ajoutée au référentiel et devient sélectionnable partout dans le module.</p>
        <footer class="bea-ct-modal__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer.emit()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !valeur.trim()">
            <mat-icon>check</mat-icon> Ajouter
          </button>
        </footer>
      </form>
    </div>
  `,
})
export class FoRefAddComponent {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly store = inject(FormationStore);

  readonly domaine = input.required<Domaine>();
  readonly cree = output<RefItem>();
  readonly fermer = output<void>();

  readonly busy = signal(false);
  readonly erreur = signal('');
  valeur = '';

  readonly libelle = computed(() => DOMAINES.find((d) => d.code === this.domaine())?.label ?? 'Valeur');

  valider(): void {
    const libelle = this.valeur.trim();
    if (!libelle) return;
    this.erreur.set('');
    this.feedback
      .run(() => this.api.post<RefItem>(`${FO_BASE}/referentiels`, { domaine: this.domaine(), libelle }), {
        busy: this.busy,
        loading: 'Ajout…',
        success: (r) => ({ title: `${this.libelle()} ajouté`, message: r.libelle }),
        errorTitle: "Échec de l'ajout",
        idempotent: true,
        onError: (e) => this.erreur.set(e.message),
      })
      .subscribe((r) => {
        this.store.recharger$().subscribe();
        this.cree.emit(r);
      });
  }
}
