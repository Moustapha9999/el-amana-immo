import { DatePipe } from '@angular/common';
import { MontantInputDirective } from '../shared/montant-input.directive';
import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, effect, inject, input, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { map, Observable, of, switchMap } from 'rxjs';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { tauxLineaireFromDuree, formatPeriodeAmortissement } from '../shared/amortissement-rate.util';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import {
  MODE_AMORTISSEMENT_OPTIONS,
  PERIODICITE_OPTIONS,
  findNatureImmoOfficielle,
  sortCategoriesNatureImmo,
  natureImmoOptionLabel,
  statutLabel,
  STATUT_IMMOBILISATION_LABELS,
  MESSAGE_NON_AMORTISSABLE_EL_AMANA,
  isCompteNonAmortissable,
} from './immobilisation.constants';

type ImmoSection = 'fiche' | 'modifier' | 'amortissement' | 'reevaluation' | 'sortie' | 'pieces';

interface PieceComptable {
  id: string;
  immobilisation_id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
  type_piece: string;
  date_journee: string;
  reference: string | null;
  libelle: string | null;
  montant: number | string | null;
}

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

interface CentreCout {
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
  centre_cout_id: string | null;
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
    DatePipe,
    MontantPipe,
    MontantInputDirective,
    MatButtonModule,
    MatIconModule,
    MatTableModule,
  ],
  templateUrl: './immobilisation-form.component.html',
  styleUrl: './immobilisation-form.component.css',
})
export class ImmobilisationFormComponent implements OnInit {
  readonly id = input<string | undefined>();
  /** Route `:section` — modifier | amortissement | reevaluation | sortie | pieces */
  readonly section = input<string | undefined>();
  protected readonly natureImmoOptionLabel = natureImmoOptionLabel;
  protected readonly formatPeriode = formatPeriodeAmortissement;
  protected readonly pieceTypeLabel = (v: string) =>
    (
      {
        facture: 'Facture',
        pv: 'PV',
        bon_commande: 'Bon de commande',
        bon_livraison: 'Bon de livraison',
        contrat: 'Contrat',
        protocole_accord: "Protocole d'accord",
        autre: 'Autre',
      } as Record<string, string>
    )[v] || v;

  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly dialogs = inject(UiDialogService);

  private errMsg(err: { error?: { detail?: unknown } }, fallback: string): string {
    const d = err.error?.detail;
    return typeof d === 'string' ? d : fallback;
  }

  readonly activeSection = computed<ImmoSection>(() => {
    if (!this.id()) {
      return 'fiche';
    }
    const s = (this.section() ?? '').toLowerCase();
    if (
      s === 'modifier' ||
      s === 'amortissement' ||
      s === 'reevaluation' ||
      s === 'sortie' ||
      s === 'pieces'
    ) {
      return s;
    }
    return 'fiche';
  });

  readonly isCreate = computed(() => !this.id());
  readonly isView = computed(() => !!this.id() && this.activeSection() === 'fiche');
  readonly isEdit = computed(() => this.isCreate() || this.activeSection() === 'modifier');
  readonly showFiche = computed(() => this.isCreate() || this.activeSection() === 'fiche' || this.activeSection() === 'modifier');
  readonly showAmortissement = computed(() => this.activeSection() === 'amortissement');
  readonly showReevaluation = computed(() => this.activeSection() === 'reevaluation');
  readonly showSortie = computed(() => this.activeSection() === 'sortie');
  readonly showPieces = computed(() => this.activeSection() === 'pieces');

  readonly pageTitle = computed(() => {
    if (this.isCreate()) {
      return 'Nouvelle Saisie';
    }
    switch (this.activeSection()) {
      case 'modifier':
        return 'Modifier l’immobilisation';
      case 'amortissement':
        return 'Amortissement & comptabilisation';
      case 'reevaluation':
        return 'Réévaluation & ajustements';
      case 'sortie':
        return 'Sortie d’actif';
      case 'pieces':
        return 'Pièces comptables';
      default:
        return 'Détails immobilisation';
    }
  });

