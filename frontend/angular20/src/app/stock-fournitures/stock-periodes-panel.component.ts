import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { QuantitePipe } from '../shared/montant.pipe';
import { aPermission } from './inventaire/inventaire.model';

type StatutPeriode = 'OUVERTE' | 'ROUVERTE' | 'CLOTUREE';

interface PeriodeStock {
  id: string;
  libelle: string;
  statut: StatutPeriode;
  statut_libelle?: string;
  date_debut: string;
  date_fin: string;
  premiere_cloture_at?: string | null;
  premiere_cloture_par?: string | null;
  cloture_at?: string | null;
  cloture_par?: string | null;
  reopen_at?: string | null;
  reopen_par?: string | null;
  reopen_motif?: string | null;
  nb_reouvertures?: number;
}

interface PeriodeActive extends PeriodeStock {
  cloture_message?: string | null;
  periodes_non_cloturees?: { id: string; libelle: string; statut: StatutPeriode }[];
}

interface SoldePeriode {
  article_code: string | null;
  article_designation: string | null;
  stock_initial: number;
  entrees: number;
  sorties: number;
  ajustements: number;
  stock_theorique: number;
  stock_physique: number | null;
  ecart: number | null;
  stock_final: number | null;
}

interface PeriodeSuivante {
  id: string;
  libelle: string;
  statut: StatutPeriode;
  mouvements: number;
  articles_impactes?: number;
  variation_stock_initial?: number;
}

interface ReouverturePreview {
  periode: PeriodeStock;
  peut_rouvrir: boolean;
  blocages: string[];
  consequences: string[];
  articles: number;
  stock_final: number;
  inventaires_ajustes: number;
  periodes_suivantes: PeriodeSuivante[];
}

interface Controle {
  code: string;
  libelle: string;
  ok: boolean;
  bloquant: boolean;
  detail: string | null;
}

interface Correction {
  id: string;
  reference: string;
  type_mouvement: string;
  article_code: string;
  quantite: number;
  date_mouvement: string;
  date_enregistrement: string;
  saisi_par: string | null;
}

interface ArticleModifie {
  article_code: string;
  article_designation: string | null;
  stock_final_avant: number | null;
  stock_final_apres: number;
  variation: number;
}

interface CloturePreview {
  periode: PeriodeStock;
  articles: number;
  stock_final: number;
  articles_avec_ecarts: number;
  ajustements: number;
  periode_suivante: string;
  controles: Controle[];
  avertissements: string[];
  anomalies: string[];
  bloquant: boolean;
  regularisation: {
    motif: string | null;
    reouverte_le: string | null;
    reouverte_par: string | null;
    cloture_precedente_at: string | null;
    corrections: Correction[];
    articles_modifies: ArticleModifie[];
    periodes_suivantes: PeriodeSuivante[];
  } | null;
}

interface EvenementPeriode {
  id: string;
  action: string;
  resultat: 'SUCCES' | 'ECHEC';
  statut_avant: string | null;
  statut_apres: string | null;
  motif: string | null;
  user_nom: string | null;
  created_at: string;
  details: { erreur?: string; corrections?: number; reports_corriges?: number } | null;
}

const ACTIONS: Record<string, string> = {
  CLOTURE: 'Clôture',
  RECLOTURE: 'Nouvelle clôture',
  REOUVERTURE: 'Réouverture',
  CLOTURE_OFFICE: 'Clôture d’office (ancienne règle)',
  REOUVERTURE_OFFICE: 'Réouverture automatique (ancienne règle)',
  REOUVERTURE_REFUSEE: 'Réouverture refusée',
  CLOTURE_REFUSEE: 'Clôture refusée',
};

const PERM = {
  cloture: 'mg.stock.period.close',
  reouverture: 'mg.stock.period.reopen',
  historique: 'mg.stock.period.view',
};

