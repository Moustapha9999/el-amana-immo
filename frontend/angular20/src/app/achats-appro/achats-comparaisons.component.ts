import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { MontantPipe } from '../shared/montant.pipe';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { DevisRow } from './achats-devis.component';

interface ConsultationOpt {
  id: string;
  reference: string;
  objet: string;
  statut: string;
  demande_id?: string | null;
}

export interface ComparaisonRow {
  id: string;
  reference: string;
  consultation_id: string;
  demande_id: string | null;
  statut: string;
  fournisseur_retenu_id: string | null;
  motif_choix: string | null;
  snapshot_json: string | null;
  observation: string | null;
}

type Mode = 'list' | 'create' | 'fiche';

@Component({
  selector: 'bea-achats-comparaisons',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MatIconModule],
  templateUrl: './achats-comparaisons.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsComparaisonsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<ComparaisonRow[]>([]);
  readonly current = signal<ComparaisonRow | null>(null);
  readonly consultations = signal<ConsultationOpt[]>([]);
  readonly devis = signal<DevisRow[]>([]);
  readonly fournisseurLabels = signal<Record<string, string>>({});
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly validating = signal(false);
  readonly q = signal('');
  readonly confirm = signal<{ row: ComparaisonRow; action: 'desactiver' | 'supprimer' } | null>(
    null,
  );

  readonly filters = this.fb.nonNullable.group({ q: '' });
  readonly createForm = this.fb.nonNullable.group({
    consultation_id: ['', Validators.required],
    observation: [''],
  });
  readonly validateForm = this.fb.nonNullable.group({
    fournisseur_retenu_id: ['', Validators.required],
    motif_choix: [''],
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    return this.rows().filter((r) => {
      if (!term) return true;
      return (
        r.reference.toLowerCase().includes(term) ||
        (r.motif_choix ?? '').toLowerCase().includes(term)
      );
    });
  });

  readonly active = computed(
    () => this.rows().filter((r) => !['VALIDEE', 'CLOTUREE', 'ANNULEE'].includes(r.statut)).length,
  );

  readonly canValidate = computed(() => {
    const s = this.current()?.statut;
    return !!s && ['BROUILLON', 'EN_COURS'].includes(s);
  });

  readonly consultationLabel = computed(() => {
    const cid = this.current()?.consultation_id;
    if (!cid) return '';
    const c = this.consultations().find((x) => x.id === cid);
    return c ? `${c.reference} — ${c.objet}` : cid;
  });

  ngOnInit(): void {
    this.api.get<ConsultationOpt[]>('/mg/achats/consultations').subscribe({
      next: (rows) =>
        this.consultations.set(rows.filter((c) => !['ANNULEE'].includes(c.statut))),
    });

    const url = this.router.url;
    const param = this.route.snapshot.paramMap.get('id');
    if (url.endsWith('/nouvelle')) {
      this.mode.set('create');
    } else if (param) {
      this.id.set(param);
      this.mode.set('fiche');
      this.loadOne(param);
    } else {
      this.loadList();
    }
  }

  loadList(): void {
    this.api.get<ComparaisonRow[]>('/mg/achats/comparaisons').subscribe({
      next: (rows) => this.rows.set(rows),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Comparaisons indisponibles.')),
    });
  }

  loadOne(id: string): void {
    this.api.get<ComparaisonRow>(`/mg/achats/comparaisons/${id}`).subscribe({
      next: (c) => {
        this.current.set(c);
        if (c.fournisseur_retenu_id) {
          this.validateForm.patchValue({
            fournisseur_retenu_id: c.fournisseur_retenu_id,
            motif_choix: c.motif_choix ?? '',
          });
        }
        this.loadDevisForConsultation(c.consultation_id);
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Comparaison introuvable.')),
    });
  }

  loadDevisForConsultation(consultationId: string): void {
    this.api
      .get<DevisRow[]>('/mg/achats/devis', { consultation_id: consultationId })
      .subscribe({
        next: (rows) => {
          this.devis.set(rows);
          this.resolveFournisseurLabels(rows.map((d) => d.fournisseur_id));
        },
        error: () => this.devis.set([]),
      });
  }

  resolveFournisseurLabels(ids: string[]): void {
    const unique = [...new Set(ids)];
    for (const fid of unique) {
      if (this.fournisseurLabels()[fid]) continue;
      this.api
        .get<{ id: string; raison_sociale: string; code?: string }>(
          `/mg/achats/fournisseurs/${fid}`,
        )
        .subscribe({
          next: (f) => {
            this.fournisseurLabels.update((m) => ({
              ...m,
              [fid]: f.raison_sociale || f.code || fid.slice(0, 8),
            }));
          },
        });
    }
  }

  fournisseurLabel(id: string): string {
    return this.fournisseurLabels()[id] || id.slice(0, 8) + '…';
  }

  search(): void {
    this.q.set(this.filters.controls.q.value.trim());
  }

  openFiche(r: ComparaisonRow): void {
    void this.router.navigateByUrl(`/achats-appro/comparaisons/${r.id}`);
  }

  askAction(row: ComparaisonRow, action: 'desactiver' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/comparaisons/${c.row.id}`)
        : this.api.post(`/mg/achats/comparaisons/${c.row.id}/desactiver`, {});
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? `Comparaison ${c.row.reference} supprimée.`
            : `Comparaison ${c.row.reference} désactivée.`,
        );
        if (this.mode() === 'list') this.loadList();
        else void this.router.navigateByUrl('/achats-appro/comparaisons');
      },
      error: (err) => {
        this.confirm.set(null);
        this.erreur.set(this.apiDetail(err, 'Action refusée.'));
      },
    });
  }

  saveCreate(): void {
    if (this.createForm.invalid) {
      this.createForm.markAllAsTouched();
      this.erreur.set('Sélectionnez une consultation.');
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    const v = this.createForm.getRawValue();
    this.api
      .post<ComparaisonRow>('/mg/achats/comparaisons', {
        consultation_id: v.consultation_id,
        observation: v.observation.trim() || null,
      })
      .subscribe({
        next: (c) => {
          this.saving.set(false);
          void this.router.navigateByUrl(`/achats-appro/comparaisons/${c.id}`);
        },
        error: (err) => {
          this.saving.set(false);
          this.erreur.set(this.apiDetail(err, 'Enregistrement impossible.'));
        },
      });
  }

  valider(): void {
    const id = this.id();
    if (!id || this.validateForm.invalid) {
      this.validateForm.markAllAsTouched();
      this.erreur.set('Indiquez le fournisseur retenu.');
      return;
    }
    this.validating.set(true);
    this.erreur.set('');
    const v = this.validateForm.getRawValue();
    this.api
      .post<ComparaisonRow>(`/mg/achats/comparaisons/${id}/valider`, {
        fournisseur_retenu_id: v.fournisseur_retenu_id,
        motif_choix: v.motif_choix.trim() || null,
      })
      .subscribe({
        next: (c) => {
          this.validating.set(false);
          this.current.set(c);
          this.msg.set('Comparaison validée — devis mis à jour.');
          const cid = c.consultation_id;
          this.loadDevisForConsultation(cid);
          this.validateForm.disable({ emitEvent: false });
        },
        error: (err) => {
          this.validating.set(false);
          this.erreur.set(this.apiDetail(err, 'Validation refusée.'));
        },
      });
  }

  bcQueryParams(): {
    fournisseur_id?: string;
    consultation_id?: string;
    comparaison_id?: string;
  } {
    const c = this.current();
    if (!c?.fournisseur_retenu_id) return {};
    return {
      fournisseur_id: c.fournisseur_retenu_id,
      consultation_id: c.consultation_id,
      comparaison_id: c.id,
    };
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
