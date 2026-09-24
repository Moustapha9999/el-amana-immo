import { MontantPipe } from '../shared/montant.pipe';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

interface FactureOpt {
  id: string;
  reference: string;
  montant_ttc: number;
  statut: string;
  date_echeance?: string | null;
}

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
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MatIconModule],
  templateUrl: './achats-paiements.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsPaiementsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<PaiementRow[]>([]);
  readonly current = signal<PaiementRow | null>(null);
  readonly factures = signal<FactureOpt[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly q = signal('');
  readonly confirm = signal<{ row: PaiementRow; action: 'desactiver' | 'supprimer' } | null>(null);

  readonly filters = this.fb.nonNullable.group({ q: '' });
  readonly form = this.fb.nonNullable.group({
    facture_id: ['', Validators.required],
    montant: [0, [Validators.required, Validators.min(0.01)]],
    date_echeance: [''],
    date_paiement: [''],
    mode_paiement: [''],
    reference_paiement: [''],
    observation: [''],
  });

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

  readonly total = computed(() => this.rows().reduce((n, r) => n + Number(r.montant || 0), 0));
  readonly pending = computed(() => this.rows().filter((r) => r.statut !== 'PAYE').length);
  readonly canEditForm = computed(() => !this.id() || this.current()?.statut !== 'ANNULE');

  ngOnInit(): void {
    this.api.get<FactureOpt[]>('/mg/achats/factures').subscribe({
      next: (r) => this.factures.set(r.filter((f) => !['ANNULE'].includes(f.statut))),
    });
    this.form.controls.facture_id.valueChanges.subscribe((fid) => {
      if (this.id()) return;
      const f = this.factures().find((x) => x.id === fid);
      if (f) {
        this.form.patchValue(
          {
            montant: Number(f.montant_ttc),
            date_echeance: f.date_echeance ?? '',
          },
          { emitEvent: false },
        );
      }
    });
    const param = this.route.snapshot.paramMap.get('id');
    if (this.router.url.endsWith('/nouveau') || param) {
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
    return `${f.reference} — ${f.montant_ttc} MRU (${f.statut})`;
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
          mode_paiement: p.mode_paiement ?? '',
          reference_paiement: p.reference_paiement ?? '',
          observation: p.observation ?? '',
        });
        if (!this.canEditForm()) this.form.disable({ emitEvent: false });
        else {
          this.form.enable({ emitEvent: false });
          this.form.controls.facture_id.disable({ emitEvent: false });
        }
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Paiement introuvable.')),
    });
  }

  search(): void {
    this.q.set(this.filters.controls.q.value.trim());
  }

  open(r: PaiementRow): void {
    void this.router.navigateByUrl(`/achats-appro/paiements/${r.id}`);
  }

  askAction(row: PaiementRow, action: 'desactiver' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/paiements/${c.row.id}`)
        : this.api.post(`/mg/achats/paiements/${c.row.id}/desactiver`, {});
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? `Paiement ${c.row.reference} supprimé.`
            : `Paiement ${c.row.reference} désactivé.`,
        );
        if (this.mode() === 'form') void this.router.navigateByUrl('/achats-appro/paiements');
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
      mode_paiement: v.mode_paiement.trim() || null,
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
          statut: body.date_paiement ? 'PAYE' : undefined,
        })
      : this.api.post<PaiementRow>('/mg/achats/paiements', body);
    req.subscribe({
      next: (p) => {
        this.saving.set(false);
        this.msg.set(this.id() ? 'Suivi mis à jour.' : 'Suivi de paiement créé.');
        void this.router.navigateByUrl(`/achats-appro/paiements/${p.id}`);
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
