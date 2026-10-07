import { MontantPipe, TauxPipe } from '../shared/montant.pipe';
import { FeedbackService } from '../core/feedback/feedback.service';
import {
  BC_ACTIONS,
  BC_CHAMPS_LOGISTIQUES,
  BC_STATUT_LABELS,
  BcActionDef,
  bcAnnulable,
  bcEditable,
  bcLignesEditables,
  bcRecevable,
  calculerLigne,
  chargerModeTest,
  modeTestAchats,
  totaliser,
} from './achats-circuit';
import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal, untracked } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { SupplierSelectComponent } from './supplier-select.component';
import { AchatsBonApercuComponent } from './achats-apercu.component';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';

interface Agence {
  id: string;
  libelle: string;
}

interface Bon {
  id: string;
  reference: string;
  date_bc: string;
  fournisseur_id?: string | null;
  fournisseur_raison_sociale: string | null;
  statut: string;
  total_ht: number;
  total_tva?: number;
  total_ttc?: number;
  demande_id?: string | null;
  consultation_id?: string | null;
  comparaison_id?: string | null;
  agence_facturation_id?: string | null;
  agence_livraison_id?: string | null;
  date_livraison_prevue?: string | null;
  lignes?: {
    description: string;
    quantite: number;
    prix_unitaire: number;
    uom: string;
    taux_tva?: number;
  }[];
}

const MOYENS_PRESET = ['Amanty', 'Virement', 'Cash'] as const;

