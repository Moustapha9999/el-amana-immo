import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { dateFr, dateHeureFr, n } from '../clientele.models';
import {
  EtatChargement, Filtres360, GROUPES_ALERTE, LIB_NIVEAU, LIB_PROFIL, NIVEAUX_360, Synthese360, Vue360, pct, variation,
} from './vue360.models';

/** ``fusion`` : ajoute aux filtres courants au lieu de remplacer les filtres d’exploration. */
export interface Ouvrir360 { vue: Vue360; filtres: Filtres360; fusion?: boolean; }

const AGES = [
  { code: '0_7', libelle: '0 – 7 jours', min: 0 }, { code: '8_30', libelle: '8 – 30 jours', min: 8 },
  { code: '31_90', libelle: '31 – 90 jours', min: 31 }, { code: '90_PLUS', libelle: 'Plus de 90 jours', min: 91 },
];

@Component({
  selector: 'bea-cl360-synthese',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule],
  template: `
    @if (etat() === 'erreur') {
      <section class="bea-mg__panel"><div class="bea-cl360-state" data-s="erreur">
        <mat-icon>cloud_off</mat-icon><span>{{ erreur() }}</span>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="recharger.emit()"><mat-icon>refresh</mat-icon> Réessayer</button>
      </div></section>
    } @else {
      @let s = data();
      <p class="bea-cl-hint" style="margin:0 0 0.6rem">
        @if (s) {
          Stock au {{ dateFr(s.reference.stock_au) }} · activité du {{ dateFr(s.reference.periode.du) }} au {{ dateFr(s.reference.periode.au) }} ({{ s.reference.fuseau }}) · généré le {{ dh(s.reference.genere_le) }}. {{ s.reference.note }}
        } @else { Chargement des indicateurs… }
      </p>

      <div class="bea-cl-pilot">
        <button type="button" class="bea-cl-kpi" (click)="ouvrir('profilage', {})">
          <mat-icon class="bea-cl-kpi__ico">groups</mat-icon>
          <span>Clients distincts</span>
          <strong>{{ v(s?.clients?.total) }}</strong>
          <small>PP {{ v(s?.clients?.pp) }} · PM {{ v(s?.clients?.pm) }} · non identifiés {{ v(s?.clients?.non_identifies) }}</small>
          <em>Unité : racine ORION (un client multi-comptes compte une fois)</em>
        </button>
        @if (s && !s.profilage) {
          <div class="bea-cl-kpi"><mat-icon class="bea-cl-kpi__ico">lock</mat-icon><span>Profilages exploitables</span><strong>Non autorisé</strong><small>Permission clientele.classif.view requise.</small></div>
        } @else {
          <button type="button" class="bea-cl-kpi" (click)="ouvrir('profilage', { profilage: 'EXPLOITABLE' })">
            <mat-icon class="bea-cl-kpi__ico">fact_check</mat-icon>
            <span>Profilages exploitables</span>
            <strong>{{ v(s?.profilage?.exploitables) }}</strong>
            <small>Couverture {{ pct(s?.profilage?.exploitables, s?.clients?.total) }} · {{ v(s?.profilage?.non_profiles) }} non profilés</small>
            <em>Classification enregistrée (clientele_classifications)</em>
          </button>
        }
        <button type="button" class="bea-cl-kpi" [attr.data-tone]="s?.filtrage?.alertes?.['A_EXAMINER'] ? 'warn' : null" (click)="ouvrir('filtrage', { groupe: 'A_EXAMINER' })">
          <mat-icon class="bea-cl-kpi__ico">policy</mat-icon>
          <span>Correspondances à examiner</span>
          <strong>{{ v(s?.filtrage?.alertes?.['A_EXAMINER']) }}</strong>
          <small>{{ v(s?.filtrage?.clients_a_examiner) }} clients concernés</small>
          <em>Unité : alerte (NOUVELLE + A_ANALYSER), potentielle ≠ confirmée</em>
        </button>
        <button type="button" class="bea-cl-kpi" [attr.data-tone]="s?.alertes?.ouvertes ? 'warn' : null" (click)="ouvrir('alertes', { groupe: 'OUVERTES' })">
          <mat-icon class="bea-cl-kpi__ico">notification_important</mat-icon>
          <span>Alertes ouvertes</span>
          <strong>{{ v(s?.alertes?.ouvertes) }}</strong>
          <small>{{ v(s?.alertes?.ouvertes_non_attribuees) }} non attribuées · {{ v(s?.alertes?.en_attente_decision) }} en attente de décision</small>
          <em>Plus ancienne : {{ dh(s?.alertes?.plus_ancienne_ouverte) }}</em>
        </button>
      </div>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Indicateurs détaillés</h2></div>
        <div class="bea-cl-stats">
          <button type="button" class="bea-cl-stat" (click)="ouvrir('profilage', { profil: 'PP' })"><span>Personnes physiques</span><strong>{{ v(s?.clients?.pp) }}</strong><small>clients</small></button>
          <button type="button" class="bea-cl-stat" (click)="ouvrir('profilage', { profil: 'PM' })"><span>Personnes morales</span><strong>{{ v(s?.clients?.pm) }}</strong><small>clients</small></button>
          <button type="button" class="bea-cl-stat" (click)="ouvrir('profilage', { profil: 'NON_IDENTIFIE' })"><span>Profil non identifié</span><strong>{{ v(s?.clients?.non_identifies) }}</strong><small>clients</small></button>
          @if (!s || s.profilage) {
            <button type="button" class="bea-cl-stat" [attr.data-tone]="s?.risque?.['NON_EVALUE'] ? 'warn' : null" (click)="ouvrir('profilage', { niveau: 'NON_EVALUE' })"><span>Risque non évalué</span><strong>{{ v(s?.risque?.['NON_EVALUE']) }}</strong><small>clients · jamais comptés en Faible</small></button>
            <button type="button" class="bea-cl-stat" [attr.data-tone]="s?.profilage?.a_verifier ? 'warn' : null" (click)="ouvrir('profilage', { coherence: 'A_VERIFIER' })"><span>Résultat à vérifier</span><strong>{{ v(s?.profilage?.a_verifier) }}</strong><small>clients · diagnostic de cohérence</small></button>
            <button type="button" class="bea-cl-stat" (click)="ouvrir('profilage', { anomalie: 'REEXAMEN_OUVERT' })"><span>Réexamens ouverts</span><strong>{{ v(s?.reexamens_ouverts) }}</strong><small>signaux SCORE</small></button>
          }
          <button type="button" class="bea-cl-stat" [attr.data-tone]="s?.profilage?.incomplets ? 'warn' : null" (click)="ouvrir('profilage', { completude: 'INCOMPLET' })"><span>Données incomplètes</span><strong>{{ v(s?.profilage?.incomplets) }}</strong><small>clients · identifiant, nationalité ou profil manquant</small></button>
          <button type="button" class="bea-cl-stat" (click)="ouvrir('filtrage', { filtrage: 'AVEC' })"><span>Clients avec correspondance</span><strong>{{ v(s?.filtrage?.clients_avec_correspondance) }}</strong><small>clients · toutes décisions</small></button>
          <button type="button" class="bea-cl-stat" (click)="ouvrir('alertes', { groupe: 'EN_ANALYSE' })"><span>Dossiers en attente de décision</span><strong>{{ v(s?.alertes?.en_attente_decision) }}</strong><small>alertes EN_INVESTIGATION</small></button>
          <div class="bea-cl-stat is-lock" [title]="s?.alertes?.priorite?.message ?? ''"><span>Alertes prioritaires</span><strong>Non défini</strong><small>Aucune priorité enregistrée</small></div>
          <div class="bea-cl-stat is-lock" [title]="s?.alertes?.delais?.message ?? ''"><span>Alertes en retard</span><strong>Non défini</strong><small>Aucun délai métier paramétré</small></div>
        </div>
      </section>

      <div class="bea-cl-grid">
        @if (!s || s.risque) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Niveaux de risque enregistrés</h2></div>
            <p class="bea-cl-hint" style="padding:0 1.1rem">Classes retenues telles qu’enregistrées, sans recalcul. Cliquer pour ouvrir la liste.</p>
            @if (totalRisque()) {
              <div class="bea-cl-stack" role="img" [attr.aria-label]="'Répartition de ' + n(totalRisque()) + ' clients par niveau de risque'">
                @for (x of niveaux; track x.code) {
                  @if (s?.risque?.[x.code]) { <i [attr.data-n]="x.code" [style.flex-grow]="s!.risque![x.code]" [title]="x.libelle + ' : ' + n(s!.risque![x.code])"></i> }
                }
              </div>
            }
            <div class="bea-cl360-legend">
              @for (x of niveaux; track x.code) {
                <button type="button" [attr.data-n]="x.code" (click)="ouvrir('profilage', { niveau: x.code })">
                  {{ x.libelle }} <b>{{ v(s?.risque?.[x.code]) }}</b> <small class="bea-cl-hint">{{ pct(s?.risque?.[x.code], totalRisque()) }}</small>
                </button>
              }
            </div>
            @if (s?.risque_par_profil?.length) {
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead><tr><th>Profil</th>@for (x of niveaux; track x.code) { <th>{{ x.libelle }}</th> }</tr></thead>
                  <tbody>
                    @for (p of profils; track p) {
                      <tr>
                        <td>{{ libProfil[p] }}</td>
                        @for (x of niveaux; track x.code) {
                          <td>
                            @if (cellule(p, x.code); as c) {
                              <button type="button" class="bea-cl360-cell" (click)="ouvrir('profilage', { profil: p, niveau: x.code })">{{ n(c) }}</button>
                            } @else { 0 }
                          </td>
                        }
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </section>
        }
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Alertes par statut et ancienneté</h2></div>
          <ul class="bea-cl-bars">
            @for (g of groupes; track g.code; let i = $index) {
              <li [style.--d]="i">
                <span><button type="button" class="bea-cl360-cell" (click)="ouvrir('alertes', { groupe: g.code })">{{ g.libelle }}</button> <small class="bea-cl-hint">{{ g.statuts }}</small></span>
                <b>{{ v(s?.alertes?.par_groupe?.[g.code]) }}</b>
                <i><em [style.width.%]="part(s?.alertes?.par_groupe?.[g.code], s?.alertes?.total)"></em></i>
              </li>
            }
          </ul>
          <p class="bea-cl-hint" style="padding:0 1.1rem">Ancienneté des alertes ouvertes (depuis la création) :</p>
          <div class="bea-cl360-legend">
            @for (a of ages; track a.code) {
              <button type="button" (click)="ouvrir('alertes', { groupe: 'OUVERTES', anciennete_min: a.min ? '' + a.min : '' })">{{ a.libelle }} <b>{{ v(s?.alertes?.anciennete_ouvertes?.[a.code]) }}</b></button>
            }
          </div>
          <p class="bea-cl-hint" style="padding:0 1.1rem 0.9rem">
            Sources : ORION (champ Liste d’interdiction) {{ v(s?.alertes?.par_source?.['ORION']) }} · listes internes {{ v(s?.alertes?.par_source?.['LISTE']) }}.
            {{ s?.alertes?.delais?.message }}
          </p>
        </section>
      </div>

      <div class="bea-cl-grid">
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Anomalies et contrôles</h2><span class="bea-mg__count">diagnostics</span></div>
          <p class="bea-cl-hint" style="padding:0 1.1rem">Calculés à part, en lecture seule. Ils signalent un résultat à vérifier ; ils ne corrigent rien et ne sont pas des motifs du moteur.</p>
          <ul class="bea-cl360-anoms">
            @for (a of s?.anomalies ?? []; track a.code) {
              <li><button type="button" [attr.data-zero]="!a.clients" [title]="a.definition" (click)="ouvrir('profilage', { anomalie: a.code })">
                <span>{{ a.libelle }}</span><b>{{ n(a.clients) }}</b><small>{{ a.definition }}</small>
              </button></li>
            } @empty { <li class="bea-cl-empty">{{ s ? 'Aucun contrôle disponible.' : 'Chargement…' }}</li> }
          </ul>
        </section>
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Activité de la période</h2></div>
          <div class="bea-cl-stats">
            <button type="button" class="bea-cl-stat" (click)="ouvrir('alertes', { periode_alertes: '1' })"><span>Alertes créées</span><strong>{{ v(s?.activite?.alertes_creees?.valeur) }}</strong><small>{{ variation(s?.activite?.alertes_creees) }}</small></button>
            <div class="bea-cl-stat"><span>Décisions sur alertes</span><strong>{{ v(s?.activite?.decisions_alertes?.valeur) }}</strong><small>{{ variation(s?.activite?.decisions_alertes) }}</small></div>
            @if (s?.activite?.classifications_enregistrees; as c) {
              <button type="button" class="bea-cl-stat" (click)="ouvrir('profilage', { classe_periode: '1' })"><span>Classifications enregistrées</span><strong>{{ n(c.valeur) }}</strong><small>{{ variation(c) }}</small></button>
              <div class="bea-cl-stat"><span>Premières classifications</span><strong>{{ n(s?.activite?.premieres_classifications?.valeur) }}</strong><small>{{ variation(s?.activite?.premieres_classifications) }}</small></div>
              <div class="bea-cl-stat" [attr.data-tone]="s?.activite?.changements_de_classe?.valeur ? 'warn' : null"><span>Changements de classe</span><strong>{{ n(s?.activite?.changements_de_classe?.valeur) }}</strong><small>{{ variation(s?.activite?.changements_de_classe) }}</small></div>
            }
          </div>
          <p class="bea-cl-hint" style="padding:0 1.1rem 0.9rem">{{ s?.activite?.note }}</p>
        </section>
      </div>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Historique de la période</h2><span class="bea-mg__count">pas : {{ libPas[s?.historique?.pas ?? 'day'] }}</span></div>
        <p class="bea-cl-hint" style="padding:0 1.1rem">Bleu : classifications enregistrées (dont changements de classe en infobulle). Orange : alertes créées. Cliquer une colonne ouvre les dossiers de cette date.</p>
        @if (s?.historique?.classifications; as cl) {
          <div class="bea-cl-cols" style="height:11rem">
            @for (c of colonnesClassif(); track c.jour; let i = $index) {
              <button type="button" class="bea-cl-col" [style.--d]="i" [title]="dateFr(c.jour) + ' : ' + n(c.ecrits) + ' écrites, ' + n(c.premieres) + ' premières, ' + n(c.changements) + ' changements'" (click)="ouvrirJour(c.jour, 'profilage')">
                <b>{{ n(c.ecrits) }}</b><i [style.height.%]="part(c.ecrits, maxClassif())"></i><span>{{ dateFr(c.jour).slice(0, 5) }}</span>
              </button>
            } @empty { <div class="bea-cl-empty" style="grid-column:1/-1">Aucune classification enregistrée sur la période.</div> }
          </div>
        }
        <div class="bea-cl-cols" style="height:9rem">
          @for (a of s?.historique?.alertes ?? []; track a.jour; let i = $index) {
            <button type="button" class="bea-cl-col" [style.--d]="i" [title]="dateFr(a.jour) + ' : ' + n(a.creees) + ' alertes créées, ' + n(a.decisions) + ' décisions'" (click)="ouvrirJour(a.jour, 'alertes')">
              <b>{{ n(a.creees) }}</b><i class="is-alt" [style.height.%]="part(a.creees, maxAlertes())"></i><span>{{ dateFr(a.jour).slice(0, 5) }}</span>
            </button>
          } @empty { <div class="bea-cl-empty" style="grid-column:1/-1">{{ s ? 'Aucune alerte créée sur la période.' : 'Chargement…' }}</div> }
        </div>
      </section>
    }
  `,
})
export class Cl360SyntheseComponent {
  readonly data = input<Synthese360 | null>(null);
  readonly etat = input<EtatChargement>('chargement');
  readonly erreur = input('');
  readonly navigation = output<Ouvrir360>();
  readonly recharger = output<void>();
  readonly n = n;
  readonly dateFr = dateFr;
  readonly dh = dateHeureFr;
  readonly pct = pct;
  readonly variation = variation;
  readonly niveaux = NIVEAUX_360;
  readonly groupes = GROUPES_ALERTE;
  readonly ages = AGES;
  readonly profils = ['PP', 'PM', 'NON_IDENTIFIE'];
  readonly libProfil = LIB_PROFIL;
  readonly libNiveau = LIB_NIVEAU;
  readonly libPas: Record<string, string> = { day: 'jour', week: 'semaine', month: 'mois' };
  readonly totalRisque = computed(() => Object.values(this.data()?.risque ?? {}).reduce((a, b) => a + b, 0));
  readonly colonnesClassif = computed(() => {
    const parJour = new Map<string, { jour: string; ecrits: number; premieres: number; changements: number }>();
    for (const c of this.data()?.historique?.classifications ?? []) {
      const x = parJour.get(c.jour) ?? { jour: c.jour, ecrits: 0, premieres: 0, changements: 0 };
      x.ecrits += c.ecrits; x.premieres += c.premieres; x.changements += c.changements;
      parJour.set(c.jour, x);
    }
    return [...parJour.values()];
  });
  readonly maxClassif = computed(() => Math.max(0, ...this.colonnesClassif().map((c) => c.ecrits)));
  readonly maxAlertes = computed(() => Math.max(0, ...(this.data()?.historique?.alertes ?? []).map((a) => a.creees)));

