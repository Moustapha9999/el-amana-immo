import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { TableauBord, montantFr } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcComparaisonComponent } from '../shared/rc-comparaison.component';
import { RcExportComponent } from '../shared/rc-export.component';

/** Rapports : volumes, comparaison de périodes, répartitions et exports. */
@Component({
  selector: 'bea-rc-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, RouterLink, ReclamationsUiComponent, RcExportComponent, RcComparaisonComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Rapports & statistiques</h1>
          <p class="bea-ct-head__sub">Calculés sur les dossiers de votre périmètre. Chaque nombre cliquable ouvre la liste exacte des dossiers comptés.</p>
        </div>
        <div class="bea-mg__actions">
          <bea-rc-export [filtres]="base()" />
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()" title="Actualiser" aria-label="Actualiser"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      <form class="bea-mg__search bea-ct-filters bea-rc-filters" (ngSubmit)="charger()">
        <label class="bea-mg__field">Agence du client
          <select [(ngModel)]="agence" name="agence" (change)="charger()">
            <option value="">Toutes</option>
            <option value="AUCUNE">Sans agence</option>
            @for (a of store.config()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Période du <input type="date" [(ngModel)]="debut" name="debut" /></label>
        <label class="bea-mg__field">au <input type="date" [(ngModel)]="fin" name="fin" /></label>
        <div class="bea-ct-filters__btns">
          <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Appliquer</button>
        </div>
      </form>

      @if (erreur()) {
        <div class="bea-ct-empty bea-ct-empty--hero"><mat-icon>cloud_off</mat-icon>
          <p>Impossible de charger les rapports.</p>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon> Réessayer</button>
        </div>
      } @else if (data(); as d) {
        <div class="bea-rc-kpis">
          <a class="bea-rc-kpi" routerLink="/reclamations/dossiers" [queryParams]="kpi('total')"><mat-icon>forum</mat-icon><p>Reçues</p><strong>{{ d.total }}</strong></a>
          <a class="bea-rc-kpi" routerLink="/reclamations/dossiers" [queryParams]="kpi('ouvertes')"><mat-icon>pending_actions</mat-icon><p>Ouvertes</p><strong>{{ d.ouvertes }}</strong></a>
          <a class="bea-rc-kpi" routerLink="/reclamations/dossiers" [queryParams]="kpi('operations')"><mat-icon>receipt_long</mat-icon><p>Opérations</p><strong>{{ d.nb_operations }}</strong><small>dans {{ d.dossiers_avec_operations }} dossier(s)</small></a>
          <a class="bea-rc-kpi" routerLink="/reclamations/dossiers" [queryParams]="kpi('operations')"><mat-icon>payments</mat-icon><p>Montant total</p><strong>{{ montant(d.montant_total, d.devise) }}</strong></a>
        </div>

        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Comparaison de deux périodes</h2><small class="bea-rc-hint">Agence : {{ agenceLibelle() }}</small></div>
          <div class="bea-rc-pad"><bea-rc-comparaison [filtres]="base()" /></div>
        </section>

        <div class="bea-rc-grid">
          @for (r of repartitions(); track r.titre) {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>{{ r.titre }}</h2></div>
              <ul class="bea-rc-bars">
                @for (c of r.items; track c.id) {
                  <li>
                    @if (r.param && c.id !== 'None') { <a [routerLink]="['/reclamations/dossiers']" [queryParams]="filtre(r.param, c.id)">{{ c.libelle }}</a> }
                    @else { <span>{{ c.id === 'None' ? 'Non renseigné' : c.libelle }}</span> }
                    <span><span class="bea-rc-bars__n">{{ c.n }}</span>@if (c.nb_operations) { <small class="bea-rc-hint"> · {{ montant(c.montant ?? null, d.devise) }}</small> }</span>
                  </li>
                } @empty { <li class="bea-rc-muted">Aucune donnée.</li> }
              </ul>
            </section>
          }
        </div>
      } @else {
        <p class="bea-rc-pad bea-rc-muted">Chargement des rapports…</p>
      }
    </section>
  `,
})
export class RcRapportsComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);

  readonly data = signal<TableauBord | null>(null);
  readonly erreur = signal(false);
  private readonly appliques = signal<Record<string, string | null>>({});
  agence = '';
  debut = '';
  fin = '';

  readonly base = computed(() => this.appliques());

  readonly agenceLibelle = computed(() => {
    const a = this.appliques()['client_agence_id'];
    if (!a) return 'toutes';
    if (a === 'AUCUNE') return 'sans agence';
    return this.store.config()?.agences.find((x) => x.id === a)?.libelle ?? '';
  });

  readonly repartitions = computed(() => {
    const d = this.data();
    if (!d) return [];
    return [
      { titre: 'Types', items: d.types, param: 'type_id' },
      { titre: 'Motifs', items: d.motifs, param: 'motif_id' },
      { titre: 'Agences', items: d.agences, param: 'client_agence_id' },
      { titre: 'Canaux', items: d.canaux, param: 'canal_id' },
      { titre: 'Unités de réception', items: d.unites_reception, param: 'unite_reception_id' },
      { titre: 'Services (traitement ou concerné)', items: d.services, param: '' },
    ];
  });

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    if (this.debut && this.fin && this.fin < this.debut) {
      this.feedback.warning({ title: 'Dates incohérentes', message: 'La date de fin précède la date de début.' });
      return;
    }
    this.appliques.set({ client_agence_id: this.agence || null, date_debut: this.debut || null, date_fin: this.fin || null });
    this.erreur.set(false);
    this.rc.tableauDeBord(this.base()).subscribe({
      next: (d) => this.data.set(d),
      error: (e) => {
        this.erreur.set(true);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Rapports indisponibles'));
      },
    });
  }

  kpi(code: string): Record<string, string | null> {
    return { ...(this.data()?.liens[code] ?? {}), client_agence_id: this.base()['client_agence_id'] ?? null };
  }

  filtre(param: string, id: string | undefined): Record<string, string | null> {
    return { ...this.base(), [param]: id ?? null };
  }

  montant(v: string | null, devise: string): string {
    return montantFr(v, devise);
  }
}
