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
import { AuthService } from '../../core/services/auth.service';
import { MontantPipe, formatMontantOuTiret } from '../../shared/montant.pipe';
import { RbcmCampaignPickerComponent } from '../rbcm-campaign-picker.component';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmPagerComponent } from '../rbcm-pager.component';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import {
  IMPORT_STATUS_LABELS,
  NCG_ORIENTATION_OPERATION_LABELS,
  NCG_ORIENTATION_STATUS_LABELS,
  NCG_STRUCTURE_STATUS_LABELS,
  RBCM_API,
  RbcmImport,
  RbcmImportList,
  RbcmNcgDetail,
  RbcmNcgOrientation,
  RbcmNcgStructure,
  RbcmNcgStructureItem,
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
    MontantPipe,
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
              @if (d.status === 'VALIDATED') {
                <div class="bea-rbcm-quick" style="margin-top:0.65rem">
                  <a
                    class="bea-mg__btn bea-mg__btn--primary"
                    routerLink="/reporting-bcm-sm/rapprochement"
                    [queryParams]="{ campaign: d.campaign_id }"
                  >
                    <mat-icon>fact_check</mat-icon> Contrôler la BAL DET
                  </a>
                </div>
              }
            } @else {
              <div class="bea-rbcm-empty bea-rbcm-empty--compact">
                <mat-icon>upload_file</mat-icon>
                <div><strong>Absent</strong><p>Importez la balance détaillée pour démarrer.</p></div>
              </div>
            }
          </article>
        </section>
      </div>

      @if (ctx.selected(); as c) {
        <section class="bea-mg__panel" aria-label="Structure NCG de la BAL DET">
          <div class="bea-mg__panel-top">
            <div>
              <h2>Structure NCG de la BAL DET</h2>
              <p class="bea-rbcm-sub">
                Comparaison par période avec l’historique des BAL DET validées et le catalogue central.
                Aucune orientation automatique vers une cellule.
              </p>
            </div>
            <div class="bea-rbcm-quick">
              <a
                class="bea-mg__btn bea-mg__btn--ghost"
                routerLink="/reporting-bcm-sm/ncg-revue"
                [queryParams]="{ campaign: c.id }"
              >
                <mat-icon>rule</mat-icon> Revue Comptabilité
              </a>
              <button
                type="button"
                class="bea-mg__btn bea-mg__btn--ghost"
                [disabled]="structureBusy() || !detValidated()"
                (click)="loadStructure()"
              >
                <mat-icon>refresh</mat-icon> Actualiser
              </button>
            </div>
          </div>

          @if (!detValidated()) {
            <p class="bea-rbcm-hint">Confirmez une BAL DET pour comparer la structure des NCG.</p>
          } @else if (structureBusy() && !structure()) {
            <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Analyse de structure…</p></div>
          } @else if (structure(); as s) {
            <div class="bea-fx-kpis bea-rbcm-import-kpis">
              <div class="bea-fx-kpi"><p>NCG période</p><strong>{{ s.ncg_count }}</strong></div>
              <div class="bea-fx-kpi" [attr.data-tone]="(s.counts['nouveau'] || 0) ? 'warn' : null">
                <p>Nouveaux</p><strong>{{ s.counts['nouveau'] || 0 }}</strong>
              </div>
              <div class="bea-fx-kpi">
                <p>Non orientés</p><strong>{{ s.counts['connu_non_oriente'] || 0 }}</strong>
              </div>
              <div class="bea-fx-kpi" data-tone="ok">
                <p>Mappés</p><strong>{{ s.counts['deja_mappe'] || 0 }}</strong>
              </div>
              <div class="bea-fx-kpi">
                <p>Réapparus</p><strong>{{ s.counts['reapparu'] || 0 }}</strong>
              </div>
              <div class="bea-fx-kpi">
                <p>Soldes nuls</p><strong>{{ s.counts['present_zero'] || 0 }}</strong>
              </div>
              <div class="bea-fx-kpi" [attr.data-tone]="(s.counts['absent_mappe'] || 0) ? 'warn' : null">
                <p>Absents mappés</p><strong>{{ s.counts['absent_mappe'] || 0 }}</strong>
              </div>
              <div class="bea-fx-kpi">
                <p>Historique</p><strong>{{ s.history_period_count }} période(s)</strong>
              </div>
            </div>
            <p class="bea-rbcm-hint">
              Périodes disponibles :
              {{ availablePeriodsLabel(s) }}.
              {{ s.note }}
            </p>

            <div class="bea-rbcm-filters">
              <label class="bea-mg__field">
                <mat-icon>filter_list</mat-icon>
                <select
                  [ngModel]="structureFilter()"
                  (ngModelChange)="structureFilter.set($event)"
                  aria-label="Filtrer les NCG par statut"
                >
                  <option value="">Tous les NCG de la période</option>
                  <option value="nouveau">Nouveaux</option>
                  <option value="connu_non_oriente">Connus non orientés</option>
                  <option value="deja_mappe">Déjà mappés</option>
                  <option value="reapparu">Réapparus</option>
                  <option value="present_zero">Soldes nuls</option>
                </select>
              </label>
              <label class="bea-mg__field bea-mg__field--grow">
                <mat-icon>search</mat-icon>
                <input
                  type="search"
                  placeholder="NCG ou libellé…"
                  [ngModel]="structureSearch()"
                  (ngModelChange)="structureSearch.set($event)"
                  aria-label="Rechercher un NCG"
                />
              </label>
            </div>

            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th>NCG</th>
                    <th>Libellé</th>
                    <th>Statut</th>
                    <th>Débit</th>
                    <th>Crédit</th>
                    <th>Cellules catalogue</th>
                    <th>Vu</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of filteredStructureItems(); track row.ncg) {
                    <tr class="bea-rbcm-row" (click)="openNcg(row.ncg)">
                      <td class="bea-rbcm-mono">{{ row.ncg }}</td>
                      <td class="bea-rbcm-ellipsis" [title]="row.libelle || ''">{{ row.libelle || '—' }}</td>
                      <td>
                        <span class="bea-ct-badge" [attr.data-tone]="structureTone(row)">
                          {{ structureStatusLabel(row) }}
                        </span>
                      </td>
                      <td>{{ row.tot_debit | montant }}</td>
                      <td>{{ row.tot_credit | montant }}</td>
                      <td class="bea-rbcm-ellipsis" [title]="cellsLabel(row)">{{ cellsLabel(row) }}</td>
                      <td>
                        {{ row.first_seen_period || '—' }}
                        @if (row.last_seen_period && row.last_seen_period !== row.first_seen_period) {
                          → {{ row.last_seen_period }}
                        }
                      </td>
                    </tr>
                  } @empty {
                    <tr>
                      <td colspan="7">Aucun NCG pour ce filtre.</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>

            @if (s.absents.length) {
              <h3>Absents de cette BAL DET</h3>
              <p class="bea-rbcm-sub">
                NCG mappés ou déjà vus absents ce mois (contribution nulle si mappés).
              </p>
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead>
                    <tr>
                      <th>NCG</th>
                      <th>Statut</th>
                      <th>Cellules</th>
                      <th>Dernière vue</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (row of s.absents.slice(0, 80); track row.ncg) {
                      <tr>
                        <td class="bea-rbcm-mono">{{ row.ncg }}</td>
                        <td>{{ NCG_STRUCTURE_STATUS_LABELS[row.status] || row.status }}</td>
                        <td class="bea-rbcm-ellipsis">{{ absentCellsLabel(row) }}</td>
                        <td>{{ row.last_seen_period || '—' }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              @if (s.absents.length > 80) {
                <p class="bea-rbcm-hint">{{ s.absents.length - 80 }} autre(s) absence(s) non affichée(s).</p>
              }
            }
          }
        </section>
      }

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

          @if (structureFromReport(imp); as ns) {
            <h3>Structure NCG (à la confirmation)</h3>
            <dl class="bea-rbcm-dl">
              <div><dt>Nouveaux</dt><dd>{{ countOf(ns, 'nouveau') }}</dd></div>
              <div><dt>Non orientés</dt><dd>{{ countOf(ns, 'connu_non_oriente') }}</dd></div>
              <div><dt>Mappés</dt><dd>{{ countOf(ns, 'deja_mappe') }}</dd></div>
              <div><dt>Réapparus</dt><dd>{{ countOf(ns, 'reapparu') }}</dd></div>
              <div><dt>Absents mappés</dt><dd>{{ countOf(ns, 'absent_mappe') }}</dd></div>
              <div><dt>Historique</dt><dd>{{ ns['history_period_count'] ?? '—' }} période(s)</dd></div>
            </dl>
            <p class="bea-rbcm-hint">Descriptif uniquement — aucune orientation automatique.</p>
          }

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

      @if (ncgDetail(); as d) {
        <bea-detail-drawer
          [titre]="'NCG ' + d.ncg"
          kicker="Orientation métier"
          [sousTitre]="(d.libelle || 'Sans libellé') + ' · ' + (NCG_STRUCTURE_STATUS_LABELS[d.structure_status || ''] || d.structure_status || '—')"
          [large]="true"
          (fermer)="closeNcg()"
        >
          <p class="bea-rbcm-hint">{{ d.note }}</p>

          <h3>Soldes par période</h3>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead>
                <tr><th>Période</th><th>Présence</th><th>Débit</th><th>Crédit</th></tr>
              </thead>
              <tbody>
                @for (b of d.balances; track b.label) {
                  <tr>
                    <td>{{ b.label }}</td>
                    <td>{{ b.present ? 'Présent' : 'Absent' }}</td>
                    <td>{{ fmtMontant(b.tot_debit) }}</td>
                    <td>{{ fmtMontant(b.tot_credit) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <h3>Mapping catalogue existant</h3>
          @if (d.catalog_mappings.length) {
            <ul class="bea-rbcm-hint">
              @for (m of d.catalog_mappings; track m.cell_ref + m.basis + m.sign) {
                <li>{{ m.cell_ref }} · {{ m.basis }} · signe {{ m.sign }} · {{ m.currency }}</li>
              }
            </ul>
          } @else {
            <p class="bea-rbcm-hint">Aucun mapping exact dans le catalogue central.</p>
          }

          <h3>Orientations</h3>
          @if (d.orientations.length) {
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead>
                  <tr><th>Statut</th><th>Cellule</th><th>Opération</th><th>Devise</th><th></th></tr>
                </thead>
                <tbody>
                  @for (o of d.orientations; track o.id) {
                    <tr>
                      <td>
                        <span class="bea-ct-badge" [attr.data-tone]="orientationTone(o.status)">
                          {{ NCG_ORIENTATION_STATUS_LABELS[o.status] || o.status }}
                        </span>
                      </td>
                      <td>{{ o.cell_ref || '—' }}</td>
                      <td>{{ o.operation ? (NCG_ORIENTATION_OPERATION_LABELS[o.operation] || o.operation) : '—' }}</td>
                      <td>{{ o.currency_scope }}</td>
                      <td (click)="$event.stopPropagation()">
                        <div class="bea-rbcm-quick">
                          @if (o.status === 'A_ORIENTER' && canProposeOrientation()) {
                            <button
                              type="button"
                              class="bea-mg__btn bea-mg__btn--ghost"
                              [disabled]="busy() || !o.cell_ref || !o.operation"
                              [title]="!o.cell_ref || !o.operation ? 'Cellule et opération requises' : ''"
                              (click)="submitOrientation(o)"
                            >Soumettre</button>
                          }
                          @if (o.status === 'EN_ATTENTE_VALIDATION' && canValidateOrientation()) {
                            <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="validateOrientation(o)">Valider</button>
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="rejectOrientation(o)">Rejeter</button>
                          }
                          @if (o.status === 'VALIDE_ACTIF' && canValidateOrientation()) {
                            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="deactivateOrientation(o)">Désactiver</button>
                          }
                        </div>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          } @else {
            <p class="bea-rbcm-hint">Aucune orientation enregistrée — décision métier requise avant activation.</p>
          }

          @if (canProposeOrientation()) {
            <h3>Préparer une orientation</h3>
            <p class="bea-rbcm-hint">Enregistrement = « À orienter » uniquement. Jamais d’activation automatique.</p>
            <div class="bea-rbcm-filters" style="flex-wrap:wrap; gap:0.75rem">
              <label class="bea-mg__field">
                <span>État</span>
                <select [(ngModel)]="oriSheet">
                  <option value="ETAT_A">ETAT A</option>
                  <option value="ETAT_B">ETAT B</option>
                </select>
              </label>
              <label class="bea-mg__field bea-mg__field--grow">
                <span>Cellule SM</span>
                <select [(ngModel)]="oriCell">
                  <option value="">— choisir —</option>
                  @for (c of filteredTargetCells(); track c.cell_ref) {
                    <option [ngValue]="c.cell_ref">{{ c.cell_ref }}</option>
                  }
                </select>
              </label>
              <label class="bea-mg__field">
                <span>Devise</span>
                <select [(ngModel)]="oriCurrency">
                  <option value="ALL">Toutes</option>
                  <option value="LOCAL">MRU / MRO</option>
                  <option value="FX">Devises</option>
                </select>
              </label>
              <label class="bea-mg__field">
                <span>Catégorie</span>
                <select [(ngModel)]="oriResidence">
                  <option value="RESIDENTS">Résidents</option>
                  <option value="NON_RESIDENTS">Non-résidents</option>
                  <option value="ALL">Toutes</option>
                </select>
              </label>
              <label class="bea-mg__field bea-mg__field--grow">
                <span>Opération</span>
                <select [(ngModel)]="oriOperation">
                  <option value="">— choisir —</option>
                  @for (op of d.operations; track op) {
                    <option [ngValue]="op">{{ NCG_ORIENTATION_OPERATION_LABELS[op] || op }}</option>
                  }
                </select>
              </label>
            </div>
            <label class="bea-mg__field bea-mg__field--grow" style="margin-top:0.5rem">
              <span>Notes</span>
              <input type="text" [(ngModel)]="oriNotes" placeholder="Décision métier…" />
            </label>
            <div class="bea-rbcm-quick" style="margin-top:0.75rem">
              <button
                type="button"
                class="bea-mg__btn bea-mg__btn--primary"
                [disabled]="busy() || !oriSheet"
                (click)="prepareOrientation()"
              >
                Enregistrer (À orienter)
              </button>
            </div>
          } @else {
            <p class="bea-rbcm-hint">Lecture seule — permission « mapping.propose » requise pour préparer une orientation.</p>
          }
        </bea-detail-drawer>
      }
    </div>
  `,
})
export class RbcmImportsComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
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
  readonly structure = signal<RbcmNcgStructure | null>(null);
  readonly structureBusy = signal(false);
  readonly structureFilter = signal('');
  readonly structureSearch = signal('');
  readonly ncgDetail = signal<RbcmNcgDetail | null>(null);
  readonly NCG_STRUCTURE_STATUS_LABELS = NCG_STRUCTURE_STATUS_LABELS;
  readonly NCG_ORIENTATION_STATUS_LABELS = NCG_ORIENTATION_STATUS_LABELS;
  readonly NCG_ORIENTATION_OPERATION_LABELS = NCG_ORIENTATION_OPERATION_LABELS;
  oriSheet = 'ETAT_A';
  oriCell = '';
  oriCurrency = 'ALL';
  oriResidence = 'RESIDENTS';
  oriOperation = '';
  oriNotes = '';
  pageSize = 25;
  status = '';
  search = '';
  file: File | null = null;

  readonly detCurrent = computed(() => this.pickCurrent(this.campaignItems()));
  readonly detValidated = computed(() => this.detCurrent()?.status === 'VALIDATED');
  readonly detHistoryCount = computed(() => this.campaignItems().length);
  readonly filteredStructureItems = computed(() => {
    const s = this.structure();
    if (!s) return [] as RbcmNcgStructureItem[];
    const q = this.structureSearch().trim().toLowerCase();
    const filter = this.structureFilter();
    return s.items.filter((row) => {
      if (filter === 'reapparu' && !row.reapparu) return false;
      if (filter === 'present_zero' && !row.present_zero) return false;
      if (filter && filter !== 'reapparu' && filter !== 'present_zero' && row.status !== filter) {
        return false;
      }
      if (!q) return true;
      return (
        row.ncg.toLowerCase().includes(q) ||
        (row.libelle || '').toLowerCase().includes(q)
      );
    });
  });
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
      this.structure.set(null);
      this.structureFilter.set('');
      this.structureSearch.set('');
      this.load();
      this.loadCampaignSources();
    });
    effect(() => {
      const cid = this.ctx.selectedId();
      const det = this.detCurrent();
      const validatedId = det?.status === 'VALIDATED' ? det.id : null;
      if (cid && validatedId) {
        this.loadStructure();
      } else {
        this.structure.set(null);
      }
    });
  }

  ngOnInit(): void {
    this.ctx.applyCampaignQuery(this.route);
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
      return 'BAL DET confirmée — prochaine action : Contrôler la BAL DET.';
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

  loadStructure(): void {
    const cid = this.ctx.selectedId();
    if (!cid || !this.detValidated()) {
      this.structure.set(null);
      return;
    }
    this.structureBusy.set(true);
    this.api.get<RbcmNcgStructure>(`${RBCM_API}/campaigns/${cid}/ncg-structure`).subscribe({
      next: (r) => {
        this.structure.set(r);
        this.structureBusy.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Structure NCG indisponible');
          this.structureBusy.set(false);
        }),
    });
  }

  availablePeriodsLabel(s: RbcmNcgStructure): string {
    const labels = s.available_periods?.map((p) => p.label) || [];
    return labels.length ? labels.join(', ') : 'aucune';
  }

  fmtMontant(value: string | null | undefined): string {
    return formatMontantOuTiret(value);
  }

  structureStatusLabel(row: RbcmNcgStructureItem): string {
    const base = NCG_STRUCTURE_STATUS_LABELS[row.status] || row.status;
    const flags: string[] = [];
    if (row.reapparu) flags.push('réapparu');
    if (row.present_zero) flags.push('solde nul');
    if (row.covered_by_class) flags.push('classe');
    return flags.length ? `${base} · ${flags.join(' · ')}` : base;
  }

  structureTone(row: RbcmNcgStructureItem): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (row.status === 'nouveau') return 'warn';
    if (row.status === 'deja_mappe') return 'ok';
    if (row.status === 'connu_non_oriente') return 'info';
    if (row.reapparu) return 'info';
    return null;
  }

  orientationTone(status: string): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (status === 'VALIDE_ACTIF') return 'ok';
    if (status === 'EN_ATTENTE_VALIDATION') return 'warn';
    if (status === 'A_ORIENTER') return 'info';
    if (status === 'REJETE') return 'danger';
    return null;
  }

  canProposeOrientation(): boolean {
    return this.hasPerm(
      'reporting-bcm-sm.mapping.propose',
      'reporting-bcm-sm.admin',
    );
  }

  canValidateOrientation(): boolean {
    return this.hasPerm(
      'reporting-bcm-sm.mapping.validate',
      'reporting-bcm-sm.admin',
    );
  }

  private hasPerm(...codes: string[]): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const have = u.permission_codes ?? [];
    if (have.includes('*')) return true;
    return codes.some((c) => have.includes(c));
  }

  cellsLabel(row: RbcmNcgStructureItem): string {
    if (!row.cells?.length) return '—';
    return row.cells.map((c) => `${c.cell_ref} (${c.basis})`).join(', ');
  }

  absentCellsLabel(row: { cells: { cell_ref: string }[] }): string {
    if (!row.cells?.length) return '—';
    return row.cells.map((c) => c.cell_ref).join(', ');
  }

  filteredTargetCells(): RbcmNcgDetail['target_cells'] {
    const d = this.ncgDetail();
    if (!d) return [];
    return d.target_cells.filter((c) => c.sheet === this.oriSheet);
  }

  openNcg(ncg: string): void {
    const cid = this.ctx.selectedId();
    if (!cid) return;
    this.busy.set(true);
    this.api.get<RbcmNcgDetail>(`${RBCM_API}/campaigns/${cid}/ncg/${encodeURIComponent(ncg)}/detail`).subscribe({
      next: (d) => {
        this.ncgDetail.set(d);
        this.oriSheet = 'ETAT_A';
        this.oriCell = '';
        this.oriCurrency = 'ALL';
        this.oriResidence = 'RESIDENTS';
        this.oriOperation = '';
        this.oriNotes = '';
        this.busy.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Détail NCG indisponible');
          this.busy.set(false);
        }),
    });
  }

  closeNcg(): void {
    this.ncgDetail.set(null);
  }

  private reloadNcgDetail(): void {
    const d = this.ncgDetail();
    if (!d) return;
    this.openNcg(d.ncg);
  }

  prepareOrientation(): void {
    const d = this.ncgDetail();
    if (!d) return;
    this.feedback
      .run(
        () =>
          this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations`, {
            ncg: d.ncg,
            sheet: this.oriSheet,
            cell_ref: this.oriCell || null,
            operation: this.oriOperation || null,
            currency_scope: this.oriCurrency,
            residence_scope: this.oriResidence,
            ncg_libelle: d.libelle,
            notes: this.oriNotes || null,
          }),
        {
          busy: this.busy,
          loading: 'Enregistrement…',
          success: { title: 'Orientation préparée (non active)' },
          errorTitle: 'Préparation impossible',
        },
      )
      .subscribe({ next: () => this.reloadNcgDetail() });
  }

  submitOrientation(o: RbcmNcgOrientation): void {
    this.feedback
      .run(() => this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/${o.id}/submit`, {}), {
        busy: this.busy,
        confirm: {
          title: 'Soumettre pour validation ?',
          message: 'L’orientation passera en attente. Elle ne sera pas active.',
          confirmLabel: 'Soumettre',
        },
        loading: 'Soumission…',
        success: { title: 'En attente de validation' },
        errorTitle: 'Soumission impossible',
      })
      .subscribe({ next: () => this.reloadNcgDetail() });
  }

  validateOrientation(o: RbcmNcgOrientation): void {
    this.feedback
      .run(() => this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/${o.id}/validate`, {}), {
        busy: this.busy,
        confirm: {
          title: 'Valider et activer ?',
          message: 'L’orientation entrera dans le catalogue central pour les prochains calculs.',
          confirmLabel: 'Valider',
        },
        loading: 'Validation…',
        success: { title: 'Orientation active' },
        errorTitle: 'Validation impossible',
      })
      .subscribe({ next: () => this.reloadNcgDetail() });
  }

  rejectOrientation(o: RbcmNcgOrientation): void {
    this.feedback
      .runWithReason(
        (motif) =>
          this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/${o.id}/reject`, { comment: motif }),
        {
          busy: this.busy,
          reason: {
            title: 'Rejeter cette orientation ?',
            message: 'Motif obligatoire. L’historique est conservé.',
            confirmLabel: 'Rejeter',
            tone: 'danger',
            required: true,
          },
          loading: 'Rejet…',
          success: { title: 'Orientation rejetée' },
          errorTitle: 'Rejet impossible',
        },
      )
      .subscribe({ next: () => this.reloadNcgDetail() });
  }

  deactivateOrientation(o: RbcmNcgOrientation): void {
    this.feedback
      .run(
        () =>
          this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/${o.id}/deactivate`, {
            comment: 'Désactivation',
          }),
        {
          busy: this.busy,
          confirm: {
            title: 'Désactiver sans effacer l’historique ?',
            message: 'L’orientation ne sera plus appliquée aux prochains calculs.',
            confirmLabel: 'Désactiver',
          },
          loading: 'Désactivation…',
          success: { title: 'Orientation désactivée' },
          errorTitle: 'Désactivation impossible',
        },
      )
      .subscribe({ next: () => this.reloadNcgDetail() });
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
          this.loadStructure();
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

  structureFromReport(imp: RbcmImport): Record<string, unknown> | null {
    const raw = (imp.control_report || {})['ncg_structure'];
    return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : null;
  }

  countOf(ns: Record<string, unknown>, key: string): number {
    const counts = ns['counts'];
    if (!counts || typeof counts !== 'object') return 0;
    return Number((counts as Record<string, unknown>)[key] ?? 0);
  }
}
