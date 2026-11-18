import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import { RbcmCampagneDocumentsComponent } from './rbcm-campagne-documents.component';
import { formatMontantOuTiret } from '../../shared/montant.pipe';
import {
  CONTROL_RESULT_LABELS,
  RBCM_API,
  RESOLUTION_LABELS,
  RbcmCampaign,
  RbcmComplements,
  RbcmControlRun,
  RbcmDeleteCheck,
  RbcmHistoryEvent,
  RbcmOwnerCandidate,
  RbcmOwnerHistory,
  RbcmParamCatalog,
  RbcmProgress,
  RbcmReview,
  RbcmReviewFinding,
  RbcmWorkflow,
  WORKFLOW_ACTION_LABELS,
  CELL_STATUS_LABELS,
  CHECK_STATE_TONE,
  DOC_VERDICT_TONE,
  FINDING_CATEGORY_LABELS,
  PREP_VERDICT_TONE,
  PARAM_NATURE_LABELS,
  PARAM_STATUS_LABELS,
  SM_GUIDED_STEPS,
  STATUS_LABELS,
  RbcmCellResult,
  RbcmCellResultList,
  cellKind,
  currentGuidedStep,
  deleteCampaignConfirm,
  guidedStepState,
  paramIsFilled,
  paramStatusTone,
  periodLabel,
  statusTone,
} from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-campagne-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, RouterLink, DatePipe, FormsModule, RbcmStylesComponent, RbcmCampagneDocumentsComponent],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Situation Mensuelle</p>
          <h1>SM {{ camp() ? periodLabel(camp()!) : '…' }}</h1>
          @if (camp(); as c) {
            <p class="bea-rbcm-statusline">
              <span class="bea-ct-badge" [attr.data-tone]="statusTone(c.status)">{{ STATUS_LABELS[c.status] || c.status }}</span>
              <span class="bea-rbcm-hint">Étape {{ displayStep() }} / {{ steps.length }} — {{ stepLabel() }}</span>
            </p>
          }
        </div>
        <div class="bea-mg__actions">
          <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/campagnes">Liste</a>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="reload()">
            <mat-icon>refresh</mat-icon>
          </button>
        </div>
      </header>

      @if (loading()) {
        <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
      } @else if (camp(); as c) {
        <div class="bea-rbcm-grid">
          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Où en est cette SM</h2>
                <p class="bea-rbcm-sub">{{ nextHint() }}</p>
              </div>
            </div>
            <div class="bea-fx-kpis bea-rbcm-hub-kpis">
              <div class="bea-fx-kpi" [attr.data-tone]="progress()?.det_validated ? 'ok' : 'warn'">
                <mat-icon>upload_file</mat-icon>
                <p>BAL DET</p>
                <strong>{{ progress()?.det_validated ? 'Importée' : 'À importer' }}</strong>
              </div>
              <div class="bea-fx-kpi" [attr.data-tone]="controlKpiTone()">
                <mat-icon>fact_check</mat-icon>
                <p>Contrôles</p>
                <strong>{{ controlKpiLabel() }}</strong>
              </div>
              <div class="bea-fx-kpi" [attr.data-tone]="calculatedCells().length ? 'ok' : null">
                <mat-icon>auto_awesome</mat-icon>
                <p>Cellules calculées</p>
                <strong>{{ calculatedCells().length }}</strong>
              </div>
              <div class="bea-fx-kpi" [attr.data-tone]="paramCounts().missing ? 'warn' : 'ok'">
                <mat-icon>edit_note</mat-icon>
                <p>À compléter</p>
                <strong>{{ paramCounts().missing }}</strong>
              </div>
              <div class="bea-fx-kpi" [attr.data-tone]="progress()?.work_document_id ? (progress()?.work_stale ? 'warn' : 'info') : null">
                <mat-icon>description</mat-icon>
                <p>Canevas</p>
                <strong>{{ canvasKpiLabel() }}</strong>
              </div>
              <div class="bea-fx-kpi" [attr.data-tone]="validationKpiTone()">
                <mat-icon>gavel</mat-icon>
                <p>Réglementaire</p>
                <strong>{{ validationKpiLabel() }}</strong>
              </div>
            </div>
            <div class="bea-rbcm-steps">
              @for (s of steps; track s.n) {
                <div class="bea-rbcm-step" [attr.data-state]="guidedStepState(s.n, step())">
                  <mat-icon>{{ stepIcon(s.n) }}</mat-icon>
                  <span>{{ s.n }}. {{ s.label }}</span>
                  <small>{{ stepCaption(s.n) }}</small>
                </div>
              }
            </div>
            <div class="bea-rbcm-quick" style="margin-top:0.85rem">
              @if (primaryCta(); as cta) {
                @if (cta.kind === 'link') {
                  <a class="bea-mg__btn bea-mg__btn--primary" [routerLink]="cta.link" [queryParams]="cta.query">
                    <mat-icon>{{ cta.icon }}</mat-icon> {{ cta.label }}
                  </a>
                } @else {
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--primary"
                    [disabled]="busy() || cta.disabled"
                    [title]="cta.reason || ''"
                    (click)="runPrimary(cta)"
                  >
                    <mat-icon>{{ cta.icon }}</mat-icon> {{ cta.label }}
                  </button>
                }
              }
              @if (step() === 4 || step() >= 5) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="scrollTo('rbcm-docs')">
                  <mat-icon>download</mat-icon> {{ step() >= 5 ? 'Canevas de travail' : 'Saisie dans Excel' }}
                </button>
              }
            </div>
            @if (primaryCta()?.reason) {
              <p class="bea-rbcm-hint" style="margin-top:0.65rem">{{ primaryCta()!.reason }}</p>
            }
            <ul class="bea-rbcm-summary" aria-label="Synthèse de la SM">
              <li><strong>Canevas de travail</strong> {{ canvasKpiLabel() }}</li>
              <li><strong>Informations à compléter</strong> {{ paramCounts().missing }}</li>
              <li><strong>Contrôles</strong> {{ controlKpiLabel() }}</li>
              <li><strong>Validation réglementaire</strong> {{ validationKpiLabel() }}</li>
            </ul>
          </section>

          <section class="bea-mg__panel bea-rbcm-span6">
            <div class="bea-mg__panel-top"><div><h2>Informations de la SM</h2></div></div>
            <dl class="bea-rbcm-dl">
              <div><dt>Période</dt><dd>{{ periodLabel(c) }}</dd></div>
              <div><dt>Créateur</dt><dd>{{ c.preparer_name || '—' }}</dd></div>
              <div><dt>Responsable</dt><dd>{{ c.reporting_owner_name || '—' }}</dd></div>
              <div>
                <dt>Désigné le</dt>
                <dd>{{ c.reporting_owner_set_at ? (c.reporting_owner_set_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</dd>
              </div>
              <div><dt>Créée le</dt><dd>{{ c.created_at | date: 'dd/MM/yyyy HH:mm' }}</dd></div>
            </dl>
            @if (canChangeOwner() && !campaignReadOnly()) {
              <div class="bea-rbcm-form-grid" style="margin-top:0.85rem">
                <label class="bea-mg__field bea-rbcm-form-wide">
                  <mat-icon>person</mat-icon>
                  <select [(ngModel)]="nextOwnerId" name="nextOwner" aria-label="Nouveau responsable">
                    @for (u of owners(); track u.id) {
                      <option [value]="u.id">{{ u.full_name }} — {{ u.email }}</option>
                    }
                  </select>
                </label>
              </div>
              <div class="bea-rbcm-quick" style="margin-top:0.65rem">
                <button
                  type="button"
                  class="bea-mg__btn bea-mg__btn--ghost"
                  [disabled]="busy() || !nextOwnerId || nextOwnerId === c.reporting_owner_id"
                  (click)="changerResponsable()"
                >
                  <mat-icon>swap_horiz</mat-icon> Changer le responsable
                </button>
              </div>
            }
            <div class="bea-rbcm-quick" style="margin-top:0.75rem">
              @if (canChangeOwner() && !campaignReadOnly()) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="editNotes()">
                  <mat-icon>edit</mat-icon> Modifier les notes
                </button>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="supprimer()">
                <mat-icon>delete</mat-icon> Supprimer
              </button>
              @if (deleteCheck()?.can_archive) {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="archiver()">
                  <mat-icon>inventory_2</mat-icon> Archiver
                </button>
              }
              @if (c.status === 'CLOTUREE') {
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="rouvrir()">
                  <mat-icon>lock_open</mat-icon> Rouvrir
                </button>
              }
            </div>
            <p class="bea-rbcm-hint" style="margin-top:0.75rem">
              Suppression possible quel que soit le statut — imports, calculs et documents liés sont retirés définitivement.
            </p>
          </section>

          <section class="bea-mg__panel bea-rbcm-span6">
            <div class="bea-mg__panel-top"><div><h2>Historique du responsable</h2></div></div>
            @if (!ownerHistory().length) {
              <p class="bea-rbcm-hint">Aucune désignation enregistrée.</p>
            } @else {
              <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Date</th><th>De</th><th>Vers</th><th>Motif</th></tr></thead>
                <tbody>
                  @for (h of ownerHistory(); track h.id) {
                    <tr>
                      <td>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>{{ h.from_owner_name || '—' }}</td>
                      <td>{{ h.to_owner_name || '—' }}</td>
                      <td>{{ h.motif }}</td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Contrôles</h2>
                <p class="bea-rbcm-sub">Chaque lancement produit un rapport horodaté. Les rapports précédents restent consultables.</p>
              </div>
            </div>
            @if (!runs().length) {
              <p class="bea-rbcm-hint">Aucun contrôle lancé. Importez la BAL DET puis cliquez sur « Contrôler la SM ».</p>
            } @else {
              <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Date</th><th>Résultat</th><th>Lancé par</th><th class="bea-rbcm-col-actions"></th></tr></thead>
                <tbody>
                  @for (r of runs(); track r.id) {
                    <tr>
                      <td>{{ r.created_at ? (r.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}</td>
                      <td>
                        <span class="bea-ct-badge" [attr.data-tone]="resultTone(r.result)">
                          {{ CONTROL_RESULT_LABELS[r.result] || r.result }}
                        </span>
                      </td>
                      <td>{{ r.actor_name || '—' }}</td>
                      <td class="bea-rbcm-col-actions">
                        <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="voirRapport(r.id)">
                          Consulter
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
            }
            @if (historicRun(); as hr) {
              <div class="bea-rbcm-hint" style="margin-top:0.85rem">
                <p>
                  Rapport du {{ hr.created_at ? (hr.created_at | date: 'dd/MM/yyyy HH:mm') : '—' }}
                  — consultation historique (non modifié).
                </p>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="historicRun.set(null)">Fermer</button>
              </div>
              <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Catégorie</th><th>Intitulé</th><th>État</th><th>Gravité</th></tr></thead>
                <tbody>
                  @for (i of hr.issues || []; track i.id) {
                    <tr>
                      <td>{{ i.category || '—' }}</td>
                      <td>{{ i.title }}</td>
                      <td>{{ RESOLUTION_LABELS[i.resolution_state] || i.resolution_state }}</td>
                      <td>{{ i.severity }}</td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12" id="rbcm-completer">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Cellules manuelles</h2>
                <p class="bea-rbcm-sub">
                  Option A — saisie dans BEA DIGITAL. Les valeurs sont conservées lors des recalculs. Un zéro n’est pas une information complétée.
                </p>
              </div>
              <div class="bea-rbcm-quick">
                <button
                  type="button"
                  class="bea-mg__btn bea-mg__btn--ghost"
                  [disabled]="busy() || !progress()?.det_validated"
                  (click)="calculer()"
                >
                  <mat-icon>calculate</mat-icon> Relancer l’alimentation
                </button>
              </div>
            </div>
            @if (complements()?.technical_failure) {
              <p class="bea-rbcm-hint">Le dernier contrôle a échoué techniquement. Relancez les contrôles avant de clôturer la saisie.</p>
            }
            <div class="bea-rbcm-counts">
              <span class="bea-ct-badge" [attr.data-tone]="paramCounts().missing ? 'warn' : 'ok'">
                {{ paramCounts().missing }} à compléter
              </span>
              <span class="bea-ct-badge" [attr.data-tone]="paramCounts().saisi ? 'ok' : null">
                {{ paramCounts().saisi }} saisi{{ paramCounts().saisi > 1 ? 's' : '' }}
              </span>
              <span class="bea-ct-badge" [attr.data-tone]="paramCounts().calcule ? 'info' : null">
                {{ paramCounts().calcule }} calculé{{ paramCounts().calcule > 1 ? 's' : '' }}
              </span>
            </div>

            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead>
                  <tr>
                    <th>Information</th>
                    <th>Cellule</th>
                    <th>Nature</th>
                    <th>Valeur</th>
                    <th>Statut</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  @for (p of params(); track p.code) {
                    <tr>
                      <td>
                        <strong>{{ p.label }}</strong>
                        <small class="bea-rbcm-hint" style="display:block;margin:0">{{ p.code }}</small>
                      </td>
                      <td class="bea-rbcm-mono">{{ p.cell_hint || '—' }}</td>
                      <td>{{ PARAM_NATURE_LABELS[p.nature || 'manuel'] || p.nature }}</td>
                      <td>{{ displayParamAmount(p.value) }}</td>
                      <td>
                        <span class="bea-ct-badge" [attr.data-tone]="paramStatusTone(p.status)">
                          {{ PARAM_STATUS_LABELS[p.status] || p.status }}
                        </span>
                      </td>
                      <td class="bea-rbcm-col-actions">
                        @if (canSaisir() && !campaignReadOnly()) {
                          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvrirSaisieParam(p)">
                            {{ paramIsFilled(p) ? 'Modifier' : 'Saisir' }}
                          </button>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <p class="bea-rbcm-hint">
              Option B — saisir dans Excel via le canevas de travail (document non validé). Laisser une valeur vide signifie « non renseigné », jamais 0,00.
            </p>

            @if (saisieParam(); as p) {
              <div class="bea-mg__panel" style="margin-top:1rem">
                <div class="bea-mg__panel-top">
                  <div>
                    <h2>{{ paramIsFilled(p) ? 'Modifier' : 'Saisir' }} — {{ p.label }}</h2>
                    <p class="bea-rbcm-sub">{{ p.cell_hint || p.code }} · {{ PARAM_NATURE_LABELS[p.nature || 'manuel'] }}</p>
                  </div>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="saisieParam.set(null)">Annuler</button>
                </div>
                @if (p.code === 'caisse_devises' && caisseProposal()) {
                  <p class="bea-rbcm-hint">Proposition BAL DET : {{ displayParamAmount(caisseProposal()) }}. Confirmation manuelle requise.</p>
                }
                <div class="bea-rbcm-form-grid">
                  <label class="bea-mg__field bea-rbcm-form-wide">
                    <mat-icon>payments</mat-icon>
                    <input [(ngModel)]="saisieForm.value" name="saisieValue" placeholder="Valeur (laisser vide = non renseigné, pas zéro)" />
                  </label>
                  <label class="bea-mg__field">
                    <mat-icon>source</mat-icon>
                    <input [(ngModel)]="saisieForm.source" name="saisieSource" placeholder="Source" />
                  </label>
                  <label class="bea-mg__field">
                    <mat-icon>description</mat-icon>
                    <input [(ngModel)]="saisieForm.justificatif_ref" name="saisieJustifRef" placeholder="Référence justificatif (optionnel)" />
                  </label>
                  <label class="bea-mg__field bea-rbcm-form-wide bea-rbcm-form-textarea">
                    <mat-icon>notes</mat-icon>
                    <textarea rows="3" [(ngModel)]="saisieForm.justification" name="saisieJustif" placeholder="Justification (obligatoire si source absente)"></textarea>
                  </label>
                </div>
                <div class="bea-rbcm-quick" style="margin-top:0.65rem">
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="enregistrerSaisie()">Enregistrer</button>
                </div>
              </div>
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Cellules de la SM</h2>
                <p class="bea-rbcm-sub">Trois listes distinctes — calculé, saisie manuelle, à ajuster. Les totaux de ligne (:H) restent dans Excel.</p>
              </div>
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || campaignReadOnly() || !progress()?.det_validated" (click)="calculer()">
                <mat-icon>calculate</mat-icon> Alimenter depuis la BAL DET
              </button>
            </div>
            @if (!cells().length) {
              <p class="bea-rbcm-hint">Aucun calcul pour cette SM. Importez la BAL DET puis lancez l’alimentation.</p>
            } @else {
              <div class="bea-rbcm-block">
                <h3>Calculé ({{ calculatedCells().length }})</h3>
                <p class="bea-rbcm-hint">Valeurs automatiques depuis la BAL DET. Lecture seule.</p>
                <div class="bea-mg__table-wrap bea-rbcm-table-scroll">
                  <table class="bea-mg__table">
                    <thead>
                      <tr><th>Cellule</th><th>Calculé</th><th>Retenu</th><th>Statut</th></tr>
                    </thead>
                    <tbody>
                      @for (row of calculatedCells(); track row.cell_ref) {
                        <tr>
                          <td class="bea-rbcm-mono">{{ row.cell_ref }}</td>
                          <td>{{ displayCellAmount(row.calculated_value) }}</td>
                          <td>{{ displayCellAmount(row.retained_value) }}</td>
                          <td>
                            <span class="bea-ct-badge" data-tone="ok">{{ CELL_STATUS_LABELS[row.value_status] || row.value_status }}</span>
                          </td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="bea-rbcm-block">
                <h3>Saisie manuelle ({{ manualCells().length }})</h3>
                <p class="bea-rbcm-hint">Cellules alimentées par les paramètres ci-dessus après l’alimentation. A:114:D reste hors paramètre mensuel (D01).</p>
                @if (!manualCells().length) {
                  <p class="bea-rbcm-hint">Aucune cellule manuelle dans le dernier calcul.</p>
                } @else {
                  <div class="bea-mg__table-wrap">
                    <table class="bea-mg__table">
                      <thead>
                        <tr><th>Cellule</th><th>Retenu</th><th>Statut</th></tr>
                      </thead>
                      <tbody>
                        @for (row of manualCells(); track row.cell_ref) {
                          <tr>
                            <td class="bea-rbcm-mono">{{ row.cell_ref }}</td>
                            <td>{{ displayCellAmount(row.retained_value) }}</td>
                            <td>
                              <span class="bea-ct-badge" [attr.data-tone]="row.value_status === 'SAISIE_MANUELLE' ? 'ok' : 'warn'">
                                {{ CELL_STATUS_LABELS[row.value_status] || row.value_status }}
                              </span>
                            </td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              </div>

              <div class="bea-rbcm-block">
                <h3>À ajuster ({{ adjustCells().length }})</h3>
                <p class="bea-rbcm-hint">Lecture seule. Les règles d’ajustement Excel restent en attente des décisions D01/D02.</p>
                @if (!adjustCells().length) {
                  <p class="bea-rbcm-hint">Aucune cellule à ajuster dans le dernier calcul.</p>
                } @else {
                  <div class="bea-mg__table-wrap">
                    <table class="bea-mg__table">
                      <thead>
                        <tr><th>Cellule</th><th>Calculé</th><th>Retenu</th><th>Statut</th></tr>
                      </thead>
                      <tbody>
                        @for (row of adjustCells(); track row.cell_ref) {
                          <tr>
                            <td class="bea-rbcm-mono">{{ row.cell_ref }}</td>
                            <td>{{ displayCellAmount(row.calculated_value) }}</td>
                            <td>{{ displayCellAmount(row.retained_value) }}</td>
                            <td>
                              <span class="bea-ct-badge" data-tone="warn">{{ CELL_STATUS_LABELS[row.value_status] || row.value_status }}</span>
                            </td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              </div>
            }
          </section>

          <div id="rbcm-docs" class="bea-rbcm-span12">
            <bea-rbcm-campagne-documents [campaignId]="c.id" [refreshNonce]="docNonce()" />
          </div>

          <section class="bea-mg__panel bea-rbcm-span12" id="rbcm-prep">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Préparation</h2>
                <p class="bea-rbcm-sub">Synthèse du dossier de travail. Distincte de la validation réglementaire.</p>
              </div>
              @if (review(); as rv) {
                <span class="bea-ct-badge" [attr.data-tone]="PREP_VERDICT_TONE[rv.preparation.verdict]">
                  {{ rv.preparation.verdict_label }}
                </span>
              }
            </div>
            @if (!review()) {
              <p class="bea-rbcm-hint">Chargement de la synthèse…</p>
            } @else {
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead>
                    <tr><th>Contrôle</th><th>État</th><th>Détail</th><th>Action</th></tr>
                  </thead>
                  <tbody>
                    @for (ck of review()!.preparation.checks; track ck.code) {
                      <tr>
                        <td>{{ ck.title }}</td>
                        <td>
                          <span class="bea-ct-badge" [attr.data-tone]="CHECK_STATE_TONE[ck.state]">
                            {{ checkStateLabel(ck.state) }}
                          </span>
                        </td>
                        <td>{{ ck.detail }}</td>
                        <td>{{ ck.action || '—' }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              @if (review()!.preparation.missing_params.length) {
                <p class="bea-rbcm-hint">
                  {{ review()!.preparation.missing_params.length }} information(s) encore à saisir :
                  {{ missingParamLabels() }}.
                </p>
              }
              @if (review()!.preparation.decisions.length || laterItems().length) {
                <p class="bea-rbcm-hint">
                  Validation réglementaire non disponible tant que les décisions métier restent ouvertes.
                  <button type="button" class="bea-rbcm-inline" (click)="openRegulatoryDetails()">Voir les détails</button>
                </p>
              }
              <div class="bea-rbcm-quick" style="margin-top:0.85rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="scrollTo('rbcm-docs')">
                  <mat-icon>description</mat-icon> Générer le canevas SM
                </button>
                @if (review()!.preparation.can_verify) {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="scrollToVerif()">
                    <mat-icon>fact_check</mat-icon> Vérifier le canevas
                  </button>
                } @else {
                  <p class="bea-rbcm-hint">La vérification du canevas s’ouvre après import, contrôles et alimentation.</p>
                }
                @if (canSaisir() && !campaignReadOnly() && progress()?.det_validated) {
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="calculer()">
                    <mat-icon>calculate</mat-icon> {{ review()!.preparation.work_stale ? 'Actualiser le canevas' : 'Relancer l’alimentation' }}
                  </button>
                }
              </div>
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12" id="rbcm-verif">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Vérification du document</h2>
                <p class="bea-rbcm-sub">Contrôle du canevas de travail. N’ouvre pas le circuit Visa / Approbation.</p>
              </div>
              @if (review(); as rv) {
                <span class="bea-ct-badge" [attr.data-tone]="DOC_VERDICT_TONE[rv.verification.verdict]">
                  {{ rv.verification.verdict_label }}
                </span>
              }
            </div>
            @if (!review()) {
              <p class="bea-rbcm-hint">Chargement de la vérification…</p>
            } @else if (!review()!.preparation.can_verify) {
              <p class="bea-rbcm-hint">{{ review()!.verification.findings[0]?.message || 'Conditions de vérification non réunies.' }}</p>
            } @else {
              @if (review()!.verification.stale) {
                <p class="bea-rbcm-hint">Les résultats portent sur une version antérieure. Relancez l’alimentation pour les actualiser.</p>
              }
              @if (!review()!.verification.work_id) {
                <p class="bea-rbcm-hint">Aucun canevas de travail. Générez-le dans Documents après l’alimentation.</p>
              }
              <p class="bea-rbcm-hint">
                Canevas de travail uniquement — mention « Document de travail — non validé ».
                {{ regulatoryUnavailable() ? 'La validation réglementaire reste non disponible.' : '' }}
              </p>
              @for (cat of findingCategories; track cat) {
                <div class="bea-rbcm-block">
                  <h3>{{ FINDING_CATEGORY_LABELS[cat] }}</h3>
                  <div class="bea-mg__table-wrap">
                    <table class="bea-mg__table">
                      <thead>
                        <tr><th>Contrôle</th><th>Feuille / cellule</th><th>Résultat</th><th>Explication</th><th>Action</th></tr>
                      </thead>
                      <tbody>
                        @for (f of findingsOf(cat); track f.code) {
                          <tr>
                            <td>{{ f.title }}</td>
                            <td class="bea-rbcm-mono">{{ f.sheet || '—' }}{{ f.cell ? ' · ' + f.cell : '' }}</td>
                            <td>
                              <span class="bea-ct-badge" [attr.data-tone]="findingTone(f)">
                                {{ findingStatusLabel(f) }}
                              </span>
                            </td>
                            <td>{{ f.message }}</td>
                            <td>{{ f.action || '—' }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                </div>
              }
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12" id="rbcm-valider">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Validation réglementaire</h2>
                <p class="bea-rbcm-sub">
                  Circuit distinct du canevas de travail. Visa contrôleur et approbation n’entrent pas dans le parcours quotidien.
                </p>
              </div>
              <span class="bea-ct-badge" [attr.data-tone]="validationKpiTone()">{{ validationKpiLabel() }}</span>
            </div>
            <ul class="bea-rbcm-summary">
              <li><strong>Canevas de travail</strong> {{ canvasKpiLabel() }} — génération indépendante de ce circuit</li>
              <li><strong>Informations à compléter</strong> {{ paramCounts().missing }}</li>
              <li><strong>Contrôles</strong> {{ controlKpiLabel() }}</li>
              <li><strong>Validation réglementaire</strong> {{ validationKpiLabel() }}</li>
            </ul>
            @if (!workflow()) {
              <p class="bea-rbcm-hint">Chargement du circuit réglementaire…</p>
            } @else {
              <details class="bea-rbcm-reg">
                <summary>Détails de validation réglementaire</summary>
                <dl class="bea-rbcm-dl" style="margin-top:0.85rem">
                  <div><dt>Soumission</dt><dd>{{ workflow()!.submitted.at ? (workflow()!.submitted.at | date: 'dd/MM/yyyy HH:mm') : 'Non soumise' }}</dd></div>
                  <div><dt>Visa contrôleur</dt><dd>{{ workflow()!.control_visa.at ? (workflow()!.control_visa.at | date: 'dd/MM/yyyy HH:mm') : '—' }}</dd></div>
                  <div><dt>Approbation</dt><dd>{{ workflow()!.approved.at ? (workflow()!.approved.at | date: 'dd/MM/yyyy HH:mm') : '—' }}</dd></div>
                  <div><dt>Document final</dt><dd>{{ workflow()!.final_download.allowed ? 'Disponible' : 'Non disponible' }}</dd></div>
                </dl>
                @if (workflow()!.open_gates.length) {
                  <div class="bea-rbcm-block">
                    <h3>Décisions métier encore ouvertes</h3>
                    <p class="bea-rbcm-hint">Elles bloquent uniquement le circuit réglementaire, pas la génération du canevas de travail.</p>
                    <ul class="bea-rbcm-warn-list">
                      @for (g of workflow()!.open_gates; track g.code) {
                        <li>{{ g.code }} — {{ g.label }}</li>
                      }
                    </ul>
                  </div>
                }
                @for (d of review()?.preparation?.decisions || []; track d.code) {
                  <p class="bea-rbcm-hint">{{ d.code }} — {{ d.label }}</p>
                }
                @if (c.status === 'A_CONTROLER') {
                  <p class="bea-rbcm-hint">Dossier soumis : les saisies et l’alimentation sont verrouillées. Un contrôleur peut renvoyer en correction.</p>
                }
                <div class="bea-rbcm-quick" style="margin-top:0.85rem">
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--ghost"
                    [disabled]="busy() || !canPrepareWf() || !workflow()!.submit.allowed"
                    [title]="actionTitle('submit')"
                    (click)="soumettre()"
                  >
                    <mat-icon>{{ workflow()!.submit.allowed ? 'send' : 'lock' }}</mat-icon> Soumettre au contrôle
                  </button>
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--ghost"
                    [disabled]="busy() || !canControlWf() || !workflow()!.control_ok.allowed"
                    [title]="actionTitle('control_ok')"
                    (click)="visaControle()"
                  >
                    <mat-icon>{{ workflow()!.control_ok.allowed ? 'verified' : 'lock' }}</mat-icon> Visa contrôleur
                  </button>
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--ghost"
                    [disabled]="busy() || !canControlWf() || c.status !== 'A_CONTROLER'"
                    [title]="c.status !== 'A_CONTROLER' ? 'Aucun dossier soumis à renvoyer.' : 'Renvoyer en correction'"
                    (click)="rejeter()"
                  >
                    <mat-icon>undo</mat-icon> Renvoyer en correction
                  </button>
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--ghost"
                    [disabled]="busy() || !canApproveWf() || !workflow()!.approve.allowed"
                    [title]="actionTitle('approve')"
                    (click)="approuver()"
                  >
                    <mat-icon>{{ workflow()!.approve.allowed ? 'gavel' : 'lock' }}</mat-icon> Approuver
                  </button>
                  <button
                    type="button"
                    class="bea-mg__btn bea-mg__btn--ghost"
                    [disabled]="busy() || !canExportWf() || !workflow()!.final_download.allowed"
                    [title]="finalDownloadTitle()"
                    (click)="telechargerFinal()"
                  >
                    <mat-icon>{{ workflow()!.final_download.allowed ? 'file_download' : 'lock' }}</mat-icon> Télécharger le document final
                  </button>
                </div>
                <details class="bea-rbcm-tech" style="margin-top:0.85rem">
                  <summary>Messages techniques (API)</summary>
                  @if (!workflow()!.submit.allowed) {
                    <p class="bea-rbcm-hint">Soumission : {{ workflowBlockerText(workflow()!.submit.blockers) || 'non autorisée' }}</p>
                  }
                  @if (!workflow()!.control_ok.allowed) {
                    <p class="bea-rbcm-hint">Visa : {{ workflowBlockerText(workflow()!.control_ok.blockers) || 'non autorisé' }}</p>
                  }
                  @if (!workflow()!.approve.allowed) {
                    <p class="bea-rbcm-hint">Approbation : {{ workflowBlockerText(workflow()!.approve.blockers) || 'non autorisée' }}</p>
                  }
                </details>
                @if (history().length) {
                  <div class="bea-mg__table-wrap" style="margin-top:0.85rem">
                    <table class="bea-mg__table">
                      <thead><tr><th>Date</th><th>Décision</th><th>De → Vers</th><th>Motif</th></tr></thead>
                      <tbody>
                        @for (h of history(); track h.id) {
                          <tr>
                            <td>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                            <td>{{ WORKFLOW_ACTION_LABELS[h.action] || h.action }}</td>
                            <td>{{ h.from_status || '—' }} → {{ h.to_status || '—' }}</td>
                            <td>{{ h.comment || '—' }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              </details>
            }
          </section>

          <section class="bea-mg__panel bea-rbcm-span12">
            <div class="bea-mg__panel-top">
              <div>
                <h2>Accès expert</h2>
                <p class="bea-rbcm-sub">Écrans techniques — hors parcours comptable principal.</p>
              </div>
            </div>
            <div class="bea-rbcm-quick">
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/imports" [queryParams]="{ campaign: c.id }"><mat-icon>upload_file</mat-icon> Imports</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/bal-det"><mat-icon>table_rows</mat-icon> Lignes DET</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/rapprochement" [queryParams]="{ campaign: c.id }"><mat-icon>fact_check</mat-icon> Contrôles</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/parametres"><mat-icon>tune</mat-icon> Paramètres</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/mapping"><mat-icon>account_tree</mat-icon> Correspondances</a>
              <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/archives"><mat-icon>inventory_2</mat-icon> Archives</a>
              @if (progress()?.cond_validated) {
                <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/reporting-bcm-sm/bal-cond"><mat-icon>history</mat-icon> Historique COND</a>
              }
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="openRegulatoryDetails()">
                <mat-icon>gavel</mat-icon> Circuit réglementaire
              </button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="calculer()">
                <mat-icon>calculate</mat-icon> Calcul (expert)
              </button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="exportExcel()">
                <mat-icon>table_view</mat-icon> Export technique
              </button>
            </div>
            @if (history().length) {
              <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Date</th><th>Action</th><th>De → Vers</th></tr></thead>
                <tbody>
                  @for (h of history(); track h.id) {
                    <tr>
                      <td>{{ h.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td>{{ WORKFLOW_ACTION_LABELS[h.action] || h.action }}</td>
                      <td>{{ h.from_status || '—' }} → {{ h.to_status || '—' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
              </div>
            }
          </section>
        </div>
      }
    </div>
  `,
})
export class RbcmCampagneDetailComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly ctx = inject(RbcmContextService);

  readonly STATUS_LABELS = STATUS_LABELS;
  readonly CELL_STATUS_LABELS = CELL_STATUS_LABELS;
  readonly PARAM_STATUS_LABELS = PARAM_STATUS_LABELS;
  readonly PARAM_NATURE_LABELS = PARAM_NATURE_LABELS;
  readonly CONTROL_RESULT_LABELS = CONTROL_RESULT_LABELS;
  readonly RESOLUTION_LABELS = RESOLUTION_LABELS;
  readonly PREP_VERDICT_TONE = PREP_VERDICT_TONE;
  readonly DOC_VERDICT_TONE = DOC_VERDICT_TONE;
  readonly CHECK_STATE_TONE = CHECK_STATE_TONE;
  readonly FINDING_CATEGORY_LABELS = FINDING_CATEGORY_LABELS;
  readonly WORKFLOW_ACTION_LABELS = WORKFLOW_ACTION_LABELS;
  readonly findingCategories = ['structure', 'donnees', 'anomalie'] as const;
  readonly statusTone = statusTone;
  readonly paramStatusTone = paramStatusTone;
  readonly paramIsFilled = paramIsFilled;
  readonly periodLabel = periodLabel;
  readonly guidedStepState = guidedStepState;
  readonly steps = SM_GUIDED_STEPS;

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly camp = signal<RbcmCampaign | null>(null);
  readonly progress = signal<RbcmProgress | null>(null);
  readonly history = signal<RbcmHistoryEvent[]>([]);
  readonly ownerHistory = signal<RbcmOwnerHistory[]>([]);
  readonly owners = signal<RbcmOwnerCandidate[]>([]);
  readonly deleteCheck = signal<RbcmDeleteCheck | null>(null);
  readonly runs = signal<RbcmControlRun[]>([]);
  readonly complements = signal<RbcmComplements | null>(null);
  readonly historicRun = signal<RbcmControlRun | null>(null);
  readonly params = signal<RbcmParamCatalog[]>([]);
  readonly review = signal<RbcmReview | null>(null);
  readonly workflow = signal<RbcmWorkflow | null>(null);
  readonly saisieParam = signal<RbcmParamCatalog | null>(null);
  readonly cells = signal<RbcmCellResult[]>([]);
  readonly docNonce = signal(0);
  saisieForm = { value: '', source: '', justification: '', justificatif_ref: '' };
  nextOwnerId = '';
  private id = '';

  readonly step = computed(() => {
    const c = this.camp();
    return c ? currentGuidedStep(c, this.progress()) : 1;
  });
  readonly displayStep = computed(() => Math.min(this.step(), this.steps.length));
  readonly stepLabel = computed(() => {
    const n = this.step();
    if (n > this.steps.length) return 'Canevas généré';
    return this.steps.find((s) => s.n === n)?.label || '';
  });
  readonly paramCounts = computed(() => {
    const rows = this.params();
    const saisi = rows.filter((p) => p.status === 'SAISI' || p.status === 'VALIDE').length;
    const calcule = rows.filter((p) => p.status === 'CALCULE').length;
    const missing = rows.filter((p) => !paramIsFilled(p)).length;
    return { total: rows.length, saisi, calcule, missing };
  });
  readonly calculatedCells = computed(() =>
    this.cells().filter((r) => !r.cell_ref.endsWith(':H') && cellKind(r.origin) === 'calculated'),
  );
  readonly manualCells = computed(() =>
    this.cells().filter((r) => !r.cell_ref.endsWith(':H') && cellKind(r.origin) === 'manual'),
  );
  readonly adjustCells = computed(() =>
    this.cells().filter((r) => !r.cell_ref.endsWith(':H') && cellKind(r.origin) === 'adjust'),
  );
  readonly laterItems = computed(() =>
    (this.complements()?.items || []).filter(
      (it) => it.category === 'B' || it.category === 'D' || it.item_key === 'FPN:ANNEXES',
    ),
  );
  readonly missingParamLabels = computed(() =>
    (this.review()?.preparation?.missing_params || []).map((p) => p.label).join(', '),
  );

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') || '';
    this.ctx.select(this.id);
    this.reload();
    const frag = this.route.snapshot.fragment;
    if (frag) setTimeout(() => this.scrollTo(frag), 700);
  }

  canChangeOwner(): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const codes = u.permission_codes ?? [];
    return (
      codes.includes('*') ||
      codes.includes('reporting-bcm-sm.prepare') ||
      codes.includes('reporting-bcm-sm.admin')
    );
  }

  readonly primaryCta = computed(() => {
    const c = this.camp();
    const p = this.progress();
    const n = this.step();
    if (!c) return null;
    const q = { campaign: c.id };
    if (n <= 2 && !p?.det_validated) {
      return {
        kind: 'link' as const,
        label: 'Importer la BAL DET',
        icon: this.canImport() ? 'upload_file' : 'lock',
        link: '/reporting-bcm-sm/imports',
        query: q,
        disabled: !this.canImport(),
        reason: this.canImport() ? undefined : 'Permission d’import requise.',
      };
    }
    if (n === 3) {
      return {
        kind: 'link' as const,
        label: 'Contrôler la BAL DET',
        icon: this.canControl() ? 'fact_check' : 'lock',
        link: '/reporting-bcm-sm/rapprochement',
        query: q,
        disabled: !this.canControl(),
        reason: this.canControl() ? undefined : 'Permission de contrôle requise.',
      };
    }
    if (n === 4) {
      return {
        kind: 'scroll' as const,
        label: 'Compléter les cellules manuelles',
        icon: 'edit_note',
        target: 'rbcm-completer',
      };
    }
    return {
      kind: 'scroll' as const,
      label: p?.work_document_id && !p.work_stale ? 'Télécharger le canevas SM' : 'Générer le canevas SM',
      icon: 'description',
      target: 'rbcm-docs',
    };
  });

  controlKpiLabel(): string {
    const p = this.progress();
    if (!p?.det_validated) return 'Après import';
    if (!p.last_control_run_id) return 'À lancer';
    return CONTROL_RESULT_LABELS[p.last_control_result || ''] || 'Exécutés';
  }

  controlKpiTone(): 'ok' | 'warn' | 'danger' | null {
    const r = this.progress()?.last_control_result;
    if (!r) return this.progress()?.det_validated ? 'warn' : null;
    if (r === 'OK') return 'ok';
    if (r === 'BLOCKING' || r === 'FAILED') return 'danger';
    return 'warn';
  }

  canvasKpiLabel(): string {
    const p = this.progress();
    if (!p?.work_document_id) return 'Non généré';
    return p.work_stale ? 'À actualiser' : 'Travail';
  }

  validationKpiLabel(): string {
    const st = this.camp()?.status;
    if (st === 'APPROUVEE' || st === 'CLOTUREE') return STATUS_LABELS[st] || st;
    if (st === 'A_CONTROLER') return 'Soumise';
    if (this.regulatoryUnavailable()) return 'Non disponible';
    return 'Non validée';
  }

  validationKpiTone(): 'ok' | 'warn' | 'info' | null {
    const st = this.camp()?.status;
    if (st === 'APPROUVEE' || st === 'CLOTUREE') return 'ok';
    if (st === 'A_CONTROLER') return 'warn';
    return 'info';
  }

  runPrimary(cta: { kind: string; target?: string }): void {
    if (cta.kind === 'scroll' && cta.target) this.scrollTo(cta.target);
  }

  canControl(): boolean {
    return this.hasPerm(
      'reporting-bcm-sm.prepare',
      'reporting-bcm-sm.control',
      'reporting-bcm-sm.import',
      'reporting-bcm-sm.admin',
    );
  }

  canSaisir(): boolean {
    return this.hasPerm(
      'reporting-bcm-sm.parameters.write',
      'reporting-bcm-sm.prepare',
      'reporting-bcm-sm.control',
      'reporting-bcm-sm.correct',
      'reporting-bcm-sm.admin',
    );
  }

  canImport(): boolean {
    return this.hasPerm(
      'reporting-bcm-sm.import',
      'reporting-bcm-sm.prepare',
      'reporting-bcm-sm.control',
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

  nextHint(): string {
    const p = this.progress();
    if (!p?.det_validated) return 'Étape suivante : importer et confirmer la BAL DET.';
    if (!p.last_control_run_id) return 'Étape suivante : lancer les contrôles de la SM.';
    const missing = this.paramCounts().missing;
    if (missing > 0) return `${missing} information(s) à saisir. Le canevas de travail reste générable.`;
    if (!this.cells().length) return 'Paramètres enregistrés. Alimentez la SM depuis la BAL DET.';
    if (p.work_stale) return 'Les données ont changé. Régénérez le canevas de travail.';
    if (!p.work_document_id) return 'Prochaine action : générer le canevas SM (document de travail, non validé).';
    return 'Canevas de travail disponible. La validation réglementaire est un circuit distinct.';
  }

  campaignLocked(): boolean {
    const st = this.camp()?.status;
    return st === 'APPROUVEE' || st === 'CLOTUREE';
  }

  campaignReadOnly(): boolean {
    return this.campaignLocked() || this.camp()?.status === 'A_CONTROLER';
  }

  caisseProposal(): string | null {
    const it = (this.complements()?.items || []).find((row) => row.parameter_code === 'caisse_devises');
    if (!it) return null;
    if (it.proposed_value) return it.proposed_value;
    const fromDetails = it.details?.['proposed_value'];
    return typeof fromDetails === 'string' ? fromDetails : null;
  }

  resultTone(result: string): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (result === 'OK') return 'ok';
    if (result === 'BLOCKING' || result === 'FAILED') return 'danger';
    if (result === 'INCOMPLETE' || result === 'DECISIONS_PENDING') return 'warn';
    return 'info';
  }

  displayParamAmount(value: string | number | null | undefined): string {
    if (value == null || value === '') return '—';
    return formatMontantOuTiret(String(value));
  }

  stepIcon(n: number): string {
    const st = guidedStepState(n, this.step());
    if (st === 'done') return 'check_circle';
    if (st === 'current') return 'play_circle';
    if (st === 'blocked') return 'lock';
    return 'radio_button_unchecked';
  }

  stepCaption(n: number): string {
    const st = guidedStepState(n, this.step());
    if (st === 'done') return 'Terminé';
    if (st === 'current') return 'En cours';
    return 'À venir';
  }

  checkStateLabel(state: string): string {
    if (state === 'ok') return 'OK';
    if (state === 'fail') return 'Blocage';
    if (state === 'missing') return 'À compléter';
    if (state === 'stale') return 'À actualiser';
    return 'En attente';
  }

  findingsOf(cat: string): RbcmReviewFinding[] {
    return (this.review()?.verification?.findings || []).filter((f) => f.category === cat);
  }

  findingTone(f: RbcmReviewFinding): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (f.severity === 'blocking' && f.status === 'fail') return 'danger';
    if (f.status === 'ok') return 'ok';
    if (f.status === 'pending') return 'warn';
    if (f.severity === 'warning') return 'warn';
    return 'info';
  }

  findingStatusLabel(f: RbcmReviewFinding): string {
    if (f.status === 'ok') return 'OK';
    if (f.status === 'pending') return 'En attente';
    if (f.severity === 'blocking') return 'Blocage';
    return 'Avertissement';
  }

  scrollTo(id: string): void {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  scrollToVerif(): void {
    this.scrollTo('rbcm-verif');
  }

  scrollToValider(): void {
    this.scrollTo('rbcm-valider');
  }

  openRegulatoryDetails(): void {
    setTimeout(() => {
      const el = document.querySelector('#rbcm-valider details.bea-rbcm-reg') as HTMLDetailsElement | null;
      if (el) el.open = true;
      this.scrollTo('rbcm-valider');
    }, 50);
  }

  regulatoryUnavailable(): boolean {
    const st = this.camp()?.status;
    if (st === 'APPROUVEE' || st === 'CLOTUREE') return false;
    const wf = this.workflow();
    if (!wf) return true;
    return !wf.can_finalize_regulatory || wf.open_gates.length > 0;
  }

  reload(): void {
    this.loading.set(true);
    this.api.get<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}`).subscribe({
      next: (c) => {
        this.camp.set(c);
        this.nextOwnerId = c.reporting_owner_id || '';
        this.loading.set(false);
        this.api.get<RbcmProgress>(`${RBCM_API}/campaigns/${this.id}/progress`).subscribe((p) => this.progress.set(p));
        this.api.get<{ items: RbcmControlRun[] }>(`${RBCM_API}/campaigns/${this.id}/controls/runs`).subscribe({
          next: (r) => this.runs.set(r.items || []),
          error: () => this.runs.set([]),
        });
        this.api.get<RbcmComplements>(`${RBCM_API}/campaigns/${this.id}/complements`).subscribe({
          next: (cplt) => this.complements.set(cplt),
          error: () => this.complements.set(null),
        });
        this.api.get<RbcmParamCatalog[]>(`${RBCM_API}/campaigns/${this.id}/parameters`).subscribe({
          next: (rows) => this.params.set(rows || []),
          error: () => this.params.set([]),
        });
        this.api.get<RbcmReview>(`${RBCM_API}/campaigns/${this.id}/review`).subscribe({
          next: (rev) => this.review.set(rev),
          error: () => this.review.set(null),
        });
        this.api.get<RbcmWorkflow>(`${RBCM_API}/campaigns/${this.id}/workflow`).subscribe({
          next: (wf) => this.workflow.set(wf),
          error: () => this.workflow.set(null),
        });
        this.api.get<RbcmHistoryEvent[]>(`${RBCM_API}/campaigns/${this.id}/history`).subscribe((h) => this.history.set(h));
        this.api
          .get<RbcmOwnerHistory[]>(`${RBCM_API}/campaigns/${this.id}/reporting-owner/history`)
          .subscribe((h) => this.ownerHistory.set(h));
        this.api.get<RbcmDeleteCheck>(`${RBCM_API}/campaigns/${this.id}/delete-check`).subscribe((d) => this.deleteCheck.set(d));
        this.api.get<RbcmCellResultList>(`${RBCM_API}/campaigns/${this.id}/cells`).subscribe({
          next: (res) => this.cells.set(res.items || []),
          error: () => this.cells.set([]),
        });
        if (this.canChangeOwner()) {
          this.api.get<RbcmOwnerCandidate[]>(`${RBCM_API}/preparateurs`).subscribe({
            next: (rows) => this.owners.set(rows),
            error: () => this.owners.set([]),
          });
        }
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'SM introuvable');
          this.loading.set(false);
        }),
    });
  }

  changerResponsable(): void {
    const c = this.camp();
    if (!c || !this.nextOwnerId || this.nextOwnerId === c.reporting_owner_id) return;
    const dest = this.owners().find((u) => u.id === this.nextOwnerId);
    this.feedback
      .runWithReason(
        (motif) =>
          this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}/reporting-owner`, {
            reporting_owner_id: this.nextOwnerId,
            motif,
          }),
        {
          busy: this.busy,
          reason: {
            title: 'Changer le responsable ?',
            message: `Nouveau responsable : ${dest?.full_name || 'sélectionné'}. Le motif est obligatoire.`,
            confirmLabel: 'Enregistrer',
            required: true,
          },
          loading: 'Enregistrement…',
          success: { title: 'Responsable mis à jour' },
          errorTitle: 'Changement impossible',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  editNotes(): void {
    const c = this.camp();
    if (!c) return;
    this.feedback
      .runWithReason(
        (notes) => this.api.patch<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}`, { notes }),
        {
          busy: this.busy,
          reason: {
            title: 'Modifier les notes',
            message: periodLabel(c),
            confirmLabel: 'Enregistrer',
            reasonLabel: 'Notes',
            required: false,
          },
          loading: 'Enregistrement…',
          success: { title: 'SM mise à jour' },
          errorTitle: 'Modification impossible',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  rouvrir(): void {
    const c = this.camp();
    if (!c) return;
    this.feedback
      .runWithReason(
        (comment) => this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}/reopen`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Réouverture contrôlée',
            message: 'Une nouvelle version sera créée. Les anciennes versions sont conservées.',
            confirmLabel: 'Rouvrir',
            reasonLabel: 'Motif',
            required: true,
          },
          loading: 'Réouverture…',
          success: { title: 'Nouvelle version créée' },
          errorTitle: 'Réouverture impossible',
        },
      )
      .subscribe({
        next: (n) => {
          this.ctx.select(n.id);
          void this.router.navigate(['/reporting-bcm-sm/campagnes', n.id]);
        },
      });
  }

  supprimer(): void {
    const c = this.camp();
    if (!c) return;
    this.feedback
      .run(() => this.api.delete(`${RBCM_API}/campaigns/${this.id}`), {
        busy: this.busy,
        confirm: {
          title: 'Supprimer ?',
          message: deleteCampaignConfirm(c, this.deleteCheck()),
          confirmLabel: 'Supprimer',
          tone: 'danger',
        },
        loading: 'Suppression…',
        success: { title: 'SM supprimée' },
        errorTitle: 'Suppression impossible',
      })
      .subscribe({ next: () => void this.router.navigate(['/reporting-bcm-sm/campagnes']) });
  }

  archiver(): void {
    this.feedback
      .runWithReason(
        (comment) => this.api.post(`${RBCM_API}/campaigns/${this.id}/archive`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Archiver ?',
            message: 'Données conservées, statut CLOTUREE.',
            confirmLabel: 'Archiver',
            required: false,
          },
          loading: 'Archivage…',
          success: { title: 'SM archivée' },
          errorTitle: 'Archivage impossible',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  lancerControles(): void {
    this.feedback
      .run(() => this.api.post<RbcmControlRun>(`${RBCM_API}/campaigns/${this.id}/controls/runs`, {}), {
        busy: this.busy,
        loading: 'Contrôles en cours…',
        success: { title: 'Contrôles enregistrés' },
        errorTitle: 'Contrôles impossibles',
      })
      .subscribe({
        next: () => {
          this.historicRun.set(null);
          this.saisieParam.set(null);
          this.reload();
        },
      });
  }

  voirRapport(runId: string): void {
    this.api.get<RbcmControlRun>(`${RBCM_API}/campaigns/${this.id}/controls/runs/${runId}`).subscribe({
      next: (r) => this.historicRun.set(r),
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Rapport introuvable')),
    });
  }

  ouvrirSaisieParam(p: RbcmParamCatalog): void {
    const proposal = p.code === 'caisse_devises' ? this.caisseProposal() : null;
    this.saisieForm = {
      value: p.value || proposal || '',
      source: p.source || '',
      justification: p.justification || '',
      justificatif_ref: p.justificatif_ref || '',
    };
    this.saisieParam.set(p);
  }

  enregistrerSaisie(): void {
    const p = this.saisieParam();
    if (!p) return;
    const value = this.saisieForm.value.trim() === '' ? null : this.saisieForm.value.trim();
    this.feedback
      .run(
        () =>
          this.api.post(`${RBCM_API}/campaigns/${this.id}/parameters`, {
            parameter_code: p.code,
            value,
            source: this.saisieForm.source || null,
            justification: this.saisieForm.justification || null,
            justificatif_ref: this.saisieForm.justificatif_ref || null,
            expected_value_id: p.value_id,
          }),
        {
          busy: this.busy,
          loading: 'Enregistrement…',
          success: { title: 'Information enregistrée' },
          errorTitle: 'Saisie impossible',
        },
      )
      .subscribe({
        next: () => {
          this.saisieParam.set(null);
          this.reload();
        },
      });
  }

  calculer(): void {
    this.feedback
      .run(() => this.api.post(`${RBCM_API}/campaigns/${this.id}/calculate`, {}), {
        busy: this.busy,
        loading: 'Alimentation depuis la BAL DET…',
        success: { title: 'SM alimentée' },
        errorTitle: 'Calcul impossible',
      })
      .subscribe({
        next: () => {
          this.docNonce.update((n) => n + 1);
          this.reload();
        },
      });
  }

  displayCellAmount(value: string | number | null | undefined): string {
    if (value == null || value === '') return '—';
    return formatMontantOuTiret(String(value));
  }

  canPrepareWf(): boolean {
    return this.hasPerm('reporting-bcm-sm.prepare', 'reporting-bcm-sm.admin');
  }

  canControlWf(): boolean {
    return this.hasPerm('reporting-bcm-sm.control', 'reporting-bcm-sm.admin');
  }

  canApproveWf(): boolean {
    return this.hasPerm('reporting-bcm-sm.approve', 'reporting-bcm-sm.admin');
  }

  canExportWf(): boolean {
    return this.hasPerm('reporting-bcm-sm.export', 'reporting-bcm-sm.admin');
  }

  workflowBlockerText(blockers: { code: string; title: string; message: string }[]): string {
    if (!blockers.length) return '';
    return blockers.map((b) => b.message).join(' ');
  }

  actionTitle(kind: 'submit' | 'approve' | 'control_ok'): string {
    const wf = this.workflow();
    if (!wf) return 'Chargement…';
    if (kind === 'submit' && !this.canPrepareWf()) return 'Permission reporting-bcm-sm.prepare requise';
    if (kind === 'approve' && !this.canApproveWf()) return 'Permission reporting-bcm-sm.approve requise';
    if (kind === 'control_ok' && !this.canControlWf()) return 'Permission reporting-bcm-sm.control requise';
    const action = wf[kind];
    if (action.allowed) {
      if (kind === 'submit') return 'Soumettre la dernière version vérifiée';
      if (kind === 'approve') return 'Approuver le dossier soumis';
      return 'Enregistrer le visa du contrôleur';
    }
    return this.workflowBlockerText(action.blockers) || 'Action bloquée';
  }

  finalDownloadTitle(): string {
    const wf = this.workflow();
    if (!wf) return 'Chargement…';
    if (!this.canExportWf()) return 'Permission reporting-bcm-sm.export requise';
    if (wf.final_download.allowed) return `Télécharger ${wf.final_download.filename}`;
    return this.workflowBlockerText(wf.final_download.blockers);
  }

  soumettre(): void {
    const wf = this.workflow();
    if (!wf?.submit.allowed) return;
    this.feedback
      .runWithReason(
        (comment) => this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}/workflow/submit-control`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Soumettre au contrôle ?',
            message: 'La dernière vérification et le canevas actuel seront figés pour le contrôle. Commentaire optionnel.',
            confirmLabel: 'Soumettre',
            required: false,
          },
          loading: 'Soumission…',
          success: { title: 'SM soumise au contrôle' },
          errorTitle: 'Soumission refusée',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  visaControle(): void {
    if (!this.workflow()?.control_ok.allowed) return;
    this.feedback
      .runWithReason(
        (comment) => this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}/workflow/control-ok`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Visa du contrôleur ?',
            message: 'Le préparateur ne peut pas viser sa propre SM.',
            confirmLabel: 'Enregistrer le visa',
            required: false,
          },
          loading: 'Enregistrement…',
          success: { title: 'Visa enregistré' },
          errorTitle: 'Visa refusé',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  rejeter(): void {
    this.feedback
      .runWithReason(
        (comment) => this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}/workflow/reject`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Renvoyer en correction ?',
            message: 'Le dossier redevient modifiable. Le motif est obligatoire.',
            confirmLabel: 'Renvoyer',
            required: true,
          },
          loading: 'Renvoi…',
          success: { title: 'Dossier renvoyé en correction' },
          errorTitle: 'Renvoi impossible',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  approuver(): void {
    if (!this.workflow()?.approve.allowed) return;
    this.feedback
      .runWithReason(
        (comment) => this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${this.id}/workflow/approve`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Approuver la SM ?',
            message: 'Le canevas actuel sera figé comme document final. Auto-approbation interdite.',
            confirmLabel: 'Approuver',
            required: false,
          },
          loading: 'Approbation…',
          success: { title: 'SM approuvée' },
          errorTitle: 'Approbation refusée',
        },
      )
      .subscribe({ next: () => this.reload() });
  }

  telechargerFinal(): void {
    const wf = this.workflow();
    if (!wf?.final_download.allowed) return;
    this.feedback
      .run(
        () => this.api.download(`${RBCM_API}/campaigns/${this.id}/documents/final/download`),
        {
          busy: this.busy,
          loading: 'Téléchargement du document final…',
          success: { title: 'Fichier prêt' },
          errorTitle: 'Téléchargement final impossible',
        },
      )
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = wf.final_download.filename || 'SM.xlsx';
          a.click();
          URL.revokeObjectURL(url);
        },
      });
  }

  exportExcel(): void {
    this.feedback
      .run(
        () =>
          this.api.post<{ id: string; filename: string }>(`${RBCM_API}/campaigns/${this.id}/exports/excel`, {}),
        {
          busy: this.busy,
          loading: 'Export…',
          success: { title: 'Excel généré' },
          errorTitle: 'Export impossible',
        },
      )
      .subscribe({
        next: (d) => {
          if (!d?.id) return;
          this.feedback
            .run(
              () => this.api.download(`${RBCM_API}/campaigns/${this.id}/exports/${d.id}/download`),
              {
                busy: this.busy,
                loading: 'Téléchargement…',
                success: { title: 'Fichier prêt' },
                errorTitle: 'Téléchargement impossible',
              },
            )
            .subscribe({
              next: (blob) => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = d.filename || 'export-bcm.xlsx';
                a.click();
                URL.revokeObjectURL(url);
              },
            });
        },
      });
  }
}
