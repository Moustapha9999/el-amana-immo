import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FormationUiComponent } from '../formation-ui.component';
import { ANNEE_COURANTE, FO_BASE, Page, Session, dateFr, nettoyer, statutAffiche, taux } from '../formation.models';
import { FormationStore } from '../formation.store';

const ONGLETS = [
  { code: 'ACTIVES', label: 'Actives', icon: 'event_available' },
  { code: 'PLANIFIEE', label: 'Planifiées', icon: 'event' },
  { code: 'A_SAISIR', label: 'Présences à saisir', icon: 'edit_calendar' },
  { code: 'REALISEE', label: 'Réalisées', icon: 'fact_check' },
  { code: 'CLOTUREE', label: 'Clôturées', icon: 'task_alt' },
  { code: 'ANNULEE', label: 'Annulées', icon: 'event_busy' },
  { code: 'ARCHIVEE', label: 'Archivées', icon: 'inventory_2' },
  { code: 'TOUTES', label: 'Toutes', icon: 'list' },
];

const FILTRES = ['q', 'annee', 'theme_id', 'formateur_id', 'lieu_id', 'entite_id', 'perimetre_id', 'feuille', 'date_debut', 'date_fin'] as const;
type Filtre = (typeof FILTRES)[number];

@Component({
  selector: 'bea-fo-sessions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, FormationUiComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <p class="bea-stock-page__kicker">Formation &amp; Sensibilisation</p>
          <h1>Formations</h1>
          <p class="bea-fo-head__sub">Toutes les sessions de formation : planification, présences, clôture et archivage.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap().creer) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/formation/sessions/nouvelle"><mat-icon>add</mat-icon> Nouvelle formation</a>
          }
        </div>
      </header>

      <nav class="bea-ct-tabs" style="margin-bottom:0.9rem">
        @for (o of onglets; track o.code) {
          <button type="button" [class.is-on]="onglet() === o.code" (click)="choisirOnglet(o.code)"><mat-icon>{{ o.icon }}</mat-icon> {{ o.label }}</button>
        }
      </nav>

      <section class="bea-mg__panel">
        <div class="bea-fo-filters">
          <label style="grid-column: span 2">Recherche
            <input type="search" placeholder="Référence, thème, lieu, formateur…" [value]="f().q ?? ''" (input)="saisirQ($any($event.target).value)" />
          </label>
          <label>Année
            <select [value]="f().annee ?? ''" (change)="maj('annee', $any($event.target).value)">
              <option value="">Toutes</option>
              @for (a of annees; track a) { <option [value]="a">{{ a }}</option> }
            </select>
          </label>
          <label>Thème
            <select [value]="f().theme_id ?? ''" (change)="maj('theme_id', $any($event.target).value)">
              <option value="">Tous</option>
              @for (r of store.refs('THEME', true); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
            </select>
          </label>
          <label>Formateur
            <select [value]="f().formateur_id ?? ''" (change)="maj('formateur_id', $any($event.target).value)">
              <option value="">Tous</option>
              @for (r of store.refs('FORMATEUR', true); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
            </select>
          </label>
          <label>Lieu
            <select [value]="f().lieu_id ?? ''" (change)="maj('lieu_id', $any($event.target).value)">
              <option value="">Tous</option>
              @for (r of store.refs('LIEU', true); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
            </select>
          </label>
          <label>Périmètre
            <select [value]="f().perimetre_id ?? ''" (change)="maj('perimetre_id', $any($event.target).value)">
              <option value="">Tous</option>
              @for (r of store.refs('PERIMETRE', true); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
            </select>
          </label>
          <label>Entité
            <select [value]="f().entite_id ?? ''" (change)="maj('entite_id', $any($event.target).value)">
              <option value="">Toutes</option>
              @for (e of store.entites(); track e.id) { <option [value]="e.id">{{ e.libelle }}</option> }
            </select>
          </label>
          <label>Feuille signée
            <select [value]="f().feuille ?? ''" (change)="maj('feuille', $any($event.target).value)">
              <option value="">Toutes</option>
              <option value="AVEC">Déposée dans la GED</option>
              <option value="SANS">Manquante</option>
            </select>
          </label>
          <label>Du <input type="date" [value]="f().date_debut ?? ''" (change)="maj('date_debut', $any($event.target).value)" /></label>
          <label>Au <input type="date" [value]="f().date_fin ?? ''" (change)="maj('date_fin', $any($event.target).value)" /></label>
        </div>
        @if (actifs().length) {
          <div class="bea-fo-filters__foot">
            <div class="bea-fo-active">
              @for (a of actifs(); track a.cle) {
                <button type="button" (click)="maj(a.cle, '')">{{ a.label }} <mat-icon>close</mat-icon></button>
              }
            </div>
            <button type="button" class="bea-fo-linkbtn" (click)="reinitialiser()">Réinitialiser</button>
          </div>
        }
      </section>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>{{ libelleOnglet() }}</h2>
          <span class="bea-mg__count">{{ page()?.total ?? 0 }} formation(s)</span>
        </div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-fo-table">
            <thead>
              <tr>
                <th><button type="button" class="bea-fx-sort" (click)="trier('date')">Date <mat-icon>{{ icone('date') }}</mat-icon></button></th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('reference')">Référence <mat-icon>{{ icone('reference') }}</mat-icon></button></th>
                <th>Thème</th>
                <th>Lieu</th>
                <th>Formateur</th>
                <th class="is-num"><button type="button" class="bea-fx-sort" (click)="trier('participants')">Participants <mat-icon>{{ icone('participants') }}</mat-icon></button></th>
                <th>Présence</th>
                <th class="is-c" title="Feuille de présence signée dans la GED">Feuille</th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('statut')">Statut <mat-icon>{{ icone('statut') }}</mat-icon></button></th>
              </tr>
            </thead>
            <tbody>
              @if (charge()) {
                @for (i of [1, 2, 3, 4, 5, 6]; track i) {
                  <tr>@for (j of [1, 2, 3, 4, 5, 6, 7, 8, 9]; track j) { <td><span class="bea-fx-skel"></span></td> }</tr>
                }
              } @else {
                @for (s of page()?.items ?? []; track s.id; let i = $index) {
                  <tr class="is-click bea-fx-row-in" [style.--i]="i" (click)="ouvrir(s)">
                    <td><strong>{{ dateFr(s.date_session) }}</strong></td>
                    <td><span class="bea-mg__code">{{ s.reference }}</span></td>
                    <td>
                      <div class="bea-fo-tags">@for (t of s.themes; track t.id) { <span class="bea-fo-tag">{{ t.libelle }}</span> }</div>
                      @if (s.intitule) { <small>{{ s.intitule }}</small> }
                    </td>
                    <td>{{ s.lieu?.libelle || '—' }}</td>
                    <td>{{ s.formateur_libelle || '—' }}</td>
                    <td class="is-num">{{ s.stats.participants }}</td>
                    <td>
                      @if (s.stats.presents + s.stats.absents) {
                        <span class="bea-fo-pct" [title]="s.stats.presents + ' présent(s), ' + s.stats.absents + ' absent(s)'">
                          <span class="bea-fo-progress">
                            <i class="is-p" [style.width.%]="pct(s.stats.presents, s.stats.participants)"></i>
                            <i class="is-a" [style.width.%]="pct(s.stats.absents, s.stats.participants)"></i>
                          </span>
                          <b>{{ taux(s.stats.taux_presence) }}</b>
                        </span>
                      } @else {
                        <span class="bea-fo-hint">{{ s.a_venir ? 'À venir' : 'Non saisie' }}</span>
                      }
                    </td>
                    <td class="is-c">
                      @if (s.feuilles_signees) {
                        <span class="bea-fo-feuille-ok" [title]="s.feuilles_signees + ' feuille(s) signée(s) dans la GED'"><mat-icon>verified</mat-icon></span>
                      } @else if (s.statut === 'REALISEE' || s.statut === 'CLOTUREE') {
                        <span class="bea-fo-feuille-ko" title="Feuille signée manquante"><mat-icon>priority_high</mat-icon></span>
                      } @else {
                        <span class="bea-fo-hint">—</span>
                      }
                    </td>
                    <td><span class="bea-fo-badge" [attr.data-s]="st(s).code">{{ st(s).label }}</span></td>
                  </tr>
                } @empty {
                  <tr><td colspan="9">
                    <div class="bea-fo-empty"><mat-icon>event_note</mat-icon><strong>Aucune formation</strong>Modifiez les filtres ou créez une nouvelle formation.</div>
                  </td></tr>
                }
              }
            </tbody>
          </table>
        </div>
        @if ((page()?.total ?? 0) > taille) {
          <div class="bea-fx-pager">
            <button type="button" class="bea-mg__icon-btn" [disabled]="pageNo() <= 1" (click)="allerPage(pageNo() - 1)"><mat-icon>chevron_left</mat-icon></button>
            <span>Page {{ pageNo() }} / {{ nbPages() }}</span>
            <button type="button" class="bea-mg__icon-btn" [disabled]="pageNo() >= nbPages()" (click)="allerPage(pageNo() + 1)"><mat-icon>chevron_right</mat-icon></button>
          </div>
        }
      </section>
    </div>
  `,
})
export class FoSessionsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(FormationStore);

  readonly onglets = ONGLETS;
  readonly annees = Array.from({ length: 8 }, (_, i) => ANNEE_COURANTE + 1 - i);
  readonly taille = 25;
  readonly dateFr = dateFr;
  readonly taux = taux;
  readonly st = statutAffiche;

  readonly onglet = signal('ACTIVES');
  readonly f = signal<Partial<Record<Filtre, string>>>({});
  readonly tri = signal('date');
  readonly sens = signal<'asc' | 'desc'>('desc');
  readonly pageNo = signal(1);
  readonly page = signal<Page<Session> | null>(null);
  readonly charge = signal(true);
  private minuteur: ReturnType<typeof setTimeout> | null = null;

  readonly nbPages = computed(() => Math.max(1, Math.ceil((this.page()?.total ?? 0) / this.taille)));
  readonly libelleOnglet = computed(() => ONGLETS.find((o) => o.code === this.onglet())?.label ?? 'Formations');
  readonly actifs = computed(() => {
    const f = this.f();
    const out: { cle: Filtre; label: string }[] = [];
    const lib = (d: 'THEME' | 'FORMATEUR' | 'LIEU' | 'PERIMETRE', id?: string) => this.store.libelle(d, id);
    if (f.q) out.push({ cle: 'q', label: `« ${f.q} »` });
    if (f.annee) out.push({ cle: 'annee', label: f.annee });
    if (f.theme_id) out.push({ cle: 'theme_id', label: lib('THEME', f.theme_id) });
    if (f.formateur_id) out.push({ cle: 'formateur_id', label: lib('FORMATEUR', f.formateur_id) });
    if (f.lieu_id) out.push({ cle: 'lieu_id', label: lib('LIEU', f.lieu_id) });
    if (f.perimetre_id) out.push({ cle: 'perimetre_id', label: lib('PERIMETRE', f.perimetre_id) });
    if (f.entite_id) out.push({ cle: 'entite_id', label: this.store.entite(f.entite_id)?.libelle ?? 'Entité' });
    if (f.feuille) out.push({ cle: 'feuille', label: f.feuille === 'AVEC' ? 'Feuille signée déposée' : 'Feuille signée manquante' });
    if (f.date_debut) out.push({ cle: 'date_debut', label: `Depuis ${dateFr(f.date_debut)}` });
    if (f.date_fin) out.push({ cle: 'date_fin', label: `Jusqu’au ${dateFr(f.date_fin)}` });
    return out;
  });

  ngOnInit(): void {
    this.store.charger();
    const qp = this.route.snapshot.queryParamMap;
    const statut = qp.get('statut');
    if (statut && ONGLETS.some((o) => o.code === statut)) this.onglet.set(statut);
    const f: Partial<Record<Filtre, string>> = {};
    for (const k of FILTRES) {
      const v = qp.get(k);
      if (v) f[k] = v;
    }
    this.f.set(f);
    this.charger();
  }

  choisirOnglet(code: string): void {
    this.onglet.set(code);
    this.pageNo.set(1);
    this.synchroniser();
  }

  saisirQ(v: string): void {
    if (this.minuteur) clearTimeout(this.minuteur);
    this.minuteur = setTimeout(() => this.maj('q', v.trim()), 300);
  }

  maj(cle: Filtre, v: string): void {
    this.f.set({ ...this.f(), [cle]: v || undefined });
    this.pageNo.set(1);
    this.synchroniser();
  }

  reinitialiser(): void {
    this.f.set({});
    this.pageNo.set(1);
    this.synchroniser();
  }

  trier(col: string): void {
    if (this.tri() === col) this.sens.set(this.sens() === 'asc' ? 'desc' : 'asc');
    else {
      this.tri.set(col);
      this.sens.set(col === 'reference' ? 'asc' : 'desc');
    }
    this.charger();
  }

  icone(col: string): string {
    return this.tri() !== col ? 'unfold_more' : this.sens() === 'asc' ? 'arrow_upward' : 'arrow_downward';
  }

  allerPage(n: number): void {
    this.pageNo.set(n);
    this.charger();
  }

  pct(n: number, total: number): number {
    return total ? (n / total) * 100 : 0;
  }

  ouvrir(s: Session): void {
    void this.router.navigate(['/formation/sessions', s.id]);
  }

  private synchroniser(): void {
    const qp = nettoyer({ ...this.f(), statut: this.onglet() === 'ACTIVES' ? '' : this.onglet() });
    void this.router.navigate([], { relativeTo: this.route, queryParams: qp, replaceUrl: true });
    this.charger();
  }

  private charger(): void {
    this.charge.set(true);
    const o = this.onglet();
    const params = nettoyer({
      ...this.f(),
      statut: o === 'TOUTES' ? '' : o === 'A_SAISIR' ? '' : o,
      a_saisir: o === 'A_SAISIR',
      tri: this.tri(),
      sens: this.sens(),
      page: this.pageNo(),
      taille: this.taille,
    });
    this.api.get<Page<Session>>(`${FO_BASE}/sessions`, params).subscribe({
      next: (p) => {
        this.page.set(p);
        this.charge.set(false);
      },
      error: (e) => {
        this.charge.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Liste des formations indisponible'));
      },
    });
  }
}
