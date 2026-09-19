import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { coreAdminOpsError } from './core-admin-ops.models';

interface BackupRow {
  id: string;
  level: string;
  backup_type: string;
  espace_code?: string | null;
  module_code?: string | null;
  status: string;
  size_bytes: number;
  label?: string | null;
  created_at?: string | null;
  error_message?: string | null;
  shared_dependencies?: string[] | null;
}

interface ModuleState {
  id: string;
  code: string;
  label: string;
  espace_code?: string | null;
  espace_label?: string | null;
  statut: string;
  status_message: string;
  version: string;
  admins_bypass_maintenance: boolean;
  maintenance_ends_at?: string | null;
}

const STATUT_OPTIONS = [
  'actif',
  'developpement',
  'mise_a_jour',
  'maintenance',
  'suspendu',
  'bloque',
  'bientot',
  'archive',
  'inactif',
];

@Component({
  selector: 'bea-core-admin-backups',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, DecimalPipe, FormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash bea-admin-backups">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Sauvegardes</h1>
          <p>Sauvegardes globales, par département ou par module — historisées et auditées.</p>
        </div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/recovery">Recovery</a>
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }

      <div class="bea-admin-panels bea-admin-panels--equal">
        <section class="bea-admin-panel bea-admin-backups__card">
          <p class="bea-admin-backups__kicker">Continuité</p>
          <h2>Synthèse</h2>
          @if (dash(); as d) {
            <div class="bea-admin-backups__stats">
              <article class="bea-admin-backups__stat">
                <span>Dernière globale</span>
                <strong>
                  @if (d.derniere_globale; as g) {
                    {{ g.created_at | date: 'dd/MM/yyyy HH:mm' }}
                  } @else {
                    —
                  }
                </strong>
                @if (d.derniere_globale; as g) {
                  <em class="bea-admin-backups__status" [attr.data-status]="g.status">{{ g.status }}</em>
                }
              </article>
              <article class="bea-admin-backups__stat">
                <span>Dernière manuelle</span>
                <strong>
                  @if (d.derniere_manuelle; as m) {
                    {{ m.created_at | date: 'dd/MM/yyyy HH:mm' }}
                  } @else {
                    —
                  }
                </strong>
              </article>
              <article class="bea-admin-backups__stat">
                <span>Disponibles</span>
                <strong>{{ d.success }} / {{ d.total }}</strong>
              </article>
              <article class="bea-admin-backups__stat">
                <span>Dernière erreur</span>
                <strong>{{ d.derniere_erreur?.error_message || 'Aucune' }}</strong>
              </article>
            </div>
          }
        </section>

        <section class="bea-admin-panel bea-admin-backups__card bea-admin-backups__create">
          <p class="bea-admin-backups__kicker">Action</p>
          <h2>Créer une sauvegarde</h2>
          <div class="bea-admin-backups__form">
            <label class="bea-admin-field">
              <span>Niveau</span>
              <select [(ngModel)]="level">
                <option value="global">Global — BEA-DIGITAL</option>
                <option value="departement">Département</option>
                <option value="module">Module</option>
              </select>
            </label>
            @if (level === 'departement' || level === 'module') {
              <label class="bea-admin-field">
                <span>Département (code)</span>
                <input [(ngModel)]="espaceCode" placeholder="comptabilite" />
              </label>
            }
            @if (level === 'module') {
              <label class="bea-admin-field">
                <span>Module (code)</span>
                <input [(ngModel)]="moduleCode" placeholder="immobilisations" />
              </label>
            }
            <button
              type="button"
              class="bea-admin-btn bea-admin-backups__submit"
              [disabled]="busy()"
              (click)="confirmBackup()"
            >
              {{ busy() ? 'Sauvegarde…' : 'Sauvegarder BEA-DIGITAL' }}
            </button>
          </div>
        </section>
      </div>

      <section class="bea-admin-panel bea-admin-backups__history">
        <div class="bea-admin-backups__history-head">
          <div>
            <p class="bea-admin-backups__kicker">Journal</p>
            <h2>Historique</h2>
          </div>
        </div>
        @if (loading()) {
          <p class="bea-admin-dash__loading">Chargement…</p>
        } @else {
          <div class="bea-admin-panel__scroll">
            <table class="bea-admin-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Niveau</th>
                  <th>Cible</th>
                  <th>Taille</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                @for (row of items(); track row.id) {
                  <tr>
                    <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    <td>{{ row.backup_type }}</td>
                    <td>
                      <span class="bea-admin-backups__level">{{ row.level }}</span>
                    </td>
                    <td>{{ row.label || row.module_code || row.espace_code || 'BEA-DIGITAL' }}</td>
                    <td>{{ (row.size_bytes / 1048576) | number: '1.1-1' }} Mo</td>
                    <td>
                      <span class="bea-admin-backups__status" [attr.data-status]="row.status">
                        {{ row.status }}
                      </span>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </section>
    </section>
  `,
})
export class CoreAdminBackupsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialog = inject(BeaAdminDialogService);

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly erreur = signal('');
  readonly items = signal<BackupRow[]>([]);
  readonly dash = signal<{
    total: number;
    success: number;
    derniere_globale?: BackupRow | null;
    derniere_manuelle?: BackupRow | null;
    derniere_erreur?: BackupRow | null;
  } | null>(null);

  level: 'global' | 'departement' | 'module' = 'global';
  espaceCode = 'comptabilite';
  moduleCode = 'immobilisations';

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.get<typeof this.dash extends never ? never : any>('/plateforme/admin/backups/dashboard').subscribe({
      next: (d) => this.dash.set(d),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Synthèse indisponible')),
    });
    this.api
      .get<{ items: BackupRow[] }>('/plateforme/admin/backups', { page: 1, size: 30 })
      .subscribe({
        next: (res) => {
          this.items.set(res.items);
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          this.erreur.set(coreAdminOpsError(err, 'Impossible de charger les sauvegardes.'));
        },
      });
  }

  async confirmBackup(): Promise<void> {
    const ok = await this.dialog.confirm({
      title: 'Sauvegarde',
      message:
        this.level === 'global'
          ? 'Créer une sauvegarde complète de BEA-DIGITAL (CORE + métiers + fichiers) ?'
          : `Créer une sauvegarde ${this.level} ? Les tables CORE ne sont pas écrasées en recovery partiel.`,
      confirmLabel: 'Confirmer',
      cancelLabel: 'Annuler',
    });
    if (!ok) return;
    this.busy.set(true);
    this.erreur.set('');
    const body: Record<string, string> = {
      level: this.level,
      backup_type: 'manuelle',
    };
    if (this.level !== 'global') body['espace_code'] = this.espaceCode;
    if (this.level === 'module') body['module_code'] = this.moduleCode;
    this.api.post<BackupRow>('/plateforme/admin/backups', body).subscribe({
      next: (row) => {
        this.busy.set(false);
        this.reload();
        void this.dialog.success(
          `Sauvegarde ${row.level} créée avec succès${row.label ? ` (« ${row.label} ») ` : ' '}.`,
          'Sauvegarde effectuée',
        );
      },
      error: (err) => {
        this.busy.set(false);
        const msg = coreAdminOpsError(err, 'Échec de la sauvegarde');
        this.erreur.set(msg);
        void this.dialog.error(msg, 'Sauvegarde impossible');
      },
    });
  }
}

@Component({
  selector: 'bea-core-admin-recovery',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash bea-admin-recovery">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Recovery</h1>
          <p>
            Restauration par périmètre. Un backup de sécurité est créé automatiquement avant chaque
            recovery. La restauration globale reste manuelle (scripts).
          </p>
        </div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/backups">Sauvegardes</a>
      </header>
      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (message()) {
        <p class="bea-admin-dash__ok">{{ message() }}</p>
      }

      <div class="bea-admin-recovery__note">
        <strong>Sécurité</strong>
        <span>
          Chaque restauration partielle crée d’abord un backup de sécurité. Les tables CORE ne sont
          pas écrasées.
        </span>
      </div>

      <section class="bea-admin-panel bea-admin-recovery__card">
        <div class="bea-admin-recovery__card-head">
          <div>
            <p class="bea-admin-recovery__kicker">Sources</p>
            <h2>Sauvegardes disponibles</h2>
          </div>
          <span class="bea-admin-recovery__count">{{ items().length }} dispo.</span>
        </div>
        @if (items().length === 0) {
          <p class="bea-admin-panel__empty">Aucune sauvegarde restaurable pour le moment.</p>
        } @else {
          <div class="bea-admin-panel__scroll">
            <table class="bea-admin-table bea-admin-recovery__table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Niveau</th>
                  <th>Cible</th>
                  <th>Statut</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (row of items(); track row.id) {
                  <tr>
                    <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    <td>
                      <span class="bea-admin-backups__level">{{ row.level }}</span>
                    </td>
                    <td>{{ row.label || row.module_code || row.espace_code || 'BEA-DIGITAL' }}</td>
                    <td>
                      <span class="bea-admin-backups__status" [attr.data-status]="row.status">
                        {{ row.status }}
                      </span>
                    </td>
                    <td class="bea-admin-recovery__actions">
                      @if (row.status === 'success' && row.level !== 'global') {
                        <button
                          type="button"
                          class="bea-admin-btn bea-admin-recovery__restore"
                          (click)="restore(row)"
                        >
                          Restaurer
                        </button>
                      } @else if (row.level === 'global') {
                        <span class="bea-admin-recovery__hint">Manuel (scripts)</span>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </section>

      <section class="bea-admin-panel bea-admin-recovery__card bea-admin-recovery__history">
        <div class="bea-admin-recovery__card-head">
          <div>
            <p class="bea-admin-recovery__kicker">Journal</p>
            <h2>Historique recovery</h2>
          </div>
        </div>
        @if (restores().length === 0) {
          <p class="bea-admin-panel__empty">Aucune restauration enregistrée pour l’instant.</p>
        } @else {
          <div class="bea-admin-panel__scroll">
            <table class="bea-admin-table bea-admin-recovery__table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Niveau</th>
                  <th>Module</th>
                  <th>Statut</th>
                  <th>Backup sécurité</th>
                </tr>
              </thead>
              <tbody>
                @for (r of restores(); track r.id) {
                  <tr>
                    <td>{{ r.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    <td>
                      <span class="bea-admin-backups__level">{{ r.level }}</span>
                    </td>
                    <td>{{ r.module_code || '—' }}</td>
                    <td>
                      <span class="bea-admin-backups__status" [attr.data-status]="r.status">
                        {{ r.status }}
                      </span>
                    </td>
                    <td class="bea-admin-recovery__mono">{{ r.safety_backup_id || '—' }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </section>
    </section>
  `,
})
export class CoreAdminRecoveryComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialog = inject(BeaAdminDialogService);
  readonly items = signal<BackupRow[]>([]);
  readonly restores = signal<
    {
      id: string;
      level: string;
      module_code?: string;
      status: string;
      safety_backup_id?: string;
      created_at?: string;
    }[]
  >([]);
  readonly erreur = signal('');
  readonly message = signal('');

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.api.get<{ backups: BackupRow[]; restores: any[] }>('/plateforme/admin/recovery').subscribe({
      next: (res) => {
        this.items.set(res.backups.filter((b) => b.status === 'success'));
        this.restores.set(res.restores);
      },
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Recovery indisponible')),
    });
  }

  async restore(row: BackupRow): Promise<void> {
    const ok = await this.dialog.confirm({
      title: '⚠ Restauration',
      message:
        `Restaurer « ${row.label || row.module_code} » (${row.created_at}) ?\n` +
        `Un backup de sécurité sera créé d'abord. Les tables CORE ne seront pas écrasées.\n` +
        `Dépendances partagées (users, agences, …) doivent déjà être cohérentes.`,
      confirmLabel: 'Confirmer la restauration',
      cancelLabel: 'Annuler',
      tone: 'danger',
    });
    if (!ok) return;
    this.erreur.set('');
    this.message.set('');
    this.api
      .post(`/plateforme/admin/recovery/${row.id}`, { acknowledge_dependencies: true })
      .subscribe({
        next: () => {
          this.message.set('Recovery terminé avec succès.');
          this.reload();
          void this.dialog.success(
            `Restauration de « ${row.label || row.module_code || 'BEA-DIGITAL'} » terminée.`,
            'Recovery effectué',
          );
        },
        error: (err) => {
          const msg = coreAdminOpsError(err, 'Échec recovery');
          this.erreur.set(msg);
          void this.dialog.error(msg, 'Recovery impossible');
        },
      });
  }
}

