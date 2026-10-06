import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { debounceTime } from 'rxjs';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { ACTION_LABELS, FX_BASE, FxJournal, FxJournalItem, dateFr, dateHeureFr, nettoyer, telechargerBlob } from './facturation.models';
import { FacturationStore } from './facturation.store';
import { FactureDrawerComponent } from './facture-drawer.component';

const TAILLE = 50;

const ICONES: Record<string, string> = {
  CREATION: 'post_add',
  MODIFICATION: 'edit_note',
  PAIEMENT: 'payments',
  PAIEMENT_ANNULE: 'money_off',
  DOCUMENT: 'attach_file',
  DUPLICATION: 'content_copy',
  SUPPRESSION: 'delete',
};

/** Journal de toutes les opérations du module (factures et points), tracées par utilisateur. */
@Component({
  selector: 'bea-fx-historique',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, FactureDrawerComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux · Facturation fournisseurs</p>
          <h1>Historique</h1>
          <p class="bea-ct-head__sub">Toutes les opérations sur les factures et les points de facturation : saisie, pièces, validation, paiements. Journal non modifiable.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap().export || store.cap().reports) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy() || !journal()?.total" (click)="exporter()"><mat-icon>download</mat-icon> CSV</button>
          }
        </div>
      </header>

      <form class="bea-mg__search bea-ct-filters bea-fx-filters" [formGroup]="filtres">
        <label class="bea-mg__field bea-fx-grow">Rechercher <input type="search" formControlName="q" placeholder="Référence, point, utilisateur, message…" /></label>
        <label class="bea-mg__field">Objet
          <select formControlName="entite">
            <option value="">Tous</option>
            <option value="facture">Factures</option>
            <option value="point_facturation">Points de facturation</option>
          </select>
        </label>
        <label class="bea-mg__field">Du <input type="date" formControlName="date_from" /></label>
        <label class="bea-mg__field">Au <input type="date" formControlName="date_to" /></label>
      </form>

      <div class="bea-mg__panel bea-ct-panel">
        @if (journal() === null) {
          @for (i of [1, 2, 3, 4, 5, 6]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
        } @else {
          <div class="bea-fx-journal-head">
            <p class="bea-fx-sub">{{ journal()!.total }} opération(s)</p>
            <label class="bea-fx-journal-size">Afficher
              <select [value]="taille()" (change)="changerTaille(+$any($event.target).value)">
                @for (t of tailles; track t) { <option [value]="t">{{ t }}</option> }
              </select>
              par page
            </label>
          </div>
          <div class="bea-fx-journal-wrap">
          <ol class="bea-fx-journal">
            @for (g of groupes(); track g.jour) {
              <li class="bea-fx-journal__day"><span>{{ g.jour }}</span></li>
              @for (e of g.items; track e.id; let i = $index) {
                <li class="bea-fx-journal__item bea-fx-row-in" [style.--i]="i" [attr.data-entite]="e.entite">
                  <span class="bea-fx-journal__dot"><mat-icon>{{ icone(e) }}</mat-icon></span>
                  <div class="bea-fx-journal__body">
                    <p>
                      <strong>{{ e.action_label }}</strong>
                      @if (e.entite === 'facture') {
                        <button type="button" class="bea-ct-link" (click)="factureId.set(e.entity_id)">{{ e.reference }}</button>
                      } @else {
                        <a class="bea-ct-link" [routerLink]="base + '/points'" [queryParams]="{ point: e.entity_id }"><mat-icon class="bea-fx-ico">place</mat-icon> {{ e.reference }}</a>
                      }
                    </p>
                    @if (e.message) { <small>{{ e.message }}</small> }
                  </div>
                  <span class="bea-fx-journal__meta"><strong>{{ heure(e.created_at) }}</strong><small>{{ e.user_nom || 'Système' }}</small></span>
                </li>
              }
            } @empty {
              <li><div class="bea-ct-empty"><mat-icon>history</mat-icon><p>Aucune opération pour ces critères.</p></div></li>
            }
          </ol>
          </div>
          @if (journal()!.total > 0) {
            <nav class="bea-fx-pager bea-fx-journal-pager" aria-label="Pagination">
              <span class="bea-fx-sub">{{ debut() }}–{{ fin() }} sur {{ journal()!.total }}</span>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="aller(1)" title="Première page"><mat-icon>first_page</mat-icon></button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="aller(page() - 1)" title="Page précédente"><mat-icon>chevron_left</mat-icon></button>
              <span>Page {{ page() }} / {{ pages() }}</span>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= pages()" (click)="aller(page() + 1)" title="Page suivante"><mat-icon>chevron_right</mat-icon></button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= pages()" (click)="aller(pages())" title="Dernière page"><mat-icon>last_page</mat-icon></button>
            </nav>
          }
        }
      </div>
    </section>

    @if (factureId(); as id) {
      <bea-fx-facture-drawer [factureId]="id" (closed)="factureId.set(null)" (changed)="charger()" />
    }
  `,
})
export class FacturationHistoriqueComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly base = FX_BASE;
  readonly journal = signal<FxJournal | null>(null);
  readonly page = signal(1);
  readonly busy = signal(false);
  readonly factureId = signal<string | null>(null);
  private readonly drawer = viewChild(FactureDrawerComponent);
  readonly hasUnsavedChanges = () => !!this.drawer()?.dirty();

  readonly filtres = this.fb.nonNullable.group({ q: [''], entite: [''], date_from: [''], date_to: [''] });

  readonly tailles = [25, 50, 100, 200];
  readonly taille = signal(TAILLE);
  readonly pages = computed(() => Math.max(1, Math.ceil((this.journal()?.total ?? 0) / this.taille())));
  readonly debut = computed(() => (this.page() - 1) * this.taille() + 1);
  readonly fin = computed(() => Math.min(this.page() * this.taille(), this.journal()?.total ?? 0));

  readonly groupes = computed(() => {
    const out: { jour: string; items: FxJournalItem[] }[] = [];
    for (const e of this.journal()?.items ?? []) {
      const jour = dateFr(e.created_at.slice(0, 10));
      const dernier = out[out.length - 1];
      if (dernier?.jour === jour) dernier.items.push(e);
      else out.push({ jour, items: [e] });
    }
    return out;
  });

  ngOnInit(): void {
    this.store.charger();
    this.filtres.valueChanges.pipe(debounceTime(300), takeUntilDestroyed(this.destroyRef)).subscribe(() => this.aller(1));
    this.charger();
  }

  private params(page: number, size: number): Record<string, string> {
    return nettoyer({ ...this.filtres.getRawValue(), page, size });
  }

  aller(page: number): void {
    this.page.set(page);
    this.charger();
  }

  changerTaille(taille: number): void {
    this.taille.set(taille);
    this.aller(1);
  }

  charger(): void {
    this.api.get<FxJournal>('/mg/factures/historique', this.params(this.page(), this.taille())).subscribe({
      next: (j) => this.journal.set(j),
      error: (e) => {
        this.journal.set({ items: [], total: 0, page: 1, size: this.taille() });
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Historique indisponible'));
      },
    });
  }

  exporter(): void {
    this.feedback
      .run(() => this.api.get<FxJournal>('/mg/factures/historique', this.params(1, 200)), {
        loading: 'Préparation de l’export…',
        busy: this.busy,
        errorTitle: 'Export impossible',
        success: (j) => {
          const esc = (v: string | null) => `"${(v ?? '').replaceAll('"', '""')}"`;
          const lignes = [
            ['Date', 'Utilisateur', 'Objet', 'Référence', 'Action', 'Détail'].join(';'),
            ...j.items.map((e) =>
              [dateHeureFr(e.created_at), e.user_nom ?? 'Système', e.entite === 'facture' ? 'Facture' : 'Point', e.reference, e.action_label, e.message]
                .map((v) => esc(v ?? ''))
                .join(';'),
            ),
          ];
          telechargerBlob(new Blob(['\ufeff' + lignes.join('\r\n')], { type: 'text/csv;charset=utf-8' }), 'factures-historique.csv');
          return {
            title: 'Historique exporté',
            message: j.total > j.items.length ? `${j.items.length} opérations les plus récentes sur ${j.total} (affinez les filtres pour le reste).` : `${j.items.length} opération(s).`,
          };
        },
      })
      .subscribe();
  }

  icone(e: FxJournalItem): string {
    return ACTION_LABELS[e.action.toLowerCase()]?.icon ?? ICONES[e.action] ?? (e.entite === 'facture' ? 'receipt_long' : 'place');
  }

  heure(iso: string): string {
    return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  }
}
