import {
  MontantPipe,
  QuantitePipe,
  formatMontant,
  formatQuantite,
  montantArrondi,
  quantiteEntiere,
} from '../shared/montant.pipe';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { SupplierSelectComponent } from './supplier-select.component';
import { AchatsFactureApercuComponent } from './achats-apercu.component';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';

interface BonOpt {
  id: string;
  reference: string;
  statut: string;
  fournisseur_id?: string | null;
}

export interface FactureLigne {
  id?: string;
  designation: string;
  quantite: number;
  prix_unitaire: number;
  taux_tva?: number | null;
  total_ht?: number;
}

interface LigneProposee {
  designation: string;
  uom: string;
  quantite: number;
  prix_unitaire: number;
  taux_tva: number;
  total_ht: number;
  quantite_commandee: number;
  quantite_recue: number;
  quantite_deja_facturee: number;
}

export interface FactureProposition {
  bon_id: string;
  bon_reference: string;
  bon_statut: string;
  fournisseur_id: string | null;
  fournisseur_raison_sociale: string | null;
  reception_id: string | null;
  reception_reference: string | null;
  date_echeance: string | null;
  conditions_paiement: string | null;
  devise: string;
  lignes: LigneProposee[];
  montant_ht: number;
  montant_tva: number;
  montant_ttc: number;
  bc_total_ttc: number;
  deja_facture_ttc: number;
  nb_factures: number;
  message: string | null;
}

interface BcDetail {
  id: string;
  lignes: { description: string; taux_tva: number }[];
}

interface ReceptionOpt {
  id: string;
  reference: string;
  date_reception: string;
  statut: string;
}

export interface FactureRow {
  id: string;
  reference: string;
  numero_fournisseur?: string | null;
  fournisseur_id: string;
  bon_id: string;
  reception_id?: string | null;
  date_facture: string;
  date_echeance?: string | null;
  montant_ht: number;
  montant_tva: number;
  montant_ttc: number;
  statut: string;
  ecart_quantite: boolean;
  ecart_montant: boolean;
  observation?: string | null;
  lignes?: FactureLigne[];
}

export interface ThreeWayMatch {
  resultat: string;
  ecart_quantite: boolean;
  ecart_montant: boolean;
  detail?: string | null;
  bc_total_ttc?: number | null;
  facture_ttc?: number | null;
  qty_commandee?: number | null;
  qty_recue?: number | null;
  qty_facturee?: number | null;
}

type Mode = 'list' | 'form';