@Component({
  selector: 'bea-core-admin-supervision',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash bea-admin-supervis">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Supervision</h1>
          <p>État opérationnel de BEA-DIGITAL — sans stack de monitoring externe.</p>
        </div>
      </header>
      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (data(); as d) {
        <div
          class="bea-admin-supervis__banner"
          [class.bea-admin-supervis__banner--ok]="allOk(d)"
          [class.bea-admin-supervis__banner--warn]="!allOk(d)"
        >
          <span class="bea-admin-supervis__banner-glow" aria-hidden="true"></span>
          <div class="bea-admin-supervis__banner-icon" aria-hidden="true">
            <bea-admin-icon [name]="allOk(d) ? 'verified' : 'warning'" />
          </div>
          <div class="bea-admin-supervis__banner-copy">
            <p class="bea-admin-supervis__banner-kicker">État plateforme</p>
            <h2>{{ allOk(d) ? 'Tout est opérationnel' : 'Points d’attention détectés' }}</h2>
            <p>
              {{ okCount(d) }}/{{ healthKeys.length }} services OK
              @if (d.app_env) {
                · env {{ d.app_env }}
              }
            </p>
          </div>
        </div>

        <div class="bea-admin-supervis__grid">
          @for (key of healthKeys; track key; let i = $index) {
            <article
              class="bea-admin-supervis__tile"
              [class.bea-admin-supervis__tile--ok]="d[key]?.ok"
              [class.bea-admin-supervis__tile--ko]="!d[key]?.ok"
              [style.--delay]="i * 55 + 'ms'"
            >
              <span
                class="bea-admin-health__dot"
                [class.bea-admin-health__dot--ok]="d[key]?.ok"
                [class.bea-admin-health__dot--ko]="!d[key]?.ok"
              ></span>
              <div class="bea-admin-supervis__tile-body">
                <span class="bea-admin-supervis__tile-label">{{ d[key]?.label || key }}</span>
                <strong>{{ d[key]?.ok ? 'Opérationnel' : 'Attention' }}</strong>
              </div>
              <bea-admin-icon class="bea-admin-supervis__tile-glyph" [name]="healthIcon(key)" />
            </article>
          }
        </div>

        <div class="bea-admin-panels bea-admin-panels--equal bea-admin-supervis__panels">
          <section class="bea-admin-panel bea-admin-supervis__card">
            <div class="bea-admin-supervis__card-head">
              <div>
                <p class="bea-admin-supervis__card-kicker">Continuité</p>
                <h2>Backup</h2>
              </div>
              <span
                class="bea-admin-supervis__pill"
                [class.bea-admin-supervis__pill--ok]="d.backup?.ok"
                [class.bea-admin-supervis__pill--ko]="!d.backup?.ok"
              >
                {{ d.backup?.ok ? 'OK' : 'Alerte' }}
              </span>
            </div>
            <p class="bea-admin-supervis__card-lead">
              @if (d.backup?.dernier; as b) {
                Dernier succès :
                <strong>{{ b.created_at | date: 'dd/MM/yyyy HH:mm' }}</strong>
                <span class="bea-admin-supervis__muted">({{ b.level }})</span>
              } @else {
                Aucun backup enregistré
              }
            </p>
            <a routerLink="/admin/backups" class="bea-admin-btn bea-admin-btn--ghost">
              Voir les sauvegardes
            </a>
          </section>

          <section class="bea-admin-panel bea-admin-supervis__card">
            <div class="bea-admin-supervis__card-head">
              <div>
                <p class="bea-admin-supervis__card-kicker">Organisation</p>
                <h2>Départements</h2>
              </div>
              <a routerLink="/admin/module-states" class="bea-admin-btn bea-admin-btn--ghost">
                État modules
              </a>
            </div>
            <ul class="bea-admin-supervis__deps">
              @for (dep of d.departements || []; track dep.code; let i = $index) {
                <li [style.--delay]="i * 45 + 'ms'">
                  <span class="bea-admin-supervis__dep-name">{{ dep.label }}</span>
                  <span
                    class="bea-admin-supervis__pill"
                    [class.bea-admin-supervis__pill--ok]="!dep.attention"
                    [class.bea-admin-supervis__pill--ko]="dep.attention"
                  >
                    {{ dep.attention ? 'Attention' : 'Opérationnel' }}
                  </span>
                </li>
              }
            </ul>
          </section>
        </div>
      }
    </section>
  `,
})
export class CoreAdminSupervisionComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly data = signal<any>(null);
  readonly erreur = signal('');
  readonly healthKeys = [
    'application',
    'api',
    'database',
    'authentication',
    'storage',
    'modules',
    'backup',
  ] as const;

  private readonly icons: Record<string, string> = {
    application: 'apps',
    api: 'api',
    database: 'storage',
    authentication: 'lock',
    storage: 'folder',
    modules: 'extension',
    backup: 'backup',
  };

  ngOnInit(): void {
    this.api.get('/plateforme/admin/supervision').subscribe({
      next: (d) => this.data.set(d),
      error: (err) => this.erreur.set(coreAdminOpsError(err, 'Supervision indisponible')),
    });
  }

  healthIcon(key: string): string {
    return this.icons[key] || 'monitor';
  }

  allOk(d: Record<string, { ok?: boolean }>): boolean {
    return this.healthKeys.every((key) => !!d[key]?.ok);
  }

  okCount(d: Record<string, { ok?: boolean }>): number {
    return this.healthKeys.filter((key) => !!d[key]?.ok).length;
  }
}

const STATUT_LABELS: Record<string, string> = {
  actif: 'Actif',
  developpement: 'En développement',
  mise_a_jour: 'Mise à jour',
  maintenance: 'Maintenance',
  suspendu: 'Suspendu',
  bloque: 'Bloqué',
  bientot: 'Bientôt disponible',
  archive: 'Archivé',
  inactif: 'Inactif',
};

@Component({
  selector: 'bea-core-admin-module-states',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash bea-admin-mstates">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>État des modules</h1>
          <p>Statut opérationnel, message utilisateur et fenêtre de maintenance.</p>
        </div>
        <div class="bea-admin-users__head-actions">
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/maintenance">Maintenance</a>
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/versions">Versions</a>
        </div>
      </header>
      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }

      @if (items().length) {
        <div class="bea-admin-mstates__summary">
          @for (row of summary(); track row.code) {
            <article class="bea-admin-mstates__chip" [attr.data-statut]="row.code">
              <strong>{{ row.count }}</strong>
              <span>{{ row.label }}</span>
            </article>
          }
        </div>
      }

      <div class="bea-admin-mstates__list">
        @for (m of items(); track m.id; let i = $index) {
          <section class="bea-admin-panel bea-admin-mstates__card" [style.--delay]="i * 45 + 'ms'">
            <div class="bea-admin-mstates__head">
              <div>
                <p class="bea-admin-mstates__kicker">{{ m.espace_label || 'Module' }}</p>
                <h2>{{ m.label }}</h2>
                <p class="bea-admin-mstates__meta">
                  Version {{ m.version || '—' }} · <code>{{ m.code }}</code>
                </p>
              </div>
              <span class="bea-admin-mstates__pill" [attr.data-statut]="m.statut">
                {{ statutLabel(m.statut) }}
              </span>
            </div>

            <div class="bea-admin-mstates__form">
              <label class="bea-admin-field">
                <span>Statut</span>
                <select [(ngModel)]="m.statut">
                  @for (s of statuts; track s) {
                    <option [value]="s">{{ statutLabel(s) }}</option>
                  }
                </select>
              </label>
              <label class="bea-admin-field bea-admin-mstates__message">
                <span>Message utilisateur</span>
                <textarea
                  rows="3"
                  [(ngModel)]="m.status_message"
                  placeholder="Affiché dans le popup d’accès si le module n’est pas actif"
                ></textarea>
              </label>
              <label class="bea-admin-mstates__check">
                <input type="checkbox" [(ngModel)]="m.admins_bypass_maintenance" />
                <span>Les administrateurs autorisés peuvent accéder pendant la maintenance</span>
              </label>
              <button
                type="button"
                class="bea-admin-btn bea-admin-mstates__submit"
                [disabled]="saving()"
                (click)="save(m)"
              >
                {{ saving() ? 'Enregistrement…' : 'Enregistrer' }}
              </button>
            </div>
          </section>
        }
      </div>
    </section>
  `,
})
export class CoreAdminModuleStatesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  readonly items = signal<ModuleState[]>([]);
  readonly erreur = signal('');
  readonly saving = signal(false);
  readonly statuts = STATUT_OPTIONS;

  ngOnInit(): void {
    this.api.get<{ items: ModuleState[] }>('/plateforme/admin/module-states').subscribe({
      next: (res) => this.items.set(res.items),
      error: (err) => {
        const msg = coreAdminOpsError(err, 'Impossible de charger les états');
        this.erreur.set(msg);
        void this.dialogs.error(msg);
      },
    });
  }

  statutLabel(code: string): string {
    return STATUT_LABELS[code] || code;
  }

  summary(): { code: string; label: string; count: number }[] {
    const counts = new Map<string, number>();
    for (const m of this.items()) {
      counts.set(m.statut, (counts.get(m.statut) || 0) + 1);
    }
    return [...counts.entries()]
      .map(([code, count]) => ({ code, count, label: this.statutLabel(code) }))
      .sort((a, b) => b.count - a.count);
  }

  async save(m: ModuleState): Promise<void> {
    if (this.saving()) return;
    const ok = await this.dialogs.confirm({
      title: 'Changer l’état du module',
      message:
        `Appliquer le statut « ${this.statutLabel(m.statut)} » au module « ${m.label} » ?\n` +
        `Les utilisateurs verront ce statut à l’entrée du module` +
        (m.status_message?.trim() ? ` avec le message défini.` : `.`),
      confirmLabel: 'Enregistrer',
      cancelLabel: 'Annuler',
      tone: m.statut === 'actif' ? 'success' : 'warn',
    });
    if (!ok) return;

    this.saving.set(true);
    this.erreur.set('');
    this.api
      .patch<ModuleState>(`/plateforme/admin/module-states/${m.id}`, {
        statut: m.statut,
        status_message: m.status_message,
        admins_bypass_maintenance: m.admins_bypass_maintenance,
        notify: true,
      })
      .subscribe({
        next: (updated) => {
          this.saving.set(false);
          this.items.update((list) => list.map((x) => (x.id === m.id ? { ...x, ...updated } : x)));
          void this.dialogs.success(
            `« ${updated.label} » est maintenant : ${this.statutLabel(updated.statut)}.`,
            'État mis à jour',
          );
        },
        error: (err) => {
          this.saving.set(false);
          const msg = coreAdminOpsError(err, 'Échec mise à jour statut');
          this.erreur.set(msg);
          void this.dialogs.error(msg, 'Enregistrement impossible');
        },
      });
  }
}