@Component({
  selector: 'bea-achats-bons',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MontantPipe,
    TauxPipe,
    MgGedPanelComponent,
    MatIconModule,
    SupplierSelectComponent,
    AchatsBonApercuComponent,
  ],
  styleUrl: './achats-bons.component.css',
  template: `
    <section class="bea-ach">
      @if (mode() === 'list') {
        <header class="bea-ach__hero"><p>Commande</p><h1>Bons de commande</h1><div class="bea-ach__hero-glow"></div></header>
        <div class="bea-ach__head">
          <div class="bea-ach__kpis" style="flex:1;margin:0">
            <div class="bea-ach__kpi" style="--i:0"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>draft</mat-icon></span><span class="bea-ach__kpi-meta"><span>Brouillons</span><strong>{{ count('BROUILLON') }}</strong><em>En rédaction</em></span></div>
            <div class="bea-ach__kpi" style="--i:1"><span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending_actions</mat-icon></span><span class="bea-ach__kpi-meta"><span>En cours</span><strong>{{ enCours() }}</strong><em>Soumis ou validés, non envoyés</em></span></div>
            <div class="bea-ach__kpi" style="--i:2"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>verified</mat-icon></span><span class="bea-ach__kpi-meta"><span>Validés</span><strong>{{ count('VALIDE') }}</strong><em>Commandes actives</em></span></div>
            <div class="bea-ach__kpi" style="--i:3"><span class="bea-ach__kpi-icon" data-tone="blue"><mat-icon>hourglass_bottom</mat-icon></span><span class="bea-ach__kpi-meta"><span>Partiels</span><strong>{{ count('PARTIEL') }}</strong><em>À compléter</em></span></div>
          </div>
          <a class="bea-ach__btn" routerLink="/achats-appro/nouveau"><mat-icon>add</mat-icon>Nouveau BC</a>
        </div>
        <form class="bea-ach__search" [formGroup]="filters">
          <label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence ou fournisseur…" (input)="applyFilters()" /></label>
          <label class="bea-ach__field"><mat-icon>filter_alt</mat-icon><select formControlName="statut" (change)="applyFilters()"><option value="">Tous les statuts</option>@for (s of statutOptions; track s[0]) {<option [value]="s[0]">{{ s[1] }}</option>}</select></label>
        </form>
        <div class="bea-ach__panel">
          <div class="bea-ach__panel-top"><h2>Liste des bons</h2><span class="bea-ach__count">{{ filtered().length }} résultat(s)</span></div>
          <div class="bea-mg__table-scroll"><table class="bea-ach__table">
            <thead><tr><th>Réf.</th><th>Date</th><th>Fournisseur</th><th>Total HT</th><th>Statut</th><th class="bea-ach__th-actions">Actions</th></tr></thead>
            <tbody>
              @for (b of filtered(); track b.id; let i = $index) {
                <tr [style.--i]="i"><td><code class="bea-ach__code">{{ b.reference }}</code></td><td>{{ b.date_bc }}</td><td>{{ b.fournisseur_raison_sociale || '—' }}</td><td>{{ b.total_ht | montant }} MRU</td><td><span class="bea-ach__badge" [attr.data-statut]="b.statut">{{ statutLabel(b.statut) }}</span></td>
                  <td class="bea-ach__actions">
                    <button type="button" class="bea-ach__icon-btn" title="Voir" (click)="apercuId.set(b.id)"><mat-icon>visibility</mat-icon></button>
                    <button type="button" class="bea-ach__icon-btn" [title]="canEdit(b) ? 'Éditer' : 'Bon figé (' + statutLabel(b.statut) + ')'" [disabled]="!canEdit(b)" (click)="edit(b)"><mat-icon>edit</mat-icon></button>
                    <button type="button" class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Annuler le bon" [disabled]="!canCancel(b)" (click)="askCancel(b, 'desactiver')"><mat-icon>block</mat-icon></button>
                    <button type="button" class="bea-ach__icon-btn bea-ach__icon-btn--danger" [title]="b.statut === 'BROUILLON' ? 'Supprimer' : 'Supprimer (avec réceptions, factures et paiements)'" [disabled]="busy()" (click)="askCancel(b, 'supprimer')"><mat-icon>delete</mat-icon></button>
                  </td></tr>
              } @empty { <tr class="bea-ach__empty"><td colspan="6"><mat-icon>receipt_long</mat-icon><p>Aucun bon pour ces critères.</p></td></tr> }
            </tbody>
          </table></div>
        </div>
      } @else {
        <header class="bea-ach__head"><div><p class="bea-ach__kicker">{{ bonId() ? 'Fiche' : 'Création' }}</p><h1>{{ bonId() ? 'Bon de commande' : 'Nouveau bon de commande' }} @if (bonStatut(); as s) {<span class="bea-ach__badge" [attr.data-statut]="s">{{ statutLabel(s) }}</span>}</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/bons"><mat-icon>arrow_back</mat-icon>Retour</a></header>
        @if (verrou(); as v) {
          <p class="bea-ach__lock"><mat-icon>lock</mat-icon>{{ v }}</p>
        } @else if (modeTest() && bonStatut() && bonStatut() !== 'BROUILLON') {
          <p class="bea-ach__lock"><mat-icon>science</mat-icon>Mode test : verrous levés, tout est modifiable (la quantité ne peut pas descendre sous le déjà reçu).</p>
        }
        <form class="bea-ach__form" [formGroup]="form" (ngSubmit)="save()">
          <h2 class="bea-ach__kicker" style="font-size:0.9rem;color:#0f172a;text-transform:none;letter-spacing:0">Fournisseur</h2>
          <div class="bea-ach__grid">
            <label style="grid-column:1/-1">Fournisseur *
              <bea-supplier-select formControlName="fournisseur_id" />
            </label>
            <label>Nom fournisseur <input formControlName="fournisseur_raison_sociale" placeholder="Raison sociale" /></label>
            <label>NIF fournisseur <input formControlName="fournisseur_nif" /></label>
            <label>Tél. fournisseur <input formControlName="fournisseur_telephone" placeholder="+222 …" /></label>
            <label>Adresse fournisseur <input formControlName="fournisseur_adresse" /></label>
          </div>
          <h2 class="bea-ach__kicker" style="font-size:0.9rem;color:#0f172a;text-transform:none;letter-spacing:0;margin-top:0.5rem">Commande &amp; acheteur (BEA)</h2>
          <div class="bea-ach__grid">
            <label>Date BC <input type="date" formControlName="date_bc" /></label>
            <label>Livraison prévue <input type="date" formControlName="date_livraison_prevue" /></label>
            <label>Agence facturation
              <select formControlName="agence_facturation_id">
                <option value="">— Choisir —</option>
                @for (a of agences(); track a.id) {
                  <option [value]="a.id">{{ a.libelle }}</option>
                }
              </select>
            </label>
            <label>Agence livraison
              <select formControlName="agence_livraison_id">
                <option value="">— Choisir —</option>
                @for (a of agences(); track a.id) {
                  <option [value]="a.id">{{ a.libelle }}</option>
                }
              </select>
            </label>
            <label>Département <input formControlName="departement" /></label>
            <label>Projet <input formControlName="projet" /></label>
            <label>Nom acheteur <input formControlName="acheteur_nom" placeholder="Agent BEA" /></label>
            <label>Tél. acheteur <input formControlName="acheteur_tel" placeholder="+222 …" /></label>
            <label>Nom demandeur <input formControlName="demandeur_nom" /></label>
            <label>Date de la demande <input type="date" formControlName="demandeur_date" /></label>
            <label>Adresse facturation <input formControlName="adresse_facturation" /></label>
            <label>Adresse livraison <input formControlName="adresse_livraison" /></label>
          </div>
          <h2 class="bea-ach__kicker" style="font-size:0.9rem;color:#0f172a;text-transform:none;letter-spacing:0;margin-top:0.5rem">Conditions &amp; paiement</h2>
          <div class="bea-ach__grid">
            <div class="bea-ach__field-block">
              <span>Conditions</span>
              <input type="hidden" formControlName="conditions" />
              @if (bonId(); as id) {
                <label class="bea-ach__btn bea-ach__btn--ghost" style="cursor:pointer;display:inline-flex;align-items:center;gap:0.35rem;width:fit-content">
                  <mat-icon>attach_file</mat-icon>
                  {{ conditionsFileName() || 'Importer pièce jointe' }}
                  <input type="file" hidden (change)="onConditionsFile($event, id)" />
                </label>
                @if (conditionsUploadMsg()) {
                  <small style="display:block;margin-top:0.25rem;color:#0f766e">{{ conditionsUploadMsg() }}</small>
                }
              } @else {
                <p class="bea-ach__kicker" style="margin:0;text-transform:none;letter-spacing:0;color:#64748b">Enregistrer le BC pour importer la pièce jointe (Conditions).</p>
              }
            </div>
            <label>Incoterm <input formControlName="incoterm" /></label>
            <label>Conditions de paiement <input formControlName="conditions_paiement" placeholder="Ex. 30 jours" /></label>
            <label>Moyen de paiement
              <select formControlName="moyen_paiement_liste" (change)="onMoyenChange()">
                <option value="">— Choisir —</option>
                <option value="Amanty">Amanty</option>
                <option value="Virement">Virement</option>
                <option value="Cash">Cash (espèces)</option>
                <option value="__autre__">Autre…</option>
              </select>
            </label>
            @switch (form.controls.moyen_paiement_liste.value) {
              @case ('Cash') {
                <div class="bea-ach__pay-detail">
                  <span class="bea-ach__pay-icon"><mat-icon>payments</mat-icon></span>
                  <label>Montant remis en espèces <em>Optionnel</em>
                    <span class="bea-ach__suffix">
                      <input type="number" formControlName="montant_paiement" min="0" step="0.01" placeholder="Ex. 125 000" />
                      <b>MRU</b>
                    </span>
                  </label>
                </div>
              }
              @case ('Virement') {
                <div class="bea-ach__pay-detail">
                  <span class="bea-ach__pay-icon"><mat-icon>account_balance</mat-icon></span>
                  <label>RIB / compte bénéficiaire <em>Optionnel</em>
                    <input formControlName="ref_paiement" maxlength="255" placeholder="RIB, IBAN, banque, compte ailleurs…" />
                  </label>
                </div>
              }
              @case ('Amanty') {
                <div class="bea-ach__pay-detail">
                  <span class="bea-ach__pay-icon"><mat-icon>smartphone</mat-icon></span>
                  <label>N° de téléphone du transfert Amanty <em>Optionnel</em>
                    <input type="tel" formControlName="ref_paiement" maxlength="40" placeholder="+222 …" />
                  </label>
                </div>
              }
              @case ('__autre__') {
                <label>Autre moyen de paiement
                  <input formControlName="moyen_paiement_autre" placeholder="Saisir un autre moyen de paiement…" />
                </label>
              }
            }
          </div>
          <h2 class="bea-ach__kicker" style="font-size:0.9rem;color:#0f172a;text-transform:none;letter-spacing:0;margin-top:0.5rem">Lignes</h2>
          <div class="bea-ach__lines" formArrayName="lignes">
            <div class="bea-ach__lines-head" aria-hidden="true">
              <span>#</span><span>Description</span><span>Qté</span><span>UOM</span><span>PU (MRU)</span><span>Total HT</span><span></span>
            </div>
            @for (ctrl of lignes.controls; track ctrl; let i = $index) {
              <div class="bea-ach__line" [formGroupName]="i">
                <span class="bea-ach__line-num">{{ i + 1 }}</span>
                <label><span class="bea-ach__line-label">Description</span><input formControlName="description" placeholder="Article, service…" /></label>
                <label><span class="bea-ach__line-label">Qté</span><input type="number" formControlName="quantite" min="0.001" step="0.001" /></label>
                <label><span class="bea-ach__line-label">UOM</span><input formControlName="uom" /></label>
                <label><span class="bea-ach__line-label">PU (MRU)</span><input type="number" formControlName="prix_unitaire" min="0" step="0.01" /></label>
                <span class="bea-ach__line-total"><span class="bea-ach__line-label">Total HT</span>{{ ligneHt(i) | montant }}</span>
                <button type="button" class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Retirer la ligne" [disabled]="lignes.length <= 1 || !lignesEditables()" (click)="removeLigne(i)"><mat-icon>delete</mat-icon></button>
              </div>
            }
            @if (lignesEditables()) {
              <button type="button" class="bea-ach__btn bea-ach__btn--ghost bea-ach__lines-add" (click)="addLigne()"><mat-icon>add</mat-icon>Ajouter une ligne</button>
            }
          </div>
          <div class="bea-ach__totals">
            <label class="bea-ach__tva">TVA (%)
              <span class="bea-ach__suffix">
                <input type="number" formControlName="taux_tva" min="0" max="100" step="0.01" />
                <b>%</b>
              </span>
              <small>Mettre 0 s'il n'y a pas de TVA.</small>
            </label>
            <div class="bea-ach__money">
              <div class="bea-ach__money-card"><span>Prix total HT</span><strong>{{ totaux().ht | montant }} MRU</strong></div>
              <div class="bea-ach__money-card"><span>TVA {{ totaux().rate | taux }}</span><strong>{{ totaux().tva | montant }} MRU</strong></div>
              <div class="bea-ach__money-card"><span>Prix total TTC</span><strong>{{ totaux().ttc | montant }} MRU</strong></div>
            </div>
          </div>
            <div class="bea-ach__form-actions">
            @if (!bonStatut() || editable()) {
              <button type="submit" class="bea-ach__btn" [disabled]="busy()"><mat-icon>save</mat-icon>Enregistrer</button>
            }
            @for (t of actions(); track t.action) {
              <button type="button" class="bea-ach__btn" [class.bea-ach__btn--ghost]="t.ghost" [disabled]="busy() || form.dirty" [title]="form.dirty ? 'Enregistrez d’abord vos modifications' : t.label" (click)="transition(t)"><mat-icon>{{ t.icon }}</mat-icon>{{ t.label }}</button>
            }
            @if (recevable()) {
              <a class="bea-ach__btn" routerLink="/achats-appro/receptions/nouvelle" [queryParams]="{ bon_id: bonId() }"><mat-icon>inventory</mat-icon>Réceptionner</a>
            }
          </div>
            @if (bonId(); as id) {
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="openPdfPrep()"><mat-icon>picture_as_pdf</mat-icon>PDF</button>
            <bea-mg-ged moduleCode="achats-appro" entity="bon_commande" [entityId]="id" />
          }
        </form>
      }
      @if (apercuId(); as aid) {
        <bea-achats-bon-apercu [bonId]="aid" (closed)="apercuId.set(null)" />
      }
      @if (pdfPrepOpen()) {
        <div class="bea-ach__backdrop" (click)="closePdfPrep()"></div>
        <div class="bea-ach__modal" role="dialog" aria-modal="true" aria-labelledby="pdf-prep-title">
          <header class="bea-ach__modal-head">
            <div>
              <p class="bea-ach__kicker">Export PDF</p>
              <h2 id="pdf-prep-title">Préparer le Bon de Commande</h2>
            </div>
            <button type="button" class="bea-ach__icon-btn" title="Fermer" (click)="closePdfPrep()"><mat-icon>close</mat-icon></button>
          </header>
          <p style="margin:0 0 1rem;color:#64748b;font-size:0.9rem">Sélectionnez les deux signataires avant de générer le PDF.</p>
          <form class="bea-ach__form" style="box-shadow:none;border:0;padding:0;margin:0" [formGroup]="pdfForm" (ngSubmit)="confirmPdfDownload()">
            <div class="bea-ach__grid" style="grid-template-columns:1fr">
              <label>Signature 1
                <input formControlName="signataire1" placeholder="Signature Chef Sce Moyens Généraux" />
              </label>
              <label>Signature 2
                <input formControlName="signataire2" placeholder="Signature Directrice des Ressources" />
              </label>
            </div>
            @if (pdfErreur()) {
              <p class="bea-ach__error" style="margin-top:0.75rem">{{ pdfErreur() }}</p>
            }
            <footer class="bea-ach__modal-foot" style="margin-top:1.25rem;padding:0;border:0">
              <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="closePdfPrep()">Annuler</button>
              <button type="submit" class="bea-ach__btn" [disabled]="pdfBusy()"><mat-icon>download</mat-icon>{{ pdfBusy() ? 'Génération…' : 'Télécharger le PDF' }}</button>
            </footer>
          </form>
        </div>
      }
    </section>
  `,
})
export class AchatsBonsComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(() => this.mode() === 'edit' && this.form.dirty, () => this.form);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly mode = signal<'list' | 'edit'>('list');
  readonly bons = signal<Bon[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly bonId = signal<string | null>(null);
  readonly bonReference = signal<string | null>(null);
  readonly bonStatut = signal<string | null>(null);
  readonly tvaDefaut = signal(0);
  private parentIds: {
    demande_id?: string;
    consultation_id?: string;
    comparaison_id?: string;
  } = {};
  readonly erreur = feedbackSignal('error', null);
  readonly msg = feedbackSignal('success', '');
  readonly q = signal('');
  readonly statutFilter = signal('');
  readonly busy = signal(false);
  readonly statutOptions = Object.entries(BC_STATUT_LABELS);
  readonly apercuId = signal<string | null>(null);
  readonly pdfPrepOpen = signal(false);
  readonly pdfErreur = signal<string | null>(null);
  readonly pdfBusy = signal(false);
  readonly conditionsFileName = signal<string | null>(null);
  readonly conditionsUploadMsg = signal<string | null>(null);
  readonly formTick = signal(0);
  readonly filters = this.fb.nonNullable.group({ q: '', statut: '' });
  readonly pdfForm = this.fb.nonNullable.group({
    signataire1: ['Signature Chef Sce Moyens Généraux'],
    signataire2: ['Signature Directrice des Ressources'],
  });
  readonly filtered = computed(() => {
    const q = this.q().trim().toLowerCase();
    return this.bons().filter((b) =>
      (!this.statutFilter() || b.statut === this.statutFilter()) &&
      (!q || b.reference.toLowerCase().includes(q) || (b.fournisseur_raison_sociale ?? '').toLowerCase().includes(q)),
    );
  });
  readonly enCours = computed(() => this.bons().filter((b) => ['SOUMIS', 'VALIDE'].includes(b.statut)).length);
  readonly actions = computed(() => {
    const s = this.bonStatut();
    return s ? BC_ACTIONS[s] ?? [] : [];
  });
  readonly editable = computed(() => bcEditable(this.bonStatut()));
  readonly lignesEditables = computed(() => bcLignesEditables(this.bonStatut()));
  readonly recevable = computed(() => bcRecevable(this.bonStatut() ?? ''));
  readonly modeTest = modeTestAchats;
  readonly verrou = computed(() => {
    const s = this.bonStatut();
    if (!s || s === 'BROUILLON') return null;
    if (modeTestAchats()) return null;
    if (!bcEditable(s)) return `Bon ${this.statutLabel(s).toLowerCase()} : consultation seule, aucune modification possible.`;
    return 'Bon engagé : lignes, fournisseur et montants sont verrouillés. Seules la livraison, les contacts et les modalités de paiement restent modifiables.';
  });

  readonly form = this.fb.nonNullable.group({
    date_bc: ['', Validators.required],
    date_livraison_prevue: [''],
    fournisseur_id: [null as string | null],
    fournisseur_raison_sociale: [''],
    fournisseur_nif: [''],
    fournisseur_telephone: [''],
    fournisseur_adresse: [''],
    agence_facturation_id: [''],
    agence_livraison_id: [''],
    departement: ['Siege'],
    projet: [''],
    acheteur_nom: [''],
    acheteur_tel: [''],
    demandeur_nom: [''],
    demandeur_date: [''],
    adresse_facturation: ['Banque El Amana - Siège Central'],
    adresse_livraison: ['SIEGE'],
    conditions: ['Voir pièce jointe'],
    incoterm: ['N/A'],
    conditions_paiement: [''],
    moyen_paiement_liste: [''],
    moyen_paiement_autre: [''],
    ref_paiement: [''],
    montant_paiement: [null as number | null, Validators.min(0)],
    taux_tva: [0, [Validators.required, Validators.min(0), Validators.max(100)]],
    lignes: this.fb.array([this.newLigne()]),
  });

  readonly totaux = computed(() => {
    this.formTick();
    const rate = this.tauxTva();
    const t = totaliser(this.lignes.getRawValue().map((row) => calculerLigne(row.quantite, row.prix_unitaire, rate)));
    return { ...t, rate };
  });

  statutLabel(s: string): string {
    return BC_STATUT_LABELS[s] ?? s;
  }

  /** Miroir des verrous backend : désactive ce que le statut interdit de modifier. */
  private appliquerVerrous(statut: string): void {
    if (statut === 'BROUILLON' || modeTestAchats()) {
      this.form.enable({ emitEvent: false });
      return;
    }
    if (!bcEditable(statut)) {
      this.form.disable({ emitEvent: false });
      return;
    }
    for (const [name, ctrl] of Object.entries(this.form.controls)) {
      if (BC_CHAMPS_LOGISTIQUES.includes(name)) ctrl.enable({ emitEvent: false });
      else ctrl.disable({ emitEvent: false });
    }
  }

  private tauxTva(): number {
    const n = Number(this.form.controls.taux_tva.value);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }

  ligneHt(i: number): number {
    const row = this.lignes.at(i)?.getRawValue();
    return row ? calculerLigne(row.quantite, row.prix_unitaire).ht : 0;
  }

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  private readonly reappliquerVerrous = effect(() => {
    const s = this.bonStatut();
    modeTestAchats();
    if (s) untracked(() => this.appliquerVerrous(s));
  });

  ngOnInit(): void {
    chargerModeTest(this.api);
    this.form.valueChanges.subscribe(() => this.formTick.update((n) => n + 1));
    this.form.controls.fournisseur_id.valueChanges.subscribe((id) => this.fillFromSupplier(id));
    this.loadTvaDefaut();
    this.loadAgences();
    const id = this.route.snapshot.paramMap.get('id');
    const path = this.route.snapshot.routeConfig?.path ?? '';
    if (path === 'nouveau' || id) {
      this.mode.set('edit');
      this.bonId.set(id);
      if (id) this.loadOne(id);
      else {
        this.form.patchValue({ date_bc: new Date().toISOString().slice(0, 10) });
        this.applyQueryPrefills();
      }
    } else {
      this.loadList();
    }
  }

  private loadAgences(): void {
    this.api.get<Agence[]>('/mg/achats/agences').subscribe({
      next: (rows) => this.agences.set(rows),
    });
  }

  private applyQueryPrefills(): void {
    const q = this.route.snapshot.queryParamMap;
    const fournisseurId = q.get('fournisseur_id');
    const consultationId = q.get('consultation_id');
    const demandeId = q.get('demande_id');
    const comparaisonId = q.get('comparaison_id');
    if (fournisseurId) {
      this.form.patchValue({ fournisseur_id: fournisseurId });
      this.fillFromSupplier(fournisseurId);
    }
    this.parentIds = {
      ...(demandeId ? { demande_id: demandeId } : {}),
      ...(consultationId ? { consultation_id: consultationId } : {}),
      ...(comparaisonId ? { comparaison_id: comparaisonId } : {}),
    };
  }

  private fillFromSupplier(id: string | null): void {
    if (!id) return;
    this.api
      .get<{
        raison_sociale: string;
        nif?: string | null;
        telephone?: string | null;
        adresse?: string | null;
      }>(`/mg/achats/fournisseurs/${id}`)
      .subscribe({
        next: (f) => {
          this.form.patchValue(
            {
              fournisseur_raison_sociale: f.raison_sociale ?? '',
              fournisseur_nif: f.nif ?? '',
              fournisseur_telephone: f.telephone ?? '',
              fournisseur_adresse: f.adresse ?? '',
            },
            { emitEvent: false },
          );
        },
      });
  }

  private loadTvaDefaut(): void {
    this.api.get<{ cle: string; valeur: string }[]>('/mg/achats/parametres').subscribe({
      next: (rows) => {
        const row = rows.find((p) => p.cle === 'tva_defaut');
        const n = Number(row?.valeur ?? 0);
        this.tvaDefaut.set(Number.isFinite(n) ? n : 0);
        if (!this.bonId() && this.form.controls.taux_tva.pristine) {
          this.form.controls.taux_tva.setValue(this.tvaDefaut(), { emitEvent: false });
        }
        this.formTick.update((x) => x + 1);
      },
    });
  }

  newLigne() {
    return this.fb.nonNullable.group({
      description: ['', Validators.required],
      quantite: [1, Validators.required],
      prix_unitaire: [0, Validators.required],
      uom: ['U'],
    });
  }

  private resolveMoyenPaiement(): string {
    const liste = this.form.controls.moyen_paiement_liste.value;
    if (liste === '__autre__') return this.form.controls.moyen_paiement_autre.value.trim();
    return liste;
  }

  private resolveDetailPaiement(): { ref_paiement: string | null; montant_paiement: number | null } {
    const liste = this.form.controls.moyen_paiement_liste.value;
    const ref = this.form.controls.ref_paiement.value.trim();
    const montant = this.form.controls.montant_paiement.value;
    return {
      ref_paiement: (liste === 'Virement' || liste === 'Amanty') && ref ? ref : null,
      montant_paiement:
        liste === 'Cash' && montant !== null && `${montant}` !== '' && Number.isFinite(Number(montant))
          ? Number(montant)
          : null,
    };
  }

  onMoyenChange(): void {
    this.form.patchValue({ ref_paiement: '', montant_paiement: null, moyen_paiement_autre: '' });
  }

  private applyMoyenFromApi(value: string): void {
    if (!value) {
      this.form.patchValue({ moyen_paiement_liste: '', moyen_paiement_autre: '' });
      return;
    }
    if ((MOYENS_PRESET as readonly string[]).includes(value)) {
      this.form.patchValue({ moyen_paiement_liste: value, moyen_paiement_autre: '' });
    } else {
      this.form.patchValue({ moyen_paiement_liste: '__autre__', moyen_paiement_autre: value });
    }
  }

  addLigne(): void {
    this.lignes.push(this.newLigne());
    this.form.markAsDirty();
  }

  removeLigne(i: number): void {
    if (this.lignes.length <= 1) return;
    this.lignes.removeAt(i);
    this.form.markAsDirty();
  }

  applyFilters(): void {
    const value = this.filters.getRawValue();
    this.q.set(value.q);
    this.statutFilter.set(value.statut);
  }

  count(statut: string): number {
    return this.bons().filter((b) => b.statut === statut).length;
  }

  canEdit(b: Bon): boolean {
    return bcEditable(b.statut);
  }

  canCancel(b: Bon): boolean {
    return bcAnnulable(b.statut);
  }

  private apiDetail(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((x) => (typeof x === 'string' ? x : (x as { msg?: string })?.msg))
        .filter((x): x is string => !!x);
      if (msgs.length) return msgs.join(' · ');
    }
    return fallback;
  }

  edit(b: Bon): void {
    if (this.canEdit(b)) void this.router.navigateByUrl(`/achats-appro/bons/${b.id}`);
  }

  askCancel(row: Bon, action: 'desactiver' | 'supprimer'): void {
    if (action === 'supprimer') {
      this.feedback
        .run(() => this.api.delete(`/mg/achats/bons/${row.id}`), {
          confirm: {
            action: 'suppression',
            message:
              row.statut === 'BROUILLON'
                ? `Le brouillon ${row.reference} sera retiré de la liste.`
                : `Le bon ${row.reference} sera supprimé avec ses réceptions (stock restitué), factures et paiements.`,
          },
          loading: 'Suppression…',
          errorTitle: 'Suppression refusée',
          success: { title: 'Bon supprimé', details: [{ label: 'Référence', value: row.reference }] },
          busy: this.busy,
        })
        .subscribe({ next: () => this.loadList() });
      return;
    }
    if (!this.canCancel(row)) return;
    this.feedback
      .runWithReason(
        (motif) => this.api.post(`/mg/achats/bons/${row.id}/transition`, { action: 'annuler', motif }),
        {
          reason: {
            title: `Annuler le bon ${row.reference}`,
            message: 'Le bon restera consultable avec son historique. Impossible si une réception ou une facture est active.',
            reasonLabel: 'Motif d’annulation',
            confirmLabel: 'Annuler le bon',
            tone: 'danger',
            icon: 'block',
          },
          loading: 'Annulation…',
          errorTitle: 'Annulation refusée',
          success: { title: 'Bon annulé', details: [{ label: 'Référence', value: row.reference }] },
          busy: this.busy,
        },
      )
      .subscribe({ next: () => this.loadList() });
  }

  loadList(): void {
    this.api.get<{ items: Bon[] }>('/mg/achats/bons', { page: '1', size: '50' }).subscribe({
      next: (res) => this.bons.set(res.items ?? []),
      error: () => this.erreur.set('Impossible de charger les bons.'),
    });
  }

  loadOne(id: string): void {
    this.api.get<Bon & Record<string, string | null>>(`/mg/achats/bons/${id}`).subscribe({
      next: (b) => {
        this.bonStatut.set(b.statut);
        this.bonReference.set(b.reference);
        this.form.enable({ emitEvent: false });
        this.parentIds = {
          ...(b.demande_id ? { demande_id: b.demande_id } : {}),
          ...(b.consultation_id ? { consultation_id: b.consultation_id } : {}),
          ...(b.comparaison_id ? { comparaison_id: b.comparaison_id } : {}),
        };
        this.form.patchValue({
          date_bc: b.date_bc,
          date_livraison_prevue: b.date_livraison_prevue ?? '',
          fournisseur_id: b.fournisseur_id ?? null,
          fournisseur_raison_sociale: b.fournisseur_raison_sociale ?? '',
          fournisseur_nif: (b['fournisseur_nif'] as string) ?? '',
          fournisseur_telephone: (b['fournisseur_telephone'] as string) ?? '',
          fournisseur_adresse: (b['fournisseur_adresse'] as string) ?? '',
          agence_facturation_id: b.agence_facturation_id ?? '',
          agence_livraison_id: b.agence_livraison_id ?? '',
          departement: (b['departement'] as string) ?? '',
          projet: (b['projet'] as string) ?? '',
          acheteur_nom: (b['acheteur_nom'] as string) ?? '',
          acheteur_tel: (b['acheteur_tel'] as string) ?? '',
          demandeur_nom: (b['demandeur_nom'] as string) ?? '',
          demandeur_date: (b['demandeur_date'] as string) ?? '',
          adresse_facturation: (b['adresse_facturation'] as string) ?? '',
          adresse_livraison: (b['adresse_livraison'] as string) ?? '',
          conditions: (b['conditions'] as string) ?? 'Voir pièce jointe',
          incoterm: (b['incoterm'] as string) ?? 'N/A',
          conditions_paiement: (b['conditions_paiement'] as string) ?? '',
        });
        this.applyMoyenFromApi((b['moyen_paiement'] as string) ?? '');
        const montantPaiement = b['montant_paiement'];
        this.form.patchValue({
          ref_paiement: (b['ref_paiement'] as string) ?? '',
          montant_paiement: montantPaiement === null || montantPaiement === undefined ? null : Number(montantPaiement),
          taux_tva: b.lignes?.length ? Number(b.lignes[0].taux_tva ?? 0) : this.tvaDefaut(),
        });
        this.lignes.clear();
        const lignes = b.lignes?.length
          ? b.lignes
          : [{ description: '', quantite: 1, prix_unitaire: 0, uom: 'U' }];
        for (const l of lignes) {
          this.lignes.push(
            this.fb.nonNullable.group({
              description: [l.description, Validators.required],
              quantite: [l.quantite, Validators.required],
              prix_unitaire: [l.prix_unitaire, Validators.required],
              uom: [l.uom || 'U'],
            }),
          );
        }
        this.appliquerVerrous(b.statut);
        this.form.markAsPristine();
        this.formTick.update((n) => n + 1);
      },
      error: () => this.erreur.set('Bon introuvable.'),
    });
  }

  save(): void {
    if (this.form.invalid) return;
    const raw = this.form.getRawValue();
    const {
      moyen_paiement_liste: _liste,
      moyen_paiement_autre: _autre,
      taux_tva: _taux,
      ref_paiement: _ref,
      montant_paiement: _montant,
      ...rest
    } = raw;
    const rate = this.tauxTva();
    const body = {
      ...rest,
      date_livraison_prevue: raw.date_livraison_prevue || null,
      demandeur_date: raw.demandeur_date || null,
      agence_facturation_id: raw.agence_facturation_id || null,
      agence_livraison_id: raw.agence_livraison_id || null,
      moyen_paiement: this.resolveMoyenPaiement() || null,
      ...this.resolveDetailPaiement(),
      ...this.parentIds,
      lignes: raw.lignes.map((l) => ({ ...l, taux_tva: rate })),
    };
    const id = this.bonId();
    this.feedback
      .run(
        () => (id ? this.api.patch<Bon>(`/mg/achats/bons/${id}`, body) : this.api.post<Bon>('/mg/achats/bons', body)),
        {
          loading: 'Enregistrement…',
          errorTitle: 'Enregistrement refusé',
          errorHint: 'Vos données saisies ont été conservées.',
          success: (b) => ({ title: 'Bon enregistré', details: [{ label: 'Référence', value: b.reference }] }),
          busy: this.busy,
          idempotent: !id,
        },
      )
      .subscribe({
        next: (b) => {
          this.form.markAsPristine();
          if (id) this.loadOne(id);
          else void this.router.navigateByUrl(`/achats-appro/bons/${b.id}`);
        },
      });
  }

  transition(t: BcActionDef): void {
    const id = this.bonId();
    if (!id) return;
    const ref = this.bonReference() ?? '';
    const call = (motif?: string) => this.api.post<Bon>(`/mg/achats/bons/${id}/transition`, { action: t.action, motif });
    const common = {
      loading: `${t.label}…`,
      errorTitle: `${t.label} : refusé`,
      success: (b: Bon) => ({
        title: `Bon ${ref} : ${this.statutLabel(b.statut).toLowerCase()}`,
        details: [{ label: 'Statut', value: this.statutLabel(b.statut) }],
      }),
      busy: this.busy,
    };
    const run$ = t.motif
      ? this.feedback.runWithReason((motif) => call(motif), {
          ...common,
          reason: { title: `${t.label} le bon ${ref}`, message: 'Le motif est tracé dans l’historique du bon.', reasonLabel: 'Motif', confirmLabel: t.label, tone: 'danger', icon: t.icon },
        })
      : this.feedback.run(() => call(), {
          ...common,
          confirm: { title: `${t.label} le bon ${ref} ?`, message: this.messageTransition(t.action), confirmLabel: t.label, icon: t.icon },
        });
    run$.subscribe({ next: () => this.loadOne(id) });
  }

  private messageTransition(action: string): string {
    switch (action) {
      case 'soumettre':
        return 'Le bon part en validation. Les lignes ne seront plus modifiables sauf retour en brouillon.';
      case 'valider':
        return 'Le bon devient engageant : lignes, fournisseur et montants seront figés.';
      case 'envoyer':
        return 'Le bon est marqué comme transmis au fournisseur.';
      case 'cloturer':
        return 'Le bon sera figé définitivement.';
      default:
        return 'Le bon revient en brouillon pour correction.';
    }
  }

  openPdfPrep(): void {
    if (!this.bonId()) return;
    this.pdfErreur.set(null);
    this.pdfBusy.set(false);
    this.pdfForm.reset({
      signataire1: 'Signature Chef Sce Moyens Généraux',
      signataire2: 'Signature Directrice des Ressources',
    });
    this.pdfPrepOpen.set(true);
  }

  closePdfPrep(): void {
    this.pdfPrepOpen.set(false);
    this.pdfErreur.set(null);
    this.pdfBusy.set(false);
  }

  private pdfFilename(reference: string | null): string {
    const digits = (reference || '').replace(/\D/g, '') || '0';
    return `Bon-Commande-${digits.padStart(6, '0')}.pdf`;
  }

  confirmPdfDownload(): void {
    const id = this.bonId();
    if (!id) return;
    const v = this.pdfForm.getRawValue();
    const s1 = v.signataire1.trim();
    const s2 = v.signataire2.trim();
    if (!s1 || !s2) {
      this.pdfErreur.set('Veuillez renseigner les deux signataires avant de générer le PDF.');
      return;
    }
    this.pdfErreur.set(null);
    this.pdfBusy.set(true);
    this.api
      .download(`/mg/achats/bons/${id}/pdf`, {
        signataire_1: s1,
        signataire_2: s2,
      })
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = this.pdfFilename(this.bonReference());
          a.click();
          URL.revokeObjectURL(url);
          this.pdfBusy.set(false);
          this.closePdfPrep();
        },
        error: (err) => {
          this.pdfBusy.set(false);
          this.pdfErreur.set(this.apiDetail(err, 'Export PDF impossible.'));
        },
      });
  }

  onConditionsFile(ev: Event, bonId: string): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.conditionsFileName.set(file.name);
    this.conditionsUploadMsg.set(null);
    this.form.patchValue({ conditions: 'Voir pièce jointe' });
    this.api
      .upload('/documents/from-operation', file, {
        espace_code: 'moyens-generaux',
        module_code: 'achats-appro',
        source_type: 'bon_commande',
        source_id: bonId,
        doc_type: 'CONDITIONS',
        title: file.name,
      })
      .subscribe({
        next: () => {
          this.conditionsUploadMsg.set(`Document déposé (OCR en cours) : ${file.name}`);
          input.value = '';
        },
        error: (err) => {
          this.conditionsUploadMsg.set(null);
          this.erreur.set(this.apiDetail(err, 'Import Conditions refusé (permission ged.write ?).'));
        },
      });
  }
}
