import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { FX_BASE, FxProfil, FxTva, dateFr, fxStatut, fxTone } from './facturation.models';
import { FacturationStore } from './facturation.store';
import { FxTvaFormComponent } from './fx-tva-form.component';

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
  imports: [RouterLink, MatIconModule, FxTvaFormComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances · Factures</p>
          <h1>Paramètres de facturation</h1>
          <p class="bea-ct-head__sub">Seuils d’alerte, numérotation et TVA par profil. Les fournisseurs restent gérés dans le référentiel Achats, les agences dans le référentiel commun.</p>
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

        <div class="bea-mg__panel bea-ct-panel bea-fx-span2" id="tva">
          <div class="bea-mg__panel-top">
            <h2><mat-icon>percent</mat-icon> TVA par profil fournisseur</h2>
            <span class="bea-fx-tva__compte">{{ nbConfigures() }} / {{ profils()?.length ?? 0 }} profils configurés</span>
          </div>
          <p class="bea-ct-help"><mat-icon>gavel</mat-icon> Aucun taux n’est supposé : un profil sans taux en vigueur n’a ni proposition de TVA à la saisie, ni contrôle « TVA incohérente ». Chaque facture est contrôlée avec le taux applicable à sa date de facture.</p>
          @if (profils() === null) {
            @for (i of [1, 2, 3]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }
          } @else if (!profils()!.length) {
            <p class="bea-ct-help"><mat-icon>info</mat-icon> Aucun profil fournisseur. Créez-en un depuis la page Fournisseurs.</p>
          } @else {
            <div class="bea-fx-tva">
              @for (p of profils()!; track p.id) {
                <article class="bea-fx-tva__row" [class.is-off]="!p.actif">
                  <div class="bea-fx-tva__profil">
                    <strong>{{ p.libelle }}</strong>
                    <small>{{ p.fournisseur || '—' }}{{ p.actif ? '' : ' · inactif' }}</small>
                  </div>
                  <div class="bea-fx-tva__courant">
                    @if (p.taux_tva !== null) {
                      <span class="bea-ct-badge" data-tone="ACTIF">{{ p.taux_tva }} % aujourd’hui</span>
                    } @else {
                      <span class="bea-ct-badge" data-tone="EXPIRE">Non configurée</span>
                    }
                  </div>
                  <ul class="bea-fx-tva__liste">
                    @for (t of p.taux_tva_liste; track t.id) {
                      <li [attr.data-etat]="t.etat">
                        <span class="bea-fx-tva__taux">{{ t.taux }} %</span>
                        <span class="bea-fx-tva__periode">{{ periode(t) }}</span>
                        <span class="bea-fx-tva__etat">{{ etatLabel(t.etat) }}</span>
                        @if (t.observation) { <small class="bea-fx-tva__obs" [title]="t.observation">{{ t.observation }}</small> }
                        @if (store.cap().manage) {
                          <span class="bea-fx-tva__actions">
                            <button type="button" class="bea-fx-tva__btn" title="Modifier" [attr.aria-label]="'Modifier le taux ' + t.taux + ' %'" (click)="editer(p, t)"><mat-icon>edit</mat-icon></button>
                            <button type="button" class="bea-fx-tva__btn bea-fx-tva__btn--danger" title="Supprimer" [attr.aria-label]="'Supprimer le taux ' + t.taux + ' %'" [disabled]="busy()" (click)="supprimer(p, t)"><mat-icon>delete</mat-icon></button>
                          </span>
                        }
                      </li>
                    } @empty {
                      <li class="bea-fx-tva__vide">Aucun taux — aucune TVA proposée ni contrôlée.</li>
                    }
                  </ul>
                  @if (store.cap().manage) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-fx-tva__add" (click)="editer(p, null)"><mat-icon>add</mat-icon> Taux</button>
                  }
                </article>
              }
            </div>
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

      @if (edition(); as e) {
        <bea-fx-tva-form [profil]="e.profil" [tva]="e.tva" (saved)="tvaEnregistree($event)" (closed)="edition.set(null)" />
      }
    </section>
  `,
})
export class FacturationParametresComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(UiDialogService);

  readonly base = FX_BASE;
  readonly flux = ['BROUILLON', 'RECUE', 'A_CONTROLER', 'CONTROLEE', 'VALIDEE', 'A_PAYER', 'PAYEE', 'ARCHIVEE'];
  readonly params = signal<Parametre[] | null>(null);
  readonly brouillon = signal<Record<string, string>>({});
  readonly busy = signal(false);

  private readonly nbModifies = computed(() => {
    const b = this.brouillon();
    return (this.params() ?? []).filter((p) => b[p.cle] !== undefined && b[p.cle] !== p.valeur).length;
  });
  readonly hasUnsavedChanges = unsavedChanges(() => this.nbModifies() > 0 || !!this.tvaForm()?.dirty());

  readonly profils = signal<FxProfil[] | null>(null);
  readonly edition = signal<{ profil: FxProfil; tva: FxTva | null } | null>(null);
  private readonly tvaForm = viewChild(FxTvaFormComponent);
  readonly nbConfigures = computed(() => (this.profils() ?? []).filter((p) => p.taux_tva !== null).length);

  ngOnInit(): void {
    this.store.charger();
    this.chargerTva();
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

  private chargerTva(): void {
    this.api.get<FxProfil[]>('/mg/factures/tva').subscribe({
      next: (p) => this.profils.set(p),
      error: (e) => {
        this.profils.set([]);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'TVA des profils indisponible'));
      },
    });
  }

  periode(t: FxTva): string {
    if (!t.date_debut && !t.date_fin) return 'Toutes dates';
    if (!t.date_fin) return `Depuis le ${dateFr(t.date_debut)}`;
    if (!t.date_debut) return `Jusqu’au ${dateFr(t.date_fin)}`;
    return `Du ${dateFr(t.date_debut)} au ${dateFr(t.date_fin)}`;
  }

  etatLabel(etat: FxTva['etat']): string {
    return { EN_VIGUEUR: 'En vigueur', A_VENIR: 'À venir', EXPIRE: 'Expiré' }[etat];
  }

  editer(profil: FxProfil, tva: FxTva | null): void {
    if (this.store.cap().manage) this.edition.set({ profil, tva });
  }

  tvaEnregistree(p: FxProfil): void {
    this.edition.set(null);
    this.majProfil(p);
  }

  private majProfil(p: FxProfil): void {
    this.profils.update((rows) => (rows ?? []).map((x) => (x.id === p.id ? p : x)));
    this.store.charger(true);
  }

  supprimer(profil: FxProfil, t: FxTva): void {
    this.dialog
      .confirm({
        title: 'Supprimer ce taux de TVA ?',
        message: `${profil.libelle} : ${t.taux} % (${this.periode(t).toLowerCase()}).`,
        hint: 'Les factures de cette période ne seront plus contrôlées sur la TVA, sauf si un autre taux couvre leur date. L’opération est tracée dans l’audit.',
        confirmLabel: 'Supprimer',
        tone: 'danger',
        icon: 'delete',
      })
      .subscribe((ok) => {
        if (!ok) return;
        this.feedback
          .run(() => this.api.delete<FxProfil>(`/mg/factures/tva/${t.id}`), {
            loading: 'Suppression du taux…',
            busy: this.busy,
            errorTitle: 'Suppression refusée',
            success: (r) => ({
              title: 'Taux supprimé',
              message: `${r.libelle} : ${t.taux} % retiré`,
              details: [{ label: 'TVA en vigueur aujourd’hui', value: r.taux_tva === null ? 'Non configurée' : `${r.taux_tva} %` }],
            }),
          })
          .subscribe((r) => this.majProfil(r));
      });
  }

  statut(code: string): string {
    return fxStatut(code);
  }

  tone(code: string): string {
    return fxTone(code);
  }
}