/** Paramètres → périodes de stock : clôture, réouverture pour régularisation, historique. */
@Component({
  selector: 'bea-stock-periodes-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, MatIconModule, RouterLink, DatePipe, QuantitePipe],
  template: `
    <section class="bea-mg__panel" style="margin-bottom:1rem">
      <div class="bea-mg__panel-top">
        <h2>Périodes de stock</h2>
        <span class="bea-mg__count">{{ periodes().length }} période(s)</span>
      </div>
      @if (active(); as pa) {
        <div class="bea-stock-period-banner" [attr.data-statut]="pa.statut">
          <div class="bea-stock-period-banner__copy">
            <span class="bea-stock-period-banner__label">Période de saisie courante</span>
            <strong>{{ pa.libelle }}</strong>
          </div>
          <span class="bea-stock-badge" [attr.data-niveau]="niveau(pa.statut)">{{ libelle(pa) }}</span>
        </div>
        @if (pa.cloture_message) {
          <a class="bea-stock-period-alert" routerLink="/stock-fournitures/inventaires">
            <mat-icon>event_busy</mat-icon>
            <span>{{ pa.cloture_message }}</span>
          </a>
        }
      }
      <div class="bea-mg__table-scroll">
        <table class="bea-mg__table">
          <thead>
            <tr>
              <th>Période</th>
              <th>Statut</th>
              <th>Clôture initiale</th>
              <th>Dernière clôture</th>
              <th>Dernière réouverture</th>
              <th class="bea-mg__th-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (p of periodes(); track p.id) {
              <tr>
                <td>
                  <strong>{{ p.libelle }}</strong>
                  <div class="bea-periode__sub">{{ p.date_debut | date: 'dd/MM/yyyy' }} → {{ p.date_fin | date: 'dd/MM/yyyy' }}</div>
                </td>
                <td>
                  <span class="bea-stock-badge" [attr.data-niveau]="niveau(p.statut)">{{ libelle(p) }}</span>
                </td>
                <td>
                  @if (p.premiere_cloture_at) {
                    {{ p.premiere_cloture_at | date: 'dd/MM/yyyy HH:mm' }}
                    <div class="bea-periode__sub">{{ p.premiere_cloture_par || '—' }}</div>
                  } @else {
                    —
                  }
                </td>
                <td>
                  @if (p.cloture_at) {
                    {{ p.cloture_at | date: 'dd/MM/yyyy HH:mm' }}
                    <div class="bea-periode__sub">{{ p.cloture_par || '—' }}</div>
                  } @else {
                    —
                  }
                </td>
                <td>
                  @if (p.reopen_at) {
                    {{ p.reopen_at | date: 'dd/MM/yyyy HH:mm' }}
                    <div class="bea-periode__sub">
                      {{ p.reopen_par || '—' }} · {{ p.nb_reouvertures || 0 }} réouverture(s)
                    </div>
                    @if (p.reopen_motif) {
                      <div class="bea-periode__sub" [title]="p.reopen_motif">« {{ p.reopen_motif }} »</div>
                    }
                  } @else {
                    —
                  }
                </td>
                <td class="bea-mg__actions-cell">
                  <button type="button" class="bea-mg__icon-btn" title="Voir les soldes" (click)="voirSoldes(p)">
                    <mat-icon>visibility</mat-icon>
                  </button>
                  @if (peutVoirHistorique()) {
                    <button type="button" class="bea-mg__icon-btn" title="Historique des clôtures" (click)="voirHistorique(p)">
                      <mat-icon>history</mat-icon>
                    </button>
                  }
                  @if (p.statut !== 'CLOTUREE' && peutCloturer()) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="ouvrirCloture(p)">
                      {{ p.statut === 'ROUVERTE' ? 'Clôturer de nouveau' : 'Clôturer' }}
                    </button>
                  }
                  @if (p.statut === 'CLOTUREE' && peutRouvrir()) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="ouvrirReouverture(p)">
                      Rouvrir
                    </button>
                  }
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="6" class="bea-mg__empty">Aucune période (créée au premier accès).</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>

    @if (reouverture(); as r) {
      <div class="bea-mg__backdrop" (click)="fermerReouverture()" role="presentation"></div>
      <div class="bea-mg__modal" role="dialog" aria-modal="true" aria-label="Réouverture de période">
        <header class="bea-mg__modal-head">
          <div>
            <p class="bea-stock-page__kicker">Régularisation · administrateur du stock</p>
            <h2>Rouvrir {{ r.periode.libelle }}</h2>
          </div>
          <button type="button" class="bea-mg__icon-btn" (click)="fermerReouverture()" title="Fermer"><mat-icon>close</mat-icon></button>
        </header>
        <form [formGroup]="motifForm" (ngSubmit)="confirmerReouverture()">
          <div class="bea-mg__modal-body">
            <p class="bea-periode__sub" style="margin:0 0 0.75rem">
              Clôturée le {{ r.periode.cloture_at | date: 'dd/MM/yyyy HH:mm' }} par {{ r.periode.cloture_par || '—' }}
              · {{ r.articles }} article(s) · stock final {{ r.stock_final | quantite }}
            </p>
            @for (b of r.blocages; track b) {
              <p class="bea-stock-page__error">{{ b }}</p>
            }
            <h3 class="bea-periode__h3">Conséquences</h3>
            <ul class="bea-periode__list">
              @for (c of r.consequences; track c) {
                <li>{{ c }}</li>
              }
            </ul>
            @if (r.periodes_suivantes.length) {
              <h3 class="bea-periode__h3">Périodes suivantes impactées</h3>
              <ul class="bea-periode__list">
                @for (s of r.periodes_suivantes; track s.id) {
                  <li>{{ s.libelle }} ({{ statutLibelle(s.statut) }}) — {{ s.mouvements }} mouvement(s), stock initial recalculé</li>
                }
              </ul>
            }
            <label class="bea-mg__span2" style="margin-top:0.75rem">
              Motif de la réouverture (obligatoire, tracé dans l’historique)
              <textarea formControlName="motif" rows="3" maxlength="500"
                        placeholder="Ex. : facture fournisseur du 12 reçue après la clôture"></textarea>
            </label>
          </div>
          <footer class="bea-mg__modal-foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerReouverture()">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary"
                    [disabled]="!r.peut_rouvrir || motifForm.invalid || busy()">
              Rouvrir la période
            </button>
          </footer>
        </form>
      </div>
    }

    @if (cloture(); as c) {
      <div class="bea-mg__backdrop" (click)="cloture.set(null)" role="presentation"></div>
      <div class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" aria-label="Clôture de période">
        <header class="bea-mg__modal-head">
          <div>
            <p class="bea-stock-page__kicker">{{ c.regularisation ? 'Nouvelle clôture après régularisation' : 'Clôture mensuelle' }}</p>
            <h2>{{ c.periode.libelle }}</h2>
          </div>
          <button type="button" class="bea-mg__icon-btn" (click)="cloture.set(null)" title="Fermer"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-mg__modal-body">
          <p class="bea-periode__sub" style="margin:0 0 0.75rem">
            {{ c.articles }} article(s) · stock final {{ c.stock_final | quantite }} · {{ c.articles_avec_ecarts }} écart(s)
            d’inventaire · période suivante : {{ c.periode_suivante }}
          </p>
          @if (c.regularisation; as reg) {
            <p class="bea-periode__sub" style="margin:0 0 0.75rem">
              Rouverte le {{ reg.reouverte_le | date: 'dd/MM/yyyy HH:mm' }} par {{ reg.reouverte_par || '—' }} — « {{ reg.motif }} »
            </p>
          }
          <h3 class="bea-periode__h3">Contrôles</h3>
          <ul class="bea-periode__checks">
            @for (k of c.controles; track k.code) {
              <li [attr.data-etat]="k.ok ? 'ok' : k.bloquant ? 'ko' : 'warn'">
                <mat-icon>{{ k.ok ? 'check_circle' : k.bloquant ? 'cancel' : 'warning' }}</mat-icon>
                <span><strong>{{ k.libelle }}</strong>@if (k.detail) { — {{ k.detail }} }</span>
              </li>
            }
          </ul>
          @for (a of c.avertissements; track a) {
            <p class="bea-stock-period-alert" style="margin:0.5rem 0"><mat-icon>info</mat-icon><span>{{ a }}</span></p>
          }
          @if (c.regularisation; as reg) {
            <h3 class="bea-periode__h3">Corrections saisies ({{ reg.corrections.length }})</h3>
            <div class="bea-mg__table-scroll" style="max-height:14rem">
              <table class="bea-mg__table">
                <thead>
                  <tr><th>Référence</th><th>Type</th><th>Article</th><th>Quantité</th><th>Date du mouvement</th><th>Enregistré le</th><th>Par</th></tr>
                </thead>
                <tbody>
                  @for (m of reg.corrections; track m.id) {
                    <tr>
                      <td><code class="bea-mg__code">{{ m.reference }}</code></td>
                      <td>{{ m.type_mouvement }}</td>
                      <td>{{ m.article_code }}</td>
                      <td>{{ m.quantite | quantite }}</td>
                      <td>{{ m.date_mouvement | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>{{ m.date_enregistrement | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>{{ m.saisi_par || '—' }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="7" class="bea-mg__empty">Aucune correction saisie depuis la réouverture.</td></tr>
                  }
                </tbody>
              </table>
            </div>
            @if (reg.articles_modifies.length) {
              <h3 class="bea-periode__h3">Articles modifiés</h3>
              <ul class="bea-periode__list">
                @for (a of reg.articles_modifies; track a.article_code) {
                  <li>
                    {{ a.article_code }} — stock final {{ a.stock_final_avant | quantite }} → {{ a.stock_final_apres | quantite }}
                  </li>
                }
              </ul>
            }
            @if (reg.periodes_suivantes.length) {
              <h3 class="bea-periode__h3">Périodes suivantes recalculées</h3>
              <ul class="bea-periode__list">
                @for (s of reg.periodes_suivantes; track s.id) {
                  <li>
                    {{ s.libelle }} ({{ statutLibelle(s.statut) }}) — stock initial {{ (s.variation_stock_initial ?? 0) >= 0 ? '+' : '' }}{{ s.variation_stock_initial | quantite }}
                    sur {{ s.articles_impactes }} article(s)
                  </li>
                }
              </ul>
            }
          }
          @if (c.bloquant) {
            <p class="bea-stock-page__error">Clôture impossible : {{ c.anomalies.join(' ; ') }}</p>
          }
        </div>
        <footer class="bea-mg__modal-foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="cloture.set(null)">Annuler</button>
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || c.bloquant" (click)="confirmerCloture(c)">
            {{ c.regularisation ? 'Confirmer la nouvelle clôture' : 'Confirmer la clôture' }}
          </button>
        </footer>
      </div>
    }

    @if (historique(); as h) {
      <div class="bea-mg__backdrop" (click)="historique.set(null)" role="presentation"></div>
      <div class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" aria-label="Historique de période">
        <header class="bea-mg__modal-head">
          <div>
            <p class="bea-stock-page__kicker">Historique des clôtures et réouvertures</p>
            <h2>{{ h.periode.libelle }}</h2>
          </div>
          <button type="button" class="bea-mg__icon-btn" (click)="historique.set(null)" title="Fermer"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-mg__modal-body">
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table">
              <thead>
                <tr><th>Date</th><th>Action</th><th>Résultat</th><th>Par</th><th>Motif / détail</th></tr>
              </thead>
              <tbody>
                @for (e of h.evenements; track e.id) {
                  <tr>
                    <td>{{ e.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    <td>{{ actionLibelle(e.action) }}</td>
                    <td>
                      <span class="bea-stock-badge" [attr.data-niveau]="e.resultat === 'SUCCES' ? 'normal' : 'epuise'">
                        {{ e.resultat === 'SUCCES' ? 'Succès' : 'Échec' }}
                      </span>
                    </td>
                    <td>{{ e.user_nom || '—' }}</td>
                    <td>
                      {{ e.motif || '' }}
                      @if (e.details?.erreur) {
                        <div class="bea-periode__sub">{{ e.details?.erreur }}</div>
                      }
                      @if (e.details?.corrections) {
                        <div class="bea-periode__sub">{{ e.details?.corrections }} correction(s) intégrée(s)</div>
                      }
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="5" class="bea-mg__empty">Aucun événement enregistré.</td></tr>
                }
              </tbody>
            </table>
          </div>
        </div>
        <footer class="bea-mg__modal-foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="historique.set(null)">Fermer</button>
        </footer>
      </div>
    }

    @if (soldes(); as s) {
      <div class="bea-mg__backdrop" (click)="soldes.set(null)" role="presentation"></div>
      <div class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" aria-label="Soldes de période">
        <header class="bea-mg__modal-head">
          <div>
            <p class="bea-stock-page__kicker">Contrôle période</p>
            <h2>{{ s.periode.libelle }}</h2>
          </div>
          <span class="bea-stock-badge" [attr.data-niveau]="niveau(s.periode.statut)">{{ libelle(s.periode) }}</span>
        </header>
        <div class="bea-mg__modal-body">
          <p class="bea-stock-period-banner__label" style="margin:0 0 0.65rem">
            Du {{ s.periode.date_debut | date: 'dd/MM/yyyy' }} au {{ s.periode.date_fin | date: 'dd/MM/yyyy' }} · {{ s.lignes.length }} article(s)
          </p>
          <div class="bea-mg__table-scroll" style="max-height:min(22rem, 50vh)">
            <table class="bea-mg__table">
              <thead>
                <tr><th>Article</th><th>Réf.</th><th>Initial</th><th>Entrées</th><th>Sorties</th><th>Ajust.</th><th>Théorique</th><th>Compté</th><th>Final</th></tr>
              </thead>
              <tbody>
                @for (l of s.lignes; track l.article_code) {
                  <tr>
                    <td>{{ l.article_designation }}</td>
                    <td><code class="bea-mg__code">{{ l.article_code }}</code></td>
                    <td>{{ l.stock_initial | quantite }}</td>
                    <td>{{ l.entrees | quantite }}</td>
                    <td>{{ l.sorties | quantite }}</td>
                    <td>{{ l.ajustements | quantite }}</td>
                    <td>{{ l.stock_theorique | quantite }}</td>
                    <td>{{ l.stock_physique != null ? (l.stock_physique | quantite) : '—' }}</td>
                    <td><strong>{{ l.stock_final | quantite }}</strong></td>
                  </tr>
                } @empty {
                  <tr><td colspan="9" class="bea-mg__empty">Aucun solde sur cette période.</td></tr>
                }
              </tbody>
            </table>
          </div>
          @if (s.periode.statut === 'ROUVERTE') {
            <p class="bea-periode__sub" style="margin-top:0.85rem">
              Période rouverte : saisissez les régularisations dans
              <a routerLink="/stock-fournitures/entrees">Entrées</a> ou <a routerLink="/stock-fournitures/sorties">Sorties</a>
              en choisissant une date de {{ s.periode.libelle }}, puis clôturez de nouveau.
            </p>
          }
        </div>
        <footer class="bea-mg__modal-foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="soldes.set(null)">Fermer</button>
        </footer>
      </div>
    }
  `,
  styles: `
    .bea-periode__sub { font-size: 0.78rem; color: #64748b; }
    .bea-periode__h3 { font-size: 0.9rem; margin: 0.9rem 0 0.35rem; }
    .bea-periode__list { margin: 0; padding-left: 1.1rem; font-size: 0.86rem; display: grid; gap: 0.25rem; }
    .bea-periode__checks { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.35rem; font-size: 0.86rem; }
    .bea-periode__checks li { display: flex; gap: 0.45rem; align-items: flex-start; }
    .bea-periode__checks li[data-etat='ok'] mat-icon { color: #15803d; }
    .bea-periode__checks li[data-etat='ko'] mat-icon { color: #b91c1c; }
    .bea-periode__checks li[data-etat='warn'] mat-icon { color: #b45309; }
  `,
})
export class StockPeriodesPanelComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);

  readonly periodes = signal<PeriodeStock[]>([]);
  readonly active = signal<PeriodeActive | null>(null);
  readonly reouverture = signal<ReouverturePreview | null>(null);
  readonly cloture = signal<CloturePreview | null>(null);
  readonly historique = signal<{ periode: PeriodeStock; evenements: EvenementPeriode[] } | null>(null);
  readonly soldes = signal<{ periode: PeriodeStock; lignes: SoldePeriode[] } | null>(null);
  readonly busy = signal(false);

  readonly peutCloturer = computed(() => aPermission(this.auth.user(), PERM.cloture));
  readonly peutRouvrir = computed(() => aPermission(this.auth.user(), PERM.reouverture));
  readonly peutVoirHistorique = computed(() => aPermission(this.auth.user(), PERM.historique));

  readonly motifForm = this.fb.nonNullable.group({
    motif: ['', [Validators.required, Validators.minLength(5), Validators.maxLength(500)]],
  });

  readonly hasUnsavedChanges = unsavedChanges(
    () => !!this.reouverture() && this.motifForm.dirty && !this.busy(),
    () => this.motifForm,
  );

  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.reouverture()) this.fermerReouverture();
    else if (this.cloture()) this.cloture.set(null);
    else if (this.historique()) this.historique.set(null);
    else if (this.soldes()) this.soldes.set(null);
  }

  ngOnInit(): void {
    this.charger();
  }

  charger(): void {
    this.api.get<PeriodeStock[]>('/mg/stock/periodes').subscribe({
      next: (rows) => this.periodes.set(rows),
      error: (err) => this.erreur(err, 'Périodes indisponibles'),
    });
    this.api.get<PeriodeActive>('/mg/stock/periodes/active').subscribe({
      next: (p) => this.active.set(p),
      error: () => this.active.set(null),
    });
  }

  niveau(statut: StatutPeriode): string {
    return statut === 'OUVERTE' ? 'normal' : statut === 'ROUVERTE' ? 'warn' : 'epuise';
  }

  libelle(p: PeriodeStock): string {
    return p.statut_libelle || this.statutLibelle(p.statut);
  }

  statutLibelle(statut: StatutPeriode): string {
    return statut === 'OUVERTE' ? 'Ouverte' : statut === 'ROUVERTE' ? 'Rouverte' : 'Clôturée';
  }

  actionLibelle(action: string): string {
    return ACTIONS[action] ?? action;
  }

  voirSoldes(p: PeriodeStock): void {
    this.api
      .get<{ items: SoldePeriode[] }>(`/mg/stock/periodes/${p.id}/soldes`, { page: 1, size: 500 })
      .subscribe({
        next: (res) => this.soldes.set({ periode: p, lignes: res.items || [] }),
        error: (err) => this.erreur(err, 'Soldes de la période indisponibles'),
      });
  }

  voirHistorique(p: PeriodeStock): void {
    this.api.get<EvenementPeriode[]>(`/mg/stock/periodes/${p.id}/historique`).subscribe({
      next: (evenements) => this.historique.set({ periode: p, evenements }),
      error: (err) => this.erreur(err, 'Historique indisponible'),
    });
  }

  ouvrirReouverture(p: PeriodeStock): void {
    this.api.get<ReouverturePreview>(`/mg/stock/periodes/${p.id}/preview-reouverture`).subscribe({
      next: (preview) => {
        this.motifForm.reset({ motif: '' });
        this.reouverture.set(preview);
      },
      error: (err) => this.erreur(err, 'Réouverture impossible'),
    });
  }

  fermerReouverture(): void {
    this.reouverture.set(null);
    this.motifForm.reset({ motif: '' });
  }

  confirmerReouverture(): void {
    const preview = this.reouverture();
    if (!preview || this.motifForm.invalid) return;
    const motif = this.motifForm.getRawValue().motif.trim();
    this.feedback
      .run(() => this.api.post<PeriodeStock>(`/mg/stock/periodes/${preview.periode.id}/rouvrir`, { motif }), {
        loading: 'Réouverture…',
        busy: this.busy,
        errorTitle: 'Réouverture refusée',
        errorHint: 'La période reste clôturée ; le refus est tracé dans son historique.',
        success: (p) => ({
          title: `${p.libelle} rouverte pour régularisation`,
          message: 'Saisissez les corrections datées de cette période (Entrées / Sorties), puis clôturez-la de nouveau.',
          details: [{ label: 'Motif', value: motif }],
        }),
      })
      .subscribe(() => {
        this.motifForm.markAsPristine();
        this.reouverture.set(null);
        this.charger();
      });
  }

  ouvrirCloture(p: PeriodeStock): void {
    this.api.get<CloturePreview>(`/mg/stock/periodes/${p.id}/preview-cloture`).subscribe({
      next: (preview) => this.cloture.set(preview),
      error: (err) => this.erreur(err, 'Contrôles de clôture indisponibles'),
    });
  }

  confirmerCloture(preview: CloturePreview): void {
    this.feedback
      .run(
        () =>
          this.api.post<{ periode: PeriodeStock; periode_suivante: PeriodeStock; reports_corriges: number }>(
            `/mg/stock/periodes/${preview.periode.id}/cloturer`,
            {},
          ),
        {
          loading: 'Clôture…',
          busy: this.busy,
          errorTitle: 'Clôture refusée',
          errorHint: 'Aucune modification n’a été appliquée ; le refus est tracé dans l’historique.',
          success: (r) => ({
            title: `${r.periode.libelle} clôturée`,
            details: [
              { label: 'Stock reporté sur', value: r.periode_suivante.libelle },
              ...(preview.regularisation
                ? [{ label: 'Corrections intégrées', value: String(preview.regularisation.corrections.length) }]
                : []),
            ],
          }),
        },
      )
      .subscribe(() => {
        this.cloture.set(null);
        this.charger();
      });
  }

  private erreur(err: unknown, titre: string): void {
    describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, titre));
  }
}
