import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import { RBCM_API, RbcmCampaign, RbcmOwnerCandidate } from '../rbcm.models';

const MONTHS = [
  { v: 1, l: 'Janvier' },
  { v: 2, l: 'Février' },
  { v: 3, l: 'Mars' },
  { v: 4, l: 'Avril' },
  { v: 5, l: 'Mai' },
  { v: 6, l: 'Juin' },
  { v: 7, l: 'Juillet' },
  { v: 8, l: 'Août' },
  { v: 9, l: 'Septembre' },
  { v: 10, l: 'Octobre' },
  { v: 11, l: 'Novembre' },
  { v: 12, l: 'Décembre' },
];

@Component({
  selector: 'bea-rbcm-campagne-nouvelle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, RouterLink, RbcmStylesComponent],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>Nouvelle Situation Mensuelle</h1>
          <p class="bea-rbcm-sub">
            Choisissez le mois, l’année et le responsable chargé de préparer le reporting.
          </p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/campagnes">Retour</a>
      </header>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <div>
            <h2>Informations de la SM</h2>
            <p class="bea-rbcm-sub">Une seule SM ouverte par période. Le créateur et le responsable peuvent être distincts.</p>
          </div>
        </div>
        <div class="bea-rbcm-form-grid">
          <label class="bea-mg__field">
            <mat-icon>calendar_month</mat-icon>
            <select [(ngModel)]="month" name="month" aria-label="Mois">
              @for (m of months; track m.v) {
                <option [ngValue]="m.v">{{ m.l }}</option>
              }
            </select>
          </label>
          <label class="bea-mg__field">
            <mat-icon>event</mat-icon>
            <input type="number" [(ngModel)]="year" name="year" min="2000" max="2100" aria-label="Année" />
          </label>
          <label class="bea-mg__field bea-rbcm-form-wide">
            <mat-icon>person</mat-icon>
            <select [(ngModel)]="ownerId" name="owner" aria-label="Responsable du reporting">
              <option value="">Choisir le responsable…</option>
              @for (u of owners(); track u.id) {
                <option [value]="u.id">{{ u.full_name }} — {{ u.email }}</option>
              }
            </select>
          </label>
        </div>
        @if (ownersError()) {
          <p class="bea-rbcm-hint">{{ ownersError() }}</p>
        }
        <p class="bea-rbcm-hint">
          Vous serez enregistré comme créateur. Le responsable prépare ensuite la SM (import BAL DET, contrôles, document).
        </p>
        <div class="bea-rbcm-quick" style="margin-top:1rem">
          <button
            type="button"
            class="bea-mg__btn bea-mg__btn--primary"
            [disabled]="busy() || !year || !month || !ownerId"
            (click)="creer()"
          >
            <mat-icon>save</mat-icon> Créer la SM
          </button>
        </div>
      </section>
    </div>
  `,
})
export class RbcmCampagneNouvelleComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);

  readonly months = MONTHS;
  year = new Date().getFullYear();
  month = new Date().getMonth() + 1;
  ownerId = '';
  readonly owners = signal<RbcmOwnerCandidate[]>([]);
  readonly ownersError = signal<string | null>(null);
  readonly busy = signal(false);

  ngOnInit(): void {
    const me = this.auth.user();
    if (me?.id) this.ownerId = me.id;
    this.api.get<RbcmOwnerCandidate[]>(`${RBCM_API}/preparateurs`).subscribe({
      next: (rows) => {
        this.owners.set(rows);
        if (this.ownerId && !rows.some((u) => u.id === this.ownerId) && rows.length) {
          this.ownerId = rows[0].id;
        }
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.ownersError.set(i.message || 'Impossible de charger les responsables autorisés.');
        }),
    });
  }

  creer(): void {
    if (this.month < 1 || this.month > 12) {
      this.feedback.warning({ title: 'Mois invalide', message: 'Choisissez un mois entre 1 et 12.' });
      return;
    }
    if (!this.ownerId) {
      this.feedback.warning({
        title: 'Responsable manquant',
        message: 'Désignez le responsable chargé de préparer le reporting.',
      });
      return;
    }
    const monthLabel = this.months.find((m) => m.v === this.month)?.l || String(this.month);
    const owner = this.owners().find((u) => u.id === this.ownerId);
    this.feedback
      .run(
        () =>
          this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns`, {
            period_year: this.year,
            period_month: this.month,
            bank_code: 'BEA',
            reporting_owner_id: this.ownerId,
          }),
        {
          busy: this.busy,
          confirm: {
            title: 'Créer la Situation Mensuelle ?',
            message: `${monthLabel} ${this.year} — responsable : ${owner?.full_name || 'désigné'}.`,
            confirmLabel: 'Créer',
          },
          loading: 'Création…',
          success: { title: 'SM créée', message: 'La fiche de la Situation Mensuelle est ouverte.' },
          errorTitle: 'Création impossible',
          idempotent: true,
        },
      )
      .subscribe({
        next: (c) => void this.router.navigate(['/reporting-bcm-sm/campagnes', c.id]),
      });
  }
}
