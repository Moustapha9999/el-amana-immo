import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FoDonutComponent, FoHBarsComponent, FoLineComponent, FoStackComponent } from '../formation-charts';
import { FormationUiComponent } from '../formation-ui.component';
import { ANNEE_COURANTE, Domaine, Employe, FO_BASE, Groupe, Page, Reporting, dateFr, nettoyer, taux, telecharger } from '../formation.models';
import { FormationStore } from '../formation.store';

const CLES = ['annee', 'date_debut', 'date_fin', 'theme_id', 'formateur_id', 'lieu_id', 'entite_id', 'perimetre_id', 'fonction_id', 'employe_id', 'presence'] as const;
type Cle = (typeof CLES)[number];
const PRESENCES: Record<string, string> = { PRESENT: 'Présents', ABSENT: 'Absents', NON_SAISI: 'Non saisies' };
type Tableau = 'formations' | 'participants' | 'theme' | 'entite' | 'perimetre' | 'fonction' | 'formateur' | 'lieu';

@Component({
  selector: 'bea-fo-reporting',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, FormationUiComponent, FoStackComponent, FoLineComponent, FoDonutComponent, FoHBarsComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <p class="bea-stock-page__kicker">Formation &amp; Sensibilisation</p>
          <h1>Reporting</h1>
          <p class="bea-fo-head__sub">Statistiques par année, thème, entité, périmètre, présence et absence. Les exports reprennent exactement les filtres appliqués.</p>
        </div>
        @if (store.cap().reporting_exporter) {
          <div class="bea-mg__actions">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="exporter('pdf')" [disabled]="export() !== null"><mat-icon>{{ export() === 'pdf' ? 'hourglass_top' : 'picture_as_pdf' }}</mat-icon> Rapport PDF</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="exporter('xlsx')" [disabled]="export() !== null"><mat-icon>{{ export() === 'xlsx' ? 'hourglass_top' : 'grid_on' }}</mat-icon> Rapport Excel</button>
          </div>
        }
      </header>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2><mat-icon style="vertical-align:middle;color:#1a5278">filter_alt</mat-icon> Filtres</h2></div>
        <div class="bea-fo-filters">
          <label>Année
            <select [value]="f().annee ?? ''" (change)="maj('annee', $any($event.target).value)">
              <option value="">Toutes</option>
              @for (a of annees; track a) { <option [value]="a">{{ a }}</option> }
            </select>
          </label>
          <label>Du <input type="date" [value]="f().date_debut ?? ''" (change)="maj('date_debut', $any($event.target).value)" /></label>
          <label>Au <input type="date" [value]="f().date_fin ?? ''" (change)="maj('date_fin', $any($event.target).value)" /></label>
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
          <label>Fonction
            <select [value]="f().fonction_id ?? ''" (change)="maj('fonction_id', $any($event.target).value)">
              <option value="">Toutes</option>
              @for (r of store.refs('FONCTION', true); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
            </select>
          </label>
          <label>Présence
            <select [value]="f().presence ?? ''" (change)="maj('presence', $any($event.target).value)">
              <option value="">Toutes</option><option value="PRESENT">Présents</option><option value="ABSENT">Absents</option><option value="NON_SAISI">Non saisies</option>
            </select>
          </label>
          <label style="position:relative;grid-column: span 2">Employé
            @if (f().employe_id) {
              <span class="bea-fo-active" style="padding-top:0.2rem"><button type="button" (click)="maj('employe_id', '')">{{ nomEmploye() || 'Employé sélectionné' }} <mat-icon>close</mat-icon></button></span>
            } @else {
              <input type="search" placeholder="Rechercher un employé…" [value]="qEmp()" (input)="chercherEmploye($any($event.target).value)" />
              @if (resultatsEmp().length) {
                <div class="bea-fo-search__drop">
                  @for (e of resultatsEmp(); track e.id) {
                    <button type="button" class="bea-fo-search__item" (mousedown)="choisirEmploye(e)">
                      <mat-icon>person</mat-icon><span><strong>{{ e.nom_complet }}</strong><small>{{ e.entite || '—' }}</small></span>
                    </button>
                  }
                </div>
              }
            }
          </label>
        </div>
        @if (actifs().length) {
          <div class="bea-fo-filters__foot">
            <div class="bea-fo-active">
              @for (a of actifs(); track a.cle) { <button type="button" (click)="maj(a.cle, '')">{{ a.label }} <mat-icon>close</mat-icon></button> }
            </div>
            <button type="button" class="bea-fo-linkbtn" (click)="reinitialiser()">Réinitialiser</button>
          </div>
        }
      </section>

      @if (!r()) {
        <div class="bea-fx-kpis">@for (i of [1, 2, 3, 4, 5, 6]; track i) { <span class="bea-fx-skel bea-fx-skel--kpi"></span> }</div>
        <div class="bea-fo-grid"><span class="bea-fx-skel bea-fx-skel--chart bea-fo-span2"></span><span class="bea-fx-skel bea-fx-skel--chart"></span></div>
      } @else {
        @let d = r()!;
        <div class="bea-fx-kpis" [style.opacity]="charge() ? 0.55 : 1" style="transition:opacity 0.2s">
          <div class="bea-fx-kpi"><mat-icon>school</mat-icon><p>Formations</p><strong>{{ d.kpis.formations }}</strong><small>{{ d.kpis.formations_realisees }} réalisée(s)</small></div>
          <div class="bea-fx-kpi" data-tone="alert"><mat-icon>groups</mat-icon><p>Participations</p><strong>{{ d.kpis.participations }}</strong><small>{{ d.kpis.employes_concernes }} employé(s)</small></div>
          <div class="bea-fx-kpi" data-tone="ok"><mat-icon>how_to_reg</mat-icon><p>Présents</p><strong>{{ d.kpis.presents }}</strong><small>{{ d.kpis.employes_formes }} employé(s) formé(s)</small></div>
          <div class="bea-fx-kpi" data-tone="danger"><mat-icon>person_off</mat-icon><p>Absents</p><strong>{{ d.kpis.absents }}</strong><small>{{ d.kpis.non_saisis }} non saisie(s)</small></div>
          <div class="bea-fx-kpi" data-tone="brand"><mat-icon>percent</mat-icon><p>Taux de présence</p><strong>{{ taux(d.kpis.taux_presence) }}</strong><small>sur présences saisies</small></div>
          <div class="bea-fx-kpi" data-tone="warn"><mat-icon>category</mat-icon><p>Thèmes couverts</p><strong>{{ d.kpis.themes_couverts }}</strong><small>&nbsp;</small></div>
        </div>

        <div class="bea-fo-grid" [style.opacity]="charge() ? 0.55 : 1" style="transition:opacity 0.2s">
          <section class="bea-mg__panel bea-fo-span2">
            <div class="bea-mg__panel-top"><h2>{{ f().annee ? 'Évolution mensuelle ' + f().annee : 'Par année' }}</h2></div>
            @if (f().annee) { <bea-fo-line [series]="d.par_mois" /> } @else { <bea-fo-stack [series]="d.par_annee" (choisir)="maj('annee', $event)" /> }
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Présence / absence</h2></div>
            <bea-fo-donut [parts]="presenceParts()" [centre]="taux(d.kpis.taux_presence)" unite="présence" (choisir)="maj('presence', $event)" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par thème</h2></div>
            <bea-fo-hbars [groupes]="d.par_theme" [cliquable]="true" (choisir)="filtrerPar('theme_id', 'THEME', $event)" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par périmètre</h2></div>
            <bea-fo-hbars [groupes]="d.par_perimetre" [cliquable]="true" (choisir)="filtrerPar('perimetre_id', 'PERIMETRE', $event)" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par entité</h2></div>
            <bea-fo-hbars [groupes]="d.par_entite" [cliquable]="true" (choisir)="filtrerEntite($event)" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par formateur</h2></div>
            <bea-fo-hbars [groupes]="d.par_formateur" [limite]="6" [cliquable]="true" (choisir)="filtrerPar('formateur_id', 'FORMATEUR', $event)" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par lieu</h2></div>
            <bea-fo-hbars [groupes]="d.par_lieu" [limite]="6" [cliquable]="true" (choisir)="filtrerPar('lieu_id', 'LIEU', $event)" />
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par fonction</h2></div>
            <bea-fo-hbars [groupes]="d.par_fonction" [limite]="6" [cliquable]="true" (choisir)="filtrerPar('fonction_id', 'FONCTION', $event)" />
          </section>
        </div>

        <nav class="bea-ct-tabs" style="margin-bottom:0.9rem">
          @for (t of tableaux; track t.code) {
            <button type="button" [class.is-on]="tableau() === t.code" (click)="tableau.set(t.code)">{{ t.label }}</button>
          }
        </nav>
        <section class="bea-mg__panel">
          <div class="bea-mg__table-wrap">
            @if (tableau() === 'formations') {
              <table class="bea-mg__table bea-fo-table">
                <thead><tr><th>Date</th><th>Référence</th><th>Thème</th><th>Lieu</th><th>Formateur</th><th class="is-num">Participants</th><th class="is-num">Présents</th><th class="is-num">Absents</th><th>Taux</th><th>Statut</th></tr></thead>
                <tbody>
                  @for (x of d.formations.slice(0, limite()); track x.id) {
                    <tr class="is-click" (click)="router.navigate(['/formation/sessions', x.id])">
                      <td>{{ dateFr(x.date) }}</td><td><span class="bea-mg__code">{{ x.reference }}</span></td><td>{{ x.theme }}</td><td>{{ x.lieu }}</td><td>{{ x.formateur }}</td>
                      <td class="is-num">{{ x.participants }}</td><td class="is-num">{{ x.presents }}</td><td class="is-num">{{ x.absents }}</td>
                      <td>{{ taux(x.taux) }}</td><td><span class="bea-fo-badge" [attr.data-s]="x.statut">{{ x.statut_libelle }}</span></td>
                    </tr>
                  } @empty { <tr><td colspan="10"><div class="bea-fo-empty">Aucune formation.</div></td></tr> }
                </tbody>
              </table>
              @if (d.formations.length > limite()) { <div class="bea-fx-pager"><button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="limite.set(limite() + 100)">Afficher plus</button></div> }
            } @else if (tableau() === 'participants') {
              <table class="bea-mg__table bea-fo-table">
                <thead><tr><th>Date</th><th>Nom</th><th>Prénom</th><th>Fonction</th><th>Entité</th><th>Périmètre</th><th>Thème</th><th>Présence</th></tr></thead>
                <tbody>
                  @for (x of d.participations.slice(0, limite()); track x.session_id + x.employe_id) {
                    <tr>
                      <td>{{ dateFr(x.date) }}</td>
                      <td><a class="bea-ct-link" (click)="router.navigate(['/formation/employes', x.employe_id])">{{ x.nom }}</a></td>
                      <td>{{ x.prenom || '—' }}</td><td>{{ x.fonction || '—' }}</td><td>{{ x.entite || '—' }}</td><td>{{ x.perimetre || '—' }}</td><td>{{ x.theme }}</td>
                      <td><span class="bea-fo-badge" [attr.data-s]="x.presence ?? 'NON_SAISI'">{{ x.presence_libelle || 'Non saisie' }}</span></td>
                    </tr>
                  } @empty { <tr><td colspan="8"><div class="bea-fo-empty">Aucune participation.</div></td></tr> }
                </tbody>
              </table>
              @if (d.participations.length > limite()) { <div class="bea-fx-pager"><button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="limite.set(limite() + 100)">Afficher plus</button></div> }
              @if (d.participations_total > d.participations.length) { <p class="bea-fo-hint" style="padding:0 1rem 0.8rem">{{ d.participations_total }} participations au total : l’export Excel les contient toutes.</p> }
            } @else {
              <table class="bea-mg__table bea-fo-table">
                <thead><tr><th>{{ libTableau() }}</th><th class="is-num">Formations</th><th class="is-num">Participations</th><th class="is-num">Présents</th><th class="is-num">Absents</th><th class="is-num">Employés</th><th>Taux de présence</th></tr></thead>
                <tbody>
                  @for (g of groupes(); track g.libelle) {
                    <tr>
                      <td><strong>{{ g.libelle }}</strong></td><td class="is-num">{{ g.formations }}</td><td class="is-num">{{ g.participants }}</td>
                      <td class="is-num">{{ g.presents }}</td><td class="is-num">{{ g.absents }}</td><td class="is-num">{{ g.employes }}</td>
                      <td><span class="bea-fo-pct"><span class="bea-fo-progress"><i class="is-p" [style.width.%]="g.taux ?? 0"></i></span><b>{{ taux(g.taux) }}</b></span></td>
                    </tr>
                  } @empty { <tr><td colspan="7"><div class="bea-fo-empty">Aucune donnée.</div></td></tr> }
                </tbody>
              </table>
            }
          </div>
        </section>
      }
    </div>
  `,
})
export class FoReportingComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly router = inject(Router);
  readonly store = inject(FormationStore);

  readonly annees = Array.from({ length: 8 }, (_, i) => ANNEE_COURANTE - i);
  readonly dateFr = dateFr;
  readonly taux = taux;
  readonly tableaux: { code: Tableau; label: string }[] = [
    { code: 'formations', label: 'Formations' },
    { code: 'participants', label: 'Participants' },
    { code: 'theme', label: 'Par thème' },
    { code: 'entite', label: 'Par entité' },
    { code: 'perimetre', label: 'Par périmètre' },
    { code: 'fonction', label: 'Par fonction' },
    { code: 'formateur', label: 'Par formateur' },
    { code: 'lieu', label: 'Par lieu' },
  ];

  readonly f = signal<Partial<Record<Cle, string>>>({});
  readonly r = signal<Reporting | null>(null);
  readonly charge = signal(false);
  readonly export = signal<'pdf' | 'xlsx' | null>(null);
  readonly tableau = signal<Tableau>('formations');
  readonly limite = signal(100);
  readonly qEmp = signal('');
  readonly resultatsEmp = signal<Employe[]>([]);
  readonly nomEmploye = signal('');
  private minuteur: ReturnType<typeof setTimeout> | null = null;

  readonly presenceParts = computed(() => {
    const couleurs: Record<string, string> = { PRESENT: '#15803d', ABSENT: '#dc2626', NON_SAISI: '#cbd5e1' };
    return (this.r()?.presence ?? []).map((p) => ({ label: p.libelle, value: p.valeur, color: couleurs[p.cle], cle: p.cle }));
  });
  readonly libTableau = computed(() => this.tableaux.find((t) => t.code === this.tableau())?.label.replace('Par ', '') ?? '');
  readonly groupes = computed<Groupe[]>(() => {
    const d = this.r();
    if (!d) return [];
    const m: Partial<Record<Tableau, Groupe[]>> = {
      theme: d.par_theme, entite: d.par_entite, perimetre: d.par_perimetre, fonction: d.par_fonction, formateur: d.par_formateur, lieu: d.par_lieu,
    };
    return m[this.tableau()] ?? [];
  });
  readonly actifs = computed(() => {
    const f = this.f();
    const out: { cle: Cle; label: string }[] = [];
    const lib = (d: Domaine, id?: string) => this.store.libelle(d, id) || '…';
    if (f.annee) out.push({ cle: 'annee', label: f.annee });
    if (f.date_debut) out.push({ cle: 'date_debut', label: `Depuis ${dateFr(f.date_debut)}` });
    if (f.date_fin) out.push({ cle: 'date_fin', label: `Jusqu’au ${dateFr(f.date_fin)}` });
    if (f.theme_id) out.push({ cle: 'theme_id', label: lib('THEME', f.theme_id) });
    if (f.formateur_id) out.push({ cle: 'formateur_id', label: lib('FORMATEUR', f.formateur_id) });
    if (f.lieu_id) out.push({ cle: 'lieu_id', label: lib('LIEU', f.lieu_id) });
    if (f.perimetre_id) out.push({ cle: 'perimetre_id', label: lib('PERIMETRE', f.perimetre_id) });
    if (f.entite_id) out.push({ cle: 'entite_id', label: this.store.entite(f.entite_id)?.libelle ?? 'Entité' });
    if (f.fonction_id) out.push({ cle: 'fonction_id', label: lib('FONCTION', f.fonction_id) });
    if (f.presence) out.push({ cle: 'presence', label: PRESENCES[f.presence] ?? f.presence });
    if (f.employe_id) out.push({ cle: 'employe_id', label: this.nomEmploye() || 'Employé' });
    return out;
  });

  ngOnInit(): void {
    this.store.charger();
    this.route.queryParamMap.subscribe((qp) => {
      const f: Partial<Record<Cle, string>> = {};
      for (const k of CLES) {
        const v = qp.get(k);
        if (v) f[k] = v;
      }
      this.f.set(f);
      this.charger();
    });
  }

  maj(cle: Cle, v: string): void {
    const f = { ...this.f(), [cle]: v || undefined };
    if (cle === 'annee' && v) {
      f.date_debut = undefined;
      f.date_fin = undefined;
    }
    if ((cle === 'date_debut' || cle === 'date_fin') && v) f.annee = undefined;
    if (cle === 'employe_id' && !v) this.nomEmploye.set('');
    void this.router.navigate([], { relativeTo: this.route, queryParams: nettoyer(f), replaceUrl: true });
  }

  reinitialiser(): void {
    this.nomEmploye.set('');
    void this.router.navigate([], { relativeTo: this.route, queryParams: {}, replaceUrl: true });
  }

  filtrerPar(cle: Cle, domaine: Domaine, libelle: string): void {
    const id = this.store.refs(domaine, true).find((r) => r.libelle === libelle)?.id;
    if (id) this.maj(cle, id);
  }

  filtrerEntite(libelle: string): void {
    const id = this.store.entites().find((e) => e.libelle === libelle)?.id;
    if (id) this.maj('entite_id', id);
  }

  chercherEmploye(q: string): void {
    this.qEmp.set(q);
    if (this.minuteur) clearTimeout(this.minuteur);
    if (q.trim().length < 2) {
      this.resultatsEmp.set([]);
      return;
    }
    this.minuteur = setTimeout(() => {
      this.api.get<Page<Employe>>(`${FO_BASE}/employes`, { q: q.trim(), actif: 'tous', taille: 8 }).subscribe({
        next: (p) => this.resultatsEmp.set(p.items),
        error: () => this.resultatsEmp.set([]),
      });
    }, 250);
  }

  choisirEmploye(e: Employe): void {
    this.nomEmploye.set(e.nom_complet);
    this.qEmp.set('');
    this.resultatsEmp.set([]);
    this.maj('employe_id', e.id);
  }

  private charger(): void {
    this.charge.set(true);
    this.limite.set(100);
    this.api.get<Reporting>(`${FO_BASE}/reporting`, nettoyer(this.f())).subscribe({
      next: (r) => {
        this.r.set(r);
        this.charge.set(false);
        const id = this.f().employe_id;
        if (id && !this.nomEmploye()) this.nomEmploye.set(r.participations.find((p) => p.employe_id === id)?.nom_complet ?? '');
      },
      error: (e) => {
        this.charge.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Reporting indisponible'));
      },
    });
  }

  exporter(format: 'pdf' | 'xlsx'): void {
    this.export.set(format);
    const h = this.feedback.loading(format === 'pdf' ? 'Génération du rapport PDF…' : 'Génération du rapport Excel…');
    this.api.download(`${FO_BASE}/reporting/export`, { ...nettoyer(this.f()), format }).subscribe({
      next: (b) => {
        this.export.set(null);
        telecharger(b, `Rapport_Formation.${format}`);
        h.success({ title: 'Rapport généré', message: `Rapport_Formation.${format}` });
      },
      error: (e) => {
        this.export.set(null);
        h.close();
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, "Échec de l'export"));
      },
    });
  }
}
