import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { MontantPipe } from '../shared/montant.pipe';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { NoteApercuComponent } from './note-apercu.component';
import { PaiementFormComponent } from './paiement-form.component';
import {
  NOTE_STATUTS,
  Note,
  NotePaiement,
  canPayNotes,
  isNotePayable,
  paiementReference,
  statutPaiementLabel,
  statutPaiementTone,
  canDeleteNote,
  canEditNote,
  deleteNoteHint,
  editNoteHint,
  formatNoteApiError,
  noteStatutLabel,
  noteStatutTone,
} from './notes-frais.shared';

interface Agence {
  id: string;
  code: string;
  libelle: string;
}
interface Paginated {
  items: Note[];
  total: number;
  page: number;
  size: number;
}

@Component({
  selector: 'bea-notes-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatIconModule,
    DatePipe,
    MontantPipe,
    MgGedPanelComponent,
    PaginationComponent,
    NoteApercuComponent,
    PaiementFormComponent,
  ],
  template: `
    <section class="bea-mg bea-nf">
      @if (mode() === 'list') {
        <header class="bea-mg__head">
          <div>
            <p class="bea-stock-page__kicker">Workflow</p>
            <h1>Notes de frais</h1>
          </div>
          <div class="bea-mg__actions">
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/notes-frais">Dashboard</a>
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/notes-frais/nouvelle">
              <mat-icon>add</mat-icon> Nouvelle note
            </a>
          </div>
        </header>

        <form class="bea-mg__search" [formGroup]="filters" (ngSubmit)="applyFilters()">
          <label class="bea-mg__field bea-mg__field--grow">
            <mat-icon>search</mat-icon>
            <input formControlName="q" placeholder="Réf., demandeur, intitulé…" />
          </label>
          <label class="bea-mg__field">
            <mat-icon>flag</mat-icon>
            <select formControlName="statut" (change)="applyFilters()">
              <option value="">Tous les statuts</option>
              @for (s of statuts; track s) {
                <option [value]="s">{{ statutLabel(s) }}</option>
              }
            </select>
          </label>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Filtrer</button>
        </form>


        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Registre</h2>
            <span class="bea-mg__count">{{ total() }} résultat{{ total() > 1 ? 's' : '' }}</span>
          </div>
          <div class="bea-mg__table-scroll bea-nf__registre-scroll">
            <table class="bea-mg__table bea-nf-table">
              <thead>
                <tr>
                  <th>Référence</th>
                  <th>Date</th>
                  <th>Demandeur</th>
                  <th>Intitulé</th>
                  <th class="is-num">Montant</th>
                  <th class="is-num">Reste</th>
                  <th>Statut</th>
                  <th class="bea-mg__th-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                @for (n of notes(); track n.id; let i = $index) {
                  <tr class="bea-nf-row" [style.animation-delay.ms]="i < 20 ? i * 35 : 0" (dblclick)="openApercu(n.id)">
                    <td class="is-nowrap"><code class="bea-mg__code">{{ n.reference }}</code></td>
                    <td class="is-nowrap">{{ n.date_demande | date: 'dd/MM/yyyy' }}</td>
                    <td>
                      <strong class="bea-nf-cell__main">{{ n.demandeur_nom || '—' }}</strong>
                      @if (n.departement || n.fonction) {
                        <small class="bea-nf-cell__sub">{{ n.departement || n.fonction }}</small>
                      }
                    </td>
                    <td>
                      <span class="bea-nf-cell__main">{{ n.agence_libelle_snapshot || '—' }}</span>
                      @if (n.objet) { <small class="bea-nf-cell__sub">{{ n.objet }}</small> }
                    </td>
                    <td class="is-num is-nowrap"><strong>{{ n.total_mru | montant }}</strong></td>
                    <td class="is-num is-nowrap" [class.bea-nf-cell--due]="n.total_mru - n.montant_paye > 0">
                      {{ (n.total_mru - n.montant_paye) | montant }}
                    </td>
                    <td class="is-nowrap"><span class="bea-nf-badge" [attr.data-tone]="statutTone(n.statut)">{{ statutLabel(n.statut) }}</span></td>
                    <td class="bea-mg__actions-cell">
                      <button type="button" class="bea-mg__icon-btn" title="Voir le détail" (click)="openApercu(n.id)">
                        <mat-icon>visibility</mat-icon>
                      </button>
                      @if (canPay() && isPayable(n)) {
                        <button type="button" class="bea-mg__icon-btn bea-pay-btn" title="Payer" (click)="payerDepuisListe(n)">
                          <mat-icon>payments</mat-icon>
                        </button>
                      }
                      @if (canEdit(n)) {
                        <a class="bea-mg__icon-btn" [routerLink]="['/notes-frais/notes', n.id]" title="Modifier">
                          <mat-icon>edit</mat-icon>
                        </a>
                      } @else {
                        <button type="button" class="bea-mg__icon-btn" disabled [title]="editHint(n)">
                          <mat-icon>edit</mat-icon>
                        </button>
                      }
                      <button
                        type="button"
                        class="bea-mg__icon-btn bea-mg__icon-btn--danger"
                        [title]="deleteHint(n)"
                        [disabled]="!canDelete(n) || deletingId() === n.id"
                        (click)="remove(n)"
                      >
                        <mat-icon>delete</mat-icon>
                      </button>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="8">
                      <div class="bea-mg__empty">
                        <mat-icon>receipt_long</mat-icon>
                        <p>Aucune note de frais.</p>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          @if (total() > 0) {
            <app-pagination
              [page]="page()"
              [total]="total()"
              [pageSize]="pageSize"
              label="note(s)"
              (pageChange)="goToPage($event)"
            />
          }
        </div>

        @if (apercuId(); as id) {
          <bea-note-apercu [noteId]="id" (closed)="apercuId.set(null)" (deleted)="onApercuDeleted()" />
        }
      }

      @if (mode() === 'create' || mode() === 'detail') {
        <header class="bea-mg__head">
          <div>
            <p class="bea-stock-page__kicker">{{ mode() === 'create' ? 'Création' : 'Fiche' }}</p>
            <h1>{{ current()?.reference || 'Nouvelle note de frais' }}</h1>
          </div>
          <div class="bea-mg__actions">
            <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/notes-frais/notes">
              <mat-icon>arrow_back</mat-icon> Retour
            </a>
          </div>
        </header>


        <form class="bea-mg__panel" [formGroup]="form" (ngSubmit)="save()" style="overflow:visible">
          <div class="bea-mg__panel-top">
            <h2>Fiche note de frais</h2>
            <span class="bea-nf-badge" [attr.data-tone]="statutTone(current()?.statut || 'BROUILLON')">{{ statutLabel(current()?.statut || 'BROUILLON') }}</span>
          </div>
          <div class="bea-mg__modal-body">
            <div class="bea-nf-fiche">
              <div class="bea-nf-fiche__top">
                <div class="bea-nf-fiche__brand">
                  <img src="/brand/icon-bea.png" width="52" height="52" alt="BEA" />
                  <strong>Banque El Amana</strong>
                </div>
                <div class="bea-nf-fiche__dept">
                  Département Ressources Humaines<br />et Moyens Généraux
                  <span>Service Moyens Généraux</span>
                </div>
                <div class="bea-nf-fiche__id">
                  <div class="bea-nf-fiche__id-row">
                    <label>Identité du demandeur</label>
                    <input formControlName="demandeur_nom" placeholder="Nom Prénom" />
                  </div>
                  <div class="bea-nf-fiche__id-row">
                    <label>Département</label>
                    <input formControlName="departement" />
                  </div>
                  <div class="bea-nf-fiche__id-row">
                    <label>Fonction</label>
                    <input formControlName="fonction" />
                  </div>
                  <div class="bea-nf-fiche__id-row">
                    <label>date de la demande</label>
                    <input type="date" formControlName="date_demande" />
                  </div>
                </div>
              </div>

              <div class="bea-nf-fiche__title-row">
                <strong>NOTE DE FRAIS :</strong>
                <select formControlName="intitule_mode" (change)="onIntituleModeChange()">
                  <option value="agence">Agence</option>
                  <option value="autre">Autre</option>
                </select>
                @if (form.value.intitule_mode === 'agence') {
                  <select formControlName="agence_id">
                    <option value="">— Sélectionner l'agence —</option>
                    @for (a of agences(); track a.id) {
                      <option [value]="a.id">{{ a.libelle }}</option>
                    }
                  </select>
                } @else {
                  <input
                    formControlName="intitule"
                    placeholder="Ex. Frais Carburant, Paiement mission…"
                  />
                }
              </div>

              <div class="bea-mg__grid" style="padding:0.75rem 1rem;border-bottom:1px solid #cbd5e1">
                <label class="bea-mg__span2">Objet / motif général <input formControlName="objet" /></label>
              </div>

              <table class="bea-mg__table" formArrayName="lignes">
                <thead>
                  <tr>
                    <th>Date de la dépense</th>
                    <th>Description</th>
                    <th>Motif</th>
                    <th>Montant En MRU</th>
                    <th>Mode de règlement</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  @for (ctrl of lignes.controls; track ctrl; let i = $index) {
                    <tr [formGroupName]="i">
                      <td><input type="date" formControlName="date_depense" /></td>
                      <td><input formControlName="description" placeholder="Description" /></td>
                      <td><input formControlName="motif" /></td>
                      <td><input type="number" formControlName="montant" min="0.01" step="0.01" /></td>
                      <td class="bea-nf-fiche__mode">
                        <select formControlName="mode_type" (change)="onModeTypeChange(i)">
                          <option value="">—</option>
                          <option value="Espèces">Espèces</option>
                          <option value="Carte">Carte</option>
                          <option value="Virement">Virement</option>
                          <option value="Chèque">Chèque</option>
                          <option value="Amanty">Amanty</option>
                        </select>
                        @if (ctrl.value.mode_type === 'Amanty') {
                          <input
                            formControlName="amanty_ref"
                            placeholder="Ex. Via Amanty 31004531"
                          />
                        }
                      </td>
                      <td class="bea-mg__actions-cell">
                        <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" (click)="removeLigne(i)">
                          <mat-icon>remove</mat-icon>
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>

              <div class="bea-nf-fiche__total">
                <span>TOTAL</span>
                <span>{{ sumLignes() | montant }} MRU</span>
              </div>

              <div class="bea-nf-fiche__signs">
                <div>Signature Chef Sce Moyens Généraux</div>
                <div>Signature Directrice des Ressources</div>
              </div>
            </div>
          </div>

          <footer class="bea-nf-actions">
            @if (editable()) {
              <div class="bea-nf-actions__group">
                <span class="bea-nf-actions__label">Saisie</span>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="addLigne()">
                  <mat-icon>add</mat-icon> Ligne
                </button>
                <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="form.invalid || saving()">
                  {{ saveLabel() }}
                </button>
              </div>
            }

            @if (current(); as n) {
              @if (n.statut === 'BROUILLON') {
                <div class="bea-nf-actions__group">
                  <span class="bea-nf-actions__label">Envoi</span>
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="doTransition('soumettre')">
                    Soumettre
                  </button>
                </div>
              }
              @if (n.statut === 'CORRECTION_REQUISE') {
                <div class="bea-nf-actions__group">
                  <span class="bea-nf-actions__label">Envoi</span>
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="doTransition('resoumettre')">
                    Resoumettre
                  </button>
                </div>
              }
              @if (n.statut === 'SOUMIS' || n.statut === 'EN_CONTROLE' || n.statut === 'VISA_MG' || n.statut === 'VISA_DR') {
                <div class="bea-nf-actions__group">
                  <span class="bea-nf-actions__label">Décision</span>
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="doTransition('valider')">
                    Valider
                  </button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="askCorrection()">
                    Demander correction
                  </button>
                  <button type="button" class="bea-mg__btn bea-mg__btn--danger" (click)="askReject()">Rejeter</button>
                </div>
              }
              @if (isPayable(n)) {
                <div class="bea-nf-actions__group">
                  <span class="bea-nf-actions__label">Paiement</span>
                  @if (n.statut === 'VALIDEE') {
                    <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="doTransition('mettre_en_paiement')">
                      Mise en paiement
                    </button>
                  }
                  @if (canPay()) {
                    <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="payerOpen.set(true)">
                      <mat-icon>payments</mat-icon> Payer
                    </button>
                  }
                </div>
              }
              @if (n.statut === 'PAYEE') {
                <div class="bea-nf-actions__group">
                  <span class="bea-nf-actions__label">Clôture</span>
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="doTransition('cloturer')">
                    Clôturer
                  </button>
                </div>
              }
              @if (n.statut === 'CLOTUREE') {
                <div class="bea-nf-actions__group">
                  <span class="bea-nf-actions__label">Archive</span>
                  <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="doTransition('archiver')">
                    Archiver
                  </button>
                </div>
              }
              <div class="bea-nf-actions__group">
                <span class="bea-nf-actions__label">Document</span>
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="openPdfModal()">
                  <mat-icon>picture_as_pdf</mat-icon> Télécharger PDF
                </button>
              </div>
            }
          </footer>
        </form>

        @if (current(); as n) {
          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top">
              <h2>Paiements</h2>
              <span class="bea-nf-badge" [attr.data-tone]="payTone(n.statut_paiement)">{{ payLabel(n.statut_paiement) }}</span>
            </div>
            <div class="bea-mg__modal-body">
              <div class="bea-ct-view__kpis bea-pay-kpis">
                <div><span>Montant initial</span><strong>{{ n.total_mru | montant }} MRU</strong></div>
                <div><span>Total payé</span><strong>{{ n.montant_paye | montant }} MRU</strong></div>
                <div [class.is-due]="n.total_mru - n.montant_paye > 0">
                  <span>Solde restant</span><strong>{{ (n.total_mru - n.montant_paye) | montant }} MRU</strong>
                </div>
              </div>
              @if (notePaiements().length) {
                <div class="bea-nf-view__table">
                  <table class="bea-mg__table bea-nf-table">
                    <thead>
                      <tr><th>N° paiement</th><th>Date</th><th>Mode</th><th>Référence</th><th class="is-num">Montant</th><th>Statut</th><th></th></tr>
                    </thead>
                    <tbody>
                      @for (p of notePaiements(); track p.id) {
                        <tr [class.is-cancelled]="p.statut === 'ANNULE'">
                          <td><code class="bea-mg__code">{{ p.numero }}</code></td>
                          <td class="is-nowrap">{{ p.date_paiement | date: 'dd/MM/yyyy' }}</td>
                          <td>{{ p.mode_paiement }}</td>
                          <td>{{ paiementRef(p) }}</td>
                          <td class="is-num is-nowrap">{{ p.montant | montant }}</td>
                          <td><span class="bea-nf-badge" [attr.data-tone]="p.statut === 'ANNULE' ? 'danger' : 'ok'">{{ p.statut === 'ANNULE' ? 'Annulé' : 'Validé' }}</span></td>
                          <td class="bea-mg__actions-cell">
                            <a class="bea-mg__icon-btn" [routerLink]="['/notes-frais/paiements']" [queryParams]="{ voir: p.id }" title="Voir le paiement">
                              <mat-icon>visibility</mat-icon>
                            </a>
                          </td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              } @else {
                <p class="bea-ct-view__none">Aucun paiement enregistré pour cette note.</p>
              }
              @if (isPayable(n) && canPay()) {
                <div class="bea-pay-cta">
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="payerOpen.set(true)">
                    <mat-icon>payments</mat-icon> Payer {{ (n.total_mru - n.montant_paye) | montant }} MRU
                  </button>
                </div>
              }
            </div>
          </div>

          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Workflow</h2></div>
            <div class="bea-mg__table-scroll">
              <table class="bea-mg__table">
                <thead>
                  <tr><th>Date</th><th>Action</th><th>De</th><th>Vers</th><th>Par</th><th>Commentaire</th></tr>
                </thead>
                <tbody>
                  @for (h of n.historique; track h.id) {
                    <tr>
                      <td>{{ h.created_at | date: 'short' }}</td>
                      <td>{{ h.action }}</td>
                      <td>{{ h.from_statut || '—' }}</td>
                      <td>{{ h.to_statut || '—' }}</td>
                      <td>{{ h.user_nom || '—' }}</td>
                      <td>{{ h.commentaire || '—' }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="6"><div class="bea-mg__empty"><p>Aucun historique.</p></div></td></tr>
                  }
                </tbody>
              </table>
            </div>
          </div>

          <div class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Justificatifs (GED)</h2></div>
            <div class="bea-mg__modal-body">
              <bea-mg-ged moduleCode="notes-frais" entity="note_frais" [entityId]="n.id" />
            </div>
          </div>
        }
      }

      @if (payerOpen()) {
        <bea-paiement-form
          [noteId]="payerNoteId()"
          (closed)="closePayer()"
          (saved)="onPaid()"
        />
      }

      @if (pdfModal()) {
        <div class="bea-mg__backdrop" (click)="closePdfModal()"></div>
        <div class="bea-mg__modal bea-mg__modal--sm" role="dialog">
          <div class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Export PDF</p>
              <h2>Préparer la note de frais</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closePdfModal()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </div>
          <div class="bea-mg__modal-body">
            <p style="margin:0 0 1rem;color:#64748b;font-size:0.9rem">
              Signataires proposés par défaut — vous pouvez les modifier avant de télécharger.
              La fiche est au format A4.
            </p>
            <form class="bea-mg__grid bea-mg__grid--1" [formGroup]="pdfForm" (ngSubmit)="downloadPdf()">
              <label>
                Orientation
                <select formControlName="orientation">
                  <option value="portrait">A4 — Portrait</option>
                  <option value="paysage">A4 — Paysage</option>
                </select>
              </label>
              <label>
                Signature 1
                <input formControlName="signataire1" placeholder="Signature Chef Sce Moyens Généraux" />
              </label>
              <label>
                Signature 2
                <input formControlName="signataire2" placeholder="Signature Directrice des Ressources" />
              </label>
              @if (pdfErreur()) {
                <p class="bea-stock-page__error">{{ pdfErreur() }}</p>
              }
              <footer class="bea-mg__modal-foot" style="padding:0;margin-top:0.5rem">
                <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closePdfModal()">Annuler</button>
                <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="pdfBusy()">
                  <mat-icon>download</mat-icon>
                  {{ pdfBusy() ? 'Génération…' : 'Télécharger le PDF' }}
                </button>
              </footer>
            </form>
          </div>
        </div>
      }
    </section>
  `,
})
export class NotesListComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(() => this.mode() === 'create' && this.form.dirty && !this.saving(), () => this.form);
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly mode = signal<'list' | 'create' | 'detail'>('list');
  readonly notes = signal<Note[]>([]);
  readonly current = signal<Note | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly page = signal(1);
  readonly total = signal(0);
  readonly pageSize = 10;
  readonly saving = signal(false);
  readonly deletingId = signal<string | null>(null);
  readonly erreur = feedbackSignal('error', '');
  readonly msg = feedbackSignal('success', '');
  readonly pdfModal = signal(false);
  readonly pdfBusy = signal(false);
  readonly pdfErreur = signal('');
  readonly payerOpen = signal(false);
  readonly payerNote = signal<string | null>(null);
  readonly payerNoteId = computed(() => this.payerNote() ?? this.current()?.id ?? null);
  readonly notePaiements = signal<NotePaiement[]>([]);
  readonly canPay = computed(() => canPayNotes(this.auth.user()));
  readonly isPayable = isNotePayable;
  readonly payLabel = statutPaiementLabel;
  readonly payTone = statutPaiementTone;
  readonly paiementRef = paiementReference;

  readonly pdfForm = this.fb.nonNullable.group({
    orientation: ['paysage' as 'portrait' | 'paysage'],
    signataire1: ['Signature Chef Sce Moyens Généraux'],
    signataire2: ['Signature Directrice des Ressources'],
  });

  readonly statuts = NOTE_STATUTS;
  readonly apercuId = signal<string | null>(null);
  readonly statutLabel = noteStatutLabel;
  readonly statutTone = noteStatutTone;
  readonly formatApiError = formatNoteApiError;

  readonly filters = this.fb.nonNullable.group({ q: '', statut: '' });

  readonly form = this.fb.nonNullable.group({
    intitule_mode: ['agence' as 'agence' | 'autre'],
    agence_id: [''],
    intitule: [''],
    date_demande: ['', Validators.required],
    demandeur_nom: [''],
    departement: [''],
    fonction: [''],
    objet: [''],
    lignes: this.fb.array([this.newLigne()]),
  });

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  editable = computed(() => {
    const n = this.current();
    if (!n) return true;
    return this.canEdit(n);
  });

  saveLabel(): string {
    const s = this.current()?.statut;
    return !s || s === 'BROUILLON' ? 'Enregistrer brouillon' : 'Enregistrer';
  }

  canEdit(note: Note): boolean {
    return canEditNote(this.auth.user(), note);
  }

  canDelete(note: Note): boolean {
    return canDeleteNote(this.auth.user(), note);
  }

  editHint(note: Note): string {
    return editNoteHint(this.auth.user(), note);
  }

  deleteHint(note: Note): string {
    return deleteNoteHint(this.auth.user(), note);
  }

  openApercu(id: string): void {
    this.apercuId.set(id);
  }

  onApercuDeleted(): void {
    this.apercuId.set(null);
    if (this.notes().length <= 1 && this.page() > 1) {
      this.page.update((p) => p - 1);
    }
    this.loadList();
  }

  remove(note: Note): void {
    this.dialogs
      .confirmAction('suppression', `Supprimer la note « ${note.reference} » ? Elle sera retirée du registre.`)
      .subscribe((ok) => {
        if (!ok) return;
        this.deletingId.set(note.id);
        this.erreur.set('');
        this.api.delete<{ ok: boolean }>(`/mg/notes-frais/notes/${note.id}`).subscribe({
          next: () => {
            this.deletingId.set(null);
            if (this.mode() !== 'list') {
              void this.router.navigate(['/notes-frais/notes']);
              return;
            }
            if (this.notes().length <= 1 && this.page() > 1) {
              this.page.update((p) => p - 1);
            }
            this.loadList();
          },
          error: (err) => {
            this.deletingId.set(null);
            this.erreur.set(this.formatApiError(err, 'Suppression refusée'));
          },
        });
      });
  }

  sumLignes(): number {
    return this.lignes.controls.reduce((acc, c) => acc + (Number(c.value.montant) || 0), 0);
  }

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/notes-frais/agences').subscribe((a) => {
      this.agences.set(a);
      if (a[0] && !this.form.value.agence_id) this.form.patchValue({ agence_id: a[0].id });
    });

    this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (this.router.url.endsWith('/nouvelle')) {
        this.mode.set('create');
        this.current.set(null);
        const today = new Date().toISOString().slice(0, 10);
        this.form.reset({
          intitule_mode: 'agence',
          agence_id: this.agences()[0]?.id || '',
          intitule: '',
          date_demande: today,
          demandeur_nom: '',
          departement: '',
          fonction: '',
          objet: '',
        });
        this.lignes.clear();
        this.addLigne();
        this.lignes.at(0)?.patchValue({ date_depense: today });
        return;
      }
      if (id) {
        this.mode.set('detail');
        this.loadOne(id);
        return;
      }
      this.mode.set('list');
      this.loadList();
    });
  }

  newLigne() {
    const today = new Date().toISOString().slice(0, 10);
    return this.fb.nonNullable.group({
      date_depense: [today, Validators.required],
      description: ['', Validators.required],
      motif: [''],
      montant: [1, Validators.required],
      mode_type: [''],
      amanty_ref: [''],
    });
  }

  /** Décompose « Via Amanty 31004531 » / « Amanty » stocké en base. */
  parseModeReglement(raw: string | null | undefined): { mode_type: string; amanty_ref: string } {
    const v = (raw || '').trim();
    if (!v) return { mode_type: '', amanty_ref: '' };
    const via = /^via\s+amanty\s*(.*)$/i.exec(v);
    if (via) {
      const ref = via[1].trim();
      return { mode_type: 'Amanty', amanty_ref: ref ? `Via Amanty ${ref}` : 'Via Amanty ' };
    }
    if (/^amanty$/i.test(v)) return { mode_type: 'Amanty', amanty_ref: '' };
    return { mode_type: v, amanty_ref: '' };
  }

  resolveModeReglement(modeType: string, amantyRef: string): string | null {
    if (!modeType) return null;
    if (modeType === 'Amanty') {
      const ref = (amantyRef || '').trim();
      if (!ref) return 'Amanty';
      return /^via\s+amanty/i.test(ref) ? ref : `Via Amanty ${ref}`;
    }
    return modeType;
  }

  onModeTypeChange(i: number): void {
    const g = this.lignes.at(i);
    if (g.value.mode_type !== 'Amanty') {
      g.patchValue({ amanty_ref: '' });
    } else if (!g.value.amanty_ref) {
      g.patchValue({ amanty_ref: 'Via Amanty ' });
    }
  }

  onIntituleModeChange(): void {
    const mode = this.form.value.intitule_mode;
    if (mode === 'agence') {
      this.form.patchValue({ intitule: '' });
      if (!this.form.value.agence_id && this.agences()[0]) {
        this.form.patchValue({ agence_id: this.agences()[0].id });
      }
    } else {
      this.form.patchValue({ agence_id: '' });
    }
  }

  addLigne(): void {
    this.lignes.push(this.newLigne());
  }

  removeLigne(i: number): void {
    if (this.lignes.length > 1) this.lignes.removeAt(i);
  }

  applyFilters(): void {
    this.page.set(1);
    this.loadList();
  }

  goToPage(page: number): void {
    this.page.set(page);
    this.loadList();
  }

  loadList(): void {
    this.erreur.set('');
    const v = this.filters.getRawValue();
    const params: Record<string, string | number> = { page: this.page(), size: this.pageSize };
    if (v.q?.trim()) params['q'] = v.q.trim();
    if (v.statut) params['statut'] = v.statut;
    this.api.get<Paginated>('/mg/notes-frais/notes', params).subscribe({
      next: (res) => {
        this.notes.set(res.items);
        this.total.set(res.total);
      },
      error: () => {
        this.notes.set([]);
        this.total.set(0);
        this.erreur.set('Chargement impossible');
      },
    });
  }

  loadOne(id: string): void {
    this.loadNotePaiements(id);
    this.api.get<Note>(`/mg/notes-frais/notes/${id}`).subscribe({
      next: (n) => {
        this.current.set(n);
        this.form.patchValue({
          intitule_mode: n.agence_id ? 'agence' : 'autre',
          agence_id: n.agence_id || '',
          intitule: n.agence_id ? '' : n.agence_libelle_snapshot || '',
          date_demande: n.date_demande,
          demandeur_nom: n.demandeur_nom || '',
          departement: n.departement || '',
          fonction: n.fonction || '',
          objet: n.objet || '',
        });
        this.lignes.clear();
        for (const l of n.lignes) {
          const mode = this.parseModeReglement(l.mode_reglement);
          this.lignes.push(
            this.fb.nonNullable.group({
              date_depense: [l.date_depense, Validators.required],
              description: [l.description, Validators.required],
              motif: [l.motif || ''],
              montant: [l.montant, Validators.required],
              mode_type: [mode.mode_type],
              amanty_ref: [mode.amanty_ref],
            }),
          );
        }
        if (!n.lignes.length) this.addLigne();
        if (!this.editable()) this.form.disable();
        else this.form.enable();
      },
      error: () => this.erreur.set('Note introuvable ou accès refusé'),
    });
  }

  bodyFromForm() {
    const raw = this.form.getRawValue();
    const isAgence = raw.intitule_mode === 'agence';
    return {
      agence_id: isAgence ? raw.agence_id || null : null,
      intitule: isAgence ? null : raw.intitule || null,
      date_demande: raw.date_demande,
      demandeur_nom: raw.demandeur_nom || null,
      departement: raw.departement || null,
      fonction: raw.fonction || null,
      objet: raw.objet || null,
      lignes: raw.lignes.map((l) => ({
        date_depense: l.date_depense,
        description: l.description,
        motif: l.motif || null,
        montant: l.montant,
        mode_reglement: this.resolveModeReglement(l.mode_type, l.amanty_ref),
      })),
    };
  }

  save(): void {
    const raw = this.form.getRawValue();
    if (raw.intitule_mode === 'agence' && !raw.agence_id) {
      this.erreur.set('Sélectionnez une agence.');
      return;
    }
    if (raw.intitule_mode === 'autre' && !raw.intitule.trim()) {
      this.erreur.set('Saisissez l’intitulé (ex. Frais Carburant).');
      return;
    }
    const amantyIncomplet = raw.lignes.some(
      (l) => l.mode_type === 'Amanty' && !(l.amanty_ref || '').replace(/^via\s+amanty\s*/i, '').trim(),
    );
    if (amantyIncomplet) {
      this.erreur.set('Indiquez la référence Amanty (ex. Via Amanty 31004531).');
      return;
    }
    if (this.form.invalid) return;
    this.saving.set(true);
    this.erreur.set('');
    const body = this.bodyFromForm();
    const id = this.current()?.id;
    const req = id
      ? this.api.patch<Note>(`/mg/notes-frais/notes/${id}`, body)
      : this.api.post<Note>('/mg/notes-frais/notes', body);
    req.subscribe({
      next: (n) => {
        this.saving.set(false);
        this.msg.set('Enregistré.');
        void this.router.navigate(['/notes-frais/notes', n.id]);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(this.formatApiError(err, 'Enregistrement refusé'));
      },
    });
  }

  doTransition(action: string, commentaire?: string): void {
    const id = this.current()?.id;
    if (!id) return;
    this.erreur.set('');
    this.api.post<Note>(`/mg/notes-frais/notes/${id}/transition`, { action, commentaire }).subscribe({
      next: (n) => {
        this.current.set(n);
        this.msg.set('Étape enregistrée.');
        this.loadOne(id);
      },
      error: (err) => this.erreur.set(this.formatApiError(err, 'Transition refusée')),
    });
  }

  askCorrection(): void {
    this.dialogs
      .confirmWithReason({
        title: 'Demander une correction',
        message: `La note « ${this.current()?.reference ?? ''} » sera renvoyée au demandeur.`,
        confirmLabel: 'Demander la correction',
        cancelLabel: 'Annuler',
        tone: 'warn',
        icon: 'edit_note',
        reasonLabel: 'Motif de la correction',
      })
      .subscribe((motif) => {
        if (motif?.trim()) this.doTransition('demander_correction', motif.trim());
      });
  }

  askReject(): void {
    this.dialogs
      .confirmWithReason({
        title: 'Rejeter la note',
        message: `La note « ${this.current()?.reference ?? ''} » sera rejetée.`,
        confirmLabel: 'Rejeter',
        cancelLabel: 'Annuler',
        tone: 'danger',
        icon: 'block',
        reasonLabel: 'Motif du rejet',
      })
      .subscribe((motif) => {
        if (motif?.trim()) this.doTransition('rejeter', motif.trim());
      });
  }

  /** « Payer » depuis une ligne du registre. */
  payerDepuisListe(note: Note): void {
    this.payerNote.set(note.id);
    this.payerOpen.set(true);
  }

  closePayer(): void {
    this.payerOpen.set(false);
    this.payerNote.set(null);
  }

  onPaid(): void {
    const detailId = this.mode() === 'detail' ? this.current()?.id : null;
    this.closePayer();
    if (detailId) this.loadOne(detailId);
    else this.loadList();
  }

  loadNotePaiements(noteId: string): void {
    this.api
      .get<{ items: NotePaiement[] }>('/mg/notes-frais/paiements', {
        note_id: noteId,
        size: 100,
        sort: 'date_paiement',
        order: 'asc',
      })
      .subscribe({
        next: (r) => this.notePaiements.set(r.items),
        error: () => this.notePaiements.set([]),
      });
  }

  openPdfModal(): void {
    this.pdfErreur.set('');
    this.pdfForm.reset({
      orientation: 'paysage',
      signataire1: 'Signature Chef Sce Moyens Généraux',
      signataire2: 'Signature Directrice des Ressources',
    });
    this.pdfModal.set(true);
  }

  closePdfModal(): void {
    this.pdfModal.set(false);
    this.pdfBusy.set(false);
  }

  downloadPdf(): void {
    const id = this.current()?.id;
    if (!id) return;
    const v = this.pdfForm.getRawValue();
    const s1 = v.signataire1.trim();
    const s2 = v.signataire2.trim();
    if (!s1 || !s2) {
      this.pdfErreur.set('Veuillez renseigner les deux signataires avant de générer le PDF.');
      return;
    }
    this.pdfBusy.set(true);
    this.pdfErreur.set('');
    this.api
      .download(`/mg/notes-frais/notes/${id}/pdf`, {
        signataire_1: s1,
        signataire_2: s2,
        orientation: v.orientation,
      })
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${this.current()?.reference || 'note'}.pdf`;
          a.click();
          URL.revokeObjectURL(url);
          this.closePdfModal();
          this.msg.set('PDF téléchargé.');
        },
        error: () => {
          this.pdfBusy.set(false);
          this.pdfErreur.set('Export PDF impossible');
        },
      });
  }
}
