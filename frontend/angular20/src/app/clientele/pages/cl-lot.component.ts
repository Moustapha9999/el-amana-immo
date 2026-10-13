import { ChangeDetectionStrategy, Component, OnInit, ViewEncapsulation, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, dateFr, dateHeureFr, n, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

export type TypeLot = 'LISTE' | 'SITUATION';

interface LigneLot {
  ligne: number; brut: string | null; racine: string | null; statut: string;
  nom: string | null; nom_fichier: string | null;
  niveau_fichier: string | null; niveau_fichier_brut: string | null; motif_fichier: string | null;
  entreprise_recente: string | null;
  date_ouverture: string | null; date_ouverture_brut: string | null; source_date_ouverture: string | null;
  date_maj: string | null; date_maj_brut: string | null; analyste: string | null;
  anomalies: string[];
  classe_actuelle: string | null; source_actuelle: string | null;
  colonnes: Record<string, string | null>;
  moteur: { score: number; niveau: string | null; statut: string; motif: string | null; classable: boolean } | null;
  divergence: boolean;
  decision: string | null;
  decision_detail: Record<string, unknown> | null;
  controle: Controle | null;
  decision_controle: DecisionControle | null;
}
type StatutControle = 'CONFORME' | 'ECART' | 'DONNEE_MANQUANTE' | 'NON_COMPARABLE';
interface Controle {
  statut: StatutControle; message: string;
  niveau_fichier_brut: string | null; niveau_fichier: string | null;
  niveau_moteur: string | null; score_moteur: number | null; version_regles: string | null;
  niveau_retenu: string | null; mode_retenu: string | null; controle_le: string | null;
}
interface DecisionControle {
  choix: 'MOTEUR' | 'FICHIER'; libelle: string; niveau_retenu: string | null;
  niveau_fichier: string | null; niveau_moteur: string | null; justification: string | null;
  effet: 'AUCUNE_MODIFICATION' | 'CLASSIFICATION_MODIFIEE'; force: boolean;
  par: string; par_nom: string | null; le: string;
}
interface Bilan {
  origine: string; ecrits: number; inchanges: number; manuels_preserves: number; non_classables: number;
  divergences_a_traiter?: number; a_reevaluer?: number; force?: boolean;
}
interface Lot {
  id: string; fichier_nom: string; type: TypeLot; statut_lot: string; periode_reference: string | null;
  feuille: string; ligne_entete: number; entetes: string[];
  colonne_racine: string | null; colonne_niveau: string | null; colonne_motif: string | null;
  colonne_entreprise_recente: string | null; colonne_date_ouverture: string | null;
  colonne_date_maj: string | null; colonne_analyste: string | null;
  colonnes_affichees: string[]; message: string | null; doublon_de: string | null;
  stats: Record<string, number>; total_filtre: number; page: number; taille: number; lignes: LigneLot[];
  evaluation: {
    nb: number; par_niveau: Record<string, number>; classables: number; a_arbitrer: number;
    divergences?: number; contradictions_entreprise?: number; version_moteur?: string; version_regles?: string;
  } | null;
  limite_evaluation: number;
  dernier_classement: Bilan | null;
}
interface LotResume {
  id: string; fichier_nom: string; type: TypeLot; statut: string; periode_reference: string | null;
  stats: Record<string, number>; dernier_classement: Bilan | null; created_at: string | null;
  actions?: { voir: boolean; exporter: boolean; modifier: boolean; fermer: boolean; supprimer: boolean };
}
type Cible = 'racine' | 'niveau' | 'motif' | 'entreprise_recente' | 'date_ouverture' | 'date_maj' | 'analyste';

const CIBLES: { cle: Cible; libelle: string }[] = [
  { cle: 'racine', libelle: 'Racine client' },
  { cle: 'niveau', libelle: 'Classe risque LBC FT' },
  { cle: 'motif', libelle: 'Motif de risque' },
  { cle: 'entreprise_recente', libelle: 'Entreprise ouverture récente' },
  { cle: 'date_ouverture', libelle: 'Date ouverture entreprise' },
  { cle: 'date_maj', libelle: 'Date de mise à jour' },
  { cle: 'analyste', libelle: 'Analyste KYC' },
];

const TEXTES: Record<TypeLot, { titre: string; depot: string; aide: string }> = {
  LISTE: {
    titre: 'Liste de clients',
    depot: 'Déposez le classeur hebdomadaire (feuille CLIENTS, une ligne par racine)',
    aide: '22 colonnes métier + DATE_CREATION_ENTREPRISE / ENTREPRISE_OUVERTURE_RECENTE. Les listes de référence ne sont pas importées comme des clients. DATE EER n’est jamais une date de création. Téléchargez le modèle avant le premier dépôt.',
  },
  SITUATION: {
    titre: 'Situation des comptes PP & PM',
    depot: 'Déposez le classeur « Situation des comptes PP et PM »',
    aide: 'Reprise de la classe de risque Conformité (source EXCEL_CONFORMITE). Racines absentes du référentiel : signalées, jamais créées.',
  },
};

const LIB_DECISION: Record<string, string> = {
  ECRIT: 'Enregistré', INCHANGE: 'Inchangé', MANUEL_PRESERVE: 'Manuel préservé (réexamen ouvert)',
  NON_ADMISSIBLE: 'Moteur non admissible', NON_CLASSABLE: 'Non classable',
  DIVERGENCE_A_TRAITER: 'Divergence à traiter', A_REEVALUER: 'À réévaluer',
  ARBITRE_MOTEUR: 'Arbitré : moteur', ARBITRE_FICHIER: 'Arbitré : fichier', ARBITRE_AUTRE: 'Arbitré : autre niveau',
  CONSERVE_MOTEUR: 'Classement SCORE conservé', RETENU_FICHIER: 'Niveau du fichier retenu',
};

const LIB_CONTROLE: Record<StatutControle, string> = {
  CONFORME: 'Conforme', ECART: 'Écart détecté',
  DONNEE_MANQUANTE: 'Comparaison impossible — donnée manquante', NON_COMPARABLE: 'Non comparable — à vérifier',
};
const ICONE_CONTROLE: Record<StatutControle, string> = {
  CONFORME: 'check_circle', ECART: 'compare_arrows', DONNEE_MANQUANTE: 'help', NON_COMPARABLE: 'report',
};

@Component({
  selector: 'bea-cl-lot',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  styleUrls: ['./cl-lot.css'],
  encapsulation: ViewEncapsulation.None,
  template: `
    @let t = textes();
    @let liste = type() === 'LISTE';
    @if (!lot()) {
      <section class="bea-mg__panel" style="padding:1rem">
        <div class="bea-cl-filters" style="padding:0 0 0.75rem">
          <label>Période de référence
            <input type="date" [(ngModel)]="periode" />
          </label>
        </div>
        <label class="bea-fx-dropzone" [class.is-over]="survol()" (dragover)="$event.preventDefault(); survol.set(true)" (dragleave)="survol.set(false)" (drop)="deposer($event)">
          <input type="file" accept=".xlsx,.xlsm" hidden (change)="choisir($any($event.target))" />
          @if (busy()) {
            <mat-icon class="bea-cl-spin">progress_activity</mat-icon><strong>Analyse du fichier…</strong>
          } @else {
            <mat-icon>{{ type() === 'SITUATION' ? 'assignment' : 'group_add' }}</mat-icon>
            <strong>{{ t.depot }}</strong>
            <span>.xlsx, 40 Mo maximum. Aucune classification n’est écrite avant votre confirmation.</span>
          }
        </label>
        <p class="bea-cl-hint" style="margin:0.6rem 0 0">{{ t.aide }}</p>
        @if (type() === 'LISTE') {
          <p style="margin:0.75rem 0 0">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="telechargerModele()" [disabled]="busy()">
              <mat-icon>table_view</mat-icon> Télécharger le modèle (CLIENTS / REFERENTIELS / NOTICE)
            </button>
          </p>
        }
      </section>

      @if (historique().length) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Historique des lots</h2></div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th>Déposé le</th><th>Fichier</th><th>Période</th><th>Statut</th><th>Racines</th><th>Dernier classement</th><th style="text-align:right">Actions</th></tr></thead>
              <tbody>
                @for (h of historique(); track h.id) {
                  <tr>
                    <td>{{ dateHeureFr(h.created_at) }}</td>
                    <td>{{ h.fichier_nom }}</td>
                    <td>{{ dateFr(h.periode_reference) }}</td>
                    <td><span class="bea-cl-badge" [attr.data-s]="h.statut">{{ libLot[h.statut] || h.statut }}</span></td>
                    <td>{{ n(h.stats['racines_ok']) }} / {{ n(h.stats['lignes']) }}</td>
                    <td>
                      @if (h.dernier_classement; as b) { {{ b.origine === 'MOTEUR' ? 'Moteur' : 'Fichier' }} : {{ b.ecrits }} écrit(s), {{ b.manuels_preserves }} manuel(s) préservé(s) }
                      @else { — }
                    </td>
                    <td>
                      <div class="bea-cl-row-actions">
                        <button type="button" (click)="ouvrirLot(h.id)" [disabled]="busy()" title="Voir" aria-label="Voir"><mat-icon>visibility</mat-icon></button>
                        <button type="button" (click)="exporterLot(h)" [disabled]="busy()" title="Exporter" aria-label="Exporter"><mat-icon>download</mat-icon></button>
                        @if (h.actions?.modifier !== false && h.statut !== 'FERME') {
                          <button type="button" (click)="editer(h)" [disabled]="busy()" title="Modifier" aria-label="Modifier"><mat-icon>edit</mat-icon></button>
                        }
                        @if (h.actions?.fermer !== false && h.statut !== 'FERME') {
                          <button type="button" (click)="fermerLot(h)" [disabled]="busy()" title="Fermer" aria-label="Fermer"><mat-icon>lock</mat-icon></button>
                        }
                        <button type="button" class="is-danger" (click)="supprimerLot(h)" [disabled]="busy()" title="Supprimer" aria-label="Supprimer"><mat-icon>delete</mat-icon></button>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
            @if (edition(); as ed) {
              <form class="bea-cl-filters" style="padding:0.9rem 1.1rem" (submit)="$event.preventDefault(); enregistrerEdition()">
                <label>Libellé du lot<input type="text" [(ngModel)]="ed.fichier_nom" name="lot_nom" maxlength="255" /></label>
                <label>Période de référence<input type="date" [(ngModel)]="ed.periode_reference" name="lot_periode" /></label>
                <div style="display:flex;align-items:end;gap:0.45rem">
                  <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer</button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="edition.set(null)">Annuler</button>
                </div>
              </form>
            }
          </div>
        </section>
      }
    } @else {
      @let l = lot()!;
      @let fige = l.statut_lot === 'FERME';
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <div>
            <h2>{{ l.fichier_nom }}</h2>
            <p class="bea-cl-hint">{{ t.titre }} · feuille « {{ l.feuille }} », en-têtes ligne {{ l.ligne_entete }} · période {{ dateFr(l.periode_reference) }} · <span class="bea-cl-badge" [attr.data-s]="l.statut_lot">{{ libLot[l.statut_lot] || l.statut_lot }}</span></p>
          </div>
          <span style="display:flex;gap:0.4rem;flex-wrap:wrap">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter()" [disabled]="busy() || !l.colonne_racine"><mat-icon>download</mat-icon> Exporter</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="quitter()" [disabled]="busy()"><mat-icon>arrow_back</mat-icon> Retour</button>
            @if (!fige) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()" [disabled]="busy()"><mat-icon>lock</mat-icon> Fermer</button>
            }
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost bea-cl-btn--danger" (click)="supprimer()" [disabled]="busy()"><mat-icon>delete</mat-icon> Supprimer</button>
          </span>
        </div>
        @if (!fige && l.statut_lot !== 'ENREGISTRE') {
          <div class="bea-cl-filters">
            @for (c of cibles; track c.cle) {
              <label>{{ c.libelle }}
                <select [ngModel]="colonnes[c.cle]" (ngModelChange)="colonnes[c.cle] = $event">
                  @if (c.cle === 'racine') { <option [ngValue]="null">— choisir —</option> }
                  @else { <option [ngValue]="''">Aucune</option> }
                  @for (e of l.entetes; track e) { <option [ngValue]="e">{{ e }}</option> }
                </select>
              </label>
            }
            <label>Période de référence <input type="date" [(ngModel)]="periode" /></label>
            <label>&nbsp;<button type="button" class="bea-mg__btn" (click)="recartographier()" [disabled]="busy() || !colonnes.racine">Appliquer les colonnes</button></label>
          </div>
        }
        @if (l.message) {
          <div class="bea-cl-note" style="margin:0 1.1rem 0.9rem"><mat-icon>info</mat-icon><span>{{ l.message }}</span></div>
        }
        @if (l.colonne_racine) {
          <div class="bea-cl-stats">
            <div class="bea-cl-stat"><span>Lignes clients</span><strong>{{ n(l.stats['lignes']) }}</strong></div>
            @if (l.stats['lignes_ignorees']) {
              <div class="bea-cl-stat"><span>Listes / consignes ignorées</span><strong>{{ n(l.stats['lignes_ignorees']) }}</strong></div>
            }
            <div class="bea-cl-stat" data-tone="ok"><span>Racines reconnues</span><strong>{{ n(l.stats['racines_ok']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="l.stats['inconnues'] ? 'warn' : ''" title="Racine absente de la Base Clientèle. Le lot ne crée jamais de client."><span>Inconnues (jamais créées)</span><strong>{{ n(l.stats['inconnues']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="l.stats['invalides'] ? 'danger' : ''"><span>Invalides</span><strong>{{ n(l.stats['invalides']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="l.stats['doublons'] ? 'warn' : ''"><span>Doublons</span><strong>{{ n(l.stats['doublons']) }}</strong></div>
            @if (l.colonne_niveau) { <div class="bea-cl-stat"><span>Avec classe fichier</span><strong>{{ n(l.stats['avec_niveau']) }}</strong></div> }
            <div class="bea-cl-stat"><span>Avec date d’ouverture</span><strong>{{ n(l.stats['avec_date_ouverture']) }}</strong></div>
            <div class="bea-cl-stat"><span>Avec analyste KYC</span><strong>{{ n(l.stats['avec_analyste']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="l.stats['avec_anomalie'] ? 'warn' : ''"><span>Lignes en anomalie</span><strong>{{ n(l.stats['avec_anomalie']) }}</strong></div>
            <div class="bea-cl-stat"><span>Déjà classés</span><strong>{{ n(l.stats['deja_classes']) }}</strong></div>
            <div class="bea-cl-stat"><span>Classés manuellement</span><strong>{{ n(l.stats['manuels']) }}</strong></div>
          </div>
          @if (liste && l.colonne_niveau) {
            @let aDecider = (l.stats['controle_ecarts'] || 0) - (l.stats['controle_ecarts_decides'] || 0);
            <h3 class="bea-cl-ctl-titre">Contrôle fichier / moteur SCORE (niveau enregistré, moteur non relancé)</h3>
            <div class="bea-cl-stats bea-cl-ctl-stats">
              <button type="button" class="bea-cl-stat" data-tone="ok" (click)="filtrer('CONTROLE_CONFORME')"><span>Conformes</span><strong>{{ n(l.stats['controle_conformes']) }}</strong></button>
              <button type="button" class="bea-cl-stat" [attr.data-tone]="aDecider ? 'danger' : ''" (click)="filtrer('CONTROLE_A_DECIDER')"><span>Écarts à décider</span><strong>{{ n(aDecider) }}</strong></button>
              <button type="button" class="bea-cl-stat" (click)="filtrer('CONTROLE_DECIDE')"><span>Écarts décidés</span><strong>{{ n(l.stats['controle_ecarts_decides']) }}</strong></button>
              <button type="button" class="bea-cl-stat" [attr.data-tone]="l.stats['controle_manquants'] ? 'warn' : ''" (click)="filtrer('CONTROLE_DONNEE_MANQUANTE')"><span>Comparaison impossible</span><strong>{{ n(l.stats['controle_manquants']) }}</strong></button>
              <button type="button" class="bea-cl-stat" [attr.data-tone]="l.stats['controle_non_comparables'] ? 'warn' : ''" (click)="filtrer('CONTROLE_NON_COMPARABLE')"><span>Non comparables</span><strong>{{ n(l.stats['controle_non_comparables']) }}</strong></button>
            </div>
            <div class="bea-cl-note bea-cl-note--info" style="margin:0 1.1rem 0.9rem"><mat-icon>rule</mat-icon>
              <span>Chaque niveau du fichier est comparé au niveau enregistré par le moteur SCORE. Seuls les écarts confirmés appellent une décision, ligne par ligne : conserver le classement du moteur SCORE (aucune modification) ou retenir le niveau du fichier (justification obligatoire, décision manuelle tracée). Correspondances admises : Faible, Moyen, Élevé, Interdit uniquement.</span>
            </div>
          }
          @if (l.stats['inconnues']) {
            <div class="bea-cl-note bea-cl-note--warn" style="margin:0 1.1rem 0.9rem"><mat-icon>info</mat-icon>
              <span>{{ n(l.stats['inconnues']) }} racine(s) absente(s) de la Base Clientèle. Le lot ne crée jamais de client : importez-les d’abord via l’import ORION, puis réimportez ce fichier.</span>
            </div>
          }
        }
      </section>

      @if (l.colonne_racine) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Évaluation et enregistrement</h2></div>
          <div class="bea-cl-options" style="padding:0 1.1rem">
            <button type="button" class="bea-cl-option" (click)="evaluer()" [disabled]="busy() || fige || !l.stats['racines_ok']">
              <mat-icon>calculate</mat-icon><strong>Évaluer avec le moteur</strong>
              <span>Score CDC 1.0 et comparaison fichier / moteur. Aucune classification écrite (≤ {{ n(l.limite_evaluation) }} racines).</span>
            </button>
            @if (store.cap().classif_executer) {
              <button type="button" class="bea-cl-option" (click)="classer('MOTEUR')" [disabled]="busy() || fige || !l.evaluation?.classables || !masseAutorisee()">
                <mat-icon>{{ masseAutorisee() ? 'rule' : 'lock' }}</mat-icon><strong>Enregistrer le niveau proposé par le moteur</strong>
                <span>{{ masseAutorisee() ? 'Résultats admissibles uniquement (jamais NON CLASSÉ ni À ARBITRER). Décisions manuelles préservées.' : 'Suspendu côté serveur : règles SCORE en attente de validation Conformité. Écart par écart : décision ligne à ligne ci-dessous.' }}</span>
              </button>
              @if (l.colonne_niveau && !liste) {
                <button type="button" class="bea-cl-option" (click)="classer('FICHIER')" [disabled]="busy() || fige || !l.evaluation || !l.stats['avec_niveau']">
                  <mat-icon>file_download_done</mat-icon><strong>Enregistrer la classe du fichier</strong>
                  <span>Les divergences fichier / moteur ne sont pas écrites : décision humaine requise.</span>
                </button>
              }
            }
          </div>
          @if (store.cap().classif_forcer && !fige) {
            <label class="bea-cl-check" style="padding:0.75rem 1.1rem 0"><input type="checkbox" [(ngModel)]="forcer" /> Forçage : remplacer aussi les décisions manuelles (permission dédiée, confirmation et motif exigés, tracé dans l’audit)</label>
          }
          @if (l.evaluation; as ev) {
            <div class="bea-cl-stats">
              <div class="bea-cl-stat"><span>Évaluées</span><strong>{{ n(ev.nb) }}</strong></div>
              <div class="bea-cl-stat" data-tone="ok"><span>Admissibles</span><strong>{{ n(ev.classables) }}</strong></div>
              <div class="bea-cl-stat" [attr.data-tone]="ev.a_arbitrer ? 'warn' : ''"><span>À arbitrer (moteur)</span><strong>{{ n(ev.a_arbitrer) }}</strong></div>
              @if (!liste) {
                <div class="bea-cl-stat" [attr.data-tone]="ev.divergences ? 'danger' : ''"><span>Divergences fichier / moteur</span><strong>{{ n(ev.divergences) }}</strong></div>
              }
              <div class="bea-cl-stat" [attr.data-tone]="ev.contradictions_entreprise ? 'warn' : ''"><span>Entreprise récente à vérifier</span><strong>{{ n(ev.contradictions_entreprise) }}</strong></div>
              @for (k of niveaux; track k) {
                <div class="bea-cl-stat"><span>{{ k === 'NON_CLASSE' ? 'Non classé' : k }}</span><strong>{{ n(ev.par_niveau[k] || 0) }}</strong></div>
              }
            </div>
            @if (ev.version_moteur) { <p class="bea-cl-hint" style="padding:0 1.1rem">Moteur {{ ev.version_moteur }} · règles {{ ev.version_regles }}</p> }
          }
          @if (l.dernier_classement; as b) {
            <div class="bea-cl-note bea-cl-note--info" style="margin:0 1.1rem 0.9rem"><mat-icon>task_alt</mat-icon>
              <span>Dernier enregistrement ({{ b.origine === 'MOTEUR' ? 'moteur' : 'fichier' }}{{ b.force ? ', forcé' : '' }}) : {{ b.ecrits }} écrit(s), {{ b.inchanges }} inchangé(s), {{ b.manuels_preserves }} manuel(s) préservé(s), {{ b.non_classables }} non classable(s), {{ b.divergences_a_traiter ?? 0 }} divergence(s) à traiter, {{ b.a_reevaluer ?? 0 }} à réévaluer.</span>
            </div>
          }
        </section>

        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Lignes</h2>
            <span style="display:flex;gap:0.5rem;align-items:center">
              <select [(ngModel)]="filtre" (ngModelChange)="recharger()" style="font:inherit;padding:0.35rem 0.5rem;border:1px solid #dbe3ee;border-radius:0.5rem">
                <option [ngValue]="''">Toutes</option>
                <option value="OK">Reconnues</option>
                @if (liste) {
                  <option value="CONTROLE_A_DECIDER">Écarts à décider</option>
                  <option value="CONTROLE_DECIDE">Écarts décidés</option>
                  <option value="CONTROLE_CONFORME">Conformes</option>
                  <option value="CONTROLE_DONNEE_MANQUANTE">Comparaison impossible</option>
                  <option value="CONTROLE_NON_COMPARABLE">Non comparables</option>
                } @else {
                  <option value="DIVERGENCE">Divergences fichier / moteur</option>
                  <option value="A_TRAITER">À traiter</option>
                }
                <option value="ANOMALIE">Anomalies</option>
                <option value="INCONNUE">Inconnues</option>
                <option value="INVALIDE">Invalides</option>
                <option value="DOUBLON">Doublons</option>
              </select>
              <span class="bea-mg__count">{{ n(l.total_filtre) }}</span>
            </span>
          </div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-cl-lot-table" [class.is-liste]="liste">
              <thead><tr>
                <th>Racine</th><th>Nom</th><th>État</th>
                @if (liste) {
                  <th>Fichier</th><th>SCORE enregistré</th><th class="bea-cl-ctl">Contrôle fichier / SCORE</th><th>Anomalies</th>
                } @else {
                  <th>Fichier</th><th>Moteur</th><th>Anomalies</th><th>Décision</th>
                }
              </tr></thead>
              <tbody>
                @for (x of l.lignes; track x.ligne) {
                  @let c = x.controle;
                  @let dc = x.decision_controle;
                  <tr [class.is-div]="liste ? (c?.statut === 'ECART' && !dc) : (x.divergence && !x.decision?.startsWith('ARBITRE'))" [class.is-open]="detail()===x.ligne">
                    <td>
                      @if (x.statut === 'OK') { <a [routerLink]="['/clientele/clients', x.racine]"><code>{{ x.racine }}</code></a> }
                      @else { <code>{{ x.racine || x.brut || '—' }}</code> }
                    </td>
                    <td class="bea-cl-nom" [attr.title]="x.nom || x.nom_fichier || ''">
                      <button type="button" class="bea-cl-link" (click)="basculer(x.ligne)">{{ x.nom || x.nom_fichier || '—' }}</button>
                    </td>
                    <td><span class="bea-cl-badge" [attr.data-s]="x.statut" [attr.title]="aideStatut[x.statut] || null">{{ libStatut[x.statut] || x.statut }}</span></td>
                    @if (liste) {
                    <td>
                      @if (c?.niveau_fichier) { <span class="bea-cl-badge" [attr.data-s]="c!.niveau_fichier">{{ c!.niveau_fichier }}</span> }
                      @else if (x.niveau_fichier_brut) { <span class="bea-cl-brut" title="Libellé du fichier, tel quel">« {{ x.niveau_fichier_brut }} »</span> }
                      @else { — }
                    </td>
                    <td>
                      @if (c?.niveau_moteur) {
                        <span class="bea-cl-badge" [attr.data-s]="c!.niveau_moteur">{{ c!.niveau_moteur }}</span>
                        @if (c!.score_moteur !== null) { <small class="bea-cl-hint"> {{ n(c!.score_moteur) }}</small> }
                      } @else { — }
                    </td>
                    <td class="bea-cl-ctl">
                      @if (c) {
                        <span class="bea-cl-ctl-badge" [attr.data-c]="dc ? 'DECIDE' : c.statut" [attr.title]="c.message">
                          <mat-icon>{{ dc ? 'task_alt' : icone[c.statut] }}</mat-icon>{{ dc ? 'Écart décidé' : libControle[c.statut] }}
                        </span>
                        @if (dc) {
                          <span class="bea-cl-ctl-l2">{{ dc.choix === 'MOTEUR' ? 'A' : 'B' }} · {{ dc.libelle }} → <strong>{{ dc.niveau_retenu }}</strong></span>
                          <span class="bea-cl-ctl-l2 bea-cl-hint">{{ dc.par_nom || 'Utilisateur' }} · {{ dateHeureFr(dc.le) }}</span>
                          @if (dc.justification) { <span class="bea-cl-ctl-l2 bea-cl-ctl-just" [attr.title]="dc.justification">« {{ dc.justification }} »</span> }
                        } @else if (c.statut === 'ECART') {
                          <span class="bea-cl-ctl-l2">Fichier <strong>{{ c.niveau_fichier }}</strong> ≠ SCORE <strong>{{ c.niveau_moteur }}</strong></span>
                          @if (store.cap().classif_executer && !fige) {
                            @let bloque = c.niveau_moteur === 'INTERDIT' && !store.cap().classif_forcer;
                            <span class="bea-cl-ctl-actions">
                              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="conserverMoteur(x)" [disabled]="busy()" title="Aucune modification de la classification enregistrée">A · Conserver le classement SCORE</button>
                              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="retenirFichier(x)" [disabled]="busy() || bloque"
                                [attr.title]="bloque ? 'Blocage INTERDIT du moteur SCORE : permission de forçage requise' : 'Justification obligatoire, décision manuelle tracée'">B · Retenir le niveau du fichier</button>
                            </span>
                          }
                        } @else {
                          <span class="bea-cl-ctl-l2 bea-cl-hint">{{ c.statut === 'CONFORME' ? 'Aucune décision requise.' : c.statut === 'NON_COMPARABLE' ? 'Vérification requise.' : 'Aucune décision automatique.' }}</span>
                        }
                      } @else { — }
                    </td>
                    <td>
                      @if (x.anomalies.length) {
                        <button type="button" class="bea-cl-chip bea-cl-chip--n" [attr.title]="x.anomalies.join(' · ')" (click)="basculer(x.ligne)">{{ x.anomalies.length }} anomalie(s)</button>
                      } @else { — }
                    </td>
                    } @else {
                    <td>
                      @if (x.niveau_fichier) { <span class="bea-cl-badge" [attr.data-s]="x.niveau_fichier">{{ x.niveau_fichier }}</span> }
                      @else { {{ x.niveau_fichier_brut || '—' }} }
                    </td>
                    <td [attr.title]="x.moteur?.motif || ''">
                      @if (x.moteur; as m) {
                        <span class="bea-cl-badge" [attr.data-s]="m.niveau || m.statut">{{ m.niveau || 'NON CLASSÉ' }}</span>
                        <small class="bea-cl-hint"> {{ n(m.score) }}</small>
                      } @else { — }
                    </td>
                    <td>
                      @if (x.anomalies.length) {
                        <button type="button" class="bea-cl-chip bea-cl-chip--n" [attr.title]="x.anomalies.join(' · ')" (click)="basculer(x.ligne)">{{ x.anomalies.length }} anomalie(s)</button>
                      } @else { — }
                    </td>
                    <td>
                      @if (x.divergence) { <span class="bea-cl-badge" data-s="A_ARBITRER">Divergence</span> }
                      @if (x.decision) { <span class="bea-cl-badge" [attr.data-s]="x.decision">{{ libDecision[x.decision] || x.decision }}</span> }
                      @if (x.divergence && store.cap().classif_executer && !fige && !x.decision?.startsWith('ARBITRE')) {
                        <span style="display:inline-flex;gap:0.3rem;margin-left:0.35rem">
                          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="trancher(x, 'MOTEUR')" [disabled]="busy()">Moteur</button>
                          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="trancher(x, 'FICHIER')" [disabled]="busy()">Fichier</button>
                        </span>
                      }
                    </td>
                    }
                  </tr>
                  @if (detail() === x.ligne) {
                    <tr class="bea-cl-lot-detail">
                      <td colspan="7">
                        <div class="bea-cl-lot-detail__grid">
                          @if (c) {
                            <section>
                              <h3>Contrôle fichier / moteur SCORE</h3>
                              <p><span class="bea-cl-ctl-badge" [attr.data-c]="c.statut"><mat-icon>{{ icone[c.statut] }}</mat-icon>{{ libControle[c.statut] }}</span></p>
                              <p>{{ c.message }}</p>
                              <p class="bea-cl-hint">Fichier « {{ c.niveau_fichier_brut || '—' }} » → {{ c.niveau_fichier || 'hors correspondance' }} · SCORE enregistré {{ c.niveau_moteur || '—' }}{{ c.score_moteur !== null ? ' (' + n(c.score_moteur) + ')' : '' }}{{ c.version_regles ? ' · règles ' + c.version_regles : '' }}</p>
                              <p class="bea-cl-hint">Classement en vigueur au contrôle : {{ c.niveau_retenu || '—' }}{{ c.mode_retenu ? ' (' + c.mode_retenu + ')' : '' }} · contrôlé le {{ dateHeureFr(c.controle_le) }}</p>
                              @if (dc) {
                                <p><strong>Décision :</strong> {{ dc.choix === 'MOTEUR' ? 'A' : 'B' }} · {{ dc.libelle }} — niveau retenu {{ dc.niveau_retenu }}{{ dc.force ? ' (forçage)' : '' }}</p>
                                <p class="bea-cl-hint">Par {{ dc.par_nom || 'Utilisateur' }}, le {{ dateHeureFr(dc.le) }} · {{ dc.effet === 'CLASSIFICATION_MODIFIEE' ? 'classification modifiée (décision manuelle)' : 'classification enregistrée inchangée' }}</p>
                                <p>Justification : {{ dc.justification || '—' }}</p>
                              }
                            </section>
                          }
                          <section>
                            <h3>{{ liste ? 'Évaluation du lot (non enregistrée)' : 'Moteur' }}</h3>
                            <p>{{ x.moteur?.motif || 'Pas encore évalué.' }}</p>
                            @if (x.classe_actuelle) {
                              <p class="bea-cl-hint">Classe actuelle : {{ x.classe_actuelle }} ({{ x.source_actuelle }})</p>
                            }
                            @if (liste && x.decision && !dc) {
                              <p class="bea-cl-hint">Enregistrement du lot : {{ libDecision[x.decision] || x.decision }}</p>
                            }
                          </section>
                          <section>
                            <h3>Fichier</h3>
                            <p>Motif : {{ x.motif_fichier || '—' }}</p>
                            <p class="bea-cl-hint">Analyste {{ x.analyste || '—' }} · MAJ {{ x.date_maj ? dateFr(x.date_maj) : (x.date_maj_brut || '—') }}</p>
                            <p>
                              Date création entreprise
                              @if (x.statut === 'OK' && store.cap().classif_executer && !fige) {
                                <input type="date" [ngModel]="x.date_ouverture" (change)="saisirDate(x, $any($event.target).value)" [disabled]="busy()" />
                              } @else { : {{ x.date_ouverture ? dateFr(x.date_ouverture) : (x.date_ouverture_brut || '—') }} }
                            </p>
                          </section>
                          <section>
                            <h3>Anomalies ({{ x.anomalies.length }})</h3>
                            @if (x.anomalies.length) {
                              <ul>@for (a of x.anomalies; track $index) { <li>{{ a }}</li> }</ul>
                            } @else { <p>Aucune.</p> }
                          </section>
                        </div>
                      </td>
                    </tr>
                  }
                } @empty {
                  <tr><td colspan="7"><div class="bea-cl-empty">Aucune ligne.</div></td></tr>
                }
              </tbody>
            </table>
          </div>
          @if (l.total_filtre > l.lignes.length) {
            <div class="bea-cl-bar" style="position:static">
              <span>Page {{ l.page }} — {{ l.lignes.length }} ligne(s) affichée(s) sur {{ n(l.total_filtre) }}</span>
              <span style="display:flex;gap:0.5rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="l.page <= 1" (click)="page(l.page - 1)">Précédent</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="l.page * l.taille >= l.total_filtre" (click)="page(l.page + 1)">Suivant</button>
              </span>
            </div>
          }
        </section>
      }
    }
  `,
})
export class ClLotComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly type = input.required<TypeLot>();
  readonly textes = computed(() => TEXTES[this.type()]);
  readonly lot = signal<Lot | null>(null);
  readonly historique = signal<LotResume[]>([]);
  readonly edition = signal<{ id: string; fichier_nom: string; periode_reference: string } | null>(null);
  readonly detail = signal<number | null>(null);
  readonly busy = signal(false);
  readonly masseAutorisee = signal(false);
  readonly survol = signal(false);
  readonly niveaux = ['FAIBLE', 'MOYEN', 'ELEVE', 'INTERDIT', 'NON_CLASSE'];
  readonly cibles = CIBLES;
  readonly libStatut: Record<string, string> = { OK: 'Reconnue', INCONNUE: 'Inconnue', INVALIDE: 'Invalide', DOUBLON: 'Doublon' };
  readonly aideStatut: Record<string, string> = {
    OK: 'Racine trouvée dans la Base Clientèle.',
    INCONNUE: 'Racine absente de la Base Clientèle : le lot ne crée jamais de client. Importez-la d’abord via l’import ORION.',
    INVALIDE: 'Racine non conforme (6 chiffres attendus).',
    DOUBLON: 'Racine déjà présente plus haut dans le fichier.',
  };
  readonly libLot: Record<string, string> = { ANALYSE: 'Analysé', EVALUE: 'Évalué', ENREGISTRE: 'Enregistré', FERME: 'Fermé' };
  readonly libDecision = LIB_DECISION;
  readonly libControle = LIB_CONTROLE;
  readonly icone = ICONE_CONTROLE;
  readonly n = n;
  readonly dateFr = dateFr;
  readonly dateHeureFr = dateHeureFr;
  colonnes: Record<Cible, string | null> = {
    racine: null, niveau: '', motif: '', entreprise_recente: '', date_ouverture: '', date_maj: '', analyste: '',
  };
  periode = new Date().toISOString().slice(0, 10);
  filtre = '';
  forcer = false;

  ngOnInit(): void {
    this.chargerHistorique();
    this.api.get<{ actif: boolean }>(`${CL_BASE}/classification/taches/autorisation`).subscribe({
      next: (v) => this.masseAutorisee.set(v.actif),
      error: () => this.masseAutorisee.set(false),
    });
  }

  chargerHistorique(): void {
    this.api.get<{ items: LotResume[] }>(`${CL_BASE}/lots`).subscribe({
      next: (r) => this.historique.set(r.items.filter((x) => x.type === this.type())),
      error: () => this.historique.set([]),
    });
  }

  deposer(e: DragEvent): void {
    e.preventDefault();
    this.survol.set(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) this.analyser(f);
  }

  choisir(input: HTMLInputElement): void {
    const f = input.files?.[0];
    input.value = '';
    if (f) this.analyser(f);
  }

  private analyser(f: File): void {
    if (!/\.(xlsx|xlsm)$/i.test(f.name)) {
      this.feedback.warning({ title: 'Format non pris en charge', message: 'Fichier .xlsx attendu.' });
      return;
    }
    const fd = new FormData();
    fd.append('fichier', f);
    const periode = this.periode ? `&periode_reference=${this.periode}` : '';
    this.feedback.run(() => this.api.post<Lot>(`${CL_BASE}/lots/analyse?type=${this.type()}${periode}`, fd), {
      busy: this.busy, loading: 'Analyse du fichier…',
      success: (l) => l.colonne_racine
        ? { title: 'Analyse terminée', message: `${l.stats['racines_ok'] ?? 0} racine(s) reconnue(s) sur ${l.stats['lignes'] ?? 0} ligne(s)` }
        : { title: 'Fichier lu', message: 'Choisissez la colonne Racine client.' },
      errorTitle: "Échec de l'analyse", retry: false,
    }).subscribe((l) => this.ouvrir(l));
  }

  ouvrirLot(id: string): void {
    this.busy.set(true);
    this.api.get<Lot>(`${CL_BASE}/lots/${id}`).subscribe({
      next: (l) => { this.busy.set(false); this.ouvrir(l); },
      error: (e) => { this.busy.set(false); void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Lot indisponible')); },
    });
  }

  private ouvrir(l: Lot): void {
    this.colonnes = {
      racine: l.colonne_racine, niveau: l.colonne_niveau ?? '', motif: l.colonne_motif ?? '',
      entreprise_recente: l.colonne_entreprise_recente ?? '', date_ouverture: l.colonne_date_ouverture ?? '',
      date_maj: l.colonne_date_maj ?? '', analyste: l.colonne_analyste ?? '',
    };
    if (l.periode_reference) this.periode = l.periode_reference;
    this.forcer = false;
    this.filtre = '';
    this.detail.set(null);
    this.lot.set(l);
  }

  recartographier(): void {
    const l = this.lot()!;
    const c = this.colonnes;
    this.feedback.run(() => this.api.post<Lot>(`${CL_BASE}/lots/${l.id}/mapping`, {
      colonne_racine: c.racine, colonne_niveau: c.niveau ?? '', colonne_motif: c.motif ?? '',
      colonne_entreprise_recente: c.entreprise_recente ?? '', colonne_date_ouverture: c.date_ouverture ?? '',
      colonne_date_maj: c.date_maj ?? '', colonne_analyste: c.analyste ?? '',
      periode_reference: this.periode || null,
    }), {
      busy: this.busy, loading: 'Nouvelle analyse…', success: { title: 'Colonnes appliquées' }, errorTitle: 'Analyse refusée',
    }).subscribe((x) => this.ouvrir(x));
  }

  recharger(p = 1): void {
    const l = this.lot()!;
    const params: Record<string, string | number> = { page: p };
    if (this.filtre) params['statut'] = this.filtre;
    this.api.get<Lot>(`${CL_BASE}/lots/${l.id}`, params).subscribe({
      next: (x) => this.lot.set(x),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Lot indisponible')),
    });
  }

  page(p: number): void {
    this.recharger(p);
  }

  basculer(ligne: number): void {
    this.detail.update((c) => c === ligne ? null : ligne);
  }

  evaluer(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.post<Lot>(`${CL_BASE}/lots/${l.id}/evaluer`, {}), {
      busy: this.busy, loading: `Évaluation de ${l.stats['racines_ok']} racine(s)…`,
      success: (x) => ({
        title: 'Évaluation terminée', message: 'Aucune classification écrite.',
        details: [
          { label: 'Admissibles', value: String(x.evaluation?.classables ?? 0) },
          { label: 'Divergences fichier / moteur', value: String(x.evaluation?.divergences ?? 0) },
          { label: 'À arbitrer (moteur)', value: String(x.evaluation?.a_arbitrer ?? 0) },
        ],
      }),
      errorTitle: 'Évaluation refusée', retry: false,
    }).subscribe((x) => { this.filtre = ''; this.lot.set(x); });
  }

  classer(origine: 'MOTEUR' | 'FICHIER'): void {
    const l = this.lot()!;
    const nb = origine === 'MOTEUR' ? l.evaluation?.classables ?? 0 : l.stats['avec_niveau'] ?? 0;
    const forcer = this.forcer && !!this.store.cap().classif_forcer;
    this.feedback.runWithReason(
      (motif) => this.api.post<Lot & { bilan: Bilan }>(`${CL_BASE}/lots/${l.id}/classer`, { origine, motif, forcer, confirmation: forcer }),
      {
        reason: {
          title: forcer ? 'Forçage de classification' : origine === 'MOTEUR' ? 'Enregistrer le niveau proposé' : 'Enregistrer la classe du fichier',
          message: `${forcer ? 'FORÇAGE — ' : ''}Enregistrer la classification de ${nb} client(s) du fichier « ${l.fichier_nom} » ?`,
          hint: forcer
            ? 'Les décisions manuelles seront remplacées. Action tracée dans l’audit (forçage). Les divergences fichier / moteur restent à traiter ligne par ligne.'
            : 'Les décisions manuelles sont préservées (un réexamen est ouvert si le niveau diffère). Les divergences ne sont pas écrites. Historique conservé.',
          reasonLabel: 'Motif', reasonPlaceholder: 'Ex. revue hebdomadaire KYC du 08/10/2026', maxLength: 500,
          confirmLabel: forcer ? 'Confirmer le forçage' : 'Enregistrer', tone: forcer ? 'danger' : 'primary',
        },
        busy: this.busy, loading: 'Enregistrement…',
        success: (x) => ({ title: 'Classification enregistrée', details: [
          { label: 'Écrits', value: String(x.bilan.ecrits) },
          { label: 'Inchangés', value: String(x.bilan.inchanges) },
          { label: 'Manuels préservés', value: String(x.bilan.manuels_preserves) },
          { label: 'Divergences à traiter', value: String(x.bilan.divergences_a_traiter ?? 0) },
          { label: 'Non classables', value: String(x.bilan.non_classables) },
        ] }),
        errorTitle: 'Enregistrement refusé', retry: false,
      },
    ).subscribe((x) => { this.filtre = ''; this.forcer = false; this.lot.set(x); this.chargerHistorique(); });
  }

  trancher(x: LigneLot, choix: 'MOTEUR' | 'FICHIER'): void {
    const l = this.lot()!;
    const niveau = choix === 'MOTEUR' ? x.moteur?.niveau : x.niveau_fichier;
    this.feedback.runWithReason(
      (motif) => this.api.post<Lot>(`${CL_BASE}/lots/${l.id}/divergences`, { decisions: [{ ligne: x.ligne, choix, motif }] }),
      {
        reason: {
          title: 'Traiter la divergence',
          message: `Racine ${x.racine} : fichier ${x.niveau_fichier ?? '—'}, moteur ${x.moteur?.niveau ?? '—'}. Retenir ${niveau} (${choix === 'MOTEUR' ? 'moteur' : 'fichier'}) ?`,
          hint: 'Décision manuelle motivée : auteur, date, niveau retenu et valeurs contradictoires conservés dans l’historique.',
          reasonLabel: 'Motif de la décision', maxLength: 500, confirmLabel: 'Retenir', tone: 'primary',
        },
        busy: this.busy, loading: 'Enregistrement de la décision…',
        success: { title: 'Divergence traitée', message: `Niveau retenu : ${niveau}` },
        errorTitle: 'Décision refusée', retry: false,
      },
    ).subscribe(() => this.recharger(l.page));
  }

  filtrer(statut: string): void {
    this.filtre = this.filtre === statut ? '' : statut;
    this.recharger();
  }

  conserverMoteur(x: LigneLot): void {
    const l = this.lot()!;
    const c = x.controle!;
    this.feedback.runWithReason(
      (commentaire) => this.decider(l, x, { choix: 'MOTEUR', justification: commentaire || null }),
      {
        reason: {
          title: 'Conserver le classement du moteur SCORE',
          message: `Racine ${x.racine} : fichier ${c.niveau_fichier}, moteur SCORE ${c.niveau_moteur}. Conserver ${c.niveau_moteur} ?`,
          hint: 'Décision de contrôle uniquement : la classification enregistrée n’est pas modifiée. Auteur, date et commentaire sont conservés.',
          reasonLabel: 'Commentaire (facultatif)', required: false, maxLength: 2000,
          confirmLabel: 'Conserver le classement SCORE', tone: 'primary', icon: 'verified',
        },
        busy: this.busy, loading: 'Enregistrement de la décision…',
        success: { title: 'Écart décidé', message: `Classement SCORE ${c.niveau_moteur} conservé. Aucune modification.` },
        errorTitle: 'Décision refusée', retry: false,
      },
    ).subscribe(() => this.recharger(l.page));
  }

  retenirFichier(x: LigneLot): void {
    const l = this.lot()!;
    const c = x.controle!;
    const forcer = c.niveau_moteur === 'INTERDIT' && !!this.store.cap().classif_forcer;
    this.feedback.runWithReason(
      (justification) => this.decider(l, x, { choix: 'FICHIER', justification, forcer, confirmation: forcer }),
      {
        reason: {
          title: forcer ? 'Forçage — retenir le niveau du fichier' : 'Retenir le niveau du fichier',
          message: `Racine ${x.racine} : moteur SCORE ${c.niveau_moteur}, fichier ${c.niveau_fichier}. Retenir ${c.niveau_fichier} ?`,
          hint: forcer
            ? 'Le moteur SCORE classe ce client INTERDIT (blocage). Retenir le fichier lève le blocage : forçage tracé dans l’audit. Le niveau calculé par le moteur reste conservé.'
            : 'Décision manuelle motivée : le niveau retenu remplace la classification en vigueur, le niveau calculé par le moteur SCORE reste conservé. Historique : auteur, date, justification.',
          reasonLabel: 'Justification', reasonPlaceholder: 'Ex. revue KYC du 08/10/2026 : activité réelle confirmée', required: true, maxLength: 2000,
          confirmLabel: forcer ? 'Confirmer le forçage' : 'Retenir le niveau du fichier', tone: forcer ? 'danger' : 'warn', icon: 'gavel',
        },
        busy: this.busy, loading: 'Enregistrement de la décision…',
        success: { title: 'Écart décidé', message: `Niveau du fichier ${c.niveau_fichier} retenu (décision manuelle).` },
        errorTitle: 'Décision refusée', retry: false,
      },
    ).subscribe(() => this.recharger(l.page));
  }

  private decider(l: Lot, x: LigneLot, corps: Record<string, unknown>) {
    return this.api.post<LigneLot>(`${CL_BASE}/lots/${l.id}/controle/decision`, { ligne: x.ligne, ...corps });
  }

  saisirDate(x: LigneLot, valeur: string): void {
    const l = this.lot()!;
    if ((valeur || null) === x.date_ouverture) return;
    this.feedback.run(() => this.api.post<LigneLot>(`${CL_BASE}/lots/${l.id}/date-ouverture`, { ligne: x.ligne, date_ouverture: valeur || null }), {
      busy: this.busy, loading: 'Enregistrement de la date…',
      success: { title: 'Date d’ouverture enregistrée', message: 'Relancez l’évaluation du lot pour recalculer le critère « Entreprise récente ».' },
      errorTitle: 'Date refusée', retry: false,
    }).subscribe((maj) => this.lot.update((cur) => cur && { ...cur, lignes: cur.lignes.map((y) => (y.ligne === maj.ligne ? maj : y)) }));
  }

  telechargerModele(): void {
    this.api.download(`${CL_BASE}/lots/modele.xlsx`).subscribe({
      next: (b) => telecharger(b, 'modele-import-hebdomadaire-classification.xlsx'),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Modèle indisponible')),
    });
  }

  exporter(): void {
    const l = this.lot()!;
    this.exporterId(l.id, l.fichier_nom);
  }

  exporterLot(h: LotResume): void {
    this.exporterId(h.id, h.fichier_nom);
  }

  private exporterId(id: string, nom: string): void {
    this.api.download(`${CL_BASE}/lots/${id}/export.xlsx`).subscribe({
      next: (b) => telecharger(b, `${nom.replace(/\.xlsx?m?$/i, '')}.xlsx`),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export impossible')),
    });
  }

  editer(h: LotResume): void {
    this.edition.set({ id: h.id, fichier_nom: h.fichier_nom, periode_reference: h.periode_reference ?? '' });
  }

  enregistrerEdition(): void {
    const ed = this.edition();
    if (!ed) return;
    this.feedback.run(() => this.api.patch<Lot>(`${CL_BASE}/lots/${ed.id}`, {
      fichier_nom: ed.fichier_nom, periode_reference: ed.periode_reference || null,
    }), {
      busy: this.busy, loading: 'Enregistrement…',
      success: { title: 'Lot modifié', details: [{ label: 'Fichier', value: ed.fichier_nom }] },
      errorTitle: 'Modification impossible',
    }).subscribe(() => {
      this.edition.set(null);
      this.chargerHistorique();
      const ouvert = this.lot();
      if (ouvert?.id === ed.id) this.ouvrirLot(ed.id);
    });
  }

  quitter(): void {
    this.lot.set(null);
    this.filtre = '';
    this.chargerHistorique();
  }

  fermer(): void {
    const l = this.lot();
    if (l) this.fermerId(l.id, l.fichier_nom, true);
  }

  fermerLot(h: LotResume): void {
    this.fermerId(h.id, h.fichier_nom, false);
  }

  private fermerId(id: string, nom: string, retour: boolean): void {
    this.feedback.run(() => this.api.post<void>(`${CL_BASE}/lots/${id}/fermer`, {}), {
      confirm: {
        title: `Fermer « ${nom} »`,
        message: 'Le fichier temporaire est retiré. Le lot reste consultable et exportable.',
        confirmLabel: 'Fermer',
        tone: 'primary',
        icon: 'lock',
      },
      busy: this.busy, success: { title: 'Lot fermé' }, errorTitle: 'Fermeture impossible',
    }).subscribe(() => {
      if (retour) this.quitter();
      else this.chargerHistorique();
    });
  }

  supprimer(): void {
    const l = this.lot();
    if (l) this.supprimerId(l.id, l.fichier_nom, true);
  }

  supprimerLot(h: LotResume): void {
    this.supprimerId(h.id, h.fichier_nom, false);
  }

  private supprimerId(id: string, nom: string, retour: boolean): void {
    this.feedback.runWithReason(
      (motif) => this.api.delete<void>(`${CL_BASE}/lots/${id}?motif=${encodeURIComponent(motif)}`),
      {
        reason: {
          title: `Supprimer « ${nom} »`,
          message: 'Le lot et ses lignes seront définitivement retirés. Les classifications déjà enregistrées sur les fiches clients sont conservées.',
          hint: 'Irréversible. Le motif est conservé dans l’audit.',
          reasonLabel: 'Motif de suppression',
          maxLength: 2000,
          confirmLabel: 'Supprimer définitivement',
          tone: 'danger',
          icon: 'delete_forever',
        },
        busy: this.busy,
        loading: 'Suppression…',
        success: { title: 'Lot supprimé', details: [{ label: 'Fichier', value: nom }] },
        errorTitle: 'Suppression impossible',
      },
    ).subscribe(() => {
      this.edition.set(null);
      if (retour) this.quitter();
      else this.chargerHistorique();
    });
  }
}
