import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, FicheClient, MODES_DECISION, TraceClassification, dateFr, dateHeureFr } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface EvaluationMoteur {
  score_total: number; niveau_final: string | null; statut: string; admissible: boolean;
  motif_principal: string | null; motif_genere?: string; avertissement?: string;
  date_reference: string | null; source_date_reference: string | null;
  version_moteur: string; version_regles: string;
  lignes: {
    critere: string; libelle: string; etat: string; valeur: string | null; source_donnee: string | null;
    poids: number | null; motif: string; blocking_propose: boolean; contribue_au_score: boolean;
  }[];
}

interface HistoriqueClassif extends Partial<TraceClassification> {
  id: string; ancienne_classe: string | null; nouvelle_classe: string; source: string;
  motif_classement: string | null; utilisateur: string | null; date: string | null;
}

const RESULTATS: Record<string, string> = {
  ECRIT: 'Classification enregistrée',
  INCHANGE: 'Classification inchangée (même niveau)',
  MANUEL_PRESERVE: 'Décision manuelle préservée : réexamen ouvert',
  NON_ADMISSIBLE: 'Résultat non admissible : rien n’a été enregistré',
};

@Component({
  selector: 'bea-cl-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent],
  styles: `
    .bea-cl-decision { display: grid; grid-template-columns: minmax(10rem, 13rem) minmax(16rem, 1fr) auto auto; align-items: end; gap: 0.75rem; padding: 0.95rem 1.1rem; }
    .bea-cl-decision > label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.72rem; font-weight: 700; color: #64748b; text-transform: uppercase; }
    .bea-cl-decision select, .bea-cl-decision__motif input { font: inherit; font-size: 0.88rem; font-weight: 500; text-transform: none; min-height: 2.5rem; padding: 0.5rem 0.65rem; border: 1px solid #cbd5e1; border-radius: 0.6rem; background: #fff; color: #0f172a; }
    .bea-cl-decision select:focus, .bea-cl-decision__motif input:focus { outline: none; border-color: #1a5278; box-shadow: 0 0 0 3px rgba(26, 82, 120, 0.15); }
    .bea-cl-decision > .bea-cl-decision__force { flex-direction: row; align-items: center; gap: 0.55rem; min-height: 2.5rem; padding: 0.35rem 0.75rem; border: 1px dashed #cbd5e1; border-radius: 0.6rem; background: #f8fafc; text-transform: none; cursor: pointer; }
    .bea-cl-decision__force input { width: 1.05rem; height: 1.05rem; accent-color: #b45309; }
    .bea-cl-decision__force span { display: flex; flex-direction: column; line-height: 1.2; }
    .bea-cl-decision__force strong { font-size: 0.82rem; color: #0f172a; }
    .bea-cl-decision__force small { font-size: 0.7rem; font-weight: 500; color: #64748b; }
    .bea-cl-decision__force.is-on { border-style: solid; border-color: #f59e0b; background: #fffbeb; }
    .bea-cl-decision__force.is-on strong { color: #b45309; }
    .bea-cl-decision__btn { min-height: 2.5rem; padding: 0.55rem 1.15rem; white-space: nowrap; }
    @media (max-width: 900px) { .bea-cl-decision { grid-template-columns: 1fr; } .bea-cl-decision__btn { justify-content: center; } }
  `,
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/situation-pp"><mat-icon>arrow_back</mat-icon> Situations</button>
          <h1>Client {{ f()?.client?.['racine_client'] }}</h1>
          <p class="bea-cl-head__sub">{{ f()?.client?.['raison_sociale'] }}</p>
        </div>
      </header>
      @if (f(); as x) {
        <div class="bea-cl-grid">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Identité</h2>
              @if (x.situation) { <span class="bea-cl-badge" [attr.data-s]="x.situation.profil_derive">{{ x.situation.profil_derive }}</span> }
            </div>
            <dl class="bea-cl-dl">
              <dt>Racine</dt><dd><code>{{ x.client['racine_client'] }}</code></dd>
              <dt>Nom</dt><dd>{{ x.client['raison_sociale'] }}</dd>
              <dt>Prénoms</dt><dd>{{ x.client['prenoms'] || '—' }}</dd>
              <dt>Nationalité</dt><dd>{{ x.client['nationalite'] || '—' }}</dd>
              <dt>Résident</dt><dd>{{ x.client['statut_resident'] || '—' }}</dd>
              <dt>NNI</dt><dd>{{ x.client['nni'] || '—' }}</dd>
              <dt>NIF</dt><dd>{{ x.client['nif'] || '—' }}</dd>
              <dt>Catégorie</dt><dd>{{ x.client['categorie_juridique'] || '—' }}</dd>
              <dt>Agent éco.</dt><dd>{{ x.client['agent_economique'] || '—' }}</dd>
              <dt>Extraction</dt><dd>{{ dateFr(x.client['date_extraction']) }}</dd>
            </dl>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Agrégats</h2></div>
            <dl class="bea-cl-dl">
              <dt>État</dt><dd>{{ x.situation?.etat_client || '—' }}</dd>
              <dt>Agence</dt><dd>{{ agenceLib(x.situation?.code_agence, x.situation?.agence) }}</dd>
              <dt>Date ouv.</dt><dd>{{ dateFr(x.situation?.date_ouverture) }}</dd>
              <dt>Comptes</dt><dd>{{ x.situation?.nb_comptes }}</dd>
              <dt>Classe risque</dt>
              <dd>@if (x.classification) { <span class="bea-cl-badge" [attr.data-s]="x.classification.niveau">{{ x.classification.niveau }}</span> } @else { Non classé }</dd>
              <dt>Dernier import</dt><dd>{{ x.dernier_import?.fichier_nom || '—' }}</dd>
            </dl>
          </section>
        </div>
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Classification retenue</h2>
            @if (x.classification) {
              <span class="bea-cl-badge" [attr.data-s]="x.classification.source">{{ modes[x.classification.mode_decision || ''] || x.classification.source }}</span>
            }
          </div>
          @if (x.classification; as c) {
            <dl class="bea-cl-dl">
              <dt>Niveau retenu</dt><dd><span class="bea-cl-badge" [attr.data-s]="c.niveau">{{ c.niveau }}</span>
                @if (c.force) { <small class="bea-cl-hint"> · forcé</small> }
                @if (c.blocage_leve) { <small class="bea-cl-hint"> · levée de blocage INTERDIT</small> }
              </dd>
              <dt>Mode de décision</dt><dd>{{ modes[c.mode_decision || ''] || '—' }} <small class="bea-cl-hint">({{ c.source }})</small></dd>
              <dt>Score calculé</dt><dd>{{ c.score_calcule ?? '—' }}</dd>
              <dt>Niveau proposé (moteur)</dt><dd>{{ c.niveau_propose || '—' }}</dd>
              <dt>Classe du fichier</dt><dd>{{ c.classe_source_fichier || '—' }}</dd>
              <dt>Motif moteur</dt><dd>{{ c.motif_moteur || '—' }}</dd>
              <dt>Motif source</dt><dd>{{ c.motif_source || c.motif_risque || '—' }}</dd>
              <dt>Motif décision manuelle</dt><dd>{{ c.motif_decision_manuelle || '—' }}</dd>
              <dt>Motif classement</dt><dd>{{ c.motif_classement || '—' }}</dd>
              <dt>Analyste KYC</dt><dd>{{ c.analyste_kyc || '—' }}</dd>
              <dt>Mise à jour métier</dt><dd>{{ dateFr(c.date_maj_metier) }}</dd>
              <dt>Date de référence</dt><dd>{{ dateFr(c.date_reference) }}</dd>
              <dt>Classé le</dt><dd>{{ dateHeureFr(c.classifie_le) }}</dd>
              <dt>Versions</dt><dd>{{ c.version_moteur || '—' }} / {{ c.version_regles || '—' }}</dd>
            </dl>
          } @else {
            <p class="bea-cl-hint" style="padding:0.9rem 1.1rem">Pas encore classé. Une donnée absente n’est jamais Faible. 0 critère exploitable → NON CLASSÉ (jamais enregistré).</p>
          }
        </section>

        @if (store.cap().classif_voir) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Moteur de scoring (CDC 1.0)</h2>
              <span style="display:flex;gap:0.4rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="evaluer()" [disabled]="busy()"><mat-icon>calculate</mat-icon> Évaluer avec le moteur</button>
                @if (store.cap().classif_executer && evaluation()?.admissible) {
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="enregistrerMoteur()" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer le résultat du moteur</button>
                }
              </span>
            </div>
            @if (evaluation(); as e) {
              <dl class="bea-cl-dl">
                <dt>Score</dt><dd><strong>{{ e.score_total }}</strong> — {{ e.niveau_final || 'NON CLASSÉ' }} <small class="bea-cl-hint">({{ e.statut }})</small></dd>
                <dt>Admissible</dt><dd>{{ e.admissible ? 'Oui' : 'Non — ne peut pas être enregistré comme classification valide' }}</dd>
                <dt>Motif</dt><dd>{{ e.motif_genere || e.motif_principal || '—' }}</dd>
                <dt>Date de référence</dt><dd>{{ dateFr(e.date_reference) }} <small class="bea-cl-hint">{{ libRef[e.source_date_reference || ''] || e.source_date_reference }}</small></dd>
                <dt>Versions</dt><dd>{{ e.version_moteur }} / {{ e.version_regles }}</dd>
              </dl>
              @if (e.avertissement) { <div class="bea-cl-note" style="margin:0 1.1rem 0.9rem"><mat-icon>info</mat-icon><span>{{ e.avertissement }}</span></div> }
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead><tr><th>Critère</th><th>Valeur</th><th>Source</th><th>État</th><th>Poids</th><th>Compté</th><th>Motif</th></tr></thead>
                  <tbody>
                    @for (lg of e.lignes; track lg.critere) {
                      <tr>
                        <td>{{ lg.libelle }}</td>
                        <td>{{ lg.valeur || '—' }}</td>
                        <td>{{ lg.source_donnee || '—' }}</td>
                        <td><span class="bea-cl-badge" [attr.data-s]="lg.etat">{{ lg.etat }}</span>@if (lg.blocking_propose) { <small class="bea-cl-hint"> bloquant</small> }</td>
                        <td>{{ lg.poids ?? '—' }}</td>
                        <td>{{ lg.contribue_au_score ? 'Oui' : '—' }}</td>
                        <td style="max-width:30rem">{{ lg.motif }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <p class="bea-cl-hint" style="padding:0.9rem 1.1rem">Évaluation explicable : score, critères, motif. Rien n’est enregistré tant que vous ne le confirmez pas.</p>
            }
          </section>
        }

        @if (store.cap().classif_executer) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Décision manuelle</h2></div>
            <div class="bea-cl-decision">
              <label>Niveau retenu
                <select [(ngModel)]="niveau"><option>FAIBLE</option><option>MOYEN</option><option>ELEVE</option><option>INTERDIT</option></select>
              </label>
              <label class="bea-cl-decision__motif">Motif de la décision (obligatoire)
                <input [(ngModel)]="motif" maxlength="2000" placeholder="Ex. revue KYC du 15/10 : activité confirmée" />
              </label>
              @if (store.cap().classif_forcer) {
                <label class="bea-cl-decision__force" [class.is-on]="forcer">
                  <input type="checkbox" [(ngModel)]="forcer" />
                  <span><strong>Forçage</strong><small>Lever un blocage INTERDIT du moteur</small></span>
                </label>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--primary bea-cl-decision__btn" (click)="classer()" [disabled]="busy() || !motif.trim()">
                <mat-icon>gavel</mat-icon> Enregistrer la décision
              </button>
            </div>
            <p class="bea-cl-hint" style="padding:0 1.1rem 0.9rem">Auteur, date, niveau retenu et motif sont historisés. Un INTERDIT proposé par le moteur ne peut être abaissé que par forçage (permission dédiée).</p>
          </section>
        }

        @if (historique().length) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Historique de classification</h2><span class="bea-mg__count">{{ historique().length }}</span></div>
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Date</th><th>Utilisateur</th><th>Ancien → nouveau</th><th>Mode</th><th>Score / proposé</th><th>Fichier</th><th>Motif</th><th>Analyste KYC</th><th>Lot / ligne</th></tr></thead>
                <tbody>
                  @for (h of historique(); track h.id) {
                    <tr>
                      <td>{{ dateHeureFr(h.date) }}</td>
                      <td>{{ h.utilisateur || '—' }}</td>
                      <td>{{ h.ancienne_classe || '—' }} → <strong>{{ h.nouvelle_classe }}</strong>
                        @if (h.force) { <small class="bea-cl-hint"> forcé</small> }
                        @if (h.blocage_leve) { <small class="bea-cl-hint"> levée INTERDIT</small> }
                      </td>
                      <td>{{ modes[h.mode_decision || ''] || h.source }}</td>
                      <td>{{ h.score_calcule ?? '—' }} / {{ h.niveau_propose || '—' }}</td>
                      <td>{{ h.classe_source_fichier || '—' }}</td>
                      <td style="max-width:24rem">{{ h.motif_decision_manuelle || h.motif_classement || '—' }}</td>
                      <td>{{ h.analyste_kyc || '—' }}</td>
                      <td>{{ h.lot_id ? 'Lot · L' + h.ligne_source : '—' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }
        @if (x.alertes_ouvertes.length) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Alertes ouvertes</h2></div>
            <ul class="bea-cl-anoms">
              @for (al of x.alertes_ouvertes; track al.id) {
                <li data-n="alerte"><mat-icon>notification_important</mat-icon>
                  <a [routerLink]="['/clientele/filtrage', al.id]">{{ al.motif }} — {{ al.statut }}</a>
                  @if (al.precedent_faux_positif) { (FP antérieur) }
                </li>
              }
            </ul>
          </section>
        }
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Comptes / RIB</h2><span class="bea-mg__count">{{ x.comptes.length }}</span></div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th>Compte</th><th>RIB</th><th>Agence</th><th>État</th><th>Devise</th><th>Ouverture</th></tr></thead>
              <tbody>
                @for (c of x.comptes; track c.compte) {
                  <tr>
                    <td><code>{{ c.compte }}</code></td>
                    <td><code>{{ c.rib }}</code></td>
                    <td>{{ agenceLib(c.code_agence, c.agence) }}</td>
                    <td><span class="bea-cl-badge" [attr.data-s]="c.etat_compte === 'FERME' ? 'CLOTURE' : 'OUVERT'">{{ c.etat_compte }}</span></td>
                    <td>{{ c.devise }}</td>
                    <td>{{ dateFr(c.date_ouverture) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </section>
      }
    </div>
  `,
})
export class ClFicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly store = inject(ClienteleStore);
  readonly f = signal<FicheClient | null>(null);
  readonly evaluation = signal<EvaluationMoteur | null>(null);
  readonly historique = signal<HistoriqueClassif[]>([]);
  readonly busy = signal(false);
  readonly dateFr = dateFr;
  readonly dateHeureFr = dateHeureFr;
  readonly modes = MODES_DECISION;
  readonly libRef: Record<string, string> = {
    EXTRACTION_ORION: 'date d’extraction ORION', DATE_CALCUL: 'date du calcul', PARAMETRE: 'paramètre', FOURNIE: 'fournie',
  };
  forcer = false;

  agenceLib(code: string | null | undefined, libelle: string | null | undefined): string {
    if (!code) return '—';
    return libelle ? `${code} — ${libelle}` : code;
  }
  niveau = 'MOYEN';
  motif = '';
  readonly hasUnsavedChanges = unsavedChanges(() => !!this.motif.trim());

  ngOnInit(): void {
    this.store.charger();
    this.recharger();
  }

  private racine(): string {
    return this.route.snapshot.paramMap.get('racine') ?? '';
  }

  private recharger(): void {
    const racine = this.racine();
    this.api.get<FicheClient>(`${CL_BASE}/clients/${racine}`).subscribe({
      next: (d) => this.f.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Fiche introuvable')),
    });
    this.api.get<HistoriqueClassif[]>(`${CL_BASE}/clients/${racine}/classification/historique`).subscribe({
      next: (h) => this.historique.set(h),
      error: () => this.historique.set([]),
    });
  }

  classer(): void {
    const racine = this.racine();
    const motif = this.motif.trim();
    if (!motif) {
      this.feedback.warning({ title: 'Motif obligatoire', message: 'Indiquez le motif de la décision manuelle.' });
      return;
    }
    const forcer = this.forcer && !!this.store.cap().classif_forcer;
    this.feedback.run(() => this.api.post(`${CL_BASE}/clients/${racine}/classification`, {
      niveau: this.niveau, motif_classement: motif, forcer, confirmation: forcer,
    }), {
      confirm: forcer
        ? { title: 'Forçage de classification', message: `FORÇAGE — retenir ${this.niveau} pour ${racine} ?`, hint: 'Lève un éventuel blocage INTERDIT du moteur. Action tracée dans l’audit (levée de blocage).', confirmLabel: 'Confirmer le forçage', tone: 'danger' }
        : { action: 'validation', title: 'Décision manuelle', message: `Retenir ${this.niveau} pour ${racine} ?`, hint: 'Auteur, date, niveau et motif historisés. Les imports ultérieurs ne remplaceront pas cette décision.' },
      busy: this.busy, success: { title: 'Décision enregistrée', message: `Niveau retenu : ${this.niveau}` }, errorTitle: 'Décision refusée', retry: false,
    }).subscribe(() => { this.motif = ''; this.forcer = false; this.recharger(); });
  }

  evaluer(): void {
    const racine = this.racine();
    this.feedback.run(() => this.api.post<EvaluationMoteur>(`${CL_BASE}/classification/evaluer`, { racine, persister: true }), {
      busy: this.busy, loading: 'Évaluation…',
      success: (e) => ({ title: 'Évaluation moteur', message: `Score ${e.score_total} — ${e.niveau_final || 'NON CLASSÉ'}${e.admissible ? '' : ' (non admissible)'}` }),
      errorTitle: 'Évaluation refusée',
    }).subscribe((e) => this.evaluation.set(e));
  }

  enregistrerMoteur(): void {
    const racine = this.racine();
    const e = this.evaluation();
    if (!e) return;
    this.feedback.runWithReason(
      (motif) => this.api.post<{ resultat: string }>(`${CL_BASE}/clients/${racine}/classification/moteur`, { motif }),
      {
        reason: {
          title: 'Enregistrer le résultat du moteur',
          message: `Retenir ${e.niveau_final} (score ${e.score_total}) pour ${racine} ?`,
          hint: 'Le moteur est réévalué au moment de l’enregistrement. Une décision manuelle existante est préservée (un réexamen est ouvert).',
          reasonLabel: 'Motif', maxLength: 500, confirmLabel: 'Enregistrer', tone: 'primary',
        },
        busy: this.busy, loading: 'Enregistrement…',
        success: (r) => ({ title: RESULTATS[r.resultat] ?? r.resultat }),
        errorTitle: 'Enregistrement refusé', retry: false,
      },
    ).subscribe(() => this.recharger());
  }
}
