import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { RbcmBarsComponent, RbcmDonutComponent } from '../rbcm-charts';
import { RbcmCampaignPickerComponent } from '../rbcm-campaign-picker.component';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import {
  IMPORT_STATUS_LABELS,
  RBCM_API,
  RbcmAccueil,
  RbcmProgress,
  STATUS_LABELS,
  periodLabel,
} from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-accueil',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    MatIconModule,
    RouterLink,
    DatePipe,
    RbcmStylesComponent,
    RbcmBarsComponent,
    RbcmDonutComponent,
    RbcmCampaignPickerComponent,
  ],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Comptabilité</p>
          <h1>Reporting BCM — Situation Mensuelle</h1>
          <p class="bea-rbcm-sub">
            Pilotage des situations mensuelles — source unique BAL DET, paramètres et contrôles.
            Mapping non activé · ECART désactivé.
          </p>
        </div>
      </header>

      <bea-rbcm-campaign-picker />

      @if (loading()) {
        <div class="bea-fx-kpis">
          @for (i of [1, 2, 3, 4, 5, 6]; track i) {
            <span class="bea-fx-skel bea-fx-skel--kpi"></span>
          }
        </div>
      } @else if (data(); as d) {
        @if (dash(); as k) {
          <!-- Zone 2 KPI -->
          <div class="bea-fx-kpis">
            <a class="bea-fx-kpi" routerLink="/reporting-bcm-sm/campagnes">
              <mat-icon>folder</mat-icon><p>Situations mensuelles</p><strong>{{ k.campaigns_total }}</strong>
            </a>
            <a class="bea-fx-kpi" data-tone="info" routerLink="/reporting-bcm-sm/campagnes">
              <mat-icon>folder_open</mat-icon><p>SM ouvertes</p><strong>{{ k.campaigns_open }}</strong>
            </a>
            <div class="bea-fx-kpi">
              <mat-icon>sync</mat-icon><p>SM en cours</p><strong>{{ k.campaigns_in_progress ?? 0 }}</strong>
            </div>
            <div class="bea-fx-kpi" data-tone="warn">
              <mat-icon>pending</mat-icon><p>SM en attente</p><strong>{{ k.campaigns_pending }}</strong>
            </div>
            <div class="bea-fx-kpi" data-tone="warn">
              <mat-icon>calculate</mat-icon><p>SM calculées</p><strong>{{ k.campaigns_calculated ?? 0 }}</strong>
            </div>
            <div class="bea-fx-kpi" data-tone="ok">
              <mat-icon>verified</mat-icon><p>SM approuvées</p><strong>{{ k.campaigns_approved ?? 0 }}</strong>
            </div>
            <div class="bea-fx-kpi" data-tone="ok">
              <mat-icon>task_alt</mat-icon><p>SM clôturées</p><strong>{{ k.campaigns_closed }}</strong>
            </div>
            <a class="bea-fx-kpi" routerLink="/reporting-bcm-sm/imports">
              <mat-icon>cloud_done</mat-icon><p>BAL DET OK</p><strong>{{ detValidatedCount() }}</strong>
            </a>
            <div class="bea-fx-kpi" data-tone="warn">
              <mat-icon>warning</mat-icon><p>Imports anomalie</p><strong>{{ k.imports_anomaly }}</strong>
            </div>
            <div class="bea-fx-kpi" data-tone="ok">
              <mat-icon>tune</mat-icon><p>Params renseignés</p><strong>{{ k.parameters_filled ?? 0 }}</strong>
            </div>
            <div class="bea-fx-kpi" data-tone="warn">
              <mat-icon>hourglass_empty</mat-icon><p>Params en attente</p><strong>{{ k.parameters_missing }}</strong>
            </div>
          </div>

          <div class="bea-rbcm-grid">
            <!-- Zone 3 progression -->
            <section class="bea-mg__panel bea-rbcm-span6">
              <div class="bea-mg__panel-top">
                <div>
                  <h2>Progression de la SM</h2>
                  <p class="bea-rbcm-sub">{{ ctx.selectedLabel() }}</p>
                </div>
                @if (progress(); as p) {
                  <strong class="bea-rbcm-pct">{{ p.pct }}&nbsp;%</strong>
                }
              </div>
              @if (progress(); as p) {
                <div class="bea-rbcm-progress" role="progressbar" [attr.aria-valuenow]="p.pct">
                  <div class="bea-rbcm-progress__bar" [style.width.%]="p.pct"></div>
                </div>
                <div class="bea-rbcm-steps" style="margin-top:0.85rem">
                  <div class="bea-rbcm-step" data-state="done">
                    <mat-icon>check_circle</mat-icon>
                    <span>1. SM</span>
                    <small>Sélectionnée</small>
                  </div>
                  <div class="bea-rbcm-step" [attr.data-state]="p.det_validated ? 'done' : 'wait'">
                    <mat-icon>{{ p.det_validated ? 'check_circle' : 'radio_button_unchecked' }}</mat-icon>
                    <span>2. Import BAL DET</span>
                    <small>{{ p.det_validated ? 'Terminé' : 'À faire' }}</small>
                  </div>
                  <div class="bea-rbcm-step" [attr.data-state]="p.det_validated ? 'done' : 'wait'">
                    <mat-icon>{{ p.det_validated ? 'check_circle' : 'fact_check' }}</mat-icon>
                    <span>3. Contrôles internes</span>
                    <small>{{ p.det_validated ? 'Exécutés à la confirmation' : 'Après confirmation' }}</small>
                  </div>
                  <div
                    class="bea-rbcm-step"
                    [attr.data-state]="p.parameters_filled >= p.parameters_total ? 'done' : 'wait'"
                  >
                    <mat-icon>edit_note</mat-icon>
                    <span>4. Cellules manuelles</span>
                    <small>{{ p.parameters_filled }}/{{ p.parameters_total }}</small>
                  </div>
                  <div class="bea-rbcm-step" [attr.data-state]="p.work_document_id ? 'done' : 'wait'">
                    <mat-icon>description</mat-icon>
                    <span>5. Canevas SM</span>
                    <small>{{ p.work_document_id ? 'Document de travail' : 'À générer' }}</small>
                  </div>
                </div>
              } @else {
                <div class="bea-rbcm-empty">
                  <mat-icon>info</mat-icon>
                  <div>
                    <strong>Sélectionnez une SM</strong>
                    <p>La progression détaillée s’affiche pour la SM active.</p>
                  </div>
                </div>
              }
            </section>

            <!-- Zone 6 actions rapides -->
            <section class="bea-mg__panel bea-rbcm-span6">
              <div class="bea-mg__panel-top">
                <div><h2>Actions rapides</h2><p class="bea-rbcm-sub">Uniquement des actions disponibles</p></div>
              </div>
              <div class="bea-rbcm-quick">
                <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/reporting-bcm-sm/campagnes/nouvelle">
                  <mat-icon>add</mat-icon> Nouvelle SM
                </a>
                <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/imports">
                  <mat-icon>upload</mat-icon> Importer BAL DET
                </a>
                <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/parametres">
                  <mat-icon>tune</mat-icon> Paramètres
                </a>
                <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/rapprochement">
                  <mat-icon>fact_check</mat-icon> Contrôles
                </a>
                <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/mapping">
                  <mat-icon>account_tree</mat-icon> Correspondances
                </a>
              </div>
              <p class="bea-rbcm-hint" style="margin-top:1rem">{{ d.mapping_policy }}</p>
              <p class="bea-rbcm-hint">{{ d.ecart_policy }}</p>
            </section>

            <!-- Zone 4 graphiques -->
            <section class="bea-mg__panel bea-rbcm-span4">
              <div class="bea-mg__panel-top"><div><h2>SM par statut</h2></div></div>
              <bea-rbcm-donut [parts]="statusParts()" [centre]="k.campaigns_total" unite="SM" />
            </section>
            <section class="bea-mg__panel bea-rbcm-span4">
              <div class="bea-mg__panel-top"><div><h2>Imports validés</h2><p class="bea-rbcm-sub">Source BAL DET</p></div></div>
              <bea-rbcm-donut [parts]="importTypeParts()" unite="validés" />
            </section>
            <section class="bea-mg__panel bea-rbcm-span4">
              <div class="bea-mg__panel-top"><div><h2>Mapping</h2><p class="bea-rbcm-sub">Aucun ACTIVE</p></div></div>
              <bea-rbcm-donut [parts]="k.mapping_by_lifecycle || []" unite="règles" vide="Aucune règle" />
            </section>
            <section class="bea-mg__panel bea-rbcm-span8">
              <div class="bea-mg__panel-top"><div><h2>Anomalies</h2></div></div>
              <bea-rbcm-bars [parts]="k.anomalies_by_code" vide="Aucune anomalie" />
            </section>
            <section class="bea-mg__panel bea-rbcm-span4">
              <div class="bea-mg__panel-top"><div><h2>Évolution mensuelle des imports</h2></div></div>
              <bea-rbcm-bars [parts]="monthlyBars()" vide="Aucun import validé" />
            </section>

            <!-- Zone 5 activité -->
            <section class="bea-mg__panel bea-rbcm-span6">
              <div class="bea-mg__panel-top">
                <div><h2>Dernières SM</h2></div>
                <a routerLink="/reporting-bcm-sm/campagnes">Tout voir</a>
              </div>
              <ul class="bea-rbcm-list">
                @for (c of k.recent_campaigns || []; track c.id) {
                  <li (click)="openCamp(c.id)">
                    <span>
                      <strong>{{ c.label }}</strong>
                      <small>{{ STATUS_LABELS[c.status] || c.status }} · {{ c.created_at | date: 'dd/MM/yyyy HH:mm' }}</small>
                    </span>
                  </li>
                } @empty {
                  <li style="cursor:default"><span class="bea-rbcm-hint">Aucune SM.</span></li>
                }
              </ul>
            </section>
            <section class="bea-mg__panel bea-rbcm-span6">
              <div class="bea-mg__panel-top">
                <div><h2>Derniers imports</h2></div>
                <a routerLink="/reporting-bcm-sm/imports">Tout voir</a>
              </div>
              <ul class="bea-rbcm-list">
                @for (i of recentDetImports(); track i.id) {
                  <li (click)="openImport(i.campaign_id)">
                    <span>
                      <strong>{{ i.filename }}</strong>
                      <small>BAL DET · {{ importStatus(i.status) }} · {{ i.created_at | date: 'dd/MM/yyyy HH:mm' }}</small>
                    </span>
                  </li>
                } @empty {
                  <li style="cursor:default"><span class="bea-rbcm-hint">Aucun import BAL DET.</span></li>
                }
              </ul>
            </section>
          </div>
        }
      }
    </div>
  `,
})
export class RbcmAccueilComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  readonly ctx = inject(RbcmContextService);

  readonly loading = signal(true);
  readonly data = signal<RbcmAccueil | null>(null);
  readonly progress = signal<RbcmProgress | null>(null);
  readonly STATUS_LABELS = STATUS_LABELS;
  readonly periodLabel = periodLabel;

  readonly dash = computed(() => this.data()?.dashboard ?? null);
  readonly monthlyBars = computed(() =>
    (this.dash()?.imports_monthly ?? []).map((m) => ({ label: m.label, value: m.value })),
  );
  readonly statusParts = computed(() =>
    (this.dash()?.by_status ?? []).map((s) => ({
      label: STATUS_LABELS[s.label] || s.label,
      value: s.value,
    })),
  );
  readonly importTypeParts = computed(() =>
    (this.dash()?.imports_by_type ?? [])
      .filter((s) => s.label === 'BAL_DET')
      .map((s) => ({ label: 'BAL DET', value: s.value })),
  );
  readonly recentDetImports = computed(() =>
    (this.dash()?.recent_imports ?? []).filter((i) => i.file_type === 'BAL_DET'),
  );
  readonly detValidatedCount = computed(() => {
    const part = (this.dash()?.imports_by_type ?? []).find((s) => s.label === 'BAL_DET');
    return part?.value ?? this.dash()?.imports_validated ?? 0;
  });

  importStatus(status: string): string {
    return IMPORT_STATUS_LABELS[status] || status;
  }

  constructor() {
    effect(() => {
      const id = this.ctx.selectedId();
      if (!id) {
        this.progress.set(null);
        return;
      }
      this.api.get<RbcmProgress>(`${RBCM_API}/campaigns/${id}/progress`).subscribe({
        next: (p) => this.progress.set(p),
        error: () => this.progress.set(null),
      });
    });
  }

  ngOnInit(): void {
    this.ctx.loadCampaigns();
    this.api.get<RbcmAccueil>(`${RBCM_API}/accueil`).subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Accueil BCM SM indisponible');
          this.loading.set(false);
        }),
    });
  }

  openCamp(id: string): void {
    this.ctx.select(id);
    void this.router.navigate(['/reporting-bcm-sm/campagnes', id]);
  }

  openImport(campaignId: string): void {
    this.ctx.select(campaignId);
    void this.router.navigate(['/reporting-bcm-sm/imports']);
  }
}
