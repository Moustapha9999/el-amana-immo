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
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';
import { SupplierSelectComponent } from './supplier-select.component';

interface Agence {
  id: string;
  libelle: string;
}

interface DemandeOpt {
  id: string;
  reference: string;
  objet?: string;
  motif?: string | null;
  statut: string;
}

interface FrsInvite {
  id: string;
  code: string;
  raison_sociale: string;
  is_active?: boolean;
}

export interface ConsultationRow {
  id: string;
  reference: string;
  date_consultation: string;
  demande_id: string | null;
  demande_reference?: string | null;
  agence_id: string;
  objet: string;
  date_limite?: string | null;
  statut: string;
  observation?: string | null;
  fournisseur_ids: string[];
  fournisseurs?: FrsInvite[];
  nb_devis?: number;
  nb_fournisseurs?: number;
}

type Mode = 'list' | 'form';

@Component({
  selector: 'bea-achats-consultations',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, MgGedPanelComponent, SupplierSelectComponent],
  templateUrl: './achats-consultations.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsConsultationsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<ConsultationRow[]>([]);
  readonly current = signal<ConsultationRow | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly demandes = signal<DemandeOpt[]>([]);
  readonly invites = signal<FrsInvite[]>([]);
  readonly pickId = signal<string | null>(null);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly q = signal('');
  readonly statutFilter = signal('');
  readonly confirm = signal<{ row: ConsultationRow; action: 'annuler' | 'supprimer' } | null>(null);

  readonly filters = this.fb.nonNullable.group({ q: '', statut: '' });
  readonly form = this.fb.nonNullable.group({
    date_consultation: [new Date().toISOString().slice(0, 10), Validators.required],
    agence_id: ['', Validators.required],
    demande_id: [''],
    objet: ['', Validators.required],
    date_limite: [''],
    observation: [''],
    pick_fournisseur: [null as string | null],
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    const statut = this.statutFilter();
    return this.rows().filter((r) => {
      if (statut && r.statut !== statut) return false;
      if (!term) return true;
      return r.reference.toLowerCase().includes(term) || r.objet.toLowerCase().includes(term);
    });
  });

  readonly active = computed(
    () => this.rows().filter((r) => !['CLOTUREE', 'ANNULEE'].includes(r.statut)).length,
  );

  readonly nextActions = computed(() => {
    const s = this.current()?.statut;
    const map: Record<string, { action: string; label: string }[]> = {
      BROUILLON: [{ action: 'ouvrir', label: 'Ouvrir' }],
      OUVERTE: [{ action: 'cloturer', label: 'Clôturer' }],
    };
    return s ? map[s] ?? [] : [];
  });

  readonly canEditForm = computed(
    () => !this.id() || ['BROUILLON', 'OUVERTE'].includes(this.current()?.statut ?? 'BROUILLON'),
  );

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/achats/agences').subscribe({
      next: (r) => this.agences.set(r),
      error: () => this.erreur.set('Agences indisponibles.'),
    });
    this.api.get<DemandeOpt[]>('/mg/achats/demandes').subscribe({
      next: (r) =>
        this.demandes.set(
          r.filter((d) => !['ANNULEE', 'REJETEE', 'CLOTUREE'].includes(d.statut)),
        ),
    });
    this.form.controls.pick_fournisseur.valueChanges.subscribe((id) => {
      if (id) this.addInvite(id);
    });
    const url = this.router.url;
    const param = this.route.snapshot.paramMap.get('id');
    if (url.endsWith('/nouvelle') || param) {
      this.mode.set('form');
      if (param) {
        this.id.set(param);
        this.loadOne(param);
      }
    } else {
      this.loadList();
    }
  }

  loadList(): void {
    this.api.get<ConsultationRow[]>('/mg/achats/consultations').subscribe({
      next: (r) => this.rows.set(r),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Consultations indisponibles.')),
    });
  }

  loadOne(id: string): void {
    this.api.get<ConsultationRow>(`/mg/achats/consultations/${id}`).subscribe({
      next: (c) => {
        this.current.set(c);
        this.form.patchValue({
          date_consultation: c.date_consultation,
          agence_id: c.agence_id,
          demande_id: c.demande_id ?? '',
          objet: c.objet,
          date_limite: c.date_limite ?? '',
          observation: c.observation ?? '',
          pick_fournisseur: null,
        });
        this.invites.set(c.fournisseurs ?? []);
        if (!this.canEditForm()) this.form.disable({ emitEvent: false });
        else this.form.enable({ emitEvent: false });
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Consultation introuvable.')),
    });
  }

  addInvite(id: string): void {
    if (this.invites().some((f) => f.id === id)) {
      this.form.controls.pick_fournisseur.setValue(null, { emitEvent: false });
      return;
    }
    this.api
      .get<{ id: string; code: string; raison_sociale: string; is_active?: boolean }>(
        `/mg/achats/fournisseurs/${id}`,
      )
      .subscribe({
        next: (f) => {
          this.invites.update((list) => [
            ...list,
            { id: f.id, code: f.code, raison_sociale: f.raison_sociale, is_active: f.is_active },
          ]);
          this.form.controls.pick_fournisseur.setValue(null, { emitEvent: false });
        },
      });
  }

  removeInvite(id: string): void {
    this.invites.update((list) => list.filter((f) => f.id !== id));
  }

  search(): void {
    const v = this.filters.getRawValue();
    this.q.set(v.q);
    this.statutFilter.set(v.statut);
  }

  canEdit(r: ConsultationRow): boolean {
    return ['BROUILLON', 'OUVERTE'].includes(r.statut);
  }

  canCancel(r: ConsultationRow): boolean {
    return !['ANNULEE', 'CLOTUREE'].includes(r.statut);
  }

  edit(r: ConsultationRow): void {
    void this.router.navigateByUrl(`/achats-appro/consultations/${r.id}`);
  }

  askAction(row: ConsultationRow, action: 'annuler' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/consultations/${c.row.id}`)
        : this.api.post(`/mg/achats/consultations/${c.row.id}/transition`, { action: 'annuler' });
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? `Consultation ${c.row.reference} supprimée.`
            : `Consultation ${c.row.reference} annulée.`,
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
      this.erreur.set('Complétez les champs obligatoires (agence, objet).');
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    const v = this.form.getRawValue();
    const body = {
      date_consultation: v.date_consultation,
      agence_id: v.agence_id,
      demande_id: v.demande_id || null,
      objet: v.objet.trim(),
      date_limite: v.date_limite || null,
      observation: v.observation.trim() || null,
      fournisseur_ids: this.invites().map((f) => f.id),
    };
    const req = this.id()
      ? this.api.patch<ConsultationRow>(`/mg/achats/consultations/${this.id()}`, body)
      : this.api.post<ConsultationRow>('/mg/achats/consultations', body);
    req.subscribe({
      next: (c) => {
        this.saving.set(false);
        this.msg.set(this.id() ? 'Consultation mise à jour.' : 'Consultation créée.');
        void this.router.navigateByUrl(`/achats-appro/consultations/${c.id}`);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.'));
      },
    });
  }

  go(action: string): void {
    const id = this.id();
    if (!id) return;
    this.erreur.set('');
    this.api
      .post<ConsultationRow>(`/mg/achats/consultations/${id}/transition`, { action })
      .subscribe({
        next: (c) => {
          this.current.set(c);
          this.msg.set(`Transition effectuée → ${c.statut}`);
          this.loadOne(id);
        },
        error: (err) => this.erreur.set(this.apiDetail(err, 'Transition refusée.')),
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
