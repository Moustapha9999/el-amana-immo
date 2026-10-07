import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FormationUiComponent } from '../formation-ui.component';
import { ANNEE_COURANTE, FO_BASE, JournalLigne, Page, Reporting, correspond, dateFr, dateHeureFr, nettoyer } from '../formation.models';
import { FormationStore } from '../formation.store';

const ACTIONS_JOURNAL = [
  { code: '', label: 'Toutes les actions' },
  { code: 'formation.session', label: 'Formations' },
  { code: 'formation.presence', label: 'Présences' },
  { code: 'formation.participant', label: 'Participants' },
  { code: 'formation.employe', label: 'Employés' },
  { code: 'formation.referentiel', label: 'Référentiels' },
  { code: 'formation.entite', label: 'Entités' },
  { code: 'formation.import', label: 'Imports' },
  { code: 'formation.export', label: 'Exports' },
];

@Component({
  selector: 'bea-fo-historique',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, FormationUiComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <p class="bea-stock-page__kicker">Formation &amp; Sensibilisation</p>
          <h1>Historique</h1>
          <p class="bea-fo-head__sub">Historique des participations par employé et journal d’audit de toutes les actions du module.</p>
        </div>
      </header>

      <nav class="bea-ct-tabs" style="margin-bottom:0.9rem">
        <button type="button" [class.is-on]="onglet() === 'participations'" (click)="choisir('participations')"><mat-icon>groups</mat-icon> Participations</button>
        <button type="button" [class.is-on]="onglet() === 'journal'" (click)="choisir('journal')"><mat-icon>policy</mat-icon> Journal d’audit</button>
      </nav>

      @if (onglet() === 'participations') {
        <section class="bea-mg__panel">
          <div class="bea-fo-filters">
            <label style="grid-column: span 2">Employé / formation
              <input type="search" placeholder="Nom, thème, référence…" [value]="q()" (input)="q.set($any($event.target).value)" />
            </label>
            <label>Année
              <select [value]="pf().annee ?? ''" (change)="majP('annee', $any($event.target).value)">
                <option value="">Toutes</option>
                @for (a of annees; track a) { <option [value]="a">{{ a }}</option> }
              </select>
            </label>
            <label>Thème
              <select [value]="pf().theme_id ?? ''" (change)="majP('theme_id', $any($event.target).value)">
                <option value="">Tous</option>
                @for (r of store.refs('THEME', true); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
              </select>
            </label>
            <label>Entité
              <select [value]="pf().entite_id ?? ''" (change)="majP('entite_id', $any($event.target).value)">
                <option value="">Toutes</option>
                @for (e of store.entites(); track e.id) { <option [value]="e.id">{{ e.libelle }}</option> }
              </select>
            </label>
            <label>Présence
              <select [value]="pf().presence ?? ''" (change)="majP('presence', $any($event.target).value)">
                <option value="">Toutes</option><option value="PRESENT">Présent</option><option value="ABSENT">Absent</option><option value="NON_SAISI">Non saisie</option>
              </select>
            </label>
          </div>
        </section>
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Participations</h2>
            <span class="bea-mg__count">{{ lignes().length }}{{ (rep()?.participations_total ?? 0) > (rep()?.participations?.length ?? 0) ? ' / ' + rep()!.participations_total + ' (1 000 premières)' : '' }}</span></div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-fo-table">
              <thead><tr><th>Date</th><th>Employé</th><th>Fonction</th><th>Entité</th><th>Thème</th><th>Lieu</th><th>Présence</th></tr></thead>
              <tbody>
                @if (chargeP()) {
                  @for (i of [1, 2, 3, 4, 5]; track i) { <tr>@for (j of [1, 2, 3, 4, 5, 6, 7]; track j) { <td><span class="bea-fx-skel"></span></td> }</tr> }
                } @else {
                  @for (l of lignes().slice(0, limite()); track l.session_id + l.employe_id; let i = $index) {
                    <tr class="bea-fx-row-in" [style.--i]="i < 25 ? i : 0">
                      <td><a class="bea-ct-link" (click)="router.navigate(['/formation/sessions', l.session_id])">{{ dateFr(l.date) }}</a><small>{{ l.reference }}</small></td>
                      <td><a class="bea-ct-link" (click)="router.navigate(['/formation/employes', l.employe_id])"><strong>{{ l.nom_complet }}</strong></a></td>
                      <td>{{ l.fonction || '—' }}</td>
                      <td>{{ l.entite || '—' }}<small>{{ l.perimetre }}</small></td>
                      <td>{{ l.theme }}</td>
                      <td>{{ l.lieu }}</td>
                      <td><span class="bea-fo-badge" [attr.data-s]="l.presence ?? 'NON_SAISI'">{{ l.presence_libelle || 'Non saisie' }}</span></td>
                    </tr>
                  } @empty {
                    <tr><td colspan="7"><div class="bea-fo-empty"><mat-icon>history</mat-icon>Aucune participation.</div></td></tr>
                  }
                }
              </tbody>
            </table>
          </div>
          @if (lignes().length > limite()) {
            <div class="bea-fx-pager"><button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="limite.set(limite() + 100)">Afficher 100 de plus ({{ lignes().length - limite() }} restantes)</button></div>
          }
        </section>
      } @else {
        <section class="bea-mg__panel">
          <div class="bea-fo-filters">
            <label style="grid-column: span 2">Recherche
              <input type="search" placeholder="Utilisateur, référence, nom…" [value]="jf().q ?? ''" (input)="saisirJ($any($event.target).value)" />
            </label>
            <label>Type d’action
              <select [value]="jf().action ?? ''" (change)="majJ('action', $any($event.target).value)">
                @for (a of actionsJournal; track a.code) { <option [value]="a.code">{{ a.label }}</option> }
              </select>
            </label>
            <label>Du <input type="date" [value]="jf().date_debut ?? ''" (change)="majJ('date_debut', $any($event.target).value)" /></label>
            <label>Au <input type="date" [value]="jf().date_fin ?? ''" (change)="majJ('date_fin', $any($event.target).value)" /></label>
          </div>
        </section>
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Journal d’audit</h2><span class="bea-mg__count">{{ journal()?.total ?? 0 }} action(s)</span></div>
          @if (chargeJ()) {
            <div class="bea-fo-pad">@for (i of [1, 2, 3, 4]; track i) { <span class="bea-fx-skel bea-fx-skel--line"></span> }</div>
          } @else {
            <ul class="bea-fo-timeline">
              @for (h of journal()?.items ?? []; track h.id; let i = $index) {
                <li [style.--i]="i" [attr.data-k]="cle(h.action)">
                  <div class="bea-fo-timeline__head">
                    <strong>{{ h.libelle }}</strong>
                    <small>{{ dh(h.date) }} · {{ h.utilisateur }}</small>
                    @if (lien(h)) { <a class="bea-ct-link" style="font-size:0.78rem" (click)="ouvrir(h)">Ouvrir</a> }
                    <button type="button" class="bea-fo-linkbtn" (click)="basculer(h.id)">{{ ouverts().has(h.id) ? 'Masquer' : 'Détails' }}</button>
                  </div>
                  <p>{{ resume(h) }}</p>
                  @if (ouverts().has(h.id)) {
                    <div class="bea-fo-grid bea-fo-grid--2" style="margin:0.5rem 0 0">
                      @if (h.avant) { <pre class="bea-mg__panel bea-fo-pad" style="margin:0;font-size:0.72rem;white-space:pre-wrap;overflow:auto;max-height:16rem">Avant : {{ json(h.avant) }}</pre> }
                      @if (h.apres) { <pre class="bea-mg__panel bea-fo-pad" style="margin:0;font-size:0.72rem;white-space:pre-wrap;overflow:auto;max-height:16rem">Après : {{ json(h.apres) }}</pre> }
                    </div>
                    @if (h.request_id) { <p class="bea-fo-hint">Référence : {{ h.request_id }}</p> }
                  }
                </li>
              } @empty {
                <li>Aucune action.</li>
              }
            </ul>
          }
          @if ((journal()?.total ?? 0) > tailleJ) {
            <div class="bea-fx-pager">
              <button type="button" class="bea-mg__icon-btn" [disabled]="pageJ() <= 1" (click)="allerJ(pageJ() - 1)"><mat-icon>chevron_left</mat-icon></button>
              <span>Page {{ pageJ() }} / {{ nbPagesJ() }}</span>
              <button type="button" class="bea-mg__icon-btn" [disabled]="pageJ() >= nbPagesJ()" (click)="allerJ(pageJ() + 1)"><mat-icon>chevron_right</mat-icon></button>
            </div>
          }
        </section>
      }
    </div>
  `,
})
export class FoHistoriqueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly router = inject(Router);
  readonly store = inject(FormationStore);

  readonly annees = Array.from({ length: 8 }, (_, i) => ANNEE_COURANTE - i);
  readonly actionsJournal = ACTIONS_JOURNAL;
  readonly tailleJ = 30;
  readonly dateFr = dateFr;
  readonly dh = dateHeureFr;

  readonly onglet = signal<'participations' | 'journal'>('participations');
  readonly pf = signal<Partial<Record<'annee' | 'theme_id' | 'entite_id' | 'presence', string>>>({});
  readonly q = signal('');
  readonly rep = signal<Reporting | null>(null);
  readonly chargeP = signal(true);
  readonly limite = signal(100);
  readonly jf = signal<Partial<Record<'q' | 'action' | 'date_debut' | 'date_fin', string>>>({});
  readonly journal = signal<Page<JournalLigne> | null>(null);
  readonly chargeJ = signal(true);
  readonly pageJ = signal(1);
  readonly ouverts = signal(new Set<string>());
  private minuteur: ReturnType<typeof setTimeout> | null = null;

  readonly nbPagesJ = computed(() => Math.max(1, Math.ceil((this.journal()?.total ?? 0) / this.tailleJ)));
  readonly lignes = computed(() => {
    const q = this.q().trim();
    const l = this.rep()?.participations ?? [];
    return q ? l.filter((x) => correspond(`${x.nom_complet} ${x.theme} ${x.reference} ${x.entite ?? ''}`, q)) : l;
  });

  ngOnInit(): void {
    this.store.charger();
    if (this.route.snapshot.queryParamMap.get('onglet') === 'journal') this.onglet.set('journal');
    this.chargerP();
    if (this.onglet() === 'journal') this.chargerJ();
  }

  choisir(o: 'participations' | 'journal'): void {
    this.onglet.set(o);
    void this.router.navigate([], { relativeTo: this.route, queryParams: o === 'journal' ? { onglet: o } : {}, replaceUrl: true });
    if (o === 'journal' && !this.journal()) this.chargerJ();
  }

  majP(k: 'annee' | 'theme_id' | 'entite_id' | 'presence', v: string): void {
    this.pf.set({ ...this.pf(), [k]: v || undefined });
    this.chargerP();
  }

  private chargerP(): void {
    this.chargeP.set(true);
    this.limite.set(100);
    this.api.get<Reporting>(`${FO_BASE}/reporting`, nettoyer(this.pf())).subscribe({
      next: (r) => {
        this.rep.set(r);
        this.chargeP.set(false);
      },
      error: (e) => {
        this.chargeP.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Historique indisponible'));
      },
    });
  }

  saisirJ(v: string): void {
    if (this.minuteur) clearTimeout(this.minuteur);
    this.minuteur = setTimeout(() => this.majJ('q', v.trim()), 300);
  }

  majJ(k: 'q' | 'action' | 'date_debut' | 'date_fin', v: string): void {
    this.jf.set({ ...this.jf(), [k]: v || undefined });
    this.pageJ.set(1);
    this.chargerJ();
  }

  allerJ(n: number): void {
    this.pageJ.set(n);
    this.chargerJ();
  }

  private chargerJ(): void {
    this.chargeJ.set(true);
    this.api.get<Page<JournalLigne>>(`${FO_BASE}/journal`, nettoyer({ ...this.jf(), page: this.pageJ(), taille: this.tailleJ })).subscribe({
      next: (p) => {
        this.journal.set(p);
        this.chargeJ.set(false);
      },
      error: (e) => {
        this.chargeJ.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Journal indisponible'));
      },
    });
  }

  basculer(id: string): void {
    const s = new Set(this.ouverts());
    if (s.has(id)) s.delete(id);
    else s.add(id);
    this.ouverts.set(s);
  }

  cle(a: string): string {
    if (a.includes('cancel')) return 'cancel';
    if (a.includes('delete') || a.includes('remove') || a.includes('deactivate')) return 'delete';
    if (a.includes('close') || a.includes('confirm')) return 'close';
    if (a.includes('presence')) return 'attendance';
    return 'other';
  }

  lien(h: JournalLigne): string | null {
    if (!h.entity_id) return null;
    if (h.entity === 'formation_session' && h.action !== 'formation.session.delete') return `/formation/sessions/${h.entity_id}`;
    if (h.entity === 'formation_employe') return `/formation/employes/${h.entity_id}`;
    if (h.entity === 'formation_export' && h.apres?.['document'] === 'feuille_presence') return `/formation/sessions/${h.entity_id}`;
    return null;
  }

  ouvrir(h: JournalLigne): void {
    const l = this.lien(h);
    if (l) void this.router.navigateByUrl(l);
  }

  resume(h: JournalLigne): string {
    const a = h.apres ?? {};
    const b = h.avant ?? {};
    const champs = ['reference', 'libelle', 'nom_complet', 'fichier', 'document', 'motif', 'statut'];
    const parts: string[] = [];
    for (const k of champs) {
      const v = a[k] ?? b[k];
      if (typeof v === 'string' && v) parts.push(k === 'motif' ? `Motif : ${v}` : k === 'statut' ? `Statut : ${v}` : v);
    }
    if (typeof a['ajoutes'] === 'number') parts.push(`${a['ajoutes']} participant(s) ajouté(s)`);
    if (typeof a['sessions_creees'] === 'number') parts.push(`${a['sessions_creees']} formation(s) créée(s)`);
    if (typeof a['participations_creees'] === 'number') parts.push(`${a['participations_creees']} participation(s)`);
    if (typeof a['filtres'] === 'string') parts.push(`Filtres : ${a['filtres']}`);
    return parts.join(' · ') || h.entity;
  }

  json(v: unknown): string {
    return JSON.stringify(v, null, 2);
  }
}
