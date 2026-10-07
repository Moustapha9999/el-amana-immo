import {
  MontantPipe,
  QuantitePipe,
  formatMontant,
  formatQuantite,
  montantArrondi,
  quantiteDecimale,
} from '../shared/montant.pipe';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { SupplierSelectComponent } from './supplier-select.component';
import { AchatsFactureApercuComponent } from './achats-apercu.component';
import { PIECES_ACCEPT, PIECES_FORMATS_LABEL, verifierPieceJointe } from '../shared/pieces-jointes';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import {
  BC_STATUT_LABELS,
  FACTURE_STATUT_LABELS,
  bcFacturable,
  calculerLigne,
  chargerModeTest,
  factureModifiable,
  facturePayable,
  totaliser,
} from './achats-circuit';

interface BonOpt {
  id: string;
  reference: string;
  statut: string;
  fournisseur_id?: string | null;
}

export interface FactureLigne {
  id?: string;
  bc_ligne_id?: string | null;
  designation: string;
  quantite: number;
  prix_unitaire: number;
  taux_tva?: number | null;
  total_ht?: number;
}

interface LigneProposee {
  bc_ligne_id: string | null;
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
  nb_justificatifs?: number;
  montant_paye?: number;
  reste_a_payer?: number;
  motif_validation?: string | null;
}

export interface RapprochementLigne {
  designation: string;
  quantite_commandee: number;
  quantite_recue: number;
  quantite_deja_facturee: number;
  quantite_facturee: number;
  prix_unitaire_bc: number | null;
  prix_unitaire_facture: number;
  taux_tva_bc: number | null;
  taux_tva_facture: number;
  ok: boolean;
  motifs: string[];
}

export interface ThreeWayMatch {
  resultat: string;
  ecart_quantite: boolean;
  ecart_montant: boolean;
  detail?: string | null;
  bc_total_ttc?: number | null;
  attendu_ttc?: number | null;
  facture_ttc?: number | null;
  qty_commandee?: number | null;
  qty_recue?: number | null;
  qty_facturee?: number | null;
  lignes?: RapprochementLigne[];
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
  private readonly feedback = inject(FeedbackService);
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
  readonly proposition = signal<FactureProposition | null>(null);
  readonly receptions = signal<ReceptionOpt[]>([]);
  readonly chargementBc = signal(false);
  readonly preuve = signal<File | null>(null);
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

  readonly totaux = computed(() =>
    totaliser(this.lignesVal().map((l) => calculerLigne(l.quantite, l.prix_unitaire, l.taux_tva))),
  );

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
  readonly canEditForm = computed(() => {
    const c = this.current();
    return !c || factureModifiable(c.statut);
  });
  readonly matchDetails = computed(() =>
    (this.matchResult()?.detail ?? '')
      .split(';')
      .map((d) => d.trim())
      .filter(Boolean),
  );

  statutLabel(s: string): string {
    return FACTURE_STATUT_LABELS[s] ?? s;
  }

  bcLabel(s: string): string {
    return BC_STATUT_LABELS[s] ?? s;
  }

  payable(s: string): boolean {
    return facturePayable(s);
  }

  pctRegle(f: FactureRow): number {
    const ttc = Number(f.montant_ttc) || 0;
    return ttc > 0 ? Math.min(100, Math.round(((Number(f.montant_paye) || 0) / ttc) * 100)) : 0;
  }

  /** Écart quantité ligne à ligne : somme des dépassements du reçu non encore facturé. */
  ecartQuantite(m: ThreeWayMatch): number {
    return (m.lignes ?? []).reduce((s, l) => {
      const dispo = quantiteDecimale(l.quantite_recue) - quantiteDecimale(l.quantite_deja_facturee);
      return s + Math.max(0, quantiteDecimale(l.quantite_facturee) - dispo);
    }, 0);
  }

