import { MontantPipe } from '../shared/montant.pipe';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ApiService } from '../core/services/api.service';
import { AuthService } from '../core/services/auth.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';

interface DashboardKpi {
  nombre_immobilisations: number;
  valeur_brute_totale: number;
  vnc_totale: number;
  dotation_periode: number;
  annee_reference: number;
}

type BusyKey =
  | 'ecritures-xlsx'
  | 'ecritures-pdf'
  | 'immo'
  | 'template'
  | 'import'
  | 'import-banque'
  | 'purge-banque'
  | 'audit'
  | null;

@Component({
  selector: 'app-rapports',
  imports: [MontantPipe, ReactiveFormsModule, RouterLink, MatButtonModule, MatIconModule],
  templateUrl: './rapports.component.html',
  styleUrl: './rapports.component.css',
})
export class RapportsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly dialogs = inject(UiDialogService);
  private readonly fb = inject(FormBuilder);

  readonly kpi = signal<DashboardKpi | null>(null);
  readonly loadingKpi = signal(true);
  readonly busy = signal<BusyKey>(null);
  readonly importResult = signal<string | null>(null);
  readonly importFileName = signal<string | null>(null);
  readonly bankImportResult = signal<string | null>(null);
  readonly bankImportFileName = signal<string | null>(null);
  readonly bankImportCount = signal<number | null>(null);

  readonly filterForm = this.fb.nonNullable.group({
    date_debut: '',
    date_fin: '',
  });

  readonly canAudit = computed(() => {
    const u = this.auth.user();
    if (!u) {
      return false;
    }
    if (u.is_superuser) {
      return true;
    }
    return u.roles.some((r) => r.code === 'administrateur' || r.code === 'auditeur');
  });

  readonly canImport = computed(() => {
    const u = this.auth.user();
    if (!u) {
      return false;
    }
    if (u.is_superuser) {
      return true;
    }
    return u.roles.some((r) => r.code === 'administrateur' || r.code === 'comptable');
  });

  ngOnInit(): void {
    this.loadKpi();
    this.refreshBankImportCount();
  }

  refreshBankImportCount(): void {
    if (!this.canImport()) {
      return;
    }
    this.api.get<{ count: number }>('/immobilisations/import-banque/count').subscribe({
      next: (res) => this.bankImportCount.set(res.count),
      error: () => this.bankImportCount.set(null),
    });
  }

  loadKpi(): void {
    this.loadingKpi.set(true);
    this.api.get<DashboardKpi>('/dashboard/kpi').subscribe({
      next: (data) => {
        this.kpi.set(data);
        this.loadingKpi.set(false);
      },
      error: () => {
        this.kpi.set(null);
        this.loadingKpi.set(false);
      },
    });
  }

  resetFilters(): void {
    this.filterForm.reset({ date_debut: '', date_fin: '' });
  }

  exportEcritures(format: 'xlsx' | 'pdf'): void {
    const f = this.filterForm.getRawValue();
    const params: Record<string, string> = { format };
    if (f.date_debut) {
      params['date_debut'] = f.date_debut;
    }
    if (f.date_fin) {
      params['date_fin'] = f.date_fin;
    }
    const key: BusyKey = format === 'pdf' ? 'ecritures-pdf' : 'ecritures-xlsx';
    const ext = format === 'pdf' ? 'pdf' : 'xlsx';
    this.runDownload(key, '/reporting/ecritures/export', `ecritures-bea-digital.${ext}`, params);
  }

  exportImmobilisations(): void {
    this.runDownload('immo', '/reporting/immobilisations/export', 'immobilisations-bea-digital.xlsx');
  }

  downloadImportTemplate(): void {
    this.runDownload(
      'template',
      '/reporting/immobilisations/import-template',
      'modele-import-immobilisations.xlsx',
    );
  }

  exportAudit(): void {
    this.runDownload('audit', '/reporting/audit/export', 'audit-bea-digital.xlsx');
  }

  onImportFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    this.dialogs
      .confirmAction('ajout', `Importer le fichier « ${file.name} » ?`)
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.importFileName.set(file.name);
        this.importResult.set(null);
        this.busy.set('import');
        this.api.upload<{ created: number; errors: string[] }>('/immobilisations/import', file).subscribe({
          next: (res) => {
            this.busy.set(null);
            const errPart = res.errors.length ? ` — ${res.errors.length} erreur(s)` : '';
            this.importResult.set(`${res.created} créée(s)${errPart}`);
            if (res.errors.length) {
              void this.dialogs.error(res.errors.slice(0, 3).join(' · '), 'Import partiel').subscribe();
            } else {
              void this.dialogs
                .successAction('ajout', `${res.created} immobilisation(s) importée(s)`)
                .subscribe();
            }
            this.loadKpi();
          },
          error: (err) => {
            this.busy.set(null);
            this.importResult.set(null);
            void this.dialogs.error(err.error?.detail ?? 'Import impossible').subscribe();
          },
        });
      });
  }

  onBankImportFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    this.dialogs
      .confirmAction(
        'ajout',
        `Importer le tableau banque « ${file.name} » (immobilisations + amortissements) ?`,
      )
      .subscribe((ok) => {
        if (!ok) {
          return;
        }
        this.bankImportFileName.set(file.name);
        this.bankImportResult.set(null);
        this.busy.set('import-banque');
        this.api
          .upload<{
            created: number;
            amortissements_created: number;
            errors: string[];
            reports_created: number;
            negatives: number;
          }>('/immobilisations/import-banque', file)
          .subscribe({
            next: (res) => {
              this.busy.set(null);
              const errPart = res.errors.length ? ` — ${res.errors.length} erreur(s)` : '';
              this.bankImportResult.set(
                `${res.created} bien(s), ${res.amortissements_created} amort.${errPart}`,
              );
              if (res.errors.length) {
                void this.dialogs
                  .error(res.errors.slice(0, 3).join(' · '), 'Import banque partiel')
                  .subscribe();
              } else {
                void this.dialogs
                  .successAction(
                    'ajout',
                    `${res.created} immobilisation(s) et ${res.amortissements_created} amortissement(s) importés`,
                  )
                  .subscribe();
              }
              this.loadKpi();
              this.refreshBankImportCount();
            },
            error: (err) => {
              this.busy.set(null);
              this.bankImportResult.set(null);
              void this.dialogs
                .error(err.error?.detail ?? 'Import banque impossible')
                .subscribe();
            },
          });
      });
  }

  purgeBankImport(): void {
    const n = this.bankImportCount();
    const msg =
      n != null && n > 0
        ? `Supprimer définitivement les ${n} immobilisation(s) issues de l’import banque (et leurs amortissements) ? Vous pourrez réimporter ensuite.`
        : 'Supprimer définitivement tous les biens issus de l’import banque (et leurs amortissements) ?';
    this.dialogs.confirmAction('suppression', msg).subscribe((ok) => {
      if (!ok) {
        return;
      }
      this.busy.set('purge-banque');
      this.api.post<{ deleted: number; message: string }>('/immobilisations/import-banque/purge', {}).subscribe({
        next: (res) => {
          this.busy.set(null);
          this.bankImportResult.set(res.message);
          void this.dialogs.successAction('suppression', res.message).subscribe();
          this.loadKpi();
          this.refreshBankImportCount();
        },
        error: (err) => {
          this.busy.set(null);
          void this.dialogs
            .error(err.error?.detail ?? 'Suppression de l’import impossible')
            .subscribe();
        },
      });
    });
  }

  private runDownload(
    key: BusyKey,
    path: string,
    filename: string,
    params?: Record<string, string>,
  ): void {
    this.busy.set(key);
    this.api.download(path, params).subscribe({
      next: (blob) => {
        this.busy.set(null);
        this.saveBlob(blob, filename);
      },
      error: () => {
        this.busy.set(null);
        void this.dialogs.error('Téléchargement impossible').subscribe();
      },
    });
  }

  private saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}
