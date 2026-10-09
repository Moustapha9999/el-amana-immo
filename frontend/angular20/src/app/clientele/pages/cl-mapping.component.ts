import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import {
  AnomaliePage, CL_BASE, ETAT_MAPPING, SourceColonne, TableauBord, dateFr, etatMapping, n,
} from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

@Component({
  selector: 'bea-cl-mapping',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <p class="bea-stock-page__kicker">Imports &amp; qualité des données</p>
          <h1>Mapping &amp; sources</h1>
          <p class="bea-cl-head__sub">Règles appliquées à la situation client. Un champ dérivé ou partiel n’est pas présenté comme une colonne brute ORION. Version {{ version() }}.</p>
        </div>
      </header>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Colonnes Situation</h2></div>
        <p class="bea-cl-hint" style="padding:0 1.1rem">Date de vérification : non enregistrée. La version ci-dessus est celle du catalogue de règles dans l’application.</p>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Colonne métier</th>
                <th>Colonne ORION</th>
                <th>Règle</th>
                <th>État</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              @for (s of sources(); track s.colonne) {
                <tr>
                  <td><strong>{{ s.colonne }}</strong></td>
                  <td>{{ s.colonne_orion || '—' }}</td>
                  <td>{{ s.detail }}</td>
                  <td><span class="bea-cl-badge" [attr.data-s]="etat(s)">{{ libelle(s) }}</span></td>
                  <td>{{ s.version_regle || version() }}</td>
                </tr>
              } @empty {
                <tr><td colspan="5"><div class="bea-cl-empty">Catalogue de mapping indisponible.</div></td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>

      <section class="bea-mg__panel" id="qualite">
        <div class="bea-mg__panel-top">
          <h2>Valeurs rejetées</h2>
          @if (store.cap().imports_voir) {
            <a routerLink="/clientele/imports">Ouvrir les imports</a>
          }
        </div>
        @if (!store.cap().imports_voir) {
          <p class="bea-cl-hint" style="padding:0 1.1rem 1rem">La consultation des rejets demande le droit de voir les imports.</p>
        } @else if (!importId()) {
          <p class="bea-cl-hint" style="padding:0 1.1rem 1rem">Aucun import ORION pour rattacher des rejets.</p>
        } @else {
          <p class="bea-cl-hint" style="padding:0 1.1rem">Dernier traitement : {{ dernier()?.fichier_nom }} · {{ n(dernier()?.nb_rejets) }} rejets · {{ n(dernier()?.nb_anomalies) }} anomalies. Extraction {{ dateFr(dernier()?.date_extraction) }}.</p>
          <ul class="bea-cl-anoms">
            @for (x of rejets(); track $index) {
              <li [attr.data-n]="x.bloquante ? 'bloquant' : 'alerte'">
                <mat-icon>{{ x.bloquante ? 'block' : 'warning' }}</mat-icon>
                <span>@if (x.numero) { <b>Ligne {{ x.numero }} :</b> }{{ x.message }}</span>
              </li>
            } @empty {
              <li data-n="info"><mat-icon>check</mat-icon><span>Aucun rejet chargé pour ce traitement.</span></li>
            }
          </ul>
        }
      </section>
    </div>
  `,
})
export class ClMappingComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly bord = signal<TableauBord | null>(null);
  readonly rejets = signal<AnomaliePage['items']>([]);
  readonly dateFr = dateFr;
  readonly n = n;

  readonly sources = computed(() => this.store.config()?.sources ?? this.bord()?.sources ?? []);
  readonly version = computed(() => this.sources()[0]?.version_regle || '2026.10.situation.1');
  readonly dernier = computed(() => this.bord()?.dernier_import ?? null);
  readonly importId = computed(() => this.dernier()?.id ?? null);
  private rejetsDemandes = false;

  constructor() {
    effect(() => {
      const id = this.importId();
      if (id && this.store.cap().imports_voir && !this.rejetsDemandes) {
        this.rejetsDemandes = true;
        this.chargerRejets(id);
      }
    });
  }

  ngOnInit(): void {
    this.store.charger();
    this.api.get<TableauBord>(`${CL_BASE}/tableau-de-bord`).subscribe({
      next: (d) => this.bord.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Mapping indisponible')),
    });
  }

  etat(s: SourceColonne): string {
    return etatMapping(s);
  }

  libelle(s: SourceColonne): string {
    return ETAT_MAPPING[etatMapping(s)] ?? etatMapping(s);
  }

  private chargerRejets(id: string): void {
    this.api.get<AnomaliePage>(`${CL_BASE}/imports/${id}/anomalies`, { taille: 40 }).subscribe({
      next: (p) => this.rejets.set(p.items),
      error: () => this.rejets.set([]),
    });
  }
}
