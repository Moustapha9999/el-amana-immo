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
import { QuantitePipe } from '../shared/montant.pipe';

interface ArticleOption {
  id: string;
  code: string;
  designation: string;
  stock_actuel: number;
}

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

const TYPE_VIEW: Record<string, { label: string; icon: string; qte: string }> = {
  ENTREE: { label: 'Entrée', icon: 'south_west', qte: 'Quantité entrée' },
  SORTIE: { label: 'Sortie', icon: 'north_east', qte: 'Quantité sortie' },
  AJUSTEMENT: { label: 'Ajustement', icon: 'tune', qte: 'Correction' },
  INVENTAIRE: { label: 'Inventaire', icon: 'fact_check', qte: 'Stock compté' },
};

export function raisonVerrouMouvement(m: StockMouvementRow): string {
  if (m.source_type && m.source_type !== 'usb_import' && m.source_type !== 'manuel') {
    return 'mouvement généré par un workflow (demande, inventaire, réception) : modifiez l’opération d’origine.';
  }
  if (m.type_mouvement === 'INVENTAIRE') return 'un mouvement d’inventaire fixe le stock ; saisissez un ajustement.';
  if (m.periode_cloturee) return 'période clôturée ; rouvrez-la depuis les paramètres.';
  return '';
}

/** Fiche de consultation d'un mouvement (Entrées, Sorties, Journal). */
@Component({
  selector: 'bea-stock-mouvement-view',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, DatePipe, QuantitePipe],
  template: `
    <div class="bea-mg__backdrop" (click)="closed.emit()" role="presentation"></div>
    <div class="bea-mg__modal bea-stock-view bea-mvt-view" role="dialog" aria-modal="true" aria-label="Détail du mouvement">
      <header class="bea-mg__modal-head">
        <div class="bea-stock-view__head">
          <span class="bea-stock-view__avatar bea-mvt-view__avatar" [attr.data-type]="m().type_mouvement">
            <mat-icon>{{ vue().icon }}</mat-icon>
          </span>
          <div>
            <p class="bea-stock-page__kicker">Consultation · {{ vue().label }}</p>
            <h2>{{ m().reference }}</h2>
          </div>
        </div>
        <button type="button" class="bea-mg__icon-btn" (click)="closed.emit()" title="Fermer">
          <mat-icon>close</mat-icon>
        </button>
      </header>
      <div class="bea-mg__modal-body bea-stock-view__body">
        <div class="bea-mvt-view__hero" [attr.data-type]="m().type_mouvement">
          <div>
            <span>{{ vue().qte }}</span>
            <strong>{{ signe() }}{{ absQte() | quantite }}</strong>
          </div>
          <div class="bea-mvt-view__hero-side">
            <span>Stock actuel de l’article</span>
            <strong>{{ m().stock_disponible != null ? (m().stock_disponible | quantite) : '—' }}</strong>
          </div>
        </div>

        <dl class="bea-stock-view__infos bea-stock-view__infos--2">
          <div class="bea-stock-view__wide">
            <dt><mat-icon>inventory_2</mat-icon> Article</dt>
            <dd>
              <code>{{ m().article_code || '—' }}</code>
              @if (m().article_designation) {
                — {{ m().article_designation }}
              }
            </dd>
          </div>
          <div>
            <dt><mat-icon>event</mat-icon> Date</dt>
            <dd>{{ m().date_mouvement | date: 'dd/MM/yyyy HH:mm' }}</dd>
          </div>
          <div>
            <dt><mat-icon>person</mat-icon> Initiateur</dt>
            <dd>{{ m().initiateur_nom || '—' }}</dd>
          </div>
          <div>
            <dt><mat-icon>apartment</mat-icon> Agence</dt>
            <dd>{{ agence() || '—' }}</dd>
          </div>
          <div>
            <dt><mat-icon>groups</mat-icon> Département</dt>
            <dd>{{ m().departement || '—' }}</dd>
          </div>
          <div class="bea-stock-view__wide">
            <dt><mat-icon>notes</mat-icon> Motif</dt>
            <dd>{{ m().motif || '—' }}</dd>
          </div>
          @if (m().observation) {
            <div class="bea-stock-view__wide">
              <dt><mat-icon>chat_bubble_outline</mat-icon> Observation</dt>
              <dd>{{ m().observation }}</dd>
            </div>
          }
          @if (m().periode_libelle) {
            <div class="bea-stock-view__wide">
              <dt><mat-icon>date_range</mat-icon> Période</dt>
              <dd>
                {{ m().periode_libelle }}
                <span class="bea-mvt-view__periode" [attr.data-cloturee]="m().periode_cloturee ? '1' : '0'">
                  {{ m().periode_cloturee ? 'Clôturée' : 'Ouverte' }}
                </span>
              </dd>
            </div>
          }
        </dl>

        @if (!m().quantite_modifiable && verrou()) {
          <p class="bea-mvt-view__note">
            <mat-icon>lock</mat-icon>
            <span>Article et quantité verrouillés : {{ verrou() }} Date, agence, motif et observation restent modifiables.</span>
          </p>
        }
      </div>
      <footer class="bea-mg__modal-foot bea-stock-view__foot">
        @if (peutSupprimer()) {
          <button type="button" class="bea-mg__btn bea-mg__btn--danger bea-mvt-view__del" (click)="supprimer.emit()">
            <mat-icon>delete</mat-icon> Supprimer
          </button>
        }
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closed.emit()">Fermer</button>
        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="modifier.emit()">
          <mat-icon>edit</mat-icon> Modifier
        </button>
      </footer>
    </div>
  `,
})
export class StockMouvementViewComponent {
  readonly m = input.required<StockMouvementRow & { initiateur_nom?: string | null; stock_disponible?: number | null }>({
    alias: 'mouvement',
  });
  readonly agence = input<string | null>(null);
  readonly peutSupprimer = input(false);
  readonly closed = output<void>();
  readonly modifier = output<void>();
  readonly supprimer = output<void>();

