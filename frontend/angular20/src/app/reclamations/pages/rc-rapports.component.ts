import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { TableauBord, montantFr, telechargerBlob } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

/** Rapports : répartitions du périmètre et export Excel (plafond serveur 5 000 lignes). */
@Component({
  selector: 'bea-rc-rapports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, ReclamationsUiComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Rapports & statistiques</h1>
          <p class="bea-ct-head__sub">Répartitions calculées sur les dossiers de votre périmètre. L’export Excel est plafonné à 5 000 lignes.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap('reporting_exporter')) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="exporter()"><mat-icon>download</mat-icon> Exporter Excel</button>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      @if (erreur()) {
        <div class="bea-ct-empty bea-ct-empty--hero"><mat-icon>cloud_off</mat-icon>
          <p>Impossible de charger les rapports.</p>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon> Réessayer</button>
        </div>
      } @else if (data(); as d) {
        <div class="bea-rc-kpis">
          <div class="bea-rc-kpi"><mat-icon>forum</mat-icon><p>Total</p><strong>{{ d.total }}</strong></div>
          <div class="bea-rc-kpi"><mat-icon>pending_actions</mat-icon><p>Ouvertes</p><strong>{{ d.ouvertes }}</strong></div>
          <div class="bea-rc-kpi" data-tone="danger"><mat-icon>timer_off</mat-icon><p>Retards</p><strong>{{ d.retards }}</strong></div>
          <div class="bea-rc-kpi"><mat-icon>task_alt</mat-icon><p>Clôturées 30 j</p><strong>{{ d.cloturees_30j }}</strong></div>
          <div class="bea-rc-kpi"><mat-icon>receipt_long</mat-icon><p>Opérations</p><strong>{{ d.nb_operations }}</strong><small>dans {{ d.dossiers_avec_operations }} dossier(s)</small></div>
          <div class="bea-rc-kpi"><mat-icon>payments</mat-icon><p>Montant total</p><strong>{{ montant(d.montant_total, d.devise) }}</strong></div>
        </div>
        <div class="bea-rc-grid">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Types</h2></div>
            <ul class="bea-rc-bars">
              @for (t of d.types; track t.id) {
                <li><a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ type_id: t.id }">{{ t.libelle }}</a><span class="bea-rc-bars__n">{{ t.n }}</span></li>
              } @empty { <li class="bea-rc-muted">Aucun type renseigné.</li> }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Motifs</h2></div>
            <ul class="bea-rc-bars">
              @for (m of d.motifs; track m.id) {
                <li>
                  @if (m.id !== 'None') { <a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ motif_id: m.id }">{{ m.libelle }}</a> }
                  @else { <span>Non qualifié</span> }
                  <span><span class="bea-rc-bars__n">{{ m.n }}</span>@if (m.nb_operations) { <small class="bea-rc-hint"> · {{ montant(m.montant ?? null, d.devise) }}</small> }</span>
                </li>
              } @empty { <li class="bea-rc-muted">Aucun motif renseigné.</li> }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Agences</h2></div>
            <ul class="bea-rc-bars">
              @for (a of d.agences; track a.id) {
                <li>
                  @if (a.id !== 'None') { <a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ client_agence_id: a.id }">{{ a.libelle }}</a> }
                  @else { <span>Non renseignée</span> }
                  <span><span class="bea-rc-bars__n">{{ a.n }}</span>@if (a.nb_operations) { <small class="bea-rc-hint"> · {{ montant(a.montant ?? null, d.devise) }}</small> }</span>
                </li>
              } @empty { <li class="bea-rc-muted">Aucune agence renseignée.</li> }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Canaux</h2></div>
            <ul class="bea-rc-bars">
              @for (c of d.canaux; track c.id) {
                <li><a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ canal_id: c.id }">{{ c.libelle }}</a><span class="bea-rc-bars__n">{{ c.n }}</span></li>
              } @empty { <li class="bea-rc-muted">Aucun canal renseigné.</li> }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Unités de réception</h2></div>
            <ul class="bea-rc-bars">
              @for (u of d.unites_reception; track u.id) {
                <li><a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ unite_reception_id: u.id }">{{ u.libelle }}</a><span class="bea-rc-bars__n">{{ u.n }}</span></li>
              } @empty { <li class="bea-rc-muted">Aucune unité de réception.</li> }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Services</h2></div>
            <ul class="bea-rc-bars">
              @for (u of d.services; track u.id) {
                <li><span>{{ u.id === 'None' ? 'Non déterminé' : u.libelle }}</span><span class="bea-rc-bars__n">{{ u.n }}</span></li>
              } @empty { <li class="bea-rc-muted">Aucun service.</li> }
            </ul>
          </section>
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
  readonly busy = signal(false);

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    this.erreur.set(false);
    this.rc.tableauDeBord().subscribe({
      next: (d) => this.data.set(d),
      error: (e) => {
        this.erreur.set(true);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Rapports indisponibles'));
      },
    });
  }

  montant(v: string | null, devise: string): string {
    return montantFr(v, devise);
  }

  exporter(): void {
    this.feedback
      .run(() => this.rc.exporter(), {
        busy: this.busy, loading: 'Préparation de l’export…',
        success: () => ({ title: 'Export prêt' }),
        errorTitle: 'Export refusé', retry: false,
      })
      .subscribe((b) => telechargerBlob(b, `reclamations-${new Date().toISOString().slice(0, 10)}.xlsx`));
  }
}
