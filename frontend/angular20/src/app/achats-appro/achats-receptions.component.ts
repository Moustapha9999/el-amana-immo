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
import { FeedbackService } from '../core/feedback/feedback.service';
import { feedbackSignal } from '../core/feedback/feedback-signal';
import { bcRecevable } from './achats-circuit';
import { quantiteDecimale } from '../shared/montant.pipe';
import { unsavedChanges } from '../core/feedback/unsaved-changes.guard';
import { AchatsBonApercuComponent, AchatsReceptionApercuComponent } from './achats-apercu.component';

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
  motif_annulation?: string | null;
  lignes?: ReceptionLigne[];
}

type Mode = 'list' | 'form';

@Component({
  selector: 'bea-achats-receptions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, AchatsBonApercuComponent, AchatsReceptionApercuComponent],
  templateUrl: './achats-receptions.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsReceptionsComponent implements OnInit {
  readonly hasUnsavedChanges = unsavedChanges(() => this.mode() === 'form' && this.form.dirty && !this.saving(), () => this.form);
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<ReceptionRow[]>([]);
  readonly current = signal<ReceptionRow | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly bons = signal<BonOpt[]>([]);
  readonly bonDetail = signal<BonDetail | null>(null);
  readonly erreur = feedbackSignal('error', '');
  readonly msg = feedbackSignal('success', '');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly q = signal('');
  readonly apercuId = signal<string | null>(null);
  readonly bonApercuId = signal<string | null>(null);

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
        this.bons.set(r.items.filter((b) => bcRecevable(b.statut))),
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
    if (this.router.url.split('?')[0].endsWith('/nouvelle') || param) {
      this.mode.set('form');
      if (param) {
        this.id.set(param);
        this.loadOne(param);
        this.form.disable({ emitEvent: false });
      } else {
        const bonId = this.route.snapshot.queryParamMap.get('bon_id');
        if (bonId) this.form.controls.bon_id.setValue(bonId);
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
          const reste = Math.max(0, quantiteDecimale(Number(l.quantite) - Number(l.quantite_recue || 0)));
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
        if (rec.statut !== 'ANNULEE') {
          for (const c of [this.form.controls.date_reception, this.form.controls.agence_id, this.form.controls.observation]) {
            c.enable({ emitEvent: false });
          }
        }
        this.form.markAsPristine();
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Réception introuvable.')),
    });
  }

  search(): void {
    this.q.set(this.filters.controls.q.value.trim());
  }

  open(r: ReceptionRow): void {
    this.apercuId.set(r.id);
  }

  supprimer(row: ReceptionRow): void {
    this.feedback
      .run(() => this.api.delete(`/mg/achats/receptions/${row.id}`), {
        confirm: {
          action: 'suppression',
          message: `La réception ${row.reference} sera supprimée, le stock contre-passé et les quantités rendues au BC.`,
        },
        loading: 'Suppression…',
        errorTitle: 'Suppression refusée',
        success: { title: 'Réception supprimée', details: [{ label: 'Référence', value: row.reference }] },
        busy: this.saving,
      })
      .subscribe({
        next: () => {
          if (this.mode() === 'form') void this.router.navigateByUrl('/achats-appro/receptions');
          else this.loadList();
        },
      });
  }

  /** Annulation = contre-passation (quantités reçues et stock restitués), jamais une suppression. */
  annuler(row: ReceptionRow): void {
    this.feedback
      .runWithReason((motif) => this.api.post<ReceptionRow>(`/mg/achats/receptions/${row.id}/annuler`, { motif }), {
        reason: {
          title: `Annuler la réception ${row.reference}`,
          message: 'Les quantités reçues seront retirées du BC et le stock contre-passé.',
          hint: 'Refusé si ces quantités sont déjà facturées : annulez d’abord la facture.',
          reasonLabel: 'Motif d’annulation',
          confirmLabel: 'Annuler la réception',
          tone: 'danger',
          icon: 'undo',
        },
        loading: 'Annulation…',
        errorTitle: 'Annulation refusée',
        success: { title: 'Réception annulée', details: [{ label: 'Référence', value: row.reference }] },
        busy: this.saving,
      })
      .subscribe({
        next: (rec) => {
          if (this.mode() === 'form') this.current.set(rec);
          else this.loadList();
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