@Component({
  selector: 'bea-core-admin-versions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash bea-admin-versions">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Versions & déploiements</h1>
          <p>Historique des versions par module (pas un CI/CD — traçabilité opérationnelle).</p>
        </div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/module-states"
          >État des modules</a
        >
      </header>
      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }

      <section class="bea-admin-panel bea-admin-versions__card">
        <p class="bea-admin-versions__kicker">Cible</p>
        <h2>Module</h2>
        <label class="bea-admin-field">
          <span>Sélection</span>
          <select [(ngModel)]="selectedId" (ngModelChange)="loadVersions()">
            @for (m of modules(); track m.id) {
              <option [value]="m.id">{{ m.label }} ({{ m.version }})</option>
            }
          </select>
        </label>
      </section>

      <section class="bea-admin-panel bea-admin-versions__card">
        <p class="bea-admin-versions__kicker">Publication</p>
        <h2>Nouvelle version</h2>
        <div class="bea-admin-versions__form">
          <label class="bea-admin-field">
            <span>Version</span>
            <input [(ngModel)]="version" placeholder="1.4.2" />
          </label>
          <label class="bea-admin-field">
            <span>Notes</span>
            <textarea rows="3" [(ngModel)]="notes"></textarea>
          </label>
          <label class="bea-admin-versions__check">
            <input type="checkbox" [(ngModel)]="createBackup" />
            <span>Créer une sauvegarde module avant</span>
          </label>
          <button
            type="button"
            class="bea-admin-btn bea-admin-versions__submit"
            [disabled]="saving()"
            (click)="publish()"
          >
            {{ saving() ? 'Enregistrement…' : 'Enregistrer' }}
          </button>
        </div>
      </section>

      <section class="bea-admin-panel bea-admin-versions__card">
        <div class="bea-admin-versions__history-head">
          <div>
            <p class="bea-admin-versions__kicker">Journal</p>
            <h2>Historique</h2>
          </div>
        </div>
        @if (versions().length === 0) {
          <p class="bea-admin-panel__empty">Aucune version enregistrée pour ce module.</p>
        } @else {
          <ul class="bea-admin-versions__list">
            @for (v of versions(); track v.id; let i = $index) {
              <li [style.--delay]="i * 40 + 'ms'">
                <div class="bea-admin-versions__ver">
                  <strong>{{ v.version }}</strong>
                  <span>{{ v.created_at | date: 'dd/MM/yyyy HH:mm' }}</span>
                </div>
                @if (v.notes) {
                  <p>{{ v.notes }}</p>
                }
              </li>
            }
          </ul>
        }
      </section>
    </section>
  `,
})
export class CoreAdminVersionsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  readonly modules = signal<ModuleState[]>([]);
  readonly versions = signal<{ id: string; version: string; notes: string; created_at?: string }[]>(
    [],
  );
  readonly erreur = signal('');
  readonly saving = signal(false);
  selectedId = '';
  version = '';
  notes = '';
  createBackup = true;

  ngOnInit(): void {
    this.api.get<{ items: ModuleState[] }>('/plateforme/admin/module-states').subscribe({
      next: (res) => {
        this.modules.set(res.items);
        if (res.items[0] && !this.selectedId) {
          this.selectedId = res.items[0].id;
          this.loadVersions();
        } else if (this.selectedId) {
          this.loadVersions();
        }
      },
      error: (err) => {
        const msg = coreAdminOpsError(err, 'Modules indisponibles');
        this.erreur.set(msg);
        void this.dialogs.error(msg);
      },
    });
  }

  loadVersions(): void {
    if (!this.selectedId) return;
    this.api.get<{ items: any[] }>(`/plateforme/admin/versions/${this.selectedId}`).subscribe({
      next: (res) => this.versions.set(res.items),
      error: (err) => {
        const msg = coreAdminOpsError(err, 'Versions indisponibles');
        this.erreur.set(msg);
        void this.dialogs.error(msg);
      },
    });
  }

  async publish(): Promise<void> {
    if (this.saving()) return;
    if (!this.selectedId || !this.version.trim()) {
      await this.dialogs.error('Indiquez un numéro de version.', 'Validation');
      return;
    }
    const mod = this.modules().find((m) => m.id === this.selectedId);
    const ok = await this.dialogs.confirm({
      title: 'Enregistrer une version',
      message:
        `Passer « ${mod?.label || 'module'} » de ${mod?.version || '?'} à ${this.version.trim()} ?` +
        (this.createBackup ? `\nUne sauvegarde du module sera créée avant.` : ''),
      confirmLabel: 'Enregistrer',
      cancelLabel: 'Annuler',
    });
    if (!ok) return;

    this.saving.set(true);
    this.erreur.set('');
    const version = this.version.trim();
    this.api
      .post(`/plateforme/admin/versions/${this.selectedId}`, {
        version,
        notes: this.notes,
        set_current: true,
        create_backup: this.createBackup,
        activate_maintenance: false,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.version = '';
          this.notes = '';
          this.loadVersions();
          this.api.get<{ items: ModuleState[] }>('/plateforme/admin/module-states').subscribe({
            next: (res) => this.modules.set(res.items),
          });
          void this.dialogs.success(
            `Version ${version} enregistrée pour « ${mod?.label || 'module'} ».`,
            'Version mise à jour',
          );
        },
        error: (err) => {
          this.saving.set(false);
          const msg = coreAdminOpsError(err, 'Échec enregistrement version');
          this.erreur.set(msg);
          void this.dialogs.error(msg, 'Enregistrement impossible');
        },
      });
  }
}
