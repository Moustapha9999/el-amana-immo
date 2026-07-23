import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';
import { ApiService } from '../core/services/api.service';
import { tauxLineaireFromDuree } from '../shared/amortissement-rate.util';

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
}

interface ParamAmortissement {
  id: string;
  periodicite: string;
  prorata: boolean;
  journal_code: string;
  compte_dotation_defaut: string;
  compte_amortissement_defaut: string;
}

@Component({
  selector: 'app-parametres',
  imports: [
    ReactiveFormsModule,
    DecimalPipe,
    MatTabsModule,
    MatTableModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
  ],
  templateUrl: './parametres.component.html',
})
export class ParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly snack = inject(MatSnackBar);

  readonly agences = signal<AgenceRow[]>([]);
  readonly categories = signal<CategorieRow[]>([]);
  readonly comptes = signal<CompteRow[]>([]);
  readonly editingCategoryId = signal<string | null>(null);
  readonly tauxPreview = signal<number | null>(null);
  readonly totpEnabled = signal(false);
  readonly totpPending = signal(false);
  readonly totpSetupUrl = signal<string | null>(null);
  readonly totpQrSrc = signal<string | null>(null);
  readonly totpSetupSecret = signal<string | null>(null);

  readonly comptesImmo = computed(() => this.comptes().filter((c) => c.type_compte === 'immobilisation'));
  readonly comptesAmort = computed(() => this.comptes().filter((c) => c.type_compte === 'amortissement'));
  readonly comptesDotation = computed(() => this.comptes().filter((c) => c.type_compte === 'dotation'));

  readonly agenceColumns = ['code', 'libelle', 'ville', 'active'];
  readonly catColumns = ['famille', 'comptes', 'duree', 'taux', 'actions'];
  readonly compteColumns = ['numero', 'libelle', 'type'];

  readonly newAgence = this.fb.group({
    code: ['', Validators.required],
    libelle: ['', Validators.required],
    ville: [''],
  });

  readonly categoryEdit = this.fb.group({
    duree_annees_defaut: [null as number | null],
    compte_immobilisation: ['', Validators.required],
    compte_amortissement: [''],
    compte_dotation: [''],
    amortissable: [true],
    mode_amortissement_defaut: ['lineaire'],
    periodicite_defaut: ['annuel'],
  });

  readonly paramGlobal = this.fb.group({
    periodicite: ['mensuel'],
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
    this.reloadAgences();
    this.reloadCategories();
    this.reloadComptes();
    this.api.get<ParamAmortissement>('/parametrage/amortissement').subscribe((p) => {
      this.paramGlobal.patchValue(p);
    });
    this.categoryEdit.controls.duree_annees_defaut.valueChanges.subscribe((d) => {
      this.tauxPreview.set(tauxLineaireFromDuree(d));
    });
    this.loadTotpStatus();
  }

  compteLabel(c: CompteRow): string {
    return `${c.numero} — ${c.libelle}`;
  }

  loadTotpStatus(): void {
    this.api.get<{ enabled: boolean; pending_setup: boolean }>('/auth/2fa/status').subscribe((s) => {
      this.totpEnabled.set(s.enabled);
      this.totpPending.set(s.pending_setup);
    });
  }

  startTotpSetup(): void {
    this.api.post<{ secret: string; otpauth_url: string; qr_image_base64: string }>('/auth/2fa/setup', {}).subscribe({
      next: (res) => {
        this.totpSetupSecret.set(res.secret);
        this.totpSetupUrl.set(res.otpauth_url);
        this.totpQrSrc.set(`data:image/png;base64,${res.qr_image_base64}`);
        this.totpPending.set(true);
        this.snack.open('Scannez le QR dans Google Authenticator (ou saisissez le secret)', 'Fermer', {
          duration: 6000,
        });
      },
      error: (err) => this.snack.open(err.error?.detail ?? 'Erreur', 'Fermer', { duration: 4000 }),
    });
  }

  confirmTotpEnable(): void {
    const code = this.totpEnableForm.controls.code.value?.trim();
    if (!code) {
      return;
    }
    this.api.post<{ message: string }>('/auth/2fa/enable', { code }).subscribe({
      next: () => {
        this.snack.open('2FA activée', 'Fermer', { duration: 3000 });
        this.totpEnableForm.reset();
        this.totpSetupSecret.set(null);
        this.totpSetupUrl.set(null);
        this.totpQrSrc.set(null);
        this.loadTotpStatus();
      },
      error: (err) => this.snack.open(err.error?.detail ?? 'Code invalide', 'Fermer', { duration: 4000 }),
    });
  }

  disableTotp(): void {
    if (this.totpDisableForm.invalid) {
      return;
    }
    const raw = this.totpDisableForm.getRawValue();
    this.api.post<{ message: string }>('/auth/2fa/disable', raw).subscribe({
      next: () => {
        this.snack.open('2FA désactivée', 'Fermer', { duration: 3000 });
        this.totpDisableForm.reset();
        this.loadTotpStatus();
      },
      error: (err) => this.snack.open(err.error?.detail ?? 'Erreur', 'Fermer', { duration: 4000 }),
    });
  }

  reloadAgences(): void {
    this.api.get<Paginated<AgenceRow>>('/agences', { page: 1, size: 100 }).subscribe((r) => this.agences.set(r.items));
  }

  reloadCategories(): void {
    this.api
      .get<Paginated<CategorieRow>>('/immobilisations/categories', { page: 1, size: 100 })
      .subscribe((r) => this.categories.set(r.items));
  }

  reloadComptes(): void {
    this.api.get<Paginated<CompteRow>>('/plan-comptable', { page: 1, size: 200 }).subscribe((r) => this.comptes.set(r.items));
  }

  createAgence(): void {
    if (this.newAgence.invalid) {
      return;
    }
    const raw = this.newAgence.getRawValue();
    this.api
      .post<AgenceRow>('/agences', {
        code: raw.code?.trim(),
        libelle: raw.libelle?.trim(),
        ville: raw.ville?.trim() || null,
      })
      .subscribe({
        next: () => {
          this.snack.open('Agence créée', 'Fermer', { duration: 2500 });
          this.newAgence.reset();
          this.reloadAgences();
        },
        error: (err) => this.snack.open(err.error?.detail ?? 'Erreur', 'Fermer', { duration: 4000 }),
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
      periodicite_defaut: row.periodicite_defaut,
    });
    this.tauxPreview.set(tauxLineaireFromDuree(row.duree_annees_defaut));
  }

  cancelEditCategory(): void {
    this.editingCategoryId.set(null);
  }

  saveCategory(): void {
    const id = this.editingCategoryId();
    if (!id || this.categoryEdit.invalid) {
      return;
    }
    const raw = this.categoryEdit.getRawValue();
    this.api
      .patch<CategorieRow>(`/immobilisations/categories/${id}`, {
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
          this.snack.open('Catégorie mise à jour', 'Fermer', { duration: 2500 });
          this.editingCategoryId.set(null);
          this.reloadCategories();
        },
        error: (err) => this.snack.open(err.error?.detail ?? 'Erreur', 'Fermer', { duration: 4000 }),
      });
  }

  saveParamGlobal(): void {
    this.api.patch<ParamAmortissement>('/parametrage/amortissement', this.paramGlobal.getRawValue()).subscribe({
      next: () => this.snack.open('Paramètres amortissement enregistrés', 'Fermer', { duration: 2500 }),
      error: (err) => this.snack.open(err.error?.detail ?? 'Erreur', 'Fermer', { duration: 4000 }),
    });
  }

  tauxForCategory(row: CategorieRow): number | null {
    if (row.taux_lineaire_calcule != null) {
      return Number(row.taux_lineaire_calcule);
    }
    return tauxLineaireFromDuree(row.duree_annees_defaut);
  }
}
