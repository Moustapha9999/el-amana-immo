import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  Injectable,
  OnInit,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Observable } from 'rxjs';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';

export interface StockMouvementRow {
  id: string;
  reference: string;
  date_mouvement: string;
  type_mouvement: string;
  article_id: string;
  quantite: number;
  agence_id: string | null;
  departement?: string | null;
  motif: string | null;
  observation: string | null;
  source_type?: string | null;
  article_code?: string | null;
  article_designation?: string | null;
  periode_libelle?: string | null;
  periode_debut?: string | null;
  periode_fin?: string | null;
  periode_cloturee?: boolean;
  quantite_modifiable?: boolean;
}

export interface StockAgenceOption {
  id: string;
  libelle: string;
}

const TYPE_LABELS: Record<string, string> = {
  ENTREE: 'entrée',
  SORTIE: 'sortie',
  AJUSTEMENT: 'ajustement',
  INVENTAIRE: 'inventaire',
};

/** Suppression d'un mouvement (confirmation + retour transversal). */
@Injectable({ providedIn: 'root' })
export class StockMouvementActions {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly auth = inject(AuthService);

  readonly canForce = this.auth.canForceStockDelete;

  peutSupprimer(m: StockMouvementRow): boolean {
    return !!m.quantite_modifiable || (this.canForce() && m.type_mouvement !== 'INVENTAIRE');
  }

  /** Suppression administrateur : motif obligatoire, auditée, recalcul des soldes y compris périodes clôturées. */
  supprimerForce(opts: {
    path: string;
    reference: string;
    message: string;
    hint: string;
    successTitle: string;
  }): Observable<unknown> {
    return this.feedback.runWithReason(
      (motif) => this.api.delete(`${opts.path}?force=true&motif=${encodeURIComponent(motif)}`),
      {
        reason: {
          title: 'Suppression administrateur',
          message: opts.message,
          hint: opts.hint,
          confirmLabel: 'Supprimer définitivement',
          cancelLabel: 'Annuler',
          tone: 'danger',
          icon: 'delete_forever',
          reasonLabel: 'Motif (tracé dans l’audit)',
          reasonPlaceholder: 'Ex. : données de test à nettoyer',
          required: true,
          maxLength: 500,
        },
        loading: 'Suppression…',
        errorTitle: 'Suppression refusée',
        success: { title: opts.successTitle, details: [{ label: 'Référence', value: opts.reference }] },
      },
    );
  }

