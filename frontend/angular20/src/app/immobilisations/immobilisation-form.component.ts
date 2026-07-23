import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { tauxLineaireFromDuree } from '../shared/amortissement-rate.util';
import {
  MODE_AMORTISSEMENT_OPTIONS,
  PERIODICITE_OPTIONS,
  STATUT_IMMOBILISATION_LABELS,
} from './immobilisation.constants';

interface Paginated<T> {
  items: T[];
  total: number;
}

interface Categorie {
  id: string;
  code: string;
  famille: string;
  amortissable: boolean;
  compte_immobilisation: string;
  compte_amortissement: string | null;
  compte_dotation: string | null;
  duree_annees_defaut: number | null;
  taux_lineaire_defaut: string | null;
  mode_amortissement_defaut: string;
  periodicite_defaut: string;
  prorata_temporis: boolean;
}

interface Agence {
  id: string;
  code: string;
  libelle: string;
}

interface Fournisseur {
  id: string;
  code: string;
  raison_sociale: string;
}

interface AmortissementRow {
  id: string;
  periode: string;
  montant: string;
  cumul: string;
  vnc: string;
  valide: boolean;
  simule: boolean;
}

interface ImmobilisationDto {
  id: string;
  code_inventaire: string;
  numero_facture: string | null;
  quantite: number;
  designation: string;
  description: string | null;
  observations: string | null;
  categorie_id: string;
  agence_id: string | null;
  fournisseur_id: string | null;
  date_acquisition: string;
  date_mise_en_service: string | null;
  date_comptabilisation: string | null;
  valeur_brute: string;
  valeur_residuelle: string;
  duree_annees: number | null;
  periodicite: string;
  prorata_temporis: boolean;
  mode_amortissement: string;
  taux: string | null;
  statut: string;
  compte_immobilisation: string | null;
  compte_amortissement: string | null;
  compte_dotation: string | null;
  localisation: string | null;
}

@Component({
  selector: 'app-immobilisation-form',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DecimalPipe,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatSnackBarModule,
    MatTableModule,
  ],
  templateUrl: './immobilisation-form.component.html',
})
export class ImmobilisationFormComponent implements OnInit {
  readonly id = input<string | undefined>();

  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly snack = inject(MatSnackBar);

