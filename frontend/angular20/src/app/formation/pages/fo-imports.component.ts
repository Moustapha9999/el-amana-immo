import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { FormationUiComponent } from '../formation-ui.component';
import {
  AnalyseImport, DOMAINES, Domaine, FO_BASE, ImportFormation, PersonneImport, ValeurImport, correspond, dateFr, dateHeureFr,
} from '../formation.models';
import { FormationStore } from '../formation.store';

type DomImport = Domaine | 'ENTITE';
type Mode = 'COLONNES' | 'MAJUSCULES' | 'PRENOM_NOM' | 'NOM_PRENOM' | 'NOM_COMPLET';

interface Decision {
  action: 'MAPPER' | 'CREER' | 'IGNORER';
  cible_id: string;
  libelle: string;
  perimetre_id: string;
}

interface ChoixPersonne {
  action: 'NOUVEAU' | 'EXISTANT';
  employe_id: string;
  nom: string;
  prenom: string;
  modifie: boolean;
}

const DOMS: DomImport[] = ['THEME', 'LIEU', 'FORMATEUR', 'FONCTION', 'ENTITE'];
const MODES: { code: Mode; label: string }[] = [
  { code: 'COLONNES', label: 'Colonnes Nom / Prénom du fichier' },
  { code: 'MAJUSCULES', label: 'Mots en MAJUSCULES = nom' },
  { code: 'PRENOM_NOM', label: 'Prénom(s) puis Nom (dernier mot = nom)' },
  { code: 'NOM_PRENOM', label: 'Nom puis Prénom(s) (premier mot = nom)' },
  { code: 'NOM_COMPLET', label: 'Tout dans le nom (prénom vide)' },
];
const RESULTATS: Record<string, string> = {
  sessions_creees: 'Formations créées', sessions_fusionnees: 'Formations complétées', participations_creees: 'Participations créées',
  participations_existantes: 'Participations déjà présentes', employes_crees: 'Employés créés', employes_existants: 'Employés rapprochés',
  sessions_ignorees: 'Formations ignorées', crees_theme: 'Thèmes créés', crees_lieu: 'Lieux créés', crees_formateur: 'Formateurs créés',
  crees_fonction: 'Fonctions créées', crees_entite: 'Entités créées',
};

function decouper(p: PersonneImport, mode: Mode): { nom: string; prenom: string } {
  const mots = p.mots.length ? p.mots : p.brut.split(/\s+/);
  if (mode === 'COLONNES' && (p.nom_colonne || p.prenom_colonne)) return { nom: p.nom_colonne ?? '', prenom: p.prenom_colonne ?? '' };
  if (mode === 'MAJUSCULES') {
    const maj = mots.filter((m) => m.length > 1 && m === m.toUpperCase() && /[A-Z]/.test(m));
    if (maj.length && maj.length < mots.length) return { nom: maj.join(' '), prenom: mots.filter((m) => !maj.includes(m)).join(' ') };
  }
  if (mots.length < 2 || mode === 'NOM_COMPLET') return { nom: mots.join(' '), prenom: '' };
  if (mode === 'NOM_PRENOM') return { nom: mots[0]!, prenom: mots.slice(1).join(' ') };
  return { nom: mots[mots.length - 1]!, prenom: mots.slice(0, -1).join(' ') };
}

