import { MontantPipe } from '../shared/montant.pipe';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { FeedbackService } from '../core/feedback/feedback.service';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { formatMontant } from '../shared/montant.pipe';
import { AchatsPaiementApercuComponent } from './achats-apercu.component';
import {
  FACTURE_STATUT_LABELS,
  MOYEN_AUTRE,
  chargerModeTest,
  decomposerMoyen,
  facturePayable,
  modeTestAchats,
} from './achats-circuit';

interface FactureOpt {
  id: string;
  bon_id?: string;
  reference: string;
  montant_ttc: number;
  montant_paye?: number;
  reste_a_payer?: number;
  statut: string;
  date_echeance?: string | null;
}

export const PAIEMENT_STATUT_LABELS: Record<string, string> = {
  A_PAYER: 'À payer',
  PAYE: 'Payé',
  ANNULE: 'Annulé',
};

export interface PaiementRow {
  id: string;
  reference: string;
  facture_id: string;
  fournisseur_id: string;
  montant: number;
  date_echeance: string | null;
  date_paiement: string | null;
  mode_paiement: string | null;
  reference_paiement: string | null;
  statut: string;
  observation: string | null;
}

type Mode = 'list' | 'form';

@Component({
  selector: 'bea-achats-paiements',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MatIconModule, AchatsPaiementApercuComponent],
  templateUrl: './achats-paiements.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsPaiementsComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(() => this.mode() === 'form' && this.form.dirty && !this.saving(), () => this.form);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<PaiementRow[]>([]);
  readonly current = signal<PaiementRow | null>(null);
  readonly factures = signal<FactureOpt[]>([]);
  readonly erreur = feedbackSignal('error', '');
  readonly msg = feedbackSignal('success', '');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly q = signal('');
  readonly apercuId = signal<string | null>(null);
  readonly filters = this.fb.nonNullable.group({ q: '' });
  readonly form = this.fb.nonNullable.group({
    facture_id: ['', Validators.required],
    montant: [0, [Validators.required, Validators.min(0.01)]],
    date_echeance: [''],
    date_paiement: [''],
    mode_paiement: [''],
    mode_paiement_autre: [''],
    reference_paiement: [''],
    observation: [''],
  });

  readonly autre = MOYEN_AUTRE;
  /** Moyen de paiement désigné dans le BC de la facture choisie. */
  readonly moyenBc = signal<{ bon: string; moyen: string; ref: string } | null>(null);
  readonly moyenChoisi = signal('');

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    return this.rows().filter((r) => {
      if (!term) return true;
      return (
        r.reference.toLowerCase().includes(term) ||
        r.facture_id.toLowerCase().includes(term) ||
        (r.reference_paiement ?? '').toLowerCase().includes(term)
      );
    });
  });

  readonly actifs = computed(() => this.rows().filter((r) => r.statut !== 'ANNULE'));
  readonly total = computed(() => this.actifs().reduce((n, r) => n + Number(r.montant || 0), 0));
  readonly pending = computed(() => this.actifs().filter((r) => r.statut === 'A_PAYER').length);
  /** Un paiement effectué ou annulé est figé : on n'annule que par motif tracé. */
  readonly canEditForm = computed(() => {
    const c = this.current();
    return !c || c.statut === 'A_PAYER' || (modeTestAchats() && c.statut !== 'ANNULE');
  });
  readonly modeTest = modeTestAchats;
  private readonly reappliquerVerrou = effect(() => {
    if (!this.current()) return;
    const editable = this.canEditForm();
    untracked(() => {
      if (!editable) {
        this.form.disable({ emitEvent: false });
        return;
      }
      this.form.enable({ emitEvent: false });
      this.form.controls.facture_id.disable({ emitEvent: false });
    });
  });
  readonly factureChoisie = signal<FactureOpt | null>(null);
  readonly facturesPayables = computed(() => {
    const courante = this.current()?.facture_id;
    return this.factures().filter((f) => facturePayable(f.statut) || f.id === courante);
  });

  ngOnInit(): void {
    chargerModeTest(this.api);
    const factureParam = this.route.snapshot.queryParamMap.get('facture_id');
    this.api.get<FactureOpt[]>('/mg/achats/factures').subscribe({
      next: (r) => {
        this.factures.set(r);
        if (factureParam && !this.id()) this.form.controls.facture_id.setValue(factureParam);
      },
    });
    this.form.controls.mode_paiement.valueChanges.subscribe((v) => this.moyenChoisi.set(v));
    this.form.controls.facture_id.valueChanges.subscribe((fid) => {
      const f = this.facturesPayables().find((x) => x.id === fid) ?? null;
      this.factureChoisie.set(f);
      this.chargerMoyenBc(f, !this.id());
      if (this.id() || !f) return;
      this.form.patchValue(
        { montant: Number(f.reste_a_payer ?? f.montant_ttc), date_echeance: f.date_echeance ?? '' },
        { emitEvent: false },
      );
    });
    const param = this.route.snapshot.paramMap.get('id');
    if (this.router.url.split('?')[0].endsWith('/nouveau') || param) {
      this.mode.set('form');
      if (param) {
        this.id.set(param);
        this.loadOne(param);
      }
    } else {
      this.loadList();
    }
  }

  factureLabel(f: FactureOpt): string {
    const reste = formatMontant(f.reste_a_payer ?? f.montant_ttc, 'MRU');
    return `${f.reference} — reste ${reste} (${FACTURE_STATUT_LABELS[f.statut] ?? f.statut})`;
  }

  statutLabel(s: string): string {
    return PAIEMENT_STATUT_LABELS[s] ?? s;
  }

  /** Le moyen désigné dans le BC est repris d'office à la création ; il reste modifiable. */
  private chargerMoyenBc(f: FactureOpt | null, appliquer: boolean): void {
    this.moyenBc.set(null);
    if (!f?.bon_id) return;
    this.api
      .get<{ reference: string; moyen_paiement: string | null; ref_paiement: string | null }>(`/mg/achats/bons/${f.bon_id}`)
      .subscribe({
        next: (b) => {
          if (this.form.controls.facture_id.value !== f.id) return;
          const moyen = (b.moyen_paiement ?? '').trim();
          this.moyenBc.set(moyen ? { bon: b.reference, moyen, ref: (b.ref_paiement ?? '').trim() } : null);
          if (appliquer && moyen) this.appliquerMoyen(moyen, (b.ref_paiement ?? '').trim());
        },
      });
  }

  private appliquerMoyen(valeur: string | null, ref: string | null): void {
    const { liste, autre } = decomposerMoyen(valeur);
    this.form.patchValue({ mode_paiement: liste, mode_paiement_autre: autre, reference_paiement: (ref ?? '').slice(0, 120) });
  }

  /** Changement manuel : la référence du BC (RIB / téléphone) ne vaut que pour le moyen du BC. */
  onMoyenChange(): void {
    const bc = this.moyenBc();
    const v = this.form.controls.mode_paiement.value;
    const memeQueBc = !!bc && decomposerMoyen(bc.moyen).liste === v && v !== MOYEN_AUTRE;
    this.form.patchValue({ reference_paiement: memeQueBc ? bc!.ref.slice(0, 120) : '', mode_paiement_autre: '' });
  }

  private resoudreMoyen(): string | null {
    const v = this.form.controls.mode_paiement.value;
    if (v === MOYEN_AUTRE) return this.form.controls.mode_paiement_autre.value.trim() || null;
    return v || null;
  }

  loadList(): void {
    this.api.get<PaiementRow[]>('/mg/achats/paiements').subscribe({
      next: (r) => this.rows.set(r),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Paiements indisponibles.')),
    });
  }

  loadOne(id: string): void {
    this.api.get<PaiementRow>(`/mg/achats/paiements/${id}`).subscribe({
      next: (p) => {
        this.current.set(p);
        this.form.patchValue({
          facture_id: p.facture_id,
          montant: Number(p.montant),
          date_echeance: p.date_echeance ?? '',
          date_paiement: p.date_paiement ?? '',
          mode_paiement: decomposerMoyen(p.mode_paiement).liste,
          mode_paiement_autre: decomposerMoyen(p.mode_paiement).autre,
          reference_paiement: p.reference_paiement ?? '',
          observation: p.observation ?? '',
        });
        if (!this.canEditForm()) this.form.disable({ emitEvent: false });
        else {
          this.form.enable({ emitEvent: false });
          this.form.controls.facture_id.disable({ emitEvent: false });
        }
        this.form.markAsPristine();
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Paiement introuvable.')),
    });
  }

  search(): void {
    this.q.set(this.filters.controls.q.value.trim());
  }

  open(r: PaiementRow): void {
    this.apercuId.set(r.id);
  }

  supprimer(row: PaiementRow): void {
    this.feedback
      .run(() => this.api.delete(`/mg/achats/paiements/${row.id}`), {
        confirm: {
          action: 'suppression',
          message: `Mode test : le paiement ${row.reference} sera supprimé et le reste à payer de la facture recalculé.`,
        },
        loading: 'Suppression…',
        errorTitle: 'Suppression refusée',
        success: { title: 'Paiement supprimé', details: [{ label: 'Référence', value: row.reference }] },
        busy: this.saving,
      })
      .subscribe({
        next: () => {
          if (this.mode() === 'form') void this.router.navigateByUrl('/achats-appro/paiements');
          else this.loadList();
        },
      });
  }

  annuler(row: PaiementRow): void {
    this.feedback
      .runWithReason((motif) => this.api.post<PaiementRow>(`/mg/achats/paiements/${row.id}/annuler`, { motif }), {
        reason: {
          title: `Annuler le paiement ${row.reference}`,
          message: 'Le paiement reste consultable ; le reste à payer de la facture est recalculé.',
          reasonLabel: 'Motif d’annulation',
          confirmLabel: 'Annuler le paiement',
          tone: 'danger',
          icon: 'block',
        },
        loading: 'Annulation…',
        errorTitle: 'Annulation refusée',
        success: { title: 'Paiement annulé', details: [{ label: 'Référence', value: row.reference }] },
        busy: this.saving,
      })
      .subscribe({
        next: (p) => {
          if (this.mode() === 'form') this.loadOne(p.id);
          else this.loadList();
        },
      });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.erreur.set('Sélectionnez une facture et un montant.');
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    const v = this.form.getRawValue();
    const body = {
      facture_id: v.facture_id,
      montant: Number(v.montant),
      date_echeance: v.date_echeance || null,
      date_paiement: v.date_paiement || null,
      mode_paiement: this.resoudreMoyen(),
      reference_paiement: v.reference_paiement.trim() || null,
      observation: v.observation.trim() || null,
    };
    const req = this.id()
      ? this.api.patch<PaiementRow>(`/mg/achats/paiements/${this.id()}`, {
          montant: body.montant,
          date_echeance: body.date_echeance,
          date_paiement: body.date_paiement,
          mode_paiement: body.mode_paiement,
          reference_paiement: body.reference_paiement,
          observation: body.observation,
        })
      : this.api.post<PaiementRow>('/mg/achats/paiements', body);
    req.subscribe({
      next: (p) => {
        this.saving.set(false);
        this.msg.set(this.id() ? 'Suivi mis à jour.' : 'Suivi de paiement créé.');
        this.form.markAsPristine();
        if (this.id()) this.loadOne(p.id);
        else void this.router.navigateByUrl(`/achats-appro/paiements/${p.id}`);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.'));
      },
    });
  }

  markPaid(): void {
    const today = new Date().toISOString().slice(0, 10);
    this.form.patchValue({ date_paiement: today });
    this.save();
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
