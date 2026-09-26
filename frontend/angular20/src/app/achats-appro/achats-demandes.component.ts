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

interface Agence {
  id: string;
  libelle: string;
}

export interface DemandeLigne {
  id?: string;
  designation: string;
  description?: string | null;
  quantite: number;
  uom: string;
  prix_estime: number;
  montant_estime?: number;
}

export interface DemandeRow {
  id: string;
  reference: string;
  date_demande: string;
  agence_id: string;
  demandeur_nom: string | null;
  fonction?: string | null;
  type_achat: string;
  priorite: string;
  projet?: string | null;
  motif: string | null;
  date_souhaitee?: string | null;
  budget_estime?: number | null;
  statut: string;
  observation?: string | null;
  lignes?: DemandeLigne[];
  consultation_id?: string | null;
  bon_id?: string | null;
}

type Mode = 'list' | 'form';

@Component({
  selector: 'bea-achats-demandes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MgGedPanelComponent, MatIconModule],
  templateUrl: './achats-demandes.component.html',
  styleUrl: './achats-ui.css',
})
export class AchatsDemandesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly rows = signal<DemandeRow[]>([]);
  readonly current = signal<DemandeRow | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');
  readonly mode = signal<Mode>('list');
  readonly id = signal<string | null>(null);
  readonly saving = signal(false);
  readonly q = signal('');
  readonly statutFilter = signal('');
  readonly confirm = signal<{ row: DemandeRow; action: 'annuler' | 'supprimer' } | null>(null);

  readonly filters = this.fb.nonNullable.group({ q: '', statut: '' });
  readonly form = this.fb.nonNullable.group({
    date_demande: [new Date().toISOString().slice(0, 10), Validators.required],
    agence_id: ['', Validators.required],
    demandeur_nom: [''],
    fonction: [''],
    type_achat: ['FOURNITURE', Validators.required],
    priorite: ['NORMAL', Validators.required],
    projet: [''],
    motif: [''],
    date_souhaitee: [''],
    budget_estime: [null as number | null],
    observation: [''],
    lignes: this.fb.array([this.newLigne()]),
  });

  readonly filtered = computed(() => {
    const term = this.q().trim().toLowerCase();
    const statut = this.statutFilter();
    return this.rows().filter((r) => {
      if (statut && r.statut !== statut) return false;
      if (!term) return true;
      return (
        r.reference.toLowerCase().includes(term) ||
        (r.demandeur_nom ?? '').toLowerCase().includes(term) ||
        (r.motif ?? '').toLowerCase().includes(term)
      );
    });
  });

  readonly nextActions = computed(() => {
    const s = this.current()?.statut;
    const map: Record<string, { action: string; label: string }[]> = {
      BROUILLON: [{ action: 'soumettre', label: 'Soumettre' }],
      SOUMISE: [
        { action: 'valider', label: 'Valider' },
        { action: 'rejeter', label: 'Rejeter' },
      ],
      VALIDEE: [{ action: 'commander', label: 'Transformer en BC' }],
      CONSULTATION: [{ action: 'commander', label: 'Transformer en BC' }],
      COMMANDE: [{ action: 'cloturer', label: 'Clôturer' }],
    };
    return s ? map[s] ?? [] : [];
  });

  readonly canEditForm = computed(() => true);

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/achats/agences').subscribe({
      next: (rows) => this.agences.set(rows),
      error: () => this.erreur.set('Agences indisponibles.'),
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

  newLigne() {
    return this.fb.nonNullable.group({
      designation: ['', Validators.required],
      quantite: [1, Validators.required],
      uom: ['U'],
      prix_estime: [0],
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
    this.api.get<DemandeRow[]>('/mg/achats/demandes').subscribe({
      next: (rows) => this.rows.set(rows),
      error: (err) => this.erreur.set(this.apiDetail(err, 'Demandes indisponibles.')),
    });
  }

  loadOne(id: string): void {
    this.api.get<DemandeRow>(`/mg/achats/demandes/${id}`).subscribe({
      next: (d) => {
        this.current.set(d);
        this.form.patchValue({
          date_demande: d.date_demande,
          agence_id: d.agence_id,
          demandeur_nom: d.demandeur_nom ?? '',
          fonction: d.fonction ?? '',
          type_achat: d.type_achat || 'FOURNITURE',
          priorite: d.priorite || 'NORMAL',
          projet: d.projet ?? '',
          motif: d.motif ?? '',
          date_souhaitee: d.date_souhaitee ?? '',
          budget_estime: d.budget_estime ?? null,
          observation: d.observation ?? '',
        });
        this.lignes.clear();
        const lignes = d.lignes?.length
          ? d.lignes
          : [{ designation: '', quantite: 1, uom: 'U', prix_estime: 0 }];
        for (const l of lignes) {
          this.lignes.push(
            this.fb.nonNullable.group({
              designation: [l.designation, Validators.required],
              quantite: [Number(l.quantite), Validators.required],
              uom: [l.uom || 'U'],
              prix_estime: [Number(l.prix_estime || 0)],
            }),
          );
        }
        if (!this.canEditForm()) this.form.disable({ emitEvent: false });
        else this.form.enable({ emitEvent: false });
      },
      error: (err) => this.erreur.set(this.apiDetail(err, 'Demande introuvable.')),
    });
  }

  onSearch(): void {
    const v = this.filters.getRawValue();
    this.q.set(v.q);
    this.statutFilter.set(v.statut);
  }

  countStatut(statut: string): number {
    return this.rows().filter((r) => r.statut === statut).length;
  }

  canEdit(_r: DemandeRow): boolean {
    return true;
  }

  canCancel(_r: DemandeRow): boolean {
    return true;
  }

  edit(r: DemandeRow): void {
    void this.router.navigateByUrl(`/achats-appro/demandes/${r.id}`);
  }

  askAction(row: DemandeRow, action: 'annuler' | 'supprimer'): void {
    this.confirm.set({ row, action });
  }

  confirmAction(): void {
    const c = this.confirm();
    if (!c) return;
    const req =
      c.action === 'supprimer'
        ? this.api.delete(`/mg/achats/demandes/${c.row.id}`)
        : this.api.post(`/mg/achats/demandes/${c.row.id}/transition`, { action: 'annuler' });
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.msg.set(
          c.action === 'supprimer'
            ? `Demande ${c.row.reference} supprimée.`
            : `Demande ${c.row.reference} annulée.`,
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
      this.erreur.set('Complétez les champs obligatoires (agence, lignes).');
      return;
    }
    this.saving.set(true);
    this.erreur.set('');
    const v = this.form.getRawValue();
    const body = {
      date_demande: v.date_demande,
      agence_id: v.agence_id,
      demandeur_nom: v.demandeur_nom.trim() || null,
      fonction: v.fonction.trim() || null,
      type_achat: v.type_achat,
      priorite: v.priorite,
      projet: v.projet.trim() || null,
      motif: v.motif.trim() || null,
      date_souhaitee: v.date_souhaitee || null,
      budget_estime: v.budget_estime,
      observation: v.observation.trim() || null,
      lignes: v.lignes.map((l) => ({
        designation: l.designation.trim(),
        quantite: Number(l.quantite),
        uom: l.uom || 'U',
        prix_estime: Number(l.prix_estime || 0),
      })),
    };
    const req = this.id()
      ? this.api.patch<DemandeRow>(`/mg/achats/demandes/${this.id()}`, body)
      : this.api.post<DemandeRow>('/mg/achats/demandes', body);
    req.subscribe({
      next: (d) => {
        this.saving.set(false);
        this.msg.set(this.id() ? 'Demande mise à jour.' : 'Demande créée.');
        void this.router.navigateByUrl(`/achats-appro/demandes/${d.id}`);
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
    this.api.post<DemandeRow>(`/mg/achats/demandes/${id}/transition`, { action }).subscribe({
      next: (d) => {
        this.current.set(d);
        this.msg.set(`Transition effectuée → ${d.statut}`);
        if (action === 'commander' && d.bon_id) {
          void this.router.navigateByUrl(`/achats-appro/bons/${d.bon_id}`);
          return;
        }
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
