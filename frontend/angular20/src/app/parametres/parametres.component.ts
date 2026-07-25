import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { tauxLineaireFromDuree } from '../shared/amortissement-rate.util';
import { PaginationComponent } from '../shared/pagination.component';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { pairedAccountsForImmo } from '../immobilisations/immobilisation.constants';
import { BANQUE_EL_AMANA } from './agence.constants';

type ParamTab = 'agences' | 'categories' | 'comptes' | 'amortissement' | 'securite';

interface Paginated<T> {
  items: T[];
  total: number;
}

interface AgenceRow {
  id: string;
  code: string;
  libelle: string;
  ville: string | null;
  is_active: boolean;
  code_banque: string | null;
  banque_sigle: string | null;
  banque_raison_sociale: string | null;
  code_swift: string | null;
}

interface CategorieRow {
  id: string;
  code: string;
  famille: string;
  amortissable: boolean;
  duree_annees_defaut: number | null;
  taux_lineaire_calcule?: string | null;
  compte_immobilisation: string;
  compte_amortissement: string | null;
  compte_dotation: string | null;
  mode_amortissement_defaut: string;
  periodicite_defaut: string;
}

interface CompteRow {
  id: string;
  numero: string;
  libelle: string;
  type_compte: string;
  centre_analytique?: string | null;
  is_active: boolean;
  nature_code?: string | null;
  nature_libelle?: string | null;
  nature_taux?: string | number | null;
  nature_duree_annees?: number | null;
  nature_compte_amortissement?: string | null;
  nature_compte_dotation?: string | null;
}

interface ParamAmortissement {
  id: string;
  periodicite: string;
  prorata: boolean;
  journal_code: string;
  compte_dotation_defaut: string;
  compte_amortissement_defaut: string;
}

const TYPE_LABELS: Record<string, string> = {
  immobilisation: 'Immobilisation',
  amortissement: 'Amortissement',
  dotation: 'Dotation',
  reprise: 'Reprise',
  cession: 'Cession',
  rebut: 'Rebut',
};

const TYPE_COMPTE_OPTIONS = [
  { value: 'immobilisation', label: 'Immobilisation' },
  { value: 'amortissement', label: 'Amortissement' },
  { value: 'dotation', label: 'Dotation' },
  { value: 'reprise', label: 'Reprise' },
  { value: 'cession', label: 'Cession' },
  { value: 'rebut', label: 'Rebut' },
] as const;

