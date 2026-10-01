import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { MontantPipe } from '../shared/montant.pipe';
import { PaginationComponent } from '../shared/pagination.component';
import { PaiementApercuComponent } from './paiement-apercu.component';
import { PaiementFormComponent } from './paiement-form.component';
import {
  MODES_PAIEMENT,
  NotePaiement,
  canDeletePaiement,
  canEditPaiement,
  canPayNotes,
  paiementLockHint,
  paiementReference,
  paiementStatutLabel,
  paiementStatutTone,
  statutPaiementLabel,
  statutPaiementTone,
} from './notes-frais.shared';

interface PaiementList {
  items: NotePaiement[];
  total: number;
  page: number;
  size: number;
  montant_total: number;
}

type SortKey = 'numero' | 'date_paiement' | 'registre' | 'beneficiaire' | 'montant' | 'mode_paiement' | 'statut' | 'created_at';

@Component({
  selector: 'bea-notes-paiements',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatIconModule,
    DatePipe,
    MontantPipe,
    PaginationComponent,
    PaiementFormComponent,
    PaiementApercuComponent,
  ],
  template: `
    <section class="bea-mg bea-nf">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Règlements</p>
          <h1>Paiements</h1>
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/notes-frais/notes">
            <mat-icon>list_alt</mat-icon> Registre
          </a>
          @if (canPay()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openForm()">
              <mat-icon>add</mat-icon> Nouveau paiement
            </button>
          }
        </div>
      </header>

      <form class="bea-mg__search bea-pay-filters" [formGroup]="filters" (ngSubmit)="applyFilters()">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input formControlName="q" placeholder="N° paiement, référence, registre, bénéficiaire…" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>receipt_long</mat-icon>
          <input formControlName="registre" placeholder="Registre (NF-…)" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>person</mat-icon>
          <input formControlName="beneficiaire" placeholder="Bénéficiaire" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>account_balance_wallet</mat-icon>
          <select formControlName="mode_paiement" (change)="applyFilters()">
            <option value="">Tous les modes</option>
            @for (m of modes; track m) { <option [value]="m">{{ m }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>flag</mat-icon>
          <select formControlName="statut" (change)="applyFilters()">
            <option value="">Tous les statuts</option>
            <option value="VALIDE">Validés</option>
            <option value="ANNULE">Annulés</option>
          </select>
        </label>
        <label class="bea-mg__field" title="Du">
          <mat-icon>event</mat-icon>
          <input type="date" formControlName="date_debut" (change)="applyFilters()" />
        </label>
        <label class="bea-mg__field" title="Au">
          <mat-icon>event_available</mat-icon>
          <input type="date" formControlName="date_fin" (change)="applyFilters()" />
        </label>
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Filtrer</button>
        @if (hasFilters()) {
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="resetFilters()">
            <mat-icon>filter_alt_off</mat-icon> Réinitialiser
          </button>
        }
      </form>

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Paiements enregistrés</h2>
          <span class="bea-mg__count">
            {{ total() }} paiement{{ total() > 1 ? 's' : '' }} · {{ montantTotal() | montant }} MRU validés
          </span>
        </div>
        <div class="bea-mg__table-scroll bea-nf__registre-scroll">
          <table class="bea-mg__table bea-nf-table bea-pay-table">
            <thead>
              <tr>
                @for (c of columns; track c.key) {
                  <th
                    [class.is-num]="c.key === 'montant'"
                    [class.is-sortable]="!!c.sort"
                    [attr.aria-sort]="c.sort && sort() === c.sort ? (order() === 'asc' ? 'ascending' : 'descending') : null"
                    (click)="c.sort && toggleSort(c.sort)"
                  >
                    {{ c.label }}
                    @if (c.sort && sort() === c.sort) {
                      <mat-icon class="bea-pay-sort">{{ order() === 'asc' ? 'arrow_upward' : 'arrow_downward' }}</mat-icon>
                    }
                  </th>
                }
                <th class="bea-mg__th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (p of items(); track p.id; let i = $index) {
                <tr
                  class="bea-nf-row"
                  [class.is-cancelled]="p.statut === 'ANNULE'"
                  [style.animation-delay.ms]="i < 20 ? i * 30 : 0"
                  (dblclick)="apercuId.set(p.id)"
                >
                  <td class="is-nowrap"><code class="bea-mg__code">{{ p.numero }}</code></td>
                  <td class="is-nowrap">{{ p.date_paiement | date: 'dd/MM/yyyy' }}</td>
                  <td>
                    <a class="bea-pay-link" [routerLink]="['/notes-frais/notes', p.note_id]">{{ p.registre.reference }}</a>
                    <small class="bea-nf-cell__sub">
                      <span class="bea-nf-badge" [attr.data-tone]="regTone(p.registre.statut_paiement)">{{ regLabel(p.registre.statut_paiement) }}</span>
                    </small>
                  </td>
                  <td>
                    <strong class="bea-nf-cell__main">{{ p.registre.beneficiaire || '—' }}</strong>
                    @if (p.registre.departement) { <small class="bea-nf-cell__sub">{{ p.registre.departement }}</small> }
                  </td>
                  <td><span class="bea-nf-cell__sub bea-pay-motif">{{ p.registre.motif || p.registre.intitule || '—' }}</span></td>
                  <td class="is-num is-nowrap"><strong>{{ p.montant | montant }}</strong></td>
                  <td class="is-nowrap">{{ p.mode_paiement }}</td>
                  <td><span class="bea-pay-ref">{{ reference(p) }}</span></td>
                  <td class="is-nowrap"><span class="bea-nf-badge" [attr.data-tone]="payTone(p.statut)">{{ payLabel(p.statut) }}</span></td>
                  <td>
                    <span class="bea-nf-cell__main bea-pay-user">{{ p.created_by_nom || '—' }}</span>
                    <small class="bea-nf-cell__sub">{{ p.created_at | date: 'dd/MM/yyyy HH:mm' }}</small>
                  </td>
                  <td class="bea-mg__actions-cell">
                    <button type="button" class="bea-mg__icon-btn" title="Voir le détail" (click)="apercuId.set(p.id)">
                      <mat-icon>visibility</mat-icon>
                    </button>
                    <button
                      type="button"
                      class="bea-mg__icon-btn"
                      [disabled]="!canEdit(p)"
                      [title]="canEdit(p) ? 'Modifier' : lockHint(p) || 'Permission paiement requise'"
                      (click)="openEdit(p)"
                    >
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button
                      type="button"
                      class="bea-mg__icon-btn bea-mg__icon-btn--warn"
                      [disabled]="!canEdit(p)"
                      [title]="canEdit(p) ? 'Annuler le paiement' : lockHint(p) || 'Permission paiement requise'"
                      (click)="cancel(p)"
                    >
                      <mat-icon>block</mat-icon>
                    </button>
                    <button
                      type="button"
                      class="bea-mg__icon-btn bea-mg__icon-btn--danger"
                      [disabled]="!canDelete(p)"
                      [title]="canDelete(p) ? 'Supprimer' : 'Suppression réservée à l’administrateur'"
                      (click)="remove(p)"
                    >
                      <mat-icon>delete</mat-icon>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td [attr.colspan]="columns.length + 1">
                    <div class="bea-mg__empty">
                      <mat-icon>payments</mat-icon>
                      <p>{{ hasFilters() ? 'Aucun paiement ne correspond aux filtres.' : 'Aucun paiement enregistré.' }}</p>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        @if (total() > 0) {
          <app-pagination
            [page]="page()"
            [total]="total()"
            [pageSize]="pageSize"
            label="paiement(s)"
            (pageChange)="goToPage($event)"
          />
        }
      </div>

      @if (formOpen()) {
        <bea-paiement-form
          [noteId]="formNoteId()"
          [paiementId]="formPaiementId()"
          (closed)="closeForm()"
          (saved)="onSaved($event)"
        />
      }
      @if (apercuId(); as id) {
        <bea-paiement-apercu
          [paiementId]="id"
          (closed)="apercuId.set(null)"
          (changed)="load()"
          (edit)="openEdit($event)"
        />
      }
    </section>
  `,
})
export class NotesPaiementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly modes = MODES_PAIEMENT;
  readonly pageSize = 20;
  readonly items = signal<NotePaiement[]>([]);
  readonly total = signal(0);
  readonly montantTotal = signal(0);
  readonly page = signal(1);
  readonly sort = signal<SortKey>('date_paiement');
  readonly order = signal<'asc' | 'desc'>('desc');
  readonly apercuId = signal<string | null>(null);
  readonly formOpen = signal(false);
  readonly formNoteId = signal<string | null>(null);
  readonly formPaiementId = signal<string | null>(null);
  readonly canPay = computed(() => canPayNotes(this.auth.user()));

  readonly columns: { key: string; label: string; sort?: SortKey }[] = [
    { key: 'numero', label: 'N° paiement', sort: 'numero' },
    { key: 'date', label: 'Date', sort: 'date_paiement' },
    { key: 'registre', label: 'Registre', sort: 'registre' },
    { key: 'beneficiaire', label: 'Bénéficiaire', sort: 'beneficiaire' },
    { key: 'motif', label: 'Motif' },
    { key: 'montant', label: 'Montant', sort: 'montant' },
    { key: 'mode', label: 'Mode', sort: 'mode_paiement' },
    { key: 'reference', label: 'Référence' },
    { key: 'statut', label: 'Statut', sort: 'statut' },
    { key: 'user', label: 'Saisi par', sort: 'created_at' },
  ];

  readonly filters = this.fb.nonNullable.group({
    q: '',
    registre: '',
    beneficiaire: '',
    mode_paiement: '',
    statut: '',
    date_debut: '',
    date_fin: '',
  });

  readonly reference = paiementReference;
  readonly payLabel = paiementStatutLabel;
  readonly payTone = paiementStatutTone;
  readonly regLabel = statutPaiementLabel;
  readonly regTone = statutPaiementTone;
  readonly lockHint = paiementLockHint;

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    const note = qp.get('note');
    const voir = qp.get('voir');
    const registre = qp.get('registre');
    if (registre) this.filters.patchValue({ registre });
    if (note && this.canPay()) this.openForm(note);
    if (voir) this.apercuId.set(voir);
    if (note || voir) {
      void this.router.navigate([], { relativeTo: this.route, queryParams: {}, replaceUrl: true });
    }
    this.load();
  }

  hasFilters(): boolean {
    return Object.values(this.filters.getRawValue()).some((v) => !!v);
  }

  canEdit(p: NotePaiement): boolean {
    return canEditPaiement(this.auth.user(), p);
  }

  canDelete(p: NotePaiement): boolean {
    return canDeletePaiement(this.auth.user(), p);
  }

  load(): void {
    const v = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.pageSize,
      sort: this.sort(),
      order: this.order(),
    };
    for (const [k, val] of Object.entries(v)) {
      if (val && String(val).trim()) params[k] = String(val).trim();
    }
    this.api.get<PaiementList>('/mg/notes-frais/paiements', params).subscribe({
      next: (r) => {
        this.items.set(r.items);
        this.total.set(r.total);
        this.montantTotal.set(Number(r.montant_total) || 0);
      },
      error: () => {
        this.items.set([]);
        this.total.set(0);
        this.montantTotal.set(0);
        this.feedback.error({ title: 'Chargement des paiements impossible' });
      },
    });
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  resetFilters(): void {
    this.filters.reset();
    this.applyFilters();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.load();
  }

  toggleSort(key: SortKey): void {
    if (this.sort() === key) {
      this.order.update((o) => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      this.sort.set(key);
      this.order.set(key === 'date_paiement' || key === 'created_at' || key === 'montant' ? 'desc' : 'asc');
    }
    this.page.set(1);
    this.load();
  }

  openForm(noteId: string | null = null): void {
    this.formNoteId.set(noteId);
    this.formPaiementId.set(null);
    this.formOpen.set(true);
  }

  openEdit(p: NotePaiement): void {
    this.apercuId.set(null);
    this.formNoteId.set(null);
    this.formPaiementId.set(p.id);
    this.formOpen.set(true);
  }

  closeForm(): void {
    this.formOpen.set(false);
    this.formNoteId.set(null);
    this.formPaiementId.set(null);
  }

  onSaved(p: NotePaiement): void {
    this.closeForm();
    this.load();
    this.apercuId.set(p.id);
  }

  cancel(p: NotePaiement): void {
    this.feedback
      .runWithReason(
        (motif) => this.api.post<NotePaiement>(`/mg/notes-frais/paiements/${p.id}/annuler`, { motif }),
        {
          reason: {
            title: 'Annuler le paiement',
            message: `Le paiement ${p.numero} (${p.montant} ${p.registre.devise}) sera annulé et le solde de ${p.registre.reference} recalculé.`,
            confirmLabel: 'Annuler le paiement',
            cancelLabel: 'Retour',
            tone: 'danger',
            icon: 'block',
            reasonLabel: 'Motif de l’annulation',
          },
          loading: 'Annulation…',
          errorTitle: 'Annulation refusée',
          success: { title: 'Paiement annulé', details: [{ label: 'N° paiement', value: p.numero }] },
        },
      )
      .subscribe(() => this.load());
  }

  remove(p: NotePaiement): void {
    this.feedback
      .run(() => this.api.delete<{ ok: boolean }>(`/mg/notes-frais/paiements/${p.id}`), {
        confirm: {
          action: 'suppression',
          message: `Supprimer le paiement ${p.numero} ? Le solde de ${p.registre.reference} sera recalculé.`,
          hint: 'La suppression est tracée dans l’audit. Préférez l’annulation en exploitation.',
        },
        loading: 'Suppression…',
        errorTitle: 'Suppression refusée',
        success: { title: 'Paiement supprimé', details: [{ label: 'N° paiement', value: p.numero }] },
      })
      .subscribe(() => {
        if (this.items().length <= 1 && this.page() > 1) this.page.update((n) => n - 1);
        this.load();
      });
  }
}
