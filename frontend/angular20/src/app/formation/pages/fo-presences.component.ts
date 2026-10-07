import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { forkJoin } from 'rxjs';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FormationUiComponent } from '../formation-ui.component';
import { FO_BASE, Page, Session, dateFr, jourMois, statutAffiche, taux } from '../formation.models';
import { FormationStore } from '../formation.store';

type Onglet = 'a_saisir' | 'a_cloturer' | 'a_venir' | 'saisies';

@Component({
  selector: 'bea-fo-presences',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, FormationUiComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <p class="bea-stock-page__kicker">Formation &amp; Sensibilisation</p>
          <h1>Présences</h1>
          <p class="bea-fo-head__sub">Saisie PRÉSENT / ABSENT après chaque formation, à partir de la feuille signée. Les feuilles vierges s’impriment avant la session.</p>
        </div>
      </header>

      <div class="bea-fo-alerts">
        <button type="button" class="bea-fo-alert" data-tone="warn" [class.is-active]="onglet() === 'a_saisir'" (click)="onglet.set('a_saisir')">
          <mat-icon>edit_calendar</mat-icon><span><strong>{{ listes().a_saisir.total }}</strong><small>formation(s) à saisir</small></span>
        </button>
        <button type="button" class="bea-fo-alert" data-tone="alert" (click)="onglet.set('a_cloturer')">
          <mat-icon>task_alt</mat-icon><span><strong>{{ listes().a_cloturer.total }}</strong><small>réalisée(s), à clôturer</small></span>
        </button>
        <button type="button" class="bea-fo-alert" (click)="onglet.set('a_venir')">
          <mat-icon>event_upcoming</mat-icon><span><strong>{{ listes().a_venir.total }}</strong><small>à venir : feuilles à imprimer</small></span>
        </button>
        <button type="button" class="bea-fo-alert" data-tone="ok" (click)="onglet.set('saisies')">
          <mat-icon>verified</mat-icon><span><strong>{{ listes().saisies.total }}</strong><small>clôturée(s)</small></span>
        </button>
      </div>

      <nav class="bea-ct-tabs" style="margin-bottom:0.9rem">
        <button type="button" [class.is-on]="onglet() === 'a_saisir'" (click)="onglet.set('a_saisir')"><mat-icon>edit_calendar</mat-icon> À saisir</button>
        <button type="button" [class.is-on]="onglet() === 'a_cloturer'" (click)="onglet.set('a_cloturer')"><mat-icon>task_alt</mat-icon> À clôturer</button>
        <button type="button" [class.is-on]="onglet() === 'a_venir'" (click)="onglet.set('a_venir')"><mat-icon>event_upcoming</mat-icon> À venir</button>
        <button type="button" [class.is-on]="onglet() === 'saisies'" (click)="onglet.set('saisies')"><mat-icon>verified</mat-icon> Clôturées récentes</button>
      </nav>

      <section class="bea-mg__panel">
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-fo-table">
            <thead><tr><th>Date</th><th>Formation</th><th>Lieu</th><th class="is-num">Participants</th><th>Présence</th><th>Statut</th><th></th></tr></thead>
            <tbody>
              @if (charge()) {
                @for (i of [1, 2, 3, 4]; track i) { <tr>@for (j of [1, 2, 3, 4, 5, 6, 7]; track j) { <td><span class="bea-fx-skel"></span></td> }</tr> }
              } @else {
                @for (s of listes()[onglet()].items; track s.id; let i = $index) {
                  <tr class="is-click bea-fx-row-in" [style.--i]="i" (click)="ouvrir(s)">
                    <td>
                      <span class="bea-fo-person">
                        <span class="bea-fo-date" [class.bea-fo-date--warn]="s.a_saisir" [class.bea-fo-date--muted]="s.statut === 'CLOTUREE'"><b>{{ jm(s.date_session).jour }}</b><span>{{ jm(s.date_session).mois }}</span></span>
                        <span><strong>{{ dateFr(s.date_session) }}</strong><small>{{ s.reference }}</small></span>
                      </span>
                    </td>
                    <td><strong>{{ s.theme_libelle }}</strong><small>{{ s.formateur_libelle }}</small></td>
                    <td>{{ s.lieu?.libelle }}</td>
                    <td class="is-num">{{ s.stats.participants }}</td>
                    <td>
                      <span class="bea-fo-pct">
                        <span class="bea-fo-progress">
                          <i class="is-p" [style.width.%]="pct(s.stats.presents, s.stats.participants)"></i>
                          <i class="is-a" [style.width.%]="pct(s.stats.absents, s.stats.participants)"></i>
                        </span>
                        <b>{{ s.stats.presents + s.stats.absents }}/{{ s.stats.participants }}</b>
                      </span>
                    </td>
                    <td><span class="bea-fo-badge" [attr.data-s]="st(s).code">{{ st(s).label }}</span></td>
                    <td class="is-c" (click)="$event.stopPropagation()">
                      @if (onglet() === 'a_saisir' && s.actions.saisir_presences) {
                        <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ouvrir(s, true)"><mat-icon>fact_check</mat-icon> Saisir</button>
                      } @else if (onglet() === 'a_venir') {
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrir(s)"><mat-icon>print</mat-icon> Feuille</button>
                      } @else {
                        <button type="button" class="bea-mg__icon-btn" title="Ouvrir" (click)="ouvrir(s)"><mat-icon>chevron_right</mat-icon></button>
                      }
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="7"><div class="bea-fo-empty"><mat-icon>task_alt</mat-icon><strong>Rien à traiter</strong>{{ vide[onglet()] }}</div></td></tr>
                }
              }
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `,
})
export class FoPresencesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  private readonly store = inject(FormationStore);

  readonly dateFr = dateFr;
  readonly taux = taux;
  readonly jm = jourMois;
  readonly st = statutAffiche;
  readonly vide: Record<Onglet, string> = {
    a_saisir: 'Toutes les présences des formations passées sont saisies.',
    a_cloturer: 'Aucune formation réalisée en attente de clôture.',
    a_venir: 'Aucune formation planifiée.',
    saisies: 'Aucune formation clôturée.',
  };

  readonly onglet = signal<Onglet>('a_saisir');
  readonly charge = signal(true);
  private readonly videPage: Page<Session> = { items: [], total: 0, page: 1, taille: 0 };
  readonly listes = signal<Record<Onglet, Page<Session>>>({ a_saisir: this.videPage, a_cloturer: this.videPage, a_venir: this.videPage, saisies: this.videPage });

  ngOnInit(): void {
    this.store.charger();
    const aujourdhui = new Date().toISOString().slice(0, 10);
    const lendemain = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
    const get = (p: Record<string, string | number | boolean>) => this.api.get<Page<Session>>(`${FO_BASE}/sessions`, { taille: 100, ...p });
    forkJoin({
      a_saisir: get({ a_saisir: true, tri: 'date', sens: 'asc' }),
      a_cloturer: get({ statut: 'REALISEE', tri: 'date', sens: 'asc' }),
      a_venir: get({ statut: 'PLANIFIEE', date_debut: lendemain, tri: 'date', sens: 'asc' }),
      saisies: get({ statut: 'CLOTUREE', date_fin: aujourdhui, taille: 30 }),
    }).subscribe({
      next: (r) => {
        this.listes.set(r);
        this.charge.set(false);
        if (!r.a_saisir.total && r.a_cloturer.total) this.onglet.set('a_cloturer');
      },
      error: (e) => {
        this.charge.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Présences indisponibles'));
      },
    });
  }

  pct(n: number, t: number): number {
    return t ? (n / t) * 100 : 0;
  }

  ouvrir(s: Session, saisie = false): void {
    void this.router.navigate(['/formation/sessions', s.id], saisie ? { queryParams: { saisie: 1 } } : {});
  }
}