  readonly categories = signal<Categorie[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly fournisseurs = signal<Fournisseur[]>([]);
  readonly saving = signal(false);
  readonly workflowBusy = signal(false);
  readonly statutActuel = signal('brouillon');
  readonly dateComptabilisation = signal<string | null>(null);
  readonly amortissements = signal<AmortissementRow[]>([]);
  readonly amortissementColumns = ['periode', 'montant', 'cumul', 'vnc', 'statut', 'actions'];
  readonly situationComptable = signal<{ cumul_amortissement: string; vnc: string } | null>(null);
  readonly qrImageSrc = signal<string | null>(null);
  readonly qrPayload = signal<string | null>(null);
  readonly tauxCalcule = signal<number | null>(null);

  readonly canMettreEnService = computed(() => {
    const statut = this.statutActuel();
    const miseEnService = this.form.controls.date_mise_en_service.value;
    return (
      !!this.id() &&
      statut !== 'en_service' &&
      !['cedee', 'mise_au_rebut', 'archivee', 'sortie'].includes(statut) &&
      !!miseEnService
    );
  });

  readonly canSortir = computed(() => {
    const statut = this.statutActuel();
    return !!this.id() && ['en_service', 'suspendue', 'en_cours'].includes(statut);
  });

  readonly canEvolution = computed(() => {
    const statut = this.statutActuel();
    return (
      !!this.id() &&
      !['cedee', 'mise_au_rebut', 'archivee', 'sortie'].includes(statut)
    );
  });

  readonly reevaluations = signal<
    { date_reevaluation: string; ancienne_valeur: string; nouvelle_valeur: string; justificatif: string | null }[]
  >([]);
  readonly reevalHistoryColumns = ['date', 'ancienne', 'nouvelle'];

  readonly sortieForm = this.fb.nonNullable.group({
    date_cession: [''],
    prix_cession: [0, [Validators.min(0)]],
    libelle_cession: [''],
    date_rebut: [''],
    motif_rebut: [''],
  });

  readonly reevalForm = this.fb.nonNullable.group({
    date_reevaluation: [''],
    nouvelle_valeur: [0, [Validators.min(0.01)]],
    justificatif: [''],
  });

  readonly ajustementForm = this.fb.nonNullable.group({
    type_ajustement: ['correction'],
    date_ajustement: [''],
    montant: [0],
    commentaire: [''],
  });

  readonly transfertForm = this.fb.nonNullable.group({
    agence_id: [''],
    date_transfert: [''],
    commentaire: [''],
  });

  readonly statutOptions = Object.entries(STATUT_IMMOBILISATION_LABELS).map(([value, label]) => ({
    value,
    label,
  }));
  readonly periodiciteOptions = PERIODICITE_OPTIONS;
  readonly modeOptions = MODE_AMORTISSEMENT_OPTIONS;

  readonly form = this.fb.nonNullable.group({
    code_inventaire: ['', [Validators.required, Validators.maxLength(50)]],
    designation: ['', [Validators.required, Validators.maxLength(255)]],
    description: [''],
    observations: [''],
    numero_facture: [''],
    quantite: [1, [Validators.required, Validators.min(1)]],
    categorie_id: ['', Validators.required],
    agence_id: [''],
    fournisseur_id: [''],
    date_acquisition: ['', Validators.required],
    date_mise_en_service: [''],
    valeur_brute: [0, [Validators.required, Validators.min(0.01)]],
    valeur_residuelle: [0, [Validators.min(0)]],
    duree_annees: [null as number | null],
    periodicite: ['annuel'],
    prorata_temporis: [true],
    mode_amortissement: ['lineaire'],
    statut: ['brouillon'],
    compte_immobilisation: [{ value: '', disabled: true }],
    compte_amortissement: [{ value: '', disabled: true }],
    compte_dotation: [{ value: '', disabled: true }],
    localisation: [''],
  });

  ngOnInit(): void {
    this.api.get<Paginated<Categorie>>('/immobilisations/categories', { page: 1, size: 100 }).subscribe((res) => {
      this.categories.set(res.items.filter((c) => c.code.startsWith('TY-')));
    });
    this.api.get<Paginated<Agence>>('/agences', { page: 1, size: 100 }).subscribe((res) => {
      this.agences.set(res.items);
    });
    this.api.get<Paginated<Fournisseur>>('/fournisseurs', { page: 1, size: 100 }).subscribe((res) => {
      this.fournisseurs.set(res.items);
    });

    const immoId = this.id();
    if (immoId) {
      this.api.get<ImmobilisationDto>(`/immobilisations/${immoId}`).subscribe((row) => {
        this.patchFromDto(row);
        this.loadSituationComptable(immoId);
        this.loadQrCode(immoId);
      });
      this.loadAmortissements(immoId);
      this.loadReevaluations(immoId);
    }

    this.form.controls.categorie_id.valueChanges.subscribe((catId) => this.applyCategoryDefaults(catId));
    this.form.controls.duree_annees.valueChanges.subscribe((d) => this.tauxCalcule.set(tauxLineaireFromDuree(d)));
  }

  refreshTauxCalcule(): void {
    this.tauxCalcule.set(tauxLineaireFromDuree(this.form.controls.duree_annees.value));
  }

  selectedCategory(): Categorie | undefined {
    return this.categories().find((c) => c.id === this.form.controls.categorie_id.value);
  }

  applyCategoryDefaults(catId: string): void {
    const cat = this.categories().find((c) => c.id === catId);
    if (!cat) {
      return;
    }
    this.form.patchValue({
      compte_immobilisation: cat.compte_immobilisation,
      compte_amortissement: cat.compte_amortissement ?? '',
      compte_dotation: cat.compte_dotation ?? '',
      duree_annees: cat.amortissable ? (cat.duree_annees_defaut ?? null) : null,
      periodicite: cat.periodicite_defaut,
      prorata_temporis: cat.prorata_temporis,
      mode_amortissement: cat.mode_amortissement_defaut,
    });
    this.refreshTauxCalcule();
  }

  patchFromDto(row: ImmobilisationDto): void {
    this.statutActuel.set(row.statut);
    this.dateComptabilisation.set(row.date_comptabilisation);
    this.form.patchValue({
      code_inventaire: row.code_inventaire,
      designation: row.designation,
      description: row.description ?? '',
      observations: row.observations ?? '',
      numero_facture: row.numero_facture ?? '',
      quantite: row.quantite,
      categorie_id: row.categorie_id,
      agence_id: row.agence_id ?? '',
      fournisseur_id: row.fournisseur_id ?? '',
      date_acquisition: row.date_acquisition,
      date_mise_en_service: row.date_mise_en_service ?? '',
      valeur_brute: Number(row.valeur_brute),
      valeur_residuelle: Number(row.valeur_residuelle),
      duree_annees: row.duree_annees,
      periodicite: row.periodicite,
      prorata_temporis: row.prorata_temporis,
      mode_amortissement: row.mode_amortissement,
      statut: row.statut,
      compte_immobilisation: row.compte_immobilisation ?? '',
      compte_amortissement: row.compte_amortissement ?? '',
      compte_dotation: row.compte_dotation ?? '',
      localisation: row.localisation ?? '',
    });
    this.refreshTauxCalcule();
  }

  loadAmortissements(immoId: string): void {
    this.api.get<AmortissementRow[]>(`/amortissements/immobilisation/${immoId}`).subscribe((rows) => {
      this.amortissements.set(rows.filter((r) => !r.simule));
    });
  }

  loadSituationComptable(immoId: string): void {
    this.api
      .get<{ cumul_amortissement: string; vnc: string }>(`/immobilisations/${immoId}/situation-comptable`)
      .subscribe({
        next: (sit) => this.situationComptable.set(sit),
        error: () => this.situationComptable.set(null),
      });
  }

  loadQrCode(immoId: string): void {
    this.api.get<{ payload: string; image_base64: string }>(`/immobilisations/${immoId}/qr-code`).subscribe({
      next: (qr) => {
        this.qrPayload.set(qr.payload);
        this.qrImageSrc.set(`data:image/png;base64,${qr.image_base64}`);
      },
      error: () => {
        this.qrPayload.set(null);
        this.qrImageSrc.set(null);
      },
    });
  }

  loadReevaluations(immoId: string): void {
    this.api
      .get<
        {
          date_reevaluation: string;
          ancienne_valeur: string;
          nouvelle_valeur: string;
          justificatif: string | null;
        }[]
      >(`/reevaluations/immobilisation/${immoId}`)
      .subscribe((rows) => this.reevaluations.set(rows));
  }

  enregistrerReevaluation(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const r = this.reevalForm.getRawValue();
    if (!r.date_reevaluation) {
      this.snack.open('Date de réévaluation requise', 'Fermer', { duration: 3000 });
      return;
    }
    this.workflowBusy.set(true);
    this.api
      .post<{
        reevaluation: { nouvelle_valeur: string };
        plan_regenere: boolean;
        ecriture_ids: string[];
      }>('/reevaluations', {
        immobilisation_id: immoId,
        date_reevaluation: r.date_reevaluation,
        nouvelle_valeur: r.nouvelle_valeur,
        justificatif: r.justificatif || null,
      })
      .subscribe({
        next: (res) => {
          this.workflowBusy.set(false);
          this.form.patchValue({ valeur_brute: Number(res.reevaluation.nouvelle_valeur) });
          this.loadReevaluations(immoId);
          this.loadSituationComptable(immoId);
          this.loadAmortissements(immoId);
          const ecritPart =
            res.ecriture_ids?.length ? ` — ${res.ecriture_ids.length} écriture(s) 142/282` : '';
          const msg = (res.plan_regenere
            ? 'Réévaluation enregistrée — plan d\'amortissement régénéré'
            : 'Réévaluation enregistrée — régénérez le plan si des dotations étaient déjà validées') + ecritPart;
          this.snack.open(msg, 'Fermer', { duration: 5000 });
        },
        error: (err) => {
          this.workflowBusy.set(false);
          this.snack.open(err.error?.detail ?? 'Réévaluation impossible', 'Fermer', { duration: 5000 });
        },
      });
  }

  enregistrerAjustement(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const a = this.ajustementForm.getRawValue();
    if (!a.date_ajustement) {
      this.snack.open('Date d\'ajustement requise', 'Fermer', { duration: 3000 });
      return;
    }
    this.workflowBusy.set(true);
    this.api
      .post<{ ecriture_ids: string[] }>('/ajustements', {
        immobilisation_id: immoId,
        type_ajustement: a.type_ajustement,
        date_ajustement: a.date_ajustement,
        montant: a.montant,
        commentaire: a.commentaire || null,
      })
      .subscribe({
        next: (res) => {
          this.workflowBusy.set(false);
          this.loadSituationComptable(immoId);
          this.api.get<ImmobilisationDto>(`/immobilisations/${immoId}`).subscribe((row) => this.patchFromDto(row));
          const ecritPart = res.ecriture_ids?.length ? ` — ${res.ecriture_ids.length} écriture(s) 781/148` : '';
          this.snack.open(`Ajustement enregistré${ecritPart}`, 'Fermer', { duration: 4000 });
        },
        error: (err) => {
          this.workflowBusy.set(false);
          this.snack.open(err.error?.detail ?? 'Ajustement impossible', 'Fermer', { duration: 5000 });
        },
      });
  }

  enregistrerTransfert(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const t = this.transfertForm.getRawValue();
    if (!t.agence_id || !t.date_transfert) {
      this.snack.open('Agence et date de transfert requises', 'Fermer', { duration: 3000 });
      return;
    }
    this.workflowBusy.set(true);
    this.api
      .post(`/immobilisations/${immoId}/transfert`, {
        agence_id: t.agence_id,
        date_transfert: t.date_transfert,
        commentaire: t.commentaire || null,
      })
      .subscribe({
        next: () => {
          this.workflowBusy.set(false);
          this.form.patchValue({ agence_id: t.agence_id });
          this.snack.open('Transfert inter-agences enregistré', 'Fermer', { duration: 3000 });
        },
        error: (err) => {
          this.workflowBusy.set(false);
          this.snack.open(err.error?.detail ?? 'Transfert impossible', 'Fermer', { duration: 5000 });
        },
      });
  }

  enregistrerCession(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const s = this.sortieForm.getRawValue();
    if (!s.date_cession) {
      this.snack.open('Date de cession requise', 'Fermer', { duration: 3000 });
      return;
    }
    this.workflowBusy.set(true);
    this.api
      .post<{ cession: { plus_value: string; moins_value: string }; ecriture_ids: string[] }>('/cessions', {
        immobilisation_id: immoId,
        date_cession: s.date_cession,
        prix_cession: s.prix_cession,
        libelle: s.libelle_cession || null,
      })
      .subscribe({
        next: (res) => {
          this.workflowBusy.set(false);
          this.statutActuel.set('cedee');
          this.form.patchValue({ statut: 'cedee' });
          this.snack.open(
            `Cession enregistrée — ${res.ecriture_ids.length} écriture(s), PV ${res.cession.plus_value} / MV ${res.cession.moins_value}`,
            'Fermer',
            { duration: 5000 },
          );
        },
        error: (err) => {
          this.workflowBusy.set(false);
          const msg = err.error?.detail ?? 'Cession impossible';
          this.snack.open(typeof msg === 'string' ? msg : 'Erreur', 'Fermer', { duration: 5000 });
        },
      });
  }

  enregistrerRebut(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const s = this.sortieForm.getRawValue();
    if (!s.date_rebut) {
      this.snack.open('Date de rebut requise', 'Fermer', { duration: 3000 });
      return;
    }
    this.workflowBusy.set(true);
    this.api
      .post<{ rebut: { vnc: string }; ecriture_ids: string[] }>('/rebuts', {
        immobilisation_id: immoId,
        date_rebut: s.date_rebut,
        motif: s.motif_rebut || null,
      })
      .subscribe({
        next: (res) => {
          this.workflowBusy.set(false);
          this.statutActuel.set('mise_au_rebut');
          this.form.patchValue({ statut: 'mise_au_rebut' });
          this.snack.open(
            `Rebut enregistré — VNC ${res.rebut.vnc}, ${res.ecriture_ids.length} écriture(s)`,
            'Fermer',
            { duration: 5000 },
          );
        },
        error: (err) => {
          this.workflowBusy.set(false);
          const msg = err.error?.detail ?? 'Rebut impossible';
          this.snack.open(typeof msg === 'string' ? msg : 'Erreur', 'Fermer', { duration: 5000 });
        },
      });
  }

  mettreEnService(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    this.workflowBusy.set(true);
    this.api.post<ImmobilisationDto>(`/immobilisations/${immoId}/mettre-en-service`, {}).subscribe({
      next: (row) => {
        this.workflowBusy.set(false);
        this.patchFromDto(row);
          this.loadAmortissements(immoId);
          this.loadSituationComptable(immoId);
          this.snack.open('Immobilisation mise en service — plan d\'amortissement généré', 'Fermer', {
          duration: 4000,
        });
      },
      error: (err) => {
        this.workflowBusy.set(false);
        const msg = err.error?.detail ?? 'Mise en service impossible';
        this.snack.open(typeof msg === 'string' ? msg : 'Erreur', 'Fermer', { duration: 5000 });
      },
    });
  }

  regenererPlan(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    this.workflowBusy.set(true);
    this.api
      .post<AmortissementRow[]>('/amortissements/generer-plan', { immobilisation_id: immoId })
      .subscribe({
        next: () => {
          this.workflowBusy.set(false);
          this.loadAmortissements(immoId);
          this.snack.open('Plan d\'amortissement régénéré', 'Fermer', { duration: 3000 });
        },
        error: (err) => {
          this.workflowBusy.set(false);
          const msg = err.error?.detail ?? 'Régénération impossible';
          this.snack.open(typeof msg === 'string' ? msg : 'Erreur', 'Fermer', { duration: 5000 });
        },
      });
  }

  comptabiliser(row: AmortissementRow): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const dateEcriture = new Date().toISOString().slice(0, 10);
    this.workflowBusy.set(true);
    this.api
      .post<{ amortissement: AmortissementRow }>('/amortissements/comptabiliser', {
        immobilisation_id: immoId,
        periode: row.periode,
        date_ecriture: dateEcriture,
      })
      .subscribe({
        next: () => {
          this.workflowBusy.set(false);
          this.dateComptabilisation.set(dateEcriture);
          this.loadAmortissements(immoId);
          this.loadSituationComptable(immoId);
          this.snack.open(`Écriture 681 / 148 générée pour ${row.periode}`, 'Fermer', { duration: 4000 });
        },
        error: (err) => {
          this.workflowBusy.set(false);
          const msg = err.error?.detail ?? 'Comptabilisation impossible';
          this.snack.open(typeof msg === 'string' ? msg : 'Erreur', 'Fermer', { duration: 5000 });
        },
      });
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const body: Record<string, unknown> = {
      code_inventaire: raw.code_inventaire.trim(),
      designation: raw.designation.trim(),
      description: raw.description || null,
      observations: raw.observations || null,
      numero_facture: raw.numero_facture || null,
      quantite: raw.quantite,
      categorie_id: raw.categorie_id,
      agence_id: raw.agence_id || null,
      fournisseur_id: raw.fournisseur_id || null,
      date_acquisition: raw.date_acquisition,
      date_mise_en_service: raw.date_mise_en_service || null,
      valeur_brute: raw.valeur_brute,
      valeur_residuelle: raw.valeur_residuelle,
      duree_annees: raw.duree_annees,
      periodicite: raw.periodicite,
      prorata_temporis: raw.prorata_temporis,
      mode_amortissement: raw.mode_amortissement,
      statut: raw.statut,
      localisation: raw.localisation || null,
    };

    this.saving.set(true);
    const immoId = this.id();
    const req = immoId
      ? this.api.patch<ImmobilisationDto>(`/immobilisations/${immoId}`, body)
      : this.api.post<ImmobilisationDto>('/immobilisations', body);

    req.subscribe({
      next: (saved) => {
        this.saving.set(false);
        this.snack.open('Immobilisation enregistrée', 'Fermer', { duration: 3000 });
        void this.router.navigate(['/immobilisations', saved.id]);
      },
      error: (err) => {
        this.saving.set(false);
        const msg = err.error?.detail ?? 'Erreur lors de l’enregistrement';
        this.snack.open(typeof msg === 'string' ? msg : 'Erreur', 'Fermer', { duration: 5000 });
      },
    });
  }
}
