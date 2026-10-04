import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { EerAgence, EerService } from './eer.service';
import { EerPerimetre, EerRepartition, EerTableauDeBord, TYPES_CLIENT, libelle } from './eer.models';

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
    this.eer.tableauDeBord(this.agenceId() || undefined).subscribe({
      next: (t) => this.tdb.set(t),
      error: (e) => {
        this.erreur.set(true);
        this.fail(e);
      },
    });
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

  pct(n: number, total: number): number {
    return total ? Math.round((n / total) * 100) : 0;
  }

  private fail(err: unknown): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, 'Chargement impossible'));
  }
}
