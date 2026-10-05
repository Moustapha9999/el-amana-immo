import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { EerAgence, EerDimension, EerGranularite, EerService } from './eer.service';
import {
  EerKpiEtatsCompte,
  EerKpiGlobal,
  EerKpiRepartition,
  EerKpiSerie,
  EerPerimetre,
  EerRepartition,
  EerFormatExport,
  EerTableauDeBord,
  TYPES_CLIENT,
  libelle,
  telechargerBlob,
} from './eer.models';

const DIMENSIONS: Array<[EerDimension, string]> = [
  ['risque', 'risque LBC-FT'],
  ['ppe', 'PPE'],
  ['fatca', 'FATCA'],
  ['residence', 'pays de résidence'],
  ['analyste', 'analyste'],
  ['profil', 'profil (sous-profil Excel)'],
  ['sous_profil', 'sous-profil'],
];

interface Carte {
  cle: keyof EerTableauDeBord;
  label: string;
  statut: string | null;
  tone: string;
}

const CARTES: Carte[] = [
  { cle: 'en_cours', label: 'EER en cours', statut: null, tone: 'INFO' },
  { cle: 'a_affecter', label: 'À affecter', statut: 'A_AFFECTER', tone: 'ATTENTION' },
  { cle: 'en_controle', label: 'En contrôle', statut: 'EN_CONTROLE', tone: 'INFO' },
  { cle: 'non_conformes', label: 'Non conformes', statut: 'NON_CONFORME', tone: 'CRITIQUE' },
  { cle: 'a_completer', label: 'À compléter', statut: 'A_COMPLETER', tone: 'ATTENTION' },
  { cle: 'conformes', label: 'Conformes', statut: 'CONFORME', tone: 'ACTIF' },
  { cle: 'avis_en_attente', label: 'Avis KYC en attente', statut: 'AVIS_CONFORMITE', tone: 'ATTENTION' },
  { cle: 'valides', label: 'Validés', statut: 'VALIDE', tone: 'ACTIF' },
];