  supprimer(m: StockMouvementRow): Observable<unknown> {
    if (!m.quantite_modifiable && this.canForce()) {
      return this.supprimerForce({
        path: `/mg/stock/mouvements/${m.id}`,
        reference: m.reference,
        message: `Supprimer le mouvement ${m.reference} (${TYPE_LABELS[m.type_mouvement] ?? m.type_mouvement} de ${m.quantite}) ?`,
        hint: 'Le stock de l’article et les soldes des périodes (y compris clôturées) seront recalculés.',
        successTitle: 'Mouvement supprimé',
      });
    }
    return this.feedback.run(() => this.api.delete(`/mg/stock/mouvements/${m.id}`), {
      confirm: {
        action: 'suppression',
        message: `Supprimer le mouvement ${m.reference} (${TYPE_LABELS[m.type_mouvement] ?? m.type_mouvement} de ${m.quantite}) ?`,
        hint: 'Le stock de l’article et les soldes de la période seront recalculés.',
      },
      loading: 'Suppression…',
      errorTitle: 'Suppression refusée',
      success: { title: 'Mouvement supprimé', details: [{ label: 'Référence', value: m.reference }] },
    });
  }
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

@Component({
  selector: 'bea-stock-mouvement-edit',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, DatePipe],
  template: `
    <div class="bea-mg__backdrop" (click)="fermer()" role="presentation"></div>
    <div class="bea-mg__modal" role="dialog" aria-modal="true" aria-label="Modifier le mouvement">
      <header class="bea-mg__modal-head">
        <div>
          <p class="bea-stock-page__kicker">Modification</p>
          <h2>{{ mouvement().reference }}</h2>
        </div>
        <button type="button" class="bea-mg__icon-btn" (click)="fermer()" title="Fermer">
          <mat-icon>close</mat-icon>
        </button>
      </header>
      <form [formGroup]="form" (ngSubmit)="enregistrer()">
        <div class="bea-mg__modal-body">
          @if (mouvement().periode_libelle) {
            <p class="bea-stock-edit__info">
              <mat-icon>event_note</mat-icon>
              <span>
                Période <strong>{{ mouvement().periode_libelle }}</strong>
                {{ mouvement().periode_cloturee ? '(clôturée)' : '(ouverte)' }} — la date doit rester entre le
                {{ mouvement().periode_debut | date: 'dd/MM/yyyy' }} et le {{ mouvement().periode_fin | date: 'dd/MM/yyyy' }}.
                @if (!mouvement().quantite_modifiable) {
                  <br />Quantité verrouillée : {{ raisonVerrou() }}
                }
              </span>
            </p>
          }
          <div class="bea-mg__grid">
            <label class="bea-mg__span2">
              Article
              <input [value]="(mouvement().article_code || '') + (mouvement().article_designation ? ' — ' + mouvement().article_designation : '')" readonly />
            </label>
            <label>
              Date
              <input
                type="datetime-local"
                formControlName="date_mouvement"
                [attr.min]="mouvement().periode_debut ? mouvement().periode_debut + 'T00:00' : null"
                [attr.max]="mouvement().periode_fin ? mouvement().periode_fin + 'T23:59' : null"
              />
            </label>
            <label>
              Quantité
              <input type="number" formControlName="quantite" min="1" step="1" />
            </label>
            <label>
              Agence
              <select formControlName="agence_id">
                <option value="">—</option>
                @for (a of agences(); track a.id) {
                  <option [value]="a.id">{{ a.libelle }}</option>
                }
              </select>
            </label>
            <label>
              Département
              <input formControlName="departement" />
            </label>
            <label class="bea-mg__span2">
              Motif
              <input formControlName="motif" />
            </label>
            <label class="bea-mg__span2">
              Observation
              <input formControlName="observation" />
            </label>
          </div>
        </div>
        <footer class="bea-mg__modal-foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || form.pristine || saving()">
            {{ saving() ? 'Enregistrement…' : 'Enregistrer' }}
          </button>
        </footer>
      </form>
    </div>
  `,
})
export class StockMouvementEditComponent implements OnInit {
  readonly mouvement = input.required<StockMouvementRow>();
  readonly agences = input<StockAgenceOption[]>([]);
  readonly saved = output<StockMouvementRow>();
  readonly closed = output<void>();

  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);

  readonly saving = signal(false);
  readonly form = this.fb.nonNullable.group({
    date_mouvement: ['', Validators.required],
    quantite: [1, [Validators.required, Validators.min(1)]],
    agence_id: [''],
    departement: [''],
    motif: [''],
    observation: [''],
  });
  readonly hasUnsavedChanges = unsavedChanges(() => this.form.dirty && !this.saving(), () => this.form);

  ngOnInit(): void {
    const m = this.mouvement();
    this.form.reset({
      date_mouvement: toLocalInput(m.date_mouvement),
      quantite: Number(m.quantite),
      agence_id: m.agence_id ?? '',
      departement: m.departement ?? '',
      motif: m.motif ?? '',
      observation: m.observation ?? '',
    });
    if (!m.quantite_modifiable) this.form.controls.quantite.disable();
  }

  @HostListener('document:keydown.escape')
  fermer(): void {
    if (this.saving()) return;
    if (this.form.dirty) {
      this.feedback
        .confirm({ action: 'depart', message: 'Abandonner les modifications de ce mouvement ?' })
        .subscribe((ok) => ok && this.closed.emit());
      return;
    }
    this.closed.emit();
  }

  raisonVerrou(): string {
    const m = this.mouvement();
    if (m.source_type && m.source_type !== 'usb_import' && m.source_type !== 'manuel') {
      return 'mouvement généré par un workflow (demande, inventaire, réception).';
    }
    if (m.type_mouvement !== 'ENTREE' && m.type_mouvement !== 'SORTIE') {
      return 'seules les entrées et sorties sont modifiables en quantité.';
    }
    if (m.periode_cloturee) return 'période clôturée.';
    return '';
  }

  enregistrer(): void {
    if (this.form.invalid) return;
    const m = this.mouvement();
    const c = this.form.controls;
    const body: Record<string, unknown> = {};
    if (c.date_mouvement.dirty) body['date_mouvement'] = `${c.date_mouvement.value}:00Z`;
    if (c.quantite.enabled && c.quantite.dirty) body['quantite'] = c.quantite.value;
    if (c.agence_id.dirty) body['agence_id'] = c.agence_id.value || null;
    if (c.departement.dirty) body['departement'] = c.departement.value;
    if (c.motif.dirty) body['motif'] = c.motif.value;
    if (c.observation.dirty) body['observation'] = c.observation.value;
    this.feedback
      .run(() => this.api.patch<StockMouvementRow>(`/mg/stock/mouvements/${m.id}`, body), {
        loading: 'Enregistrement…',
        busy: this.saving,
        errorTitle: 'Modification refusée',
        errorHint: 'Vos saisies ont été conservées.',
        success: (res) => ({ title: 'Mouvement modifié', details: [{ label: 'Référence', value: res.reference }] }),
      })
      .subscribe((res) => {
        this.form.markAsPristine();
        this.saved.emit(res);
      });
  }
}
