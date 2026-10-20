import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import {
  CL_BASE, FICHE_SCORING, MATRICE_LBC, MODES_DECISION, STATUTS_REGLE, TraceClassification, dateHeureFr, libSource, n,
} from '../clientele.models';
import { ClienteleStore } from '../clientele.store';
import { ClClasserClientComponent } from './cl-classer-client.component';
import { ClClasserComponent } from './cl-classer.component';
import { ClAnalystesComponent } from './cl-analystes.component';
import { ClClassifHistoriqueComponent } from './cl-classif-historique.component';
import { ClClassifManuellesComponent } from './cl-classif-manuelles.component';
import { ClClassifResultatsComponent } from './cl-classif-resultats.component';
import { ClJournalClientsComponent } from './cl-journal-clients.component';

interface Item {
  racine_client: string; raison_sociale: string; niveau: string; source: string;
  motif_risque: string | null; motif_classement: string | null; classifie_le: string | null;
}
interface Version { id: string; numero: number; libelle: string; statut: string; mode: string; }
interface CritereMaitre {
  code: string; libelle: string; source: string; disponible: string;
  utilisable_auto: boolean; type_decision: string; statut: string;
}
interface Divergence {
  id?: string; domaine: string; cle: string; source_a: string; valeur_a: string; source_b: string; valeur_b: string;
  statut: string; decision?: string | null;
}
interface DecisionDivergence {
  ancien_statut: string | null; nouveau_statut: string; decision: string | null; justification: string;
  utilisateur: string | null; date: string | null;
}
interface Reexamen {
  id: string; racine_client: string; raison_sociale: string; origine: string; lot_id: string | null; ligne_source: number | null;
  niveau_actuel: string | null; source_actuelle: string | null; niveau_suggere: string; source_suggestion: string;
  motif: string; statut: string; created_at: string | null;
}
type Actuelle = { niveau: string; source: string; classifie_le: string | null } & Partial<TraceClassification>;
interface LigneEval {
  critere: string; libelle: string; famille?: string; etat: string; valeur: string | null; poids: number | null;
  niveau_matrice: string | null; niveau_v4: string | null; motif: string; divergence: boolean;
  blocking_propose: boolean; contribue_au_score?: boolean;
}
interface Evaluation {
  racine_client: string; score_total: number; niveau_final: string | null; niveau_score: string | null;
  niveau_max: string | null; statut: string; coherence: string; motif_principal: string | null;
  admissible?: boolean; date_reference?: string | null; source_date_reference?: string | null;
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

type Onglet = 'classer' | 'resultats' | 'manuelles' | 'historique' | 'analystes' | 'clients' | 'reexamens' | 'journal'
  | 'simulation' | 'referentiel' | 'criteres' | 'divergences' | 'versions' | 'masse';
const ONGLETS: readonly Onglet[] = [
  'classer', 'resultats', 'manuelles', 'historique', 'analystes', 'clients', 'reexamens', 'journal',
  'simulation', 'referentiel', 'criteres', 'divergences', 'versions', 'masse',
];
/** Écrans ouverts directement depuis le menu latéral : pas de barre d'onglets, titre propre. */
const PAGES_MENU: Partial<Record<Onglet, { titre: string; sous: string }>> = {
  resultats: { titre: 'Résultats du moteur', sous: 'Dernier calcul du moteur par client, à côté de la classe retenue. Un écart est signalé, jamais appliqué automatiquement.' },
  manuelles: { titre: 'Décisions manuelles', sous: 'Classes retenues par décision motivée : ni l’import ni le moteur ne les remplacent.' },
  historique: { titre: 'Historique des classifications', sous: 'Tous les changements de classe, en ajout seul : ancienne et nouvelle classe, motif, analyste, auteur, date.' },
  analystes: { titre: 'Analystes KYC', sous: 'Référentiel des analystes reconnus dans l’import hebdomadaire et les décisions de classification.' },
};
const ENTETE_DEFAUT = {
  titre: 'Classification individuelle',
  sous: 'Classer un client, consulter les clients classés, les réexamens et le journal. Au niveau CLIENT (racine 6 chiffres), jamais RIB.',
};
const PARAMETRAGE: readonly Onglet[] = ['simulation', 'referentiel', 'criteres', 'divergences', 'versions', 'masse'];
const STATUTS_DIVERGENCE: Record<string, string> = {
  A_ARBITRER: 'À arbitrer', VALIDEE: 'Validée', INVALIDE_SOURCE: 'Source invalidée', ALIGNEE: 'Alignée',
};
const TAILLE_VALEURS = 80;

@Component({
  selector: 'bea-cl-classification',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule, RouterLink, MatIconModule, ClienteleUiComponent, ClClasserComponent, ClClasserClientComponent,
    ClJournalClientsComponent, ClClassifResultatsComponent, ClClassifManuellesComponent, ClClassifHistoriqueComponent,
    ClAnalystesComponent,
  ],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl bea-cl--large">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Classification</p>
          <h1>{{ entete().titre }}</h1>
          <p class="bea-cl-head__sub">{{ entete().sous }}</p>
        </div>
        @if (store.cap().classif_voir && !pageMenu()) {
          <div class="bea-mg__actions">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [class.is-on]="parametrage()" (click)="basculerParametrage()">
              <mat-icon>tune</mat-icon> {{ parametrage() ? 'Retour au module' : 'Paramétrage Conformité' }}
            </button>
          </div>
        }
      </header>

      @if (!pageMenu()) {
        <nav class="bea-cl-tabs" role="tablist" aria-label="Classification">
          @for (o of ongletsVisibles(); track o.code) {
            <button type="button" role="tab" [class.is-on]="onglet() === o.code" [attr.aria-selected]="onglet() === o.code" (click)="ouvrir(o.code)">
              <mat-icon>{{ o.icon }}</mat-icon>{{ o.libelle }}
              @if (o.compte(); as c) { <span class="bea-cl-tabs__n">{{ n(c) }}</span> }
            </button>
          }
        </nav>
      }

      @switch (onglet()) {
        @case ('classer') {
          <bea-cl-classer-client />
        }
        @case ('resultats') {
          <bea-cl-classif-resultats />
        }
        @case ('manuelles') {
          <bea-cl-classif-manuelles />
        }
        @case ('historique') {
          <bea-cl-classif-historique />
        }
        @case ('analystes') {
          <bea-cl-analystes />
        }
        @case ('journal') {
          <bea-cl-journal-clients />
        }
        @case ('masse') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Classification massive (moteur)</h2></div>
            <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">Traitement global verrouillé : il ne s’exécute qu’après autorisation explicite de la Conformité. Les décisions manuelles ne sont jamais remplacées.</p>
            @if (store.cap().classif_executer) {
              <bea-cl-classer (termine)="classementTermine()" />
            }
          </section>
        }
        @case ('clients') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Clients classés</h2>
            </div>
            <div class="bea-cl-filters">
              <label>Niveau
                <select [(ngModel)]="niveau" (ngModelChange)="charger(1)">
                  <option value="">Tous</option>
                  <option>FAIBLE</option><option>MOYEN</option><option>ELEVE</option><option>INTERDIT</option>
                </select>
              </label>
              <label>Recherche
                <input [(ngModel)]="q" (keyup.enter)="charger(1)" placeholder="Racine ou nom" />
              </label>
              <label>Par page
                <select [ngModel]="taille()" (ngModelChange)="taille.set($event); charger(1)">
                  @for (t of tailles; track t) { <option [ngValue]="t">{{ t }}</option> }
                </select>
              </label>
            </div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th class="c-sm">Racine</th><th class="c-lg">Nom</th><th class="c-sm">Niveau</th><th class="c-sm">Source</th><th class="c-xl">Motifs</th><th class="c-date">Le</th></tr></thead>
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
                    <tr><td colspan="6"><div class="bea-cl-empty">Aucun client classé. Classez un client depuis sa fiche ou décidez les propositions de l’import hebdomadaire.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
            @if (total() > 0) {
              <div class="bea-cl-pager">
                <span>{{ n(debut()) }}–{{ n(fin()) }} sur {{ n(total()) }} client(s) · page {{ page() }} / {{ n(nbPages()) }}</span>
                <span class="bea-cl-pager__btns">
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="charger(1)" title="Première page"><mat-icon>first_page</mat-icon></button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="charger(page() - 1)"><mat-icon>chevron_left</mat-icon> Précédent</button>
                  <label class="bea-cl-pager__aller">Page
                    <input type="number" min="1" [max]="nbPages()" [ngModel]="page()" (keyup.enter)="allerPage($any($event.target).value)" (change)="allerPage($any($event.target).value)" />
                  </label>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= nbPages()" (click)="charger(page() + 1)">Suivant <mat-icon>chevron_right</mat-icon></button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= nbPages()" (click)="charger(nbPages())" title="Dernière page"><mat-icon>last_page</mat-icon></button>
                </span>
              </div>
            }
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
            <p class="bea-cl-hint" style="padding:0 1.1rem">Simulation : rien n’est écrit (ni évaluation, ni classification). Comparaison entre la classification retenue et le niveau proposé.</p>
            <div class="bea-cl-filters" style="align-items:flex-end">
              <label>Racine client (6 chiffres)
                <input [(ngModel)]="racineEval" maxlength="6" inputmode="numeric" placeholder="000001" (keyup.enter)="evaluer()" />
              </label>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" style="padding:0.55rem 1.2rem;font-weight:700" (click)="evaluer()" [disabled]="busy() || !racineEval.trim()">
                <mat-icon>calculate</mat-icon> Calculer le score
              </button>
            </div>
            @if (evaluation(); as e) {
              @let c = actuelle();
              <div class="bea-cl-stats">
                <div class="bea-cl-stat"><span>Classification retenue</span><strong>{{ c?.niveau || 'Non classé' }}</strong>
                  @if (c) { <small class="bea-cl-hint">{{ modes[c.mode_decision || ''] || c.source }} · {{ dh(c.classifie_le) }}</small> }
                </div>
                <div class="bea-cl-stat" [attr.data-tone]="e.admissible ? 'ok' : 'warn'"><span>Niveau proposé</span><strong>{{ e.niveau_final || 'NON CLASSÉ' }}</strong>
                  <small class="bea-cl-hint">{{ e.admissible ? 'admissible' : 'non admissible' }}</small>
                </div>
                <div class="bea-cl-stat" [attr.data-tone]="c && e.admissible && c.niveau !== e.niveau_final ? 'danger' : ''"><span>Écart</span>
                  <strong>{{ !c ? '—' : !e.admissible ? 'Non comparable' : c.niveau === e.niveau_final ? 'Aucun' : c.niveau + ' → ' + e.niveau_final }}</strong>
                </div>
              </div>
              <dl class="bea-cl-dl">
                <dt>Score</dt><dd>{{ n(e.score_total) }}</dd>
                <dt>Date de référence</dt><dd>{{ e.date_reference || '—' }} <small class="bea-cl-hint">{{ e.source_date_reference }}</small></dd>
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
                <thead><tr><th>Domaine</th><th>Clé</th><th>{{ matrice }}</th><th>{{ fiche }}</th><th>Statut</th><th>Décision</th><th></th></tr></thead>
                <tbody>
                  @for (d of divergences(); track d.domaine + d.cle) {
                    <tr>
                      <td>{{ d.domaine }}</td>
                      <td>{{ d.cle }}</td>
                      <td>{{ d.valeur_a }}</td>
                      <td>{{ d.valeur_b }}</td>
                      <td><span class="bea-cl-badge" [attr.data-s]="d.statut">{{ statuts[d.statut] || statutsDiv[d.statut] || d.statut }}</span></td>
                      <td style="max-width:22rem">{{ d.decision || '—' }}</td>
                      <td>
                        @if (d.id) {
                          <span style="display:flex;gap:0.3rem;align-items:center">
                            @if (store.cap().classif_arbitrer) {
                              <select [(ngModel)]="choixDiv[d.id]" style="font:inherit">
                                @for (s of statutsDivListe; track s[0]) { <option [ngValue]="s[0]">{{ s[1] }}</option> }
                              </select>
                              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="arbitrer(d)" [disabled]="busy()">Arbitrer</button>
                            }
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="histoDivergence(d)">Historique</button>
                          </span>
                        }
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="7"><div class="bea-cl-empty">Aucune divergence chargée.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
            @if (histoDiv(); as h) {
              <div class="bea-mg__panel-top"><h2>Historique — {{ h.libelle }}</h2></div>
              <ul class="bea-cl-anoms">
                @for (x of h.decisions; track $index) {
                  <li><mat-icon>history</mat-icon>{{ dh(x.date) }} · {{ x.utilisateur || '—' }} : {{ statutsDiv[x.ancien_statut || ''] || x.ancien_statut }} → {{ statutsDiv[x.nouveau_statut] || x.nouveau_statut }} — {{ x.justification }}@if (x.decision) { ({{ x.decision }})}</li>
                } @empty {
                  <li>Aucune décision enregistrée.</li>
                }
              </ul>
            }
            <p class="bea-cl-hint" style="padding:0.6rem 1.1rem">L’arbitrage est historisé (auteur, date, justification). Le moteur lit encore le référentiel versionné : une divergence arbitrée n’est appliquée au score qu’après publication d’une nouvelle version des règles.</p>
          </section>
        }

        @case ('reexamens') {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Réexamens ouverts</h2><span class="bea-mg__count">{{ nbReex() }}</span></div>
            <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">Ouverts lorsqu’un import ou le moteur propose un niveau différent d’une décision manuelle : la décision manuelle n’est jamais remplacée silencieusement.</p>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th class="c-date">Ouvert le</th><th class="c-sm">Racine</th><th class="c-lg">Nom</th><th class="c-sm">Actuel</th><th class="c-sm">Suggéré</th><th class="c-sm">Origine</th><th class="c-xl">Motif</th><th class="c-act"></th></tr></thead>
                <tbody>
                  @for (r of reexamens(); track r.id) {
                    <tr>
                      <td>{{ dh(r.created_at) }}</td>
                      <td><a [routerLink]="['/clientele/clients', r.racine_client]"><code>{{ r.racine_client }}</code></a></td>
                      <td>{{ r.raison_sociale }}</td>
                      <td><span class="bea-cl-badge" [attr.data-s]="r.niveau_actuel">{{ r.niveau_actuel || '—' }}</span> <small class="bea-cl-hint">{{ r.source_actuelle }}</small></td>
                      <td><span class="bea-cl-badge" [attr.data-s]="r.niveau_suggere">{{ r.niveau_suggere }}</span> <small class="bea-cl-hint">{{ r.source_suggestion }}</small></td>
                      <td>{{ r.origine }}@if (r.ligne_source) { · L{{ r.ligne_source }}}</td>
                      <td style="max-width:26rem">{{ r.motif }}</td>
                      <td>
                        @if (store.cap().classif_arbitrer) {
                          <span style="display:flex;gap:0.3rem">
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="traiter(r, false)" [disabled]="busy()">Conserver {{ r.niveau_actuel }}</button>
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="traiter(r, true)" [disabled]="busy()">Retenir {{ r.niveau_suggere }}</button>
                          </span>
                        }
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="8"><div class="bea-cl-empty">Aucun réexamen ouvert.</div></td></tr>
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
  private readonly destroyRef = inject(DestroyRef);
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
  readonly page = signal(1);
  readonly tailles = [50, 100, 200];
  readonly taille = signal(100);
  readonly nbPages = computed(() => Math.max(1, Math.ceil(this.total() / this.taille())));
  readonly debut = computed(() => (this.total() ? (this.page() - 1) * this.taille() + 1 : 0));
  readonly fin = computed(() => Math.min(this.page() * this.taille(), this.total()));
  readonly versions = signal<Version[]>([]);
  readonly avertissement = signal('');
  readonly busy = signal(false);
  readonly criteres = signal<CritereMaitre[]>([]);
  readonly divergences = signal<Divergence[]>([]);
  readonly nbDiv = signal(0);
  readonly evaluation = signal<Evaluation | null>(null);
  readonly actuelle = signal<Actuelle | null>(null);
  readonly histoDiv = signal<{ libelle: string; decisions: DecisionDivergence[] } | null>(null);
  readonly reexamens = signal<Reexamen[]>([]);
  readonly nbReex = signal(0);
  readonly modes = MODES_DECISION;
  readonly statutsDiv = STATUTS_DIVERGENCE;
  readonly statutsDivListe = Object.entries(STATUTS_DIVERGENCE);
  choixDiv: Record<string, string> = {};
  readonly valeurs = signal<ValeurMaitre[]>([]);
  readonly synValeurs = signal<SyntheseValeurs>({});
  readonly pageValeurs = signal(1);
  readonly tailleValeurs = TAILLE_VALEURS;
  readonly onglet = signal<Onglet>('classer');
  readonly parametrage = signal(false);
  readonly onglets: { code: Onglet; libelle: string; icon: string; compte: () => number | null }[] = [
    { code: 'classer', libelle: 'Classer un client', icon: 'person_search', compte: () => null },
    { code: 'clients', libelle: 'Clients classés', icon: 'verified_user', compte: () => this.total() },
    { code: 'reexamens', libelle: 'Réexamens', icon: 'pending_actions', compte: () => this.nbReex() || null },
    { code: 'journal', libelle: 'Journal', icon: 'history_edu', compte: () => null },
    { code: 'simulation', libelle: 'Simulation', icon: 'calculate', compte: () => null },
    { code: 'referentiel', libelle: 'Référentiel maître', icon: 'table_view', compte: () => this.synValeurs().total ?? null },
    { code: 'criteres', libelle: 'Critères', icon: 'checklist', compte: () => this.criteres().length || null },
    { code: 'divergences', libelle: 'Divergences', icon: 'call_split', compte: () => this.nbDiv() || null },
    { code: 'versions', libelle: 'Versions', icon: 'history', compte: () => null },
    { code: 'masse', libelle: 'Classification massive', icon: 'lock', compte: () => null },
  ];
  readonly pageMenu = computed(() => PAGES_MENU[this.onglet()] ?? null);
  readonly entete = computed(() =>
    this.pageMenu() ?? (this.parametrage() ? { titre: 'Paramétrage Conformité', sous: 'Simulation, référentiel maître, critères, divergences, versions et classification massive.' } : ENTETE_DEFAUT));
  readonly ongletsVisibles = computed(() =>
    this.onglets.filter((o) => PARAMETRAGE.includes(o.code) === this.parametrage()));
  niveau = '';
  q = '';
  racineEval = '';
  dimension = '';
  statutValeur = '';
  readonly n = n;
  readonly dh = dateHeureFr;

  ngOnInit(): void {
    this.store.charger();
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((qp) => {
      const o = qp.get('onglet');
      if (o === 'import') {
        void this.router.navigate(['/clientele/classification-lot'], { replaceUrl: true });
        return;
      }
      const cible = o && ONGLETS.includes(o as Onglet) ? (o as Onglet) : 'classer';
      this.onglet.set(cible);
      this.parametrage.set(PARAMETRAGE.includes(cible));
    });
    this.api.get<{ versions: Version[]; avertissement: string }>(`${CL_BASE}/classification/referentiel`).subscribe({
      next: (r) => { this.versions.set(r.versions); this.avertissement.set(r.avertissement); },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Référentiel indisponible')),
    });
    this.charger();
    this.api.get<{ criteres: CritereMaitre[] }>(`${CL_BASE}/classification/matrice`).subscribe({
      next: (r) => this.criteres.set(r.criteres || []),
      error: () => this.criteres.set([]),
    });
    this.chargerDivergences();
    this.chargerReexamens();
    this.chargerValeurs(1);
  }

  chargerDivergences(): void {
    this.api.get<{ total: number; items: Divergence[] }>(`${CL_BASE}/classification/divergences`, { taille: 200 }).subscribe({
      next: (r) => {
        const items = r.items || [];
        this.choixDiv = Object.fromEntries(items.filter((d) => d.id).map((d) => [d.id!, d.statut === 'A_ARBITRER' ? 'VALIDEE' : d.statut]));
        this.divergences.set(items);
        this.nbDiv.set(r.total || 0);
      },
      error: () => this.divergences.set([]),
    });
  }

  chargerReexamens(): void {
    this.api.get<{ total: number; items: Reexamen[] }>(`${CL_BASE}/classification/reexamens`, { statut: 'OUVERT', taille: 200 }).subscribe({
      next: (r) => { this.reexamens.set(r.items || []); this.nbReex.set(r.total || 0); },
      error: () => this.reexamens.set([]),
    });
  }

  arbitrer(d: Divergence): void {
    const statut = this.choixDiv[d.id!] || 'VALIDEE';
    this.feedback.runWithReason(
      (justification) => this.api.post<{ decisions: DecisionDivergence[] }>(`${CL_BASE}/classification/divergences/${d.id}/arbitrer`, { statut, justification }),
      {
        reason: {
          title: 'Arbitrer la divergence',
          message: `${d.domaine} « ${d.cle} » : ${this.matrice} = ${d.valeur_a}, ${this.fiche} = ${d.valeur_b}. Nouveau statut : ${STATUTS_DIVERGENCE[statut]} ?`,
          hint: 'Décision historisée (auteur, date, justification).',
          reasonLabel: 'Justification', maxLength: 2000, confirmLabel: 'Arbitrer', tone: 'primary',
        },
        busy: this.busy, loading: 'Arbitrage…', success: { title: 'Divergence arbitrée', message: STATUTS_DIVERGENCE[statut] },
        errorTitle: 'Arbitrage refusé', retry: false,
      },
    ).subscribe((r) => {
      this.histoDiv.set({ libelle: `${d.domaine} « ${d.cle} »`, decisions: r.decisions });
      this.chargerDivergences();
    });
  }

  histoDivergence(d: Divergence): void {
    this.api.get<{ decisions: DecisionDivergence[] }>(`${CL_BASE}/classification/divergences/${d.id}/historique`).subscribe({
      next: (r) => this.histoDiv.set({ libelle: `${d.domaine} « ${d.cle} »`, decisions: r.decisions }),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Historique indisponible')),
    });
  }

  traiter(r: Reexamen, appliquer: boolean): void {
    const niveau = appliquer ? r.niveau_suggere : null;
    this.feedback.runWithReason(
      (decision) => this.api.post(`${CL_BASE}/classification/reexamens/${r.id}/traiter`, { decision, niveau }),
      {
        reason: {
          title: 'Traiter le réexamen',
          message: appliquer
            ? `Retenir ${r.niveau_suggere} (${r.source_suggestion}) pour ${r.racine_client} à la place de ${r.niveau_actuel} ?`
            : `Conserver ${r.niveau_actuel} pour ${r.racine_client} ?`,
          hint: appliquer ? 'Enregistré comme décision manuelle motivée (historique conservé).' : 'Le réexamen est clos, la décision manuelle est conservée.',
          reasonLabel: 'Motif de la décision', maxLength: 2000, confirmLabel: appliquer ? 'Retenir' : 'Conserver', tone: 'primary',
        },
        busy: this.busy, loading: 'Enregistrement…', success: { title: 'Réexamen traité' },
        errorTitle: 'Décision refusée', retry: false,
      },
    ).subscribe(() => { this.chargerReexamens(); this.charger(); });
  }

  ouvrir(o: Onglet): void {
    this.onglet.set(o);
    void this.router.navigate([], { relativeTo: this.route, queryParams: { onglet: o }, replaceUrl: true });
  }

  basculerParametrage(): void {
    const on = !this.parametrage();
    this.parametrage.set(on);
    this.ouvrir(on ? 'simulation' : 'classer');
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
    this.feedback.run(() => this.api.post<Evaluation>(`${CL_BASE}/classification/evaluer`, { racine, persister: false }), {
      busy: this.busy, loading: 'Évaluation…',
      success: (e) => ({ title: 'Évaluation (simulation)', message: `Score ${e.score_total} — ${e.niveau_final || 'NON CLASSÉ'} (${e.coherence})` }),
      errorTitle: 'Évaluation refusée',
    }).subscribe((e) => {
      this.evaluation.set(e);
      this.actuelle.set(null);
      this.api.get<{ classification: Actuelle | null }>(`${CL_BASE}/clients/${racine}/classification`).subscribe({
        next: (r) => this.actuelle.set(r.classification),
        error: () => this.actuelle.set(null),
      });
    });
  }

  backtest(): void {
    this.feedback.run(() => this.api.post<{ nb: number; compteurs: Record<string, number> }>(`${CL_BASE}/classification/backtest`, { limite: 50 }), {
      confirm: { action: 'validation', title: 'Backtest', message: 'Comparer le moteur à 50 classifications déjà stockées ?', hint: 'Aucune classe n’est écrasée. Copie de test uniquement.' },
      busy: this.busy, success: (r) => ({ title: 'Backtest', message: `${r.nb} client(s)`, details: Object.entries(r.compteurs || {}).slice(0, 8).map(([k, v]) => ({ label: k, value: String(v) })) }),
      errorTitle: 'Backtest refusé',
    }).subscribe();
  }

  charger(page = this.page()): void {
    const params: Record<string, string | number> = { page: Math.max(1, page), taille: this.taille() };
    if (this.niveau) params['niveau'] = this.niveau;
    if (this.q) params['q'] = this.q;
    this.api.get<{ total: number; items: Item[] }>(`${CL_BASE}/classification`, params).subscribe({
      next: (p) => {
        this.items.set(p.items);
        this.total.set(p.total);
        this.page.set(Math.max(1, page));
        document.querySelector('.bea-cl .bea-mg__table-wrap')?.scrollTo({ top: 0 });
      },
      error: () => this.items.set([]),
    });
  }

  allerPage(valeur: string | number): void {
    const p = Math.trunc(Number(valeur));
    if (!Number.isFinite(p)) return;
    const cible = Math.min(Math.max(1, p), this.nbPages());
    if (cible !== this.page()) this.charger(cible);
  }

  classementTermine(): void {
    this.charger(1);
    this.chargerReexamens();
    this.store.charger(true);
  }
}