  vue() {
    return TYPE_VIEW[this.m().type_mouvement] ?? { label: this.m().type_mouvement, icon: 'swap_vert', qte: 'Quantité' };
  }

  signe(): string {
    const t = this.m().type_mouvement;
    const q = Number(this.m().quantite) || 0;
    if (t === 'ENTREE') return '+';
    if (t === 'SORTIE') return '−';
    if (t === 'AJUSTEMENT') return q > 0 ? '+' : q < 0 ? '−' : '';
    return '';
  }

  absQte(): number {
    return Math.abs(Number(this.m().quantite) || 0);
  }

  verrou(): string {
    return raisonVerrouMouvement(this.m());
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
  imports: [ReactiveFormsModule, MatIconModule, DatePipe, QuantitePipe],
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
                  <br />Article et quantité verrouillés : {{ raisonVerrou() }}
                } @else {
                  <br />Changer l’article ou la quantité recalcule le stock et les soldes de la période.
                }
              </span>
            </p>
          }
          <div class="bea-mg__grid">
            <label class="bea-mg__span2">
              Article
              @if (mouvement().quantite_modifiable) {
                <select formControlName="article_id">
                  @if (!articles().length) {
                    <option [value]="mouvement().article_id">{{ mouvement().article_code }} — {{ mouvement().article_designation }}</option>
                  }
                  @for (a of articles(); track a.id) {
                    <option [value]="a.id">{{ a.code }} — {{ a.designation }} (stock {{ a.stock_actuel | quantite }})</option>
                  }
                </select>
              } @else {
                <input [value]="(mouvement().article_code || '') + (mouvement().article_designation ? ' — ' + mouvement().article_designation : '')" readonly />
              }
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
              {{ ajustement() ? 'Correction (+ ajoute, − retire)' : 'Quantité' }}
              <input type="number" formControlName="quantite" [attr.min]="ajustement() ? null : 0.001" step="0.001" />
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
  readonly articles = signal<ArticleOption[]>([]);
  readonly form = this.fb.nonNullable.group({
    date_mouvement: ['', Validators.required],
    article_id: ['', Validators.required],
    quantite: [1, [Validators.required]],
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
      article_id: m.article_id,
      quantite: Number(m.quantite),
      agence_id: m.agence_id ?? '',
      departement: m.departement ?? '',
      motif: m.motif ?? '',
      observation: m.observation ?? '',
    });
    const q = this.form.controls.quantite;
    q.addValidators(
      this.ajustement()
        ? (c) => (Number(c.value) === 0 ? { nul: true } : null)
        : Validators.min(0.001),
    );
    q.updateValueAndValidity({ emitEvent: false });
    if (!m.quantite_modifiable) {
      q.disable();
      this.form.controls.article_id.disable();
      return;
    }
    this.api
      .get<{ items: ArticleOption[] }>('/mg/stock/articles', { page: 1, size: 500 })
      .subscribe({ next: (res) => this.articles.set(res.items) });
  }

  ajustement(): boolean {
    return this.mouvement().type_mouvement === 'AJUSTEMENT';
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
    return raisonVerrouMouvement(this.mouvement());
  }

  enregistrer(): void {
    if (this.form.invalid) return;
    const m = this.mouvement();
    const c = this.form.controls;
    const body: Record<string, unknown> = {};
    if (c.date_mouvement.dirty) body['date_mouvement'] = `${c.date_mouvement.value}:00Z`;
    if (c.article_id.enabled && c.article_id.value !== m.article_id) body['article_id'] = c.article_id.value;
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
