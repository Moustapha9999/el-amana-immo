import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClExportComponent } from '../cl-export.component';
import {
  ApercuIntegration, CL_BASE, ETATS_PROPOSITION, LIB_INTEGRATION, LIB_PREPARATION, LigneHebdo, LotHebdo,
  SOURCES_MANUELLES, STATUTS_CLIENT, STATUTS_DECISION, dateFr, dateHeureFr, n, telecharger,
} from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

export type ModeHebdo = 'import' | 'lot' | 'historique';

interface LotResume {
  id: string; fichier_nom: string; type: string; statut: string; periode_reference: string | null;
  stats: Record<string, number>; created_at: string | null; actions?: Record<string, boolean>;
}
interface Bilan {
  lot: { fichier_nom: string; importe_par: string | null; importe_le: string | null; sha256: string; fichier_disponible: boolean };
  stats: Record<string, number>; decisions: Record<string, number>; operations: Record<string, number>;
  groupes: number; clients_crees: number;
}
interface BilanIntegration {
  integrees: number; clients_crees: number; clients_mis_a_jour: number; non_integrees: number; erreurs: number;
  deja_integrees: number; par_nom?: string | null; le?: string | null;
}
type Preparation = 'ACCEPTER' | 'MODIFIER' | 'REJETER' | 'ATTENTE';
interface Filtre { code: string; libelle: string; compte?: (s: Record<string, number>) => number | undefined }

const somme = (...cles: string[]) => (s: Record<string, number>) =>
  cles.some((c) => s[c] !== undefined) ? cles.reduce((t, c) => t + (s[c] || 0), 0) : undefined;
const cle = (c: string) => (s: Record<string, number>) => s[c];

const FILTRES_IMPORT: Filtre[] = [
  { code: '', libelle: 'Toutes', compte: cle('lignes') },
  { code: 'NOUVEAU', libelle: 'Nouveaux clients', compte: cle('nouveaux') },
  { code: 'AMBIGU', libelle: 'Identités ambiguës', compte: cle('ambigus') },
  { code: 'CONTRADICTION', libelle: 'Contradictions ORION', compte: cle('contradictions') },
  { code: 'DOUBLON', libelle: 'Doublons', compte: cle('doublons') },
  { code: 'INVALIDE', libelle: 'Invalides', compte: cle('invalides') },
  { code: 'ANALYSTE', libelle: 'Analyste absent / inconnu', compte: somme('analyste_absent', 'analyste_inconnu') },
  { code: 'MANQUANTS', libelle: 'Champs manquants', compte: cle('avec_manquants') },
  { code: 'CONFLITS', libelle: 'Conflits avec la base', compte: cle('conflits_base') },
  { code: 'INTEGREE', libelle: 'Intégrées', compte: cle('integrees') },
  { code: 'NON_INTEGREE', libelle: 'Non intégrées' },
];
const FILTRES_LOT: Filtre[] = [
  { code: '', libelle: 'Toutes', compte: cle('lignes') },
  { code: 'EN_ATTENTE', libelle: 'À décider', compte: cle('en_attente') },
  { code: 'PREPAREE', libelle: 'Décisions préparées', compte: cle('preparees') },
  { code: 'ATTENTE_ANALYSTE', libelle: 'En attente analyste' },
  { code: 'PROPOSE', libelle: 'Proposées', compte: cle('proposition_propose') },
  { code: 'A_VERIFIER', libelle: 'À vérifier', compte: cle('proposition_a_verifier') },
  { code: 'NON_CLASSIFIABLE', libelle: 'Non classifiables', compte: cle('proposition_non_classifiable') },
  { code: 'A_EVALUER', libelle: 'Sans calcul moteur', compte: cle('proposition_a_evaluer') },
  { code: 'ANALYSTE', libelle: 'Analyste absent / inconnu', compte: somme('analyste_absent', 'analyste_inconnu') },
  { code: 'DECIDEE', libelle: 'Décidées', compte: somme('acceptees', 'modifiees', 'rejetees') },
];
const PROFILS: Record<string, string> = { PP: 'PP', PM: 'PM', NON_IDENTIFIE: 'Non identifié' };
const NIVEAUX = ['FAIBLE', 'MOYEN', 'ELEVE', 'INTERDIT'];
const MAX_SELECTION = 200;
const LIB_LOT: Record<string, string> = { ANALYSE: 'Analysé', EVALUE: 'Évalué', ENREGISTRE: 'Tout décidé', FERME: 'Fermé' };
const LIB_ANALYSTE: Record<string, string> = { ABSENT: 'Absent', INCONNU: 'Inconnu', RECONNU: 'Reconnu' };

