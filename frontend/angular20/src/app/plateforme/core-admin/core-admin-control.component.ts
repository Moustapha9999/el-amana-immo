import { DatePipe } from '@angular/common';
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
import { feedbackSignal } from '../../core/feedback/feedback-signal';

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
  selector: 'bea-core-admin-supervision',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash bea-admin-supervis">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Supervision</h1>
          <p>État opérationnel de BEA-DIGITAL — sans stack de monitoring externe.</p>
        </div>
        <button type="button" class="bea-admin-btn bea-admin-btn--refresh" (click)="reload()">
          <bea-admin-icon name="refresh" />
          Actualiser
        </button>
      </header>
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
            <a routerLink="/admin/sauvegardes" class="bea-admin-btn bea-admin-btn--ghost">
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
  readonly erreur = feedbackSignal('error', '');
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
    this.reload();
  }

  reload(): void {
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
  imports: [FormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash bea-admin-mstates">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>État des modules</h1>
          <p>Statut opérationnel, message utilisateur et fenêtre de maintenance.</p>
        </div>
        <div class="bea-admin-users__head-actions">
          <button type="button" class="bea-admin-btn bea-admin-btn--refresh" (click)="reload()">
            <bea-admin-icon name="refresh" />
            Actualiser
          </button>
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/maintenance">Maintenance</a>
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/versions">Versions</a>
        </div>
      </header>

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
  readonly erreur = feedbackSignal('error', '');
  readonly saving = signal(false);
  readonly statuts = STATUT_OPTIONS;

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
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
  readonly erreur = feedbackSignal('error', '');
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