  v(x: number | null | undefined): string {
    if (this.etat() !== 'ok' || x === null || x === undefined) return '—';
    return n(x);
  }

  part(x: number | null | undefined, max: number | null | undefined): number {
    return max ? Math.max(2, Math.round(((x ?? 0) / max) * 100)) : 0;
  }

  cellule(profil: string, niveau: string): number {
    return this.data()?.risque_par_profil?.find((r) => r.profil === profil && r.niveau === niveau)?.clients ?? 0;
  }

  ouvrir(vue: Vue360, filtres: Filtres360): void {
    this.navigation.emit({ vue, filtres });
  }

  ouvrirJour(jour: string, vue: Vue360): void {
    const filtres: Filtres360 = { periode: 'perso', du: jour, au: this.finBucket(jour) };
    if (vue === 'profilage') filtres.classe_periode = '1';
    else filtres.periode_alertes = '1';
    this.navigation.emit({ vue, filtres });
  }

  private finBucket(jour: string): string {
    const pas = this.data()?.historique?.pas;
    if (pas === 'day') return jour;
    const d = new Date(`${jour}T00:00:00Z`);
    if (pas === 'week') d.setUTCDate(d.getUTCDate() + 6);
    else { d.setUTCMonth(d.getUTCMonth() + 1); d.setUTCDate(0); }
    return d.toISOString().slice(0, 10);
  }
}