@Component({
  selector: 'bea-cl-hebdo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClExportComponent],
  styles: `
    .bea-hb-table { table-layout: fixed; width: 100%; }
    .bea-hb-table th, .bea-hb-table td { padding: 0.6rem 0.7rem; }
    .bea-hb-table th { white-space: normal; line-height: 1.25; vertical-align: bottom; }
    .bea-hb-table td { vertical-align: top; overflow-wrap: anywhere; }
    .bea-hb-table td code, .bea-hb-table td .bea-cl-badge { white-space: nowrap; overflow-wrap: normal; }
    .bea-hb-table input[type='checkbox'] { width: auto; }
    .bea-hb-table .w-chk { width: 2.75rem; }
    .bea-hb-table .w-l { width: 3.25rem; }
    .bea-hb-table .w-racine { width: 7.5rem; }
    .bea-hb-table .w-profil { width: 7rem; }
    .bea-hb-table .w-id { width: 13rem; }
    .bea-hb-table .w-classe { width: 8.5rem; }
    .bea-hb-table .w-prop { width: 14rem; }
    .bea-hb-table .w-statut { width: 9.5rem; }
    .bea-hb-table .w-analyste { width: 9.5rem; }
    .bea-hb-table .w-motif { width: 10rem; }
    .bea-hb-table .w-date { width: 9.5rem; }
    .bea-hb-table .w-act { width: 15.5rem; position: sticky; right: 0; z-index: 1; background: #fff; box-shadow: -8px 0 10px -8px rgba(15, 23, 42, 0.25); }
    .bea-hb-table thead .w-act { z-index: 2; background: #f8fafc; }
    .bea-hb-table tr.is-sel td { background: #eff6ff; }
    .bea-hb-table tr.is-prep td { background: #f0fdf4; }
    :host-context(html[data-theme='dark']) .bea-hb-table .w-act { background: #1f1f1f; }
    :host-context(html[data-theme='dark']) .bea-hb-table thead .w-act { background: #152332; }
    .bea-hb-actions { display: flex; gap: 0.3rem; flex-wrap: wrap; align-items: center; }
    .bea-hb-actions select { width: auto; min-width: 9rem; flex: 1 1 9rem; }
    .bea-hb-actions button { display: inline-flex; align-items: center; gap: 0.2rem; font: inherit; font-size: 0.78rem; font-weight: 600; padding: 0.3rem 0.55rem; border-radius: 0.45rem; border: 1px solid #cbd5e1; background: #fff; color: #0f172a; cursor: pointer; }
    .bea-hb-actions button mat-icon { font-size: 1rem; width: 1rem; height: 1rem; }
    .bea-hb-actions button.is-ok { border-color: #16a34a; color: #166534; }
    .bea-hb-actions button.is-ko { border-color: #dc2626; color: #991b1b; }
    .bea-hb-actions button:disabled { opacity: 0.45; cursor: not-allowed; }
    .bea-hb-actions select { font: inherit; font-size: 0.78rem; padding: 0.25rem; border: 1px solid #cbd5e1; border-radius: 0.45rem; }
    .bea-hb-raison { display: block; max-width: 22rem; font-size: 0.75rem; color: #64748b; white-space: normal; }
    .bea-hb-alerte { display: block; max-width: 22rem; font-size: 0.75rem; color: #9a3412; white-space: normal; }
    .bea-hb-table .bea-hb-raison, .bea-hb-table .bea-hb-alerte { max-width: none; margin-top: 0.2rem; line-height: 1.3; }
    .bea-hb-groupe { position: sticky; bottom: 0; display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; padding: 0.7rem 1.1rem; background: #0f2a43; color: #fff; border-radius: 0.75rem; margin-top: 0.6rem; z-index: 2; }
    .bea-hb-groupe .bea-mg__btn { background: #fff; }
    .bea-hb-groupe select { font: inherit; font-size: 0.82rem; padding: 0.35rem; border-radius: 0.45rem; }
    .bea-hb-confirmer { background: #ecfdf5; color: #064e3b; border: 1px solid #10b981; }
    .bea-hb-confirmer .bea-mg__btn { background: #fff; }
    .bea-hb-filtres { display: flex; gap: 0.35rem; flex-wrap: wrap; padding: 0 1.1rem 0.7rem; }
    .bea-hb-filtres button { font: inherit; font-size: 0.78rem; padding: 0.3rem 0.65rem; border-radius: 999px; border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
    .bea-hb-filtres button.is-on { background: #1a5278; color: #fff; border-color: #1a5278; }
    .bea-hb-analyste { display: flex; align-items: end; gap: 0.75rem; flex-wrap: wrap; padding: 0 1.1rem 0.8rem; }
    .bea-hb-analyste label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.72rem; font-weight: 700; color: #64748b; text-transform: uppercase; }
    .bea-hb-analyste select { font: inherit; font-size: 0.88rem; text-transform: none; min-width: 16rem; padding: 0.45rem 0.6rem; border: 1px solid #cbd5e1; border-radius: 0.55rem; }
    .bea-hb-recap { margin: 0 1.1rem 1rem; padding: 1rem 1.1rem; border: 1px solid #93c5fd; border-radius: 0.75rem; background: #f8fbff; }
    .bea-hb-recap h3 { margin: 0 0 0.6rem; font-size: 1rem; }
    .bea-hb-recap ul { margin: 0.4rem 0 0.8rem; padding-left: 1.1rem; font-size: 0.84rem; color: #334155; }
    .bea-hb-recap__btns { display: flex; gap: 0.5rem; justify-content: flex-end; flex-wrap: wrap; }
    tr.is-sel td { background: #eff6ff; }
    tr.is-prep td { background: #f0fdf4; }
  `,
  template: `
    @if (!lot()) {
      @if (mode() !== 'historique' && peutDeposer()) {
        <section class="bea-mg__panel" style="padding:1rem">
          <div class="bea-mg__panel-top" style="padding:0 0 0.6rem">
            <h2>{{ mode() === 'lot' ? 'Téléverser un fichier à classifier' : 'Importer la liste hebdomadaire' }}</h2>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="modele()" [disabled]="busy()"><mat-icon>table_view</mat-icon> Modèle Excel</button>
          </div>
          <div class="bea-cl-filters" style="padding:0 0 0.75rem">
            <label>Semaine / période de référence <input type="date" [(ngModel)]="periode" /></label>
          </div>
          <label class="bea-fx-dropzone" [class.is-over]="survol()" (dragover)="$event.preventDefault(); survol.set(true)" (dragleave)="survol.set(false)" (drop)="deposer($event)">
            <input type="file" accept=".xlsx,.xlsm" hidden (change)="choisir($any($event.target))" />
            @if (busy()) {
              <mat-icon class="bea-cl-spin">progress_activity</mat-icon><strong>Contrôle du fichier…</strong>
            } @else {
              <mat-icon>upload_file</mat-icon><strong>Déposez le fichier Excel de la semaine (feuille CLIENTS)</strong>
              <span>.xlsx, 40 Mo maximum. Contrôle de structure, rapprochement par racine (zéros de tête conservés), aperçu détaillé — rien n’est écrit avant votre confirmation.</span>
            }
          </label>
        </section>
      }
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>{{ mode() === 'lot' ? 'Fichiers à classifier' : mode() === 'historique' ? 'Historique des imports' : 'Derniers imports' }}</h2>
          <span class="bea-cl-actions">
            <span class="bea-mg__count">{{ listeLots().length }}</span>
            @if (mode() === 'historique') {
              <bea-cl-export [chemin]="base + '/lots/export'" libelle="Historique des imports" nomFichier="historique-imports" />
            }
          </span>
        </div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Déposé le</th><th>Fichier</th><th>Période</th><th>Lignes</th><th>Nouveaux</th><th>Intégrées</th><th>À décider</th><th>Décidées</th><th>Statut</th><th></th></tr></thead>
            <tbody>
              @for (h of listeLots(); track h.id) {
                <tr style="cursor:pointer" (click)="choisirLot(h.id)">
                  <td>{{ dh(h.created_at) }}</td>
                  <td><strong>{{ h.fichier_nom }}</strong></td>
                  <td>{{ df(h.periode_reference) }}</td>
                  <td>{{ n(h.stats['lignes']) }}</td>
                  <td>{{ n(h.stats['nouveaux']) }}</td>
                  <td>{{ h.stats['integrees'] === undefined ? '—' : n(h.stats['integrees']) }}</td>
                  <td>{{ h.stats['en_attente'] === undefined ? '—' : n(h.stats['en_attente']) }}</td>
                  <td>{{ n((h.stats['acceptees'] || 0) + (h.stats['modifiees'] || 0) + (h.stats['rejetees'] || 0)) }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="h.statut">{{ libLot[h.statut] || h.statut }}</span></td>
                  <td (click)="$event.stopPropagation()" style="white-space:nowrap">
                    @if (mode() === 'historique') {
                      <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/clientele/import-hebdo']" [queryParams]="{ lot: h.id }" title="Aperçu et intégration"><mat-icon>upload_file</mat-icon></a>
                      <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/clientele/classification-lot']" [queryParams]="{ lot: h.id }" title="Classification par lot"><mat-icon>rule</mat-icon></a>
                    } @else {
                      <mat-icon>chevron_right</mat-icon>
                    }
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="10"><div class="bea-cl-empty"><mat-icon>history</mat-icon>Aucun import hebdomadaire.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
        @if (mode() === 'import' && historique().length > listeLots().length) {
          <p class="bea-cl-hint" style="padding:0.6rem 1.1rem"><a routerLink="/clientele/imports-historique">Voir tout l’historique des imports ({{ historique().length }})</a></p>
        }
      </section>
    } @else {
      @let l = lot()!;
      @let s = l.stats;
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <div>
            <h2>{{ l.fichier_nom }}</h2>
            <p class="bea-cl-hint">Période {{ df(l.periode_reference) }} · déposé le {{ dh(l.created_at) }} · <span class="bea-cl-badge" [attr.data-s]="l.statut_lot">{{ libLot[l.statut_lot] || l.statut_lot }}</span></p>
          </div>
          <span style="display:flex;gap:0.4rem;flex-wrap:wrap">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerVue()"><mat-icon>arrow_back</mat-icon> {{ mode() === 'lot' ? 'Fichiers' : 'Imports' }}</button>
            @if (mode() === 'import') {
              @if (store.cap().imports_executer && l.statut_lot !== 'FERME') {
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="preparerIntegration()" [disabled]="busy()"><mat-icon>playlist_add_check</mat-icon> Intégrer dans la Base Clientèle</button>
              }
              <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/clientele/classification-lot']" [queryParams]="{ lot: l.id }"><mat-icon>rule</mat-icon> Classifier ce lot</a>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="rejetsXlsx()" [disabled]="busy()"><mat-icon>report</mat-icon> Rapport des rejets</button>
            } @else {
              @if (store.cap().classif_voir && l.statut_lot !== 'FERME' && (s['proposition_a_evaluer'] || 0) > 0) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="evaluer()" [disabled]="busy()"><mat-icon>calculate</mat-icon> Exécuter le moteur ({{ n(s['proposition_a_evaluer']) }})</button>
              }
              <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/clientele/import-hebdo']" [queryParams]="{ lot: l.id }"><mat-icon>upload_file</mat-icon> Aperçu de l’import</a>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="chargerBilan()" [disabled]="busy()"><mat-icon>summarize</mat-icon> Bilan</button>
            }
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="bilanXlsx()" [disabled]="busy()"><mat-icon>download</mat-icon> Export Excel</button>
            @if (l.fichier_disponible) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fichierOrigine()" [disabled]="busy()"><mat-icon>attach_file</mat-icon> Fichier importé</button>
            }
            @if (l.statut_lot !== 'FERME') {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerLot()" [disabled]="busy()"><mat-icon>lock</mat-icon> Fermer</button>
            }
          </span>
        </div>
        @if (l.message) { <div class="bea-cl-note bea-cl-note--info" style="margin:0 1.1rem 0.8rem"><mat-icon>info</mat-icon><span>{{ l.message }}</span></div> }
        @if (colonnesManquantes().length) {
          <div class="bea-cl-note bea-cl-note--warn" style="margin:0 1.1rem 0.8rem"><mat-icon>warning</mat-icon>
            <span>Colonne(s) obligatoire(s) non reconnue(s) : <strong>{{ colonnesManquantes().join(', ') }}</strong>. Les lignes concernées ne seront pas intégrées.</span>
          </div>
        }

        @if (mode() === 'import') {
          <div class="bea-cl-stats">
            <div class="bea-cl-stat"><span>Lignes reçues</span><strong>{{ n(s['lignes']) }}</strong></div>
            <div class="bea-cl-stat"><span>Nouveaux clients</span><strong>{{ n(s['nouveaux']) }}</strong></div>
            <div class="bea-cl-stat" data-tone="ok"><span>Clients existants</span><strong>{{ n(s['racines_ok']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="s['doublons'] ? 'danger' : ''"><span>Doublons</span><strong>{{ n(s['doublons']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="s['invalides'] ? 'danger' : ''"><span>Invalides</span><strong>{{ n(s['invalides']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="(s['ambigus'] || 0) + (s['contradictions'] || 0) ? 'warn' : ''"><span>Identités ambiguës</span><strong>{{ n((s['ambigus'] || 0) + (s['contradictions'] || 0)) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="s['avec_manquants'] ? 'warn' : ''"><span>Champs manquants</span><strong>{{ n(s['avec_manquants']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="s['conflits_base'] ? 'warn' : ''"><span>Conflits avec la base</span><strong>{{ n(s['conflits_base']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="(s['analyste_absent'] || 0) + (s['analyste_inconnu'] || 0) ? 'danger' : ''"><span>Analyste absent / inconnu</span><strong>{{ n((s['analyste_absent'] || 0) + (s['analyste_inconnu'] || 0)) }}</strong></div>
            <div class="bea-cl-stat" data-tone="ok"><span>Intégrées</span><strong>{{ n(s['integrees']) }}</strong></div>
          </div>
          @if (s['absents_du_fichier'] !== undefined) {
            <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">{{ n(s['absents_du_fichier']) }} client(s) de la Base Clientèle absent(s) de ce fichier : ils sont conservés tels quels (ni supprimés, ni désactivés).</p>
          }
          @if (integration(); as b) {
            <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">Dernière intégration : {{ n(b.integrees) }} ligne(s) intégrée(s) — {{ n(b.clients_crees) }} client(s) créé(s), {{ n(b.clients_mis_a_jour) }} mis à jour, {{ n(b.non_integrees) }} non intégrée(s), {{ n(b.erreurs) }} erreur(s) · {{ b.par_nom || '—' }} · {{ dh(b.le) }}</p>
          }
          @if (apercu(); as a) {
            <div class="bea-hb-recap" role="region" aria-label="Récapitulatif avant intégration">
              <h3>Récapitulatif avant intégration</h3>
              <div class="bea-cl-stats" style="padding:0">
                <div class="bea-cl-stat"><span>Clients à créer</span><strong>{{ n(a.a_creer) }}</strong></div>
                <div class="bea-cl-stat"><span>Clients à mettre à jour</span><strong>{{ n(a.a_mettre_a_jour) }}</strong></div>
                <div class="bea-cl-stat"><span>Inchangés</span><strong>{{ n(a.inchangees) }}</strong></div>
                <div class="bea-cl-stat"><span>Déjà intégrées</span><strong>{{ n(a.deja_integrees) }}</strong></div>
                <div class="bea-cl-stat" [attr.data-tone]="a.non_integrables ? 'warn' : ''"><span>Non intégrées</span><strong>{{ n(a.non_integrables) }}</strong></div>
              </div>
              @if (champsApercu().length) {
                <p class="bea-cl-hint">Champs mis à jour : {{ champsApercu().join(' · ') }}</p>
              }
              <ul>@for (r of a.regles; track r) { <li>{{ r }}</li> }</ul>
              @if (a.details_non_integrables.length) {
                <p class="bea-cl-hint"><strong>Lignes non intégrées</strong> (extrait — le détail complet est dans le rapport des rejets) :</p>
                <ul>
                  @for (d of a.details_non_integrables.slice(0, 15); track d.ligne) {
                    <li>Ligne {{ d.ligne }} · <code>{{ d.racine || '—' }}</code> {{ d.nom || '' }} — {{ d.raison }}</li>
                  }
                </ul>
              }
              <div class="bea-hb-recap__btns">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="apercu.set(null)">Annuler</button>
                @if (a.details_non_integrables.length) {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="rejetsXlsx()" [disabled]="busy()"><mat-icon>report</mat-icon> Rapport des rejets</button>
                }
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="integrer()" [disabled]="busy() || !(a.a_creer + a.a_mettre_a_jour + a.inchangees)"><mat-icon>done_all</mat-icon> Confirmer l’intégration</button>
              </div>
            </div>
          }
        } @else {
          <div class="bea-cl-stats">
            <div class="bea-cl-stat"><span>Lignes</span><strong>{{ n(s['lignes']) }}</strong></div>
            <div class="bea-cl-stat" data-tone="warn"><span>À décider</span><strong>{{ n(s['en_attente']) }}</strong></div>
            <div class="bea-cl-stat"><span>Décisions préparées</span><strong>{{ n(s['preparees']) }}</strong></div>
            <div class="bea-cl-stat" data-tone="ok"><span>Acceptées</span><strong>{{ n(s['acceptees']) }}</strong></div>
            <div class="bea-cl-stat" data-tone="ok"><span>Classes manuelles</span><strong>{{ n(s['modifiees']) }}</strong></div>
            <div class="bea-cl-stat"><span>Rejetées</span><strong>{{ n(s['rejetees']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="(s['analyste_absent'] || 0) + (s['analyste_inconnu'] || 0) ? 'danger' : ''"><span>Analyste absent / inconnu</span><strong>{{ n((s['analyste_absent'] || 0) + (s['analyste_inconnu'] || 0)) }}</strong></div>
          </div>
          @if (bilan(); as b) {
            <div class="bea-mg__panel-top"><h2>Bilan du lot</h2>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="bilan.set(null)"><mat-icon>close</mat-icon></button>
            </div>
            <dl class="bea-cl-dl">
              <dt>Importé par</dt><dd>{{ b.lot.importe_par || '—' }} · {{ dh(b.lot.importe_le) }}</dd>
              <dt>Empreinte</dt><dd><code>{{ b.lot.sha256.slice(0, 16) }}…</code></dd>
              <dt>Décisions</dt><dd>{{ n(b.decisions['ACCEPTEE']) }} acceptée(s) · {{ n(b.decisions['MODIFIEE']) }} modifiée(s) · {{ n(b.decisions['REJETEE']) }} rejetée(s) · {{ n(b.decisions['EN_ATTENTE']) }} en attente</dd>
              <dt>Confirmations groupées</dt><dd>{{ n(b.groupes) }}</dd>
            </dl>
          }
        }

        <div class="bea-hb-filtres" role="tablist" aria-label="Filtrer les lignes">
          @for (f of filtres(); track f.code) {
            @let c = f.compte ? f.compte(s) : undefined;
            <button type="button" [class.is-on]="filtre() === f.code" (click)="filtrer(f.code)">{{ f.libelle }}@if (c !== undefined) { ({{ n(c) }})}</button>
          }
        </div>
        <div class="bea-cl-filters" style="padding:0 1.1rem 0.7rem">
          <label>Recherche
            <input [(ngModel)]="q" (keyup.enter)="charger(1)" placeholder="Racine, nom ou analyste" />
          </label>
          <label>PP / PM
            <select [(ngModel)]="profil" (ngModelChange)="charger(1)">
              <option value="">Tous</option>
              @for (p of profils; track p[0]) { <option [value]="p[0]">{{ p[1] }}</option> }
            </select>
          </label>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger(1)"><mat-icon>search</mat-icon> Rechercher</button>
        </div>

        @if (peutDecider()) {
          <div class="bea-hb-analyste">
            <label>Analyste KYC des décisions
              <select [(ngModel)]="analyste">
                <option value="">Analyste indiqué dans le fichier</option>
                @for (a of analystes(); track a) { <option [value]="a">{{ a }}</option> }
              </select>
            </label>
            <p class="bea-cl-hint" style="margin:0">Analyste obligatoire et présent dans le référentiel (Classification › Analystes KYC). Les décisions sont d’abord préparées, puis enregistrées à la confirmation globale.</p>
          </div>
        }

        <div class="bea-mg__table-wrap">
          @if (mode() === 'import') {
            <table class="bea-mg__table bea-hb-table">
              <thead><tr><th class="w-l">L.</th><th class="w-racine">Racine</th><th class="w-id">Identité</th><th class="w-profil">PP/PM</th><th class="w-prop">Client</th><th class="w-analyste">Analyste KYC</th><th class="w-motif">Champs manquants</th><th class="w-prop">Conflits avec la base</th><th class="w-statut">Intégration</th></tr></thead>
              <tbody>
                @for (x of l.lignes; track x.ligne) {
                  <tr>
                    <td>{{ x.ligne }}</td>
                    <td>@if (x.racine && x.statut === 'OK') { <a [routerLink]="['/clientele/clients', x.racine]"><code>{{ x.racine }}</code></a> } @else { <code>{{ x.racine || x.brut || '—' }}</code> }</td>
                    <td>{{ x.nom || '—' }}</td>
                    <td>{{ profilLib(x.profil) }}</td>
                    <td><span class="bea-cl-badge" [attr.data-s]="x.statut_client">{{ statutsClient[x.statut_client] || x.statut_client }}</span>
                      @for (v of x.identite; track v) { <small class="bea-hb-raison">{{ v }}</small> }
                      @for (v of x.verification; track v) { <small class="bea-hb-alerte">{{ v }}</small> }
                      @for (v of x.anomalies; track v) { <small class="bea-hb-raison">{{ v }}</small> }
                    </td>
                    <td>
                      @if (x.analyste_controle; as a) {
                        @if (a.etat === 'RECONNU') { {{ a.nom }} } @else {
                          <span class="bea-cl-badge" data-s="A_VERIFIER">{{ libAnalyste[a.etat] }}</span>
                          @if (a.brut) { <small class="bea-hb-raison">« {{ a.brut }} »</small> }
                        }
                      } @else { {{ x.analyste || '—' }} }
                    </td>
                    <td>@if (x.manquants?.length) { <small class="bea-hb-alerte">{{ x.manquants!.join(', ') }}</small> } @else { — }</td>
                    <td>@if (x.conflits?.length) { @for (c of x.conflits!; track c) { <small class="bea-hb-alerte">{{ c }}</small> } } @else { — }</td>
                    <td>
                      @if (x.integration; as i) {
                        <span class="bea-cl-badge" [attr.data-s]="i.etat === 'INTEGREE' ? 'OK' : 'A_VERIFIER'">{{ libIntegration[i.etat] || i.etat }}</span>
                        @if (i.client_cree) { <small class="bea-hb-raison">fiche créée</small> }
                        @if (i.maj_donnees?.length) { <small class="bea-hb-raison">{{ i.maj_donnees!.join(', ') }}</small> }
                        @if (i.raison) { <small class="bea-hb-raison">{{ i.raison }}</small> }
                      } @else { <small class="bea-cl-hint">Non intégrée</small> }
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="9"><div class="bea-cl-empty">Aucune ligne pour ce filtre.</div></td></tr>
                }
              </tbody>
            </table>
          } @else {
            <table class="bea-mg__table bea-hb-table">
              <thead><tr>
                @if (peutDecider()) { <th class="w-chk"><input type="checkbox" [checked]="toutSelectionne()" (change)="toutSelectionner($any($event.target).checked)" aria-label="Tout sélectionner" /></th> }
                <th class="w-l">L.</th><th class="w-racine">Racine</th><th class="w-profil">PP/PM</th><th class="w-id">Identité</th><th class="w-classe">Classe précédente</th><th class="w-classe">Classe moteur</th><th class="w-prop">Classe proposée</th><th class="w-classe">Classe retenue</th><th class="w-statut">Statut</th><th class="w-analyste">Analyste</th><th class="w-motif">Motif</th><th class="w-date">Date</th>
                @if (peutDecider()) { <th class="w-act">Actions</th> }
              </tr></thead>
              <tbody>
                @for (x of l.lignes; track x.ligne) {
                  @let p = x.proposition;
                  @let d = x.decision_ligne;
                  @let prep = x.statut_decision === 'EN_ATTENTE' ? x.preparation : null;
                  <tr [class.is-sel]="selection().has(x.ligne)" [class.is-prep]="!!prep && prep.decision !== 'ATTENTE'">
                    @if (peutDecider()) {
                      <td><input type="checkbox" [disabled]="x.statut_decision !== 'EN_ATTENTE'" [checked]="selection().has(x.ligne)" (change)="basculer(x.ligne)" aria-label="Sélectionner" /></td>
                    }
                    <td>{{ x.ligne }}</td>
                    <td>@if (x.racine && x.statut === 'OK') { <a [routerLink]="['/clientele/clients', x.racine]"><code>{{ x.racine }}</code></a> } @else { <code>{{ x.racine || x.brut || '—' }}</code> }
                      @if (x.statut !== 'OK') { <small class="bea-hb-raison">{{ statutsClient[x.statut_client] || x.statut_client }}</small> }
                    </td>
                    <td>{{ profilLib(x.profil) }}</td>
                    <td>{{ x.nom || '—' }}</td>
                    <td>
                      @let prec = d?.classe_precedente !== undefined ? d?.classe_precedente : x.classe_actuelle;
                      @if (prec) { <span class="bea-cl-badge" [attr.data-s]="prec">{{ prec }}</span> @if (!d && x.source_actuelle) { <small class="bea-cl-hint">{{ x.source_actuelle }}</small> } } @else { — }
                    </td>
                    <td>@if (p.statut_moteur) { <span class="bea-cl-badge" [attr.data-s]="p.niveau_moteur">{{ p.niveau_moteur || 'NON CLASSÉ' }}</span> <small class="bea-hb-raison">{{ p.statut_moteur }}</small> } @else { <small class="bea-cl-hint">non calculée</small> }</td>
                    <td>
                      @if (p.niveau) { <span class="bea-cl-badge" [attr.data-s]="p.niveau">{{ p.niveau }}</span> }
                      <small class="bea-hb-raison">{{ etats[p.etat] || p.etat }}{{ p.origine ? ' · ' + (p.origine === 'FICHIER' ? 'fichier' : 'moteur') : '' }}</small>
                      @if (p.raison) { <small class="bea-hb-raison">{{ p.raison }}</small> }
                    </td>
                    <td>
                      @if (d?.niveau) { <span class="bea-cl-badge" [attr.data-s]="d!.niveau">{{ d!.niveau }}</span> }
                      @else if (prep?.niveau) { <span class="bea-cl-badge" [attr.data-s]="prep!.niveau">{{ prep!.niveau }}</span> <small class="bea-hb-raison">à confirmer</small> }
                      @else { — }
                    </td>
                    <td>
                      <span class="bea-cl-badge" [attr.data-s]="x.statut_decision">{{ statutsDecision[x.statut_decision] || x.statut_decision }}</span>
                      @if (prep) { <small class="bea-hb-raison"><strong>{{ libPreparation[prep.decision] }}</strong>{{ prep.decision === 'ATTENTE' ? '' : ' — préparée' }}</small> }
                      @if (d?.client_cree) { <small class="bea-hb-raison">fiche créée</small> }
                    </td>
                    <td>
                      {{ d?.analyste_kyc || prep?.analyste_kyc || x.analyste_controle?.nom || x.analyste || '—' }}
                      @if (!d && x.analyste_controle && x.analyste_controle.etat !== 'RECONNU') { <small class="bea-hb-alerte">{{ libAnalyste[x.analyste_controle.etat] }}</small> }
                    </td>
                    <td>@if (d?.motif || prep?.motif) { <small class="bea-hb-raison">« {{ d?.motif || prep?.motif }} »</small> } @else { — }</td>
                    <td>@if (d) { {{ dh(d.le) }} <small class="bea-hb-raison">{{ d.par_nom }}</small> } @else if (prep) { <small class="bea-hb-raison">préparée {{ dh(prep.le) }} · {{ prep.par_nom }}</small> } @else { — }</td>
                    @if (peutDecider()) {
                      <td class="w-act">
                        @if (x.statut_decision === 'EN_ATTENTE') {
                          <div class="bea-hb-actions">
                            @if (p.niveau && (x.statut === 'OK' || x.statut === 'INCONNUE')) {
                              <button type="button" class="is-ok" (click)="preparer([x], 'ACCEPTER')" [disabled]="busy()" title="Accepter la classe proposée"><mat-icon>check</mat-icon> Accepter</button>
                            }
                            @if (x.statut === 'OK' || x.statut === 'INCONNUE') {
                              <select [(ngModel)]="niveaux[x.ligne]" aria-label="Classe manuelle">
                                <option [ngValue]="undefined">Classe manuelle…</option>
                                @for (nv of niveauxListe; track nv) { <option [ngValue]="nv">{{ nv }}</option> }
                              </select>
                              <button type="button" (click)="preparer([x], 'MODIFIER')" [disabled]="busy() || !niveaux[x.ligne]" title="Classe manuelle (motif obligatoire)"><mat-icon>edit</mat-icon></button>
                            }
                            <button type="button" (click)="preparer([x], 'ATTENTE')" [disabled]="busy()" title="Laisser en attente d’un analyste"><mat-icon>schedule</mat-icon></button>
                            <button type="button" class="is-ko" (click)="preparer([x], 'REJETER')" [disabled]="busy()" title="Rejeter (motif obligatoire)"><mat-icon>close</mat-icon></button>
                          </div>
                        }
                      </td>
                    }
                  </tr>
                } @empty {
                  <tr><td [attr.colspan]="peutDecider() ? 14 : 12"><div class="bea-cl-empty">Aucune ligne pour ce filtre.</div></td></tr>
                }
              </tbody>
            </table>
          }
        </div>
        @if (l.total_filtre > l.taille) {
          <div class="bea-cl-pager">
            <span>{{ n(l.total_filtre) }} ligne(s) · page {{ l.page }} / {{ n(nbPages()) }}</span>
            <span class="bea-cl-pager__btns">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="l.page <= 1" (click)="charger(l.page - 1)"><mat-icon>chevron_left</mat-icon> Précédent</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="l.page >= nbPages()" (click)="charger(l.page + 1)">Suivant <mat-icon>chevron_right</mat-icon></button>
            </span>
          </div>
        }
        @if (mode() === 'lot' && peutDecider()) {
          @if (selection().size) {
            <div class="bea-hb-groupe">
              <span><strong>{{ selection().size }}</strong> ligne(s) sélectionnée(s) — préparer une décision (max {{ maxSelection }}).</span>
              <span style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="toutSelectionner(false)">Vider</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="preparerSelection('ATTENTE')" [disabled]="busy()"><mat-icon>schedule</mat-icon> En attente</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="preparerSelection('REJETER')" [disabled]="busy()"><mat-icon>close</mat-icon> Rejeter</button>
                <select [(ngModel)]="niveauGroupe" aria-label="Classe manuelle pour la sélection">
                  <option [ngValue]="''">Classe manuelle…</option>
                  @for (nv of niveauxListe; track nv) { <option [ngValue]="nv">{{ nv }}</option> }
                </select>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="preparerSelection('MODIFIER')" [disabled]="busy() || !niveauGroupe"><mat-icon>edit</mat-icon> Appliquer</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="preparerSelection('ACCEPTER')" [disabled]="busy()"><mat-icon>done_all</mat-icon> Accepter</button>
              </span>
            </div>
          }
          @if ((s['preparees'] || 0) > 0) {
            <div class="bea-hb-groupe bea-hb-confirmer">
              <span><strong>{{ n(s['preparees']) }}</strong> décision(s) préparée(s), pas encore enregistrée(s).</span>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="confirmer()" [disabled]="busy()"><mat-icon>task_alt</mat-icon> Confirmer les décisions</button>
            </div>
          }
        }
        <p class="bea-cl-hint" style="padding:0.6rem 1.1rem">
          @if (mode() === 'import') {
            Rapprochement par racine client uniquement (jamais par le nom seul). Un client absent du fichier n’est jamais supprimé. L’intégration ne modifie aucune classification : la classification se fait ensuite, par lot.
          } @else {
            Une classification manuelle existante n’est jamais écrasée sans décision motivée. La classe moteur reste visible à côté de la classe retenue ; chaque décision est tracée (analyste, auteur, date, motif).
          }
        </p>
      </section>
    }
  `,
})
export class ClHebdoComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  readonly base = CL_BASE;
  readonly mode = input<ModeHebdo>('import');
  readonly historique = signal<LotResume[]>([]);
  readonly lot = signal<LotHebdo | null>(null);
  readonly bilan = signal<Bilan | null>(null);
  readonly apercu = signal<ApercuIntegration | null>(null);
  readonly busy = signal(false);
  readonly survol = signal(false);
  readonly filtre = signal('');
  readonly selection = signal(new Set<number>());
  readonly analystes = signal<string[]>([]);
  readonly etats = ETATS_PROPOSITION;
  readonly statutsClient = STATUTS_CLIENT;
  readonly statutsDecision = STATUTS_DECISION;
  readonly libLot = LIB_LOT;
  readonly libAnalyste = LIB_ANALYSTE;
  readonly libIntegration = LIB_INTEGRATION;
  readonly libPreparation = LIB_PREPARATION;
  readonly profils = Object.entries(PROFILS);
  readonly niveauxListe = NIVEAUX;
  readonly maxSelection = MAX_SELECTION;
  readonly n = n;
  readonly df = dateFr;
  readonly dh = dateHeureFr;
  readonly filtres = computed(() => (this.mode() === 'import' ? FILTRES_IMPORT : FILTRES_LOT));
  readonly listeLots = computed(() => {
    const h = this.historique();
    if (this.mode() === 'lot') return h.filter((x) => x.statut !== 'FERME');
    return this.mode() === 'import' ? h.slice(0, 5) : h;
  });
  readonly peutDeposer = computed(() => !!(this.store.cap().imports_executer || this.store.cap().classif_executer));
  readonly peutDecider = computed(() =>
    this.mode() === 'lot' && !!this.store.cap().classif_executer && this.lot()?.statut_lot !== 'FERME');
  readonly nbPages = computed(() => {
    const l = this.lot();
    return l ? Math.max(1, Math.ceil(l.total_filtre / l.taille)) : 1;
  });
  readonly colonnesManquantes = computed(() => {
    const v = (this.lot()?.stats as Record<string, unknown> | undefined)?.['colonnes_manquantes'];
    return Array.isArray(v) ? (v as string[]) : [];
  });
  readonly integration = computed(() => {
    const v = (this.lot()?.stats as Record<string, unknown> | undefined)?.['integration'];
    return v && typeof v === 'object' ? (v as BilanIntegration) : null;
  });
  readonly champsApercu = computed(() =>
    Object.entries(this.apercu()?.champs ?? {}).map(([c, k]) => `${c} (${n(k)})`));
  readonly selectionnables = computed(() =>
    (this.lot()?.lignes ?? []).filter((x) => x.statut_decision === 'EN_ATTENTE').map((x) => x.ligne));
  readonly toutSelectionne = computed(() => {
    const ids = this.selectionnables();
    return ids.length > 0 && ids.every((i) => this.selection().has(i));
  });
  niveaux: Record<number, string | undefined> = {};
  niveauGroupe = '';
  periode = new Date().toISOString().slice(0, 10);
  analyste = '';
  q = '';
  profil = '';

  ngOnInit(): void {
    this.filtre.set(this.mode() === 'lot' ? 'EN_ATTENTE' : '');
    this.chargerHistorique();
    this.api.get<string[]>(`${CL_BASE}/classification/analystes`).subscribe({
      next: (a) => this.analystes.set(a), error: () => this.analystes.set([]),
    });
    const id = this.route.snapshot.queryParamMap.get('lot');
    if (id) this.ouvrir(id);
  }

  private chargerHistorique(): void {
    this.api.get<{ items: LotResume[] }>(`${CL_BASE}/lots`).subscribe({
      next: (r) => this.historique.set((r.items || []).filter((x) => x.type === 'LISTE')),
      error: () => this.historique.set([]),
    });
  }

  profilLib(p: string | null | undefined): string {
    return p ? PROFILS[p] ?? p : '—';
  }

  modele(): void {
    this.api.download(`${CL_BASE}/lots/modele.xlsx`).subscribe({
      next: (b) => telecharger(b, 'modele-import-hebdomadaire.xlsx'),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Modèle indisponible')),
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

  private analyser(f: File, forcer = false): void {
    if (!/\.(xlsx|xlsm)$/i.test(f.name)) {
      this.feedback.warning({ title: 'Format non pris en charge', message: 'Fichier .xlsx attendu.' });
      return;
    }
    const fd = new FormData();
    fd.append('fichier', f);
    const params = [`type=LISTE`, this.periode ? `periode_reference=${this.periode}` : '', forcer ? 'forcer=true' : '']
      .filter(Boolean).join('&');
    let dejaImporte = false;
    this.feedback.run(() => this.api.post<LotHebdo>(`${CL_BASE}/lots/analyse?${params}`, fd), {
      busy: this.busy, loading: 'Contrôle du fichier…',
      success: (r) => ({
        title: 'Fichier contrôlé',
        message: `${r.stats['lignes'] ?? 0} ligne(s) : ${r.stats['racines_ok'] ?? 0} client(s) existant(s), ${r.stats['nouveaux'] ?? 0} nouveau(x). Rien n’est encore écrit.`,
      }),
      errorTitle: 'Fichier refusé', retry: false,
      onError: (i) => { dejaImporte = i.code === 'FICHIER_DEJA_IMPORTE'; },
    }).subscribe({
      next: (r) => {
        this.chargerHistorique();
        this.ouvrir(r.id);
      },
      complete: () => {
        if (!dejaImporte) return;
        this.feedback.confirm({
          action: 'validation', title: 'Fichier déjà importé',
          message: `« ${f.name} » a déjà été déposé. Créer un nouveau lot quand même ?`,
          hint: 'Rejouer un fichier ne crée aucun doublon : les clients existants ne sont jamais recréés et les lignes déjà intégrées ne le sont pas deux fois.',
        }).subscribe((ok) => { if (ok) this.analyser(f, true); });
      },
    });
  }

  choisirLot(id: string): void {
    if (this.mode() === 'historique') {
      void this.router.navigate(['/clientele/import-hebdo'], { queryParams: { lot: id } });
      return;
    }
    this.ouvrir(id);
  }

  ouvrir(id: string): void {
    this.bilan.set(null);
    this.apercu.set(null);
    this.selection.set(new Set());
    this.niveaux = {};
    void this.router.navigate([], { relativeTo: this.route, queryParams: { lot: id }, replaceUrl: true });
    this.charger(1, id);
  }

  charger(page = 1, id = this.lot()?.id): void {
    if (!id) return;
    const params: Record<string, string | number> = { page };
    if (this.filtre()) params['statut'] = this.filtre();
    if (this.q.trim()) params['q'] = this.q.trim();
    if (this.profil) params['profil'] = this.profil;
    this.api.get<LotHebdo>(`${CL_BASE}/lots/${id}`, params).subscribe({
      next: (l) => this.lot.set(l),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Import introuvable')),
    });
  }

  filtrer(code: string): void {
    this.filtre.set(code);
    this.selection.set(new Set());
    this.charger(1);
  }

  fermerVue(): void {
    this.lot.set(null);
    this.bilan.set(null);
    this.apercu.set(null);
    this.selection.set(new Set());
    void this.router.navigate([], { relativeTo: this.route, queryParams: { lot: null }, replaceUrl: true });
    this.chargerHistorique();
  }

  basculer(ligne: number): void {
    const s = new Set(this.selection());
    if (s.has(ligne)) s.delete(ligne);
    else if (s.size < MAX_SELECTION) s.add(ligne);
    else this.feedback.warning({ title: 'Sélection limitée', message: `${MAX_SELECTION} lignes maximum à la fois.` });
    this.selection.set(s);
  }

  toutSelectionner(on: boolean): void {
    this.selection.set(on ? new Set(this.selectionnables().slice(0, MAX_SELECTION)) : new Set());
  }

  // ---------------------------------------------------------------- intégration (Base Clientèle)
  preparerIntegration(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.get<ApercuIntegration>(`${CL_BASE}/lots/${l.id}/integration`), {
      busy: this.busy, loading: 'Calcul du récapitulatif…', success: () => null, errorTitle: 'Récapitulatif indisponible',
    }).subscribe((a) => this.apercu.set(a));
  }

  integrer(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.post<{ bilan: BilanIntegration }>(`${CL_BASE}/lots/${l.id}/integrer`, {}), {
      busy: this.busy, loading: 'Intégration…', idempotent: true,
      success: (r) => ({
        title: 'Intégration enregistrée',
        message: `${r.bilan.integrees} ligne(s) intégrée(s) : ${r.bilan.clients_crees} client(s) créé(s), ${r.bilan.clients_mis_a_jour} mis à jour, ${r.bilan.non_integrees} non intégrée(s), ${r.bilan.erreurs} erreur(s).`,
      }),
      errorTitle: 'Intégration refusée', retry: false,
    }).subscribe(() => {
      this.apercu.set(null);
      this.charger(this.lot()?.page ?? 1);
      this.chargerHistorique();
    });
  }

  rejetsXlsx(): void {
    const l = this.lot()!;
    this.api.download(`${CL_BASE}/lots/${l.id}/rejets.xlsx`).subscribe({
      next: (b) => telecharger(b, `rejets-import-${l.periode_reference || l.id}.xlsx`),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Rapport indisponible')),
    });
  }

  // ---------------------------------------------------------------- classification par lot
  evaluer(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.post<LotHebdo>(`${CL_BASE}/lots/${l.id}/evaluer`, {}), {
      confirm: {
        action: 'validation', title: 'Exécuter le moteur',
        message: 'Calculer la classe moteur (SCORE) pour les clients reconnus en attente de décision ?',
        hint: 'Calcul seulement : aucune classification n’est modifiée.',
      },
      busy: this.busy, loading: 'Calcul…', success: { title: 'Classes moteur calculées' }, errorTitle: 'Calcul refusé',
    }).subscribe(() => this.charger(1));
  }

  private motifRequis(x: LigneHebdo, d: Preparation): boolean {
    if (d === 'MODIFIER' || d === 'REJETER') return true;
    if (d === 'ATTENTE') return false;
    const manuelDifferent = SOURCES_MANUELLES.includes(x.source_actuelle || '') && x.classe_actuelle !== x.proposition.niveau;
    return x.proposition.etat === 'A_VERIFIER' || manuelDifferent;
  }

  preparerSelection(d: Preparation): void {
    const lignes = (this.lot()?.lignes ?? []).filter((x) => this.selection().has(x.ligne));
    if (d === 'MODIFIER') lignes.forEach((x) => (this.niveaux[x.ligne] = this.niveauGroupe));
    this.preparer(lignes, d);
  }

  preparer(lignes: LigneHebdo[], d: Preparation): void {
    if (!lignes.length) return;
    const niveau = d === 'MODIFIER' ? this.niveaux[lignes[0].ligne] : null;
    const requis = lignes.some((x) => this.motifRequis(x, d));
    const appel = (motif: string | null) => this.api.post<{ preparees: number; refus: { ligne: number; raison: string }[] }>(
      `${CL_BASE}/lots/${this.lot()!.id}/lignes/preparer`,
      { lignes: lignes.map((x) => x.ligne), decision: d, niveau, motif, analyste_kyc: this.analyste || null },
    );
    const succes = (r: { preparees: number; refus: { ligne: number; raison: string }[] }) => ({
      title: d === 'ATTENTE' ? 'Laissé en attente' : 'Décision préparée',
      message: `${r.preparees} ligne(s) préparée(s)${r.refus.length ? `, ${r.refus.length} refusée(s)` : ''}. Confirmez pour enregistrer.`,
      details: r.refus.slice(0, 5).map((x) => ({ label: `Ligne ${x.ligne}`, value: x.raison })),
      duration: r.refus.length ? 0 : undefined,
    });
    const options = { busy: this.busy, loading: 'Préparation…', success: succes, errorTitle: 'Préparation refusée', retry: false };
    if (!requis && d !== 'ACCEPTER') {
      this.feedback.run(() => appel(null), options).subscribe(() => this.apresPreparation());
      return;
    }
    const cible = lignes.length === 1 ? `la ligne ${lignes[0].ligne} (${lignes[0].racine || lignes[0].brut})` : `${lignes.length} ligne(s)`;
    const titre = { ACCEPTER: 'Accepter la classe proposée', MODIFIER: `Classe manuelle ${niveau}`, REJETER: 'Rejeter', ATTENTE: '' }[d];
    this.feedback.runWithReason((motif) => appel(motif || null), {
      ...options,
      reason: {
        title: titre,
        message: `${titre} pour ${cible} ? La décision est préparée ; elle ne sera enregistrée qu’à la confirmation globale.`,
        hint: requis ? 'Motif obligatoire (classe manuelle, rejet, ligne à vérifier ou décision manuelle existante différente).' : 'Motif facultatif.',
        reasonLabel: 'Motif', required: requis, maxLength: 2000,
        confirmLabel: 'Préparer', tone: d === 'REJETER' ? 'danger' : 'primary',
      },
    }).subscribe(() => this.apresPreparation());
  }

  private apresPreparation(): void {
    this.selection.set(new Set());
    this.niveaux = {};
    this.niveauGroupe = '';
    this.charger(this.lot()?.page ?? 1);
  }

  confirmer(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.post<{ confirmees: number; erreurs: { ligne: number; message: string }[] }>(
      `${CL_BASE}/lots/${l.id}/confirmer`, {}), {
      confirm: {
        action: 'validation', title: 'Confirmer les décisions',
        message: `Enregistrer les ${l.stats['preparees'] || 0} décision(s) préparée(s) ?`,
        hint: 'Chaque décision est historisée (classe précédente, classe retenue, analyste, auteur, date, motif). Une ligne en erreur reste à décider.',
      },
      busy: this.busy, loading: 'Enregistrement…', idempotent: true,
      success: (r) => ({
        title: 'Décisions enregistrées',
        message: `${r.confirmees} décision(s) enregistrée(s)${r.erreurs.length ? `, ${r.erreurs.length} en erreur (restées à décider)` : ''}.`,
        details: r.erreurs.slice(0, 5).map((e) => ({ label: `Ligne ${e.ligne}`, value: e.message })),
        duration: r.erreurs.length ? 0 : undefined,
      }),
      errorTitle: 'Confirmation refusée', retry: false,
    }).subscribe(() => {
      this.charger(this.lot()?.page ?? 1);
      if (this.bilan()) this.chargerBilan();
      this.chargerHistorique();
    });
  }

  chargerBilan(): void {
    this.api.get<Bilan>(`${CL_BASE}/lots/${this.lot()!.id}/bilan`).subscribe({
      next: (b) => this.bilan.set(b),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Bilan indisponible')),
    });
  }

  bilanXlsx(): void {
    const l = this.lot()!;
    this.api.download(`${CL_BASE}/lots/${l.id}/bilan.xlsx`).subscribe({
      next: (b) => telecharger(b, `bilan-import-${l.periode_reference || l.id}.xlsx`),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible')),
    });
  }

  fichierOrigine(): void {
    const l = this.lot()!;
    this.api.download(`${CL_BASE}/lots/${l.id}/fichier`).subscribe({
      next: (b) => telecharger(b, l.fichier_nom),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Fichier indisponible')),
    });
  }

  fermerLot(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.post<void>(`${CL_BASE}/lots/${l.id}/fermer`, {}), {
      confirm: {
        action: 'validation', title: 'Fermer le lot',
        message: `Fermer « ${l.fichier_nom} » ?`,
        hint: `${l.stats['en_attente'] || 0} ligne(s) à décider resteront non décidées. Le lot, ses décisions et le fichier restent consultables.`,
      },
      busy: this.busy, success: { title: 'Lot fermé' }, errorTitle: 'Fermeture impossible',
    }).subscribe(() => this.charger(1));
  }
}
