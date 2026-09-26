import { MontantPipe, montantLigne } from '../shared/montant.pipe';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { SupplierSelectComponent } from './supplier-select.component';

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
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MgGedPanelComponent, MatIconModule, SupplierSelectComponent],
  template: `
    <section class="bea-ach">
      @if (mode() === 'list') {
        <header class="bea-ach__hero"><p>Commande</p><h1>Bons de commande</h1><div class="bea-ach__hero-glow"></div></header>
        <div class="bea-ach__head">
          <div class="bea-ach__kpis" style="flex:1;margin:0">
            <div class="bea-ach__kpi" style="--i:0"><span class="bea-ach__kpi-icon" data-tone="navy"><mat-icon>draft</mat-icon></span><span class="bea-ach__kpi-meta"><span>Brouillons</span><strong>{{ count('BROUILLON') }}</strong><em>En rédaction</em></span></div>
            <div class="bea-ach__kpi" style="--i:1"><span class="bea-ach__kpi-icon" data-tone="warn"><mat-icon>pending_actions</mat-icon></span><span class="bea-ach__kpi-meta"><span>En cours</span><strong>{{ enCours() }}</strong><em>Circuits de visa</em></span></div>
            <div class="bea-ach__kpi" style="--i:2"><span class="bea-ach__kpi-icon" data-tone="teal"><mat-icon>verified</mat-icon></span><span class="bea-ach__kpi-meta"><span>Validés</span><strong>{{ count('VALIDE') }}</strong><em>Commandes actives</em></span></div>
            <div class="bea-ach__kpi" style="--i:3"><span class="bea-ach__kpi-icon" data-tone="blue"><mat-icon>hourglass_bottom</mat-icon></span><span class="bea-ach__kpi-meta"><span>Partiels</span><strong>{{ count('PARTIEL') }}</strong><em>À compléter</em></span></div>
          </div>
          <a class="bea-ach__btn" routerLink="/achats-appro/nouveau"><mat-icon>add</mat-icon>Nouveau BC</a>
        </div>
        <form class="bea-ach__search" [formGroup]="filters">
          <label class="bea-ach__field bea-ach__field--grow"><mat-icon>search</mat-icon><input formControlName="q" placeholder="Référence ou fournisseur…" (input)="applyFilters()" /></label>
          <label class="bea-ach__field"><mat-icon>filter_alt</mat-icon><select formControlName="statut" (change)="applyFilters()"><option value="">Tous les statuts</option><option value="BROUILLON">Brouillon</option><option value="SOUMIS">Soumis</option><option value="VISA_MG">Visa MG</option><option value="VISA_DR">Visa DR</option><option value="VALIDE">Validé</option><option value="PARTIEL">Partiel</option><option value="ANNULE">Annulé</option></select></label>
        </form>
        @if (erreur()) { <p class="bea-ach__error">{{ erreur() }}</p> }
        @if (msg()) { <p class="bea-ach__ok">{{ msg() }}</p> }
        <div class="bea-ach__panel">
          <div class="bea-ach__panel-top"><h2>Liste des bons</h2><span class="bea-ach__count">{{ filtered().length }} résultat(s)</span></div>
          <div class="bea-mg__table-scroll"><table class="bea-ach__table">
            <thead><tr><th>Réf.</th><th>Date</th><th>Fournisseur</th><th>Total HT</th><th>Statut</th><th class="bea-ach__th-actions">Actions</th></tr></thead>
            <tbody>
              @for (b of filtered(); track b.id; let i = $index) {
                <tr [style.--i]="i"><td><code class="bea-ach__code">{{ b.reference }}</code></td><td>{{ b.date_bc }}</td><td>{{ b.fournisseur_raison_sociale || '—' }}</td><td>{{ b.total_ht | montant }} MRU</td><td><span class="bea-ach__badge" [attr.data-statut]="b.statut">{{ b.statut }}</span></td>
                  <td class="bea-ach__actions">
                    <a class="bea-ach__icon-btn" title="Voir" [routerLink]="['/achats-appro/bons', b.id]"><mat-icon>visibility</mat-icon></a>
                    <button type="button" class="bea-ach__icon-btn" title="Éditer" [disabled]="!canEdit(b)" (click)="edit(b)"><mat-icon>edit</mat-icon></button>
                    <button type="button" class="bea-ach__icon-btn bea-ach__icon-btn--warn" title="Désactiver" [disabled]="!canCancel(b)" (click)="askCancel(b, 'desactiver')"><mat-icon>block</mat-icon></button>
                    <button type="button" class="bea-ach__icon-btn bea-ach__icon-btn--danger" title="Supprimer" [disabled]="!canDelete(b)" (click)="askCancel(b, 'supprimer')"><mat-icon>delete</mat-icon></button>
                  </td></tr>
              } @empty { <tr class="bea-ach__empty"><td colspan="6"><mat-icon>receipt_long</mat-icon><p>Aucun bon pour ces critères.</p></td></tr> }
            </tbody>
          </table></div>
        </div>
      } @else {
        <header class="bea-ach__head"><div><p class="bea-ach__kicker">{{ bonId() ? 'Fiche' : 'Création' }}</p><h1>{{ bonId() ? 'Bon de commande' : 'Nouveau bon de commande' }}</h1></div><a class="bea-ach__btn bea-ach__btn--ghost" routerLink="/achats-appro/bons"><mat-icon>arrow_back</mat-icon>Retour</a></header>
        @if (erreur()) { <p class="bea-ach__error">{{ erreur() }}</p> }
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
              <span class="bea-ach__field-label">Conditions</span>
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
              <select formControlName="moyen_paiement_liste">
                <option value="">— Choisir —</option>
                <option value="Amanty">Amanty</option>
                <option value="Virement">Virement</option>
                <option value="Cash">Cash</option>
                <option value="__autre__">Autre…</option>
              </select>
            </label>
            <label>Autre moyen (si différent)
              <input formControlName="moyen_paiement_autre" placeholder="Saisir un autre moyen de paiement…" />
            </label>
          </div>
          <h2 style="margin:0.75rem 0 0.35rem;font-size:1rem">Lignes</h2>
          <div formArrayName="lignes">
            @for (ctrl of lignes.controls; track $index; let i = $index) {
              <div class="bea-ach__grid" [formGroupName]="i">
                <label>Description <input formControlName="description" /></label>
                <label>Qté <input type="number" formControlName="quantite" /></label>
                <label>PU <input type="number" formControlName="prix_unitaire" /></label>
                <label>UOM <input formControlName="uom" /></label>
              </div>
            }
          </div>
          <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="addLigne()"><mat-icon>add</mat-icon>Ligne</button>
          <p class="bea-ach__kicker" style="margin:0.75rem 0 0.35rem;text-transform:none;letter-spacing:0;color:#64748b">
            TVA appliquée : {{ tvaDefaut() }}% (paramètre <code class="bea-ach__code">tva_defaut</code>)
          </p>
          <div class="bea-ach__money" style="margin:0.35rem 0 0.75rem">
            <div class="bea-ach__money-card"><span>Prix total HT</span><strong>{{ totaux().ht | montant }} MRU</strong></div>
            <div class="bea-ach__money-card"><span>Prix total TVA</span><strong>{{ totaux().tva | montant }} MRU</strong></div>
            <div class="bea-ach__money-card"><span>Prix total TTC</span><strong>{{ totaux().ttc | montant }} MRU</strong></div>
          </div>
            <div class="bea-ach__form-actions">
            <button type="submit" class="bea-ach__btn"><mat-icon>save</mat-icon>Enregistrer</button>
            @if (nextTransition(); as next) {
              <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="transition(next.action)">{{ next.label }}</button>
            }
            @if (bonStatut() === 'VALIDE' || bonStatut() === 'PARTIEL' || bonStatut() === 'ENVOYE') {
              <a class="bea-ach__btn" routerLink="/stock-fournitures/entrees"><mat-icon>inventory</mat-icon>Réception stock</a>
            }
          </div>
            @if (bonId(); as id) {
            <button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="openPdfPrep()"><mat-icon>picture_as_pdf</mat-icon>PDF</button>
            <bea-mg-ged moduleCode="achats-appro" entity="bon_commande" [entityId]="id" />
          }
        </form>
      }
      @if (confirm(); as c) {
        <div class="bea-ach__backdrop" (click)="confirm.set(null)"></div>
        <div class="bea-ach__modal" role="dialog" aria-modal="true"><header class="bea-ach__modal-head"><div><p class="bea-ach__kicker">Confirmation</p><h2>{{ c.action === 'supprimer' ? 'Supprimer' : 'Désactiver' }} le bon ?</h2></div><button type="button" class="bea-ach__icon-btn" title="Fermer" (click)="confirm.set(null)"><mat-icon>close</mat-icon></button></header><p>Le bon <code class="bea-ach__code">{{ c.row.reference }}</code> {{ c.action === 'supprimer' ? 'sera retiré de la liste.' : 'sera annulé.' }}</p><footer class="bea-ach__modal-foot"><button type="button" class="bea-ach__btn bea-ach__btn--ghost" (click)="confirm.set(null)">Retour</button><button type="button" class="bea-ach__btn" (click)="confirmCancel()">Confirmer</button></footer></div>
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
  private readonly api = inject(ApiService);
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
  readonly erreur = signal<string | null>(null);
  readonly msg = signal('');
  readonly q = signal('');
  readonly statutFilter = signal('');
  readonly confirm = signal<{ row: Bon; action: 'desactiver' | 'supprimer' } | null>(null);
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
  readonly enCours = computed(() => this.bons().filter((b) => ['SOUMIS', 'VISA_MG', 'VISA_DR'].includes(b.statut)).length);
  readonly nextTransition = computed(() => {
    const s = this.bonStatut();
    const map: Record<string, { action: string; label: string }> = {
      BROUILLON: { action: 'soumettre', label: 'Soumettre' },
      SOUMIS: { action: 'visa_mg', label: 'Visa MG' },
      VISA_MG: { action: 'visa_dr', label: 'Visa DR' },
      VISA_DR: { action: 'valider', label: 'Valider' },
    };
    return s ? map[s] ?? null : null;
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
    lignes: this.fb.array([this.newLigne()]),
  });

  readonly totaux = computed(() => {
    this.formTick();
    const rate = this.tvaDefaut();
    let ht = 0;
    for (const row of this.lignes.getRawValue()) {
      ht += montantLigne(row.quantite, row.prix_unitaire);
    }
    const tva = ht * (rate / 100);
    return { ht, tva, ttc: ht + tva };
  });

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
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
        this.formTick.update((x) => x + 1);
      },
    });
  }

  newLigne() {
    return this.fb.nonNullable.group({
      description: ['', Validators.required],
      quantite: [1, Validators.required],
      prix_unitaire: [0, Validators.required],
      taux_tva: [this.tvaDefaut()],
      uom: ['U'],
    });
  }

  private resolveMoyenPaiement(): string {
    const autre = this.form.controls.moyen_paiement_autre.value.trim();
    const liste = this.form.controls.moyen_paiement_liste.value;
    if (autre) return autre;
    if (liste && liste !== '__autre__') return liste;
    return '';
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
  }

  applyFilters(): void {
    const value = this.filters.getRawValue();
    this.q.set(value.q);
    this.statutFilter.set(value.statut);
  }

  count(statut: string): number {
    return this.bons().filter((b) => b.statut === statut).length;
  }

  canEdit(_b: Bon): boolean {
    return true;
  }

  canCancel(_b: Bon): boolean {
    return true;
  }

  canDelete(_b: Bon): boolean {
    return true;
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
    if (action === 'supprimer' ? this.canDelete(row) : this.canCancel(row)) {
      this.confirm.set({ row, action });
    }
  }

  confirmCancel(): void {
    const current = this.confirm();
    if (!current) return;
    const id = current.row.id;
    const req =
      current.action === 'supprimer'
        ? this.api.delete(`/mg/achats/bons/${id}`)
        : this.api.post(`/mg/achats/bons/${id}/transition`, { action: 'annuler' });
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          current.action === 'supprimer'
            ? `Bon ${current.row.reference} supprimé.`
            : `Bon ${current.row.reference} annulé.`,
        );
        this.loadList();
      },
      error: (err) => {
        this.confirm.set(null);
        this.erreur.set(
          this.apiDetail(
            err,
            current.action === 'supprimer' ? 'Suppression refusée.' : 'Annulation refusée.',
          ),
        );
      },
    });
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
        this.lignes.clear();
        const rate = this.tvaDefaut();
        const lignes = b.lignes?.length
          ? b.lignes
          : [{ description: '', quantite: 1, prix_unitaire: 0, uom: 'U', taux_tva: rate }];
        for (const l of lignes) {
          this.lignes.push(
            this.fb.nonNullable.group({
              description: [l.description, Validators.required],
              quantite: [l.quantite, Validators.required],
              prix_unitaire: [l.prix_unitaire, Validators.required],
              taux_tva: [rate],
              uom: [l.uom || 'U'],
            }),
          );
        }
        this.formTick.update((n) => n + 1);
      },
      error: () => this.erreur.set('Bon introuvable.'),
    });
  }

  save(): void {
    if (this.form.invalid) return;
    const raw = this.form.getRawValue();
    const { moyen_paiement_liste: _liste, moyen_paiement_autre: _autre, ...rest } = raw;
    const rate = this.tvaDefaut();
    const body = {
      ...rest,
      date_livraison_prevue: raw.date_livraison_prevue || null,
      demandeur_date: raw.demandeur_date || null,
      agence_facturation_id: raw.agence_facturation_id || null,
      agence_livraison_id: raw.agence_livraison_id || null,
      moyen_paiement: this.resolveMoyenPaiement() || null,
      ...this.parentIds,
      lignes: raw.lignes.map((l) => ({ ...l, taux_tva: rate })),
    };
    const req = this.bonId()
      ? this.api.patch<Bon>(`/mg/achats/bons/${this.bonId()}`, body)
      : this.api.post<Bon>('/mg/achats/bons', body);
    req.subscribe({
      next: (b) => void this.router.navigateByUrl(`/achats-appro/bons/${b.id}`),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.')),
    });
  }

  transition(action: string): void {
    const id = this.bonId();
    if (!id) return;
    this.erreur.set(null);
    this.api.post(`/mg/achats/bons/${id}/transition`, { action }).subscribe({
      next: () => this.loadOne(id),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Transition refusée.')),
    });
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
