import { DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { SupplierSelectComponent } from './supplier-select.component';

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
  total_ht?: number;
}

export interface FactureRow {
  id: string;
  reference: string;
  numero_fournisseur?: string | null;
  fournisseur_id: string;
  bon_id: string;
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
    DecimalPipe,
    MatIconModule,
    MgGedPanelComponent,
    SupplierSelectComponent,
  ],
  templateUrl: './achats-factures.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsFacturesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<FactureRow[]>([]);
  readonly current = signal<FactureRow | null>(null);
  readonly bons = signal<BonOpt[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly matching = signal(false);
  readonly matchResult = signal<ThreeWayMatch | null>(null);
  readonly q = signal('');
  readonly confirm = signal<{ row: FactureRow; action: 'desactiver' | 'supprimer' } | null>(null);

  readonly filters = this.fb.nonNullable.group({ q: '' });
  readonly form = this.fb.nonNullable.group({
    fournisseur_id: ['', Validators.required],
    bon_id: ['', Validators.required],
    numero_fournisseur: [''],
    date_facture: [new Date().toISOString().slice(0, 10), Validators.required],
    date_echeance: [''],
    observation: [''],
    lignes: this.fb.array([this.newLigne()]),
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
  readonly canEditForm = computed(() => !this.id() || !['ANNULE', 'PAYEE'].includes(this.current()?.statut ?? ''));

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    this.api.get<{ items: BonOpt[] }>('/mg/achats/bons', { page: '1', size: '100' }).subscribe({
      next: (r) =>
        this.bons.set(r.items.filter((b) => !['BROUILLON', 'ANNULE', 'REJETEE'].includes(b.statut))),
    });
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

  newLigne() {
    return this.fb.nonNullable.group({
      designation: ['', Validators.required],
      quantite: [1, Validators.required],
      prix_unitaire: [0, Validators.required],
    });
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
        this.form.patchValue({
          fournisseur_id: f.fournisseur_id,
          bon_id: f.bon_id,
          numero_fournisseur: f.numero_fournisseur ?? '',
          date_facture: f.date_facture,
          date_echeance: f.date_echeance ?? '',
          observation: f.observation ?? '',
        });
        this.lignes.clear();
        const lignes = f.lignes?.length
          ? f.lignes
          : [{ designation: '', quantite: 1, prix_unitaire: 0 }];
        for (const l of lignes) {
          this.lignes.push(
            this.fb.nonNullable.group({
              designation: [l.designation, Validators.required],
              quantite: [Number(l.quantite), Validators.required],
              prix_unitaire: [Number(l.prix_unitaire), Validators.required],
            }),
          );
        }
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
    void this.router.navigateByUrl(`/achats-appro/factures/${r.id}`);
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
      lignes: v.lignes.map((l) => ({
        designation: l.designation.trim(),
        quantite: Number(l.quantite),
        prix_unitaire: Number(l.prix_unitaire),
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
