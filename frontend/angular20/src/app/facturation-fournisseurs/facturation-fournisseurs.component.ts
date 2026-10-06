import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';
import { MontantPipe } from '../shared/montant.pipe';
import { ChampProfil, FX_BASE, FxFournisseurStat, FxFournisseursStats, FxProfil, LIBELLES_CHAMPS, annees, dateFr } from './facturation.models';
import { FacturationStore } from './facturation.store';
import { FxProfilFormComponent } from './fx-profil-form.component';

/** Fournisseurs facturés et leurs profils (champs, libellés, TVA) : ajout d'un fournisseur sans modifier le code. */
@Component({
  selector: 'bea-fx-fournisseurs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, MontantPipe, FxProfilFormComponent],
  template: `
    <section class="bea-mg bea-nf bea-ct bea-fx">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Moyens Généraux · Facturation fournisseurs</p>
          <h1>Fournisseurs</h1>
          <p class="bea-ct-head__sub">Chaque profil définit les champs obligatoires, facultatifs ou masqués, les libellés de la facture et le taux de TVA. Aucune règle fiscale n’est supposée.</p>
        </div>
        <div class="bea-mg__actions">
          <label class="bea-mg__field bea-fx-inline">Année
            <select [value]="annee()" (change)="changerAnnee(+$any($event.target).value)">
              @for (a of annees; track a) { <option [value]="a" [selected]="a === annee()">{{ a }}</option> }
            </select>
          </label>
          @if (store.cap().manage) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouveau()"><mat-icon>add_business</mat-icon> Nouveau fournisseur</button>
          }
        </div>
      </header>

      @if (stats(); as s) {
        <div class="bea-fx-kpis bea-fx-kpis--4">
          <article class="bea-fx-kpi" data-tone="brand"><mat-icon>local_shipping</mat-icon><p>Profils actifs</p><strong>{{ s.nb_profils }}</strong><small>{{ s.items.length }} fournisseur(s) suivis</small></article>
          <article class="bea-fx-kpi"><mat-icon>account_balance_wallet</mat-icon><p>Facturé {{ s.annee }}</p><strong>{{ s.total | montant }}</strong><small>Montants TTC comptés</small></article>
          <a class="bea-fx-kpi" data-tone="warn" [routerLink]="base + '/factures'" [queryParams]="{ vue: 'a_payer' }"><mat-icon>payments</mat-icon><p>Reste à payer</p><strong>{{ s.reste | montant }}</strong><small>Toutes périodes</small></a>
          <a class="bea-fx-kpi" data-tone="alert" [routerLink]="base + '/controles'"><mat-icon>fact_check</mat-icon><p>À contrôler</p><strong>{{ aControler() }}</strong><small>Factures reçues non contrôlées</small></a>
        </div>

        <div class="bea-mg__search bea-ct-filters bea-fx-filters">
          <label class="bea-mg__field bea-fx-grow">Rechercher
            <input type="search" [value]="q()" (input)="q.set($any($event.target).value)" placeholder="Fournisseur, profil, code…" />
          </label>
          <label class="bea-fx-check"><input type="checkbox" [checked]="inactifs()" (change)="inactifs.set($any($event.target).checked)" /> Afficher les profils inactifs</label>
        </div>

        <div class="bea-fx-suppliers">
          @for (it of visibles(); track it.cle; let i = $index) {
            <article class="bea-fx-supplier" [class.is-off]="!it.actif" [style.--i]="i">
              <header class="bea-fx-supplier__head">
                <span class="bea-fx-supplier__avatar" aria-hidden="true">{{ initiales(it.libelle) }}</span>
                <div>
                  <h2>{{ it.libelle }}</h2>
                  <small>{{ it.fournisseur || '—' }}{{ it.fournisseur_code ? ' · ' + it.fournisseur_code : '' }}</small>
                </div>
                @if (store.cap().manage) {
                  @if (it.profil) {
                    <button type="button" class="bea-mg__icon-btn" title="Configurer le profil" aria-label="Configurer le profil" (click)="configurer(it)"><mat-icon>tune</mat-icon></button>
                  } @else {
                    <button type="button" class="bea-mg__icon-btn" title="Créer un profil" aria-label="Créer un profil" (click)="nouveau(it.fournisseur_id)"><mat-icon>add_circle</mat-icon></button>
                  }
                }
              </header>

              <p class="bea-fx-tags">
                @if (it.profil?.type_facture) { <span>{{ store.typeFacture(it.profil!.type_facture) }}</span> }
                @if (it.profil) {
                  <span [attr.data-tone]="it.profil.taux_tva === null ? 'muted' : null">{{ it.profil.taux_tva === null ? 'TVA non configurée' : 'TVA ' + it.profil.taux_tva + ' %' }}</span>
                } @else { <span data-tone="warn">Sans profil</span> }
                @if (!it.actif) { <span data-tone="muted">Inactif</span> }
                @if (!it.fournisseur_actif) { <span data-tone="warn">Fournisseur inactif</span> }
              </p>

              <dl class="bea-fx-supplier__stats">
                <div><dt>Facturé {{ annee() }}</dt><dd>{{ it.montant | montant }}</dd></div>
                <div><dt>Factures</dt><dd>{{ it.nb }}</dd></div>
                <div><dt>Reste à payer</dt><dd [class.bea-ct-neg]="it.reste > 0">{{ it.reste | montant }}</dd></div>
                <div><dt>Points actifs</dt><dd>{{ it.points }}</dd></div>
              </dl>

              <svg class="bea-fx-spark" viewBox="0 0 120 28" preserveAspectRatio="none" role="img" [attr.aria-label]="'Évolution mensuelle ' + it.libelle">
                <polyline [attr.points]="spark(it.mensuel)" />
              </svg>

              @if (it.profil; as p) {
                <p class="bea-fx-supplier__champs">
                  <mat-icon>rule</mat-icon>
                  @if (obligatoires(p).length) { Obligatoire : {{ obligatoires(p).join(', ') }} } @else { Aucun champ obligatoire hors TTC }
                  @if (masques(p).length) { <br /><mat-icon>visibility_off</mat-icon> Masqué : {{ masques(p).join(', ') }} }
                </p>
              }

              <footer class="bea-fx-supplier__foot">
                <small>{{ it.derniere_facture ? 'Dernière facture ' + date(it.derniere_facture) : 'Aucune facture' }}</small>
                <span>
                  @if (it.a_controler) {
                    <a class="bea-ct-badge" data-tone="WARN" [routerLink]="base + '/controles'" [queryParams]="filtre(it)">{{ it.a_controler }} à contrôler</a>
                  }
                  <a class="bea-ct-link" [routerLink]="base + '/factures'" [queryParams]="filtre(it)">Factures <mat-icon>chevron_right</mat-icon></a>
                </span>
              </footer>
            </article>
          } @empty {
            <div class="bea-ct-empty bea-fx-span2"><mat-icon>local_shipping</mat-icon><p>Aucun fournisseur ne correspond.</p></div>
          }
        </div>
      } @else {
        <div class="bea-fx-kpis bea-fx-kpis--4">@for (i of [1, 2, 3, 4]; track i) { <span class="bea-fx-skel bea-fx-skel--kpi"></span> }</div>
        <div class="bea-fx-suppliers">@for (i of [1, 2, 3, 4, 5, 6]; track i) { <span class="bea-fx-skel bea-fx-skel--chart"></span> }</div>
      }
    </section>

    @if (edition(); as e) {
      <bea-fx-profil-form [profil]="e.profil" [fournisseurId]="e.fournisseurId" [profilUtilise]="e.utilise"
        (saved)="apresEnregistrement()" (closed)="edition.set(null)" />
    }
  `,
})
export class FacturationFournisseursComponent implements OnInit {
  readonly store = inject(FacturationStore);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);

  readonly base = FX_BASE;
  readonly annees = annees();
  readonly annee = signal(new Date().getFullYear());
  readonly stats = signal<FxFournisseursStats | null>(null);
  readonly q = signal('');
  readonly inactifs = signal(false);
  readonly edition = signal<{ profil: FxProfil | null; fournisseurId: string | null; utilise: boolean } | null>(null);
  private readonly form = viewChild(FxProfilFormComponent);
  readonly hasUnsavedChanges = () => !!this.form()?.isDirty();

  readonly visibles = computed(() => {
    const q = this.q().trim().toLowerCase();
    return (this.stats()?.items ?? []).filter(
      (i) =>
        (this.inactifs() || i.actif) &&
        (!q || [i.libelle, i.fournisseur, i.fournisseur_code, i.profil?.code].some((v) => v?.toLowerCase().includes(q))),
    );
  });

  readonly aControler = computed(() => (this.stats()?.items ?? []).reduce((a, i) => a + i.a_controler, 0));

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    this.api.get<FxFournisseursStats>('/mg/factures/fournisseurs', { year: String(this.annee()) }).subscribe({
      next: (s) => this.stats.set(s),
      error: (e) => {
        this.stats.set({ annee: this.annee(), items: [], total: 0, reste: 0, nb_profils: 0 });
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Fournisseurs indisponibles'));
      },
    });
  }

  changerAnnee(a: number): void {
    this.annee.set(a);
    this.stats.set(null);
    this.charger();
  }

  nouveau(fournisseurId: string | null = null): void {
    this.edition.set({ profil: null, fournisseurId, utilise: false });
  }

  configurer(it: FxFournisseurStat): void {
    if (!it.profil) return;
    this.edition.set({ profil: it.profil, fournisseurId: null, utilise: it.nb > 0 || it.nb_ouvertes > 0 || it.points > 0 });
  }

  apresEnregistrement(): void {
    this.edition.set(null);
    this.charger();
  }

  filtre(it: FxFournisseurStat): Record<string, string> {
    return it.profil_id ? { profil_id: it.profil_id } : { supplier_id: it.fournisseur_id ?? '' };
  }

  obligatoires(p: FxProfil): string[] {
    return this.parEtat(p, 'obligatoire').filter((c) => c !== 'montant_ttc').map((c) => p.libelles?.[c] || LIBELLES_CHAMPS[c]);
  }

  masques(p: FxProfil): string[] {
    return this.parEtat(p, 'masque').map((c) => LIBELLES_CHAMPS[c]);
  }

  private parEtat(p: FxProfil, etat: string): ChampProfil[] {
    return (Object.keys(p.champs ?? {}) as ChampProfil[]).filter((c) => p.champs[c] === etat && LIBELLES_CHAMPS[c]);
  }

  spark(valeurs: number[]): string {
    const max = Math.max(...valeurs, 1);
    return valeurs.map((v, i) => `${((i / 11) * 120).toFixed(1)},${(26 - (v / max) * 24).toFixed(1)}`).join(' ');
  }

  initiales(nom: string): string {
    return nom.split(/[\s\-()]+/).filter(Boolean).slice(0, 2).map((m) => m[0]).join('').toUpperCase();
  }

  date(iso: string): string {
    return dateFr(iso);
  }
}
