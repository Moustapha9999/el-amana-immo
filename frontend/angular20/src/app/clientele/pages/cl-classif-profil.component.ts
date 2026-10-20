import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { PaginationComponent } from '../../shared/pagination.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClExportComponent } from '../cl-export.component';
import { ClienteleUiComponent } from '../clientele-ui.component';
import {
  BlocProgression, CL_BASE, LigneSuivi, PageSuivi, ProgressionClassification, STATUTS_CLASSIFICATION, dateFr, n, pourcentageFr,
} from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

type Profil = 'PP' | 'PM';
const CHAMPS = ['q', 'racine', 'nom', 'classe', 'statut', 'analyste', 'source', 'agence', 'du', 'au'] as const;
type Champ = (typeof CHAMPS)[number];

@Component({
  selector: 'bea-cl-classif-profil',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, PaginationComponent, ClienteleUiComponent, ClExportComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl bea-cl--large">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Classification</p>
          <h1>Classification des {{ pm ? 'personnes morales' : 'personnes physiques' }}</h1>
          <p class="bea-cl-head__sub">Uniquement les clients {{ profil }}. Une décision manuelle n’est jamais remplacée par le moteur ni par un import.</p>
        </div>
        <div class="bea-cl-actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/classification-suivi"><mat-icon>insights</mat-icon> Tableau de bord</a>
          <bea-cl-export [chemin]="base + '/suivi/export'" [apercu]="base + '/suivi/export/apercu'" [params]="paramsExport()"
            [filtresActifs]="filtresActifs()" [libelle]="'Classification ' + profil" [nomFichier]="'classification-' + profil.toLowerCase()"
            [perimetre]="'Tous les clients ' + profil + ' — ' + (perimetre === 'OUVERTS' ? 'clients ouverts' : 'tous les clients')" />
        </div>
      </header>

      @if (bloc(); as b) {
        <section class="bea-cl-prog__card bea-cl-prog__card--inline" aria-label="Avancement">
          <div class="bea-cl-prog__top">
            <div><h2>Avancement {{ profil }}</h2><p>{{ prog()?.perimetre_libelle }}</p></div>
            <span class="bea-cl-prog__pct" [class.is-na]="b.pourcentage === null">{{ pct(b.pourcentage) }}</span>
          </div>
          <div class="bea-cl-progress" role="progressbar" [attr.aria-valuenow]="b.pourcentage ?? 0" aria-valuemin="0" aria-valuemax="100" aria-label="Part classée">
            <span [style.width.%]="b.pourcentage ?? 0"></span>
          </div>
          <div class="bea-cl-prog__nums">
            <button type="button" (click)="filtrerStatut('')"><strong>{{ n(b.total) }}</strong><span>Clients {{ profil }}</span></button>
            <button type="button" class="is-ok" (click)="filtrerStatut('CLASSE')"><strong>{{ n(b.classes) }}</strong><span>Classés</span></button>
            <button type="button" class="is-warn" (click)="filtrerStatut('NON_CLASSE')"><strong>{{ n(b.non_classes) }}</strong><span>Non classés</span></button>
            <button type="button" (click)="filtrerStatut('A_VALIDER')"><strong>{{ n(b.a_valider) }}</strong><span>Propositions à valider</span></button>
            <button type="button" (click)="filtrerStatut('ECART')"><strong>{{ n(b.ecarts_moteur) }}</strong><span>Écarts moteur</span></button>
          </div>
        </section>
      }

      <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); appliquer()">
        <label>Recherche<input [(ngModel)]="f.q" name="q" [placeholder]="pm ? 'Racine, raison sociale, NIF…' : 'Racine, nom, NNI…'" /></label>
        <label>Racine<input [(ngModel)]="f.racine" name="racine" maxlength="6" /></label>
        <label>{{ pm ? 'Raison sociale' : 'Nom / prénom' }}<input [(ngModel)]="f.nom" name="nom" maxlength="120" /></label>
        <label>Classe
          <select [(ngModel)]="f.classe" name="classe">
            <option value="">Toutes</option>
            <option value="FAIBLE">Faible</option><option value="MOYEN">Moyen</option>
            <option value="ELEVE">Élevé</option><option value="INTERDIT">Interdit</option>
          </select>
        </label>
        <label>Statut
          <select [(ngModel)]="f.statut" name="statut">
            <option value="">Tous</option>
            <option value="CLASSE">Classé</option>
            <option value="NON_CLASSE">Non classé</option>
            <option value="A_VALIDER">Proposition à valider</option>
            <option value="NON_CLASSABLE">Moteur sans résultat</option>
            <option value="NON_CALCULE">Non calculé</option>
            <option value="ECART">Écart moteur / retenue</option>
          </select>
        </label>
        <label>Analyste KYC
          <select [(ngModel)]="f.analyste" name="analyste">
            <option value="">Tous</option>
            @for (a of analystes(); track a) { <option [value]="a">{{ a }}</option> }
          </select>
        </label>
        <label>Source
          <select [(ngModel)]="f.source" name="source">
            <option value="">Toutes</option>
            <option value="MANUELLES">Décision manuelle</option>
            <option value="FICHIER">Fichier / lot</option>
            <option value="MOTEUR">Moteur</option>
          </select>
        </label>
        <label>Agence
          <select [(ngModel)]="f.agence" name="agence">
            <option value="">Toutes</option>
            @for (a of store.agences(); track a.code) { <option [value]="a.code">{{ a.code }} — {{ a.libelle }}</option> }
          </select>
        </label>
        <label>Classé du<input type="date" [(ngModel)]="f.du" name="du" /></label>
        <label>au<input type="date" [(ngModel)]="f.au" name="au" /></label>
        <label>Périmètre
          <select [(ngModel)]="perimetre" name="perimetre">
            <option value="TOUS">Tous les clients</option>
            <option value="OUVERTS">Clients ouverts</option>
          </select>
        </label>
        <div class="bea-cl-actions" style="align-items:end">
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary"><mat-icon>search</mat-icon> Filtrer</button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
        </div>
      </form>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>Clients {{ profil }}</h2>
          <span class="bea-cl-actions">
            <span class="bea-mg__count">{{ n(data()?.total) }} client(s)</span>
            @if (store.cap().classif_executer) {
              <label class="bea-mg__btn bea-mg__btn--ghost" [class.is-disabled]="busy()">
                <mat-icon>upload_file</mat-icon> Importer une liste {{ profil }}
                <input type="file" accept=".xlsx,.xlsm" hidden (change)="importer($event)" [disabled]="busy()" />
              </label>
            }
          </span>
        </div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr>
              @if (store.cap().classif_executer) {
                <th class="c-xs"><input type="checkbox" [checked]="toutCoche()" (change)="cocherPage($any($event.target).checked)" aria-label="Sélectionner la page" /></th>
              }
              <th class="c-sm">Racine</th>
              <th class="c-md">{{ pm ? 'NIF' : 'NNI' }}</th>
              @if (pm) { <th class="c-xl">Raison sociale</th> } @else { <th class="c-lg">Nom</th><th class="c-lg">Prénom(s)</th> }
              <th class="c-md">Classe moteur</th><th class="c-md">Classe retenue</th><th class="c-md">Source</th>
              <th class="c-md">Analyste KYC</th><th class="c-date">Date</th><th class="c-md">Statut</th><th class="c-act">Actions</th>
            </tr></thead>
            <tbody>
              @for (r of data()?.items ?? []; track r.racine_client) {
                <tr>
                  @if (store.cap().classif_executer) {
                    <td><input type="checkbox" [checked]="selection().has(r.racine_client)" (change)="cocher(r.racine_client, $any($event.target).checked)" [attr.aria-label]="'Sélectionner ' + r.racine_client" /></td>
                  }
                  <td><code>{{ r.racine_client }}</code></td>
                  <td><code>{{ (pm ? r.nif : r.nni) || '—' }}</code></td>
                  @if (pm) { <td>{{ r.nom_client }}</td> } @else { <td>{{ r.nom_client }}</td><td>{{ r.prenoms || '—' }}</td> }
                  <td>@if (r.classe_moteur) { <span class="bea-cl-badge" [attr.data-s]="r.classe_moteur">{{ r.classe_moteur }}</span> } @else { — }</td>
                  <td>@if (r.classe_retenue) { <span class="bea-cl-badge" [attr.data-s]="r.classe_retenue">{{ r.classe_retenue }}</span> } @else { <small class="bea-cl-hint">non classé</small> }
                    @if (r.ecart_moteur) { <span class="bea-cl-badge" data-s="A_VERIFIER" title="La classe moteur diffère de la classe retenue">Écart</span> }
                  </td>
                  <td>{{ r.source || '—' }}</td>
                  <td>{{ r.analyste_kyc || '—' }}</td>
                  <td>{{ dateFr(r.classifie_le) }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="r.statut_classification">{{ statuts[r.statut_classification] }}</span></td>
                  <td class="c-act">
                    @if (store.cap().classif_executer) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrirDecision(r)" [disabled]="busy()" [title]="'Décision manuelle pour ' + r.racine_client"><mat-icon>gavel</mat-icon> Classer</button>
                    }
                    <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/clientele/clients', r.racine_client]" [title]="'Fiche et classification individuelle de ' + r.racine_client"><mat-icon>open_in_new</mat-icon> Fiche</a></td>
                </tr>
              } @empty {
                <tr><td [attr.colspan]="colonnes()"><div class="bea-cl-empty"><mat-icon>group_off</mat-icon>{{ chargement() ? 'Chargement…' : 'Aucun client ' + profil + ' pour ces critères.' }}</div></td></tr>
              }
            </tbody>
          </table>
        </div>
        @if ((data()?.total ?? 0) > taille) {
          <app-pagination [page]="page()" [total]="data()!.total" [pageSize]="taille" [label]="'clients ' + profil" (pageChange)="page.set($event); charger()" />
        }
      </section>

      @if (selection().size) {
        <div class="bea-cl-bar">
          <span>{{ n(selection().size) }} client(s) {{ profil }} sélectionné(s)</span>
          <span class="bea-cl-actions">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="vider()">Vider</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="recap.set(true)" [disabled]="busy()"><mat-icon>rule</mat-icon> Classer la sélection en lot</button>
          </span>
        </div>
      }

      @if (cible(); as c) {
        <div class="bea-cl-modal" role="dialog" aria-modal="true" [attr.aria-label]="'Classer ' + c.racine_client" (click)="fermerDecision()" (keydown.escape)="fermerDecision()">
          <div class="bea-cl-modal__box bea-cl-dec" (click)="$event.stopPropagation()">
            <header class="bea-cl-modal__head">
              <div>
                <p class="bea-cl-modal__kicker">Décision manuelle · {{ profil }}</p>
                <h2><code>{{ c.racine_client }}</code> {{ c.nom_client }} {{ c.prenoms || '' }}</h2>
                <p class="bea-cl-modal__sub">
                  Classe moteur : {{ c.classe_moteur || 'aucune' }} · Classe retenue actuelle : {{ c.classe_retenue || 'non classé' }}
                  @if (c.analyste_kyc) { · Analyste : {{ c.analyste_kyc }} }
                </p>
              </div>
              <button type="button" class="bea-cl-modal__close" (click)="fermerDecision()" aria-label="Fermer"><mat-icon>close</mat-icon></button>
            </header>
            <div class="bea-cl-modal__body bea-cl-dec__body">
              <label class="bea-cl-field">Niveau retenu
                <select [(ngModel)]="niveau" name="niveau">
                  <option value="FAIBLE">Faible</option><option value="MOYEN">Moyen</option>
                  <option value="ELEVE">Élevé</option><option value="INTERDIT">Interdit</option>
                </select>
              </label>
              <label class="bea-cl-field">Analyste KYC (obligatoire)
                <select [(ngModel)]="analysteDecision" name="analysteDecision">
                  <option value="">— Choisir —</option>
                  @for (a of analystes(); track a) { <option [value]="a">{{ a }}</option> }
                </select>
              </label>
              <label class="bea-cl-field bea-cl-dec__motif">Motif de la décision (obligatoire)
                <textarea [(ngModel)]="motif" name="motif" rows="3" maxlength="2000" placeholder="Ex. revue KYC du 20/10 : activité confirmée"></textarea>
              </label>
              @if (store.cap().classif_forcer) {
                <label class="bea-cl-dec__force"><input type="checkbox" [(ngModel)]="forcer" name="forcer" /> Forçage : lever un blocage INTERDIT du moteur</label>
              }
              <p class="bea-cl-hint bea-cl-dec__motif">Ancien et nouveau niveau, motif, analyste, auteur et date sont historisés. Les imports et le moteur ne remplaceront pas cette décision.</p>
            </div>
            <footer class="bea-cl-modal__foot">
              <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/clientele/clients', c.racine_client]"><mat-icon>open_in_new</mat-icon> Voir la fiche complète</a>
              <span class="bea-cl-modal__foot-r">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermerDecision()">Annuler</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="enregistrerDecision(c.racine_client)" [disabled]="busy() || !motif.trim() || !analysteDecision"><mat-icon>gavel</mat-icon> Enregistrer la décision</button>
              </span>
            </footer>
          </div>
        </div>
      }

      @if (recap()) {
        <div class="bea-cl-modal" role="dialog" aria-modal="true" aria-label="Créer un lot depuis la sélection" (click)="recap.set(false)" (keydown.escape)="recap.set(false)">
          <div class="bea-cl-modal__box" (click)="$event.stopPropagation()">
            <header class="bea-cl-modal__head">
              <div>
                <p class="bea-cl-modal__kicker">Lot {{ profil }}</p>
                <h2>Classer {{ n(selection().size) }} client(s) en lot</h2>
                <p class="bea-cl-modal__sub">Le lot ne contient que des clients {{ profil }}. Rien n’est écrit à ce stade : le moteur est exécuté puis chaque proposition est acceptée, modifiée ou laissée en attente avant confirmation.</p>
              </div>
              <button type="button" class="bea-cl-modal__close" (click)="recap.set(false)" aria-label="Fermer"><mat-icon>close</mat-icon></button>
            </header>
            <div class="bea-cl-modal__body">
              <label class="bea-cl-field">Analyste KYC (référentiel)
                <select [(ngModel)]="analysteLot" name="analysteLot" required>
                  <option value="">— Choisir —</option>
                  @for (a of analystes(); track a) { <option [value]="a">{{ a }}</option> }
                </select>
              </label>
              <p class="bea-cl-hint">Les clients déjà classés manuellement restent protégés : leur décision n’est jamais remplacée sans arbitrage explicite.</p>
            </div>
            <footer class="bea-cl-modal__foot">
              <span></span>
              <span class="bea-cl-modal__foot-r">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="recap.set(false)">Annuler</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="creerLot()" [disabled]="busy() || !analysteLot"><mat-icon>playlist_add_check</mat-icon> Créer le lot</button>
              </span>
            </footer>
          </div>
        </div>
      }
    </div>
  `,
  styles: `
    .bea-cl-prog__card--inline { margin-bottom: 1rem; }
    label.is-disabled { opacity: 0.55; pointer-events: none; }
    .bea-cl-field { display: grid; gap: 0.35rem; font-size: 0.84rem; font-weight: 600; }
    .bea-cl-field select, .bea-cl-field textarea { font: inherit; font-weight: 400; padding: 0.5rem 0.6rem; border-radius: 0.6rem; border: 1px solid #cbd5e1; }
    .bea-cl-dec { width: min(42rem, 100%); }
    .bea-cl-dec__body { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem 1rem; }
    .bea-cl-dec__motif, .bea-cl-dec__force { grid-column: 1 / -1; }
    .bea-cl-dec__force { display: flex; gap: 0.5rem; align-items: center; font-size: 0.84rem; color: #9a3412; }
    td.c-act { white-space: nowrap; }
    td.c-act .bea-mg__btn + .bea-mg__btn { margin-left: 0.35rem; }
  `,
})
export class ClClassifProfilComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(ClienteleStore);
  readonly base = CL_BASE;
  readonly statuts = STATUTS_CLASSIFICATION;
  readonly n = n;
  readonly dateFr = dateFr;
  readonly pct = pourcentageFr;
  readonly profil: Profil = this.route.snapshot.data['profil'] === 'PM' ? 'PM' : 'PP';
  readonly pm = this.profil === 'PM';
  readonly taille = 50;

  readonly data = signal<PageSuivi | null>(null);
  readonly prog = signal<ProgressionClassification | null>(null);
  readonly bloc = computed<BlocProgression | null>(() => {
    const p = this.prog();
    return p ? (this.pm ? p.pm : p.pp) : null;
  });
  readonly analystes = signal<string[]>([]);
  readonly page = signal(1);
  readonly chargement = signal(false);
  readonly busy = signal(false);
  readonly selection = signal(new Set<string>());
  readonly recap = signal(false);
  readonly filtresApplique = signal<Record<string, string>>({});
  readonly filtresActifs = computed(() => Object.keys(this.filtresApplique()).length > 0);
  readonly paramsExport = computed(() => ({ ...this.filtresApplique(), profil: this.profil, perimetre: this.perimetreApplique() }));
  readonly perimetreApplique = signal<'TOUS' | 'OUVERTS'>('TOUS');
  readonly colonnes = computed(() => (this.store.cap().classif_executer ? 1 : 0) + (this.pm ? 10 : 11));
  readonly toutCoche = computed(() => {
    const items = this.data()?.items ?? [];
    const sel = this.selection();
    return items.length > 0 && items.every((r) => sel.has(r.racine_client));
  });

  readonly cible = signal<LigneSuivi | null>(null);
  niveau = 'MOYEN';
  motif = '';
  analysteDecision = '';
  forcer = false;
  f: Record<Champ, string> = this.vide();
  perimetre: 'TOUS' | 'OUVERTS' = 'TOUS';
  analysteLot = '';

  ngOnInit(): void {
    this.store.charger();
    const qp = this.route.snapshot.queryParamMap;
    for (const c of CHAMPS) this.f[c] = qp.get(c) ?? '';
    this.perimetre = qp.get('perimetre') === 'OUVERTS' ? 'OUVERTS' : 'TOUS';
    this.figer();
    this.charger();
    this.chargerProgression();
    this.api.get<string[]>(`${CL_BASE}/classification/analystes`).subscribe({ next: (a) => this.analystes.set(a), error: () => this.analystes.set([]) });
  }

  private vide(): Record<Champ, string> {
    return Object.fromEntries(CHAMPS.map((c) => [c, ''])) as Record<Champ, string>;
  }

  private figer(): void {
    const actifs: Record<string, string> = {};
    for (const c of CHAMPS) {
      const v = this.f[c].trim();
      if (v) actifs[c] = v;
    }
    this.filtresApplique.set(actifs);
    this.perimetreApplique.set(this.perimetre);
  }

  appliquer(): void {
    const perimetreChange = this.perimetre !== this.perimetreApplique();
    this.figer();
    this.page.set(1);
    this.selection.set(new Set());
    void this.router.navigate([], {
      relativeTo: this.route, replaceUrl: true,
      queryParams: { ...this.filtresApplique(), perimetre: this.perimetre === 'OUVERTS' ? 'OUVERTS' : null },
    });
    this.charger();
    if (perimetreChange) this.chargerProgression();
  }

  reinitialiser(): void {
    this.f = this.vide();
    this.appliquer();
  }

  filtrerStatut(statut: string): void {
    this.f.statut = statut;
    this.appliquer();
  }

  charger(): void {
    this.chargement.set(true);
    const params = { ...this.paramsExport(), page: this.page(), taille: this.taille };
    this.api.get<PageSuivi>(`${CL_BASE}/suivi/clients`, params).subscribe({
      next: (p) => { this.data.set(p); this.chargement.set(false); },
      error: (e) => {
        this.chargement.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Liste indisponible'));
      },
    });
  }

  private chargerProgression(): void {
    this.api.get<ProgressionClassification>(`${CL_BASE}/suivi/progression`, { perimetre: this.perimetreApplique() }).subscribe({
      next: (p) => this.prog.set(p),
      error: () => this.prog.set(null),
    });
  }

  ouvrirDecision(r: LigneSuivi): void {
    this.niveau = r.classe_retenue || r.classe_moteur || 'MOYEN';
    this.motif = '';
    this.analysteDecision = r.analyste_kyc && this.analystes().includes(r.analyste_kyc) ? r.analyste_kyc : '';
    this.forcer = false;
    this.cible.set(r);
  }

  fermerDecision(): void {
    this.cible.set(null);
  }

  enregistrerDecision(racine: string): void {
    const motif = this.motif.trim();
    if (!motif || !this.analysteDecision) {
      this.feedback.warning({ title: 'Saisie incomplète', message: 'Le motif et l’analyste KYC sont obligatoires.' });
      return;
    }
    const forcer = this.forcer && !!this.store.cap().classif_forcer;
    const niveau = this.niveau;
    this.feedback.run(() => this.api.post(`${CL_BASE}/clients/${racine}/classification`, {
      niveau, motif_classement: motif, analyste_kyc: this.analysteDecision, forcer, confirmation: forcer,
    }), {
      confirm: forcer
        ? { title: 'Forçage de classification', message: `FORÇAGE — retenir ${niveau} pour ${racine} ?`, hint: 'Lève un éventuel blocage INTERDIT du moteur. Action tracée dans l’audit.', confirmLabel: 'Confirmer le forçage', tone: 'danger' }
        : { action: 'validation', title: 'Décision manuelle', message: `Retenir ${niveau} pour ${racine} ?`, hint: 'Auteur, date, niveau et motif historisés.' },
      busy: this.busy,
      success: { title: 'Décision enregistrée', message: `${racine} : niveau retenu ${niveau}` },
      errorTitle: 'Décision refusée', retry: false,
    }).subscribe(() => {
      this.cible.set(null);
      this.charger();
      this.chargerProgression();
    });
  }

  vider(): void {
    this.selection.set(new Set());
  }

  cocher(racine: string, on: boolean): void {
    const s = new Set(this.selection());
    if (on) s.add(racine); else s.delete(racine);
    this.selection.set(s);
  }

  cocherPage(on: boolean): void {
    const s = new Set(this.selection());
    for (const r of this.data()?.items ?? []) {
      if (on) s.add(r.racine_client); else s.delete(r.racine_client);
    }
    this.selection.set(s);
  }

  creerLot(): void {
    const racines = [...this.selection()];
    this.feedback.run(() => this.api.post<{ id: string; racines: number }>(`${CL_BASE}/lots/depuis-selection`, {
      profil: this.profil, racines, analyste_kyc: this.analysteLot,
    }), {
      busy: this.busy, loading: 'Création du lot…',
      success: (r) => ({ title: 'Lot créé', message: `${n(r.racines)} client(s) ${this.profil}. Exécutez le moteur puis validez les décisions.` }),
      errorTitle: 'Lot refusé', retry: false,
    }).subscribe({
      next: (r) => {
        this.recap.set(false);
        this.selection.set(new Set());
        void this.router.navigate(['/clientele/classification-lot'], { queryParams: { lot: r.id } });
      },
    });
  }

  importer(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const fichier = input.files?.[0];
    input.value = '';
    if (!fichier) return;
    if (!/\.(xlsx|xlsm)$/i.test(fichier.name)) {
      this.feedback.warning({ title: 'Format non pris en charge', message: 'Fichier .xlsx attendu.' });
      return;
    }
    const fd = new FormData();
    fd.append('fichier', fichier);
    this.feedback.run(() => this.api.post<{ id: string; stats: Record<string, number> }>(`${CL_BASE}/lots/analyse?type=LISTE&profil=${this.profil}`, fd), {
      busy: this.busy, loading: 'Contrôle de la liste…',
      success: (r) => ({
        title: 'Liste contrôlée',
        message: `${n(r.stats['lignes'])} ligne(s), ${n(r.stats['racines_ok'])} client(s) ${this.profil} reconnu(s). Rien n’est encore écrit.`,
      }),
      errorTitle: 'Liste refusée', retry: false,
    }).subscribe({
      next: (r) => void this.router.navigate(['/clientele/classification-lot'], { queryParams: { lot: r.id } }),
    });
  }
}