  /** TTC facture − TTC attendu pour les quantités de CETTE facture (pas le total du BC). */
  ecartMontant(m: ThreeWayMatch): number {
    return montantArrondi(montantArrondi(m.facture_ttc) - montantArrondi(m.attendu_ttc ?? m.bc_total_ttc));
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

  readonly aValider = computed(() => ['BROUILLON', 'RECUE', 'ANOMALIE'].includes(this.current()?.statut ?? ''));
  private readonly reappliquerVerrou = effect(() => {
    if (!this.current()) return;
    const editable = this.canEditForm();
    untracked(() => (editable ? this.form.enable({ emitEvent: false }) : this.form.disable({ emitEvent: false })));
  });

  ngOnInit(): void {
    chargerModeTest(this.api);
    this.api.get<{ items: BonOpt[] }>('/mg/achats/bons', { page: '1', size: '100' }).subscribe({
      next: (r) =>
        this.bons.set(r.items.filter((b) => bcFacturable(b.statut))),
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
      bc_ligne_id: this.fb.control<string | null>(l?.bc_ligne_id ?? null),
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
  }

  choisirPreuve(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    const refus = verifierPieceJointe(file);
    if (refus) {
      this.erreur.set(refus);
      return;
    }
    this.preuve.set(file);
  }

  readonly piecesAccept = PIECES_ACCEPT;
  readonly piecesFormats = PIECES_FORMATS_LABEL;

  tailleFichier(bytes: number): string {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} Mo`;
  }

  reprendreBc(): void {
    const bid = this.form.controls.bon_id.value;
    if (bid) this.onBon(bid);
  }

  totalLigne(i: number): number {
    const l = this.lignesVal()[i];
    return l ? calculerLigne(l.quantite, l.prix_unitaire).ht : 0;
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

  supprimer(row: FactureRow): void {
    this.feedback
      .run(() => this.api.delete(`/mg/achats/factures/${row.id}`), {
        confirm: {
          action: 'suppression',
          message: `La facture ${row.reference} et ses paiements seront supprimés ; ses quantités redeviennent facturables.`,
        },
        loading: 'Suppression…',
        errorTitle: 'Suppression refusée',
        success: { title: 'Facture supprimée', details: [{ label: 'Référence', value: row.reference }] },
        busy: this.saving,
      })
      .subscribe({
        next: () => {
          if (this.mode() === 'form') void this.router.navigateByUrl('/achats-appro/factures');
          else this.loadList();
        },
      });
  }

  annuler(row: FactureRow): void {
    this.feedback
      .runWithReason((motif) => this.api.post<FactureRow>(`/mg/achats/factures/${row.id}/annuler`, { motif }), {
        reason: {
          title: `Annuler la facture ${row.reference}`,
          message: 'La facture reste consultable ; ses quantités redeviennent facturables.',
          hint: 'Refusé si un paiement est actif : annulez-le d’abord.',
          reasonLabel: 'Motif d’annulation',
          confirmLabel: 'Annuler la facture',
          tone: 'danger',
          icon: 'block',
        },
        loading: 'Annulation…',
        errorTitle: 'Annulation refusée',
        success: { title: 'Facture annulée', details: [{ label: 'Référence', value: row.reference }] },
        busy: this.saving,
      })
      .subscribe({
        next: (f) => {
          if (this.mode() === 'form') this.loadOne(f.id);
          else this.loadList();
        },
      });
  }

  /** Bon à payer. Une facture en anomalie exige un motif (écart accepté, tracé). */
  valider(): void {
    const c = this.current();
    if (!c) return;
    const call = (motif?: string) => this.api.post<FactureRow>(`/mg/achats/factures/${c.id}/valider`, { motif });
    const common = {
      loading: 'Validation…',
      errorTitle: 'Validation refusée',
      success: (f: FactureRow) => ({ title: 'Facture validée', details: [{ label: 'Statut', value: this.statutLabel(f.statut) }] }),
      busy: this.saving,
    };
    const run$ =
      c.ecart_quantite || c.ecart_montant
        ? this.feedback.runWithReason((motif) => call(motif), {
            ...common,
            reason: {
              title: `Valider la facture ${c.reference} malgré l’écart`,
              message: 'Le contrôle 3 voies signale un écart. Justifiez son acceptation.',
              reasonLabel: 'Motif d’acceptation de l’écart',
              confirmLabel: 'Valider',
              tone: 'warn',
              icon: 'report',
            },
          })
        : this.feedback.run(() => call(), {
            ...common,
            confirm: { action: 'validation', message: `La facture ${c.reference} passe « à payer » et ne sera plus modifiable.` },
          });
    run$.subscribe({ next: (f) => this.loadOne(f.id) });
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
        bc_ligne_id: l.bc_ligne_id || null,
        designation: l.designation.trim(),
        quantite: Number(l.quantite),
        prix_unitaire: Number(l.prix_unitaire),
        taux_tva: l.taux_tva === null || l.taux_tva === undefined || `${l.taux_tva}` === '' ? null : Number(l.taux_tva),
      })),
    };
    const req = this.id()
      ? this.api.patch<FactureRow>(`/mg/achats/factures/${this.id()}`, body)
      : this.api.post<FactureRow>('/mg/achats/factures', body);
    const creation = !this.id();
    req.subscribe({
      next: (f) => {
        const fichier = creation ? this.preuve() : null;
        if (!fichier) {
          this.saving.set(false);
          this.msg.set(creation ? 'Facture créée.' : 'Facture mise à jour.');
          this.form.markAsPristine();
          void this.router.navigateByUrl(`/achats-appro/factures/${f.id}`);
          return;
        }
        this.api
          .upload('/documents/from-operation', fichier, {
            espace_code: 'moyens-generaux',
            module_code: 'achats-appro',
            source_type: 'achat_facture',
            source_id: f.id,
            doc_type: 'FACTURE_FOURNISSEUR',
            title: `Facture fournisseur ${f.numero_fournisseur || f.reference}`,
            reference: f.numero_fournisseur || f.reference,
            date_document: f.date_facture,
            fournisseur_id: f.fournisseur_id,
          })
          .subscribe({
            next: () => {
              this.saving.set(false);
              this.preuve.set(null);
              this.msg.set('Facture créée et facture fournisseur archivée.');
              this.form.markAsPristine();
              void this.router.navigateByUrl(`/achats-appro/factures/${f.id}`);
            },
            error: () => {
              this.saving.set(false);
              this.form.markAsPristine();
              this.erreur.set('Facture créée, mais la pièce n’a pas pu être archivée : joignez-la depuis la fiche (permission ged.write ?).');
              void this.router.navigateByUrl(`/achats-appro/factures/${f.id}`);
            },
          });
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