@Component({
  selector: 'app-parametres',
  imports: [
    ReactiveFormsModule,
    MontantPipe,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    PaginationComponent,
  ],
  templateUrl: './parametres.component.html',
  styleUrl: './parametres.component.css',
})
export class ParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly dialogs = inject(UiDialogService);

  readonly tab = signal<ParamTab>('agences');
  readonly tabs: { id: ParamTab; label: string }[] = [
    { id: 'agences', label: 'Agences' },
    { id: 'categories', label: 'Types' },
    { id: 'comptes', label: 'Plan comptable' },
    { id: 'amortissement', label: 'Amortissement' },
    { id: 'securite', label: 'Sécurité' },
  ];

  readonly agences = signal<AgenceRow[]>([]);
  readonly categories = signal<CategorieRow[]>([]);
  readonly comptes = signal<CompteRow[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);

  readonly editingAgenceId = signal<string | null>(null);
  readonly agenceFormOpen = signal(false);
  readonly editingCompteId = signal<string | null>(null);
  readonly compteFormOpen = signal(false);
  readonly editingCategoryId = signal<string | null>(null);
  readonly tauxPreview = signal<number | null>(null);
  readonly typeCompteOptions = TYPE_COMPTE_OPTIONS;

  readonly totpEnabled = signal(false);
  readonly totpSetupUrl = signal<string | null>(null);
  readonly totpQrSrc = signal<string | null>(null);
  readonly totpSetupSecret = signal<string | null>(null);

  readonly searchAgences = signal('');
  readonly searchCategories = signal('');
  readonly searchComptes = signal('');

  readonly pageSize = 50;
  readonly pageAgences = signal(1);
  readonly pageCategories = signal(1);
  readonly pageComptes = signal(1);

  readonly comptesImmo = computed(() => this.comptes().filter((c) => c.type_compte === 'immobilisation'));
  readonly comptesAmort = computed(() => this.comptes().filter((c) => c.type_compte === 'amortissement'));
  readonly comptesDotation = computed(() => this.comptes().filter((c) => c.type_compte === 'dotation'));

  readonly filteredAgences = computed(() => {
    const q = this.searchAgences().trim().toLowerCase();
    if (!q) {
      return this.agences();
    }
    return this.agences().filter(
      (a) =>
        a.code.toLowerCase().includes(q) ||
        a.libelle.toLowerCase().includes(q) ||
        (a.ville ?? '').toLowerCase().includes(q),
    );
  });

  readonly filteredCategories = computed(() => {
    const q = this.searchCategories().trim().toLowerCase();
    if (!q) {
      return this.categories();
    }
    return this.categories().filter(
      (c) =>
        c.code.toLowerCase().includes(q) ||
        c.famille.toLowerCase().includes(q) ||
        c.compte_immobilisation.toLowerCase().includes(q),
    );
  });

  readonly filteredComptes = computed(() => {
    const q = this.searchComptes().trim().toLowerCase();
    if (!q) {
      return this.comptes();
    }
    return this.comptes().filter(
      (c) =>
        c.numero.toLowerCase().includes(q) ||
        c.libelle.toLowerCase().includes(q) ||
        c.type_compte.toLowerCase().includes(q),
    );
  });

  readonly pagedAgences = computed(() => this.slicePage(this.filteredAgences(), this.pageAgences()));
  readonly pagedCategories = computed(() =>
    this.slicePage(this.filteredCategories(), this.pageCategories()),
  );
  readonly pagedComptes = computed(() => this.slicePage(this.filteredComptes(), this.pageComptes()));

  private slicePage<T>(items: T[], page: number): T[] {
    const start = (page - 1) * this.pageSize;
    return items.slice(start, start + this.pageSize);
  }

  onSearchAgences(value: string): void {
    this.searchAgences.set(value);
    this.pageAgences.set(1);
  }

  onSearchCategories(value: string): void {
    this.searchCategories.set(value);
    this.pageCategories.set(1);
  }

  onSearchComptes(value: string): void {
    this.searchComptes.set(value);
    this.pageComptes.set(1);
  }

  readonly kpi = computed(() => ({
    agences: this.agences().length,
    categories: this.categories().length,
    comptes: this.comptes().length,
    totp: this.totpEnabled() ? 'Oui' : 'Non',
  }));

  readonly banque = BANQUE_EL_AMANA;
  readonly agenceColumns = [
    'code',
    'libelle',
    'code_banque',
    'code_swift',
    'ville',
    'active',
    'actions',
  ];
  readonly catColumns = ['famille', 'comptes', 'duree', 'taux', 'actions'];
  readonly compteColumns = ['numero', 'libelle', 'type', 'nature', 'taux', 'active', 'actions'];

  readonly agenceForm = this.fb.nonNullable.group({
    code: ['', Validators.required],
    libelle: ['', Validators.required],
    ville: [''],
    code_banque: [BANQUE_EL_AMANA.code_banque, Validators.required],
    banque_sigle: [BANQUE_EL_AMANA.sigle, Validators.required],
    banque_raison_sociale: [BANQUE_EL_AMANA.raison_sociale, Validators.required],
    code_swift: [BANQUE_EL_AMANA.code_swift, Validators.required],
    is_active: [true],
  });

  readonly compteForm = this.fb.nonNullable.group({
    numero: ['', [Validators.required, Validators.maxLength(20)]],
    libelle: ['', [Validators.required, Validators.maxLength(255)]],
    type_compte: ['immobilisation' as string, Validators.required],
    centre_analytique: [''],
    nature_libelle: [''],
    duree_annees: [null as number | null],
    compte_amortissement: [''],
    compte_dotation: [''],
    is_active: [true],
  });

  readonly compteTauxPreview = signal<number | null>(null);

  readonly categoryEdit = this.fb.group({
    duree_annees_defaut: [null as number | null],
    compte_immobilisation: ['', Validators.required],
    compte_amortissement: [''],
    compte_dotation: [''],
    amortissable: [true],
    mode_amortissement_defaut: ['lineaire'],
    periodicite_defaut: ['trimestriel'],
  });

  readonly paramGlobal = this.fb.group({
    periodicite: ['trimestriel'],
    prorata: [true],
    journal_code: ['OD'],
    compte_dotation_defaut: ['681000'],
    compte_amortissement_defaut: ['148000'],
  });

  readonly totpEnableForm = this.fb.group({
    code: ['', [Validators.required, Validators.minLength(6)]],
  });

  readonly totpDisableForm = this.fb.group({
    code: ['', [Validators.required, Validators.minLength(6)]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  ngOnInit(): void {
    this.reloadAll();
    this.api.get<ParamAmortissement>('/parametrage/amortissement').subscribe({
      next: (p) => this.paramGlobal.patchValue(p),
      error: () => undefined,
    });
    this.categoryEdit.controls.duree_annees_defaut.valueChanges.subscribe((d) => {
      this.tauxPreview.set(tauxLineaireFromDuree(d));
    });
    this.loadTotpStatus();
  }

  setTab(id: ParamTab): void {
    this.tab.set(id);
  }

  typeLabel(type: string): string {
    return TYPE_LABELS[type] ?? type;
  }

  compteLabel(c: CompteRow): string {
    return `${c.numero} — ${c.libelle}`;
  }

  reloadAll(): void {
    this.loading.set(true);
    let pending = 3;
    const done = () => {
      pending -= 1;
      if (pending <= 0) {
        this.loading.set(false);
      }
    };
    this.api.get<Paginated<AgenceRow>>('/agences', { page: 1, size: 100 }).subscribe({
      next: (r) => {
        this.agences.set(r.items);
        done();
      },
      error: () => {
        this.agences.set([]);
        done();
      },
    });
    this.api.get<Paginated<CategorieRow>>('/categories', { page: 1, size: 100 }).subscribe({
      next: (r) => {
        this.categories.set(r.items);
        done();
      },
      error: () => {
        this.categories.set([]);
        done();
      },
    });
    this.loadAllComptes(done);
  }

  /** L'API limite size à 100 : on enchaîne les pages pour charger tout le plan comptable. */
  private loadAllComptes(done: () => void): void {
    const acc: CompteRow[] = [];
    const fetchPage = (page: number): void => {
      this.api.get<Paginated<CompteRow>>('/plan-comptable', { page, size: 100 }).subscribe({
        next: (r) => {
          acc.push(...r.items);
          if (acc.length < r.total && r.items.length > 0) {
            fetchPage(page + 1);
          } else {
            this.comptes.set(acc);
            done();
          }
        },
        error: () => {
          this.comptes.set(acc);
          done();
        },
      });
    };
    fetchPage(1);
  }

  loadTotpStatus(): void {
    this.api.get<{ enabled: boolean; pending_setup: boolean }>('/auth/2fa/status').subscribe({
      next: (s) => this.totpEnabled.set(s.enabled),
      error: () => this.totpEnabled.set(false),
    });
  }

  openCreateAgence(): void {
    this.editingAgenceId.set(null);
    this.agenceForm.reset({
      code: '',
      libelle: '',
      ville: '',
      code_banque: BANQUE_EL_AMANA.code_banque,
      banque_sigle: BANQUE_EL_AMANA.sigle,
      banque_raison_sociale: BANQUE_EL_AMANA.raison_sociale,
      code_swift: BANQUE_EL_AMANA.code_swift,
      is_active: true,
    });
    this.agenceForm.controls.code.enable();
    this.agenceFormOpen.set(true);
  }

  openEditAgence(row: AgenceRow): void {
    this.editingAgenceId.set(row.id);
    this.agenceForm.reset({
      code: row.code,
      libelle: row.libelle,
      ville: row.ville ?? '',
      code_banque: row.code_banque ?? BANQUE_EL_AMANA.code_banque,
      banque_sigle: row.banque_sigle ?? BANQUE_EL_AMANA.sigle,
      banque_raison_sociale: row.banque_raison_sociale ?? BANQUE_EL_AMANA.raison_sociale,
      code_swift: row.code_swift ?? BANQUE_EL_AMANA.code_swift,
      is_active: row.is_active,
    });
    this.agenceForm.controls.code.disable();
    this.agenceFormOpen.set(true);
  }

  cancelAgenceForm(): void {
    this.agenceFormOpen.set(false);
    this.editingAgenceId.set(null);
    this.agenceForm.controls.code.enable();
  }

  saveAgence(): void {
    if (this.agenceForm.invalid) {
      this.agenceForm.markAllAsTouched();
      void this.dialogs.error('Complétez les champs obligatoires', 'Validation').subscribe();
      return;
    }
    const raw = this.agenceForm.getRawValue();
    const id = this.editingAgenceId();
    const action = id ? 'modification' : 'ajout';
    const label = raw.libelle.trim() || raw.code.trim();

    this.dialogs
      .confirmAction(action, id ? `Modifier l'agence « ${label} » ?` : `Ajouter l'agence « ${label} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.saving.set(true);
        const bankPayload = {
          libelle: raw.libelle.trim(),
          ville: raw.ville.trim() || null,
          code_banque: raw.code_banque.trim(),
          banque_sigle: raw.banque_sigle.trim(),
          banque_raison_sociale: raw.banque_raison_sociale.trim(),
          code_swift: raw.code_swift.trim(),
        };

        if (id) {
          this.api
            .patch<AgenceRow>(`/agences/${id}`, {
              ...bankPayload,
              is_active: raw.is_active,
            })
            .subscribe({
              next: () => {
                this.saving.set(false);
                this.agenceFormOpen.set(false);
                this.dialogs
                  .successAction('modification', `Agence « ${label} » mise à jour.`)
                  .subscribe(() => this.reloadAll());
              },
              error: (err) => {
                this.saving.set(false);
                void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe();
              },
            });
          return;
        }

        this.api
          .post<AgenceRow>('/agences', {
            code: raw.code.trim(),
            ...bankPayload,
          })
          .subscribe({
            next: () => {
              this.saving.set(false);
              this.agenceFormOpen.set(false);
              this.dialogs
                .successAction('ajout', `Agence « ${label} » créée.`)
                .subscribe(() => this.reloadAll());
            },
            error: (err) => {
              this.saving.set(false);
              void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe();
            },
          });
      });
  }

  deleteAgence(row: AgenceRow): void {
    this.dialogs
      .confirmAction('suppression', `Désactiver l'agence « ${row.libelle} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.api.delete<{ message: string }>(`/agences/${row.id}`).subscribe({
          next: () => {
            if (this.editingAgenceId() === row.id) {
              this.cancelAgenceForm();
            }
            this.dialogs
              .successAction('suppression', `Agence « ${row.libelle} » désactivée.`)
              .subscribe(() => this.reloadAll());
          },
          error: (err) => void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe(),
        });
      });
  }

  openCreateCompte(): void {
    this.editingCompteId.set(null);
    this.compteForm.reset({
      numero: '',
      libelle: '',
      type_compte: 'immobilisation',
      centre_analytique: '',
      nature_libelle: '',
      duree_annees: null,
      compte_amortissement: '',
      compte_dotation: '',
      is_active: true,
    });
    this.compteTauxPreview.set(null);
    this.compteForm.controls.numero.enable();
    this.compteForm.controls.type_compte.enable();
    this.compteFormOpen.set(true);
  }

  openEditCompte(row: CompteRow): void {
    this.editingCompteId.set(row.id);
    this.compteForm.reset({
      numero: row.numero,
      libelle: row.libelle,
      type_compte: row.type_compte,
      centre_analytique: row.centre_analytique ?? '',
      nature_libelle: row.nature_libelle ?? '',
      duree_annees: row.nature_duree_annees ?? null,
      compte_amortissement: row.nature_compte_amortissement ?? '',
      compte_dotation: row.nature_compte_dotation ?? '',
      is_active: row.is_active,
    });
    this.compteTauxPreview.set(row.nature_taux != null ? Number(row.nature_taux) : null);
    this.compteForm.controls.numero.disable();
    this.compteForm.controls.type_compte.disable();
    this.compteFormOpen.set(true);
  }

  cancelCompteForm(): void {
    this.compteFormOpen.set(false);
    this.editingCompteId.set(null);
    this.compteForm.controls.numero.enable();
    this.compteForm.controls.type_compte.enable();
  }

  onCompteNumeroOrTypeChange(): void {
    const raw = this.compteForm.getRawValue();
    if (raw.type_compte !== 'immobilisation' || this.editingCompteId()) {
      return;
    }
    const official = pairedAccountsForImmo(raw.numero.trim());
    if (official) {
      this.compteForm.controls.compte_amortissement.setValue(official.amort, { emitEvent: false });
      this.compteForm.controls.compte_dotation.setValue(official.dotation, { emitEvent: false });
    } else {
      const digits = raw.numero.replace(/\D/g, '');
      if (digits.length >= 3) {
        const suffix = digits.slice(-3);
        if (!raw.compte_amortissement) {
          this.compteForm.controls.compte_amortissement.setValue(`148${suffix}`, { emitEvent: false });
        }
        if (!raw.compte_dotation) {
          this.compteForm.controls.compte_dotation.setValue(`681${suffix}`, { emitEvent: false });
        }
      }
    }
    if (!raw.nature_libelle && raw.libelle) {
      this.compteForm.controls.nature_libelle.setValue(raw.libelle, { emitEvent: false });
    }
    this.refreshCompteTauxPreview();
  }

  refreshCompteTauxPreview(): void {
    const duree = this.compteForm.controls.duree_annees.value;
    this.compteTauxPreview.set(tauxLineaireFromDuree(duree));
  }

  saveCompte(): void {
    if (this.compteForm.invalid) {
      this.compteForm.markAllAsTouched();
      void this.dialogs.error('Complétez les champs obligatoires', 'Validation').subscribe();
      return;
    }
    const raw = this.compteForm.getRawValue();
    const id = this.editingCompteId();
    const isImmo = raw.type_compte === 'immobilisation';
    if (!id && isImmo && (raw.duree_annees == null || raw.duree_annees < 1)) {
      void this.dialogs
        .error('Durée (années) obligatoire pour lier le compte à une nature et son taux.', 'Validation')
        .subscribe();
      return;
    }
    const action = id ? 'modification' : 'ajout';
    const label = `${raw.numero.trim()} — ${raw.libelle.trim()}`;

    this.dialogs
      .confirmAction(action, id ? `Modifier le compte « ${label} » ?` : `Ajouter le compte « ${label} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.saving.set(true);
        if (id) {
          this.api
            .patch<CompteRow>(`/plan-comptable/${id}`, {
              libelle: raw.libelle.trim(),
              type_compte: raw.type_compte,
              centre_analytique: raw.centre_analytique.trim() || null,
              is_active: raw.is_active,
            })
            .subscribe({
              next: () => {
                this.saving.set(false);
                this.compteFormOpen.set(false);
                this.dialogs
                  .successAction('modification', `Compte « ${label} » mis à jour.`)
                  .subscribe(() => this.reloadAll());
              },
              error: (err) => {
                this.saving.set(false);
                void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe();
              },
            });
          return;
        }

        this.api
          .post<CompteRow>('/plan-comptable', {
            numero: raw.numero.trim(),
            libelle: raw.libelle.trim(),
            type_compte: raw.type_compte,
            centre_analytique: raw.centre_analytique.trim() || null,
            nature_libelle: isImmo ? (raw.nature_libelle.trim() || raw.libelle.trim()) : null,
            duree_annees: isImmo ? raw.duree_annees : null,
            compte_amortissement: isImmo ? raw.compte_amortissement.trim() || null : null,
            compte_dotation: isImmo ? raw.compte_dotation.trim() || null : null,
          })
          .subscribe({
            next: () => {
              this.saving.set(false);
              this.compteFormOpen.set(false);
              this.dialogs
                .successAction(
                  'ajout',
                  isImmo
                    ? `Compte « ${label} » créé avec sa nature, taux et comptes 148/681.`
                    : `Compte « ${label} » créé.`,
                )
                .subscribe(() => this.reloadAll());
            },
            error: (err) => {
              this.saving.set(false);
              void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe();
            },
          });
      });
  }

  deleteCompte(row: CompteRow): void {
    this.dialogs
      .confirmAction('suppression', `Désactiver le compte « ${row.numero} — ${row.libelle} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.api.delete<{ message: string }>(`/plan-comptable/${row.id}`).subscribe({
          next: () => {
            if (this.editingCompteId() === row.id) {
              this.cancelCompteForm();
            }
            this.dialogs
              .successAction('suppression', `Compte « ${row.numero} » désactivé.`)
              .subscribe(() => this.reloadAll());
          },
          error: (err) => void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe(),
        });
      });
  }

  startEditCategory(row: CategorieRow): void {
    this.editingCategoryId.set(row.id);
    this.categoryEdit.patchValue({
      duree_annees_defaut: row.duree_annees_defaut,
      compte_immobilisation: row.compte_immobilisation,
      compte_amortissement: row.compte_amortissement ?? '',
      compte_dotation: row.compte_dotation ?? '',
      amortissable: row.amortissable,
      mode_amortissement_defaut: row.mode_amortissement_defaut,
      periodicite_defaut: row.periodicite_defaut || 'trimestriel',
    });
    this.tauxPreview.set(tauxLineaireFromDuree(row.duree_annees_defaut));
  }

  cancelEditCategory(): void {
    this.editingCategoryId.set(null);
  }

  saveCategory(): void {
    const id = this.editingCategoryId();
    if (!id || this.categoryEdit.invalid) {
      void this.dialogs.error('Complétez les champs obligatoires', 'Validation').subscribe();
      return;
    }
    this.dialogs
      .confirmAction('modification', 'Enregistrer les modifications de ce type d’immobilisation ?')
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        const raw = this.categoryEdit.getRawValue();
        this.saving.set(true);
        this.api
          .patch<CategorieRow>(`/categories/${id}`, {
            duree_annees_defaut: raw.amortissable ? raw.duree_annees_defaut : null,
            compte_immobilisation: raw.compte_immobilisation,
            compte_amortissement: raw.amortissable ? raw.compte_amortissement || null : null,
            compte_dotation: raw.amortissable ? raw.compte_dotation || null : null,
            amortissable: raw.amortissable,
            mode_amortissement_defaut: raw.mode_amortissement_defaut,
            periodicite_defaut: raw.periodicite_defaut,
          })
          .subscribe({
            next: () => {
              this.saving.set(false);
              this.editingCategoryId.set(null);
              this.dialogs
                .successAction('modification', 'Type d’immobilisation mis à jour.')
                .subscribe(() => this.reloadAll());
            },
            error: (err) => {
              this.saving.set(false);
              void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe();
            },
          });
      });
  }

  saveParamGlobal(): void {
    this.dialogs
      .confirmAction('enregistrement', 'Enregistrer les paramètres globaux d’amortissement ?')
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.saving.set(true);
        this.api
          .patch<ParamAmortissement>('/parametrage/amortissement', this.paramGlobal.getRawValue())
          .subscribe({
            next: () => {
              this.saving.set(false);
              void this.dialogs
                .successAction('enregistrement', 'Paramètres d’amortissement enregistrés.')
                .subscribe();
            },
            error: (err) => {
              this.saving.set(false);
              void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe();
            },
          });
      });
  }

  tauxForCategory(row: CategorieRow): number | null {
    if (row.taux_lineaire_calcule != null) {
      return Number(row.taux_lineaire_calcule);
    }
    return tauxLineaireFromDuree(row.duree_annees_defaut);
  }

  startTotpSetup(): void {
    this.api.post<{ secret: string; otpauth_url: string; qr_image_base64: string }>('/auth/2fa/setup', {}).subscribe({
      next: (res) => {
        this.totpSetupSecret.set(res.secret);
        this.totpSetupUrl.set(res.otpauth_url);
        this.totpQrSrc.set(`data:image/png;base64,${res.qr_image_base64}`);
        void this.dialogs
          .info('Scannez le QR dans votre authenticator, puis saisissez le code.', 'Ouverture 2FA')
          .subscribe();
      },
      error: (err) => void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe(),
    });
  }

  confirmTotpEnable(): void {
    const code = this.totpEnableForm.controls.code.value?.trim();
    if (!code) {
      void this.dialogs.error('Code 2FA requis', 'Validation').subscribe();
      return;
    }
    this.dialogs.confirmAction('validation', 'Activer la double authentification sur ce compte ?').subscribe((ok) => {
      if (!ok) {
        return;
      }
      this.api.post<{ message: string }>('/auth/2fa/enable', { code }).subscribe({
        next: () => {
          this.totpEnableForm.reset();
          this.totpSetupSecret.set(null);
          this.totpSetupUrl.set(null);
          this.totpQrSrc.set(null);
          this.dialogs.successAction('validation', '2FA activée.').subscribe(() => this.loadTotpStatus());
        },
        error: (err) => void this.dialogs.error(err.error?.detail ?? 'Code invalide').subscribe(),
      });
    });
  }

  disableTotp(): void {
    if (this.totpDisableForm.invalid) {
      void this.dialogs.error('Code 2FA et mot de passe requis', 'Validation').subscribe();
      return;
    }
    this.dialogs.confirmAction('cloture', 'Désactiver la double authentification ?').subscribe((ok) => {
      if (!ok) {
        return;
      }
      const raw = this.totpDisableForm.getRawValue();
      this.api.post<{ message: string }>('/auth/2fa/disable', raw).subscribe({
        next: () => {
          this.totpDisableForm.reset();
          this.dialogs.successAction('cloture', '2FA désactivée.').subscribe(() => this.loadTotpStatus());
        },
        error: (err) => void this.dialogs.error(err.error?.detail ?? 'Erreur').subscribe(),
      });
    });
  }
}
