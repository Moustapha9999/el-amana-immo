import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  OnInit,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';
import { DetailDrawerComponent } from '../../contrats-echeances/shared/detail-drawer.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { RbcmCampaignPickerComponent } from '../rbcm-campaign-picker.component';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmPagerComponent } from '../rbcm-pager.component';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import {
  IMPORT_STATUS_LABELS,
  RBCM_API,
  RbcmImport,
  RbcmImportList,
  periodLabel,
} from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-imports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    MatIconModule,
    DatePipe,
    RouterLink,
    DetailDrawerComponent,
    RbcmStylesComponent,
    RbcmCampaignPickerComponent,
    RbcmPagerComponent,
  ],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>Imports</h1>
          <p class="bea-rbcm-sub">
            Source comptable unique : BAL DET. Analyse → prévisualisation → confirmation.
            Idempotence SHA-256 · remplacement contrôlé.
          </p>
        </div>
        <div class="bea-mg__actions">
          @if (ctx.selected(); as c) {
            <a class="bea-mg__btn bea-mg__btn--ghost" [routerLink]="['/reporting-bcm-sm/campagnes', c.id]">
              <mat-icon>folder_open</mat-icon> Fiche SM
            </a>
          }
        </div>
      </header>

      <bea-rbcm-campaign-picker />

      @if (ctx.selected(); as c) {
        <section class="bea-rbcm-period-bar" aria-label="Périodes de référence">
          <div>
            <span class="bea-rbcm-period-bar__label">SM (mois de reporting)</span>
            <strong>{{ periodLabel(c) }}</strong>
          </div>
          <div>
            <span class="bea-rbcm-period-bar__label">Période comptable</span>
            <strong>{{ periodMonth(c.period_month) }}/{{ c.period_year }}</strong>
          </div>
          <div>
            <span class="bea-rbcm-period-bar__label">Date de situation (fichier)</span>
            <strong>{{ situationHint() || 'détectée à l’analyse' }}</strong>
          </div>
        </section>
      }

      <div class="bea-fx-kpis bea-rbcm-import-kpis">
        <div class="bea-fx-kpi"><mat-icon>inventory_2</mat-icon><p>Imports DET</p><strong>{{ detHistoryCount() }}</strong></div>
        <div class="bea-fx-kpi" [attr.data-tone]="detValidated() ? 'ok' : detCurrent() ? 'warn' : null">
          <mat-icon>table_rows</mat-icon><p>BAL DET</p>
          <strong>{{ detValidated() ? 'Confirmé' : detCurrent() ? statusLabel(detCurrent()!.status) : 'Absent' }}</strong>
        </div>
        <div class="bea-fx-kpi">
          <mat-icon>tag</mat-icon><p>NCG</p><strong>{{ ncgCount() ?? '—' }}</strong>
        </div>
        <div class="bea-fx-kpi">
          <mat-icon>account_balance</mat-icon><p>Comptes</p><strong>{{ compteCount() ?? '—' }}</strong>
        </div>
        <div class="bea-fx-kpi" data-tone="warn">
          <mat-icon>pending_actions</mat-icon><p>À confirmer</p><strong>{{ toConfirmCount() }}</strong>
        </div>
        <div class="bea-fx-kpi" [attr.data-tone]="anomalyCount() ? 'danger' : null">
          <mat-icon>warning</mat-icon><p>Anomalies</p><strong>{{ anomalyCount() }}</strong>
        </div>
      </div>

      <div class="bea-rbcm-grid">
        <section class="bea-mg__panel bea-rbcm-span5">
          <div class="bea-mg__panel-top">
            <div>
              <h2>Nouvel import BAL DET</h2>
              <p class="bea-rbcm-sub">Fichier Excel · NCG, COMPTE, LIBELLE, DEVISE, DEB, CRE</p>
            </div>
          </div>
          <div class="bea-rbcm-upload">
            <label class="bea-rbcm-file" [class.is-filled]="!!file">
              <mat-icon>attach_file</mat-icon>
              <span>{{ file?.name || 'Choisir BAL DET (.xlsx)' }}</span>
              <input type="file" accept=".xlsx,.xlsm" (change)="onFile($event)" aria-label="Fichier BAL DET" />
            </label>
            <div class="bea-rbcm-quick">
              <button
                type="button"
                class="bea-mg__btn bea-mg__btn--primary"
                [disabled]="!file || busy() || !ctx.selectedId()"
                (click)="upload()"
              >
                <mat-icon>analytics</mat-icon> Analyser
              </button>
            </div>
            @if (!ctx.selectedId()) {
              <p class="bea-rbcm-hint">Sélectionnez une SM avant d’importer.</p>
            }
          </div>
          <ol class="bea-rbcm-lifecycle">
            <li>Analyser — fichier stocké, rapport et prévisualisation</li>
            <li>Confirmer — soldes NCG chargés + contrôles internes</li>
            <li>Remplacer — ancienne version SUPERSEDED (historique conservé)</li>
            <li>Supprimer l’analyse — uniquement si non confirmée (réimport possible)</li>
          </ol>
        </section>

        <section class="bea-mg__panel bea-rbcm-span7">
          <div class="bea-mg__panel-top">
            <div>
              <h2>Import de référence</h2>
              <p class="bea-rbcm-sub">Un seul BAL DET actif par SM</p>
            </div>
          </div>
          <article class="bea-rbcm-source" [attr.data-state]="sourceState(detCurrent())">
            <header>
              <strong>BAL DET</strong>
              <span class="bea-ct-badge" [attr.data-tone]="statusTone(detCurrent()?.status)">
                {{ statusLabel(detCurrent()?.status) }}
              </span>
            </header>
            @if (detCurrent(); as d) {
              <p class="bea-rbcm-source__name" [title]="d.filename">{{ d.filename }}</p>
              <dl class="bea-rbcm-dl">
                <div><dt>Lignes</dt><dd>{{ d.row_count ?? '—' }}</dd></div>
                <div><dt>NCG</dt><dd>{{ ncgCount() ?? '—' }}</dd></div>
                <div><dt>Comptes</dt><dd>{{ compteCount() ?? '—' }}</dd></div>
                <div><dt>Devises</dt><dd>{{ devisesLabel() }}</dd></div>
                <div><dt>Date</dt><dd>{{ d.created_at | date: 'dd/MM/yyyy HH:mm' }}</dd></div>
                <div><dt>Empreinte</dt><dd class="bea-rbcm-mono" [title]="d.sha256">{{ d.sha256.slice(0, 12) }}…</dd></div>
              </dl>
              <div class="bea-rbcm-quick">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="open(d)">Détails</button>
                @if (d.status === 'ANALYZED') {
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--primary"
                    [disabled]="busy() || !canConfirm(d)"
                    (click)="confirm(d, false)"
                  >
                    Confirmer
                  </button>
                }
                @if (canDiscard(d)) {
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--ghost"
                    [disabled]="busy()"
                    (click)="discard(d)"
                  >
                    Supprimer l’analyse
                  </button>
                }
                <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/bal-det">Lignes</a>
              </div>
              <p class="bea-rbcm-hint">{{ nextAction(d) }}</p>
            } @else {
              <div class="bea-rbcm-empty bea-rbcm-empty--compact">
                <mat-icon>upload_file</mat-icon>
                <div><strong>Absent</strong><p>Importez la balance détaillée pour démarrer.</p></div>
              </div>
            }
          </article>
        </section>
      </div>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <div>
            <h2>Historique BAL DET</h2>
            <p class="bea-rbcm-sub">Versions et remplacements — traces conservées</p>
          </div>
        </div>

        <div class="bea-rbcm-filters">
          <label class="bea-mg__field">
            <mat-icon>flag</mat-icon>
            <select [(ngModel)]="status" (ngModelChange)="page.set(1); load()" aria-label="Filtrer par statut">
              <option value="">Tous les statuts</option>
              <option value="ANALYZED">Analysé</option>
              <option value="VALIDATED">Confirmé</option>
              <option value="SUPERSEDED">Remplacé</option>
              <option value="REJECTED">Rejeté</option>
            </select>
          </label>
          <label class="bea-mg__field bea-mg__field--grow">
            <mat-icon>search</mat-icon>
            <input
              type="search"
              placeholder="Nom de fichier…"
              [ngModel]="search"
              (ngModelChange)="onSearch($event)"
              aria-label="Rechercher un fichier"
            />
          </label>
          <label class="bea-mg__field">
            <mat-icon>view_list</mat-icon>
            <select [ngModel]="pageSize" (ngModelChange)="pageSize = +$event; page.set(1); load()" aria-label="Lignes par page">
              <option [ngValue]="10">10 / page</option>
              <option [ngValue]="25">25 / page</option>
              <option [ngValue]="50">50 / page</option>
              <option [ngValue]="100">100 / page</option>
            </select>
          </label>
        </div>

        @if (loading()) {
          <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
        } @else if (!items().length) {
          <div class="bea-rbcm-empty">
            <mat-icon>inbox</mat-icon>
            <div><strong>Aucun import BAL DET</strong><p>Importez un fichier Excel pour démarrer.</p></div>
          </div>
        } @else {
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead>
                <tr>
                  <th>Fichier</th>
                  <th>SM</th>
                  <th>Statut</th>
                  <th>Lignes</th>
                  <th>SHA-256</th>
                  <th>Date</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (imp of items(); track imp.id) {
                  <tr class="bea-rbcm-row" (click)="open(imp)">
                    <td class="bea-rbcm-ellipsis" [title]="imp.filename">{{ imp.filename }}</td>
                    <td>{{ campaignLabel(imp.campaign_id) }}</td>
                    <td>
                      <span class="bea-ct-badge" [attr.data-tone]="statusTone(imp.status)">
                        {{ statusLabel(imp.status) }}
                      </span>
                    </td>
                    <td>{{ imp.row_count ?? '—' }}</td>
                    <td class="bea-rbcm-mono" [title]="imp.sha256">{{ imp.sha256.slice(0, 10) }}…</td>
                    <td>{{ imp.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    <td (click)="$event.stopPropagation()">
                      <div class="bea-rbcm-quick">
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="open(imp)">Voir</button>
                        @if (imp.status === 'ANALYZED') {
                          <button
                            type="button"
                            class="bea-mg__btn bea-mg__btn--primary"
                            [disabled]="busy() || !canConfirm(imp)"
                            (click)="confirm(imp, false)"
                          >
                            Confirmer
                          </button>
                        }
                        @if (canDiscard(imp)) {
                          <button
                            type="button"
                            class="bea-mg__btn bea-mg__btn--ghost"
                            [disabled]="busy()"
                            (click)="discard(imp)"
                          >
                            Supprimer
                          </button>
                        }
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <bea-rbcm-pager
            [page]="page()"
            [pageSize]="pageSize"
            [total]="total()"
            label="Pagination des imports"
            noun="imports"
            (go)="go($event)"
          />
        }
      </section>

      @if (drawer(); as imp) {
        <bea-detail-drawer
          [titre]="imp.filename"
          [kicker]="'BAL DET'"
          [sousTitre]="statusLabel(imp.status) + ' · ' + (imp.row_count ?? 0) + ' lignes'"
          [large]="true"
          (fermer)="drawer.set(null)"
        >
          <div drawerActions class="bea-rbcm-quick">
            @if (imp.status === 'ANALYZED') {
              <button
                type="button"
                class="bea-mg__btn bea-mg__btn--primary"
                [disabled]="busy() || !canConfirm(imp)"
                (click)="confirm(imp, false)"
              >
                Confirmer
              </button>
              <button
                type="button"
                class="bea-mg__btn bea-mg__btn--ghost"
                [disabled]="busy() || !canConfirm(imp)"
                (click)="confirm(imp, true)"
              >
                Remplacer validé
              </button>
            }
            @if (canDiscard(imp)) {
              <button
                type="button"
                class="bea-mg__btn bea-mg__btn--ghost"
                [disabled]="busy()"
                (click)="discard(imp)"
              >
                Supprimer l’analyse
              </button>
            }
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="download(imp)">
              <mat-icon>download</mat-icon> Fichier
            </button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="copySha(imp)">
              <mat-icon>content_copy</mat-icon> SHA
            </button>
          </div>

          <h3>Informations fichier</h3>
          <dl class="bea-rbcm-dl">
            <div><dt>Nom</dt><dd>{{ imp.filename }}</dd></div>
            <div><dt>Taille</dt><dd>{{ formatSize(imp.size_bytes) }}</dd></div>
            <div><dt>SHA-256</dt><dd class="bea-rbcm-mono bea-rbcm-sha-full">{{ imp.sha256 }}</dd></div>
            <div>
              <dt>Période détectée</dt>
              <dd>
                @if (imp.period_year_detected && imp.period_month_detected) {
                  {{ periodMonth(imp.period_month_detected) }}/{{ imp.period_year_detected }}
                } @else {
                  Non détectée
                }
              </dd>
            </div>
            <div><dt>Lignes</dt><dd>{{ imp.row_count ?? '—' }}</dd></div>
          </dl>

          <h3>Structure</h3>
          <dl class="bea-rbcm-dl">
            <div><dt>Colonnes reconnues</dt><dd>{{ colsRecognized(imp) }}</dd></div>
            <div><dt>Colonnes manquantes</dt><dd>{{ colsMissing(imp) }}</dd></div>
            <div><dt>NCG distincts</dt><dd>{{ reportNum(imp, 'ncg_count') }}</dd></div>
            <div><dt>Comptes distincts</dt><dd>{{ reportNum(imp, 'compte_count') }}</dd></div>
            <div><dt>Devises</dt><dd>{{ devisesFrom(imp) }}</dd></div>
            <div><dt>Débit / Crédit</dt><dd>{{ imp.sum_debit }} / {{ imp.sum_credit }}</dd></div>
          </dl>

          <h3>Contrôles d’analyse</h3>
          <dl class="bea-rbcm-dl">
            <div><dt>Lignes valides</dt><dd>{{ reportNum(imp, 'valid_lines') }}</dd></div>
            <div><dt>Lignes rejetées</dt><dd>{{ reportNum(imp, 'rejected_lines') }}</dd></div>
            <div><dt>NCG manquants</dt><dd>{{ reportNum(imp, 'missing_ncg_count') }}</dd></div>
            <div><dt>Comptes manquants</dt><dd>{{ reportNum(imp, 'missing_compte_count') }}</dd></div>
            <div><dt>Erreurs</dt><dd>{{ reportNum(imp, 'error_count') }}</dd></div>
            <div>
              <dt>Prêt à confirmer</dt>
              <dd>
                <span class="bea-ct-badge" [attr.data-tone]="canConfirm(imp) ? 'ok' : 'danger'">
                  {{ canConfirm(imp) ? 'Oui' : 'Non' }}
                </span>
              </dd>
            </div>
          </dl>
          @if (blockingReasons(imp).length) {
            <ul class="bea-rbcm-hint">
              @for (r of blockingReasons(imp); track r) {
                <li>{{ r }}</li>
              }
            </ul>
          }

          <h3>Prochaine étape</h3>
          <p class="bea-rbcm-hint">{{ nextAction(imp) }}</p>

          <h3>Aperçu (échantillon)</h3>
          <p class="bea-rbcm-hint">Maximum {{ reportNum(imp, 'preview_limit') || '50' }} lignes — jamais le fichier complet.</p>
          @if (previewRows(imp).length) {
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead>
                  <tr><th>#</th><th>NCG</th><th>Compte</th><th>Libellé</th><th>Devise</th><th>Débit</th><th>Crédit</th></tr>
                </thead>
                <tbody>
                  @for (row of previewRows(imp); track $index) {
                    <tr>
                      <td>{{ row['line_no'] }}</td>
                      <td>{{ row['ncg'] }}</td>
                      <td>{{ row['compte'] }}</td>
                      <td class="bea-rbcm-ellipsis" [title]="'' + row['libelle']">{{ row['libelle'] }}</td>
                      <td>{{ row['devise'] }}</td>
                      <td>{{ row['debit'] }}</td>
                      <td>{{ row['credit'] }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          } @else {
            <p class="bea-rbcm-hint">Aucun échantillon disponible.</p>
          }

          @if (analysisErrors(imp).length) {
            <h3>Anomalies d’analyse</h3>
            <ul class="bea-rbcm-hint">
              @for (e of analysisErrors(imp); track $index) {
                <li>Ligne {{ e['line'] || '?' }} — {{ e['error'] }}</li>
              }
            </ul>
          }
        </bea-detail-drawer>
      }
    </div>
  `,
})
export class RbcmImportsComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly ctx = inject(RbcmContextService);
  readonly periodLabel = periodLabel;
  private readonly search$ = new Subject<string>();
  private searchSub = this.search$.pipe(debounceTime(300), distinctUntilChanged()).subscribe((q) => {
    this.search = q;
    this.page.set(1);
    this.load();
  });

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly items = signal<RbcmImport[]>([]);
  readonly campaignItems = signal<RbcmImport[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly drawer = signal<RbcmImport | null>(null);
  pageSize = 25;
  status = '';
  search = '';
  file: File | null = null;

  readonly detCurrent = computed(() => this.pickCurrent(this.campaignItems()));
  readonly detValidated = computed(() => this.detCurrent()?.status === 'VALIDATED');
  readonly detHistoryCount = computed(() => this.campaignItems().length);
  readonly toConfirmCount = computed(
    () => this.campaignItems().filter((i) => i.status === 'ANALYZED').length,
  );
  readonly anomalyCount = computed(
    () =>
      this.campaignItems().filter((i) => {
        if (i.status === 'REJECTED') return true;
        if (i.status === 'VALIDATED' || i.status === 'SUPERSEDED') return false;
        const headerOk = (i.control_report || {})['header_ok'];
        const err = Number((i.control_report || {})['error_count'] ?? 0);
        return headerOk === false || err > 0;
      }).length,
  );
  readonly ncgCount = computed(() => {
    const d = this.detCurrent();
    if (!d) return null;
    const n = (d.control_report || {})['ncg_count'] ?? (d.control_report || {})['confirmed_ncg_count'];
    return n != null ? Number(n) : null;
  });
  readonly compteCount = computed(() => {
    const d = this.detCurrent();
    if (!d) return null;
    const n = (d.control_report || {})['compte_count'];
    return n != null ? Number(n) : null;
  });

  constructor() {
    effect(() => {
      const _cid = this.ctx.selectedId();
      void _cid;
      this.page.set(1);
      this.load();
      this.loadCampaignSources();
    });
  }

  ngOnInit(): void {
    this.ctx.loadCampaigns();
  }

  ngOnDestroy(): void {
    this.searchSub.unsubscribe();
  }

  onSearch(q: string): void {
    this.search = q ?? '';
    this.search$.next(this.search);
  }

  periodMonth(m: number): string {
    return String(m).padStart(2, '0');
  }

  situationHint(): string | null {
    const d = this.detCurrent();
    if (d?.period_year_detected && d.period_month_detected) {
      return `${this.periodMonth(d.period_month_detected)}/${d.period_year_detected}`;
    }
    return null;
  }

  statusLabel(status: string | null | undefined): string {
    if (!status) return 'Absent';
    return IMPORT_STATUS_LABELS[status] || status;
  }

  statusTone(status: string | null | undefined): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (status === 'VALIDATED') return 'ok';
    if (status === 'ANALYZED') return 'warn';
    if (status === 'REJECTED') return 'danger';
    if (status === 'SUPERSEDED') return 'info';
    return null;
  }

  sourceState(imp: RbcmImport | null | undefined): string {
    if (!imp) return 'missing';
    if (imp.status === 'VALIDATED') return 'ok';
    if (imp.status === 'ANALYZED') return 'ready';
    if (imp.status === 'REJECTED') return 'error';
    return 'neutral';
  }

  nextAction(imp: RbcmImport): string {
    if (imp.status === 'ANALYZED') {
      return 'Prochaine étape : confirmer pour charger les soldes NCG et lancer les contrôles internes.';
    }
    if (imp.status === 'VALIDATED') {
      return 'BAL DET confirmée — contrôles internes disponibles, puis paramètres.';
    }
    if (imp.status === 'SUPERSEDED') return 'Version remplacée — consulter l’historique.';
    if (imp.status === 'REJECTED') return 'Corriger le fichier puis réimporter.';
    return '';
  }

  devisesLabel(): string {
    return this.devisesFrom(this.detCurrent());
  }

  devisesFrom(imp: RbcmImport | null | undefined): string {
    const d = (imp?.control_report || {})['devises'] as Record<string, number> | undefined;
    if (!d || !Object.keys(d).length) return '—';
    return Object.entries(d)
      .map(([k, v]) => `${k} (${v})`)
      .join(', ');
  }

  reportNum(imp: RbcmImport, key: string): string {
    const v = (imp.control_report || {})[key];
    return v != null ? String(v) : '—';
  }

  campaignLabel(id: string): string {
    const c = this.ctx.campaigns().find((x) => x.id === id);
    return c ? periodLabel(c) : id.slice(0, 8);
  }

  go(p: number): void {
    this.page.set(p);
    this.load();
  }

  load(): void {
    this.loading.set(true);
    const params: Record<string, string | number> = {
      page: this.page(),
      page_size: this.pageSize,
      file_type: 'BAL_DET',
    };
    const cid = this.ctx.selectedId();
    if (cid) params['campaign_id'] = cid;
    if (this.status) params['status'] = this.status;
    if (this.search) params['search'] = this.search;
    this.api.get<RbcmImportList>(`${RBCM_API}/imports`, params).subscribe({
      next: (r) => {
        this.items.set(r.items);
        this.total.set(r.total);
        this.loading.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Imports indisponibles');
          this.loading.set(false);
        }),
    });
  }

  loadCampaignSources(): void {
    const cid = this.ctx.selectedId();
    if (!cid) {
      this.campaignItems.set([]);
      return;
    }
    this.api.get<RbcmImport[]>(`${RBCM_API}/campaigns/${cid}/imports`).subscribe({
      next: (rows) => this.campaignItems.set(rows.filter((r) => r.file_type === 'BAL_DET')),
      error: () => this.campaignItems.set([]),
    });
  }

  private pickCurrent(rows: RbcmImport[]): RbcmImport | null {
    return (
      rows.find((r) => r.status === 'VALIDATED') ||
      rows.find((r) => r.status === 'ANALYZED') ||
      rows[0] ||
      null
    );
  }

  onFile(ev: Event): void {
    this.file = (ev.target as HTMLInputElement).files?.[0] ?? null;
  }

  upload(): void {
    const cid = this.ctx.selectedId();
    if (!this.file || !cid) {
      this.feedback.warning({
        title: 'SM requise',
        message: 'Sélectionnez une SM avant l’import.',
      });
      return;
    }
    const file = this.file;
    this.feedback
      .run(
        () =>
          this.api.upload<RbcmImport>(`${RBCM_API}/campaigns/${cid}/imports`, file, {
            file_type: 'BAL_DET',
          }),
        {
          busy: this.busy,
          loading: 'Analyse…',
          success: { title: 'Analyse terminée' },
          errorTitle: 'Import impossible',
        },
      )
      .subscribe({
        next: (imp) => {
          this.file = null;
          if (imp.control_report?.['idempotent']) {
            this.feedback.info({
              title: 'Doublon exact',
              message: 'Même empreinte SHA-256 — import existant réutilisé.',
            });
          }
          this.open(imp);
          this.load();
          this.loadCampaignSources();
        },
      });
  }

  open(imp: RbcmImport): void {
    this.drawer.set(imp);
  }

  confirm(imp: RbcmImport, replace: boolean): void {
    if (!this.canConfirm(imp)) {
      this.feedback.warning({
        title: 'Confirmation bloquée',
        message: this.blockingReasons(imp).join(' ') || 'Contrôles bloquants non satisfaits.',
      });
      return;
    }
    this.feedback
      .run(
        () =>
          this.api.post<RbcmImport>(`${RBCM_API}/campaigns/${imp.campaign_id}/imports/${imp.id}/confirm`, {
            replace_validated: replace,
          }),
        {
          busy: this.busy,
          confirm: {
            title: replace ? 'Remplacer l’import validé ?' : 'Confirmer BAL DET ?',
            message: replace
              ? 'L’import validé existant passera SUPERSEDED. Les traces historiques sont conservées.'
              : 'Chargement des soldes NCG et contrôles internes de cohérence.',
            confirmLabel: 'Confirmer',
          },
          loading: 'Confirmation…',
          success: { title: 'BAL DET validée' },
          errorTitle: 'Confirmation impossible',
        },
      )
      .subscribe({
        next: (r) => {
          this.drawer.set(r);
          this.load();
          this.loadCampaignSources();
        },
      });
  }

  download(imp: RbcmImport): void {
    this.feedback
      .run(() => this.api.download(`${RBCM_API}/campaigns/${imp.campaign_id}/imports/${imp.id}/download`), {
        busy: this.busy,
        loading: 'Téléchargement…',
        success: { title: 'Fichier prêt' },
        errorTitle: 'Téléchargement impossible',
      })
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = imp.filename;
          a.click();
          URL.revokeObjectURL(url);
        },
      });
  }

  copySha(imp: RbcmImport): void {
    void navigator.clipboard.writeText(imp.sha256).then(
      () => this.feedback.success({ title: 'SHA-256 copié' }),
      () => this.feedback.warning({ title: 'Copie impossible', message: imp.sha256 }),
    );
  }

  formatSize(bytes: number | null | undefined): string {
    if (bytes == null) return '—';
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} Mo`;
  }

  colsRecognized(imp: RbcmImport): string {
    const cols = (imp.control_report || {})['columns_recognized'] as string[] | undefined;
    return cols?.length ? cols.join(', ') : 'NCG, COMPTE, LIBELLE, DEVISE, DEB, CRE';
  }

  colsMissing(imp: RbcmImport): string {
    const cols = (imp.control_report || {})['columns_missing'] as string[] | undefined;
    return cols?.length ? cols.join(' ; ') : '—';
  }

  canConfirm(imp: RbcmImport): boolean {
    const r = imp.control_report || {};
    if (r['ready_to_confirm'] === false) return false;
    if (r['header_ok'] === false) return false;
    return true;
  }

  canDiscard(imp: RbcmImport): boolean {
    return imp.status === 'ANALYZED' || imp.status === 'REJECTED' || imp.status === 'UPLOADED';
  }

  discard(imp: RbcmImport): void {
    if (!this.canDiscard(imp)) {
      this.feedback.warning({
        title: 'Suppression impossible',
        message:
          'Seul un import non confirmé peut être retiré. Un import validé se remplace ; une SM calculée s’archive.',
      });
      return;
    }
    this.feedback
      .run(() => this.api.delete(`${RBCM_API}/campaigns/${imp.campaign_id}/imports/${imp.id}`), {
        busy: this.busy,
        confirm: {
          title: 'Supprimer cette analyse ?',
          message:
            'Le fichier analysé et son empreinte seront retirés. Vous pourrez réimporter le même fichier. Les imports confirmés ne sont pas concernés.',
          confirmLabel: 'Supprimer',
          tone: 'danger',
        },
        loading: 'Suppression…',
        success: { title: 'Analyse supprimée' },
        errorTitle: 'Suppression impossible',
      })
      .subscribe({
        next: () => {
          if (this.drawer()?.id === imp.id) this.drawer.set(null);
          this.load();
          this.loadCampaignSources();
        },
      });
  }

  blockingReasons(imp: RbcmImport): string[] {
    const raw = (imp.control_report || {})['blocking_reasons'];
    return Array.isArray(raw) ? raw.map(String) : [];
  }

  previewRows(imp: RbcmImport): Record<string, unknown>[] {
    const rows = (imp.control_report || {})['preview'];
    return Array.isArray(rows) ? (rows as Record<string, unknown>[]) : [];
  }

  analysisErrors(imp: RbcmImport): Record<string, unknown>[] {
    const errs = (imp.control_report || {})['errors'];
    return Array.isArray(errs) ? (errs as Record<string, unknown>[]).slice(0, 30) : [];
  }
}
