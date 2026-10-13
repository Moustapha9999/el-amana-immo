import { ChangeDetectionStrategy, Component, ViewEncapsulation, computed, effect, inject, signal, untracked } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';
import { Cl360AlertesComponent } from '../vue360/cl360-alertes.component';
import { Cl360ClientsComponent } from '../vue360/cl360-clients.component';
import { Cl360JournalComponent } from '../vue360/cl360-journal.component';
import { Cl360ListesComponent } from '../vue360/cl360-listes.component';
import { Cl360SyntheseComponent, Ouvrir360 } from '../vue360/cl360-synthese.component';
import {
  CLES_FILTRES, EtatChargement, FILTRAGES, Filtres360, GROUPES_ALERTE, LIB_NIVEAU, LIB_PROFIL, NIVEAUX_360, PERIODES, PROFILAGES,
  Synthese360, VUES_360, Vue360, bornesPeriode, filtresPopulation, nettoyer,
} from '../vue360/vue360.models';

const GLOBAUX: (keyof Filtres360)[] = ['periode', 'du', 'au', 'profil', 'agence', 'niveau'];
const AVEC_SYNTHESE: Vue360[] = ['synthese', 'filtrage', 'listes'];

@Component({
  selector: 'bea-cl-filtrage',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrls: ['../vue360/vue360.css'],
  encapsulation: ViewEncapsulation.None,
  imports: [
    FormsModule, MatIconModule, ClienteleUiComponent,
    Cl360SyntheseComponent, Cl360ClientsComponent, Cl360AlertesComponent, Cl360ListesComponent, Cl360JournalComponent,
  ],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Risque · supervision</p>
          <h1>Filtrage &amp; alertes — vue 360° clientèle</h1>
          <p class="bea-cl-head__sub">Une vue synthétique pour décider, des indicateurs cliquables pour enquêter, des dossiers détaillés pour agir. Les résultats de classification sont affichés tels qu’enregistrés : aucun recalcul.</p>
        </div>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
          @if (store.cap().exporter) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter()" [disabled]="busy()"><mat-icon>download</mat-icon> Export Excel</button>
          }
          @if (store.cap().filtrage_executer) {
            <button type="button" class="bea-mg__btn" (click)="scanner()" [disabled]="busy()"><mat-icon>search</mat-icon> Lancer le filtrage</button>
          }
        </div>
      </header>

      <nav class="bea-cl-tabs" aria-label="Sections de la vue 360°">
        @for (v of vues; track v.code) {
          <button type="button" [class.is-on]="vue() === v.code" [attr.aria-current]="vue() === v.code ? 'page' : null" (click)="naviguer({ vue: v.code, filtres: {}, fusion: false })">
            <mat-icon>{{ v.icone }}</mat-icon>{{ v.libelle }}
          </button>
        }
      </nav>

      <section class="bea-mg__panel">
        <div class="bea-cl-filters">
          <label>Période
            <select [ngModel]="filtres().periode ?? '30j'" (ngModelChange)="changerPeriode($event)">
              @for (p of periodes; track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
            </select>
          </label>
          @if (filtres().periode === 'perso') {
            <label>Du<input type="date" [ngModel]="filtres().du" (ngModelChange)="appliquer({ du: $event })" /></label>
            <label>Au<input type="date" [ngModel]="filtres().au" (ngModelChange)="appliquer({ au: $event })" /></label>
          }
          <label>Type de client
            <select [ngModel]="filtres().profil ?? ''" (ngModelChange)="appliquer({ profil: $event })">
              <option value="">PP et PM</option><option value="PP">Personnes physiques</option><option value="PM">Personnes morales</option><option value="NON_IDENTIFIE">Non identifiés</option>
            </select>
          </label>
          @if (store.cap().classif_voir) {
            <label>Niveau de risque
              <select [ngModel]="filtres().niveau ?? ''" (ngModelChange)="appliquer({ niveau: $event })">
                <option value="">Tous</option>
                @for (x of niveaux; track x.code) { <option [value]="x.code">{{ x.libelle }}</option> }
              </select>
            </label>
          }
          <label>Agence
            <select [ngModel]="filtres().agence ?? ''" (ngModelChange)="appliquer({ agence: $event })">
              <option value="">Toutes</option>
              @for (a of store.agences(); track a.code) { <option [value]="a.code">{{ a.code }} · {{ a.libelle }}</option> }
            </select>
          </label>
        </div>
        @if (puces().length) {
          <div class="bea-cl360-chips" aria-label="Filtres actifs">
            @for (p of puces(); track p.cle) {
              <button type="button" (click)="retirer(p.cle)" [attr.aria-label]="'Retirer le filtre ' + p.libelle">{{ p.libelle }}<mat-icon>close</mat-icon></button>
            }
            <button type="button" (click)="toutEffacer()" style="background:#f1f5f9;color:#475569">Tout effacer</button>
          </div>
        }
        <p class="bea-cl-hint" style="padding:0 1rem 0.85rem">Période {{ libPeriode() }} · fuseau Africa/Nouakchott (UTC+0). Le stock (clients, niveaux, alertes ouvertes) est à date ; la période s’applique aux flux (créations, décisions, classements).</p>
      </section>

      @switch (vue()) {
        @case ('synthese') {
          <bea-cl360-synthese [data]="synthese()" [etat]="etatSynthese()" [erreur]="erreurSynthese()" (navigation)="naviguer($event)" (recharger)="chargerSynthese(true)" />
        }
        @case ('profilage') { <bea-cl360-clients [filtres]="filtres()" mode="profilage" (navigation)="naviguer($event)" /> }
        @case ('recherche') { <bea-cl360-clients [filtres]="filtres()" mode="recherche" (navigation)="naviguer($event)" /> }
        @case ('filtrage') { <bea-cl360-alertes [filtres]="filtres()" [synthese]="synthese()" mode="filtrage" (navigation)="naviguer($event)" /> }
        @case ('alertes') { <bea-cl360-alertes [filtres]="filtres()" mode="alertes" (navigation)="naviguer($event)" /> }
        @case ('listes') { <bea-cl360-listes [synthese]="synthese()" /> }
        @case ('journal') { <bea-cl360-journal [filtres]="filtres()" /> }
      }
    </div>
  `,
})
export class ClFiltrageComponent {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  private readonly qp = toSignal(this.route.queryParamMap, { requireSync: true });
  private readonly rev = signal(0);
  private derniereCle = '';

  readonly vues = VUES_360;
  readonly periodes = PERIODES;
  readonly niveaux = NIVEAUX_360;
  readonly busy = signal(false);
  readonly synthese = signal<Synthese360 | null>(null);
  readonly etatSynthese = signal<EtatChargement>('chargement');
  readonly erreurSynthese = signal('');

  readonly vue = computed<Vue360>(() => {
    const v = this.qp().get('vue') as Vue360 | null;
    return v && VUES_360.some((x) => x.code === v) ? v : 'synthese';
  });

  readonly filtres = computed<Filtres360>(() => {
    this.rev();
    const m = this.qp();
    const f: Filtres360 = {};
    for (const k of CLES_FILTRES) {
      const v = m.get(k);
      if (v) f[k] = v;
    }
    return f;
  });

  readonly libPeriode = computed(() => {
    const f = this.filtres();
    const b = bornesPeriode(f);
    const lib = PERIODES.find((p) => p.code === (f.periode ?? '30j'))?.libelle ?? '';
    return b ? `${lib} (${this.jour(b.du)} → ${this.jour(b.au)})` : `${lib} : dates à saisir`;
  });

  readonly puces = computed(() => {
    const f = this.filtres();
    const lib: Partial<Record<keyof Filtres360, (v: string) => string>> = {
      profilage: (v) => PROFILAGES.find((x) => x.code === v)?.libelle ?? v,
      filtrage: (v) => `Filtrage : ${FILTRAGES.find((x) => x.code === v)?.libelle ?? v}`,
      anomalie: (v) => `Contrôle : ${this.synthese()?.anomalies.find((a) => a.code === v)?.libelle ?? v}`,
      coherence: (v) => (v === 'OK' ? 'Cohérence OK' : 'À vérifier'),
      completude: (v) => (v === 'COMPLET' ? 'Complet' : 'Incomplet'),
      q: (v) => `Recherche « ${v} »`,
      classe_periode: () => 'Classés pendant la période',
      groupe: (v) => (v === 'OUVERTES' ? 'Alertes ouvertes' : GROUPES_ALERTE.find((g) => g.code === v)?.libelle ?? v),
      source: (v) => `Source ${v === 'ORION' ? 'ORION' : 'liste interne'}`,
      assignee: (v) => (v === 'aucun' ? 'Non attribuées' : v === 'moi' ? 'Mes alertes' : 'Agent sélectionné'),
      anciennete_min: (v) => `Ouvertes depuis plus de ${Number(v) - 1} j`,
      tri: (v) => `Tri : ${v}`,
      periode_alertes: () => 'Alertes créées pendant la période',
      profil: (v) => LIB_PROFIL[v] ?? v,
      niveau: (v) => `Niveau ${LIB_NIVEAU[v] ?? v}`,
      agence: (v) => `Agence ${v}`,
    };
    return (Object.keys(lib) as (keyof Filtres360)[])
      .filter((k) => f[k])
      .map((k) => ({ cle: k, libelle: lib[k]!(f[k]!) }));
  });

  constructor() {
    this.store.charger();
    effect(() => {
      const vue = this.vue();
      this.filtres();
      if (AVEC_SYNTHESE.includes(vue)) untracked(() => this.chargerSynthese());
    });
  }

  private paramsPopulation(): Record<string, string> {
    const f = this.filtres();
    const p: Record<string, string> = { ...filtresPopulation(f) };
    for (const k of ['periode', 'du', 'au'] as const) if (f[k]) p[k] = f[k]!;
    if (f.classe_periode) p['classe_periode'] = 'true';
    return p;
  }

  chargerSynthese(force = false): void {
    const params = this.paramsPopulation();
    const cle = `${this.rev()}|${JSON.stringify(params)}`;
    if (!force && cle === this.derniereCle && this.etatSynthese() !== 'erreur') return;
    this.derniereCle = cle;
    this.etatSynthese.set('chargement');
    this.api.get<Synthese360>(`${CL_BASE}/vue360/synthese`, params).subscribe({
      next: (d) => {
        if (cle !== this.derniereCle) return;
        this.synthese.set(d);
        this.etatSynthese.set('ok');
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => {
        if (cle !== this.derniereCle) return;
        this.synthese.set(null);
        this.erreurSynthese.set(`Indicateurs indisponibles : ${i.message}${i.requestId ? ` (réf. ${i.requestId})` : ''}`);
        this.etatSynthese.set('erreur');
      }),
    });
  }

  naviguer(o: Ouvrir360): void {
    const courant = this.filtres();
    let f: Filtres360;
    if (o.fusion) {
      f = { ...courant, ...o.filtres };
    } else {
      f = {};
      for (const k of GLOBAUX) if (courant[k]) f[k] = courant[k];
      Object.assign(f, o.filtres);
    }
    void this.router.navigate([], { relativeTo: this.route, queryParams: { vue: o.vue, ...nettoyer(f) } });
  }

  appliquer(patch: Filtres360): void {
    this.naviguer({ vue: this.vue(), filtres: patch, fusion: true });
  }

  changerPeriode(code: string): void {
    if (code !== 'perso') {
      this.appliquer({ periode: code, du: '', au: '' });
      return;
    }
    const b = bornesPeriode({ periode: '30j' })!;
    this.appliquer({ periode: 'perso', du: this.filtres().du || b.du, au: this.filtres().au || b.au });
  }

  retirer(cle: keyof Filtres360): void {
    this.appliquer({ [cle]: '' });
  }

  toutEffacer(): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: { vue: this.vue() } });
  }

  exporter(): void {
    this.busy.set(true);
    this.api.download(`${CL_BASE}/vue360/export.xlsx`, this.paramsPopulation()).subscribe({
      next: (b) => {
        this.busy.set(false);
        telecharger(b, `vue360-clientele-${new Date().toISOString().slice(0, 10)}.xlsx`);
      },
      error: (e) => {
        this.busy.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Export indisponible'));
      },
    });
  }

  scanner(): void {
    this.feedback.run(() => this.api.post<{ alertes_crees: number }>(`${CL_BASE}/filtrage/scan`, {}), {
      confirm: {
        action: 'validation', title: 'Lancer le filtrage',
        message: 'Rapprocher le référentiel clients des listes internes et du champ ORION « Liste d’interdiction » ?',
        hint: 'Seules des correspondances potentielles sont créées ; aucune classification n’est modifiée.',
      },
      busy: this.busy,
      success: (r) => ({ title: 'Filtrage terminé', message: `${r.alertes_crees} nouvelle(s) correspondance(s) potentielle(s) à examiner` }),
      errorTitle: 'Filtrage impossible',
    }).subscribe(() => this.rev.update((x) => x + 1));
  }

  private jour(iso: string): string {
    const [a, m, j] = iso.split('-');
    return `${j}/${m}/${a}`;
  }
}
