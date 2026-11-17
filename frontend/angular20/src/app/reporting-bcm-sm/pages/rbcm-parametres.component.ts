import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { DetailDrawerComponent } from '../../contrats-echeances/shared/detail-drawer.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { RbcmCampaignPickerComponent } from '../rbcm-campaign-picker.component';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import { RBCM_API, RbcmParamCatalog, RbcmParameterValue } from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    MatIconModule,
    DatePipe,
    DetailDrawerComponent,
    RbcmStylesComponent,
    RbcmCampaignPickerComponent,
  ],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>Paramètres mensuels</h1>
          <p class="bea-rbcm-sub">Huit codes — pas de reconduction N−1. Absence ≠ zéro.</p>
        </div>
        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy() || !ctx.selectedId()" (click)="deriveCaisse()">
          <mat-icon>functions</mat-icon> Dériver caisse devises
        </button>
      </header>
      <bea-rbcm-campaign-picker />

      @if (!ctx.selectedId()) {
        <section class="bea-mg__panel"><div class="bea-rbcm-empty"><mat-icon>info</mat-icon><p>Sélectionnez une SM.</p></div></section>
      } @else if (loading()) {
        <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
      } @else {
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr><th>Code</th><th>Libellé</th><th>Valeur</th><th>Statut</th><th>Source</th><th></th></tr></thead>
            <tbody>
              @for (p of params(); track p.code) {
                <tr class="bea-rbcm-row" (click)="open(p)">
                  <td class="bea-rbcm-mono">{{ p.code }}</td>
                  <td>{{ p.label }}</td>
                  <td>{{ p.value ?? '—' }}</td>
                  <td><span class="bea-ct-badge">{{ p.status }}</span></td>
                  <td>{{ p.source || '—' }}</td>
                  <td><button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="$event.stopPropagation(); open(p)">Détail</button></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (drawer(); as p) {
        <bea-detail-drawer [titre]="p.label" [kicker]="p.code" [sousTitre]="p.status" [large]="true" (fermer)="drawer.set(null)"
          [onglets]="tabs" [(onglet)]="tab">
          <div drawerActions class="bea-rbcm-quick">
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="save(p)">Enregistrer</button>
            @if (p.value_id && (p.status === 'SAISI' || p.status === 'CALCULE')) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="validate(p)">Valider</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="reject(p)">Rejeter</button>
            }
          </div>
          @if (tab() === 'saisie') {
            <div class="bea-rbcm-form-grid">
              <label class="bea-mg__field bea-mg__field--grow bea-rbcm-form-wide">
                <mat-icon>payments</mat-icon>
                <input [(ngModel)]="form.value" placeholder="Valeur (Decimal)" aria-label="Valeur" />
              </label>
              <label class="bea-mg__field bea-mg__field--grow">
                <mat-icon>source</mat-icon>
                <input [(ngModel)]="form.source" placeholder="Source" aria-label="Source" />
              </label>
              <label class="bea-mg__field bea-mg__field--grow">
                <mat-icon>description</mat-icon>
                <input [(ngModel)]="form.justificatif_ref" placeholder="Référence justificatif" aria-label="Justificatif" />
              </label>
              <label class="bea-mg__field bea-mg__field--grow bea-rbcm-form-wide bea-rbcm-form-textarea">
                <mat-icon>notes</mat-icon>
                <textarea rows="3" [(ngModel)]="form.justification" placeholder="Justification"></textarea>
              </label>
            </div>
            <p class="bea-rbcm-hint">La validation est interdite pour l’auteur de la saisie (SoD).</p>
          }
          @if (tab() === 'historique') {
            @if (!history().length) {
              <p class="bea-rbcm-hint">Aucun historique.</p>
            } @else {
              <table class="bea-mg__table">
                <thead><tr><th>Date</th><th>Valeur</th><th>Statut</th><th>Source</th></tr></thead>
                <tbody>
                  @for (h of history(); track h.id) {
                    <tr>
                      <td>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>{{ h.value ?? '—' }}</td>
                      <td>{{ h.status }}</td>
                      <td>{{ h.source || '—' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          }
        </bea-detail-drawer>
      }
    </div>
  `,
})
export class RbcmParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly ctx = inject(RbcmContextService);

  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly params = signal<RbcmParamCatalog[]>([]);
  readonly drawer = signal<RbcmParamCatalog | null>(null);
  readonly history = signal<RbcmParameterValue[]>([]);
  readonly tab = signal('saisie');
  readonly tabs = [
    { key: 'saisie', label: 'Saisie' },
    { key: 'historique', label: 'Historique' },
  ];
  form = { value: '', source: '', justification: '', justificatif_ref: '' };

  constructor() {
    effect(() => {
      if (this.ctx.selectedId()) this.load();
      else this.params.set([]);
    });
  }

  ngOnInit(): void {
    this.ctx.loadCampaigns();
  }

  load(): void {
    const id = this.ctx.selectedId();
    if (!id) return;
    this.loading.set(true);
    this.api.get<RbcmParamCatalog[]>(`${RBCM_API}/campaigns/${id}/parameters`).subscribe({
      next: (r) => {
        this.params.set(r);
        this.loading.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Paramètres indisponibles');
          this.loading.set(false);
        }),
    });
  }

  open(p: RbcmParamCatalog): void {
    this.form = {
      value: p.value ?? '',
      source: p.source ?? '',
      justification: '',
      justificatif_ref: p.justificatif_ref ?? '',
    };
    this.tab.set('saisie');
    this.drawer.set(p);
    const id = this.ctx.selectedId();
    if (!id) return;
    this.api
      .get<RbcmParameterValue[]>(`${RBCM_API}/campaigns/${id}/parameters/history`, {
        parameter_code: p.code,
        page: 1,
        page_size: 50,
      })
      .subscribe({ next: (h) => this.history.set(h) });
  }

  save(p: RbcmParamCatalog): void {
    const id = this.ctx.selectedId();
    if (!id) return;
    this.feedback
      .run(
        () =>
          this.api.post(`${RBCM_API}/campaigns/${id}/parameters`, {
            parameter_code: p.code,
            value: this.form.value === '' ? null : this.form.value,
            source: this.form.source || null,
            justification: this.form.justification || null,
            justificatif_ref: this.form.justificatif_ref || null,
            expected_value_id: p.value_id,
          }),
        {
          busy: this.busy,
          loading: 'Enregistrement…',
          success: { title: 'Paramètre enregistré' },
          errorTitle: 'Enregistrement impossible',
        },
      )
      .subscribe({
        next: () => {
          this.drawer.set(null);
          this.load();
        },
      });
  }

  validate(p: RbcmParamCatalog): void {
    const id = this.ctx.selectedId();
    if (!id || !p.value_id) return;
    this.feedback
      .run(() => this.api.post(`${RBCM_API}/campaigns/${id}/parameters/${p.value_id}/validate`, {}), {
        busy: this.busy,
        confirm: { title: 'Valider ?', message: p.label, confirmLabel: 'Valider' },
        loading: 'Validation…',
        success: { title: 'Validé' },
        errorTitle: 'Validation impossible',
      })
      .subscribe({ next: () => this.load() });
  }

  reject(p: RbcmParamCatalog): void {
    const id = this.ctx.selectedId();
    if (!id || !p.value_id) return;
    this.feedback
      .runWithReason(
        (comment) => this.api.post(`${RBCM_API}/campaigns/${id}/parameters/${p.value_id}/reject`, { comment }),
        {
          busy: this.busy,
          reason: { title: 'Rejeter', message: p.label, confirmLabel: 'Rejeter', required: true },
          loading: 'Rejet…',
          success: { title: 'Rejeté' },
          errorTitle: 'Rejet impossible',
        },
      )
      .subscribe({ next: () => this.load() });
  }

  deriveCaisse(): void {
    const id = this.ctx.selectedId();
    if (!id) return;
    this.feedback
      .run(
        () =>
          this.api.get<{
            proposed_value: string;
            method: string;
            accounts_count: number;
            source_filename?: string;
          }>(`${RBCM_API}/campaigns/${id}/parameters/caisse-devises/propose`),
        {
          busy: this.busy,
          loading: 'Proposition…',
          success: { title: 'Proposition calculée' },
          errorTitle: 'Proposition impossible',
        },
      )
      .subscribe({
        next: (prop) => {
          this.feedback
            .run(() => this.api.post(`${RBCM_API}/campaigns/${id}/parameters/caisse-devises/apply`, {}), {
              busy: this.busy,
              confirm: {
                title: 'Appliquer caisse_devises ?',
                message:
                  `Valeur proposée : ${prop.proposed_value} (${prop.accounts_count} compte(s)).\n` +
                  `${prop.method}\n` +
                  (prop.source_filename ? `Fichier : ${prop.source_filename}` : ''),
                confirmLabel: 'Enregistrer CALCULE',
              },
              loading: 'Enregistrement…',
              success: { title: 'Proposition CALCULE enregistrée' },
              errorTitle: 'Dérivation impossible',
            })
            .subscribe({ next: () => this.load() });
        },
      });
  }
}
