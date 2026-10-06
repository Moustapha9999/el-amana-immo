import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { formatMontant } from '../shared/montant.pipe';
import { FX_BASE, MOIS, annees, nettoyer, telechargerBlob } from './facturation.models';
import { FacturationStore } from './facturation.store';

interface Rapport {
  key: string;
  title: string;
  headers: string[];
  rows: (string | number | null)[][];
  count: number;
}

const CATALOGUE = [
  { key: 'mensuel', label: 'Rapport mensuel', icon: 'calendar_month', desc: 'Factures d’un mois avec totaux (TTC, à payer, payé, reste).', mois: true },
  { key: 'annuel', label: 'Rapport annuel', icon: 'stacked_bar_chart', desc: 'Synthèse mois par mois et comparaison à l’année précédente.' },
  { key: 'agences', label: 'Par agence', icon: 'account_balance', desc: 'Montants, moyennes, part et variation N-1 par agence.' },
  { key: 'pdv', label: 'PDV Amanty', icon: 'storefront', desc: 'Consommation et coûts des points de vente Amanty.' },
  { key: 'fournisseurs', label: 'Par fournisseur', icon: 'local_shipping', desc: 'Montants, moyenne, part et variation N-1 par fournisseur / profil.' },
  { key: 'fournisseurs_mois', label: 'Fournisseurs × mois', icon: 'grid_on', desc: 'Matrice mensuelle par fournisseur / profil avec totaux.' },
  { key: 'controles', label: 'Factures à valider', icon: 'pending_actions', desc: 'Factures reçues en attente de validation, avec les vérifications automatiques.' },
  { key: 'classeur', label: 'Classeur complet', icon: 'library_books', desc: 'Excel multi-onglets : synthèse, fournisseurs, agences, PDV, retards, manquantes, registre, paiements.' },
  { key: 'factures', label: 'Registre des factures', icon: 'receipt_long', desc: 'Liste détaillée filtrée (toutes colonnes).', mois: true },
  { key: 'retards', label: 'Factures en retard', icon: 'running_with_errors', desc: 'Factures échues non soldées et jours de retard.' },
  { key: 'paiements', label: 'Paiements', icon: 'payments', desc: 'Règlements de l’année (y compris annulations).', mois: true },
  { key: 'manquantes', label: 'Factures manquantes', icon: 'event_busy', desc: 'Points actifs sans facture sur les périodes attendues.' },
];