@Component({
  selector: 'bea-eer-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Conformité &amp; sécurité financière · KYC</p>
          <h1>Gestion des entrées en relation</h1>
          <p class="bea-ct-head__sub">
            Suivi des dossiers EER : contrôle, compléments, avis Conformité KYC et validation.
            @if (perimetre(); as p) {
              <span class="bea-ct-badge" [attr.data-tone]="p.perimetre === 'TOUTES_AGENCES' ? 'INFO' : 'ATTENTION'">
                Périmètre : {{ p.perimetre === 'TOUTES_AGENCES' ? 'toutes les agences' : p.perimetre === 'AGENCE' ? 'votre agence' : 'aucune agence' }}
              </span>
            }
          </p>
        </div>
        <div class="bea-mg__actions">
          @if (agences().length > 1) {
            <label class="bea-mg__field">Agence
              <select [value]="agenceId()" (change)="choisirAgence($any($event.target).value)">
                <option value="">Toutes</option>
                @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
              </select>
            </label>
          }
          @if (perimetre()?.capacites?.['creation']) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/eer/dossiers/nouveau"><mat-icon>person_add</mat-icon> Nouvelle EER</a>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Actualiser" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      @if (kpi(); as k) {
        <article class="bea-mg__panel eer-panel eer-conf">
          <div class="eer-conf__head">
            <div>
              <h2>Conformité du flux</h2>
              <p class="bea-ct-note">
                Taux = conformes / (conformes + non conformes). Les dossiers non évalués et abandonnés n’entrent pas dans le taux.
              </p>
            </div>
            <label class="bea-mg__field">Référence
              <select [value]="reference()" (change)="reference.set($any($event.target).value)">
                <option value="excel">Excel historique (physique + données systèmes)</option>
                <option value="bea">BEA-DIGITAL (+ cohérence, anomalies bloquantes)</option>
              </select>
            </label>
            @if (perimetre()?.capacites?.['export'] && perimetre()?.capacites?.['reporting']) {
              <div class="bea-mg__actions">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Synthèse (gabarit Feuil2) en PDF" [disabled]="exportEnCours()" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Synthèse (gabarit Feuil2) en Excel" [disabled]="exportEnCours()" (click)="exporter('xlsx')"><mat-icon>table_chart</mat-icon> Excel</button>
              </div>
            }
          </div>
          <div class="bea-nf-kpi">
            <a class="bea-nf-kpi__card eer-kpi" routerLink="/eer/dossiers" [queryParams]="lienConformite('')"><p>Total EER</p><strong>{{ k[reference()].total }}</strong></a>
            <a class="bea-nf-kpi__card eer-kpi" data-tone="ACTIF" routerLink="/eer/dossiers" [queryParams]="lienConformite('CONFORME')"><p>Conformes</p><strong>{{ k[reference()].conformes }}</strong></a>
            <a class="bea-nf-kpi__card eer-kpi" data-tone="CRITIQUE" routerLink="/eer/dossiers" [queryParams]="lienConformite('NON_CONFORME')"><p>Non conformes</p><strong>{{ k[reference()].non_conformes }}</strong></a>
            <a class="bea-nf-kpi__card eer-kpi" routerLink="/eer/dossiers" [queryParams]="lienConformite('NON_EVALUE')"><p>Non évalués</p><strong>{{ k[reference()].non_evalues }}</strong></a>
            <div class="bea-nf-kpi__card eer-kpi" data-tone="INFO"><p>Taux de conformité</p><strong>{{ taux(k[reference()].taux) }}</strong></div>
            @if (k.divergences) {
              <div class="bea-nf-kpi__card eer-kpi" data-tone="ATTENTION" title="Dossiers dont la référence Excel et la décision BEA-DIGITAL diffèrent">
                <p>Écarts Excel / BEA-DIGITAL</p><strong>{{ k.divergences }}</strong>
              </div>
            }
          </div>
          <h3 class="eer-sub">Flux des dossiers</h3>
          <div class="bea-nf-kpi">
            <div class="bea-nf-kpi__card eer-kpi"><p>Reçus</p><strong>{{ k.flux.recus }}</strong></div>
            <div class="bea-nf-kpi__card eer-kpi"><p>En cours</p><strong>{{ k.flux.en_cours }}</strong></div>
            <div class="bea-nf-kpi__card eer-kpi" data-tone="ATTENTION"><p>À compléter</p><strong>{{ k.flux.a_completer }}</strong></div>
            <div class="bea-nf-kpi__card eer-kpi"><p>Abandonnés</p><strong>{{ k.flux.abandonnes }}</strong></div>
            <div class="bea-nf-kpi__card eer-kpi" title="Abandonnés après réception / dossiers reçus"><p>Taux d’abandon</p><strong>{{ taux(k.flux.taux_abandon) }}</strong></div>
          </div>
        </article>

        <div class="eer-grid">
          @for (t of tableaux(); track t.titre) {
            <article class="bea-mg__panel eer-panel">
              <h2>{{ t.titre }}</h2>
              <div class="bea-mg__table-scroll">
                <table class="bea-mg__table bea-ct-table eer-table">
                  <thead><tr><th>{{ t.colonne }}</th><th>Total</th><th>Conformes</th><th>Non conf.</th><th>Non éval.</th><th>Taux</th></tr></thead>
                  <tbody>
                    @for (l of t.data.lignes; track $index) {
                      <tr>
                        <td>{{ l.libelle || 'Non renseigné' }}@if (l.profil_technique) { <small class="bea-ct-sub">{{ l.profil_technique }}</small> }</td>
                        <td>{{ l[reference()].total }}</td><td>{{ l[reference()].conformes }}</td>
                        <td>{{ l[reference()].non_conformes }}</td><td>{{ l[reference()].non_evalues }}</td>
                        <td><strong>{{ taux(l[reference()].taux) }}</strong></td>
                      </tr>
                    }
                    <tr class="eer-table__total">
                      <td>Total</td><td>{{ t.data.total[reference()].total }}</td><td>{{ t.data.total[reference()].conformes }}</td>
                      <td>{{ t.data.total[reference()].non_conformes }}</td><td>{{ t.data.total[reference()].non_evalues }}</td>
                      <td>{{ taux(t.data.total[reference()].taux) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </article>
          }
          @if (etats(); as e) {
            <article class="bea-mg__panel eer-panel">
              <h2>État des comptes</h2>
              <table class="bea-mg__table bea-ct-table eer-table">
                <thead><tr><th>État</th><th>Nombre</th><th>% total</th></tr></thead>
                <tbody>
                  @for (l of e.lignes; track l.code) {
                    <tr><td>{{ l.libelle }}</td><td>{{ l.nombre }}</td><td>{{ taux(l.pourcentage) }}</td></tr>
                  }
                  <tr class="eer-table__total"><td>Total</td><td>{{ e.total }}</td><td>{{ e.total ? '100 %' : '—' }}</td></tr>
                </tbody>
              </table>
              @if (e.non_renseignes) { <p class="bea-ct-note">{{ e.non_renseignes }} dossier(s) sans état de compte (hors total).</p> }
            </article>
          }
        </div>

        <article class="bea-mg__panel eer-panel eer-ext">
          <div class="eer-conf__head">
            <div>
              <h2>Analyses complémentaires</h2>
              <p class="bea-ct-note">Fonctionnalités BEA-DIGITAL, absentes de la synthèse Excel historique.</p>
            </div>
            <div class="bea-mg__actions">
              <label class="bea-mg__field">Période
                <select [value]="granularite()" (change)="choisirGranularite($any($event.target).value)">
                  <option value="jour">Jour</option><option value="semaine">Semaine</option>
                  <option value="mois">Mois</option><option value="annee">Année</option>
                </select>
              </label>
              <label class="bea-mg__field">Dimension
                <select [value]="dimension()" (change)="choisirDimension($any($event.target).value)">
                  @for (d of dimensions; track d[0]) { <option [value]="d[0]">{{ d[1] }}</option> }
                </select>
              </label>
            </div>
          </div>
          <div class="eer-grid">
            @if (serie(); as s) {
              <div>
                <h3 class="eer-sub">Par période (date EER)</h3>
                @for (l of s.lignes; track l.periode) {
                  <div class="eer-bar">
                    <span class="eer-bar__label">{{ periode(l.periode) }}</span>
                    <span class="eer-bar__track"><span class="eer-bar__fill" [style.width.%]="tauxNum(l[reference()].taux)"></span></span>
                    <strong>{{ taux(l[reference()].taux) }}</strong>
                  </div>
                } @empty { <p class="bea-ct-note">Aucun dossier.</p> }
              </div>
            }
            @if (parDimension(); as dim) {
              <div>
                <h3 class="eer-sub">Par {{ libelleDimension() }}</h3>
                @for (l of dim.lignes; track $index) {
                  <div class="eer-bar">
                    <span class="eer-bar__label">{{ l.libelle }}</span>
                    <span class="eer-bar__track"><span class="eer-bar__fill" [style.width.%]="tauxNum(l[reference()].taux)"></span></span>
                    <strong>{{ taux(l[reference()].taux) }} · {{ l.total }}</strong>
                  </div>
                } @empty { <p class="bea-ct-note">Aucun dossier.</p> }
              </div>
            }
          </div>
        </article>
        <h2 class="eer-section">Suivi du workflow</h2>
      }

      @if (tdb(); as t) {
        <div class="bea-nf-kpi">
          @for (c of cartes; track c.cle) {
            <a class="bea-nf-kpi__card eer-kpi" [attr.data-tone]="c.tone" routerLink="/eer/dossiers" [queryParams]="lien(c)">
              <p>{{ c.label }}</p>
              <strong>{{ t[c.cle] }}</strong>
            </a>
          }
          <div class="bea-nf-kpi__card eer-kpi">
            <p>Délai moyen de traitement</p>
            <strong>{{ t.delai_moyen_jours === null ? '—' : t.delai_moyen_jours + ' j' }}</strong>
          </div>
        </div>

        <div class="eer-grid">
          @for (bloc of blocs(); track bloc.titre) {
            <article class="bea-mg__panel eer-panel">
              <h2>{{ bloc.titre }}</h2>
              @for (r of bloc.lignes; track r.code) {
                <div class="eer-bar">
                  <span class="eer-bar__label">{{ bloc.libelle(r) }}</span>
                  <span class="eer-bar__track"><span class="eer-bar__fill" [style.width.%]="pct(r.total, t.total)"></span></span>
                  <strong>{{ r.total }}</strong>
                </div>
              } @empty {
                <p class="bea-ct-note">Aucun dossier.</p>
              }
            </article>
          }
        </div>
        <p class="bea-ct-count">{{ t.total }} dossier{{ t.total > 1 ? 's' : '' }} · {{ t.brouillons }} brouillon{{ t.brouillons > 1 ? 's' : '' }} · {{ t.abandonnes }} abandonné{{ t.abandonnes > 1 ? 's' : '' }}</p>
      } @else if (!erreur()) {
        <div class="bea-ct-empty"><mat-icon>hourglass_empty</mat-icon><p>Chargement…</p></div>
      }
    </section>
  `,
  styles: [`
    .eer-kpi { text-decoration: none; color: inherit; }
    .eer-kpi[data-tone='CRITIQUE'] strong { color: #b91c1c; }
    .eer-kpi[data-tone='ATTENTION'] strong { color: #c2410c; }
    .eer-kpi[data-tone='ACTIF'] strong { color: #0f766e; }
    .eer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 1rem; margin-top: 1rem; }
    .eer-panel { padding: 1rem 1.1rem; }
    .eer-panel h2 { margin: 0 0 0.75rem; font-size: 0.95rem; color: #0f172a; }
    .eer-bar { display: grid; grid-template-columns: minmax(7rem, 1fr) 2fr auto; align-items: center; gap: 0.6rem; margin: 0.35rem 0; font-size: 0.84rem; }
    .eer-bar__label { color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .eer-bar__track { height: 0.5rem; border-radius: 999px; background: #eef2f7; overflow: hidden; }
    .eer-bar__fill { display: block; height: 100%; background: linear-gradient(90deg, #1a5278, #14b8a6); }
    .eer-conf, .eer-ext { margin-bottom: 1rem; }
    .eer-conf__head { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.75rem; }
    .eer-conf__head h2 { margin: 0 0 0.25rem; }
    .eer-sub { margin: 1rem 0 0.5rem; font-size: 0.85rem; color: #475569; font-weight: 600; }
    .eer-section { margin: 1.5rem 0 0.75rem; font-size: 1rem; color: #0f172a; }
    .eer-table td, .eer-table th { font-size: 0.82rem; }
    .eer-table__total td { font-weight: 700; border-top: 2px solid #e2e8f0; }
  `],
})
export class EerDashboardComponent implements OnInit {
  private readonly eer = inject(EerService);
  private readonly feedback = inject(FeedbackService);

  readonly cartes = CARTES;
  readonly perimetre = signal<EerPerimetre | null>(null);
  readonly tdb = signal<EerTableauDeBord | null>(null);
  readonly agences = signal<EerAgence[]>([]);
  readonly agenceId = signal('');
  readonly erreur = signal(false);

  readonly dimensions = DIMENSIONS;
  readonly reference = signal<'excel' | 'bea'>('excel');
  readonly kpi = signal<EerKpiGlobal | null>(null);
  readonly parAgence = signal<EerKpiRepartition | null>(null);
  readonly parProfil = signal<EerKpiRepartition | null>(null);
  readonly etats = signal<EerKpiEtatsCompte | null>(null);
  readonly serie = signal<EerKpiSerie | null>(null);
  readonly parDimension = signal<EerKpiRepartition | null>(null);
  readonly granularite = signal<EerGranularite>('mois');
  readonly dimension = signal<EerDimension>('risque');
  readonly exportEnCours = signal(false);

  readonly tableaux = computed(() => {
    const a = this.parAgence();
    const p = this.parProfil();
    return [
      ...(a ? [{ titre: 'Conformité par agence', colonne: 'Agence', data: a }] : []),
      ...(p ? [{ titre: 'Conformité par profil', colonne: 'Profil', data: p }] : []),
    ];
  });
  readonly libelleDimension = computed(() => DIMENSIONS.find((d) => d[0] === this.dimension())?.[1] ?? '');

  readonly blocs = computed(() => {
    const t = this.tdb();
    if (!t) return [];
    const parCode = (r: EerRepartition) => r.libelle || r.code || 'Non renseigné';
    return [
      { titre: 'Répartition par agence', lignes: t.par_agence, libelle: (r: EerRepartition) => `${r.code ?? '—'} — ${r.libelle ?? ''}` },
      { titre: 'Répartition par type de client', lignes: t.par_type_client, libelle: (r: EerRepartition) => libelle(TYPES_CLIENT, r.code) },
      { titre: 'Répartition par profil', lignes: t.par_profil, libelle: parCode },
      { titre: 'Répartition par niveau de risque', lignes: t.par_risque, libelle: (r: EerRepartition) => r.code || 'Non évalué' },
    ];
  });

  ngOnInit(): void {
    this.eer.perimetre().subscribe({ next: (p) => this.perimetre.set(p), error: (e) => this.fail(e) });
    this.eer.agences().subscribe({ next: (a) => this.agences.set(a), error: () => undefined });
    this.charger();
  }

  charger(): void {
    this.erreur.set(false);
    const f = { agence_id: this.agenceId() || undefined };
    const erreur = (e: unknown) => this.fail(e);
    this.eer.kpis(f).subscribe({ next: (k) => this.kpi.set(k), error: erreur });
    this.eer.kpisAgences(f).subscribe({ next: (r) => this.parAgence.set(r), error: erreur });
    this.eer.kpisProfils(f).subscribe({ next: (r) => this.parProfil.set(r), error: erreur });
    this.eer.kpisEtatsCompte(f).subscribe({ next: (r) => this.etats.set(r), error: erreur });
    this.chargerSerie();
    this.chargerDimension();
    this.eer.tableauDeBord(this.agenceId() || undefined).subscribe({
      next: (t) => this.tdb.set(t),
      error: (e) => {
        this.erreur.set(true);
        this.fail(e);
      },
    });
  }

  exporter(format: EerFormatExport): void {
    const ref = this.reference();
    this.feedback
      .run(() => this.eer.exporterSynthese({ agence_id: this.agenceId() || undefined }, format, ref), {
        loading: 'Génération du reporting…',
        success: () => ({ title: 'Reporting généré' }),
        busy: this.exportEnCours,
        retry: false,
        errorTitle: 'Export impossible',
      })
      .subscribe((blob) => telechargerBlob(blob, `eer-synthese-${ref}.${format}`));
  }

  choisirAgence(id: string): void {
    this.agenceId.set(id);
    this.charger();
  }

  lien(c: Carte): Record<string, string> {
    const q: Record<string, string> = {};
    if (c.statut) q['statut'] = c.statut;
    if (this.agenceId()) q['agence_id'] = this.agenceId();
    return q;
  }

  choisirGranularite(g: EerGranularite): void {
    this.granularite.set(g);
    this.chargerSerie();
  }

  choisirDimension(d: EerDimension): void {
    this.dimension.set(d);
    this.chargerDimension();
  }

  lienConformite(classement: string): Record<string, string> {
    const q: Record<string, string> = {};
    if (classement && this.reference() === 'excel') q['conformite_excel'] = classement;
    if (this.agenceId()) q['agence_id'] = this.agenceId();
    return q;
  }

  /** Taux non calculable (aucun dossier classé) : affiché « — », jamais 0 %. */
  taux(t: string | null): string {
    return t === null ? '—' : `${Number(t).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} %`;
  }

  tauxNum(t: string | null): number {
    return t === null ? 0 : Number(t);
  }

  periode(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    switch (this.granularite()) {
      case 'annee':
        return String(d.getFullYear());
      case 'mois':
        return d.toLocaleDateString('fr-FR', { month: 'short', year: 'numeric' });
      case 'semaine':
        return `Sem. du ${d.toLocaleDateString('fr-FR')}`;
      default:
        return d.toLocaleDateString('fr-FR');
    }
  }

  private chargerSerie(): void {
    this.eer.kpisSerie(this.granularite(), { agence_id: this.agenceId() || undefined }).subscribe({
      next: (s) => this.serie.set(s),
      error: (e) => this.fail(e),
    });
  }

  private chargerDimension(): void {
    this.eer.kpisDimension(this.dimension(), { agence_id: this.agenceId() || undefined }).subscribe({
      next: (r) => this.parDimension.set(r),
      error: (e) => this.fail(e),
    });
  }

  pct(n: number, total: number): number {
    return total ? Math.round((n / total) * 100) : 0;
  }

  private fail(err: unknown): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, 'Chargement impossible'));
  }
}
