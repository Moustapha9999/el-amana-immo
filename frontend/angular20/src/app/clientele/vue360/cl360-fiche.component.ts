import { ChangeDetectionStrategy, Component, ElementRef, OnInit, inject, input, output, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, CompteFiche, MODES_DECISION, TraceClassification, dateFr, dateHeureFr, n } from '../clientele.models';
import { Client360, LIB_MOTIF_CHAMP, LIB_NIVEAU, LIB_PROFIL } from './vue360.models';

interface Fiche360 {
  client: Record<string, string | null>;
  situation: { profil_derive: string; etat_client: string; code_agence: string | null; agence: string | null; nb_comptes: number; date_ouverture: string | null } | null;
  comptes: (CompteFiche & { liste_interdiction: string | null })[];
  synthese: Client360 | null;
  diagnostics: { code: string; libelle: string; definition: string; famille: string }[];
  autorisations: { classification: boolean };
  classification?: ({ niveau: string; source: string; motif_risque: string | null; motif_classement: string | null; classifie_le: string | null } & Partial<TraceClassification>) | null;
  historique_classification?: (Partial<TraceClassification> & { id: string; ancienne_classe: string | null; nouvelle_classe: string; source: string; motif_classement: string | null; utilisateur: string | null; date: string | null })[];
  derniere_evaluation?: {
    le: string | null; score_total: number; niveau_final: string | null; statut: string; coherence: string; motif_principal: string | null;
    version_moteur: string; version_regles: string; note: string;
    lignes: { critere: string; libelle: string; etat: string; valeur: string | null; poids: number | null; statut_regle: string; contribue_au_score: boolean; blocking_propose: boolean; motif: string }[];
  } | null;
  reexamens?: { id: string; statut: string; niveau_actuel: string | null; niveau_suggere: string; motif: string; cree_le: string | null; decision: string | null }[];
  alertes: { id: string; statut: string; motif: string; source: string; similarite: number; precedent_faux_positif: boolean; assignee: string | null; cree_le: string | null; derniere_action: string | null; cloturee_le: string | null }[];
  journal: { action: string; objet: string; objet_id: string | null; le: string | null; utilisateur: string | null }[];
}

type Onglet = 'synthese' | 'profilage' | 'filtrage' | 'alertes' | 'comptes' | 'historique';

