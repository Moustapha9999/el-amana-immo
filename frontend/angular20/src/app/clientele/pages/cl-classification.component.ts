import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, FICHE_SCORING, MATRICE_LBC, STATUTS_REGLE, dateHeureFr, libSource, n, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface Item {
  racine_client: string; raison_sociale: string; niveau: string; source: string;
  motif_risque: string | null; motif_classement: string | null; classifie_le: string | null;
}
interface Version { id: string; numero: number; libelle: string; statut: string; mode: string; }
interface CritereMaitre {
  code: string; libelle: string; source: string; disponible: string;
  utilisable_auto: boolean; type_decision: string; statut: string;
}
interface Divergence { domaine: string; cle: string; source_a: string; valeur_a: string; source_b: string; valeur_b: string; statut: string; }
interface LigneEval {
  critere: string; libelle: string; famille?: string; etat: string; valeur: string | null; poids: number | null;
  niveau_matrice: string | null; niveau_v4: string | null; motif: string; divergence: boolean;
  blocking_propose: boolean; contribue_au_score?: boolean;
}
interface Evaluation {
  racine_client: string; score_total: number; niveau_final: string | null; niveau_score: string | null;
  niveau_max: string | null; statut: string; coherence: string; motif_principal: string | null;
  motif_genere?: string; scores_familles?: Record<string, number>;
  version_regles: string; version_moteur: string; avertissement: string; lignes: LigneEval[];
}
interface ValeurMaitre {
  dimension: string; critere: string; code: string; libelle: string;
  score_v1: number | null; niveau_v1: string | null; score_v4: number | null; niveau_v4: string | null;
  score_retenu: number | null; niveau_retenu: string | null; is_blocking: boolean;
  source: string; source_libelle?: string; conflit: boolean; statut: string; note?: string;
}
interface SyntheseValeurs { total?: number; total_filtre?: number; nb_conflits?: number; nb_blocking?: number; par_dimension?: Record<string, number>; }

type Onglet = 'clients' | 'simulation' | 'referentiel' | 'criteres' | 'divergences' | 'versions';
const ONGLETS: readonly Onglet[] = ['clients', 'simulation', 'referentiel', 'criteres', 'divergences', 'versions'];
const TAILLE_VALEURS = 80;

