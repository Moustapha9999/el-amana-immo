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

interface Agence {
  id: string;
  libelle: string;
}

interface BonOpt {
  id: string;
  reference: string;
  statut: string;
}

interface BcLigne {
  id: string;
  description: string;
  quantite: number;
  quantite_recue: number;
  uom: string;
}

interface BonDetail {
  id: string;
  reference: string;
  statut: string;
  lignes: BcLigne[];
}

export interface ReceptionLigne {
  id: string;
  bc_ligne_id: string;
  quantite_recue: number;
}

export interface ReceptionRow {
  id: string;
  reference: string;
  bon_id: string;
  bon_reference?: string | null;
  date_reception: string;
  agence_id?: string | null;
  statut: string;
  observation?: string | null;
  lignes?: ReceptionLigne[];
}

type Mode = 'list' | 'form';

@Component({
  selector: 'bea-achats-receptions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  templateUrl: './achats-receptions.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsReceptionsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<ReceptionRow[]>([]);
  readonly current = signal<ReceptionRow | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly bons = signal<BonOpt[]>([]);
  readonly bonDetail = signal<BonDetail | null>(null);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly q = signal('');
  readonly confirm = signal<{ row: ReceptionRow; action: 'desactiver' | 'supprimer' } | null>(null);

  readonly filters = this.fb.nonNullable.group({ q: '' });
  readonly form = this.fb.nonNullable.group({
    bon_id: ['', Validators.required],
    date_reception: [new Date().toISOString().slice(0, 10), Validators.required],
    agence_id: [''],
    observation: [''],
    lignes: this.fb.array([] as ReturnType<typeof this.newLigne>[]),
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    return this.rows().filter((r) => {
      if (!term) return true;
      return (
        r.reference.toLowerCase().includes(term) ||
        (r.bon_reference ?? r.bon_id).toLowerCase().includes(term)
      );
    });
  });

  readonly partial = computed(() => this.rows().filter((r) => r.statut === 'PARTIEL').length);
  readonly isFiche = computed(() => !!this.id());

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/achats/agences').subscribe({
      next: (r) => this.agences.set(r),
    });
    this.api.get<{ items: BonOpt[] }>('/mg/achats/bons', { page: '1', size: '100' }).subscribe({
      next: (r) =>
        this.bons.set(
          r.items.filter((b) => ['ENVOYE', 'PARTIEL', 'VALIDE', 'RECU'].includes(b.statut)),
        ),
    });
    this.form.controls.bon_id.valueChanges.subscribe((bonId) => {
      if (this.isFiche()) return;
      if (bonId) this.loadBonLines(bonId);
      else {
        this.bonDetail.set(null);
        this.lignes.clear();
      }
    });
    const param = this.route.snapshot.paramMap.get('id');
    if (this.router.url.endsWith('/nouvelle') || param) {
      this.mode.set('form');
      if (param) {
        this.id.set(param);
        this.loadOne(param);
        this.form.disable({ emitEvent: false });
      }
    } else {
      this.loadList();
    }
  }

  newLigne(bcLigneId: string, designation: string, reste: number) {
    return this.fb.nonNullable.group({
      bc_ligne_id: [bcLigneId],
      designation: [{ value: designation, disabled: true }],
      reste: [{ value: reste, disabled: true }],
      quantite_recue: [reste > 0 ? reste : 0, [Validators.required, Validators.min(0.001)]],
    });
  }

  loadBonLines(bonId: string): void {
    this.api.get<BonDetail>(`/mg/achats/bons/${bonId}`).subscribe({
      next: (bon) => {
        this.bonDetail.set(bon);
        this.lignes.clear();
        for (const l of bon.lignes ?? []) {
          const reste = Math.max(0, Number(l.quantite) - Number(l.quantite_recue || 0));
          if (reste <= 0) continue;
          this.lignes.push(this.newLigne(l.id, l.description, reste));
        }
        if (!this.lignes.length) {
          this.erreur.set('Aucune quantité restante à réceptionner sur ce BC.');
        } else {
          this.erreur.set('');
        }
      },
      error: () => this.erreur.set('Impossible de charger les lignes du BC.'),
    });
  }

  loadList(): void {
    this.api.get<ReceptionRow[]>('/mg/achats/receptions').subscribe({
      next: (r) => this.rows.set(r),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Réceptions indisponibles.')),
    });
  }

  loadOne(id: string): void {
    this.api.get<ReceptionRow>(`/mg/achats/receptions/${id}`).subscribe({
      next: (rec) => {
        this.current.set(rec);
        this.form.patchValue({
          bon_id: rec.bon_id,
          date_reception: rec.date_reception,
          agence_id: rec.agence_id ?? '',
          observation: rec.observation ?? '',
        });
        this.lignes.clear();
        for (const l of rec.lignes ?? []) {
          this.lignes.push(
            this.fb.nonNullable.group({
              bc_ligne_id: [l.bc_ligne_id],
              designation: [{ value: '—', disabled: true }],
              reste: [{ value: l.quantite_recue, disabled: true }],
              quantite_recue: [{ value: l.quantite_recue, disabled: true }],
            }),
          );
        }
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Réception introuvable.')),
    });
  }

  search(): void {
    this.q.set(this.filters.controls.q.value.trim());
  }

  open(r: ReceptionRow): void {
    void this.router.navigateByUrl(`/achats-appro/receptions/${r.id}`);
  }

  askAction(row: ReceptionRow, action: 'desactiver' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/receptions/${c.row.id}`)
        : this.api.post(`/mg/achats/receptions/${c.row.id}/desactiver`, {});
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? `Réception ${c.row.reference} supprimée.`
            : `Réception ${c.row.reference} désactivée.`,
        );
        if (this.mode() === 'form') void this.router.navigateByUrl('/achats-appro/receptions');
        else this.loadList();
      },
      error: (err) => {
        this.confirm.set(null);
        this.erreur.set(this.apiDetail(err, 'Action refusée.'));
      },
    });
  }

  save(): void {
    this.erreur.set('');
    const v = this.form.getRawValue();
    if (this.id()) {
      if (!v.date_reception) {
        this.form.markAllAsTouched();
        this.erreur.set('Date de réception obligatoire.');
        return;
      }
      this.saving.set(true);
      this.api
        .patch<ReceptionRow>(`/mg/achats/receptions/${this.id()}`, {
          date_reception: v.date_reception,
          agence_id: v.agence_id || null,
          observation: v.observation.trim() || null,
        })
        .subscribe({
          next: (rec) => {
            this.saving.set(false);
            this.current.set(rec);
            this.msg.set('Réception mise à jour.');
          },
          error: (err) => {
            this.saving.set(false);
            this.erreur.set(this.apiDetail(err, 'Mise à jour refusée.'));
          },
        });
      return;
    }
    if (this.form.invalid || !this.lignes.length) {
      this.form.markAllAsTouched();
      this.erreur.set('Sélectionnez un BC et saisissez au moins une quantité reçue.');
      return;
    }
    this.saving.set(true);
    const lignesPayload = this.lignes.controls
      .map((ctrl) => {
        const g = ctrl.getRawValue() as {
          bc_ligne_id: string;
          quantite_recue: number;
        };
        return {
          bc_ligne_id: g.bc_ligne_id,
          quantite_recue: Number(g.quantite_recue),
        };
      })
      .filter((l) => l.quantite_recue > 0);
    if (!lignesPayload.length) {
      this.saving.set(false);
      this.erreur.set('Indiquez une quantité reçue > 0 pour au moins une ligne.');
      return;
    }
    const body = {
      bon_id: v.bon_id,
      date_reception: v.date_reception,
      agence_id: v.agence_id || null,
      observation: v.observation.trim() || null,
      lignes: lignesPayload,
    };
    this.api.post<ReceptionRow>('/mg/achats/receptions', body).subscribe({
      next: (rec) => {
        this.saving.set(false);
        this.msg.set('Réception enregistrée.');
        void this.router.navigateByUrl(`/achats-appro/receptions/${rec.id}`);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(this.apiDetail(err, 'Réception refusée.'));
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
