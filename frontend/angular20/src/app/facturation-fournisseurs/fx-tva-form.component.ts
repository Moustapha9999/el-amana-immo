import { ChangeDetectionStrategy, Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { parseMontant } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { FxProfil, FxTva, dateFr } from './facturation.models';

/** Ajout / modification d'un taux de TVA daté d'un profil fournisseur. */
@Component({
  selector: 'bea-fx-tva-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule],
  template: `
    <div class="bea-mg__backdrop" (click)="fermer()"></div>
    <form class="bea-mg__modal bea-ct-modal bea-fx-form" role="dialog" aria-modal="true" aria-labelledby="bea-fx-tva-title"
      [formGroup]="form" (ngSubmit)="enregistrer()">
      <header class="bea-ct-modal__head">
        <h2 id="bea-fx-tva-title"><mat-icon>percent</mat-icon> {{ tva() ? 'Modifier le taux' : 'Nouveau taux de TVA' }}</h2>
        <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
      </header>
      <div class="bea-ct-modal__body bea-fx-form__body">
        <p class="bea-fx-tva-form__profil"><strong>{{ profil().libelle }}</strong> <span>{{ profil().fournisseur }}</span></p>
        <div class="bea-ct-grid">
          <label>Taux (%) *
            <input inputmode="decimal" formControlName="taux" placeholder="Ex. 16" />
            @if (tauxInvalide()) { <small class="bea-fx-form__err">Taux entre 0 et 100 %.</small> }
          </label>
          <span></span>
          <label>En vigueur à partir du
            <input type="date" formControlName="date_debut" />
            <small class="bea-fx-form__hint">Vide = depuis toujours.</small>
          </label>
          <label>Jusqu’au (inclus)
            <input type="date" formControlName="date_fin" />
            <small class="bea-fx-form__hint">Vide = sans date de fin.</small>
            @if (periodeInvalide()) { <small class="bea-fx-form__err">La fin précède le début.</small> }
          </label>
          <label class="bea-ct-span2">Observation / référence
            <textarea formControlName="observation" rows="2" maxlength="2000" placeholder="Ex. Loi de finances 2026, courrier fournisseur…"></textarea>
          </label>
        </div>
        <p class="bea-ct-help"><mat-icon>info</mat-icon> Le taux s’applique aux factures selon leur date de facture : proposition de TVA à la saisie et contrôle « TVA incohérente ». Deux périodes d’un même profil ne peuvent pas se chevaucher : pour un changement de taux, clôturez l’ancien (date de fin) puis ajoutez le nouveau.</p>
      </div>
      <footer class="bea-ct-modal__foot">
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="invalide() || busy()">
          <mat-icon>save</mat-icon> {{ busy() ? 'Enregistrement…' : tva() ? 'Enregistrer' : 'Ajouter le taux' }}
        </button>
      </footer>
    </form>
  `,
})
export class FxTvaFormComponent implements OnInit {
  readonly profil = input.required<FxProfil>();
  readonly tva = input<FxTva | null>(null);
  readonly saved = output<FxProfil>();
  readonly closed = output<void>();

  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly busy = signal(false);
  readonly form = this.fb.nonNullable.group({ taux: [''], date_debut: [''], date_fin: [''], observation: [''] });
  readonly dirty = unsavedChanges(() => this.form.dirty && !this.busy(), () => this.form);

  ngOnInit(): void {
    const t = this.tva();
    if (t) {
      this.form.reset({
        taux: String(t.taux), date_debut: t.date_debut ?? '', date_fin: t.date_fin ?? '', observation: t.observation ?? '',
      });
    }
  }

  private taux(): number | null {
    const t = parseMontant(this.form.controls.taux.value);
    return t === null || t < 0 || t > 100 ? null : t;
  }

  tauxInvalide(): boolean {
    return !!this.form.controls.taux.value.trim() && this.taux() === null;
  }

  periodeInvalide(): boolean {
    const { date_debut, date_fin } = this.form.getRawValue();
    return !!date_debut && !!date_fin && date_fin < date_debut;
  }

  invalide(): boolean {
    return this.taux() === null || this.periodeInvalide();
  }

  fermer(): void {
    if (this.busy()) return;
    if (!this.form.dirty) {
      this.closed.emit();
      return;
    }
    this.dialog
      .confirmAction('depart', 'Fermer sans enregistrer ?', undefined, 'Le taux saisi sera perdu.')
      .subscribe((ok) => {
        if (ok) {
          this.form.markAsPristine();
          this.closed.emit();
        }
      });
  }

  enregistrer(): void {
    if (this.invalide() || this.busy()) return;
    const v = this.form.getRawValue();
    const body = {
      taux: this.taux(),
      date_debut: v.date_debut || null,
      date_fin: v.date_fin || null,
      observation: v.observation.trim() || null,
    };
    const t = this.tva();
    const periode = `${body.date_debut ? dateFr(body.date_debut) : 'origine'} → ${body.date_fin ? dateFr(body.date_fin) : 'sans fin'}`;
    this.feedback
      .run(
        () =>
          t
            ? this.api.patch<FxProfil>(`/mg/factures/tva/${t.id}`, body)
            : this.api.post<FxProfil>('/mg/factures/tva', { ...body, profil_id: this.profil().id }),
        {
          loading: 'Enregistrement du taux…',
          busy: this.busy,
          errorTitle: 'Taux refusé',
          success: (r) => ({
            title: t ? 'Taux modifié' : 'Taux ajouté',
            message: `${r.libelle} : ${body.taux} % (${periode})`,
            details: [{ label: 'TVA en vigueur aujourd’hui', value: r.taux_tva === null ? 'Non configurée' : `${r.taux_tva} %` }],
          }),
        },
      )
      .subscribe((r) => {
        this.form.markAsPristine();
        this.saved.emit(r);
      });
  }
}
