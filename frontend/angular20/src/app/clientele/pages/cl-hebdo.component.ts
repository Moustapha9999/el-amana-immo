import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import {
  CL_BASE, ETATS_PROPOSITION, LigneHebdo, LotHebdo, STATUTS_CLIENT, STATUTS_DECISION, dateFr, dateHeureFr, n, telecharger,
} from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface LotResume {
  id: string; fichier_nom: string; type: string; statut: string; periode_reference: string | null;
  stats: Record<string, number>; created_at: string | null; actions?: Record<string, boolean>;
}
interface Bilan {
  lot: { fichier_nom: string; importe_par: string | null; importe_le: string | null; sha256: string; fichier_disponible: boolean };
  stats: Record<string, number>; decisions: Record<string, number>; operations: Record<string, number>;
  groupes: number; clients_crees: number;
}
type Decision = 'ACCEPTER' | 'MODIFIER' | 'REJETER';

const FILTRES: { code: string; libelle: string; cle?: string }[] = [
  { code: '', libelle: 'Toutes', cle: 'lignes' },
  { code: 'EN_ATTENTE', libelle: 'En attente', cle: 'en_attente' },
  { code: 'PROPOSE', libelle: 'Proposées', cle: 'proposition_propose' },
  { code: 'A_VERIFIER', libelle: 'À vérifier', cle: 'proposition_a_verifier' },
  { code: 'NON_CLASSIFIABLE', libelle: 'Non classifiables', cle: 'proposition_non_classifiable' },
  { code: 'A_EVALUER', libelle: 'À évaluer', cle: 'proposition_a_evaluer' },
  { code: 'NOUVEAU', libelle: 'Nouveaux clients', cle: 'nouveaux' },
  { code: 'CONTRADICTION', libelle: 'Contradictions ORION', cle: 'contradictions' },
  { code: 'ANOMALIE', libelle: 'Anomalies', cle: 'avec_anomalie' },
  { code: 'DECIDEE', libelle: 'Décidées' },
];
const MAX_GROUPE = 200;
const LIB_LOT: Record<string, string> = { ANALYSE: 'Analysé', EVALUE: 'Évalué', ENREGISTRE: 'Tout décidé', FERME: 'Fermé' };