@Component({
  selector: 'bea-fx-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux · Facturation fournisseurs</p>
          <h1>Rapports</h1>
          <p class="bea-ct-head__sub">Aperçu à l’écran puis export PDF, Excel ou CSV, ou impression. Chaque export est tracé dans l’audit.</p>
        </div>
        <div class="bea-mg__actions"><a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="base"><mat-icon>dashboard</mat-icon> Vue 360°</a></div>
      </header>

      <div class="bea-fx-reports">
        @for (r of catalogue; track r.key) {
          <button type="button" class="bea-fx-report" [class.is-active]="cle() === r.key" (click)="choisir(r.key)">
            <mat-icon>{{ r.icon }}</mat-icon><strong>{{ r.label }}</strong><small>{{ r.desc }}</small>
          </button>
        }
      </div>

      <form class="bea-mg__search bea-ct-filters bea-fx-filters" [formGroup]="filtres">
        <label class="bea-mg__field">Année
          <select formControlName="year">
            @for (a of annees; track a) { <option [ngValue]="a">{{ a }}</option> }
          </select>
        </label>
        @if (avecMois()) {
          <label class="bea-mg__field">Mois
            <select formControlName="month">
              <option [ngValue]="null">{{ cle() === 'mensuel' ? 'Mois courant' : 'Tous' }}</option>
              @for (m of mois; track $index) { <option [ngValue]="$index + 1">{{ m }}</option> }
            </select>
          </label>
        }
        <label class="bea-mg__field">Fournisseur
          <select formControlName="supplier_id">
            <option value="">Tous</option>
            @for (f of store.ref()?.fournisseurs ?? []; track f.id) { <option [value]="f.id">{{ f.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Profil
          <select formControlName="profil_id">
            <option value="">Tous</option>
            @for (p of store.ref()?.profils ?? []; track p.id) { <option [value]="p.id">{{ p.libelle }}</option> }
          </select>
        </label>
        @if (!store.config()?.agence_scope) {
          <label class="bea-mg__field">Agence
            <select formControlName="agency_id">
              <option value="">Toutes</option>
              @for (a of store.ref()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
            </select>
          </label>
        }
        <label class="bea-mg__field">Type de site
          <select formControlName="type">
            <option value="">Tous</option>
            @for (t of store.config()?.types_point ?? []; track t.code) { <option [value]="t.code">{{ t.libelle }}</option> }
          </select>
        </label>
        <div class="bea-ct-filters__btns">
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="apercu()"><mat-icon>preview</mat-icon> Aperçu</button>
        </div>
      </form>

      <div class="bea-mg__panel bea-ct-panel">
        <div class="bea-mg__panel-top">
          <h2><mat-icon>summarize</mat-icon> {{ rapport()?.title || libelle() }}</h2>
          <div class="bea-fx-export">
            @if (store.cap().export || store.cap().reports) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporter('xlsx')"><mat-icon>table_view</mat-icon> {{ cle() === 'classeur' ? 'Excel multi-onglets' : 'Excel' }}</button>
              @if (cle() !== 'classeur') {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporter('csv')"><mat-icon>data_object</mat-icon> CSV</button>
              }
            }
          </div>
        </div>
        @if (chargement()) {
          @for (i of [1, 2, 3, 4]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
        } @else if (rapport(); as r) {
          <p class="bea-fx-sub">{{ r.count }} ligne(s)</p>
          <div class="bea-mg__table-wrap bea-fx-report-table">
            <table class="bea-mg__table">
              <thead><tr>@for (h of r.headers; track $index) { <th>{{ h }}</th> }</tr></thead>
              <tbody>
                @for (row of r.rows; track $index) {
                  <tr [class.bea-fx-total]="row[0] === 'Total'">@for (c of row; track $index) { <td [class.is-num]="isNum(c)">{{ cellule(c) }}</td> }</tr>
                } @empty { <tr><td [attr.colspan]="r.headers.length"><div class="bea-ct-empty"><mat-icon>inbox</mat-icon><p>Aucune donnée pour ces critères.</p></div></td></tr> }
              </tbody>
            </table>
          </div>
        } @else {
          <div class="bea-ct-empty"><mat-icon>summarize</mat-icon><p>Choisissez un rapport et cliquez sur « Aperçu ».</p></div>
        }
      </div>
    </section>
  `,
})
export class FacturationRapportsComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);

  readonly base = FX_BASE;
  readonly catalogue = CATALOGUE;
  readonly annees = annees();
  readonly mois = MOIS;
  readonly cle = signal('mensuel');
  readonly rapport = signal<Rapport | null>(null);
  readonly chargement = signal(false);
  readonly busy = signal(false);

  readonly filtres = this.fb.nonNullable.group({
    year: [new Date().getFullYear()],
    month: this.fb.control<number | null>(null),
    supplier_id: [''],
    profil_id: [''],
    agency_id: [''],
    type: [''],
  });

  ngOnInit(): void {
    this.store.charger();
  }

  avecMois(): boolean {
    return !!CATALOGUE.find((c) => c.key === this.cle())?.mois;
  }

  libelle(): string {
    return CATALOGUE.find((c) => c.key === this.cle())?.label ?? '';
  }

  choisir(key: string): void {
    this.cle.set(key);
    this.rapport.set(null);
    if (!this.avecMois()) this.filtres.patchValue({ month: null });
    this.apercu();
  }

  private params(format: string): Record<string, string> {
    return nettoyer({ ...this.filtres.getRawValue(), format });
  }

  apercu(): void {
    this.chargement.set(true);
    this.api.get<Rapport>(`/mg/factures/rapports/${this.cle()}`, this.params('json')).subscribe({
      next: (r) => {
        this.rapport.set(r);
        this.chargement.set(false);
      },
      error: (e) => {
        this.chargement.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Rapport indisponible'));
      },
    });
  }

  exporter(format: 'pdf' | 'xlsx' | 'csv'): void {
    const key = this.cle();
    this.feedback
      .run(() => this.api.download(`/mg/factures/rapports/${key}`, this.params(format)), {
        loading: 'Génération du rapport…',
        busy: this.busy,
        errorTitle: 'Export impossible',
        success: (blob) => {
          telechargerBlob(blob, `factures-${key}-${this.filtres.controls.year.value}.${format}`);
          return { title: 'Rapport généré', message: 'Le fichier a été téléchargé.' };
        },
      })
      .subscribe();
  }

  isNum(c: unknown): boolean {
    return typeof c === 'number';
  }

  cellule(c: string | number | null): string {
    if (c === null || c === undefined) return '';
    return typeof c === 'number' ? (Number.isInteger(c) && Math.abs(c) < 10000 ? String(c) : formatMontant(c)) : c;
  }
}
