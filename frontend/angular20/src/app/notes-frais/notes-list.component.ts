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

interface Agence {
  id: string;
  code: string;
  libelle: string;
}
interface Hist {
  id: string;
  action: string;
  from_statut: string | null;
  to_statut: string | null;
  user_nom: string | null;
  commentaire: string | null;
  created_at: string | null;
}
interface Ligne {
  id?: string;
  date_depense: string;
  description: string;
  motif: string | null;
  montant: number;
  mode_reglement: string | null;
  categorie_id: string | null;
  categorie_libelle_snapshot: string | null;
}
interface Note {
  id: string;
  reference: string;
  date_demande: string;
  agence_id: string | null;
  agence_libelle_snapshot: string | null;
  demandeur_id: string | null;
  demandeur_nom: string | null;
  departement: string | null;
  fonction: string | null;
  objet: string | null;
  periode_debut: string | null;
  periode_fin: string | null;
  devise: string;
  statut: string;
  total_mru: number;
  montant_paye: number;
  motif_rejet: string | null;
  motif_correction: string | null;
  observation: string | null;
  pdf_version: number;
  lignes: Ligne[];
  historique: Hist[];
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

        @if (erreur()) {
          <p class="bea-stock-page__error">{{ erreur() }}</p>
        }

        <div class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Registre</h2>
            <span class="bea-mg__count">{{ total() }} résultat(s)</span>
          </div>
          <div class="bea-mg__table-scroll bea-nf__registre-scroll">
            <table class="bea-mg__table">
              <thead>
                <tr>
                  <th>Réf</th>
                  <th>Date</th>
                  <th>Demandeur</th>
                  <th>Intitulé</th>
                  <th>Montant</th>
                  <th>Statut</th>
                  <th class="bea-mg__th-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                @for (n of notes(); track n.id) {
                  <tr>
                    <td><code class="bea-mg__code">{{ n.reference }}</code></td>
                    <td>{{ n.date_demande | date: 'shortDate' }}</td>
                    <td>{{ n.demandeur_nom || '—' }}</td>
                    <td>{{ n.agence_libelle_snapshot || '—' }}</td>
                    <td>{{ n.total_mru | montant }}</td>
                    <td><span class="bea-stock-badge">{{ statutLabel(n.statut) }}</span></td>
                    <td class="bea-mg__actions-cell">
                      <a class="bea-mg__icon-btn" [routerLink]="['/notes-frais/notes', n.id]" title="Voir">
                        <mat-icon>visibility</mat-icon>
                      </a>
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
                    <td colspan="7">
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

        @if (erreur()) {
          <p class="bea-stock-page__error">{{ erreur() }}</p>
        }
        @if (msg()) {
          <p class="bea-stock-page__ok">{{ msg() }}</p>
        }