@Component({
  selector: 'bea-cl-classification',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Risque</p>
          <h1>Classification des clients</h1>
          <p class="bea-cl-head__sub">Au niveau CLIENT (racine 6 chiffres), jamais RIB. Moteur SCORE (CDC 1.0) fondé sur la {{ matrice }} et la {{ fiche }}.</p>
        </div>
      </header>

      <nav class="bea-cl-tabs" role="tablist" aria-label="Classification">
        @for (o of onglets; track o.code) {
          <button type="button" role="tab" [class.is-on]="onglet() === o.code" [attr.aria-selected]="onglet() === o.code" (click)="ouvrir(o.code)">
            <mat-icon>{{ o.icon }}</mat-icon>{{ o.libelle }}
            @if (o.compte(); as c) { <span class="bea-cl-tabs__n">{{ n(c) }}</span> }
          </button>
        }
      </nav>

      @switch (onglet()) {
        @case ('clients') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Clients classés</h2>
              @if (store.cap().classif_executer) {
                <span style="display:flex;gap:0.4rem;flex-wrap:wrap">
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="modele()"><mat-icon>download</mat-icon> Modèle Excel</button>
                  <label class="bea-mg__btn bea-mg__btn--ghost">
                    <mat-icon>upload_file</mat-icon> Excel contrôlé
                    <input type="file" accept=".xlsx" hidden (change)="excel($any($event.target))" />
                  </label>
                  <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/imports" [queryParams]="{ source: 'liste' }"><mat-icon>group_add</mat-icon> Classer une liste</a>
                  <button type="button" class="bea-mg__btn" (click)="moteur()" [disabled]="busy()"><mat-icon>play_arrow</mat-icon> Appliquer règles ACTIVE</button>
                </span>
              }
            </div>
            <div class="bea-cl-filters">
              <label>Niveau
                <select [(ngModel)]="niveau" (ngModelChange)="charger()">
                  <option value="">Tous</option>
                  <option>FAIBLE</option><option>MOYEN</option><option>ELEVE</option><option>INTERDIT</option>
                </select>
              </label>
              <label>Recherche
                <input [(ngModel)]="q" (keyup.enter)="charger()" placeholder="Racine ou nom" />
              </label>
            </div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Racine</th><th>Nom</th><th>Niveau</th><th>Source</th><th>Motifs</th><th>Le</th></tr></thead>
                <tbody>
                  @for (i of items(); track i.racine_client) {
                    <tr class="is-click" [routerLink]="['/clientele/clients', i.racine_client]" style="cursor:pointer">
                      <td><code>{{ i.racine_client }}</code></td>
                      <td>{{ i.raison_sociale }}</td>
                      <td><span class="bea-cl-badge" [attr.data-s]="i.niveau">{{ i.niveau }}</span></td>
                      <td><span class="bea-cl-badge" [attr.data-s]="i.source">{{ i.source }}</span></td>
                      <td>{{ i.motif_classement || i.motif_risque || '—' }}</td>
                      <td>{{ dh(i.classifie_le) }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="6"><div class="bea-cl-empty">Aucun client classé. Saisie sur la fiche client, Excel contrôlé, liste importée, ou moteur une fois les règles validées.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('simulation') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Évaluer une racine</h2>
              @if (store.cap().classif_executer) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="backtest()" [disabled]="busy()"><mat-icon>compare_arrows</mat-icon> Backtest (échantillon)</button>
              }
            </div>
            <p class="bea-cl-hint" style="padding:0 1.1rem">Simulation : le score est calculé et tracé, la classification du client n’est pas modifiée.</p>
            <div class="bea-cl-filters">
              <label>Racine
                <input [(ngModel)]="racineEval" maxlength="6" placeholder="000001" (keyup.enter)="evaluer()" />
              </label>
              <label>&nbsp;<button type="button" class="bea-mg__btn" (click)="evaluer()" [disabled]="busy()">Calculer le score</button></label>
            </div>
            @if (evaluation(); as e) {
              <dl class="bea-cl-dl">
                <dt>Score</dt><dd>{{ n(e.score_total) }}</dd>
                <dt>Niveau</dt><dd><span class="bea-cl-badge" [attr.data-s]="e.niveau_final || 'NON_CLASSE'">{{ e.niveau_final || 'NON CLASSÉ' }}</span></dd>
                <dt>Statut</dt><dd><span class="bea-cl-badge" [attr.data-s]="e.statut">{{ e.statut }}</span> {{ e.coherence }}</dd>
                <dt>Motif</dt><dd>{{ e.motif_genere || e.motif_principal || '—' }}</dd>
                @if (e.scores_familles) {
                  <dt>Familles</dt>
                  <dd>Client {{ n(e.scores_familles['CLIENT'] || 0) }} · Géographie {{ n(e.scores_familles['GEOGRAPHIE'] || 0) }} · Produit / opération {{ n(e.scores_familles['PRODUIT_SERVICE_OPERATION'] || 0) }} · Canal {{ n(e.scores_familles['CANAL'] || 0) }}</dd>
                }
                <dt>Version</dt><dd>{{ e.version_regles }} / {{ e.version_moteur }}</dd>
              </dl>
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead><tr><th>Famille</th><th>Critère</th><th>État</th><th>Valeur</th><th>Score</th><th>{{ matrice }}</th><th>{{ fiche }}</th><th>Motif</th></tr></thead>
                  <tbody>
                    @for (lg of e.lignes; track lg.critere) {
                      <tr>
                        <td>{{ familles[lg.famille || ''] || lg.famille || '—' }}</td>
                        <td>{{ lg.libelle }}</td>
                        <td>{{ lg.etat }}@if (lg.contribue_au_score) { · compté}</td>
                        <td>{{ lg.valeur || '—' }}</td>
                        <td>{{ lg.poids ?? '—' }}</td>
                        <td>{{ lg.niveau_matrice || '—' }}</td>
                        <td>{{ lg.niveau_v4 || '—' }}</td>
                        <td>{{ lg.motif }}@if (lg.divergence) { ⚠}@if (lg.blocking_propose) { — INTERDIT}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <div class="bea-cl-empty"><mat-icon>calculate</mat-icon>Saisissez une racine pour voir le détail du score par critère.</div>
            }
          </section>
          <p class="bea-cl-note"><mat-icon>warning</mat-icon>{{ avertissement() || 'SCORE uniquement. Donnée absente ≠ Faible. 0 critère → NON CLASSÉ. INTERDIT = blocage, le score reste calculé.' }}</p>
        }

        @case ('referentiel') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <div><h2>Référentiel maître</h2><p class="bea-cl-hint">Dimension → Critère → Valeur → Score → Niveau → Source → Conflit → Statut. Aucune valeur n’est ACTIVE.</p></div>
            </div>
            <div class="bea-cl-stats">
              <div class="bea-cl-stat"><span>Valeurs</span><strong>{{ n(synValeurs().total) }}</strong></div>
              <div class="bea-cl-stat" data-tone="danger"><span>Interdites (blocage)</span><strong>{{ n(synValeurs().nb_blocking) }}</strong></div>
              <div class="bea-cl-stat" data-tone="warn"><span>Conflits à arbitrer</span><strong>{{ n(synValeurs().nb_conflits) }}</strong></div>
            </div>
            <div class="bea-cl-filters">
              <label>Dimension
                <select [(ngModel)]="dimension" (ngModelChange)="chargerValeurs(1)">
                  <option value="">Toutes</option>
                  @for (d of dimensions; track d.code) { <option [value]="d.code">{{ d.libelle }}</option> }
                </select>
              </label>
              <label>Statut
                <select [(ngModel)]="statutValeur" (ngModelChange)="chargerValeurs(1)">
                  <option value="">Tous</option>
                  @for (s of statutsRegle; track s[0]) { <option [value]="s[0]">{{ s[1] }}</option> }
                </select>
              </label>
            </div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Critère</th><th>Valeur</th><th>{{ matrice }}</th><th>{{ fiche }}</th><th>Retenu</th><th>Source</th><th>Statut</th></tr></thead>
                <tbody>
                  @for (v of valeurs(); track v.dimension + v.critere + v.code) {
                    <tr [attr.title]="v.note || null">
                      <td>{{ v.critere }}</td>
                      <td>{{ v.libelle }}</td>
                      <td>{{ v.niveau_v1 || '—' }}</td>
                      <td>{{ v.niveau_v4 || '—' }}@if (v.score_v4 !== null) { <small class="bea-cl-hint"> ({{ n(v.score_v4) }})</small> }</td>
                      <td>
                        @if (v.niveau_retenu) { <span class="bea-cl-badge" [attr.data-s]="v.niveau_retenu">{{ v.niveau_retenu }}</span> }
                        @else { {{ v.conflit ? 'À arbitrer' : '—' }} }
                      </td>
                      <td>{{ v.source_libelle || libSource(v.source) }}</td>
                      <td><span class="bea-cl-badge" [attr.data-s]="v.statut">{{ statuts[v.statut] || v.statut }}</span></td>
                    </tr>
                  } @empty {
                    <tr><td colspan="7"><div class="bea-cl-empty">Référentiel maître non chargé.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
            @if ((synValeurs().total_filtre || 0) > tailleValeurs) {
              <div class="bea-cl-bar" style="position:static">
                <span>Page {{ pageValeurs() }} — {{ n(synValeurs().total_filtre) }} valeur(s)</span>
                <span style="display:flex;gap:0.5rem">
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="pageValeurs() <= 1" (click)="chargerValeurs(pageValeurs() - 1)">Précédent</button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="pageValeurs() * tailleValeurs >= (synValeurs().total_filtre || 0)" (click)="chargerValeurs(pageValeurs() + 1)">Suivant</button>
                </span>
              </div>
            }
          </section>
        }

        @case ('criteres') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Critères de classification</h2><span class="bea-mg__count">{{ criteres().length }}</span></div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Code</th><th>Libellé</th><th>Source</th><th>Donnée</th><th>Décision</th><th>Statut</th></tr></thead>
                <tbody>
                  @for (c of criteres(); track c.code) {
                    <tr>
                      <td><code>{{ c.code }}</code></td>
                      <td>{{ c.libelle }}</td>
                      <td>{{ libSource(c.source) }}</td>
                      <td>{{ c.disponible }}</td>
                      <td>{{ c.type_decision }}</td>
                      <td><span class="bea-cl-badge" [attr.data-s]="c.statut">{{ statuts[c.statut] || c.statut }}</span></td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('divergences') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Divergences {{ matrice }} / {{ fiche }}</h2><span class="bea-mg__count">{{ nbDiv() }}</span></div>
            <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">Une divergence n’est jamais fusionnée : le critère reste « À arbitrer » et n’entre pas dans la somme du score.</p>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Domaine</th><th>Clé</th><th>{{ matrice }}</th><th>{{ fiche }}</th><th>Statut</th></tr></thead>
                <tbody>
                  @for (d of divergences(); track d.domaine + d.cle) {
                    <tr>
                      <td>{{ d.domaine }}</td>
                      <td>{{ d.cle }}</td>
                      <td>{{ d.valeur_a }}</td>
                      <td>{{ d.valeur_b }}</td>
                      <td><span class="bea-cl-badge" [attr.data-s]="d.statut">{{ statuts[d.statut] || d.statut }}</span></td>
                    </tr>
                  } @empty {
                    <tr><td colspan="5"><div class="bea-cl-empty">Aucune divergence chargée.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('versions') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Versions de règles</h2></div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>N°</th><th>Libellé</th><th>Mode</th><th>Statut</th></tr></thead>
                <tbody>
                  @for (v of versions(); track v.id) {
                    <tr>
                      <td>{{ v.numero }}</td>
                      <td>{{ v.libelle }}</td>
                      <td>{{ v.mode }}</td>
                      <td><span class="bea-cl-badge" [attr.data-s]="v.statut">{{ v.statut }}</span></td>
                    </tr>
                  } @empty {
                    <tr><td colspan="4"><div class="bea-cl-empty">Aucune version.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }
      }
    </div>
  `,
})
export class ClClassificationComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  readonly matrice = MATRICE_LBC;
  readonly fiche = FICHE_SCORING;
  readonly statuts = STATUTS_REGLE;
  readonly statutsRegle = Object.entries(STATUTS_REGLE);
  readonly libSource = libSource;
  readonly familles: Record<string, string> = {
    CLIENT: 'Client', GEOGRAPHIE: 'Géographie', PRODUIT_SERVICE_OPERATION: 'Produit / opération', CANAL: 'Canal',
  };
  readonly dimensions = [
    { code: 'CLIENT', libelle: 'Risque client' },
    { code: 'GEOGRAPHIE', libelle: 'Risque géographique' },
    { code: 'PRODUIT_SERVICE_OPERATION', libelle: 'Produit / service / opération' },
    { code: 'CANAL', libelle: 'Canal de distribution' },
  ];
  readonly items = signal<Item[]>([]);
  readonly total = signal(0);
  readonly versions = signal<Version[]>([]);
  readonly avertissement = signal('');
  readonly busy = signal(false);
  readonly criteres = signal<CritereMaitre[]>([]);
  readonly divergences = signal<Divergence[]>([]);
  readonly nbDiv = signal(0);
  readonly evaluation = signal<Evaluation | null>(null);
  readonly valeurs = signal<ValeurMaitre[]>([]);
  readonly synValeurs = signal<SyntheseValeurs>({});
  readonly pageValeurs = signal(1);
  readonly tailleValeurs = TAILLE_VALEURS;
  readonly onglet = signal<Onglet>('clients');
  readonly onglets: { code: Onglet; libelle: string; icon: string; compte: () => number | null }[] = [
    { code: 'clients', libelle: 'Clients classés', icon: 'verified_user', compte: () => this.total() },
    { code: 'simulation', libelle: 'Simulation', icon: 'calculate', compte: () => null },
    { code: 'referentiel', libelle: 'Référentiel maître', icon: 'table_view', compte: () => this.synValeurs().total ?? null },
    { code: 'criteres', libelle: 'Critères', icon: 'checklist', compte: () => this.criteres().length || null },
    { code: 'divergences', libelle: 'Divergences', icon: 'call_split', compte: () => this.nbDiv() || null },
    { code: 'versions', libelle: 'Versions', icon: 'history', compte: () => null },
  ];
  niveau = '';
  q = '';
  racineEval = '';
  dimension = '';
  statutValeur = '';
  pendingLignes: Record<string, unknown>[] | null = null;
  readonly hasUnsavedChanges = unsavedChanges(() => !!this.pendingLignes);
  readonly n = n;
  readonly dh = dateHeureFr;

  ngOnInit(): void {
    this.store.charger();
    const o = this.route.snapshot.queryParamMap.get('onglet') as Onglet | null;
    if (o && ONGLETS.includes(o)) this.onglet.set(o);
    this.api.get<{ versions: Version[]; avertissement: string }>(`${CL_BASE}/classification/referentiel`).subscribe({
      next: (r) => { this.versions.set(r.versions); this.avertissement.set(r.avertissement); },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Référentiel indisponible')),
    });
    this.charger();
    this.api.get<{ criteres: CritereMaitre[] }>(`${CL_BASE}/classification/matrice`).subscribe({
      next: (r) => this.criteres.set(r.criteres || []),
      error: () => this.criteres.set([]),
    });
    this.api.get<{ total: number; items: Divergence[] }>(`${CL_BASE}/classification/divergences`, { taille: 200 }).subscribe({
      next: (r) => { this.divergences.set(r.items || []); this.nbDiv.set(r.total || 0); },
      error: () => this.divergences.set([]),
    });
    this.chargerValeurs(1);
  }

  ouvrir(o: Onglet): void {
    this.onglet.set(o);
    void this.router.navigate([], { relativeTo: this.route, queryParams: { onglet: o === 'clients' ? null : o }, replaceUrl: true });
  }

  chargerValeurs(page: number): void {
    const params: Record<string, string | number> = { page, taille: TAILLE_VALEURS };
    if (this.dimension) params['dimension'] = this.dimension;
    if (this.statutValeur) params['statut'] = this.statutValeur;
    this.api.get<SyntheseValeurs & { items: ValeurMaitre[] }>(`${CL_BASE}/classification/valeurs`, params).subscribe({
      next: (r) => {
        this.valeurs.set(r.items || []);
        this.synValeurs.set({ total: r.total, total_filtre: r.total_filtre, nb_conflits: r.nb_conflits, nb_blocking: r.nb_blocking });
        this.pageValeurs.set(page);
      },
      error: () => this.valeurs.set([]),
    });
  }

  evaluer(): void {
    const racine = this.racineEval.trim().padStart(6, '0');
    if (!/^[0-9]{6}$/.test(racine)) {
      this.feedback.warning({ title: 'Racine invalide', message: 'Six chiffres.' });
      return;
    }
    this.feedback.run(() => this.api.post<Evaluation>(`${CL_BASE}/classification/evaluer`, { racine, persister: true }), {
      busy: this.busy, loading: 'Évaluation…',
      success: (e) => ({ title: 'Évaluation (simulation)', message: `Score ${e.score_total} — ${e.niveau_final || 'NON CLASSÉ'} (${e.coherence})` }),
      errorTitle: 'Évaluation refusée',
    }).subscribe((e) => this.evaluation.set(e));
  }

  backtest(): void {
    this.feedback.run(() => this.api.post<{ nb: number; compteurs: Record<string, number> }>(`${CL_BASE}/classification/backtest`, { limite: 50 }), {
      confirm: { action: 'validation', title: 'Backtest', message: 'Comparer le moteur à 50 classifications déjà stockées ?', hint: 'Aucune classe n’est écrasée. Copie de test uniquement.' },
      busy: this.busy, success: (r) => ({ title: 'Backtest', message: `${r.nb} client(s)`, details: Object.entries(r.compteurs || {}).slice(0, 8).map(([k, v]) => ({ label: k, value: String(v) })) }),
      errorTitle: 'Backtest refusé',
    }).subscribe();
  }

  charger(): void {
    const params: Record<string, string | number> = { taille: 80 };
    if (this.niveau) params['niveau'] = this.niveau;
    if (this.q) params['q'] = this.q;
    this.api.get<{ total: number; items: Item[] }>(`${CL_BASE}/classification`, params).subscribe({
      next: (p) => { this.items.set(p.items); this.total.set(p.total); },
      error: () => this.items.set([]),
    });
  }

  moteur(): void {
    this.feedback.run(() => this.api.post<{ modifies: number; manuels_preserves: number }>(`${CL_BASE}/classification/appliquer`, { forcer: false }), {
      confirm: { action: 'validation', title: 'Appliquer le moteur ACTIVE', message: 'Classer selon les règles de la version ACTIVE uniquement ?', hint: 'Les saisies manuelles sont conservées. La version ACTIVE est vide tant que la Conformité n’a pas validé.' },
      busy: this.busy, success: (r) => ({ title: 'Moteur exécuté', details: [
        { label: 'Modifiés', value: String(r.modifies) }, { label: 'Manuels préservés', value: String(r.manuels_preserves) },
      ] }), errorTitle: 'Moteur refusé',
    }).subscribe(() => this.charger());
  }

  modele(): void {
    this.api.download(`${CL_BASE}/classification/modele.xlsx`).subscribe({
      next: (b) => telecharger(b, 'modele-classification.xlsx'),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Modèle indisponible')),
    });
  }

  excel(input: HTMLInputElement): void {
    const f = input.files?.[0];
    input.value = '';
    if (!f) return;
    const fd = new FormData();
    fd.append('fichier', f);
    this.feedback.run(() => this.api.post<{ nb_valides: number; nb_rejets: number; lignes: Record<string, unknown>[] }>(`${CL_BASE}/classification/excel/analyse`, fd), {
      busy: this.busy, loading: 'Analyse…',
      success: (r) => ({ title: 'Analyse Excel', message: `${r.nb_valides} ligne(s) valide(s), ${r.nb_rejets} rejet(s)` }),
      errorTitle: 'Fichier refusé',
    }).subscribe((r) => {
      this.pendingLignes = r.lignes;
      if (!r.lignes.length) return;
      this.feedback.run(() => this.api.post<{ modifies: number }>(`${CL_BASE}/classification/excel/confirmer`, { lignes: r.lignes }), {
        confirm: { action: 'validation', title: 'Importer la classification', message: `Enregistrer ${r.nb_valides} classement(s) ?`, hint: 'La racine client n’est jamais modifiée.' },
        busy: this.busy, success: (x) => ({ title: 'Excel importé', message: `${x.modifies} client(s)` }),
        errorTitle: 'Import refusé',
      }).subscribe(() => { this.pendingLignes = null; this.charger(); });
    });
  }
}
