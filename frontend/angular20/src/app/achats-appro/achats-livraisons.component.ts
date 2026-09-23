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

interface Agence {
  id: string;
  libelle: string;
}

interface BonOpt {
  id: string;
  reference: string;
  statut: string;
  fournisseur_raison_sociale?: string | null;
}

export interface BlRow {
  id: string;
  reference: string;
  bon_id: string;
  bon_reference?: string | null;
  fournisseur_id: string;
  date_bl: string;
  date_livraison?: string | null;
  agence_id?: string | null;
  transporteur?: string | null;
  observation?: string | null;
  statut: string;
}

type Mode = 'list' | 'form';

@Component({
  selector: 'bea-achats-livraisons',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  templateUrl: './achats-livraisons.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsLivraisonsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<BlRow[]>([]);
  readonly current = signal<BlRow | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly bons = signal<BonOpt[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly q = signal('');
  readonly confirm = signal<{ row: BlRow; action: 'desactiver' | 'supprimer' } | null>(null);

  readonly filters = this.fb.nonNullable.group({ q: '' });
  readonly form = this.fb.nonNullable.group({
    bon_id: ['', Validators.required],
    date_bl: [new Date().toISOString().slice(0, 10), Validators.required],
    date_livraison: [''],
    agence_id: [''],
    transporteur: [''],
    observation: [''],
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    return this.rows().filter((r) => {
      if (!term) return true;
      return (
        r.reference.toLowerCase().includes(term) ||
        (r.bon_reference ?? r.bon_id).toLowerCase().includes(term) ||
        (r.transporteur ?? '').toLowerCase().includes(term)
      );
    });
  });

  readonly active = computed(
    () => this.rows().filter((r) => !['RECU', 'COMPLETE', 'CLOTURE', 'ANNULE'].includes(r.statut)).length,
  );

  readonly isFiche = computed(() => !!this.id());

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/achats/agences').subscribe({
      next: (r) => this.agences.set(r),
      error: () => this.erreur.set('Agences indisponibles.'),
    });
    this.api.get<{ items: BonOpt[] }>('/mg/achats/bons', { page: '1', size: '100' }).subscribe({
      next: (r) =>
        this.bons.set(
          r.items.filter((b) => !['BROUILLON', 'ANNULE', 'REJETEE'].includes(b.statut)),
        ),
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

  loadList(): void {
    this.api.get<BlRow[]>('/mg/achats/livraisons').subscribe({
      next: (r) => this.rows.set(r),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Livraisons indisponibles.')),
    });
  }

  loadOne(id: string): void {
    this.api.get<BlRow>(`/mg/achats/livraisons/${id}`).subscribe({
      next: (bl) => {
        this.current.set(bl);
        this.form.patchValue({
          bon_id: bl.bon_id,
          date_bl: bl.date_bl,
          date_livraison: bl.date_livraison ?? '',
          agence_id: bl.agence_id ?? '',
          transporteur: bl.transporteur ?? '',
          observation: bl.observation ?? '',
        });
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'BL introuvable.')),
    });
  }

  search(): void {
    this.q.set(this.filters.controls.q.value.trim());
  }

  open(r: BlRow): void {
    void this.router.navigateByUrl(`/achats-appro/livraisons/${r.id}`);
  }

  askAction(row: BlRow, action: 'desactiver' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/livraisons/${c.row.id}`)
        : this.api.post(`/mg/achats/livraisons/${c.row.id}/desactiver`, {});
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(c.action === 'supprimer' ? `BL ${c.row.reference} supprimé.` : `BL ${c.row.reference} désactivé.`);
        if (this.mode() === 'form') void this.router.navigateByUrl('/achats-appro/livraisons');
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
      this.erreur.set('Sélectionnez un bon de commande et une date BL.');
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    const v = this.form.getRawValue();
    const body = {
      bon_id: v.bon_id,
      date_bl: v.date_bl,
      date_livraison: v.date_livraison || null,
      agence_id: v.agence_id || null,
      transporteur: v.transporteur.trim() || null,
      observation: v.observation.trim() || null,
    };
    this.api.post<BlRow>('/mg/achats/livraisons', body).subscribe({
      next: (bl) => {
        this.saving.set(false);
        this.msg.set('Bon de livraison créé.');
        void this.router.navigateByUrl(`/achats-appro/livraisons/${bl.id}`);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.'));
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