        <form class="bea-mg__panel" [formGroup]="form" (ngSubmit)="save()" style="overflow:visible">
          <div class="bea-mg__panel-top">
            <h2>Fiche note de frais</h2>
            <span class="bea-stock-badge">{{ statutLabel(current()?.statut || 'BROUILLON') }}</span>
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
                  @for (ctrl of lignes.controls; track $index; let i = $index) {
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
              @if (n.statut === 'VALIDEE') {
                <div class="bea-nf-actions__group">
                  <span class="bea-nf-actions__label">Paiement</span>
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="doTransition('mettre_en_paiement')">
                    Mise en paiement
                  </button>
                </div>
              }
              @if (n.statut === 'MISE_EN_PAIEMENT' || n.statut === 'PARTIELLEMENT_PAYEE') {
                <div class="bea-nf-actions__group">
                  <span class="bea-nf-actions__label">Paiement</span>
                  <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="openPaiement()">
                    Enregistrer paiement
                  </button>
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
            <div class="bea-mg__panel-top"><h2>Paiement</h2></div>
            <div class="bea-mg__modal-body bea-mg__grid">
              <label>Total <input [value]="n.total_mru | montant" readonly /></label>
              <label>Payé <input [value]="n.montant_paye | montant" readonly /></label>
              <label>Reste <input [value]="(n.total_mru - n.montant_paye) | montant" readonly /></label>
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

      @if (paiementModal()) {
        <div class="bea-mg__backdrop" (click)="closePaiement()"></div>
        <div
          class="bea-mg__modal"
          role="dialog"
          aria-modal="true"
          aria-label="Enregistrer le paiement"
        >
          <div class="bea-mg__modal-head">
            <div>
              <p class="bea-stock-page__kicker">Paiement · {{ current()?.reference }}</p>
              <h2>Enregistrer le paiement</h2>
            </div>
            <button type="button" class="bea-mg__icon-btn" (click)="closePaiement()" title="Fermer">
              <mat-icon>close</mat-icon>
            </button>
          </div>
          <form class="bea-mg__modal-body" [formGroup]="paiementForm" (ngSubmit)="confirmPaiement()">
            <p style="margin:0 0 1rem;color:#64748b;font-size:0.9rem">
              Le montant proposé correspond au reste à payer. Vous pouvez le confirmer ou le modifier.
            </p>
            <div class="bea-mg__grid">
              <label>Total<input [value]="(current()?.total_mru || 0) | montant" readonly /></label>
              <label>Déjà payé<input [value]="(current()?.montant_paye || 0) | montant" readonly /></label>
              <label class="bea-mg__span2">
                Reste à payer
                <input [value]="resteAPayer() | montant" readonly />
              </label>
              <label class="bea-mg__span2">
                Montant à enregistrer (MRU)
                <input type="number" formControlName="montant" min="0.01" step="0.01" />
              </label>
              <label>
                Mode de règlement
                <select formControlName="mode_paiement">
                  <option value="Espèces">Espèces</option>
                  <option value="Carte">Carte</option>
                  <option value="Virement">Virement</option>
                  <option value="Chèque">Chèque</option>
                  <option value="Amanty">Amanty</option>
                </select>
              </label>
              <label>
                Référence
                <input formControlName="ref_paiement" placeholder="N° virement, chèque…" />
              </label>
            </div>
            @if (paiementErreur()) {
              <p class="bea-stock-page__error" style="margin-top:0.75rem">{{ paiementErreur() }}</p>
            }
            <footer class="bea-mg__modal-foot" style="padding:0.9rem 0 0">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="closePaiement()">
                Annuler
              </button>
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="paiementBusy()">
                <mat-icon>payments</mat-icon>
                {{ paiementBusy() ? 'Enregistrement…' : 'Enregistrer le paiement' }}
              </button>
            </footer>
          </form>
        </div>
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
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly pdfModal = signal(false);
  readonly pdfBusy = signal(false);
  readonly pdfErreur = signal('');
  readonly paiementModal = signal(false);
  readonly paiementBusy = signal(false);
  readonly paiementErreur = signal('');

  readonly pdfForm = this.fb.nonNullable.group({
    orientation: ['paysage' as 'portrait' | 'paysage'],
    signataire1: ['Signature Chef Sce Moyens Généraux'],
    signataire2: ['Signature Directrice des Ressources'],
  });

  readonly paiementForm = this.fb.nonNullable.group({
    montant: [0, [Validators.required, Validators.min(0.01)]],
    mode_paiement: ['Virement', Validators.required],
    ref_paiement: [''],
  });

  readonly resteAPayer = computed(() => {
    const n = this.current();
    if (!n) return 0;
    return Math.round((n.total_mru - (n.montant_paye || 0)) * 100) / 100;
  });

  readonly statuts = [
    'BROUILLON',
    'SOUMIS',
    'EN_CONTROLE',
    'CORRECTION_REQUISE',
    'VISA_MG',
    'VISA_DR',
    'VALIDEE',
    'MISE_EN_PAIEMENT',
    'PARTIELLEMENT_PAYEE',
    'PAYEE',
    'CLOTUREE',
    'ARCHIVEE',
    'REJETEE',
    'ANNULEE',
  ];

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

  private readonly mutationLocked = new Set([
    'MISE_EN_PAIEMENT',
    'PARTIELLEMENT_PAYEE',
    'PAYEE',
    'CLOTUREE',
    'ARCHIVEE',
  ]);

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
    if (!this.canMutate() || this.mutationLocked.has(note.statut)) return false;
    if (this.canSupervise()) return true;
    return note.statut === 'BROUILLON' || note.statut === 'CORRECTION_REQUISE';
  }

  canDelete(note: Note): boolean {
    if (!this.canMutate() || this.mutationLocked.has(note.statut)) return false;
    const user = this.auth.user();
    if (!user) return false;
    if (this.canSupervise()) return true;
    return note.statut === 'BROUILLON' && note.demandeur_id === user.id;
  }

  editHint(note: Note): string {
    if (this.canEdit(note)) return 'Modifier';
    if (this.mutationLocked.has(note.statut)) return 'Modification impossible après la mise en paiement';
    return 'Modification réservée à l’administrateur';
  }

  deleteHint(note: Note): string {
    if (this.canDelete(note)) return 'Supprimer';
    if (this.mutationLocked.has(note.statut)) return 'Suppression impossible après la mise en paiement';
    return 'Suppression réservée à l’administrateur';
  }

  private canMutate(): boolean {
    const user = this.auth.user();
    if (!user) return false;
    if (user.is_superuser) return true;
    return (user.permission_codes ?? []).includes('mg.notes.create');
  }

  private canSupervise(): boolean {
    const user = this.auth.user();
    if (!user) return false;
    if (user.is_superuser) return true;
    const codes = user.permission_codes ?? [];
    return [
      'mg.notes.control',
      'mg.notes.approve',
      'mg.notes.payment',
      'mg.notes.archive',
      'mg.notes.reject',
      'mg.notes.settings',
    ].some((code) => codes.includes(code));
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

  statutLabel(s: string): string {
    const map: Record<string, string> = {
      BROUILLON: 'Brouillon',
      SOUMIS: 'Soumise',
      EN_CONTROLE: 'En contrôle',
      CORRECTION_REQUISE: 'Correction requise',
      VISA_MG: 'Visa MG',
      VISA_DR: 'Visa DR',
      VALIDEE: 'Validée',
      MISE_EN_PAIEMENT: 'Mise en paiement',
      PARTIELLEMENT_PAYEE: 'Partiellement payée',
      PAYEE: 'Payée',
      CLOTUREE: 'Clôturée',
      ARCHIVEE: 'Archivée',
      REJETEE: 'Rejetée',
      ANNULEE: 'Annulée',
    };
    return map[s] || s;
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

  formatApiError(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => {
          if (typeof d === 'string') return d;
          if (d && typeof d === 'object' && 'msg' in d) return String((d as { msg: string }).msg);
          return '';
        })
        .filter(Boolean);
      if (msgs.length) return msgs.join(' · ');
    }
    return fallback;
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
    const motif = window.prompt('Motif de la correction :');
    if (!motif?.trim()) return;
    this.doTransition('demander_correction', motif.trim());
  }

  askReject(): void {
    const motif = window.prompt('Motif du rejet :');
    if (!motif?.trim()) return;
    this.doTransition('rejeter', motif.trim());
  }

  openPaiement(): void {
    const n = this.current();
    if (!n) return;
    this.paiementErreur.set('');
    this.paiementForm.reset({
      montant: this.resteAPayer(),
      mode_paiement: 'Virement',
      ref_paiement: '',
    });
    this.paiementModal.set(true);
  }

  closePaiement(): void {
    if (this.paiementBusy()) return;
    this.paiementModal.set(false);
    this.paiementErreur.set('');
  }

  confirmPaiement(): void {
    const n = this.current();
    if (!n || this.paiementBusy()) return;
    const raw = this.paiementForm.getRawValue();
    const montant = Number(String(raw.montant).replace(',', '.'));
    const reste = this.resteAPayer();
    if (!(montant > 0)) {
      this.paiementErreur.set('Indiquez un montant supérieur à 0.');
      return;
    }
    if (montant > reste + 0.001) {
      this.paiementErreur.set('Le montant dépasse le reste à payer.');
      return;
    }
    this.paiementBusy.set(true);
    this.paiementErreur.set('');
    this.api
      .post<Note>(`/mg/notes-frais/notes/${n.id}/paiement`, {
        montant,
        mode_paiement: raw.mode_paiement,
        ref_paiement: raw.ref_paiement.trim() || null,
      })
      .subscribe({
        next: (updated) => {
          this.paiementBusy.set(false);
          this.paiementModal.set(false);
          this.current.set(updated);
          this.msg.set('Paiement enregistré.');
          this.loadOne(n.id);
        },
        error: (err) => {
          this.paiementBusy.set(false);
          this.paiementErreur.set(this.formatApiError(err, 'Paiement refusé'));
        },
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
