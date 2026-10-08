import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, n, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

export type TypeLot = 'LISTE' | 'SITUATION';

interface LigneLot {
  ligne: number; brut: string | null; racine: string | null; statut: string;
  nom: string | null; nom_fichier: string | null;
  niveau_fichier: string | null; niveau_fichier_brut: string | null; motif_fichier: string | null;
  classe_actuelle: string | null; source_actuelle: string | null;
  colonnes: Record<string, string | null>;
  moteur?: { score: number; niveau: string | null; statut: string; motif: string | null; classable: boolean } | null;
}
interface Lot {
  id: string; fichier_nom: string; type: TypeLot; feuille: string; ligne_entete: number;
  entetes: string[]; colonne_racine: string | null; colonne_niveau: string | null; colonne_motif: string | null;
  colonnes_affichees?: string[]; message?: string;
  stats: Record<string, number>; total_filtre: number; page: number; lignes: LigneLot[];
  evaluation: { nb: number; par_niveau: Record<string, number>; classables: number; a_arbitrer: number } | null;
  limite_evaluation: number;
  dernier_classement?: Bilan;
}
interface Bilan { origine: string; ecrits: number; inchanges: number; manuels_preserves: number; non_classables: number; }

const TEXTES: Record<TypeLot, { titre: string; depot: string; aide: string }> = {
  LISTE: {
    titre: 'Liste de clients',
    depot: 'Déposez un fichier avec une colonne Racine client (CLIENT)',
    aide: 'Colonnes libres conservées pour l’affichage et l’export. Opérations : contrôler, évaluer avec le moteur, classer, exporter.',
  },
  SITUATION: {
    titre: 'Situation des comptes PP & PM',
    depot: 'Déposez le classeur « Situation des comptes PP et PM »',
    aide: 'Reprise de la classe de risque Conformité (source EXCEL_CONFORMITE). Racines absentes du référentiel : signalées, jamais créées.',
  },
};