@Component({
  selector: 'bea-cl360-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  host: { '(document:keydown.escape)': 'fermer.emit()' },
  template: `
    <div class="bea-cl-modal" (click)="fermer.emit()">
      <div class="bea-cl-modal__box bea-cl360-fiche" role="dialog" aria-modal="true" [attr.aria-label]="'Fiche 360° du client ' + racine()" (click)="$event.stopPropagation()" tabindex="-1">
        <div class="bea-cl-modal__head">
          <div>
            <p class="bea-cl-modal__kicker">Fiche client 360° · lecture seule</p>
            <h2>{{ f()?.client?.['raison_sociale'] || 'Client ' + racine() }}</h2>
            <p class="bea-cl-modal__sub">Racine {{ racine() }} · {{ libProfil[f()?.situation?.profil_derive || ''] || '—' }} · {{ f()?.situation?.nb_comptes ?? '—' }} compte(s)</p>
          </div>
          <div class="bea-cl-modal__head-r">
            <button type="button" class="bea-cl-modal__close" (click)="fermer.emit()" aria-label="Fermer la fiche"><mat-icon>close</mat-icon></button>
          </div>
        </div>
        <div class="bea-cl-modal__body">
          @if (erreur()) {
            <div class="bea-cl360-state" data-s="erreur"><mat-icon>cloud_off</mat-icon>{{ erreur() }}</div>
          } @else if (!f()) {
            <div class="bea-cl360-state">Chargement de la fiche…</div>
          } @else {
            @let x = f()!;
            <nav class="bea-cl-tabs" aria-label="Sections de la fiche">
              @for (o of onglets; track o.code) {
                @if (o.code !== 'profilage' || x.autorisations.classification) {
                  <button type="button" [class.is-on]="onglet() === o.code" (click)="onglet.set(o.code)">{{ o.libelle }}
                    @if (o.code === 'alertes' && alertesOuvertes()) { <span class="bea-cl-tabs__n">{{ alertesOuvertes() }}</span> }
                  </button>
                }
              }
            </nav>
            @switch (onglet()) {
              @case ('synthese') {
                <div class="bea-cl-modal__cols">
                  <section>
                    <h3>Identité</h3>
                    <dl class="bea-cl-dl">
                      <dt>Racine</dt><dd><code>{{ x.client['racine_client'] }}</code></dd>
                      <dt>Nom</dt><dd>{{ x.client['raison_sociale'] }} {{ x.client['prenoms'] || '' }}</dd>
                      <dt>Type</dt><dd>{{ libProfil[x.situation?.profil_derive || ''] || '—' }} <small class="bea-cl-hint">(heuristique ORION)</small></dd>
                      <dt>NNI / NIF</dt><dd>{{ x.client['nni'] || '—' }} / {{ x.client['nif'] || '—' }}</dd>
                      <dt>Nationalité</dt><dd>{{ x.client['nationalite'] || '—' }}</dd>
                      <dt>Agence</dt><dd>{{ x.situation?.code_agence || '—' }} {{ x.situation?.agence || '' }}</dd>
                      <dt>État</dt><dd>{{ x.situation?.etat_client || '—' }}</dd>
                      <dt>Extraction</dt><dd>{{ dateFr(x.client['date_extraction']) }}</dd>
                    </dl>
                  </section>
                  <section>
                    <h3>Situation de conformité</h3>
                    <dl class="bea-cl-dl">
                      @if (x.synthese?.classification; as k) {
                        <dt>Niveau enregistré</dt><dd>@if (k.niveau) { <span class="bea-cl-badge" [attr.data-s]="k.niveau">{{ libNiveau[k.niveau] }}</span> } @else { Non évalué }</dd>
                        <dt>Score enregistré</dt><dd>{{ k.score_enregistre ?? '—' }}</dd>
                        <dt>Mode</dt><dd>{{ modes[k.mode_decision || ''] || k.source || '—' }}</dd>
                        <dt>Classé le</dt><dd>{{ dh(k.classifie_le) }}</dd>
                      }
                      <dt>Complétude</dt><dd>{{ x.synthese?.completude === 'COMPLET' ? 'Complet' : 'Incomplet' }}</dd>
                      <dt>Alertes</dt><dd>{{ alertesOuvertes() }} ouverte(s) · {{ x.alertes.length }} au total</dd>
                    </dl>
                  </section>
                </div>
                <h3 class="bea-cl-hint" style="margin:1rem 0 0.4rem;text-transform:uppercase">Contrôles (diagnostics, pas des motifs moteur)</h3>
                <ul class="bea-cl-anoms" style="padding:0">
                  @for (d of x.diagnostics; track d.code) {
                    <li data-n="alerte"><mat-icon>report_problem</mat-icon><span><strong>{{ d.libelle }}</strong> — {{ d.definition }}</span></li>
                  } @empty { <li data-n="info"><mat-icon>check_circle</mat-icon><span>Aucun contrôle en écart pour ce client.</span></li> }
                </ul>
              }
              @case ('profilage') {
                @if (x.classification; as c) {
                  <dl class="bea-cl-dl">
                    <dt>Niveau retenu</dt><dd><span class="bea-cl-badge" [attr.data-s]="c.niveau">{{ libNiveau[c.niveau] || c.niveau }}</span> @if (c.force) { <small class="bea-cl-hint">forcé</small> }</dd>
                    <dt>Mode de décision</dt><dd>{{ modes[c.mode_decision || ''] || c.source }}</dd>
                    <dt>Score enregistré</dt><dd>{{ c.score_calcule ?? '—' }} <small class="bea-cl-hint">niveau proposé : {{ c.niveau_propose || '—' }}</small></dd>
                    <dt>Motif moteur (enregistré)</dt><dd>{{ c.motif_moteur || '—' }}</dd>
                    <dt>Motif source (enregistré)</dt><dd>{{ c.motif_source || '—' }}</dd>
                    <dt>Motif décision manuelle</dt><dd>{{ c.motif_decision_manuelle || '—' }}</dd>
                    <dt>Motif de classement</dt><dd>{{ c.motif_classement || '—' }}</dd>
                    <dt>Versions</dt><dd>{{ c.version_moteur || '—' }} / {{ c.version_regles || '—' }}</dd>
                    <dt>Classé le</dt><dd>{{ dh(c.classifie_le) }}</dd>
                  </dl>
                } @else {
                  <p class="bea-cl-hint">Aucune classification enregistrée. Une donnée absente n’est jamais Faible.</p>
                }
                @if (x.derniere_evaluation; as e) {
                  <h3 class="bea-cl-hint" style="margin:1rem 0 0.4rem;text-transform:uppercase">Dernière évaluation photographiée — {{ dh(e.le) }}</h3>
                  <p class="bea-cl-hint">{{ e.note }} Score {{ e.score_total }} · {{ e.niveau_final || 'NON CLASSÉ' }} · {{ e.statut }} / {{ e.coherence }} · {{ e.version_regles }}</p>
                  <div class="bea-mg__table-wrap">
                    <table class="bea-mg__table bea-cl360-table is-souple">
                      <thead><tr><th>Critère</th><th>Valeur</th><th>État</th><th>Règle</th><th>Poids</th><th>Compté</th><th>Motif</th></tr></thead>
                      <tbody>
                        @for (lg of e.lignes; track lg.critere) {
                          <tr>
                            <td>{{ lg.libelle }}</td><td>{{ lg.valeur || '—' }}</td>
                            <td><span class="bea-cl-badge" [attr.data-s]="lg.etat">{{ lg.etat }}</span></td>
                            <td><span class="bea-cl-badge" [attr.data-s]="lg.statut_regle">{{ lg.statut_regle }}</span></td>
                            <td>{{ lg.poids ?? '—' }}</td><td>{{ lg.contribue_au_score ? 'Oui' : '—' }}</td>
                            <td class="bea-cl360-motif">{{ lg.motif }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
                @if (x.reexamens?.length) {
                  <h3 class="bea-cl-hint" style="margin:1rem 0 0.4rem;text-transform:uppercase">Réexamens</h3>
                  <ul class="bea-cl-anoms" style="padding:0">
                    @for (r of x.reexamens; track r.id) {
                      <li [attr.data-n]="r.statut === 'OUVERT' ? 'alerte' : 'info'"><mat-icon>rule</mat-icon><span><strong>{{ r.statut }}</strong> — {{ r.niveau_actuel || '—' }} → {{ r.niveau_suggere }} : {{ r.motif }} ({{ dh(r.cree_le) }})</span></li>
                    }
                  </ul>
                }
              }
              @case ('filtrage') {
                <p class="bea-cl-hint">Valeurs brutes ORION du champ Liste d’interdiction par compte. Une inscription n’est ni un rapprochement ni une décision de conformité.</p>
                <div class="bea-mg__table-wrap">
                  <table class="bea-mg__table bea-cl360-table is-souple">
                    <thead><tr><th>Compte</th><th>État</th><th>Liste d’interdiction (ORION)</th></tr></thead>
                    <tbody>
                      @for (c of x.comptes; track c.compte) {
                        <tr><td><code>{{ c.compte }}</code></td><td>{{ c.etat_compte }}</td><td>{{ codes(c.liste_interdiction) }}</td></tr>
                      }
                    </tbody>
                  </table>
                </div>
                <p class="bea-cl-hint" style="margin-top:0.8rem">Rapprochements : {{ x.alertes.length }} correspondance(s) enregistrée(s) — détail dans l’onglet Alertes.</p>
              }
              @case ('alertes') {
                <div class="bea-mg__table-wrap">
                  <table class="bea-mg__table bea-cl360-table is-souple">
                    <thead><tr><th>Créée le</th><th>Source</th><th>Motif</th><th>Similarité</th><th>Statut</th><th>Agent</th><th>Dernière action</th><th></th></tr></thead>
                    <tbody>
                      @for (a of x.alertes; track a.id) {
                        <tr>
                          <td>{{ dh(a.cree_le) }}</td><td>{{ a.source }}</td><td>{{ a.motif }}@if (a.precedent_faux_positif) { <small class="bea-cl-hint"> FP antérieur</small> }</td>
                          <td>{{ a.similarite }}</td><td><span class="bea-cl-badge" [attr.data-s]="a.statut">{{ a.statut }}</span></td>
                          <td>{{ a.assignee || 'Non attribuée' }}</td><td>{{ dh(a.derniere_action) }}</td>
                          <td class="is-act"><span class="bea-cl-row-actions"><a [routerLink]="['/clientele/filtrage', a.id]" aria-label="Ouvrir le dossier d’alerte"><mat-icon>open_in_new</mat-icon></a></span></td>
                        </tr>
                      } @empty { <tr><td colspan="8"><div class="bea-cl-empty">Aucune alerte pour ce client.</div></td></tr> }
                    </tbody>
                  </table>
                </div>
              }
              @case ('comptes') {
                <div class="bea-mg__table-wrap">
                  <table class="bea-mg__table bea-cl360-table is-souple">
                    <thead><tr><th>Compte</th><th>RIB</th><th>Agence</th><th>État</th><th>Devise</th><th>Ouverture</th><th>Conformité</th></tr></thead>
                    <tbody>
                      @for (c of x.comptes; track c.compte) {
                        <tr><td><code>{{ c.compte }}</code></td><td><code>{{ c.rib }}</code></td><td>{{ c.code_agence || '—' }}</td><td>{{ c.etat_compte }}</td><td>{{ c.devise }}</td><td>{{ dateFr(c.date_ouverture) }}</td><td>{{ c.conformite_compte || '—' }}</td></tr>
                      }
                    </tbody>
                  </table>
                </div>
              }
              @case ('historique') {
                @if (x.historique_classification?.length) {
                  <h3 class="bea-cl-hint" style="margin:0 0 0.4rem;text-transform:uppercase">Historique de classification</h3>
                  <ul class="bea-cl-timeline">
                    @for (h of x.historique_classification; track h.id) {
                      <li><strong>{{ h.ancienne_classe || '—' }} → {{ h.nouvelle_classe }} · {{ modes[h.mode_decision || ''] || h.source }} · score {{ h.score_calcule ?? '—' }}</strong>
                        <span>{{ dh(h.date) }} · {{ h.utilisateur || '—' }} · {{ h.version_regles || '—' }} · {{ h.motif_decision_manuelle || h.motif_classement || '—' }}</span></li>
                    }
                  </ul>
                }
                <h3 class="bea-cl-hint" style="margin:1rem 0 0.4rem;text-transform:uppercase">Journal d’audit (100 dernières actions)</h3>
                <ul class="bea-cl-timeline">
                  @for (j of x.journal; track $index) {
                    <li><strong>{{ j.action }}</strong><span>{{ dh(j.le) }} · {{ j.utilisateur || '—' }} · {{ j.objet }}</span></li>
                  } @empty { <li><span>Aucune action tracée.</span></li> }
                </ul>
              }
            }
          }
        </div>
        <div class="bea-cl-modal__foot">
          <div class="bea-cl-modal__foot-l"><span class="bea-cl-hint">Aucun recalcul à l’ouverture. Consultation tracée dans l’audit.</span></div>
          <div class="bea-cl-modal__foot-r">
            <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/clientele/clients', racine()]"><mat-icon>badge</mat-icon> Fiche complète et actions</a>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer.emit()">Fermer</button>
          </div>
        </div>
      </div>
    </div>
  `,
})
export class Cl360FicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly el = inject(ElementRef<HTMLElement>);
  readonly racine = input.required<string>();
  readonly fermer = output<void>();
  readonly f = signal<Fiche360 | null>(null);
  readonly erreur = signal('');
  readonly onglet = signal<Onglet>('synthese');
  readonly onglets: { code: Onglet; libelle: string }[] = [
    { code: 'synthese', libelle: 'Synthèse' }, { code: 'profilage', libelle: 'Profilage' }, { code: 'filtrage', libelle: 'Filtrage' },
    { code: 'alertes', libelle: 'Alertes' }, { code: 'comptes', libelle: 'Comptes' }, { code: 'historique', libelle: 'Historique' },
  ];
  readonly libProfil = LIB_PROFIL;
  readonly libNiveau = LIB_NIVEAU;
  readonly libChamp = LIB_MOTIF_CHAMP;
  readonly modes = MODES_DECISION;
  readonly dateFr = dateFr;
  readonly dh = dateHeureFr;
  readonly n = n;

  ngOnInit(): void {
    queueMicrotask(() => (this.el.nativeElement.querySelector('[role=dialog]') as HTMLElement | null)?.focus());
    this.api.get<Fiche360>(`${CL_BASE}/vue360/clients/${this.racine()}`).subscribe({
      next: (d) => this.f.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) =>
        this.erreur.set(`Fiche indisponible : ${i.message}${i.requestId ? ` (réf. ${i.requestId})` : ''}`)),
    });
  }

  alertesOuvertes(): number {
    return (this.f()?.alertes ?? []).filter((a) => ['NOUVELLE', 'A_ANALYSER', 'EN_INVESTIGATION'].includes(a.statut)).length;
  }

  codes(v: string | null): string {
    const c = (v ?? '').split(',').map((s) => s.trim()).filter(Boolean);
    return c.length ? c.join(' · ') : 'Vide';
  }
}
