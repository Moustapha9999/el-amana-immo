import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { MontantPipe } from '../shared/montant.pipe';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { SupplierSelectComponent } from './supplier-select.component';

interface ConsultationOpt {
  id: string;
  reference: string;
  objet: string;
  statut: string;
}

export interface DevisLigne {
  id?: string;
  designation: string;
  quantite: number;
  prix_unitaire: number;
  remise_pct?: number;
  taux_tva?: number;
  total_ht?: number;
}

export interface DevisRow {
  id: string;
  reference: string;
  fournisseur_id: string;
  consultation_id: string | null;
  date_devis: string;
  date_validite: string | null;
  montant_ht: number;
  montant_tva: number;
  montant_ttc: number;
  devise: string;
  conditions: string | null;
  delai_livraison: string | null;
  conditions_paiement: string | null;
  statut: string;
  observation: string | null;
  lignes?: DevisLigne[];
}

type Mode = 'list' | 'form';

const EDITABLE_STATUTS = ['RECU', 'EN_COURS', 'ANALYSE'];

@Component({
  selector: 'bea-achats-devis',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MontantPipe,
    MatIconModule,
    MgGedPanelComponent,
    SupplierSelectComponent,
  ],
  templateUrl: './achats-devis.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsDevisComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<DevisRow[]>([]);
  readonly current = signal<DevisRow | null>(null);
  readonly consultations = signal<ConsultationOpt[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly q = signal('');
  readonly statutFilter = signal('');
  readonly confirm = signal<{ row: DevisRow; action: 'desactiver' | 'supprimer' } | null>(null);

  readonly filters = this.fb.nonNullable.group({ q: '', statut: '' });
  readonly form = this.fb.nonNullable.group({
    fournisseur_id: ['', Validators.required],
    consultation_id: [''],
    date_devis: [new Date().toISOString().slice(0, 10), Validators.required],
    date_validite: [''],
    devise: ['MRU'],
    conditions: [''],
    delai_livraison: [''],
    conditions_paiement: [''],
    observation: [''],
    lignes: this.fb.array([this.newLigne()]),
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    const statut = this.statutFilter();
    return this.rows().filter((r) => {
      if (statut && r.statut !== statut) return false;
      if (!term) return true;
      return r.reference.toLowerCase().includes(term);
    });
  });

  readonly totalTtc = computed(() => this.rows().reduce((n, r) => n + Number(r.montant_ttc || 0), 0));
  readonly active = computed(
    () => this.rows().filter((r) => !['RETENU', 'REJETE', 'ANNULE'].includes(r.statut)).length,
  );

  readonly canEditForm = computed(() => {
    if (!this.id()) return true;
    const s = this.current()?.statut;
    return !!s && EDITABLE_STATUTS.includes(s);
  });

  readonly canStatutActions = computed(() => {
    const s = this.current()?.statut;
    return !!s && EDITABLE_STATUTS.includes(s);
  });

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    this.api.get<ConsultationOpt[]>('/mg/achats/consultations').subscribe({
      next: (rows) =>
        this.consultations.set(rows.filter((c) => !['ANNULEE'].includes(c.statut))),
    });

    const url = this.router.url;
    const param = this.route.snapshot.paramMap.get('id');
    const consultationPrefill = this.route.snapshot.queryParamMap.get('consultation_id');

    if (url.endsWith('/nouveau') || param) {
      this.mode.set('form');
      if (param) {
        this.id.set(param);
        this.loadOne(param);
      } else if (consultationPrefill) {
        this.form.patchValue({ consultation_id: consultationPrefill });
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
      remise_pct: [0],
      taux_tva: [0],
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
    this.api.get<DevisRow[]>('/mg/achats/devis').subscribe({
      next: (rows) => this.rows.set(rows),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Devis indisponibles.')),
    });
  }

  loadOne(id: string): void {
    this.api.get<DevisRow>(`/mg/achats/devis/${id}`).subscribe({
      next: (d) => {
        this.current.set(d);
        this.form.patchValue({
          fournisseur_id: d.fournisseur_id,
          consultation_id: d.consultation_id ?? '',
          date_devis: d.date_devis,
          date_validite: d.date_validite ?? '',
          devise: d.devise || 'MRU',
          conditions: d.conditions ?? '',
          delai_livraison: d.delai_livraison ?? '',
          conditions_paiement: d.conditions_paiement ?? '',
          observation: d.observation ?? '',
        });
        this.lignes.clear();
        const lignes = d.lignes?.length
          ? d.lignes
          : [{ designation: '', quantite: 1, prix_unitaire: 0, remise_pct: 0, taux_tva: 0 }];
        for (const l of lignes) {
          this.lignes.push(
            this.fb.nonNullable.group({
              designation: [l.designation, Validators.required],
              quantite: [Number(l.quantite), Validators.required],
              prix_unitaire: [Number(l.prix_unitaire || 0), Validators.required],
              remise_pct: [Number(l.remise_pct || 0)],
              taux_tva: [Number(l.taux_tva || 0)],
            }),
          );
        }
        if (!this.canEditForm()) this.form.disable({ emitEvent: false });
        else this.form.enable({ emitEvent: false });
        if (this.id()) {
          this.form.controls.consultation_id.disable({ emitEvent: false });
          this.form.controls.fournisseur_id.disable({ emitEvent: false });
        }
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Devis introuvable.')),
    });
  }

  onSearch(): void {
    const v = this.filters.getRawValue();
    this.q.set(v.q);
    this.statutFilter.set(v.statut);
  }

  canEdit(r: DevisRow): boolean {
    return EDITABLE_STATUTS.includes(r.statut);
  }

  canDesactiver(r: DevisRow): boolean {
    return r.statut !== 'ANNULE';
  }

  edit(r: DevisRow): void {
    void this.router.navigateByUrl(`/achats-appro/devis/${r.id}`);
  }

  askAction(row: DevisRow, action: 'desactiver' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/devis/${c.row.id}`)
        : this.api.post(`/mg/achats/devis/${c.row.id}/desactiver`, {});
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? `Devis ${c.row.reference} supprimé.`
            : `Devis ${c.row.reference} désactivé.`,
        );
        this.loadList();
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
      this.erreur.set('Complétez les champs obligatoires (fournisseur, lignes).');
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    const v = this.form.getRawValue();
    const lignesBody = v.lignes.map((l) => ({
      designation: l.designation.trim(),
      quantite: Number(l.quantite),
      prix_unitaire: Number(l.prix_unitaire || 0),
      remise_pct: Number(l.remise_pct || 0),
      taux_tva: Number(l.taux_tva || 0),
    }));

    if (this.id()) {
      const body = {
        date_devis: v.date_devis,
        date_validite: v.date_validite || null,
        devise: v.devise || 'MRU',
        conditions: v.conditions.trim() || null,
        delai_livraison: v.delai_livraison.trim() || null,
        conditions_paiement: v.conditions_paiement.trim() || null,
        observation: v.observation.trim() || null,
        lignes: lignesBody,
      };
      this.api.patch<DevisRow>(`/mg/achats/devis/${this.id()}`, body).subscribe({
        next: (d) => {
          this.saving.set(false);
          this.msg.set('Devis mis à jour.');
          void this.router.navigateByUrl(`/achats-appro/devis/${d.id}`);
        },
        error: (err) => {
          this.saving.set(false);
          this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.'));
        },
      });
      return;
    }

    const body = {
      fournisseur_id: v.fournisseur_id,
      consultation_id: v.consultation_id || null,
      date_devis: v.date_devis,
      date_validite: v.date_validite || null,
      devise: v.devise || 'MRU',
      conditions: v.conditions.trim() || null,
      delai_livraison: v.delai_livraison.trim() || null,
      conditions_paiement: v.conditions_paiement.trim() || null,
      observation: v.observation.trim() || null,
      lignes: lignesBody,
    };
    this.api.post<DevisRow>('/mg/achats/devis', body).subscribe({
      next: (d) => {
        this.saving.set(false);
        this.msg.set('Devis créé.');
        void this.router.navigateByUrl(`/achats-appro/devis/${d.id}`);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.'));
      },
    });
  }

  patchStatut(statut: 'RETENU' | 'REJETE'): void {
    const id = this.id();
    if (!id) return;
    this.erreur.set('');
    this.api.patch<DevisRow>(`/mg/achats/devis/${id}`, { statut }).subscribe({
      next: (d) => {
        this.current.set(d);
        this.msg.set(`Statut → ${d.statut}`);
        this.form.disable({ emitEvent: false });
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Mise à jour du statut refusée.')),
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