@Component({
  selector: 'bea-achats-factures',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MontantPipe,
    QuantitePipe,
    MatIconModule,
    MgGedPanelComponent,
    SupplierSelectComponent,
    AchatsFactureApercuComponent,
  ],
  templateUrl: './achats-factures.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsFacturesComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(() => this.mode() === 'form' && this.form.dirty && !this.saving(), () => this.form);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly rows = signal<FactureRow[]>([]);
  readonly current = signal<FactureRow | null>(null);
  readonly bons = signal<BonOpt[]>([]);
  readonly erreur = feedbackSignal('error', '');
  readonly msg = feedbackSignal('success', '');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly matching = signal(false);
  readonly matchResult = signal<ThreeWayMatch | null>(null);
  readonly q = signal('');
  readonly apercuId = signal<string | null>(null);
  readonly confirm = signal<{ row: FactureRow; action: 'desactiver' | 'supprimer' } | null>(null);

  readonly proposition = signal<FactureProposition | null>(null);
  readonly receptions = signal<ReceptionOpt[]>([]);
  readonly chargementBc = signal(false);
  readonly fournisseurSel = signal('');
  readonly lignesVal = signal<{ quantite: number; prix_unitaire: number; taux_tva: number | null }[]>([]);

  readonly filters = this.fb.nonNullable.group({ q: '' });
  readonly form = this.fb.nonNullable.group({
    fournisseur_id: ['', Validators.required],
    bon_id: ['', Validators.required],
    reception_id: [''],
    numero_fournisseur: [''],
    date_facture: [new Date().toISOString().slice(0, 10), Validators.required],
    date_echeance: [''],
    observation: [''],
    lignes: this.fb.array([this.newLigne()]),
  });

  readonly bonsFournisseur = computed(() => {
    const fid = this.fournisseurSel();
    return fid ? this.bons().filter((b) => !b.fournisseur_id || b.fournisseur_id === fid) : this.bons();
  });

  readonly totaux = computed(() => {
    let ht = 0;
    let tva = 0;
    for (const l of this.lignesVal()) {
      const lht = montantArrondi(quantiteEntiere(l.quantite) * montantArrondi(l.prix_unitaire));
      ht += lht;
      tva += (lht * (Number(l.taux_tva) || 0)) / 100;
    }
    ht = montantArrondi(ht);
    tva = montantArrondi(tva);
    return { ht, tva, ttc: montantArrondi(ht + tva) };
  });

  /** Reste à facturer sur le BC (hors facture en cours) comparé au TTC saisi. */
  readonly ecartProposition = computed(() => {
    const p = this.proposition();
    if (!p) return null;
    const reste = montantArrondi(Number(p.bc_total_ttc) - Number(p.deja_facture_ttc));
    return { reste, ecart: montantArrondi(this.totaux().ttc - reste) };
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    return this.rows().filter((r) => {
      if (!term) return true;
      return (
        r.reference.toLowerCase().includes(term) ||
        r.bon_id.toLowerCase().includes(term) ||
        (r.numero_fournisseur ?? '').toLowerCase().includes(term)
      );
    });
  });

  readonly total = computed(() => this.rows().reduce((n, r) => n + Number(r.montant_ttc || 0), 0));
  readonly ecarts = computed(() => this.rows().filter((r) => r.ecart_quantite || r.ecart_montant).length);
  readonly canEditForm = computed(() => true);
  readonly matchDetails = computed(() =>
    (this.matchResult()?.detail ?? '')
      .split(';')
      .map((d) => d.trim())
      .filter(Boolean),
  );

  /** Référence quantité : la réception si elle existe, sinon la commande (même règle que le backend). */
  ecartQuantite(m: ThreeWayMatch): number {
    const recue = quantiteEntiere(m.qty_recue);
    const ref = recue > 0 ? recue : quantiteEntiere(m.qty_commandee);
    return quantiteEntiere(m.qty_facturee) - ref;
  }

  ecartMontant(m: ThreeWayMatch): number {
    return montantArrondi(montantArrondi(m.facture_ttc) - montantArrondi(m.bc_total_ttc));
  }

  ecartQuantiteLabel(m: ThreeWayMatch): string {
    const d = this.ecartQuantite(m);
    return `${d > 0 ? '+' : ''}${formatQuantite(d)}`;
  }

  ecartMontantLabel(m: ThreeWayMatch): string {
    const d = this.ecartMontant(m);
    return `${d > 0 ? '+' : ''}${formatMontant(d, 'MRU')}`;
  }

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    this.api.get<{ items: BonOpt[] }>('/mg/achats/bons', { page: '1', size: '100' }).subscribe({
      next: (r) =>
        this.bons.set(
          r.items.filter((b) => !['BROUILLON', 'ANNULE', 'ANNULEE', 'REJETEE'].includes(b.statut)),
        ),
    });
    this.form.controls.lignes.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.syncLignes());
    this.form.controls.fournisseur_id.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((fid) => this.onFournisseur(fid));
    this.form.controls.bon_id.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((bid) => this.onBon(bid));
    this.syncLignes();
    const param = this.route.snapshot.paramMap.get('id');
    if (this.router.url.endsWith('/nouvelle') || param) {
      this.mode.set('form');
      if (param) {
        this.id.set(param);
        this.loadOne(param);
      }
    } else {
      this.loadList();
    }
  }

  newLigne(l?: Partial<FactureLigne>) {
    return this.fb.group({
      designation: this.fb.nonNullable.control(l?.designation ?? '', Validators.required),
      quantite: this.fb.nonNullable.control(Number(l?.quantite ?? 1), Validators.required),
      prix_unitaire: this.fb.nonNullable.control(Number(l?.prix_unitaire ?? 0), Validators.required),
      taux_tva: this.fb.control<number | null>(l?.taux_tva ?? null),
    });
  }

  private syncLignes(): void {
    this.lignesVal.set(
      this.lignes.getRawValue().map((l: { quantite: number; prix_unitaire: number; taux_tva: number | null }) => ({
        quantite: Number(l.quantite) || 0,
        prix_unitaire: Number(l.prix_unitaire) || 0,
        taux_tva: l.taux_tva,
      })),
    );
  }

  private setLignes(lignes: Partial<FactureLigne>[]): void {
    this.lignes.clear({ emitEvent: false });
    for (const l of lignes.length ? lignes : [{}]) this.lignes.push(this.newLigne(l), { emitEvent: false });
    this.syncLignes();
  }

  private onFournisseur(fid: string): void {
    this.fournisseurSel.set(fid);
    const bid = this.form.controls.bon_id.value;
    const bon = this.bons().find((b) => b.id === bid);
    if (bon?.fournisseur_id && fid && bon.fournisseur_id !== fid) {
      this.form.controls.bon_id.setValue('');
      return;
    }
    if (!bid && !this.id()) {
      const candidats = this.bonsFournisseur();
      if (candidats.length === 1) this.form.controls.bon_id.setValue(candidats[0].id);
    }
  }

  /** Choix du BC : le backend propose fournisseur, réception, échéance et lignes restant à facturer. */
  private onBon(bid: string): void {
    this.proposition.set(null);
    this.receptions.set([]);
    if (!bid) return;
    this.chargementBc.set(true);
    this.api.get<ReceptionOpt[]>('/mg/achats/receptions', { bon_id: bid }).subscribe({
      next: (rows) => this.receptions.set(rows.filter((r) => r.statut !== 'ANNULEE')),
    });
    const params: Record<string, string> = { bon_id: bid, date_facture: this.form.controls.date_facture.value };
    if (this.id()) params['facture_id'] = this.id()!;
    this.api.get<FactureProposition>('/mg/achats/factures/proposition', params).subscribe({
      next: (p) => {
        this.chargementBc.set(false);
        this.proposition.set(p);
        if (p.fournisseur_id && this.form.controls.fournisseur_id.value !== p.fournisseur_id) {
          this.form.controls.fournisseur_id.setValue(p.fournisseur_id, { emitEvent: false });
          this.fournisseurSel.set(p.fournisseur_id);
        }
        this.form.controls.reception_id.setValue(p.reception_id ?? '');
        if (!this.form.controls.date_echeance.value && p.date_echeance) {
          this.form.controls.date_echeance.setValue(p.date_echeance);
        }
        this.setLignes(p.lignes);
        this.form.markAsDirty();
      },
      error: (err) => {
        this.chargementBc.set(false);
        this.erreur.set(this.apiDetail(err, 'Détails du BC indisponibles.'));
      },
    });
  }

  /** En modification : reprend le contexte du BC sans écraser les lignes saisies. */
  private chargerContexteBc(f: FactureRow): void {
    this.api.get<ReceptionOpt[]>('/mg/achats/receptions', { bon_id: f.bon_id }).subscribe({
      next: (rows) => this.receptions.set(rows.filter((r) => r.statut !== 'ANNULEE')),
    });
    this.api
      .get<FactureProposition>('/mg/achats/factures/proposition', { bon_id: f.bon_id, facture_id: f.id })
      .subscribe({ next: (p) => this.proposition.set(p) });
    this.api.get<BcDetail>(`/mg/achats/bons/${f.bon_id}`).subscribe({
      next: (b) => {
        const taux = new Map(b.lignes.map((l) => [l.description.trim().toLowerCase(), Number(l.taux_tva) || 0]));
        this.lignes.controls.forEach((ctrl) => {
          const d = String(ctrl.get('designation')?.value ?? '').trim().toLowerCase();
          if (taux.has(d)) ctrl.get('taux_tva')?.setValue(taux.get(d)!, { emitEvent: false });
        });
        this.syncLignes();
      },
    });
  }

  reprendreBc(): void {
    const bid = this.form.controls.bon_id.value;
    if (bid) this.onBon(bid);
  }

  totalLigne(i: number): number {
    const l = this.lignesVal()[i];
    return l ? montantArrondi(quantiteEntiere(l.quantite) * montantArrondi(l.prix_unitaire)) : 0;
  }

  addLigne(): void {
    this.lignes.push(this.newLigne());
  }

  removeLigne(i: number): void {
    if (this.lignes.length <= 1) return;
    this.lignes.removeAt(i);
  }

  loadList(): void {
    this.api.get<FactureRow[]>('/mg/achats/factures').subscribe({
      next: (r) => this.rows.set(r),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Factures indisponibles.')),
    });
  }

  loadOne(id: string): void {
    this.api.get<FactureRow>(`/mg/achats/factures/${id}`).subscribe({
      next: (f) => {
        this.current.set(f);
        this.form.patchValue(
          {
            fournisseur_id: f.fournisseur_id,
            bon_id: f.bon_id,
            reception_id: f.reception_id ?? '',
            numero_fournisseur: f.numero_fournisseur ?? '',
            date_facture: f.date_facture,
            date_echeance: f.date_echeance ?? '',
            observation: f.observation ?? '',
          },
          { emitEvent: false },
        );
        this.fournisseurSel.set(f.fournisseur_id);
        this.setLignes(f.lignes ?? []);
        this.form.markAsPristine();
        this.chargerContexteBc(f);
        if (!this.canEditForm()) this.form.disable({ emitEvent: false });
        else this.form.enable({ emitEvent: false });
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Facture introuvable.')),
    });
  }

  search(): void {
    this.q.set(this.filters.controls.q.value.trim());
  }

  open(r: FactureRow): void {
    this.apercuId.set(r.id);
  }

  ecartLabel(r: FactureRow): string {
    if (r.ecart_quantite || r.ecart_montant) return 'Écart';
    return 'Conforme';
  }

  ecartStatut(r: FactureRow): string {
    return r.ecart_quantite || r.ecart_montant ? 'ANOMALIE' : 'VALIDE';
  }

  askAction(row: FactureRow, action: 'desactiver' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/factures/${c.row.id}`)
        : this.api.post(`/mg/achats/factures/${c.row.id}/desactiver`, {});
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? `Facture ${c.row.reference} supprimée.`
            : `Facture ${c.row.reference} désactivée.`,
        );
        if (this.mode() === 'form') void this.router.navigateByUrl('/achats-appro/factures');
        else this.loadList();
      },
      error: (err) => {
        this.confirm.set(null);
        this.erreur.set(this.apiDetail(err, 'Action refusée.'));
      },
    });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.erreur.set('Complétez fournisseur, BC, dates et lignes.');
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    const v = this.form.getRawValue();
    const body = {
      fournisseur_id: v.fournisseur_id,
      bon_id: v.bon_id,
      numero_fournisseur: v.numero_fournisseur.trim() || null,
      date_facture: v.date_facture,
      date_echeance: v.date_echeance || null,
      observation: v.observation.trim() || null,
      ...(this.id() ? {} : { reception_id: v.reception_id || null }),
      lignes: v.lignes.map((l) => ({
        designation: l.designation.trim(),
        quantite: Number(l.quantite),
        prix_unitaire: Number(l.prix_unitaire),
        taux_tva: l.taux_tva === null || l.taux_tva === undefined || `${l.taux_tva}` === '' ? null : Number(l.taux_tva),
      })),
    };
    const req = this.id()
      ? this.api.patch<FactureRow>(`/mg/achats/factures/${this.id()}`, body)
      : this.api.post<FactureRow>('/mg/achats/factures', body);
    req.subscribe({
      next: (f) => {
        this.saving.set(false);
        this.msg.set(this.id() ? 'Facture mise à jour.' : 'Facture créée.');
        void this.router.navigateByUrl(`/achats-appro/factures/${f.id}`);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.'));
      },
    });
  }

  match(): void {
    const id = this.id();
    if (!id) return;
    this.matching.set(true);
    this.matchResult.set(null);
    this.api.post<ThreeWayMatch>(`/mg/achats/factures/${id}/match`, {}).subscribe({
      next: (r) => {
        this.matching.set(false);
        this.matchResult.set(r);
        this.loadOne(id);
      },
      error: (err) => {
        this.matching.set(false);
        this.erreur.set(this.apiDetail(err, 'Contrôle impossible.'));
      },
    });
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
}
