import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { Comparaison, LigneComparaison, dateFr, montantFr, telechargerBlob } from '../reclamations.models';
import { Periodes, ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { ParamsListe } from './rc-pilotage.component';

function jourIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function decale(jours: number): Date {
  const d = new Date();
  d.setDate(d.getDate() - jours);
  return d;
}

/** Comparaison de deux périodes (A = référence, B = période comparée), mêmes filtres que la page. */
@Component({
  selector: 'bea-rc-comparaison',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, RouterLink],
  styleUrl: './rc-pilotage.component.css',
  styles: `
    .rcc-form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 0.6rem 1rem; margin-bottom: 0.8rem; }
    .rcc-form fieldset { display: flex; gap: 0.5rem; margin: 0; padding: 0.5rem 0.7rem 0.6rem; border: 1px solid #e2e8f0; border-radius: 0.7rem; }
    .rcc-form legend { padding: 0 0.3rem; font-size: 0.72rem; font-weight: 700; color: var(--rc); text-transform: uppercase; }
    .rcc-form label { display: flex; flex-direction: column; gap: 0.15rem; font-size: 0.72rem; color: #64748b; }
    .rcc-form input { padding: 0.35rem 0.45rem; border: 1px solid #cbd5e1; border-radius: 0.45rem; font: inherit; font-size: 0.82rem; }
    .rcc-actions { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .rcc-avert { display: flex; gap: 0.4rem; align-items: flex-start; margin: 0 0 0.6rem; padding: 0.5rem 0.7rem; border-radius: 0.6rem; background: #fff7ed; color: var(--warn); font-size: 0.8rem; }
    .rcc-avert mat-icon { width: 1.1rem; height: 1.1rem; font-size: 1.1rem; flex: none; }
    .rcc-tend { display: inline-flex; align-items: center; gap: 0.2rem; padding: 0.1rem 0.45rem; border-radius: 999px; font-size: 0.72rem; font-weight: 700; white-space: nowrap; }
    .rcc-tend[data-f='ok'] { background: #dcfce7; color: var(--ok); }
    .rcc-tend[data-f='ko'] { background: #fee2e2; color: var(--ko); }
    .rcc-tend[data-f='na'] { background: #f1f5f9; color: #64748b; font-weight: 500; }
    .rcc-tend mat-icon { width: 0.95rem; height: 0.95rem; font-size: 0.95rem; }
    .rcc-sub { display: block; font-size: 0.68rem; color: #94a3b8; font-weight: 400; }
  `,
  template: `
    <form class="rcc-form" (ngSubmit)="comparer()">
      <fieldset>
        <legend>Période A (référence)</legend>
        <label>Du <input type="date" [(ngModel)]="aDebut" name="a_debut" required /></label>
        <label>au <input type="date" [(ngModel)]="aFin" name="a_fin" required /></label>
      </fieldset>
      <fieldset>
        <legend>Période B (comparée)</legend>
        <label>Du <input type="date" [(ngModel)]="bDebut" name="b_debut" required /></label>
        <label>au <input type="date" [(ngModel)]="bFin" name="b_fin" required /></label>
      </fieldset>
      <div class="rcc-actions">
        <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>compare_arrows</mat-icon> Comparer</button>
        @if (resultat() && store.cap('reporting_exporter')) {
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporter('pdf')"><mat-icon>picture_as_pdf</mat-icon> PDF</button>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporter('xlsx')"><mat-icon>table_view</mat-icon> Excel</button>
        }
      </div>
    </form>

    @if (resultat(); as r) {
      @for (a of r.avertissements; track a) {
        <p class="rcc-avert"><mat-icon>warning</mat-icon> {{ a }}</p>
      }
      <div class="rcp-table">
        <table>
          <thead><tr>
            <th>Indicateur</th>
            <th>A<span class="rcc-sub">{{ date(r.a.debut) }} – {{ date(r.a.fin) }} ({{ r.a.jours }} j)</span></th>
            <th>B<span class="rcc-sub">{{ date(r.b.debut) }} – {{ date(r.b.fin) }} ({{ r.b.jours }} j)</span></th>
            <th>Écart B − A</th><th>Variation</th><th>Appréciation</th>
          </tr></thead>
          <tbody>
            @for (l of r.lignes; track l.code) {
              <tr>
                <td>{{ l.libelle }}</td>
                <td><a routerLink="/reclamations/dossiers" [queryParams]="lien(l, r.a.debut, r.a.fin)">{{ valeur(l, l.a) }}</a></td>
                <td><a routerLink="/reclamations/dossiers" [queryParams]="lien(l, r.b.debut, r.b.fin)">{{ valeur(l, l.b) }}</a></td>
                <td>{{ l.ecart === null ? 'N/A' : (l.ecart > 0 ? '+' : '') + valeur(l, l.ecart) }}</td>
                <td>{{ l.variation === null ? 'N/A' : (l.variation > 0 ? '+' : '') + l.variation + ' %' }}</td>
                <td>
                  @if (l.favorable === true) { <span class="rcc-tend" data-f="ok"><mat-icon>thumb_up</mat-icon> Favorable</span> }
                  @else if (l.favorable === false) { <span class="rcc-tend" data-f="ko"><mat-icon>thumb_down</mat-icon> Défavorable</span> }
                  @else { <span class="rcc-tend" data-f="na">{{ l.ecart === null ? 'N/A' : l.sens ? 'Stable' : 'Sens non défini' }}</span> }
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      <p class="rcp-formule">Variation = (B − A) ÷ A × 100, « N/A » quand A vaut 0. Une appréciation n’est donnée que si le sens favorable de l’indicateur est défini (volumes : non défini). Délais en heures.</p>
    }
  `,
})
export class RcComparaisonComponent {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);
  /** Filtres de la page (agence…) appliqués aux deux périodes. */
  readonly filtres = input<ParamsListe>({});

  readonly resultat = signal<Comparaison | null>(null);
  readonly busy = signal(false);
  aDebut = jourIso(decale(59));
  aFin = jourIso(decale(30));
  bDebut = jourIso(decale(29));
  bFin = jourIso(new Date());

  private periodes(): Periodes | null {
    const p = { a_debut: this.aDebut, a_fin: this.aFin, b_debut: this.bDebut, b_fin: this.bFin };
    if (!p.a_debut || !p.a_fin || !p.b_debut || !p.b_fin) {
      this.feedback.warning({ title: 'Périodes incomplètes', message: 'Indiquez le début et la fin des deux périodes.' });
      return null;
    }
    if (p.a_fin < p.a_debut || p.b_fin < p.b_debut) {
      this.feedback.warning({ title: 'Dates incohérentes', message: 'La fin d’une période précède son début.' });
      return null;
    }
    return p;
  }

  comparer(): void {
    const p = this.periodes();
    if (!p) return;
    this.feedback
      .run(() => this.rc.comparaison(p, this.filtres()), {
        busy: this.busy, success: () => null, errorTitle: 'Comparaison impossible', retry: false,
      })
      .subscribe((r) => this.resultat.set(r));
  }

  exporter(format: 'pdf' | 'xlsx'): void {
    const p = this.periodes();
    if (!p) return;
    this.feedback
      .run(() => this.rc.exportComparaison(p, this.filtres(), format), {
        busy: this.busy, loading: 'Préparation du fichier…',
        success: () => ({ title: 'Export de la comparaison prêt' }),
        errorTitle: 'Export refusé', retry: false,
      })
      .subscribe((b) => telechargerBlob(b, `comparaison-reclamations-${p.a_debut}-${p.b_debut}.${format}`));
  }

  valeur(l: LigneComparaison, v: number | string | null): string {
    if (v === null || v === undefined) return 'N/A';
    const n = typeof v === 'number' ? v : Number(v);
    if (!Number.isFinite(n)) return 'N/A';
    if (l.unite === '%') return `${n} %`;
    if (l.unite === 'heures') return `${n} h`;
    if (l.code === 'montant') return montantFr(n);
    return String(n);
  }

  lien(l: LigneComparaison, debut: string, fin: string): ParamsListe {
    const base = { client_agence_id: this.filtres()['client_agence_id'] ?? null };
    if (l.indicateur) return { ...base, indicateur: l.indicateur, kpi_debut: debut, kpi_fin: fin };
    if (l.code === 'recues') return { ...base, date_debut: debut, date_fin: fin };
    return { ...base, indicateur: 'avec_operations', date_debut: debut, date_fin: fin };
  }

  date(iso: string): string {
    return dateFr(iso);
  }
}
