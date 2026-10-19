import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateHeureFr } from '../clientele.models';
import { BADGE_SIC, RESULTATS_DEPOT } from './cl-sic.component';

interface Entree {
  id: string; famille: 'MENSUELLE' | 'SIC'; type: string; periode: string; date_reference: string | null;
  statut: string; statut_libelle?: string; cree_le: string | null; cree_par: string | null;
  generee_le: string | null; generee_par: string | null; ref_version: string | null;
  nb_candidats: number | null; nb_lignes: number | null; nb_bloquantes: number | null;
  nb_a_corriger: number | null; nb_avertissements: number | null; fichier_nom: string | null;
  depot_resultat?: string | null; lien: string;
}

@Component({
  selector: 'bea-cl-declarations-historique',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Déclarations BCM</p>
          <h1>Historique des déclarations</h1>
          <p class="bea-cl-head__sub">Déclarations mensuelles et SIC : période, statut, référentiel utilisé, volumes, anomalies et fichier. Chaque action est tracée dans le journal d’audit.</p>
        </div>
      </header>
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <h2>{{ visibles().length }} déclaration(s)</h2>
          <label class="bea-cl-hint" style="display:flex;align-items:center;gap:0.4rem">Type
            <select [ngModel]="filtre()" (ngModelChange)="filtre.set($event)" name="filtre">
              <option value="">Toutes</option>
              <option value="MENSUELLE">Déclaration mensuelle BCM</option>
              <option value="SIC">Déclaration SIC</option>
            </select>
          </label>
        </div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr>
              <th>Déclaration</th><th>Période</th><th>Statut</th><th>Référentiel / grille</th>
              <th style="text-align:right">Candidats</th><th style="text-align:right">Lignes</th><th>Anomalies</th>
              <th>Créée</th><th>Générée / validée</th><th>Fichier</th>
            </tr></thead>
            <tbody>
              @for (h of visibles(); track h.id) {
                <tr>
                  <td><a [routerLink]="h.lien"><strong>{{ h.type }}</strong></a></td>
                  <td>{{ h.periode }}</td>
                  <td>
                    <span class="bea-cl-badge" [attr.data-s]="h.famille === 'SIC' ? badge[h.statut] : h.statut">{{ h.statut_libelle ?? h.statut.replaceAll('_', ' ') }}</span>
                    @if (h.depot_resultat) { <br /><span class="bea-cl-hint">{{ resultats[h.depot_resultat] }}</span> }
                  </td>
                  <td>{{ h.ref_version ?? '—' }}</td>
                  <td style="text-align:right">{{ h.nb_candidats ?? '—' }}</td>
                  <td style="text-align:right">{{ h.nb_lignes ?? '—' }}</td>
                  <td class="bea-cl-hint">{{ h.nb_bloquantes === null ? '—' : h.nb_bloquantes + ' bloq. · ' + h.nb_a_corriger + ' à corr. · ' + h.nb_avertissements + ' avert.' }}</td>
                  <td>{{ dateHeureFr(h.cree_le) }}<br /><span class="bea-cl-hint">{{ h.cree_par ?? '—' }}</span></td>
                  <td>{{ dateHeureFr(h.generee_le) }}<br /><span class="bea-cl-hint">{{ h.generee_par ?? '' }}</span></td>
                  <td>{{ h.fichier_nom ?? '—' }}</td>
                </tr>
              } @empty {
                <tr><td colspan="10"><div class="bea-cl-empty">Aucune déclaration.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `,
})
export class ClDeclarationsHistoriqueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly liste = signal<Entree[]>([]);
  readonly filtre = signal('');
  readonly visibles = computed(() => (this.filtre() ? this.liste().filter((h) => h.famille === this.filtre()) : this.liste()));
  readonly dateHeureFr = dateHeureFr;
  readonly badge = BADGE_SIC;
  readonly resultats = RESULTATS_DEPOT;

  ngOnInit(): void {
    this.api.get<Entree[]>(`${CL_BASE}/declarations-historique`).subscribe({
      next: (d) => this.liste.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Historique indisponible')),
    });
  }
}
