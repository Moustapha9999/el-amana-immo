import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { FX_BASE, fxStatut, fxTone } from './facturation.models';
import { FacturationStore } from './facturation.store';

interface Parametre {
  cle: string;
  valeur: string;
  libelle: string | null;
}

const UNITES: Record<string, string> = {
  'factures.delai_paiement_jours': 'jours',
  'factures.alerte_echeance_jours': 'jours',
  'factures.seuil_hausse_pct': '%',
  'factures.delai_reception_jours': 'jours',
};

@Component({
  selector: 'bea-fx-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances · Factures</p>
          <h1>Paramètres de facturation</h1>
          <p class="bea-ct-head__sub">Seuils d’alerte et numérotation. Les fournisseurs restent gérés dans le référentiel Achats, les agences dans le référentiel commun.</p>
        </div>
        <div class="bea-mg__actions"><a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="base"><mat-icon>dashboard</mat-icon> Vue 360°</a></div>
      </header>

      <div class="bea-fx-grid">
        <div class="bea-mg__panel bea-ct-panel bea-fx-span2">
          <div class="bea-mg__panel-top"><h2><mat-icon>tune</mat-icon> Seuils et numérotation</h2></div>
          @if (params() === null) {
            @for (i of [1, 2, 3]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
          } @else {
            <ul class="bea-fx-params">
              @for (p of params()!; track p.cle) {
                <li>
                  <div><strong>{{ p.libelle || p.cle }}</strong><small><code>{{ p.cle }}</code></small></div>
                  <span class="bea-fx-params__input">
                    <input [value]="valeur(p)" [disabled]="!store.cap().manage" [attr.inputmode]="unite(p.cle) ? 'numeric' : 'text'"
                      (input)="modifier(p.cle, $any($event.target).value)" (keydown.enter)="enregistrer(p)" [attr.aria-label]="p.libelle || p.cle" />
                    @if (unite(p.cle)) { <em>{{ unite(p.cle) }}</em> }
                  </span>
                  @if (store.cap().manage) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!modifie(p) || busy()" (click)="enregistrer(p)"><mat-icon>save</mat-icon></button>
                  }
                </li>
              }
            </ul>
            @if (!store.cap().manage) { <p class="bea-ct-help"><mat-icon>lock</mat-icon> Lecture seule : la permission « Paramétrer la facturation » est requise pour modifier.</p> }
          }
        </div>

        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-mg__panel-top"><h2><mat-icon>account_tree</mat-icon> Cycle de vie</h2></div>
          <ol class="bea-fx-flow">
            @for (s of flux; track s) { <li><span class="bea-ct-badge" [attr.data-tone]="tone(s)">{{ statut(s) }}</span></li> }
          </ol>
          <p class="bea-ct-help"><mat-icon>info</mat-icon> Exceptions : Contestée, Annulée (motif obligatoire). Paiement calculé automatiquement : À payer, Partiellement payée, Payée. Aucune suppression physique de l’historique financier.</p>
        </div>

        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-mg__panel-top"><h2><mat-icon>category</mat-icon> Référentiels</h2></div>
          <h3 class="bea-fx-h3">Types de facture</h3>
          <p class="bea-fx-tags">@for (t of store.config()?.types_facture ?? []; track t.code) { <span>{{ t.libelle }}</span> }</p>
          <h3 class="bea-fx-h3">Types de site</h3>
          <p class="bea-fx-tags">@for (t of store.config()?.types_point ?? []; track t.code) { <span>{{ t.libelle }}</span> }</p>
          <h3 class="bea-fx-h3">Pièces justificatives (GED)</h3>
          <p class="bea-fx-tags">@for (t of store.config()?.types_document ?? []; track t.code) { <span>{{ t.libelle }}</span> }</p>
          <p class="bea-ct-help"><mat-icon>folder_shared</mat-icon> Les pièces sont stockées dans la GED centrale (max {{ store.config()?.ged_taille_max_mo ?? '—' }} Mo par fichier).</p>
        </div>
      </div>
    </section>
  `,
})
export class FacturationParametresComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);

  readonly base = FX_BASE;
  readonly flux = ['BROUILLON', 'RECUE', 'A_CONTROLER', 'VALIDEE', 'A_PAYER', 'PAYEE', 'ARCHIVEE'];
  readonly params = signal<Parametre[] | null>(null);
  readonly brouillon = signal<Record<string, string>>({});
  readonly busy = signal(false);

  private readonly nbModifies = computed(() => {
    const b = this.brouillon();
    return (this.params() ?? []).filter((p) => b[p.cle] !== undefined && b[p.cle] !== p.valeur).length;
  });
  readonly hasUnsavedChanges = unsavedChanges(() => this.nbModifies() > 0);

  ngOnInit(): void {
    this.store.charger();
    this.api.get<Parametre[]>('/mg/factures/parametres').subscribe({
      next: (p) => this.params.set(p),
      error: (e) => {
        this.params.set([]);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Paramètres indisponibles'));
      },
    });
  }

  unite(cle: string): string {
    return UNITES[cle] ?? '';
  }

  valeur(p: Parametre): string {
    return this.brouillon()[p.cle] ?? p.valeur;
  }

  modifier(cle: string, valeur: string): void {
    this.brouillon.update((b) => ({ ...b, [cle]: valeur }));
  }

  modifie(p: Parametre): boolean {
    const v = this.brouillon()[p.cle];
    return v !== undefined && v.trim() !== p.valeur;
  }

  enregistrer(p: Parametre): void {
    if (!this.modifie(p) || !this.store.cap().manage) return;
    const valeur = this.brouillon()[p.cle].trim();
    this.feedback
      .run(() => this.api.put<Parametre>(`/mg/factures/parametres/${encodeURIComponent(p.cle)}`, { valeur }), {
        loading: 'Enregistrement…',
        busy: this.busy,
        errorTitle: 'Paramètre refusé',
        success: (r) => ({ title: 'Paramètre enregistré', message: `${r.libelle || r.cle} : ${r.valeur}` }),
      })
      .subscribe((r) => {
        this.params.update((rows) => (rows ?? []).map((x) => (x.cle === r.cle ? r : x)));
        this.brouillon.update((b) => {
          const { [r.cle]: _, ...reste } = b;
          return reste;
        });
        this.store.charger(true);
      });
  }

  statut(code: string): string {
    return fxStatut(code);
  }

  tone(code: string): string {
    return fxTone(code);
  }
}
