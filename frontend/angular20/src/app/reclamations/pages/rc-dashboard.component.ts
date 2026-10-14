import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { TableauBord, dateFr, telechargerBlob, tonePriorite, toneStatut } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

/** Tableau de bord 360° : volumes, retards et files du périmètre, sans donnée inventée. */
@Component({
  selector: 'bea-rc-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, ReclamationsUiComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Tableau de bord 360°</h1>
          <p class="bea-ct-head__sub">Stock ouvert, retards et volumes des 30 derniers jours, dans votre périmètre.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap('creer')) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/reclamations/dossiers/nouvelle"><mat-icon>add_comment</mat-icon> Nouvelle réclamation</a>
          }
          @if (store.cap('reporting_exporter')) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exporter()"><mat-icon>download</mat-icon> Exporter Excel</button>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      @if (erreur()) {
        <div class="bea-ct-empty bea-ct-empty--hero"><mat-icon>cloud_off</mat-icon>
          <p>Impossible de charger le tableau de bord.</p>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon> Réessayer</button>
        </div>
      } @else if (data(); as d) {
        <div class="bea-rc-kpis">
          <a class="bea-rc-kpi" routerLink="/reclamations/dossiers">
            <mat-icon>forum</mat-icon><p>Total</p><strong>{{ d.total }}</strong>
            <small>dans le périmètre</small>
          </a>
          <a class="bea-rc-kpi" routerLink="/reclamations/dossiers" [queryParams]="{ ouvertes: 'true' }">
            <mat-icon>pending_actions</mat-icon><p>Ouvertes</p><strong>{{ d.ouvertes }}</strong>
            <small>hors clôturées / refusées / annulées</small>
          </a>
          <a class="bea-rc-kpi" data-tone="danger" routerLink="/reclamations/dossiers" [queryParams]="{ en_retard: 'true' }">
            <mat-icon>timer_off</mat-icon><p>En retard</p><strong>{{ d.retards }}</strong>
            <small>échéance dépassée</small>
          </a>
          <a class="bea-rc-kpi" data-tone="warn" routerLink="/reclamations/dossiers" [queryParams]="{ sans_echeance: 'true', ouvertes: 'true' }">
            <mat-icon>event_busy</mat-icon><p>Sans échéance</p><strong>{{ d.sans_echeance }}</strong>
            <small>aucune règle applicable</small>
          </a>
          <div class="bea-rc-kpi">
            <mat-icon>calendar_month</mat-icon><p>Reçues 30 j</p><strong>{{ d.volume_30j }}</strong>
            <small>{{ d.cloturees_30j }} clôturée(s) sur la période</small>
          </div>
        </div>

        <div class="bea-rc-grid">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par statut simplifié</h2></div>
            <ul class="bea-rc-bars">
              @for (g of d.groupes; track g.code) {
                <li>
                  <a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ groupe: g.code }">{{ g.libelle }}</a>
                  <span class="bea-rc-bars__n">{{ g.n }}</span>
                </li>
              }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par étape du circuit</h2></div>
            <ul class="bea-rc-bars">
              @for (e of d.etapes; track e.code) {
                <li>
                  <a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ etape: e.code }">{{ e.libelle }}</a>
                  <span class="bea-rc-bars__n">{{ e.n }}</span>
                </li>
              }
            </ul>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Par priorité</h2></div>
            <ul class="bea-rc-bars">
              @for (p of d.priorites; track p.code) {
                <li>
                  <a [routerLink]="['/reclamations/dossiers']" [queryParams]="{ priorite: p.code }">{{ p.libelle }}</a>
                  <span class="bea-rc-bars__n">{{ p.n }}</span>
                </li>
              }
            </ul>
          </section>
        </div>

        <div class="bea-rc-grid">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Dossiers en retard</h2>
              <a class="bea-ct-link" routerLink="/reclamations/delais">Voir les alertes</a>
            </div>
            @if (d.dossiers_retard.length) {
              <ul class="bea-rc-mini">
                @for (r of d.dossiers_retard; track r.id) {
                  <li>
                    <a class="bea-rc-mini__row" [routerLink]="['/reclamations/dossiers', r.id]">
                      <code>{{ r.reference }}</code>
                      <span class="bea-rc-mini__obj">{{ r.objet }}</span>
                      <span class="bea-ct-badge" [attr.data-tone]="toneStatut(r.statut)">{{ r.statut_libelle }}</span>
                      <small>{{ date(r.echeance) }}</small>
                    </a>
                  </li>
                }
              </ul>
            } @else {
              <p class="bea-rc-pad bea-rc-muted">Aucun dossier ouvert en retard dans votre périmètre.</p>
            }
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Derniers dossiers</h2>
              <a class="bea-ct-link" routerLink="/reclamations/dossiers">Toutes les réclamations</a>
            </div>
            @if (d.recents.length) {
              <ul class="bea-rc-mini">
                @for (r of d.recents; track r.id) {
                  <li>
                    <a class="bea-rc-mini__row" [routerLink]="['/reclamations/dossiers', r.id]">
                      <code>{{ r.reference }}</code>
                      <span class="bea-rc-mini__obj">{{ r.objet }}</span>
                      <span class="bea-ct-badge" [attr.data-tone]="toneStatut(r.statut)">{{ r.statut_libelle }}</span>
                      <span class="bea-ct-badge" [attr.data-tone]="tonePriorite(r.priorite)">{{ r.priorite_libelle }}</span>
                      <small>{{ date(r.date_premiere_reception) }}</small>
                    </a>
                  </li>
                }
              </ul>
            } @else {
              <p class="bea-rc-pad bea-rc-muted">Aucune réclamation dans votre périmètre.</p>
            }
          </section>
        </div>
      } @else {
        <p class="bea-rc-pad bea-rc-muted">Chargement du tableau de bord…</p>
      }
    </section>
  `,
})
export class RcDashboardComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);

  readonly toneStatut = toneStatut;
  readonly tonePriorite = tonePriorite;
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
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Tableau de bord indisponible'));
      },
    });
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

  date(iso: string | null): string {
    return dateFr(iso);
  }
}