  readonly categories = signal<Categorie[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly centresCout = signal<CentreCout[]>([]);
  readonly fournisseurs = signal<Fournisseur[]>([]);
  /** True si l'utilisateur a modifié le N° à la main (stoppe l'auto-proposition). */
  private codeManuallyEdited = false;
  readonly saving = signal(false);
  readonly workflowBusy = signal(false);
  readonly statutActuel = signal('brouillon');
  /** Date de comptabilisation d'acquisition (note banque). */
  readonly dateComptabilisation = signal<string | null>(null);
  /** Dernière période d'amortissement validée (écritures 681/148). */
  readonly dernierePeriodeAmort = signal<string | null>(null);
  readonly amortissements = signal<AmortissementRow[]>([]);
  /** Exercice affiché : uniquement l'année civile en cours (Q1–Q4 ou mois). */
  readonly anneeExerciceAmort = signal(new Date().getFullYear());
  readonly amortissementColumns = ['periode', 'montant', 'cumul', 'vnc', 'statut', 'actions'];
  readonly situationComptable = signal<{ cumul_amortissement: string; vnc: string } | null>(null);
  readonly qrImageSrc = signal<string | null>(null);
  readonly qrPayload = signal<string | null>(null);
  /** True si un plan existe mais aucune ligne pour l'exercice courant. */
  readonly planHorsExercice = signal(false);
  readonly pieces = signal<PieceComptable[]>([]);

  /** Admin / comptable peuvent surcharger le taux issu de la catégorie. */
  readonly canOverrideTaux = computed(() => {
    const roles = this.auth.user()?.roles?.map((r) => r.code) ?? [];
    return this.auth.user()?.is_superuser === true || roles.includes('administrateur') || roles.includes('comptable');
  });

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
    reference_cession: [''],
    observations_cession: [''],
    date_rebut: [''],
    motif_rebut: [''],
  });

  readonly cessionPreview = signal<{
    cumul_amortissement: string;
    vnc: string;
    prix_cession: string;
    resultat: string;
    plus_value: string;
    moins_value: string;
    cas: string;
  } | null>(null);

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
    centre_cout_libre: [''],
    fournisseur_libre: [''],
    date_acquisition: ['', Validators.required],
    date_comptabilisation: ['', Validators.required],
    date_mise_en_service: [''],
    valeur_brute: [0, [Validators.required, Validators.min(0.01)]],
    valeur_residuelle: [0, [Validators.min(0)]],
    duree_annees: [null as number | null],
    taux: [null as number | null, [Validators.min(0), Validators.max(100)]],
    periodicite: [{ value: 'trimestriel', disabled: true }],
    prorata_temporis: [true],
    mode_amortissement: ['lineaire'],
    statut: ['brouillon'],
    compte_immobilisation: [{ value: '', disabled: true }],
    compte_amortissement: [{ value: '', disabled: true }],
    compte_dotation: [{ value: '', disabled: true }],
    localisation: [''],
  });

  constructor() {
    effect(() => {
      const view = this.isView();
      if (view) {
        this.form.disable({ emitEvent: false });
      } else if (this.isEdit()) {
        this.form.enable({ emitEvent: false });
        this.form.controls.periodicite.disable({ emitEvent: false });
        this.form.controls.compte_immobilisation.disable({ emitEvent: false });
        this.form.controls.compte_amortissement.disable({ emitEvent: false });
        this.form.controls.compte_dotation.disable({ emitEvent: false });
        if (!this.canOverrideTaux()) {
          this.form.controls.taux.disable({ emitEvent: false });
        }
        if (this.id()) {
          this.form.controls.code_inventaire.disable({ emitEvent: false });
        }
      }
    });
    // Recharge les pièces à chaque visite de l'onglet (retour depuis Pièces comptables)
    effect(() => {
      const immoId = this.id();
      if (this.showPieces() && immoId) {
        this.loadPieces(immoId);
      }
    });
  }

  ngOnInit(): void {
    this.api.get<Paginated<Categorie>>('/categories', { page: 1, size: 100 }).subscribe({
      next: (res) => this.categories.set(sortCategoriesNatureImmo(res.items ?? [])),
      error: () => {
        this.categories.set([]);
        void this.dialogs
          .error('Impossible de charger les natures IMMO. Vérifiez la connexion API / votre session.')
          .subscribe();
      },
    });
    this.api.get<Paginated<Agence>>('/agences', { page: 1, size: 100 }).subscribe((res) => {
      this.agences.set(res.items);
    });
    this.api.get<Paginated<CentreCout>>('/centres-cout', { page: 1, size: 100 }).subscribe({
      next: (res) => {
        this.centresCout.set(res.items ?? []);
        this.applyPendingReferentielLabels();
      },
      error: () => this.centresCout.set([]),
    });
    this.api.get<Paginated<Fournisseur>>('/fournisseurs', { page: 1, size: 100 }).subscribe({
      next: (res) => {
        this.fournisseurs.set(res.items ?? []);
        this.applyPendingReferentielLabels();
      },
      error: () => this.fournisseurs.set([]),
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
      this.loadPieces(immoId);
    }

    this.form.controls.code_inventaire.valueChanges.subscribe(() => {
      if (!this.id()) {
        this.codeManuallyEdited = true;
      }
    });
    this.form.controls.categorie_id.valueChanges.subscribe((catId) => {
      this.applyCategoryDefaults(catId);
      this.refreshCodeInventairePropose();
    });
    this.form.controls.date_acquisition.valueChanges.subscribe((acq) => {
      if (acq && !this.form.controls.date_comptabilisation.value) {
        this.form.controls.date_comptabilisation.setValue(acq, { emitEvent: false });
      }
      this.refreshCodeInventairePropose();
    });
    this.sortieForm.controls.date_cession.valueChanges.subscribe(() => this.refreshCessionPreview());
    this.sortieForm.controls.prix_cession.valueChanges.subscribe(() => this.refreshCessionPreview());
  }

  sectionLink(section?: ImmoSection): string[] {
    const immoId = this.id();
    if (!immoId) {
      return ['/immobilisations'];
    }
    if (!section || section === 'fiche') {
      return ['/immobilisations', immoId];
    }
    return ['/immobilisations', immoId, section];
  }

  refreshTauxCalcule(): void {
    if (this.form.controls.taux.value != null) {
      return;
    }
    const cat = this.selectedCategory();
    if (cat?.taux_lineaire_defaut != null) {
      this.form.controls.taux.setValue(Number(cat.taux_lineaire_defaut), { emitEvent: false });
      return;
    }
    const duree = this.form.controls.duree_annees.value;
    this.form.controls.taux.setValue(tauxLineaireFromDuree(duree), { emitEvent: false });
  }

  selectedCategory(): Categorie | undefined {
    return this.categories().find((c) => c.id === this.form.controls.categorie_id.value);
  }

  /** True si la nature / le compte est non amortissable (Banque El Amana). */
  isNonAmortissable(): boolean {
    const cat = this.selectedCategory();
    const compte =
      this.form.controls.compte_immobilisation.value || cat?.compte_immobilisation || '';
    if (isCompteNonAmortissable(compte)) {
      return true;
    }
    return cat != null && !cat.amortissable;
  }

  readonly messageNonAmortissable = MESSAGE_NON_AMORTISSABLE_EL_AMANA;

  canRegenererPlan(): boolean {
    const cat = this.selectedCategory();
    return this.statutActuel() === 'en_service' && !!cat?.amortissable && !this.isNonAmortissable();
  }

  statutBadgeLabel(): string {
    const key = this.id() ? this.statutActuel() : this.form.controls.statut.value;
    return statutLabel(key);
  }

  applyCategoryDefaults(catId: string): void {
    const cat = this.categories().find((c) => c.id === catId);
    if (!cat) {
      return;
    }
    const ref = findNatureImmoOfficielle(cat.code);
    const duree =
      cat.duree_annees_defaut ??
      ref?.duree_annees ??
      (cat.amortissable ? null : null);
    // Source de vérité : Type (DB) puis référentiel officiel — jamais 100/durée si Type connu
    const taux =
      (cat.taux_lineaire_defaut != null ? Number(cat.taux_lineaire_defaut) : null) ??
      ref?.taux ??
      tauxLineaireFromDuree(duree);

    this.form.patchValue({
      compte_immobilisation: cat.compte_immobilisation,
      compte_amortissement: cat.compte_amortissement ?? '',
      compte_dotation: cat.compte_dotation ?? '',
      duree_annees: duree,
      taux: cat.amortissable ? taux : null,
      periodicite: 'trimestriel',
      prorata_temporis: true,
      mode_amortissement: cat.mode_amortissement_defaut,
    });
    this.form.controls.taux.markAsPristine();
  }

  /** Propose AAI-2026-001 / Log-2026-001… (création uniquement, si non saisi à la main). */
  refreshCodeInventairePropose(): void {
    if (this.id() || this.codeManuallyEdited) {
      return;
    }
    const catId = this.form.controls.categorie_id.value;
    const acq = this.form.controls.date_acquisition.value;
    if (!catId || !acq) {
      return;
    }
    const annee = Number(String(acq).slice(0, 4));
    if (!Number.isFinite(annee) || annee < 2000) {
      return;
    }
    this.api
      .get<{ code_inventaire: string }>('/immobilisations/next-code', {
        categorie_id: catId,
        annee,
      })
      .subscribe({
        next: (res) => {
          if (this.codeManuallyEdited || this.id()) {
            return;
          }
          this.form.controls.code_inventaire.setValue(res.code_inventaire, { emitEvent: false });
        },
      });
  }

  patchFromDto(row: ImmobilisationDto): void {
    this.statutActuel.set(row.statut);
    this.dateComptabilisation.set(row.date_comptabilisation);
    this.pendingFournisseurId = row.fournisseur_id;
    this.pendingCentreCoutId = row.centre_cout_id;
    this.form.patchValue({
      code_inventaire: row.code_inventaire,
      designation: row.designation,
      description: row.description ?? '',
      observations: row.observations ?? '',
      numero_facture: row.numero_facture ?? '',
      quantite: row.quantite,
      categorie_id: row.categorie_id,
      agence_id: row.agence_id ?? '',
      centre_cout_libre: this.labelCentreCout(row.centre_cout_id),
      fournisseur_libre: this.labelFournisseur(row.fournisseur_id),
      date_acquisition: row.date_acquisition,
      date_comptabilisation: row.date_comptabilisation ?? '',
      date_mise_en_service: row.date_mise_en_service ?? '',
      valeur_brute: Number(row.valeur_brute),
      valeur_residuelle: Number(row.valeur_residuelle),
      duree_annees: row.duree_annees,
      taux: row.taux != null ? Number(row.taux) : null,
      periodicite: row.periodicite,
      prorata_temporis: row.prorata_temporis,
      mode_amortissement: row.mode_amortissement,
      statut: row.statut,
      compte_immobilisation: row.compte_immobilisation ?? '',
      compte_amortissement: row.compte_amortissement ?? '',
      compte_dotation: row.compte_dotation ?? '',
      localisation: row.localisation ?? '',
    });
    this.form.controls.taux.markAsPristine();
    this.applyPendingReferentielLabels();
  }

  loadAmortissements(immoId: string): void {
    this.api.get<AmortissementRow[]>(`/amortissements/immobilisation/${immoId}`).subscribe((rows) => {
      const plan = rows.filter((r) => !r.simule);
      const annee = this.anneeExerciceAmort();
      const prefix = `${annee}-`;
      // Affiche uniquement l'exercice courant (ex. 2026-Q1…Q4 ou 2026-01…12)
      const exercice = plan.filter((r) => r.periode.startsWith(prefix));
      this.amortissements.set(exercice);
      this.planHorsExercice.set(plan.length > 0 && exercice.length === 0);
      const validees = plan.filter((r) => r.valide).map((r) => r.periode).sort();
      this.dernierePeriodeAmort.set(validees.length ? validees[validees.length - 1]! : null);
    });
  }

  loadPieces(immoId: string): void {
    this.api.get<PieceComptable[]>(`/immobilisations/${immoId}/pieces`).subscribe({
      next: (rows) => this.pieces.set(rows),
      error: () => this.pieces.set([]),
    });
  }

  downloadPiece(row: PieceComptable): void {
    this.api.download(`/pieces/${row.id}/download`).subscribe({
      next: (blob) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = row.filename;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      error: () => void this.dialogs.error('Téléchargement impossible').subscribe(),
    });
  }

  removePiece(row: PieceComptable): void {
    const label = row.reference || row.filename;
    this.dialogs
      .confirmAction(
        'suppression',
        `Supprimer l’association de la pièce « ${label} » ? La pièce sera retirée de cette immobilisation.`,
      )
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        const immoId = this.id();
        this.api.delete(`/pieces/${row.id}`).subscribe({
          next: () => {
            if (immoId) {
              this.loadPieces(immoId);
            }
            void this.dialogs
              .successAction('suppression', 'Association de la pièce supprimée.')
              .subscribe();
          },
          error: () => void this.dialogs.error('Suppression impossible').subscribe(),
        });
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
      void this.dialogs.error('Date de réévaluation requise', 'Validation').subscribe();
      return;
    }
    this.dialogs
      .confirmAction('enregistrement', 'Enregistrer cette réévaluation de valeur brute ?')
      .subscribe((ok) => {
        if (!ok) {
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
              const ecritPart = res.ecriture_ids?.length
                ? ` — ${res.ecriture_ids.length} écriture(s) 142/282`
                : '';
              const msg =
                (res.plan_regenere
                  ? 'Réévaluation enregistrée — plan d’amortissement régénéré'
                  : 'Réévaluation enregistrée — régénérez le plan si besoin') + ecritPart;
              void this.dialogs.successAction('enregistrement', msg).subscribe();
            },
            error: (err) => {
              this.workflowBusy.set(false);
              void this.dialogs.error(this.errMsg(err, 'Réévaluation impossible')).subscribe();
            },
          });
      });
  }

  enregistrerAjustement(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const a = this.ajustementForm.getRawValue();
    if (!a.date_ajustement) {
      void this.dialogs.error('Date d’ajustement requise', 'Validation').subscribe();
      return;
    }
    this.dialogs.confirmAction('enregistrement', 'Enregistrer cet ajustement ?').subscribe((ok) => {
      if (!ok) {
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
            const ecritPart = res.ecriture_ids?.length ? ` — ${res.ecriture_ids.length} écriture(s)` : '';
            void this.dialogs.successAction('enregistrement', `Ajustement enregistré${ecritPart}`).subscribe();
          },
          error: (err) => {
            this.workflowBusy.set(false);
            void this.dialogs.error(this.errMsg(err, 'Ajustement impossible')).subscribe();
          },
        });
    });
  }

  enregistrerTransfert(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const t = this.transfertForm.getRawValue();
    if (!t.agence_id || !t.date_transfert) {
      void this.dialogs.error('Agence et date de transfert requises', 'Validation').subscribe();
      return;
    }
    this.dialogs.confirmAction('modification', 'Confirmer le transfert inter-agences ?').subscribe((ok) => {
      if (!ok) {
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
            void this.dialogs.successAction('modification', 'Transfert inter-agences enregistré.').subscribe();
          },
          error: (err) => {
            this.workflowBusy.set(false);
            void this.dialogs.error(this.errMsg(err, 'Transfert impossible')).subscribe();
          },
        });
    });
  }

  enregistrerCession(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const s = this.sortieForm.getRawValue();
    if (!s.date_cession) {
      void this.dialogs.error('Date de cession requise', 'Validation').subscribe();
      return;
    }
    if (!s.reference_cession.trim()) {
      void this.dialogs.error('Référence de la cession requise', 'Validation').subscribe();
      return;
    }
    this.dialogs
      .confirmAction(
        'cloture',
        'Valider la cession ? Les amortissements seront calculés jusqu’à cette date, puis arrêtés.',
      )
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.workflowBusy.set(true);
        this.api
          .post<{
            cession: { plus_value: string; moins_value: string; vnc: string };
            ecriture_ids: string[];
          }>('/cessions', {
            immobilisation_id: immoId,
            date_cession: s.date_cession,
            prix_cession: s.prix_cession,
            reference: s.reference_cession.trim(),
            observations: s.observations_cession.trim() || null,
          })
          .subscribe({
            next: (res) => {
              this.workflowBusy.set(false);
              this.statutActuel.set('cedee');
              this.form.patchValue({ statut: 'cedee' });
              this.loadAmortissements(immoId);
              this.loadSituationComptable(immoId);
              const pv = Number(res.cession.plus_value) || 0;
              const mv = Number(res.cession.moins_value) || 0;
              let resultatMsg = 'cession à l’équilibre';
              if (pv > 0) {
                resultatMsg = `plus-value ${pv.toFixed(2)} MRU`;
              } else if (mv > 0) {
                resultatMsg = `moins-value ${mv.toFixed(2)} MRU`;
              }
              void this.dialogs
                .successAction(
                  'cloture',
                  `Cession enregistrée — VNC ${res.cession.vnc}, ${resultatMsg}, ${res.ecriture_ids.length} écriture(s)`,
                )
                .subscribe();
            },
            error: (err) => {
              this.workflowBusy.set(false);
              void this.dialogs.error(this.errMsg(err, 'Cession impossible')).subscribe();
            },
          });
      });
  }

  refreshCessionPreview(): void {
    const immoId = this.id();
    const s = this.sortieForm.getRawValue();
    if (!immoId || !s.date_cession) {
      this.cessionPreview.set(null);
      return;
    }
    this.api
      .post<{
        cumul_amortissement: string;
        vnc: string;
        prix_cession: string;
        resultat: string;
        plus_value: string;
        moins_value: string;
        cas: string;
      }>('/cessions/preview', {
        immobilisation_id: immoId,
        date_cession: s.date_cession,
        prix_cession: s.prix_cession ?? 0,
      })
      .subscribe({
        next: (res) => this.cessionPreview.set(res),
        error: () => this.cessionPreview.set(null),
      });
  }

  enregistrerRebut(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    const s = this.sortieForm.getRawValue();
    if (!s.date_rebut) {
      void this.dialogs.error('Date de rebut requise', 'Validation').subscribe();
      return;
    }
    this.dialogs
      .confirmAction('cloture', 'Enregistrer la mise au rebut ? Le bien sera sorti du parc.')
      .subscribe((ok) => {
        if (!ok) {
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
              void this.dialogs
                .successAction(
                  'cloture',
                  `Rebut enregistré — VNC ${res.rebut.vnc}, ${res.ecriture_ids.length} écriture(s)`,
                )
                .subscribe();
            },
            error: (err) => {
              this.workflowBusy.set(false);
              void this.dialogs.error(this.errMsg(err, 'Rebut impossible')).subscribe();
            },
          });
      });
  }

  mettreEnService(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    this.dialogs
      .confirmAction('ouverture', 'Mettre en service cette immobilisation et générer le plan d’amortissement ?')
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.workflowBusy.set(true);
        this.api.post<ImmobilisationDto>(`/immobilisations/${immoId}/mettre-en-service`, {}).subscribe({
          next: (row) => {
            this.workflowBusy.set(false);
            this.patchFromDto(row);
            this.loadAmortissements(immoId);
            this.loadSituationComptable(immoId);
            void this.dialogs
              .successAction(
                'ouverture',
                this.isNonAmortissable()
                  ? 'Immobilisation mise en service (catégorie non amortissable — aucune dotation générée).'
                  : 'Immobilisation mise en service — plan d’amortissement généré.',
              )
              .subscribe();
          },
          error: (err) => {
            this.workflowBusy.set(false);
            void this.dialogs.error(this.errMsg(err, 'Mise en service impossible')).subscribe();
          },
        });
      });
  }

  regenererPlan(): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    this.dialogs
      .confirmAction('validation', 'Régénérer le plan d’amortissement ?')
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.workflowBusy.set(true);
        this.api
          .post<AmortissementRow[]>('/amortissements/generer-plan', { immobilisation_id: immoId })
          .subscribe({
            next: () => {
              this.workflowBusy.set(false);
              this.loadAmortissements(immoId);
              void this.dialogs.successAction('validation', 'Plan d’amortissement régénéré.').subscribe();
            },
            error: (err) => {
              this.workflowBusy.set(false);
              void this.dialogs.error(this.errMsg(err, 'Régénération impossible')).subscribe();
            },
          });
      });
  }

  comptabiliser(row: AmortissementRow): void {
    const immoId = this.id();
    if (!immoId) {
      return;
    }
    this.dialogs
      .confirmAction(
        'comptabilisation',
        `Comptabiliser la dotation de ${this.formatPeriode(row.periode)} (écriture 681 / 148) ?`,
      )
      .subscribe((ok) => {
        if (!ok) {
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
              this.loadAmortissements(immoId);
              this.loadSituationComptable(immoId);
              void this.dialogs
                .successAction('comptabilisation', `Écriture 681 / 148 générée pour ${this.formatPeriode(row.periode)}.`)
                .subscribe();
            },
            error: (err) => {
              this.workflowBusy.set(false);
              void this.dialogs.error(this.errMsg(err, 'Comptabilisation impossible')).subscribe();
            },
          });
      });
  }

  private pendingFournisseurId: string | null = null;
  private pendingCentreCoutId: string | null = null;

  private labelFournisseur(id: string | null | undefined): string {
    if (!id) {
      return '';
    }
    return this.fournisseurs().find((f) => f.id === id)?.raison_sociale ?? '';
  }

  private labelCentreCout(id: string | null | undefined): string {
    if (!id) {
      return '';
    }
    return this.centresCout().find((c) => c.id === id)?.libelle ?? '';
  }

  private applyPendingReferentielLabels(): void {
    if (this.pendingFournisseurId) {
      const label = this.labelFournisseur(this.pendingFournisseurId);
      if (label) {
        this.form.controls.fournisseur_libre.setValue(label, { emitEvent: false });
        this.pendingFournisseurId = null;
      }
    }
    if (this.pendingCentreCoutId) {
      const label = this.labelCentreCout(this.pendingCentreCoutId);
      if (label) {
        this.form.controls.centre_cout_libre.setValue(label, { emitEvent: false });
        this.pendingCentreCoutId = null;
      }
    }
  }

  private referentielCode(label: string, prefix: string): string {
    const base = label
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 20);
    return `${prefix}-${base || 'X'}`.slice(0, 30);
  }

  private resolveFournisseurId(): Observable<string | null> {
    const raw = this.form.getRawValue();
    const libre = (raw.fournisseur_libre ?? '').trim();
    if (!libre) {
      return of(null);
    }
    const existing = this.fournisseurs().find(
      (f) =>
        f.raison_sociale.trim().toLowerCase() === libre.toLowerCase() ||
        f.code.trim().toLowerCase() === libre.toLowerCase(),
    );
    if (existing) {
      return of(existing.id);
    }
    return this.api
      .post<Fournisseur>('/fournisseurs', {
        code: this.referentielCode(libre, 'FRN'),
        raison_sociale: libre,
      })
      .pipe(
        map((created) => {
          this.fournisseurs.update((list) => [...list, created]);
          return created.id;
        }),
      );
  }

  private resolveCentreCoutId(): Observable<string | null> {
    const raw = this.form.getRawValue();
    const libre = (raw.centre_cout_libre ?? '').trim();
    if (!libre) {
      return of(null);
    }
    const existing = this.centresCout().find(
      (c) =>
        c.libelle.trim().toLowerCase() === libre.toLowerCase() ||
        c.code.trim().toLowerCase() === libre.toLowerCase(),
    );
    if (existing) {
      return of(existing.id);
    }
    return this.api
      .post<CentreCout>('/centres-cout', {
        code: this.referentielCode(libre, 'CC'),
        libelle: libre,
      })
      .pipe(
        map((created) => {
          this.centresCout.update((list) => [...list, created]);
          return created.id;
        }),
      );
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      void this.dialogs.error('Complétez les champs obligatoires', 'Validation').subscribe();
      return;
    }
    const immoId = this.id();
    const action = immoId ? 'modification' : 'ajout';
    const code = this.form.getRawValue().code_inventaire.trim();

    this.dialogs
      .confirmAction(
        action,
        immoId ? `Enregistrer les modifications de « ${code} » ?` : `Créer l’immobilisation « ${code} » ?`,
      )
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.saving.set(true);
        this.resolveFournisseurId()
          .pipe(
            switchMap((fournisseur_id) =>
              this.resolveCentreCoutId().pipe(
                switchMap((centre_cout_id) => {
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
                    centre_cout_id,
                    fournisseur_id,
                    date_acquisition: raw.date_acquisition,
                    date_comptabilisation: raw.date_comptabilisation,
                    date_mise_en_service: raw.date_mise_en_service || null,
                    valeur_brute: raw.valeur_brute,
                    valeur_residuelle: raw.valeur_residuelle,
                    duree_annees: raw.duree_annees,
                    taux: raw.taux,
                    periodicite: raw.periodicite,
                    prorata_temporis: raw.prorata_temporis,
                    mode_amortissement: raw.mode_amortissement,
                    statut: raw.statut,
                    compte_immobilisation: raw.compte_immobilisation || null,
                    localisation: raw.localisation || null,
                  };
                  return immoId
                    ? this.api.patch<ImmobilisationDto>(`/immobilisations/${immoId}`, body)
                    : this.api.post<ImmobilisationDto>('/immobilisations', body);
                }),
              ),
            ),
          )
          .subscribe({
            next: (saved) => {
              this.saving.set(false);
              this.dialogs
                .successAction(
                  action,
                  immoId
                    ? `« ${saved.code_inventaire} » a été mise à jour.`
                    : `« ${saved.code_inventaire} » a été créée.`,
                )
                .subscribe(() => void this.router.navigate(['/immobilisations', saved.id]));
            },
            error: (err) => {
              this.saving.set(false);
              void this.dialogs.error(this.errMsg(err, 'Erreur lors de l’enregistrement')).subscribe();
            },
          });
      });
  }

  cancel(): void {
    const immoId = this.id();
    if (immoId && this.activeSection() === 'modifier') {
      void this.router.navigate(['/immobilisations', immoId]);
      return;
    }
    void this.router.navigate(['/immobilisations']);
  }
}