@Component({
  selector: 'bea-cl-hebdo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  styles: `
    .bea-hb-actions { display: flex; gap: 0.3rem; flex-wrap: wrap; }
    .bea-hb-actions button { display: inline-flex; align-items: center; gap: 0.2rem; font: inherit; font-size: 0.78rem; font-weight: 600; padding: 0.3rem 0.55rem; border-radius: 0.45rem; border: 1px solid #cbd5e1; background: #fff; color: #0f172a; cursor: pointer; }
    .bea-hb-actions button mat-icon { font-size: 1rem; width: 1rem; height: 1rem; }
    .bea-hb-actions button.is-ok { border-color: #16a34a; color: #166534; }
    .bea-hb-actions button.is-ko { border-color: #dc2626; color: #991b1b; }
    .bea-hb-actions button:disabled { opacity: 0.45; cursor: not-allowed; }
    .bea-hb-actions select { font: inherit; font-size: 0.78rem; padding: 0.25rem; border: 1px solid #cbd5e1; border-radius: 0.45rem; }
    .bea-hb-raison { display: block; max-width: 22rem; font-size: 0.75rem; color: #64748b; }
    .bea-hb-groupe { position: sticky; bottom: 0; display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; padding: 0.7rem 1.1rem; background: #0f2a43; color: #fff; border-radius: 0.75rem; margin-top: 0.6rem; }
    .bea-hb-groupe .bea-mg__btn { background: #fff; }
    .bea-hb-filtres { display: flex; gap: 0.35rem; flex-wrap: wrap; padding: 0 1.1rem 0.7rem; }
    .bea-hb-filtres button { font: inherit; font-size: 0.78rem; padding: 0.3rem 0.65rem; border-radius: 999px; border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
    .bea-hb-filtres button.is-on { background: #1a5278; color: #fff; border-color: #1a5278; }
    .bea-hb-analyste { display: flex; align-items: end; gap: 0.75rem; flex-wrap: wrap; padding: 0 1.1rem 0.8rem; }
    .bea-hb-analyste label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.72rem; font-weight: 700; color: #64748b; text-transform: uppercase; }
    .bea-hb-analyste input { font: inherit; font-size: 0.88rem; text-transform: none; min-width: 16rem; padding: 0.45rem 0.6rem; border: 1px solid #cbd5e1; border-radius: 0.55rem; }
    tr.is-sel td { background: #eff6ff; }
  `,
  template: `
    @if (!lot()) {
      <section class="bea-mg__panel" style="padding:1rem">
        <div class="bea-mg__panel-top" style="padding:0 0 0.6rem"><h2>Importer la liste hebdomadaire</h2>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="modele()" [disabled]="busy()"><mat-icon>table_view</mat-icon> Modèle Excel</button>
        </div>
        @if (store.cap().classif_executer || store.cap().imports_executer) {
          <div class="bea-cl-filters" style="padding:0 0 0.75rem">
            <label>Semaine / période de référence <input type="date" [(ngModel)]="periode" /></label>
          </div>
          <label class="bea-fx-dropzone" [class.is-over]="survol()" (dragover)="$event.preventDefault(); survol.set(true)" (dragleave)="survol.set(false)" (drop)="deposer($event)">
            <input type="file" accept=".xlsx,.xlsm" hidden (change)="choisir($any($event.target))" />
            @if (busy()) {
              <mat-icon class="bea-cl-spin">progress_activity</mat-icon><strong>Contrôle du fichier…</strong>
            } @else {
              <mat-icon>upload_file</mat-icon><strong>Déposez la liste Excel de la semaine</strong>
              <span>.xlsx, 40 Mo maximum. Contrôles, rapprochement par racine, nouveaux clients et propositions — rien n’est appliqué sans votre décision.</span>
            }
          </label>
        }
      </section>
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Imports précédents</h2><span class="bea-mg__count">{{ historique().length }}</span></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Déposé le</th><th>Fichier</th><th>Période</th><th>Lignes</th><th>Nouveaux</th><th>En attente</th><th>Décidées</th><th>Statut</th><th></th></tr></thead>
            <tbody>
              @for (h of historique(); track h.id) {
                <tr style="cursor:pointer" (click)="ouvrir(h.id)">
                  <td>{{ dh(h.created_at) }}</td>
                  <td><strong>{{ h.fichier_nom }}</strong></td>
                  <td>{{ df(h.periode_reference) }}</td>
                  <td>{{ n(h.stats['lignes']) }}</td>
                  <td>{{ n(h.stats['nouveaux']) }}</td>
                  <td>{{ h.stats['en_attente'] === undefined ? '—' : n(h.stats['en_attente']) }}</td>
                  <td>{{ n((h.stats['acceptees'] || 0) + (h.stats['modifiees'] || 0) + (h.stats['rejetees'] || 0)) }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="h.statut">{{ libLot[h.statut] || h.statut }}</span></td>
                  <td><mat-icon>chevron_right</mat-icon></td>
                </tr>
              } @empty {
                <tr><td colspan="9"><div class="bea-cl-empty"><mat-icon>history</mat-icon>Aucun import hebdomadaire.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
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
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerVue()"><mat-icon>arrow_back</mat-icon> Imports</button>
            @if (store.cap().classif_voir && l.statut_lot !== 'FERME' && (s['proposition_a_evaluer'] || 0) > 0) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="evaluer()" [disabled]="busy()"><mat-icon>calculate</mat-icon> Proposition moteur ({{ n(s['proposition_a_evaluer']) }})</button>
            }
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="chargerBilan()" [disabled]="busy()"><mat-icon>summarize</mat-icon> Bilan</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="bilanXlsx()" [disabled]="busy()"><mat-icon>download</mat-icon> Bilan Excel</button>
            @if (l.fichier_disponible) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fichierOrigine()" [disabled]="busy()"><mat-icon>attach_file</mat-icon> Fichier importé</button>
            }
            @if (l.statut_lot !== 'FERME') {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerLot()" [disabled]="busy()"><mat-icon>lock</mat-icon> Fermer</button>
            }
          </span>
        </div>
        @if (l.message) { <div class="bea-cl-note bea-cl-note--info" style="margin:0 1.1rem 0.8rem"><mat-icon>info</mat-icon><span>{{ l.message }}</span></div> }
        <div class="bea-cl-stats">
          <div class="bea-cl-stat"><span>Lignes</span><strong>{{ n(s['lignes']) }}</strong></div>
          <div class="bea-cl-stat" data-tone="ok"><span>Clients reconnus</span><strong>{{ n(s['racines_ok']) }}</strong></div>
          <div class="bea-cl-stat"><span>Nouveaux clients</span><strong>{{ n(s['nouveaux']) }}</strong></div>
          <div class="bea-cl-stat" [attr.data-tone]="(s['ambigus'] || 0) + (s['contradictions'] || 0) ? 'warn' : ''"><span>Identité à vérifier</span><strong>{{ n((s['ambigus'] || 0) + (s['contradictions'] || 0)) }}</strong></div>
          <div class="bea-cl-stat" [attr.data-tone]="(s['doublons'] || 0) + (s['invalides'] || 0) ? 'danger' : ''"><span>Doublons / invalides</span><strong>{{ n((s['doublons'] || 0) + (s['invalides'] || 0)) }}</strong></div>
          <div class="bea-cl-stat" data-tone="warn"><span>En attente de décision</span><strong>{{ n(s['en_attente']) }}</strong></div>
          <div class="bea-cl-stat" data-tone="ok"><span>Acceptées / modifiées</span><strong>{{ n((s['acceptees'] || 0) + (s['modifiees'] || 0)) }}</strong></div>
          <div class="bea-cl-stat"><span>Rejetées</span><strong>{{ n(s['rejetees']) }}</strong></div>
        </div>

        @if (bilan(); as b) {
          <div class="bea-mg__panel-top"><h2>Bilan de l’import</h2>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="bilan.set(null)"><mat-icon>close</mat-icon></button>
          </div>
          <dl class="bea-cl-dl">
            <dt>Importé par</dt><dd>{{ b.lot.importe_par || '—' }} · {{ dh(b.lot.importe_le) }}</dd>
            <dt>Empreinte</dt><dd><code>{{ b.lot.sha256.slice(0, 16) }}…</code></dd>
            <dt>Décisions</dt><dd>{{ n(b.decisions['ACCEPTEE']) }} acceptée(s) · {{ n(b.decisions['MODIFIEE']) }} modifiée(s) · {{ n(b.decisions['REJETEE']) }} rejetée(s) · {{ n(b.decisions['EN_ATTENTE']) }} en attente</dd>
            <dt>Décisions groupées</dt><dd>{{ n(b.groupes) }}</dd>
            <dt>Fiches créées</dt><dd>{{ n(b.clients_crees) }} <small class="bea-cl-hint">(source import hebdo, sans compte ORION — hors indicateurs et BCM)</small></dd>
            <dt>Données KYC mises à jour</dt><dd>{{ n(b.operations['MAJ_DONNEES']) }} champ(s)</dd>
          </dl>
        }

        <div class="bea-hb-filtres" role="tablist" aria-label="Filtrer les lignes">
          @for (f of filtres; track f.code) {
            <button type="button" [class.is-on]="filtre() === f.code" (click)="filtrer(f.code)">{{ f.libelle }}@if (f.cle && s[f.cle] !== undefined) { ({{ n(s[f.cle]) }})}</button>
          }
        </div>
        @if (peutDecider()) {
          <div class="bea-hb-analyste">
            <label>Analyste KYC des décisions
              <input [(ngModel)]="analyste" list="bea-hb-analystes" maxlength="120" placeholder="Par défaut : analyste indiqué dans le fichier" />
            </label>
            <datalist id="bea-hb-analystes">@for (a of analystes(); track a) { <option [value]="a"></option> }</datalist>
            <p class="bea-cl-hint" style="margin:0">Chaque décision est horodatée et tracée avec votre nom et l’analyste. Aucune proposition n’est appliquée sans décision.</p>
          </div>
        }
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr>
              @if (peutDecider()) { <th><input type="checkbox" [checked]="toutSelectionne()" (change)="toutSelectionner($any($event.target).checked)" aria-label="Tout sélectionner" /></th> }
              <th>L.</th><th>Racine</th><th>Nom</th><th>Client</th><th>Classe actuelle</th><th>Proposition</th><th>Moteur</th><th>Anomalies</th><th>Analyste</th><th>Décision</th>
              @if (peutDecider()) { <th></th> }
            </tr></thead>
            <tbody>
              @for (x of l.lignes; track x.ligne) {
                @let p = x.proposition;
                <tr [class.is-sel]="selection().has(x.ligne)">
                  @if (peutDecider()) {
                    <td><input type="checkbox" [disabled]="!!x.exclusion_groupe" [checked]="selection().has(x.ligne)" (change)="basculer(x.ligne)" [attr.title]="x.exclusion_groupe ? 'À traiter individuellement : ' + x.exclusion_groupe : 'Sélectionner'" /></td>
                  }
                  <td>{{ x.ligne }}</td>
                  <td>@if (x.racine && x.statut === 'OK') { <a [routerLink]="['/clientele/clients', x.racine]"><code>{{ x.racine }}</code></a> } @else { <code>{{ x.racine || x.brut || '—' }}</code> }</td>
                  <td>{{ x.nom || '—' }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="x.statut_client">{{ statutsClient[x.statut_client] || x.statut_client }}</span>
                    @for (v of x.identite; track v) { <small class="bea-hb-raison">{{ v }}</small> }
                  </td>
                  <td>@if (x.classe_actuelle) { <span class="bea-cl-badge" [attr.data-s]="x.classe_actuelle">{{ x.classe_actuelle }}</span> <small class="bea-cl-hint">{{ x.source_actuelle }}</small> } @else { — }</td>
                  <td>
                    @if (p.niveau) { <span class="bea-cl-badge" [attr.data-s]="p.niveau">{{ p.niveau }}</span> }
                    <span class="bea-cl-badge" [attr.data-s]="p.etat">{{ etats[p.etat] || p.etat }}</span>
                    <small class="bea-hb-raison">{{ p.categorie_libelle ? p.categorie_libelle + ' — ' : '' }}{{ p.raison }}</small>
                  </td>
                  <td>@if (p.statut_moteur) { {{ p.niveau_moteur || 'NON CLASSÉ' }} <small class="bea-cl-hint">({{ p.statut_moteur }})</small>@if (p.ecart_moteur) { <small class="bea-hb-raison">écart avec la classe du fichier</small> } } @else { — }</td>
                  <td>@if (x.anomalies.length) { <small class="bea-hb-raison">{{ x.anomalies.join(' · ') }}</small> } @else { — }</td>
                  <td>{{ x.analyste || '—' }}</td>
                  <td>
                    <span class="bea-cl-badge" [attr.data-s]="x.statut_decision">{{ statutsDecision[x.statut_decision] || x.statut_decision }}</span>
                    @if (x.decision_ligne; as d) {
                      <small class="bea-hb-raison">{{ d.niveau ? d.niveau + ' · ' : '' }}{{ d.par_nom }} · {{ dh(d.le) }}@if (d.client_cree) { · fiche créée}</small>
                      @if (d.motif) { <small class="bea-hb-raison">« {{ d.motif }} »</small> }
                    }
                  </td>
                  @if (peutDecider()) {
                    <td>
                      @if (x.statut_decision === 'EN_ATTENTE') {
                        <div class="bea-hb-actions">
                          @if (p.niveau && (x.statut === 'OK' || x.statut === 'INCONNUE')) {
                            <button type="button" class="is-ok" (click)="decider(x, 'ACCEPTER')" [disabled]="busy()" title="Accepter la proposition"><mat-icon>check</mat-icon> Accepter</button>
                          }
                          @if (x.statut === 'OK' || x.statut === 'INCONNUE') {
                            <select [(ngModel)]="niveaux[x.ligne]" aria-label="Niveau retenu">
                              <option [ngValue]="undefined">Modifier…</option>
                              @for (nv of ['FAIBLE', 'MOYEN', 'ELEVE', 'INTERDIT']; track nv) { <option [ngValue]="nv">{{ nv }}</option> }
                            </select>
                            <button type="button" (click)="decider(x, 'MODIFIER')" [disabled]="busy() || !niveaux[x.ligne]" title="Retenir un autre niveau (motif obligatoire)"><mat-icon>edit</mat-icon></button>
                          }
                          <button type="button" class="is-ko" (click)="decider(x, 'REJETER')" [disabled]="busy()" title="Rejeter (motif obligatoire)"><mat-icon>close</mat-icon> Rejeter</button>
                        </div>
                      }
                    </td>
                  }
                </tr>
              } @empty {
                <tr><td [attr.colspan]="peutDecider() ? 12 : 10"><div class="bea-cl-empty">Aucune ligne pour ce filtre.</div></td></tr>
              }
            </tbody>
          </table>
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
        @if (selection().size) {
          <div class="bea-hb-groupe">
            <span><strong>{{ selection().size }}</strong> ligne(s) sélectionnée(s) — décision groupée (max {{ maxGroupe }}), motif unique, chaque ligne tracée.</span>
            <span style="display:flex;gap:0.5rem">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="toutSelectionner(false)">Vider</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="groupe('REJETER')" [disabled]="busy()"><mat-icon>close</mat-icon> Rejeter</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="groupe('ACCEPTER')" [disabled]="busy()"><mat-icon>done_all</mat-icon> Accepter</button>
            </span>
          </div>
        }
        <p class="bea-cl-hint" style="padding:0.6rem 1.1rem">Exclus des décisions groupées (à traiter ligne par ligne) : classement manuel existant, niveau Interdit, anomalies, lignes à vérifier ou non classifiables. Un client absent du fichier n’est jamais supprimé.</p>
      </section>
    }
  `,
})
export class ClHebdoComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly historique = signal<LotResume[]>([]);
  readonly lot = signal<LotHebdo | null>(null);
  readonly bilan = signal<Bilan | null>(null);
  readonly busy = signal(false);
  readonly survol = signal(false);
  readonly filtre = signal('EN_ATTENTE');
  readonly selection = signal(new Set<number>());
  readonly analystes = signal<string[]>([]);
  readonly filtres = FILTRES;
  readonly etats = ETATS_PROPOSITION;
  readonly statutsClient = STATUTS_CLIENT;
  readonly statutsDecision = STATUTS_DECISION;
  readonly libLot = LIB_LOT;
  readonly maxGroupe = MAX_GROUPE;
  readonly n = n;
  readonly df = dateFr;
  readonly dh = dateHeureFr;
  readonly peutDecider = computed(() => !!this.store.cap().classif_executer && this.lot()?.statut_lot !== 'FERME');
  readonly nbPages = computed(() => {
    const l = this.lot();
    return l ? Math.max(1, Math.ceil(l.total_filtre / l.taille)) : 1;
  });
  readonly selectionnables = computed(() => (this.lot()?.lignes ?? []).filter((x) => !x.exclusion_groupe).map((x) => x.ligne));
  readonly toutSelectionne = computed(() => {
    const ids = this.selectionnables();
    return ids.length > 0 && ids.every((i) => this.selection().has(i));
  });
  niveaux: Record<number, string | undefined> = {};
  periode = new Date().toISOString().slice(0, 10);
  analyste = '';

  ngOnInit(): void {
    this.chargerHistorique();
    this.api.get<string[]>(`${CL_BASE}/classification/analystes`).subscribe({
      next: (a) => this.analystes.set(a), error: () => this.analystes.set([]),
    });
  }

  private chargerHistorique(): void {
    this.api.get<{ items: LotResume[] }>(`${CL_BASE}/lots`).subscribe({
      next: (r) => this.historique.set((r.items || []).filter((x) => x.type === 'LISTE')),
      error: () => this.historique.set([]),
    });
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

  private analyser(f: File): void {
    if (!/\.(xlsx|xlsm)$/i.test(f.name)) {
      this.feedback.warning({ title: 'Format non pris en charge', message: 'Fichier .xlsx attendu.' });
      return;
    }
    const fd = new FormData();
    fd.append('fichier', f);
    const periode = this.periode ? `&periode_reference=${this.periode}` : '';
    this.feedback.run(() => this.api.post<LotHebdo>(`${CL_BASE}/lots/analyse?type=LISTE${periode}`, fd), {
      busy: this.busy, loading: 'Contrôle du fichier…',
      success: (r) => ({
        title: 'Fichier contrôlé',
        message: `${r.stats['lignes'] ?? 0} ligne(s) : ${r.stats['racines_ok'] ?? 0} client(s) reconnu(s), ${r.stats['nouveaux'] ?? 0} nouveau(x).`,
      }),
      errorTitle: 'Fichier refusé', retry: false,
    }).subscribe((r) => {
      this.chargerHistorique();
      this.ouvrir(r.id);
    });
  }

  ouvrir(id: string): void {
    this.bilan.set(null);
    this.selection.set(new Set());
    this.niveaux = {};
    this.charger(1, id);
  }

  charger(page = 1, id = this.lot()?.id): void {
    if (!id) return;
    const params: Record<string, string | number> = { page };
    if (this.filtre()) params['statut'] = this.filtre();
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
    this.selection.set(new Set());
    this.chargerHistorique();
  }

  basculer(ligne: number): void {
    const s = new Set(this.selection());
    if (s.has(ligne)) s.delete(ligne);
    else if (s.size < MAX_GROUPE) s.add(ligne);
    else this.feedback.warning({ title: 'Sélection limitée', message: `${MAX_GROUPE} lignes maximum par décision groupée.` });
    this.selection.set(s);
  }

  toutSelectionner(on: boolean): void {
    this.selection.set(on ? new Set(this.selectionnables().slice(0, MAX_GROUPE)) : new Set());
  }

  evaluer(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.post<LotHebdo>(`${CL_BASE}/lots/${l.id}/evaluer`, {}), {
      confirm: {
        action: 'validation', title: 'Proposition du moteur',
        message: 'Calculer la proposition du moteur SCORE pour les clients reconnus en attente de décision ?',
        hint: 'Calcul seulement : aucune classification n’est modifiée. La classe du fichier reste prioritaire.',
      },
      busy: this.busy, loading: 'Évaluation…', success: { title: 'Propositions calculées' }, errorTitle: 'Évaluation refusée',
    }).subscribe(() => this.charger(1));
  }

  private motifRequis(x: LigneHebdo, d: Decision): boolean {
    if (d !== 'ACCEPTER') return true;
    const manuelDifferent = (x.source_actuelle === 'MANUEL' || x.source_actuelle === 'MANUEL_SURCHARGE')
      && x.classe_actuelle !== x.proposition.niveau;
    return x.proposition.etat === 'A_VERIFIER' || manuelDifferent;
  }

  decider(x: LigneHebdo, d: Decision): void {
    const niveau = d === 'MODIFIER' ? this.niveaux[x.ligne] : d === 'ACCEPTER' ? x.proposition.niveau : null;
    const requis = this.motifRequis(x, d);
    const quoi = d === 'REJETER'
      ? `Rejeter la proposition de la ligne ${x.ligne} (${x.racine || x.brut}) ? Rien n’est modifié, la décision est tracée.`
      : `${d === 'ACCEPTER' ? 'Accepter' : 'Retenir'} ${niveau} pour ${x.racine} — ${x.nom || ''} ?`
        + (x.statut === 'INCONNUE' ? ' La fiche du nouveau client sera créée (source import hebdo, sans compte ORION).' : '');
    this.feedback.runWithReason(
      (motif) => this.api.post<{ stats: Record<string, number> }>(`${CL_BASE}/lots/${this.lot()!.id}/lignes/decision`, {
        lignes: [x.ligne], decision: d, niveau, motif: motif || null, analyste_kyc: this.analyste.trim() || null,
      }),
      {
        reason: {
          title: d === 'REJETER' ? 'Rejeter la proposition' : d === 'ACCEPTER' ? 'Accepter la proposition' : 'Modifier le classement',
          message: quoi,
          hint: requis ? 'Motif obligatoire (classement manuel existant, ligne à vérifier, modification ou rejet).' : 'Motif facultatif : un motif standard est enregistré sinon.',
          reasonLabel: 'Motif', required: requis, maxLength: 2000,
          confirmLabel: d === 'REJETER' ? 'Rejeter' : 'Enregistrer', tone: d === 'REJETER' ? 'danger' : 'primary',
        },
        busy: this.busy, loading: 'Enregistrement…',
        success: { title: d === 'REJETER' ? 'Proposition rejetée' : 'Décision enregistrée', message: `Ligne ${x.ligne}` },
        errorTitle: 'Décision refusée', retry: false,
      },
    ).subscribe(() => this.apresDecision());
  }

  groupe(d: Decision): void {
    const lignes = [...this.selection()].sort((a, b) => a - b);
    if (!lignes.length) return;
    this.feedback.runWithReason(
      (motif) => this.api.post<{ groupe_id: string; resultats: unknown[] }>(`${CL_BASE}/lots/${this.lot()!.id}/lignes/decision`, {
        lignes, decision: d, motif, analyste_kyc: this.analyste.trim() || null,
      }),
      {
        reason: {
          title: d === 'ACCEPTER' ? 'Accepter en groupe' : 'Rejeter en groupe',
          message: `${d === 'ACCEPTER' ? 'Accepter la proposition de' : 'Rejeter'} ${lignes.length} ligne(s) ?`,
          hint: 'Motif unique, obligatoire. Chaque ligne est tracée individuellement avec un identifiant de groupe.',
          reasonLabel: 'Motif de la décision groupée', maxLength: 2000,
          confirmLabel: d === 'ACCEPTER' ? 'Accepter' : 'Rejeter', tone: d === 'ACCEPTER' ? 'primary' : 'danger',
        },
        busy: this.busy, loading: 'Enregistrement…',
        success: (r) => ({ title: 'Décision groupée enregistrée', message: `${r.resultats.length} ligne(s)` }),
        errorTitle: 'Décision groupée refusée', retry: false,
      },
    ).subscribe(() => this.apresDecision());
  }

  private apresDecision(): void {
    this.selection.set(new Set());
    this.niveaux = {};
    this.charger(this.lot()?.page ?? 1);
    if (this.bilan()) this.chargerBilan();
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
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Bilan indisponible')),
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
        action: 'validation', title: 'Fermer l’import',
        message: `Fermer « ${l.fichier_nom} » ?`,
        hint: `${l.stats['en_attente'] || 0} ligne(s) en attente resteront non décidées. L’import, ses décisions et le fichier restent consultables.`,
      },
      busy: this.busy, success: { title: 'Import fermé' }, errorTitle: 'Fermeture impossible',
    }).subscribe(() => this.charger(1));
  }
}