@Component({
  selector: 'bea-cl-lot',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    @let t = textes();
    @if (!lot()) {
      <section class="bea-mg__panel" style="padding:1rem">
        <label class="bea-fx-dropzone" [class.is-over]="survol()" (dragover)="$event.preventDefault(); survol.set(true)" (dragleave)="survol.set(false)" (drop)="deposer($event)">
          <input type="file" accept=".xlsx,.xlsm" hidden (change)="choisir($any($event.target))" />
          @if (busy()) {
            <mat-icon class="bea-cl-spin">progress_activity</mat-icon><strong>Analyse du fichier…</strong>
          } @else {
            <mat-icon>{{ type() === 'SITUATION' ? 'assignment' : 'group_add' }}</mat-icon>
            <strong>{{ t.depot }}</strong>
            <span>.xlsx, 40 Mo maximum. Rien n’est écrit avant confirmation.</span>
          }
        </label>
        <p class="bea-cl-hint" style="margin:0.6rem 0 0">{{ t.aide }}</p>
      </section>
    } @else {
      @let l = lot()!;
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <div><h2>{{ l.fichier_nom }}</h2><p class="bea-cl-hint">{{ t.titre }} · feuille « {{ l.feuille }} », en-têtes ligne {{ l.ligne_entete }}</p></div>
          <span style="display:flex;gap:0.4rem;flex-wrap:wrap">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter()" [disabled]="busy() || !l.colonne_racine"><mat-icon>download</mat-icon> Exporter</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()" [disabled]="busy()"><mat-icon>close</mat-icon> Fermer</button>
          </span>
        </div>
        <div class="bea-cl-filters">
          <label>Colonne Racine client
            <select [(ngModel)]="colRacine">
              <option [ngValue]="null">— choisir —</option>
              @for (e of l.entetes; track e) { <option [ngValue]="e">{{ e }}</option> }
            </select>
          </label>
          <label>Colonne niveau de risque
            <select [(ngModel)]="colNiveau">
              <option [ngValue]="''">Aucune</option>
              @for (e of l.entetes; track e) { <option [ngValue]="e">{{ e }}</option> }
            </select>
          </label>
          <label>Colonne motif
            <select [(ngModel)]="colMotif">
              <option [ngValue]="''">Aucune</option>
              @for (e of l.entetes; track e) { <option [ngValue]="e">{{ e }}</option> }
            </select>
          </label>
          <label>&nbsp;<button type="button" class="bea-mg__btn" (click)="recartographier()" [disabled]="busy() || !colRacine">Appliquer les colonnes</button></label>
        </div>
        @if (l.message) {
          <div class="bea-cl-note" style="margin:0 1.1rem 0.9rem"><mat-icon>info</mat-icon><span>{{ l.message }}</span></div>
        }
        @if (l.colonne_racine) {
          <div class="bea-cl-stats">
            <div class="bea-cl-stat"><span>Lignes</span><strong>{{ n(l.stats['lignes']) }}</strong></div>
            <div class="bea-cl-stat" data-tone="ok"><span>Racines reconnues</span><strong>{{ n(l.stats['racines_ok']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="l.stats['inconnues'] ? 'warn' : ''"><span>Inconnues</span><strong>{{ n(l.stats['inconnues']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="l.stats['invalides'] ? 'danger' : ''"><span>Invalides</span><strong>{{ n(l.stats['invalides']) }}</strong></div>
            <div class="bea-cl-stat" [attr.data-tone]="l.stats['doublons'] ? 'warn' : ''"><span>Doublons</span><strong>{{ n(l.stats['doublons']) }}</strong></div>
            @if (l.colonne_niveau) {
              <div class="bea-cl-stat"><span>Avec niveau</span><strong>{{ n(l.stats['avec_niveau']) }}</strong></div>
            }
            <div class="bea-cl-stat"><span>Déjà classés</span><strong>{{ n(l.stats['deja_classes']) }}</strong></div>
            <div class="bea-cl-stat"><span>Classés manuellement</span><strong>{{ n(l.stats['manuels']) }}</strong></div>
          </div>
        }
      </section>

      @if (l.colonne_racine) {
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Opérations</h2></div>
          <div class="bea-cl-options" style="padding:0 1.1rem">
            <button type="button" class="bea-cl-option" (click)="evaluer()" [disabled]="busy() || !l.stats['racines_ok']">
              <mat-icon>calculate</mat-icon><strong>Évaluer avec le moteur</strong>
              <span>Score CDC 1.0 sur tous les critères, sans rien écrire (≤ {{ n(l.limite_evaluation) }} racines).</span>
            </button>
            @if (store.cap().classif_executer) {
              <button type="button" class="bea-cl-option" (click)="classer('MOTEUR')" [disabled]="busy() || !l.evaluation?.classables">
                <mat-icon>rule</mat-icon><strong>Classer selon le moteur</strong>
                <span>Applique le niveau calculé aux racines classables. Conflits à arbitrer exclus.</span>
              </button>
              @if (l.colonne_niveau) {
                <button type="button" class="bea-cl-option" (click)="classer('FICHIER')" [disabled]="busy() || !l.stats['avec_niveau']">
                  <mat-icon>file_download_done</mat-icon><strong>Reprendre le niveau du fichier</strong>
                  <span>Source {{ l.type === 'SITUATION' ? 'EXCEL_CONFORMITE' : 'EXCEL' }}. Motif de classement obligatoire.</span>
                </button>
              }
            }
          </div>
          @if (store.cap().classif_executer) {
            <label class="bea-cl-check" style="padding:0.75rem 1.1rem 0"><input type="checkbox" [(ngModel)]="forcer" /> Remplacer aussi les classements manuels (sinon ils sont préservés)</label>
          }
          @if (l.evaluation; as ev) {
            <div class="bea-cl-stats">
              <div class="bea-cl-stat"><span>Évaluées</span><strong>{{ n(ev.nb) }}</strong></div>
              <div class="bea-cl-stat" data-tone="ok"><span>Classables</span><strong>{{ n(ev.classables) }}</strong></div>
              <div class="bea-cl-stat" [attr.data-tone]="ev.a_arbitrer ? 'warn' : ''"><span>À arbitrer</span><strong>{{ n(ev.a_arbitrer) }}</strong></div>
              @for (k of niveaux; track k) {
                <div class="bea-cl-stat"><span>{{ k === 'NON_CLASSE' ? 'Non classé' : k }}</span><strong>{{ n(ev.par_niveau[k] || 0) }}</strong></div>
              }
            </div>
          }
          @if (l.dernier_classement; as b) {
            <div class="bea-cl-note bea-cl-note--info" style="margin:0 1.1rem 0.9rem"><mat-icon>task_alt</mat-icon>
              <span>Dernier classement ({{ b.origine === 'MOTEUR' ? 'moteur' : 'fichier' }}) : {{ b.ecrits }} écrit(s), {{ b.inchanges }} inchangé(s), {{ b.manuels_preserves }} manuel(s) préservé(s), {{ b.non_classables }} non classable(s).</span>
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
                <option value="INCONNUE">Inconnues</option>
                <option value="INVALIDE">Invalides</option>
                <option value="DOUBLON">Doublons</option>
              </select>
              <span class="bea-mg__count">{{ n(l.total_filtre) }}</span>
            </span>
          </div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr>
                <th>Ligne</th><th>Racine</th><th>État</th><th>Nom</th>
                @for (c of l.colonnes_affichees || []; track c) { <th>{{ c }}</th> }
                @if (l.colonne_niveau) { <th>Niveau fichier</th> }
                <th>Classe actuelle</th><th>Moteur</th><th>Motif moteur</th>
              </tr></thead>
              <tbody>
                @for (x of l.lignes; track x.ligne) {
                  <tr>
                    <td>{{ x.ligne }}</td>
                    <td>
                      @if (x.statut === 'OK') { <a [routerLink]="['/clientele/clients', x.racine]"><code>{{ x.racine }}</code></a> }
                      @else { <code>{{ x.racine || x.brut || '—' }}</code> }
                    </td>
                    <td><span class="bea-cl-badge" [attr.data-s]="x.statut">{{ libStatut[x.statut] || x.statut }}</span></td>
                    <td>{{ x.nom || x.nom_fichier || '—' }}</td>
                    @for (c of l.colonnes_affichees || []; track c) { <td>{{ x.colonnes[c] ?? '—' }}</td> }
                    @if (l.colonne_niveau) {
                      <td>
                        @if (x.niveau_fichier) { <span class="bea-cl-badge" [attr.data-s]="x.niveau_fichier">{{ x.niveau_fichier }}</span> }
                        @else { {{ x.niveau_fichier_brut || '—' }} }
                      </td>
                    }
                    <td>
                      @if (x.classe_actuelle) { <span class="bea-cl-badge" [attr.data-s]="x.classe_actuelle">{{ x.classe_actuelle }}</span> <small class="bea-cl-hint">{{ x.source_actuelle }}</small> }
                      @else { — }
                    </td>
                    <td>
                      @if (x.moteur; as m) {
                        <span class="bea-cl-badge" [attr.data-s]="m.niveau || m.statut">{{ m.niveau || 'NON CLASSÉ' }}</span>
                        <small class="bea-cl-hint"> {{ n(m.score) }}@if (m.statut !== 'EVALUE') { · {{ m.statut }}}</small>
                      } @else { — }
                    </td>
                    <td style="max-width:28rem">{{ x.moteur?.motif || '—' }}</td>
                  </tr>
                } @empty {
                  <tr><td colspan="12"><div class="bea-cl-empty">Aucune ligne.</div></td></tr>
                }
              </tbody>
            </table>
          </div>
          @if (l.total_filtre > l.lignes.length) {
            <div class="bea-cl-bar" style="position:static">
              <span>Page {{ l.page }} — {{ l.lignes.length }} ligne(s) affichée(s) sur {{ n(l.total_filtre) }}</span>
              <span style="display:flex;gap:0.5rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="l.page <= 1" (click)="page(l.page - 1)">Précédent</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="l.page * 300 >= l.total_filtre" (click)="page(l.page + 1)">Suivant</button>
              </span>
            </div>
          }
        </section>
      }
    }
  `,
})
export class ClLotComponent {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly type = input.required<TypeLot>();
  readonly textes = computed(() => TEXTES[this.type()]);
  readonly lot = signal<Lot | null>(null);
  readonly busy = signal(false);
  readonly survol = signal(false);
  readonly niveaux = ['FAIBLE', 'MOYEN', 'ELEVE', 'INTERDIT', 'NON_CLASSE'];
  readonly libStatut: Record<string, string> = { OK: 'Reconnue', INCONNUE: 'Inconnue', INVALIDE: 'Invalide', DOUBLON: 'Doublon' };
  readonly n = n;
  colRacine: string | null = null;
  colNiveau = '';
  colMotif = '';
  filtre = '';
  forcer = false;

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
    this.feedback.run(() => this.api.post<Lot>(`${CL_BASE}/lots/analyse?type=${this.type()}`, fd), {
      busy: this.busy, loading: 'Analyse du fichier…',
      success: (l) => l.colonne_racine
        ? { title: 'Analyse terminée', message: `${l.stats['racines_ok'] ?? 0} racine(s) reconnue(s) sur ${l.stats['lignes'] ?? 0} ligne(s)` }
        : { title: 'Fichier lu', message: 'Choisissez la colonne Racine client.' },
      errorTitle: "Échec de l'analyse", retry: false,
    }).subscribe((l) => this.ouvrir(l));
  }

  private ouvrir(l: Lot): void {
    this.colRacine = l.colonne_racine;
    this.colNiveau = l.colonne_niveau ?? '';
    this.colMotif = l.colonne_motif ?? '';
    this.lot.set(l);
  }

  recartographier(): void {
    const l = this.lot()!;
    this.filtre = '';
    this.feedback.run(() => this.api.post<Lot>(`${CL_BASE}/lots/${l.id}/mapping`, {
      colonne_racine: this.colRacine, colonne_niveau: this.colNiveau, colonne_motif: this.colMotif || null,
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

  evaluer(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.post<Lot>(`${CL_BASE}/lots/${l.id}/evaluer`, {}), {
      busy: this.busy, loading: `Évaluation de ${l.stats['racines_ok']} racine(s)…`,
      success: (x) => ({ title: 'Évaluation terminée (simulation)', message: `${x.evaluation?.classables ?? 0} racine(s) classable(s), ${x.evaluation?.a_arbitrer ?? 0} à arbitrer` }),
      errorTitle: 'Évaluation refusée', retry: false,
    }).subscribe((x) => { this.filtre = ''; this.lot.set(x); });
  }

  classer(origine: 'MOTEUR' | 'FICHIER'): void {
    const l = this.lot()!;
    const nb = origine === 'MOTEUR' ? l.evaluation?.classables ?? 0 : l.stats['avec_niveau'] ?? 0;
    this.feedback.runWithReason(
      (motif) => this.api.post<Lot & { bilan: Bilan }>(`${CL_BASE}/lots/${l.id}/classer`, { origine, motif, forcer: this.forcer }),
      {
        reason: {
          title: origine === 'MOTEUR' ? 'Classer selon le moteur' : 'Reprendre le niveau du fichier',
          message: `Enregistrer la classification de ${nb} client(s) du fichier « ${l.fichier_nom} » ?`,
          hint: this.forcer
            ? 'Les classements manuels seront remplacés. Historique conservé.'
            : 'Les classements manuels sont préservés. Historique conservé.',
          reasonLabel: 'Motif de classement', reasonPlaceholder: 'Ex. revue Conformité du 08/10/2026', maxLength: 500,
          confirmLabel: 'Classer', tone: 'primary',
        },
        busy: this.busy, loading: 'Classement en cours…',
        success: (x) => ({ title: 'Classement enregistré', details: [
          { label: 'Écrits', value: String(x.bilan.ecrits) },
          { label: 'Inchangés', value: String(x.bilan.inchanges) },
          { label: 'Manuels préservés', value: String(x.bilan.manuels_preserves) },
          { label: 'Non classables', value: String(x.bilan.non_classables) },
        ] }),
        errorTitle: 'Classement refusé', retry: false,
      },
    ).subscribe((x) => { this.filtre = ''; this.lot.set(x); });
  }

  exporter(): void {
    const l = this.lot()!;
    this.api.download(`${CL_BASE}/lots/${l.id}/export.xlsx`).subscribe({
      next: (b) => telecharger(b, `lot-${l.fichier_nom.replace(/\.xlsx?m?$/i, '')}-resultat.xlsx`),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export impossible')),
    });
  }

  fermer(): void {
    const l = this.lot()!;
    this.feedback.run(() => this.api.delete<void>(`${CL_BASE}/lots/${l.id}`), {
      confirm: { action: 'annulation', title: 'Fermer le fichier', message: `Fermer « ${l.fichier_nom} » ?`, hint: 'Le fichier temporaire est supprimé. Les classements déjà enregistrés sont conservés.' },
      busy: this.busy, success: { title: 'Fichier fermé' }, errorTitle: 'Action impossible',
    }).subscribe(() => { this.lot.set(null); this.filtre = ''; });
  }
}