@Component({
  selector: 'bea-fo-imports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, FormationUiComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <p class="bea-stock-page__kicker">Formation &amp; Sensibilisation</p>
          <h1>Import Excel</h1>
          <p class="bea-fo-head__sub">Reprise du fichier de suivi : analyse, aperçu, corrections puis confirmation. Rien n’est enregistré avant la confirmation finale.</p>
        </div>
        @if (imp()) {
          <div class="bea-mg__actions">
            @if (imp()!.statut === 'ANALYSE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="abandonner()" [disabled]="busy()"><mat-icon>close</mat-icon> Abandonner</button>
            } @else {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()"><mat-icon>upload_file</mat-icon> Nouvel import</button>
            }
          </div>
        }
      </header>

      @if (!imp()) {
        @if (store.cap().imports_executer) {
          <section class="bea-mg__panel bea-fo-pad">
            <label class="bea-fx-dropzone" [class.is-over]="survol()" (dragover)="$event.preventDefault(); survol.set(true)" (dragleave)="survol.set(false)" (drop)="deposer($event)">
              <input type="file" accept=".xlsx,.xlsm" hidden (change)="choisirFichier($any($event.target))" />
              @if (busy()) {
                <mat-icon class="bea-fo-spin">progress_activity</mat-icon><strong>Analyse du fichier…</strong>
              } @else {
                <mat-icon>upload_file</mat-icon>
                <strong>Déposez le fichier Excel de suivi des formations</strong>
                <span>ou cliquez pour le sélectionner — .xlsx, 10 Mo maximum</span>
                <span class="bea-fo-hint">Colonnes reconnues : Date, Thème, Lieu, Formateur, Nom et prénom (ou Nom / Prénom), Fonction, Entité, Périmètre, Présence.</span>
              }
            </label>
          </section>
        }
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Historique des imports</h2><span class="bea-mg__count">{{ historique().length }}</span></div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-fo-table">
              <thead><tr><th>Fichier</th><th>Analysé le</th><th>Par</th><th class="is-num">Lignes</th><th>Résultat</th><th>Statut</th></tr></thead>
              <tbody>
                @for (h of historique(); track h.id; let i = $index) {
                  <tr class="is-click bea-fx-row-in" [style.--i]="i" (click)="reprendre(h)">
                    <td><strong>{{ h.fichier_nom }}</strong></td>
                    <td>{{ dh(h.created_at) }}</td>
                    <td>{{ h.auteur || '—' }}</td>
                    <td class="is-num">{{ h.nb_lignes }}</td>
                    <td>@if (h.resultat) { {{ h.resultat['sessions_creees'] || 0 }} formation(s), {{ h.resultat['participations_creees'] || 0 }} participation(s) } @else { — }</td>
                    <td><span class="bea-fo-badge" [attr.data-s]="h.statut">{{ libStatut[h.statut] }}</span></td>
                  </tr>
                } @empty {
                  <tr><td colspan="6"><div class="bea-fo-empty"><mat-icon>history</mat-icon>Aucun import.</div></td></tr>
                }
              </tbody>
            </table>
          </div>
        </section>
      } @else {
        @let a = analyse()!;
        <ol class="bea-fo-steps">
          @for (e of etapes; track e; let i = $index) {
            <li [class.is-on]="etape() === i" [class.is-done]="etape() > i" (click)="etape() > i && imp()!.statut === 'ANALYSE' && etape.set(i)">{{ e }}</li>
          }
        </ol>

        @if (etape() === 0) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><div><h2>{{ a.fichier }}</h2><p class="bea-fo-panel-sub">Feuille « {{ a.feuille }} », en-têtes ligne {{ a.ligne_entete }}</p></div></div>
            <div class="bea-fo-stats">
              @for (s of statsAffichees(); track s.label; let i = $index) {
                <div class="bea-fo-stat" [style.--i]="i" [attr.data-tone]="s.tone"><span>{{ s.label }}</span><strong>{{ s.valeur }}</strong></div>
              }
            </div>
            @if (a.deja_importe) {
              <div class="bea-fo-note" style="margin:0 1.1rem 1rem"><mat-icon>content_copy</mat-icon>
                <span>Ce fichier a déjà été importé le {{ dh(a.deja_importe.le) }}. Un nouvel import ne duplique pas les participations existantes.</span></div>
            }
          </section>
          <div class="bea-fo-grid bea-fo-grid--2">
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Colonnes reconnues</h2></div>
              <ul class="bea-fo-anoms">
                @for (c of a.colonnes; track c.champ) { <li data-n="info"><mat-icon>check_circle</mat-icon><span><b>{{ c.libelle }}</b> ← « {{ c.entete }} »</span></li> }
                @for (c of a.colonnes_ignorees; track c) { <li><mat-icon>remove_circle_outline</mat-icon><span>« {{ c }} » ignorée</span></li> }
                @if (!a.presence_colonne) { <li data-n="alerte"><mat-icon>info</mat-icon><span>Pas de colonne Présence : les participants des formations passées sont considérés PRÉSENTS (fichier de suivi des formations suivies).</span></li> }
              </ul>
            </section>
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Anomalies</h2>
                <div class="bea-fo-panel-top-actions">
                  @for (n of niveaux; track n.code) {
                    <button type="button" class="bea-fx-chip" [class.is-active]="niveau() === n.code" (click)="niveau.set(n.code)">{{ n.label }} <strong>{{ compteNiveau(n.code) }}</strong></button>
                  }
                </div>
              </div>
              <ul class="bea-fo-anoms">
                @for (x of anomalies(); track $index) {
                  <li [attr.data-n]="x.niveau"><mat-icon>{{ x.niveau === 'bloquant' ? 'block' : x.niveau === 'alerte' ? 'warning' : 'info' }}</mat-icon>
                    <span>@if (x.ligne) {<b>Ligne {{ x.ligne }} :</b> }{{ x.message }}</span></li>
                } @empty {
                  <li data-n="info"><mat-icon>check</mat-icon><span>Aucune anomalie.</span></li>
                }
              </ul>
              @if (compteNiveau('bloquant')) {
                <p class="bea-fo-hint" style="padding:0 1.1rem 0.9rem">Les lignes bloquantes ne seront pas importées. Corrigez-les dans le fichier puis relancez l’analyse si nécessaire.</p>
              }
            </section>
          </div>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Aperçu des formations détectées</h2><span class="bea-mg__count">{{ a.sessions.length }}</span></div>
            <div class="bea-mg__table-wrap" style="max-height:24rem">
              <table class="bea-mg__table bea-fo-table">
                <thead><tr><th>Date</th><th>Thème(s)</th><th>Lieu</th><th>Formateur(s)</th><th class="is-num">Participants</th></tr></thead>
                <tbody>
                  @for (s of a.sessions; track s.cle) {
                    <tr><td>{{ dateFr(s.date) }}</td><td>{{ s.themes.join(', ') }}</td><td>{{ s.lieu }}</td><td>{{ s.formateurs.join(' / ') || '—' }}</td><td class="is-num">{{ s.nb_participants }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @if (etape() === 1) {
          <div class="bea-fo-note bea-fo-note--info"><mat-icon>rule</mat-icon>
            <span>Chaque valeur du fichier est rapprochée d’un référentiel. <strong>Associer</strong> = valeur existante, <strong>Créer</strong> = nouvelle valeur au référentiel, <strong>Ignorer</strong> = non reprise. Les rapprochements approximatifs sont signalés « à vérifier ».</span></div>
          <nav class="bea-ct-tabs" style="margin-bottom:0.9rem">
            @for (d of doms; track d) {
              <button type="button" [class.is-on]="domaine() === d" (click)="domaine.set(d)">{{ libDom(d) }} <span class="bea-fx-count">{{ a.valeurs[d]?.length ?? 0 }}</span>
                @if (aVerifier(d)) { <span class="bea-fo-score is-mid" style="margin-left:0.3rem">{{ aVerifier(d) }}</span> }</button>
            }
          </nav>
          <section class="bea-mg__panel">
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table bea-fo-table">
                <thead><tr><th>Valeur du fichier</th><th class="is-num">Lignes</th><th>Similarité</th><th style="width:9rem">Action</th><th>Valeur retenue</th>@if (domaine() === 'ENTITE') {<th>Périmètre</th>}</tr></thead>
                <tbody>
                  @for (v of a.valeurs[domaine()] ?? []; track v.cle) {
                    @let d = decisions()[domaine()]![v.cle]!;
                    <tr>
                      <td><strong>{{ v.brut }}</strong>@if (v.a_verifier && d.action !== 'IGNORER') {<small style="color:#c2410c">à vérifier</small>}</td>
                      <td class="is-num">{{ v.occurrences }}</td>
                      <td><span class="bea-fo-score" [class.is-mid]="v.score < 1 && v.score >= 0.82" [class.is-low]="v.score < 0.82">{{ (v.score * 100).toFixed(0) }} %</span></td>
                      <td>
                        <select class="bea-fo-input" style="padding:0.35rem 0.5rem" [ngModel]="d.action" (ngModelChange)="majDecision(v, { action: $event })">
                          <option value="MAPPER">Associer</option><option value="CREER">Créer</option><option value="IGNORER">Ignorer</option>
                        </select>
                      </td>
                      <td>
                        @if (d.action === 'MAPPER') {
                          <select class="bea-fo-input" style="padding:0.35rem 0.5rem;width:100%" [class.is-invalid]="!d.cible_id" [ngModel]="d.cible_id" (ngModelChange)="majDecision(v, { cible_id: $event })">
                            <option value="">— Choisir —</option>
                            @for (o of cibles(domaine()); track o.id) { <option [value]="o.id">{{ o.libelle }}</option> }
                          </select>
                        } @else if (d.action === 'CREER') {
                          <input class="bea-fo-input" style="padding:0.35rem 0.5rem;width:100%" [ngModel]="d.libelle" (ngModelChange)="majDecision(v, { libelle: $event })" />
                          @if (v.suggestion) { <small>Proche de « {{ v.suggestion }} » — <button type="button" class="bea-fo-linkbtn" (click)="majDecision(v, { action: 'MAPPER', cible_id: v.suggestion_id ?? '' })">associer</button></small> }
                        } @else { <span class="bea-fo-hint">Non repris</span> }
                      </td>
                      @if (domaine() === 'ENTITE') {
                        <td>
                          @if (d.action === 'CREER') {
                            <select class="bea-fo-input" style="padding:0.35rem 0.5rem" [class.is-invalid]="!d.perimetre_id" [ngModel]="d.perimetre_id" (ngModelChange)="majDecision(v, { perimetre_id: $event })">
                              <option value="">— Périmètre —</option>
                              @for (p of store.refs('PERIMETRE'); track p.id) { <option [value]="p.id">{{ p.libelle }}</option> }
                            </select>
                          } @else { <span class="bea-fo-hint">{{ perimetreEntite(d.cible_id) }}</span> }
                        </td>
                      }
                    </tr>
                  } @empty {
                    <tr><td colspan="6"><div class="bea-fo-empty">Aucune valeur pour ce référentiel.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @if (etape() === 2) {
          <div class="bea-fo-note"><mat-icon>badge</mat-icon>
            <span><strong>Le découpage Nom / Prénom n’est jamais automatique :</strong> une proposition est faite selon la règle choisie ; vérifiez et corrigez chaque nouvel employé avant de confirmer.</span></div>
          <section class="bea-mg__panel">
            <div class="bea-fo-filters">
              <label style="grid-column: span 2">Règle de proposition
                <select [ngModel]="mode()" (ngModelChange)="appliquerMode($event)">
                  @for (m of modes; track m.code) { <option [value]="m.code" [disabled]="m.code === 'COLONNES' && !avecColonnes()">{{ m.label }}</option> }
                </select>
              </label>
              <label>Afficher
                <select [ngModel]="filtrePers()" (ngModelChange)="filtrePers.set($event)">
                  <option value="NOUVEAU">Nouveaux employés</option>
                  <option value="SIMILAIRE">Noms proches d’un existant</option>
                  <option value="EXISTANT">Déjà connus</option>
                  <option value="TOUS">Tous</option>
                </select>
              </label>
              <label>Recherche<input type="search" [ngModel]="qPers()" (ngModelChange)="qPers.set($event)" placeholder="Nom…" /></label>
            </div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table bea-fo-table">
                <thead><tr><th>Nom dans le fichier</th><th class="is-num">Lignes</th><th style="width:13rem">Rapprochement</th><th style="min-width:20rem">Nom &nbsp;/&nbsp; Prénom</th><th></th></tr></thead>
                <tbody>
                  @for (p of personnesVisibles(); track p.cle; let i = $index) {
                    @let c = choix()[p.cle]!;
                    <tr class="bea-fx-row-in" [style.--i]="i < 25 ? i : 0">
                      <td><strong>{{ p.brut }}</strong>
                        @if (p.variantes.length > 1) { <small>Variantes : {{ p.variantes.join(' · ') }}</small> }
                        <small>{{ p.fonction || '—' }} · {{ p.entite || '—' }}</small></td>
                      <td class="is-num">{{ p.occurrences }}</td>
                      <td>
                        <select class="bea-fo-input" style="padding:0.35rem 0.5rem;width:100%" [ngModel]="c.action === 'EXISTANT' ? c.employe_id : ''" (ngModelChange)="rapprocher(p, $event)">
                          <option value="">Nouvel employé</option>
                          @if (p.employe_id) { <option [value]="p.employe_id">= {{ p.employe }}</option> }
                          @for (k of p.candidats; track k.id) { <option [value]="k.id">≈ {{ k.nom_complet }}{{ k.entite ? ' (' + k.entite + ')' : '' }}</option> }
                        </select>
                        @if (p.candidats.length && c.action === 'NOUVEAU') { <small style="color:#c2410c">{{ p.candidats.length }} nom(s) proche(s)</small> }
                      </td>
                      <td>
                        @if (c.action === 'NOUVEAU') {
                          <div class="bea-fo-split">
                            <input [ngModel]="c.nom" (ngModelChange)="majNom(p, 'nom', $event)" placeholder="NOM" [class.is-invalid]="!c.nom.trim()" />
                            <input [ngModel]="c.prenom" (ngModelChange)="majNom(p, 'prenom', $event)" placeholder="Prénom" />
                          </div>
                        } @else { <span class="bea-fo-hint">Rattaché à l’employé existant</span> }
                      </td>
                      <td class="is-c">
                        @if (c.action === 'NOUVEAU') { <button type="button" class="bea-mg__icon-btn" title="Inverser nom et prénom" (click)="inverser(p)"><mat-icon>swap_horiz</mat-icon></button> }
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="5"><div class="bea-fo-empty">Aucune personne dans ce filtre.</div></td></tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="bea-fo-pad" style="border-top:1px solid #eef2f7">
              <label class="bea-fo-check">
                <input type="checkbox" [ngModel]="verifie()" (ngModelChange)="verifie.set($event)" />
                J’ai vérifié le découpage Nom / Prénom des {{ nbNouveaux() }} nouveaux employés.
              </label>
            </div>
          </section>
        }

        @if (etape() === 3) {
          @if (imp()!.statut === 'IMPORTE') {
            <section class="bea-mg__panel">
              <div class="bea-fo-result">
                <mat-icon>task_alt</mat-icon>
                <h2>Import terminé</h2>
                <p class="bea-fo-hint">{{ imp()!.fichier_nom }} — {{ dh(imp()!.importe_le) }}</p>
              </div>
              <div class="bea-fo-stats">
                @for (r of resultat(); track r.label; let i = $index) {
                  <div class="bea-fo-stat" [style.--i]="i" data-tone="ok"><span>{{ r.label }}</span><strong>{{ r.valeur }}</strong></div>
                }
              </div>
              <div class="bea-fo-pad" style="display:flex;gap:0.5rem;justify-content:center">
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="router.navigate(['/formation/sessions'], { queryParams: { statut: 'TOUTES' } })"><mat-icon>school</mat-icon> Voir les formations</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="router.navigate(['/formation/dashboard'])"><mat-icon>dashboard</mat-icon> Tableau de bord</button>
              </div>
            </section>
          } @else {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>Récapitulatif avant import</h2></div>
              <div class="bea-fo-stats">
                @for (s of recap(); track s.label; let i = $index) {
                  <div class="bea-fo-stat" [style.--i]="i" [attr.data-tone]="s.tone"><span>{{ s.label }}</span><strong>{{ s.valeur }}</strong></div>
                }
              </div>
              @if (problemes().length) {
                <ul class="bea-fo-anoms">
                  @for (p of problemes(); track p) { <li data-n="bloquant"><mat-icon>block</mat-icon><span>{{ p }}</span></li> }
                </ul>
              }
              <div class="bea-fo-pad" style="display:grid;gap:0.6rem;border-top:1px solid #eef2f7">
                @if (a.deja_importe) {
                  <label class="bea-fo-check"><input type="checkbox" [ngModel]="forcer()" (ngModelChange)="forcer.set($event)" /> Ce fichier a déjà été importé : je confirme vouloir l’importer de nouveau.</label>
                }
                <p class="bea-fo-hint">Les formations dont toutes les présences sont connues sont créées au statut Clôturée ; les autres restent Planifiées. Les formations identiques (même date, lieu et thèmes) déjà présentes sont complétées, sans doublon de participant.</p>
              </div>
            </section>
          }
        }

        @if (imp()!.statut === 'ANALYSE') {
          <div class="bea-fo-saisie-bar">
            <span>Étape {{ etape() + 1 }} / {{ etapes.length }} — {{ etapes[etape()] }}</span>
            <span style="display:flex;gap:0.5rem">
              @if (etape() > 0) { <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="etape.set(etape() - 1)"><mat-icon>arrow_back</mat-icon> Précédent</button> }
              @if (etape() < 3) {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="etape() === 2 && nbNouveaux() > 0 && !verifie()" (click)="suivant()">Suivant <mat-icon>arrow_forward</mat-icon></button>
              } @else {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || problemes().length > 0 || (!!a.deja_importe && !forcer())" (click)="confirmer()"><mat-icon>cloud_done</mat-icon> Confirmer l’import</button>
              }
            </span>
          </div>
        }
      }
    </div>
  `,
})
export class FoImportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly router = inject(Router);
  readonly store = inject(FormationStore);

  readonly etapes = ['Analyse & aperçu', 'Correspondances', 'Employés (Nom / Prénom)', 'Confirmation'];
  readonly doms = DOMS;
  readonly modes = MODES;
  readonly niveaux = [
    { code: 'bloquant', label: 'Bloquantes' },
    { code: 'alerte', label: 'Alertes' },
    { code: 'info', label: 'Infos' },
  ];
  readonly libStatut: Record<string, string> = { ANALYSE: 'En attente', IMPORTE: 'Importé', ABANDONNE: 'Abandonné' };
  readonly dateFr = dateFr;
  readonly dh = dateHeureFr;

  readonly historique = signal<ImportFormation[]>([]);
  readonly imp = signal<ImportFormation | null>(null);
  readonly busy = signal(false);
  readonly survol = signal(false);
  readonly etape = signal(0);
  readonly niveau = signal('bloquant');
  readonly domaine = signal<DomImport>('THEME');
  readonly decisions = signal<Record<string, Record<string, Decision>>>({});
  readonly choix = signal<Record<string, ChoixPersonne>>({});
  readonly mode = signal<Mode>('PRENOM_NOM');
  readonly filtrePers = signal('NOUVEAU');
  readonly qPers = signal('');
  readonly verifie = signal(false);
  readonly forcer = signal(false);

  readonly analyse = computed<AnalyseImport | null>(() => this.imp()?.analyse ?? null);
  readonly avecColonnes = computed(() => (this.analyse()?.personnes ?? []).some((p) => p.nom_colonne || p.prenom_colonne));

  readonly statsAffichees = computed(() => {
    const s = this.analyse()?.stats ?? {};
    return [
      { label: 'Lignes lues', valeur: s['lignes_total'] ?? 0, tone: '' },
      { label: 'Lignes valides', valeur: s['lignes_valides'] ?? 0, tone: 'ok' },
      { label: 'Lignes ignorées', valeur: s['lignes_ignorees'] ?? 0, tone: (s['lignes_ignorees'] ?? 0) ? 'danger' : '' },
      { label: 'Lignes vides', valeur: s['lignes_vides'] ?? 0, tone: '' },
      { label: 'Formations', valeur: s['sessions'] ?? 0, tone: '' },
      { label: 'Personnes', valeur: s['personnes'] ?? 0, tone: '' },
      { label: 'Déjà connues', valeur: s['employes_existants'] ?? 0, tone: 'ok' },
      { label: 'Nouveaux employés', valeur: s['nouveaux_employes'] ?? 0, tone: 'warn' },
      { label: 'Valeurs à créer', valeur: s['valeurs_a_creer'] ?? 0, tone: 'warn' },
      { label: 'Alertes', valeur: s['alertes'] ?? 0, tone: (s['alertes'] ?? 0) ? 'warn' : '' },
    ];
  });

  readonly anomalies = computed(() => (this.analyse()?.anomalies ?? []).filter((a) => a.niveau === this.niveau()));

  readonly personnesVisibles = computed(() => {
    const f = this.filtrePers();
    const q = this.qPers().trim();
    const c = this.choix();
    return (this.analyse()?.personnes ?? []).filter((p) => {
      const x = c[p.cle];
      if (!x) return false;
      if (q && !correspond(`${p.brut} ${x.nom} ${x.prenom}`, q)) return false;
      if (f === 'NOUVEAU') return x.action === 'NOUVEAU';
      if (f === 'EXISTANT') return x.action === 'EXISTANT';
      if (f === 'SIMILAIRE') return p.candidats.length > 0;
      return true;
    });
  });
  readonly nbNouveaux = computed(() => Object.values(this.choix()).filter((c) => c.action === 'NOUVEAU').length);

  readonly problemes = computed(() => {
    const out: string[] = [];
    const a = this.analyse();
    if (!a) return out;
    const d = this.decisions();
    for (const dom of DOMS) {
      for (const v of a.valeurs[dom] ?? []) {
        const x = d[dom]?.[v.cle];
        if (!x) continue;
        if (x.action === 'MAPPER' && !x.cible_id) out.push(`${this.libDom(dom)} « ${v.brut} » : valeur à associer non choisie`);
        if (x.action === 'CREER' && !x.libelle.trim()) out.push(`${this.libDom(dom)} « ${v.brut} » : libellé vide`);
        if (dom === 'ENTITE' && x.action === 'CREER' && !x.perimetre_id) out.push(`Entité « ${v.brut} » : périmètre à choisir`);
      }
    }
    for (const p of a.personnes) {
      const c = this.choix()[p.cle];
      if (c?.action === 'NOUVEAU' && !c.nom.trim()) out.push(`« ${p.brut} » : nom vide`);
    }
    if (this.nbNouveaux() && !this.verifie()) out.push('Découpage Nom / Prénom non vérifié (étape 3)');
    return out;
  });

  readonly recap = computed(() => {
    const a = this.analyse();
    if (!a) return [];
    const d = this.decisions();
    const creer = DOMS.reduce((n, dom) => n + Object.values(d[dom] ?? {}).filter((x) => x.action === 'CREER').length, 0);
    const ignorer = DOMS.reduce((n, dom) => n + Object.values(d[dom] ?? {}).filter((x) => x.action === 'IGNORER').length, 0);
    return [
      { label: 'Formations', valeur: a.sessions.length, tone: '' },
      { label: 'Participations', valeur: a.sessions.reduce((n, s) => n + s.nb_participants, 0), tone: '' },
      { label: 'Nouveaux employés', valeur: this.nbNouveaux(), tone: 'warn' },
      { label: 'Employés rapprochés', valeur: Object.values(this.choix()).length - this.nbNouveaux(), tone: 'ok' },
      { label: 'Valeurs créées', valeur: creer, tone: creer ? 'warn' : '' },
      { label: 'Valeurs ignorées', valeur: ignorer, tone: ignorer ? 'danger' : '' },
      { label: 'Lignes non importées', valeur: a.stats['lignes_ignorees'] ?? 0, tone: (a.stats['lignes_ignorees'] ?? 0) ? 'danger' : '' },
    ];
  });

  readonly resultat = computed(() =>
    Object.entries(this.imp()?.resultat ?? {})
      .filter(([, v]) => v)
      .map(([k, v]) => ({ label: RESULTATS[k] ?? k, valeur: v })),
  );

  readonly hasUnsavedChanges = unsavedChanges(() => this.imp()?.statut === 'ANALYSE' && this.etape() > 0 && !this.busy());

  ngOnInit(): void {
    this.store.charger();
    this.chargerHistorique();
  }

  private chargerHistorique(): void {
    this.api.get<ImportFormation[]>(`${FO_BASE}/imports`).subscribe({ next: (l) => this.historique.set(l), error: () => this.historique.set([]) });
  }

  libDom(d: DomImport): string {
    return DOMAINES.find((x) => x.code === d)?.pluriel ?? d;
  }

  compteNiveau(n: string): number {
    return (this.analyse()?.anomalies ?? []).filter((a) => a.niveau === n).length;
  }

  aVerifier(d: DomImport): number {
    return (this.analyse()?.valeurs[d] ?? []).filter((v) => v.a_verifier && this.decisions()[d]?.[v.cle]?.action !== 'IGNORER').length;
  }

  cibles(d: DomImport): { id: string; libelle: string }[] {
    return d === 'ENTITE' ? this.store.entites() : this.store.refs(d, true);
  }

  perimetreEntite(id: string): string {
    return this.store.entite(id)?.perimetre ?? '';
  }

  deposer(e: DragEvent): void {
    e.preventDefault();
    this.survol.set(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) this.analyser(f);
  }

  choisirFichier(input: HTMLInputElement): void {
    const f = input.files?.[0];
    input.value = '';
    if (f) this.analyser(f);
  }

  private analyser(f: File): void {
    if (!/\.(xlsx|xlsm)$/i.test(f.name)) {
      this.feedback.warning({ title: 'Format non pris en charge', message: 'Enregistrez le fichier au format .xlsx.' });
      return;
    }
    const fd = new FormData();
    fd.append('fichier', f);
    this.feedback
      .run(() => this.api.post<ImportFormation>(`${FO_BASE}/imports/analyse`, fd), {
        busy: this.busy,
        loading: 'Analyse du fichier…',
        success: (r) => ({ title: 'Analyse terminée', message: `${r.analyse?.stats['lignes_valides'] ?? 0} ligne(s) exploitable(s), ${r.analyse?.sessions.length ?? 0} formation(s)` }),
        errorTitle: "Échec de l'analyse",
        retry: false,
      })
      .subscribe((r) => this.ouvrir(r));
  }

  reprendre(h: ImportFormation): void {
    this.api.get<ImportFormation>(`${FO_BASE}/imports/${h.id}`).subscribe({
      next: (r) => this.ouvrir(r),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Import introuvable')),
    });
  }

  private ouvrir(r: ImportFormation): void {
    const a = r.analyse;
    if (!a) return;
    const dec: Record<string, Record<string, Decision>> = {};
    for (const dom of DOMS) {
      dec[dom] = {};
      for (const v of a.valeurs[dom] ?? []) {
        dec[dom][v.cle] = { action: v.action, cible_id: v.cible_id ?? '', libelle: v.libelle ?? v.brut, perimetre_id: v.perimetre_id ?? '' };
      }
    }
    this.decisions.set(dec);
    const mode: Mode = a.personnes.some((p) => p.nom_colonne || p.prenom_colonne)
      ? 'COLONNES'
      : a.personnes.filter((p) => p.mots.some((m) => m.length > 1 && m === m.toUpperCase() && /[A-Z]/.test(m)) && p.mots.some((m) => m !== m.toUpperCase())).length >= a.personnes.length / 2
        ? 'MAJUSCULES'
        : 'PRENOM_NOM';
    this.mode.set(mode);
    const choix: Record<string, ChoixPersonne> = {};
    for (const p of a.personnes) {
      const s = decouper(p, mode);
      choix[p.cle] = { action: p.action, employe_id: p.employe_id ?? '', nom: s.nom, prenom: s.prenom, modifie: false };
    }
    this.choix.set(choix);
    this.verifie.set(false);
    this.forcer.set(false);
    this.niveau.set(a.anomalies.some((x) => x.niveau === 'bloquant') ? 'bloquant' : 'alerte');
    this.domaine.set(DOMS.find((d) => (a.valeurs[d] ?? []).some((v) => v.a_verifier)) ?? 'THEME');
    this.filtrePers.set(a.personnes.some((p) => p.action === 'NOUVEAU') ? 'NOUVEAU' : 'TOUS');
    this.imp.set(r);
    this.etape.set(r.statut === 'IMPORTE' ? 3 : 0);
    if (r.statut === 'ABANDONNE') this.feedback.info({ title: 'Import abandonné', message: 'Consultation seule. Relancez une analyse pour importer ce fichier.' });
  }

  majDecision(v: ValeurImport, patch: Partial<Decision>): void {
    const dom = this.domaine();
    const d = this.decisions();
    this.decisions.set({ ...d, [dom]: { ...d[dom], [v.cle]: { ...d[dom]![v.cle]!, ...patch } } });
  }

  appliquerMode(m: Mode): void {
    this.mode.set(m);
    const a = this.analyse();
    if (!a) return;
    const c = { ...this.choix() };
    for (const p of a.personnes) {
      const x = c[p.cle]!;
      if (x.modifie) continue;
      const s = decouper(p, m);
      c[p.cle] = { ...x, nom: s.nom, prenom: s.prenom };
    }
    this.choix.set(c);
    this.verifie.set(false);
  }

  rapprocher(p: PersonneImport, id: string): void {
    const c = this.choix();
    this.choix.set({ ...c, [p.cle]: { ...c[p.cle]!, action: id ? 'EXISTANT' : 'NOUVEAU', employe_id: id } });
    this.verifie.set(false);
  }

  majNom(p: PersonneImport, champ: 'nom' | 'prenom', v: string): void {
    const c = this.choix();
    this.choix.set({ ...c, [p.cle]: { ...c[p.cle]!, [champ]: v, modifie: true } });
  }

  inverser(p: PersonneImport): void {
    const c = this.choix();
    const x = c[p.cle]!;
    this.choix.set({ ...c, [p.cle]: { ...x, nom: x.prenom, prenom: x.nom, modifie: true } });
  }

  suivant(): void {
    this.etape.set(this.etape() + 1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  abandonner(): void {
    const r = this.imp()!;
    this.feedback
      .run(() => this.api.post<ImportFormation>(`${FO_BASE}/imports/${r.id}/abandonner`, {}), {
        confirm: { action: 'annulation', title: 'Abandonner l’import', message: `Abandonner l’import de « ${r.fichier_nom} » ?`, hint: 'Aucune donnée n’a été enregistrée.' },
        busy: this.busy,
        success: { title: 'Import abandonné' },
        errorTitle: 'Action impossible',
      })
      .subscribe(() => this.reinitialiser());
  }

  reinitialiser(): void {
    this.imp.set(null);
    this.etape.set(0);
    this.chargerHistorique();
  }

  confirmer(): void {
    const r = this.imp()!;
    const decisions: Record<string, Record<string, Record<string, string | null>>> = {};
    for (const [dom, vals] of Object.entries(this.decisions())) {
      decisions[dom] = {};
      for (const [k, d] of Object.entries(vals)) {
        decisions[dom][k] = { action: d.action, cible_id: d.cible_id || null, libelle: d.libelle.trim() || null, perimetre_id: d.perimetre_id || null };
      }
    }
    const personnes: Record<string, Record<string, string | null>> = {};
    for (const [k, c] of Object.entries(this.choix())) {
      personnes[k] = c.action === 'EXISTANT'
        ? { action: 'EXISTANT', employe_id: c.employe_id }
        : { action: 'NOUVEAU', nom: c.nom.trim(), prenom: c.prenom.trim() || null };
    }
    this.feedback
      .run(
        () => this.api.post<ImportFormation>(`${FO_BASE}/imports/${r.id}/confirmer`, { decisions, personnes, verification_noms: this.verifie(), forcer: this.forcer() }),
        {
          confirm: { action: 'validation', title: 'Confirmer l’import', message: `Importer ${this.analyse()!.sessions.length} formation(s) depuis « ${r.fichier_nom} » ?`, hint: 'L’opération est tracée dans le journal d’audit.' },
          busy: this.busy,
          loading: 'Import en cours…',
          success: (x) => ({
            title: 'Import terminé',
            details: [
              { label: 'Formations créées', value: String(x.resultat?.['sessions_creees'] ?? 0) },
              { label: 'Participations', value: String(x.resultat?.['participations_creees'] ?? 0) },
              { label: 'Employés créés', value: String(x.resultat?.['employes_crees'] ?? 0) },
            ],
          }),
          errorTitle: "Échec de l'import",
          errorHint: 'Aucune donnée n’a été enregistrée ; vos corrections sont conservées.',
          retry: false,
        },
      )
      .subscribe((x) => {
        this.imp.set({ ...r, ...x, analyse: r.analyse });
        this.etape.set(3);
        this.store.recharger$().subscribe();
        this.chargerHistorique();
      });
  }
}
