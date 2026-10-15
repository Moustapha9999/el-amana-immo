import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { FeedbackService } from '../core/feedback/feedback.service';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';

interface MotifSortie {
  id: string;
  code: string;
  libelle: string;
  observation_obligatoire: boolean;
  ordre: number;
  is_active: boolean;
}

/** Paramètres → liste configurable des motifs proposés dans le formulaire de sortie ou d'entrée (sens). */
@Component({
  selector: 'bea-stock-motifs-sortie-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule],
  template: `
    <section class="bea-mg__panel" style="margin-top:1rem">
      <div class="bea-mg__panel-top">
        <h2>Motifs {{ libelle() }}</h2>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouveau()">
          <mat-icon>add</mat-icon> Nouveau motif
        </button>
      </div>
      <div class="bea-mg__table-scroll">
        <table class="bea-mg__table">
          <thead>
            <tr>
              <th>Ordre</th>
              <th>Code</th>
              <th>Libellé</th>
              <th>Observation</th>
              <th>Statut</th>
              <th class="bea-mg__th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (m of motifs(); track m.id) {
              <tr [style.opacity]="m.is_active ? 1 : 0.55">
                <td>{{ m.ordre }}</td>
                <td><code class="bea-mg__code">{{ m.code }}</code></td>
                <td>{{ m.libelle }}</td>
                <td>{{ m.observation_obligatoire ? 'Obligatoire' : 'Facultative' }}</td>
                <td>
                  <span class="bea-stock-badge" [attr.data-niveau]="m.is_active ? 'normal' : 'epuise'">
                    {{ m.is_active ? 'Actif' : 'Désactivé' }}
                  </span>
                </td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="modifier(m)">
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button
                    type="button"
                    class="bea-mg__icon-btn"
                    [class.bea-mg__icon-btn--danger]="m.is_active"
                    [title]="m.is_active ? 'Désactiver (les mouvements passés gardent leur motif)' : 'Réactiver'"
                    [disabled]="busy()"
                    (click)="basculer(m)"
                  >
                    <mat-icon>{{ m.is_active ? 'block' : 'restart_alt' }}</mat-icon>
                  </button>
                </td>
              </tr>
            } @empty {
              <tr><td colspan="6" class="bea-mg__empty">Aucun motif configuré.</td></tr>
            }
          </tbody>
        </table>
      </div>
    </section>

    @if (edition(); as mode) {
      <div class="bea-mg__backdrop" (click)="fermer()" role="presentation"></div>
      <div class="bea-mg__modal bea-mg__modal--sm" role="dialog" aria-modal="true" [attr.aria-label]="'Motif ' + libelle()">
        <header class="bea-mg__modal-head">
          <div>
            <p class="bea-stock-page__kicker">{{ mode === 'create' ? 'Création' : 'Modification' }}</p>
            <h2>{{ mode === 'create' ? 'Nouveau motif ' + libelle() : 'Modifier le motif' }}</h2>
          </div>
          <button type="button" class="bea-mg__icon-btn" (click)="fermer()" title="Fermer"><mat-icon>close</mat-icon></button>
        </header>
        <form [formGroup]="form" (ngSubmit)="enregistrer()">
          <div class="bea-mg__modal-body">
            <div class="bea-mg__grid">
              <label>
                Code
                <input formControlName="code" [readonly]="mode === 'edit'" maxlength="40" />
              </label>
              <label>
                Ordre d’affichage
                <input type="number" formControlName="ordre" step="10" />
              </label>
              <label class="bea-mg__span2">
                Libellé
                <input formControlName="libelle" maxlength="160" />
              </label>
              <label class="bea-mg__span2" style="flex-direction:row;align-items:center;gap:0.5rem">
                <input type="checkbox" formControlName="observation_obligatoire" />
                Observation obligatoire avec ce motif
              </label>
            </div>
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || busy()">
              {{ mode === 'create' ? 'Créer' : 'Enregistrer' }}
            </button>
          </footer>
        </form>
      </div>
    }
  `,
})
export class StockMotifsSortiePanelComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly feedback = inject(FeedbackService);

  readonly sens = input<'SORTIE' | 'ENTREE'>('SORTIE');
  readonly libelle = computed(() => (this.sens() === 'ENTREE' ? 'd’entrée' : 'de sortie'));
  readonly motifs = signal<MotifSortie[]>([]);
  readonly edition = signal<'create' | 'edit' | null>(null);
  readonly cible = signal<MotifSortie | null>(null);
  readonly busy = signal(false);

  readonly form = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.maxLength(40)]],
    libelle: ['', [Validators.required, Validators.maxLength(160)]],
    observation_obligatoire: [false],
    ordre: [0],
  });

  readonly hasUnsavedChanges = unsavedChanges(() => !!this.edition() && this.form.dirty && !this.busy(), () => this.form);

  ngOnInit(): void {
    this.charger();
  }

  charger(): void {
    this.api.get<MotifSortie[]>('/mg/stock/motifs-sortie', { inclure_inactifs: true, sens: this.sens() }).subscribe({
      next: (rows) => this.motifs.set(rows),
      error: (err) => describeApiErrorAsync(err).then((i) => this.feedback.apiError(i, `Motifs ${this.libelle()} indisponibles`)),
    });
  }

  nouveau(): void {
    const ordre = Math.max(0, ...this.motifs().map((m) => m.ordre)) + 10;
    this.form.reset({ code: '', libelle: '', observation_obligatoire: false, ordre });
    this.cible.set(null);
    this.edition.set('create');
  }

  modifier(m: MotifSortie): void {
    this.form.reset({ code: m.code, libelle: m.libelle, observation_obligatoire: m.observation_obligatoire, ordre: m.ordre });
    this.cible.set(m);
    this.edition.set('edit');
  }

  fermer(): void {
    this.edition.set(null);
  }

  enregistrer(): void {
    if (this.form.invalid) return;
    const v = this.form.getRawValue();
    const cible = this.cible();
    const action = cible
      ? () =>
          this.api.patch<MotifSortie>(`/mg/stock/motifs-sortie/${cible.id}`, {
            libelle: v.libelle.trim(),
            observation_obligatoire: v.observation_obligatoire,
            ordre: Number(v.ordre) || 0,
          })
      : () =>
          this.api.post<MotifSortie>('/mg/stock/motifs-sortie', {
            sens: this.sens(),
            code: v.code.trim(),
            libelle: v.libelle.trim(),
            observation_obligatoire: v.observation_obligatoire,
            ordre: Number(v.ordre) || 0,
          });
    this.feedback
      .run(action, {
        loading: 'Enregistrement…',
        busy: this.busy,
        idempotent: !cible,
        errorTitle: 'Enregistrement refusé',
        errorHint: 'Vos données saisies ont été conservées.',
        success: (m) => ({ title: cible ? 'Motif modifié' : 'Motif créé', details: [{ label: 'Motif', value: m.libelle }] }),
      })
      .subscribe(() => {
        this.form.markAsPristine();
        this.edition.set(null);
        this.charger();
      });
  }

  basculer(m: MotifSortie): void {
    const actif = !m.is_active;
    this.feedback
      .run(() => this.api.patch<MotifSortie>(`/mg/stock/motifs-sortie/${m.id}`, { is_active: actif }), {
        confirm: actif
          ? undefined
          : {
              action: 'suspension',
              title: 'Désactiver le motif',
              message: `Ne plus proposer « ${m.libelle} » dans les nouvelles ${this.sens() === 'ENTREE' ? 'entrées' : 'sorties'} ?`,
              hint: 'Les mouvements déjà validés conservent ce motif.',
            },
        busy: this.busy,
        errorTitle: 'Modification refusée',
        success: { title: actif ? 'Motif réactivé' : 'Motif désactivé', details: [{ label: 'Motif', value: m.libelle }] },
      })
      .subscribe(() => this.charger());
  }
}
