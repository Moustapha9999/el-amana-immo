import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DetailDrawerComponent } from '../../contrats-echeances/shared/detail-drawer.component';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { formatMontantOuTiret } from '../../shared/montant.pipe';
import { RbcmCampaignPickerComponent } from '../rbcm-campaign-picker.component';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import {
  NCG_ORIENTATION_OPERATION_LABELS,
  NCG_ORIENTATION_STATUS_LABELS,
  NCG_STRUCTURE_STATUS_LABELS,
  RBCM_API,
  RbcmNcgOrientation,
  RbcmNcgReviewBoard,
  RbcmNcgReviewRow,
} from '../rbcm.models';

type BoardTab = 'a_reviser' | 'en_attente' | 'actives' | 'rejetees' | 'desactivees';
type RowFilter = '' | 'nouveau' | 'connu_non_oriente' | 'deferred';

@Component({
  selector: 'bea-rbcm-ncg-revue',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    MatIconModule,
    RouterLink,
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
          <h1>Revue orientations NCG</h1>
          <p class="bea-rbcm-sub">
            Décisions Comptabilité avant activation — aucune orientation automatique.
          </p>
        </div>
        <div class="bea-rbcm-quick">
          @if (ctx.selectedId(); as cid) {
            <a
              class="bea-mg__btn bea-mg__btn--ghost"
              routerLink="/reporting-bcm-sm/imports"
              [queryParams]="{ campaign: cid }"
            >
              <mat-icon>upload_file</mat-icon> Structure NCG
            </a>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="reload()">
            <mat-icon>refresh</mat-icon> Actualiser
          </button>
        </div>
      </header>

      <bea-rbcm-campaign-picker />

      @if (!ctx.selectedId()) {
        <div class="bea-rbcm-empty"><mat-icon>calendar_month</mat-icon><p>Sélectionnez une situation mensuelle.</p></div>
      } @else if (loading()) {
        <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement de la revue…</p></div>
      } @else if (board(); as b) {
        @if (!b.has_validated_det) {
          <div class="bea-rbcm-empty">
            <mat-icon>upload_file</mat-icon>
            <p>Confirmez une BAL DET pour examiner les NCG de {{ boardPeriodLabel(b) }}.</p>
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/reporting-bcm-sm/imports" [queryParams]="{ campaign: b.campaign_id }">
              Aller aux imports
            </a>
          </div>
        } @else {
          <p class="bea-rbcm-hint">{{ b.note }}</p>

          <div class="bea-fx-kpis bea-rbcm-import-kpis">
            <button type="button" class="bea-fx-kpi" [attr.data-tone]="(b.structure_counts['nouveau'] || 0) ? 'warn' : null" (click)="showNouveaux()">
              <p>Nouveaux</p><strong>{{ b.structure_counts['nouveau'] || 0 }}</strong>
            </button>
            <button type="button" class="bea-fx-kpi" data-tone="info" (click)="showNonOrientes()">
              <p>Non orientés</p><strong>{{ b.structure_counts['connu_non_oriente'] || 0 }}</strong>
            </button>
            <button type="button" class="bea-fx-kpi" (click)="showDeferred()">
              <p>Différés</p><strong>{{ deferredCount() }}</strong>
            </button>
            <button type="button" class="bea-fx-kpi" [attr.data-tone]="(b.orientation_counts['en_attente'] || 0) ? 'warn' : null" (click)="tab.set('en_attente'); rowFilter.set('')">
              <p>En attente</p><strong>{{ b.orientation_counts['en_attente'] || 0 }}</strong>
            </button>
            <button type="button" class="bea-fx-kpi" data-tone="ok" (click)="tab.set('actives'); rowFilter.set('')">
              <p>Actives</p><strong>{{ b.orientation_counts['actif'] || 0 }}</strong>
            </button>
            <button type="button" class="bea-fx-kpi" [attr.data-tone]="(b.orientation_counts['rejete'] || 0) ? 'danger' : null" (click)="tab.set('rejetees'); rowFilter.set('')">
              <p>Rejetées</p><strong>{{ b.orientation_counts['rejete'] || 0 }}</strong>
            </button>
            <button type="button" class="bea-fx-kpi" (click)="tab.set('desactivees'); rowFilter.set('')">
              <p>Désactivées</p><strong>{{ b.orientation_counts['desactive'] || 0 }}</strong>
            </button>
          </div>

          <div class="bea-rbcm-filters">
            <label class="bea-mg__field">
              <mat-icon>filter_list</mat-icon>
              <select [ngModel]="tab()" (ngModelChange)="onTabChange($event)" aria-label="Vue revue">
                <option value="a_reviser">NCG à examiner</option>
                <option value="en_attente">Orientations en attente</option>
                <option value="actives">Orientations actives</option>
                <option value="rejetees">Orientations rejetées</option>
                <option value="desactivees">Orientations désactivées</option>
              </select>
            </label>
            @if (tab() === 'a_reviser') {
              <label class="bea-mg__field">
                <select [ngModel]="rowFilter()" (ngModelChange)="rowFilter.set($event)" aria-label="Filtrer les NCG">
                  <option value="">Tous à examiner</option>
                  <option value="nouveau">Nouveaux uniquement</option>
                  <option value="connu_non_oriente">Connus non orientés</option>
                  <option value="deferred">Décisions différées</option>
                </select>
              </label>
            }
            <label class="bea-mg__field bea-mg__field--grow">
              <mat-icon>search</mat-icon>
              <input
                type="search"
                placeholder="NCG ou libellé…"
                [ngModel]="search()"
                (ngModelChange)="search.set($event)"
                aria-label="Rechercher"
              />
            </label>
          </div>

          @if (tab() === 'a_reviser') {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top">
                <div>
                  <h2>NCG nouveaux et connus non orientés</h2>
                  <p class="bea-rbcm-sub">{{ filteredRows().length }} ligne(s) — décision métier requise avant activation.</p>
                </div>
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
                      <th>Proposition</th>
                      <th>Décision</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (row of filteredRows(); track row.ncg) {
                      <tr class="bea-rbcm-row" (click)="openRow(row)">
                        <td class="bea-rbcm-mono">{{ row.ncg }}</td>
                        <td class="bea-rbcm-ellipsis" [title]="row.libelle || ''">{{ row.libelle || '—' }}</td>
                        <td>
                          <span class="bea-ct-badge" [attr.data-tone]="structureTone(row)">
                            {{ structureLabel(row) }}
                          </span>
                        </td>
                        <td>{{ fmtMontant(row.tot_debit) }}</td>
                        <td>{{ fmtMontant(row.tot_credit) }}</td>
                        <td>
                          @if (row.proposed_cell_ref) {
                            {{ row.proposed_cell_ref }}
                            · {{ opLabel(row.proposed_operation) }}
                            · {{ currencyLabel(row.latest_orientation?.currency_scope) }}
                            · {{ statusLabel(row.proposed_status) }}
                          } @else if (row.decision_deferred) {
                            Sans orientation (différé)
                          } @else {
                            —
                          }
                        </td>
                        <td>{{ row.needs_decision ? 'À traiter' : '—' }}</td>
                      </tr>
                    } @empty {
                      <tr><td colspan="7">Aucun NCG à examiner pour ce filtre.</td></tr>
                    }
                  </tbody>
                </table>
              </div>
            </section>
          } @else {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top">
                <div>
                  <h2>{{ orientationTabTitle() }}</h2>
                  <p class="bea-rbcm-sub">{{ filteredOrientations().length }} orientation(s)</p>
                </div>
              </div>
              <div class="bea-mg__table-wrap">
                <table class="bea-mg__table">
                  <thead>
                    <tr>
                      <th>NCG</th>
                      <th>Statut</th>
                      <th>Cellule</th>
                      <th>Opération</th>
                      <th>Devise</th>
                      <th>Motif</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (o of filteredOrientations(); track o.id) {
                      <tr class="bea-rbcm-row" (click)="openOrientation(o)">
                        <td class="bea-rbcm-mono">{{ o.ncg }}</td>
                        <td>
                          <span class="bea-ct-badge" [attr.data-tone]="orientationTone(o.status)">
                            {{ statusLabel(o.status) }}
                          </span>
                        </td>
                        <td>{{ o.cell_ref || '—' }}</td>
                        <td>{{ opLabel(o.operation) }}</td>
                        <td>{{ currencyLabel(o.currency_scope) }}</td>
                        <td class="bea-rbcm-ellipsis" [title]="o.decision_comment || o.notes || ''">
                          {{ o.decision_comment || o.notes || '—' }}
                        </td>
                      </tr>
                    } @empty {
                      <tr><td colspan="6">Aucune orientation dans cette vue.</td></tr>
                    }
                  </tbody>
                </table>
              </div>
            </section>
          }
        }
      }

      @if (selected(); as row) {
        <bea-detail-drawer
          [titre]="'NCG ' + row.ncg"
          kicker="Revue Comptabilité"
          [sousTitre]="(row.libelle || 'Sans libellé') + ' · ' + structureLabel(row)"
          [large]="true"
          (fermer)="close()"
        >
          <h3>Présence BAL DET</h3>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th>Période</th><th>Présence</th><th>Débit</th><th>Crédit</th></tr></thead>
              <tbody>
                @for (bal of row.balances; track bal.label) {
                  <tr>
                    <td>{{ bal.label }}</td>
                    <td>{{ bal.present ? 'Présent' : 'Absent' }}</td>
                    <td>{{ fmtMontant(bal.tot_debit) }}</td>
                    <td>{{ fmtMontant(bal.tot_credit) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <h3>Devises & comptes (échantillon)</h3>
          <p class="bea-rbcm-hint">
            Devises : {{ row.devises.length ? row.devises.join(', ') : '—' }}
            · {{ row.line_count }} ligne(s) DET
          </p>
          @if (row.comptes.length) {
            <div class="bea-mg__table-wrap">
              <table class="bea-mg__table">
                <thead><tr><th>Compte</th><th>Devise</th><th>Débit</th><th>Crédit</th></tr></thead>
                <tbody>
                  @for (c of row.comptes; track c.compte + (c.devise || '') + c.debit + c.credit) {
                    <tr>
                      <td>{{ c.compte || '—' }}</td>
                      <td>{{ c.devise || '—' }}</td>
                      <td>{{ fmtMontant(c.debit) }}</td>
                      <td>{{ fmtMontant(c.credit) }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }

          <h3>Mapping catalogue</h3>
          @if (row.catalog_mappings.length) {
            <ul class="bea-rbcm-hint">
              @for (m of row.catalog_mappings; track m.cell_ref + m.basis + m.sign) {
                <li>{{ m.cell_ref }} · {{ m.basis }} · signe {{ m.sign }}</li>
              }
            </ul>
          } @else {
            <p class="bea-rbcm-hint">Aucun mapping exact dans le catalogue central.</p>
          }

          <h3>Orientations & traçabilité</h3>
          @if (row.orientations.length) {
            @for (o of row.orientations; track o.id) {
              <div class="bea-mg__panel" style="margin-bottom:0.75rem">
                <p>
                  <span class="bea-ct-badge" [attr.data-tone]="orientationTone(o.status)">{{ statusLabel(o.status) }}</span>
                  {{ sheetLabel(o.sheet) }} · {{ o.cell_ref || 'sans cellule' }}
                  · {{ opLabel(o.operation) }} · {{ currencyLabel(o.currency_scope) }}
                  · {{ residenceLabel(o.residence_scope) }}
                </p>
                @if (o.decision_comment) {
                  <p class="bea-rbcm-hint">Motif : {{ o.decision_comment }}</p>
                }
                @if (o.notes) {
                  <p class="bea-rbcm-hint" style="white-space:pre-wrap">{{ o.notes }}</p>
                }
                <div class="bea-rbcm-quick" style="margin-top:0.5rem">
                  @if (o.status === 'A_ORIENTER' && canPropose() && o.cell_ref && o.operation) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="submit(o)">Soumettre</button>
                  }
                  @if (o.status === 'EN_ATTENTE_VALIDATION' && canValidate()) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()" (click)="validate(o)">Confirmer</button>
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="reject(o)">Rejeter</button>
                  }
                  @if ((o.status === 'A_ORIENTER' || o.status === 'EN_ATTENTE_VALIDATION') && canPropose()) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="startEdit(o)">Corriger</button>
                  }
                  @if (o.status === 'VALIDE_ACTIF' && canValidate()) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="deactivate(o)">Désactiver</button>
                  }
                </div>
              </div>
            }
          } @else {
            <p class="bea-rbcm-hint">Aucune orientation — le NCG peut rester sans destination métier.</p>
          }

          @if (canPropose()) {
            <h3>{{ editingId() ? 'Corriger la proposition' : 'Proposer une orientation' }}</h3>
            <div class="bea-rbcm-filters" style="flex-wrap:wrap; gap:0.75rem">
              <label class="bea-mg__field">
                <span>État</span>
                <select [(ngModel)]="formSheet">
                  <option value="ETAT_A">ETAT A</option>
                  <option value="ETAT_B">ETAT B</option>
                </select>
              </label>
              <label class="bea-mg__field bea-mg__field--grow">
                <span>Cellule SM</span>
                <select [(ngModel)]="formCell">
                  <option value="">— choisir —</option>
                  @for (c of filteredCells(); track c.cell_ref) {
                    <option [ngValue]="c.cell_ref">{{ c.cell_ref }}</option>
                  }
                </select>
              </label>
              <label class="bea-mg__field">
                <span>Devise</span>
                <select [(ngModel)]="formCurrency">
                  <option value="ALL">Toutes</option>
                  <option value="LOCAL">MRU / MRO</option>
                  <option value="FX">Devises</option>
                </select>
              </label>
              <label class="bea-mg__field">
                <span>Catégorie</span>
                <select [(ngModel)]="formResidence">
                  <option value="RESIDENTS">Résidents</option>
                  <option value="NON_RESIDENTS">Non-résidents</option>
                  <option value="ALL">Toutes</option>
                </select>
              </label>
              <label class="bea-mg__field bea-mg__field--grow">
                <span>Opération</span>
                <select [(ngModel)]="formOperation">
                  <option value="">— choisir —</option>
                  @for (op of board()?.operations || []; track op) {
                    <option [ngValue]="op">{{ opLabel(op) }}</option>
                  }
                </select>
              </label>
            </div>
            <label class="bea-mg__field bea-mg__field--grow" style="margin-top:0.5rem">
              <span>Notes</span>
              <input type="text" [(ngModel)]="formNotes" placeholder="Décision métier…" />
            </label>
            <div class="bea-rbcm-quick" style="margin-top:0.75rem">
              @if (editingId(); as eid) {
                <button
                  type="button"
                  class="bea-mg__btn bea-mg__btn--primary"
                  [disabled]="busy() || !formCell || !formOperation"
                  (click)="saveCorrection()"
                >Enregistrer la correction</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="cancelEdit()">Annuler</button>
              } @else {
                <button
                  type="button"
                  class="bea-mg__btn bea-mg__btn--primary"
                  [disabled]="busy() || !formSheet || !formCell || !formOperation"
                  (click)="propose()"
                >Proposer (À orienter)</button>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="defer()">
                  Laisser sans orientation
                </button>
              }
            </div>
          } @else {
            <p class="bea-rbcm-hint">Lecture seule — permission mapping.propose requise pour proposer ou différer.</p>
          }
        </bea-detail-drawer>
      }
    </div>
  `,
})
export class RbcmNcgRevueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly ctx = inject(RbcmContextService);

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly board = signal<RbcmNcgReviewBoard | null>(null);
  readonly selected = signal<RbcmNcgReviewRow | null>(null);
  readonly tab = signal<BoardTab>('a_reviser');
  readonly rowFilter = signal<RowFilter>('');
  readonly search = signal('');
  readonly editingId = signal<string | null>(null);

  formSheet = 'ETAT_A';
  formCell = '';
  formCurrency = 'ALL';
  formResidence = 'RESIDENTS';
  formOperation = '';
  formNotes = '';

  readonly deferredCount = computed(() => {
    const b = this.board();
    if (!b) return 0;
    return b.ncg_a_reviser.filter((r) => r.decision_deferred).length;
  });

  readonly filteredRows = computed(() => {
    const b = this.board();
    if (!b) return [] as RbcmNcgReviewRow[];
    const q = this.search().trim().toLowerCase();
    const rf = this.rowFilter();
    return b.ncg_a_reviser.filter((r) => {
      if (rf === 'nouveau' && r.structure_status !== 'nouveau') return false;
      if (rf === 'connu_non_oriente' && r.structure_status !== 'connu_non_oriente') return false;
      if (rf === 'deferred' && !r.decision_deferred) return false;
      if (!q) return true;
      return r.ncg.includes(q) || (r.libelle || '').toLowerCase().includes(q);
    });
  });

  readonly filteredOrientations = computed(() => {
    const b = this.board();
    if (!b) return [] as RbcmNcgOrientation[];
    const q = this.search().trim().toLowerCase();
    const wanted =
      this.tab() === 'en_attente'
        ? 'EN_ATTENTE_VALIDATION'
        : this.tab() === 'actives'
          ? 'VALIDE_ACTIF'
          : this.tab() === 'rejetees'
            ? 'REJETE'
            : this.tab() === 'desactivees'
              ? 'DESACTIVE'
              : null;
    return b.orientations.filter((o) => {
      if (wanted && o.status !== wanted) return false;
      if (!q) return true;
      return (
        o.ncg.includes(q) ||
        (o.ncg_libelle || '').toLowerCase().includes(q) ||
        (o.cell_ref || '').toLowerCase().includes(q)
      );
    });
  });

  constructor() {
    effect(() => {
      const id = this.ctx.selectedId();
      if (id) this.reload();
      else {
        this.board.set(null);
        this.loading.set(false);
      }
    });
  }

  ngOnInit(): void {
    this.ctx.applyCampaignQuery(this.route);
    this.ctx.loadCampaigns();
  }

  reload(): void {
    const cid = this.ctx.selectedId();
    if (!cid) return;
    this.loading.set(true);
    this.api.get<RbcmNcgReviewBoard>(`${RBCM_API}/campaigns/${cid}/ncg-review`).subscribe({
      next: (b) => {
        this.board.set(b);
        const sel = this.selected();
        if (sel) {
          const fresh = b.ncg_a_reviser.find((r) => r.ncg === sel.ncg) || null;
          this.selected.set(fresh);
        }
        this.loading.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Revue NCG indisponible');
          this.loading.set(false);
        }),
    });
  }

  boardPeriodLabel(b: RbcmNcgReviewBoard): string {
    return `${String(b.period_month).padStart(2, '0')}/${b.period_year}`;
  }

  fmtMontant(value: string | null | undefined): string {
    return formatMontantOuTiret(value);
  }

  onTabChange(value: BoardTab): void {
    this.tab.set(value);
    if (value !== 'a_reviser') this.rowFilter.set('');
  }

  showNouveaux(): void {
    this.tab.set('a_reviser');
    this.rowFilter.set('nouveau');
  }

  showNonOrientes(): void {
    this.tab.set('a_reviser');
    this.rowFilter.set('connu_non_oriente');
  }

  showDeferred(): void {
    this.tab.set('a_reviser');
    this.rowFilter.set('deferred');
  }

  currencyLabel(scope: string | null | undefined): string {
    if (scope === 'LOCAL') return 'MRU / MRO';
    if (scope === 'FX') return 'Devises';
    if (scope === 'ALL') return 'Toutes devises';
    return scope || '—';
  }

  sheetLabel(sheet: string | null | undefined): string {
    if (sheet === 'ETAT_A') return 'ETAT A';
    if (sheet === 'ETAT_B') return 'ETAT B';
    return sheet || '—';
  }

  residenceLabel(scope: string | null | undefined): string {
    if (scope === 'RESIDENTS') return 'Résidents';
    if (scope === 'NON_RESIDENTS') return 'Non-résidents';
    if (scope === 'ALL') return 'Toutes catégories';
    return scope || '—';
  }

  openRow(row: RbcmNcgReviewRow): void {
    this.selected.set(row);
    this.cancelEdit();
    this.resetForm();
  }

  openOrientation(o: RbcmNcgOrientation): void {
    const b = this.board();
    if (!b) return;
    const row =
      b.ncg_a_reviser.find((r) => r.ncg === o.ncg) ||
      ({
        ncg: o.ncg,
        libelle: o.ncg_libelle,
        structure_status: 'connu_non_oriente',
        tot_debit: null,
        tot_credit: null,
        present_zero: false,
        reapparu: false,
        covered_by_class: false,
        first_seen_period: null,
        last_seen_period: null,
        immediate_previous_period: null,
        balances: [],
        devises: [],
        comptes: [],
        line_count: 0,
        catalog_mappings: [],
        latest_orientation: o,
        orientations: b.orientations.filter((x) => x.ncg === o.ncg),
        proposed_cell_ref: o.cell_ref,
        proposed_operation: o.operation,
        proposed_status: o.status,
        needs_decision: o.status === 'A_ORIENTER' || o.status === 'EN_ATTENTE_VALIDATION',
        decision_deferred: o.status === 'A_ORIENTER' && !o.cell_ref && !o.operation,
      } as RbcmNcgReviewRow);
    this.openRow(row);
  }

  close(): void {
    this.selected.set(null);
    this.cancelEdit();
  }

  filteredCells() {
    const b = this.board();
    if (!b) return [];
    return b.target_cells.filter((c) => c.sheet === this.formSheet);
  }

  structureLabel(row: RbcmNcgReviewRow): string {
    const base = NCG_STRUCTURE_STATUS_LABELS[row.structure_status] || row.structure_status;
    const flags: string[] = [];
    if (row.reapparu) flags.push('réapparu');
    if (row.present_zero) flags.push('solde nul');
    if (row.covered_by_class) flags.push('classe');
    if (row.decision_deferred) flags.push('sans orientation');
    return flags.length ? `${base} · ${flags.join(' · ')}` : base;
  }

  structureTone(row: RbcmNcgReviewRow): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (row.ncg === '847000') return 'warn';
    if (row.structure_status === 'nouveau') return 'warn';
    if (row.structure_status === 'connu_non_oriente') return 'info';
    return null;
  }

  orientationTone(status: string): 'ok' | 'warn' | 'danger' | 'info' | null {
    if (status === 'VALIDE_ACTIF') return 'ok';
    if (status === 'EN_ATTENTE_VALIDATION') return 'warn';
    if (status === 'A_ORIENTER') return 'info';
    if (status === 'REJETE') return 'danger';
    return null;
  }

  statusLabel(s: string | null | undefined): string {
    if (!s) return '—';
    return NCG_ORIENTATION_STATUS_LABELS[s] || s;
  }

  opLabel(op: string | null | undefined): string {
    if (!op) return '—';
    return NCG_ORIENTATION_OPERATION_LABELS[op] || op;
  }

  orientationTabTitle(): string {
    switch (this.tab()) {
      case 'en_attente':
        return 'Orientations en attente de validation';
      case 'actives':
        return 'Orientations validées et actives';
      case 'rejetees':
        return 'Orientations rejetées';
      case 'desactivees':
        return 'Orientations désactivées';
      default:
        return 'Orientations';
    }
  }

  canPropose(): boolean {
    return this.hasPerm('reporting-bcm-sm.mapping.propose', 'reporting-bcm-sm.admin');
  }

  canValidate(): boolean {
    return this.hasPerm('reporting-bcm-sm.mapping.validate', 'reporting-bcm-sm.admin');
  }

  private hasPerm(...codes: string[]): boolean {
    const u = this.auth.user();
    if (!u) return false;
    if (u.is_superuser) return true;
    const have = u.permission_codes ?? [];
    if (have.includes('*')) return true;
    return codes.some((c) => have.includes(c));
  }

  private resetForm(): void {
    this.formSheet = 'ETAT_A';
    this.formCell = '';
    this.formCurrency = 'ALL';
    this.formResidence = 'RESIDENTS';
    this.formOperation = '';
    this.formNotes = '';
  }

  startEdit(o: RbcmNcgOrientation): void {
    this.editingId.set(o.id);
    this.formSheet = o.sheet || 'ETAT_A';
    this.formCell = o.cell_ref || '';
    this.formCurrency = o.currency_scope || 'ALL';
    this.formResidence = o.residence_scope || 'RESIDENTS';
    this.formOperation = o.operation || '';
    this.formNotes = '';
  }

  cancelEdit(): void {
    this.editingId.set(null);
  }

  propose(): void {
    const row = this.selected();
    if (!row) return;
    this.feedback
      .run(
        () =>
          this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations`, {
            ncg: row.ncg,
            sheet: this.formSheet,
            cell_ref: this.formCell || null,
            operation: this.formOperation || null,
            currency_scope: this.formCurrency,
            residence_scope: this.formResidence,
            ncg_libelle: row.libelle,
            notes: this.formNotes || null,
          }),
        {
          busy: this.busy,
          loading: 'Proposition…',
          success: { title: 'Orientation proposée (non active)' },
          errorTitle: 'Proposition impossible',
        },
      )
      .subscribe({ next: () => this.afterMutation(row.ncg) });
  }

  defer(): void {
    const row = this.selected();
    if (!row) return;
    this.feedback
      .run(
        () =>
          this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/defer`, {
            ncg: row.ncg,
            ncg_libelle: row.libelle,
            notes: this.formNotes || 'Décision différée — destination métier non connue.',
          }),
        {
          busy: this.busy,
          confirm: {
            title: 'Laisser sans orientation ?',
            message: 'Aucune cellule ni opération ne sera attribuée. Pas d’activation.',
            confirmLabel: 'Différer',
          },
          loading: 'Enregistrement…',
          success: { title: 'NCG laissé sans orientation' },
          errorTitle: 'Différé impossible',
        },
      )
      .subscribe({ next: () => this.afterMutation(row.ncg) });
  }

  saveCorrection(): void {
    const id = this.editingId();
    const row = this.selected();
    if (!id || !row) return;
    this.feedback
      .run(
        () =>
          this.api.patch<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/${id}`, {
            sheet: this.formSheet,
            cell_ref: this.formCell || null,
            operation: this.formOperation || null,
            currency_scope: this.formCurrency,
            residence_scope: this.formResidence,
            notes: this.formNotes || null,
          }),
        {
          busy: this.busy,
          loading: 'Correction…',
          success: { title: 'Proposition corrigée (historique conservé)' },
          errorTitle: 'Correction impossible',
        },
      )
      .subscribe({ next: () => this.afterMutation(row.ncg) });
  }

  submit(o: RbcmNcgOrientation): void {
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
      .subscribe({ next: () => this.afterMutation(o.ncg) });
  }

  validate(o: RbcmNcgOrientation): void {
    this.feedback
      .run(() => this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/${o.id}/validate`, {}), {
        busy: this.busy,
        confirm: {
          title: 'Confirmer et activer ?',
          message: 'L’orientation entrera dans le catalogue pour les prochains calculs uniquement.',
          confirmLabel: 'Confirmer',
        },
        loading: 'Validation…',
        success: { title: 'Orientation active' },
        errorTitle: 'Validation impossible',
      })
      .subscribe({ next: () => this.afterMutation(o.ncg) });
  }

  reject(o: RbcmNcgOrientation): void {
    this.feedback
      .runWithReason(
        (motif) =>
          this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/${o.id}/reject`, {
            comment: motif,
          }),
        {
          busy: this.busy,
          reason: {
            title: 'Rejeter cette proposition ?',
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
      .subscribe({ next: () => this.afterMutation(o.ncg) });
  }

  deactivate(o: RbcmNcgOrientation): void {
    this.feedback
      .run(
        () =>
          this.api.post<RbcmNcgOrientation>(`${RBCM_API}/ncg-orientations/${o.id}/deactivate`, {
            comment: 'Désactivation revue Comptabilité',
          }),
        {
          busy: this.busy,
          confirm: {
            title: 'Désactiver sans effacer l’historique ?',
            message: 'Ne s’appliquera plus aux prochains calculs.',
            confirmLabel: 'Désactiver',
          },
          loading: 'Désactivation…',
          success: { title: 'Orientation désactivée' },
          errorTitle: 'Désactivation impossible',
        },
      )
      .subscribe({ next: () => this.afterMutation(o.ncg) });
  }

  private afterMutation(ncg: string): void {
    this.cancelEdit();
    this.resetForm();
    const cid = this.ctx.selectedId();
    if (!cid) return;
    this.api.get<RbcmNcgReviewBoard>(`${RBCM_API}/campaigns/${cid}/ncg-review`).subscribe({
      next: (b) => {
        this.board.set(b);
        this.selected.set(b.ncg_a_reviser.find((r) => r.ncg === ncg) || null);
      },
    });
  }
}

