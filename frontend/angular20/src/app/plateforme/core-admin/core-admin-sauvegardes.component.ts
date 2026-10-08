import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  Injectable,
  OnDestroy,
  OnInit,
  WritableSignal,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink, RouterLinkActive } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  SR_API,
  SR_LEVELS,
  SrBackup,
  SrBackupPreview,
  SrCatalogue,
  SrDashboard,
  SrHistoryItem,
  SrLevel,
  SrRestore,
  SrRestorePreview,
  SrVerifyResult,
  srArtifactLabel,
  srBackupTypeLabel,
  srBytes,
  srDuration,
  srPermissions,
  srSaveBlob,
  srStatusLabel,
  srUser,
} from './core-admin-sauvegardes.models';

const TZ = 'Africa/Nouakchott';

const SR_TABS = [
  { label: 'Vue générale', path: '/admin/sauvegardes', icon: 'insights' },
  { label: 'Sauvegarde', path: '/admin/sauvegardes/sauvegarde', icon: 'backup' },
  { label: 'Recovery', path: '/admin/sauvegardes/recovery', icon: 'settings_backup_restore' },
  { label: 'Historique', path: '/admin/sauvegardes/historique', icon: 'manage_history' },
];

function srBackupLabel(b: { type: string; perimetre: string; created_at?: string | null }): string {
  const when = b.created_at
    ? new Date(b.created_at).toLocaleString('fr-FR', { timeZone: TZ, dateStyle: 'short', timeStyle: 'short' })
    : '';
  return [b.type, b.perimetre, when].filter(Boolean).join(' — ');
}

function levelLabel(level: string | null | undefined): string {
  return SR_LEVELS.find((l) => l.value === level)?.label ?? level ?? '—';
}

interface SrBulkDeleteResult {
  deleted: string[];
  failed: { id: string; code?: string | null; message?: string | null }[];
}

/** Actions partagées (vérification, téléchargement, suppression) — succès affiché après réponse backend. */
@Injectable({ providedIn: 'root' })
export class SrActionsService {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(BeaAdminDialogService);

  /** Supprime une ou plusieurs sauvegardes (fichiers + entrée). Résout `true` si au moins une est supprimée. */
  async remove(items: { id: string; label: string }[], busy?: WritableSignal<boolean>): Promise<boolean> {
    if (!items.length) return false;
    const many = items.length > 1;
    const list = items
      .slice(0, 8)
      .map((i) => `- ${i.label}`)
      .join('\n');
    const ok = await this.dialog.confirm({
      title: many ? `Supprimer ${items.length} sauvegardes` : 'Supprimer la sauvegarde',
      message:
        `${list}${items.length > 8 ? `\n… et ${items.length - 8} autre(s)` : ''}\n\n` +
        'Les fichiers (dump, archives) sont effacés du disque : action irréversible. ' +
        'L’historique des restaurations est conservé.',
      confirmLabel: 'Supprimer',
      tone: 'danger',
    });
    if (!ok) return false;
    return new Promise<boolean>((resolve) => {
      this.feedback
        .run(() => this.api.post<SrBulkDeleteResult>(`${SR_API}/backups/bulk-delete`, { ids: items.map((i) => i.id) }), {
          loading: 'Suppression…',
          busy,
          retry: false,
          errorTitle: 'Suppression impossible',
          success: (r) =>
            r.deleted.length
              ? {
                  title: r.deleted.length > 1 ? 'Sauvegardes supprimées' : 'Sauvegarde supprimée',
                  message: `${r.deleted.length} sauvegarde(s) et leurs fichiers supprimés.`,
                }
              : null,
        })
        .subscribe({
          next: (r) => {
            if (r.failed.length) {
              this.feedback.error({
                title: `${r.failed.length} sauvegarde(s) non supprimée(s)`,
                message: r.failed.map((f) => f.message || f.code || f.id).join('\n'),
                duration: 0,
              });
            }
            resolve(r.deleted.length > 0);
          },
          error: () => resolve(false),
          complete: () => resolve(false),
        });
    });
  }

  verify(id: string, busy?: WritableSignal<boolean>): Observable<SrVerifyResult> {
    return this.feedback
      .run(() => this.api.post<SrVerifyResult>(`${SR_API}/backups/${id}/verify`, {}), {
        loading: 'Vérification de l’intégrité…',
        busy,
        retry: false,
        errorTitle: 'Vérification impossible',
        success: (r) =>
          r.integrity_status === 'ok'
            ? {
                title: 'Intégrité vérifiée',
                message: `${r.checks.length} contrôle(s) conforme(s) : empreintes SHA-256 et lisibilité des artefacts.`,
              }
            : null,
      })
      .pipe(
        tap((r) => {
          if (r.integrity_status === 'ok') return;
          this.feedback.error({
            title: 'Intégrité compromise',
            message: r.checks
              .filter((c) => !c.ok)
              .map((c) => `${srArtifactLabel(c.artifact)} : ${c.detail}`)
              .join('\n'),
            duration: 0,
          });
        }),
      );
  }

  download(id: string, type: string, busy?: WritableSignal<boolean>): Observable<Blob> {
    return this.feedback
      .run(() => this.api.download(`${SR_API}/backups/${id}/download`), {
        loading: 'Préparation du téléchargement…',
        busy,
        retry: false,
        errorTitle: 'Téléchargement impossible',
        success: { title: 'Téléchargement prêt', message: 'Archive transmise au navigateur.' },
      })
      .pipe(
        tap((blob) => {
          const ext = blob.type.includes('tar') ? 'tar' : 'dump';
          srSaveBlob(blob, `bea-sauvegarde-${type.toLowerCase()}-${id.slice(0, 8)}.${ext}`);
        }),
      );
  }
}

/* ------------------------------------------------------------------ */
/* Briques communes                                                    */
/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-sr-header',
  imports: [RouterLink, RouterLinkActive, CoreAdminIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="bea-admin-dash__head bea-sr-head">
      <div>
        <p class="bea-sr-head__kicker">Sauvegardes &amp; Recovery</p>
        <h1>{{ title() }}</h1>
        <p>{{ subtitle() }}</p>
      </div>
      <ng-content />
    </header>
    <nav class="bea-sr-tabs" aria-label="Sauvegardes & Recovery">
      @for (t of tabs; track t.path) {
        <a
          class="bea-sr-tabs__item"
          [routerLink]="t.path"
          routerLinkActive="bea-sr-tabs__item--on"
          [routerLinkActiveOptions]="{ exact: true }"
        >
          <bea-admin-icon [name]="t.icon" />
          {{ t.label }}
        </a>
      }
    </nav>
  `,
})
export class SrHeaderComponent {
  readonly title = input.required<string>();
  readonly subtitle = input<string>('');
  readonly tabs = SR_TABS;
}

@Component({
  selector: 'bea-sr-progress',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-sr-progress" role="alertdialog" aria-modal="true" aria-live="polite" [attr.aria-label]="title()">
      <div class="bea-sr-progress__card" [attr.data-tone]="tone()">
        <div class="bea-sr-progress__spinner" aria-hidden="true"></div>
        <h2>{{ title() }}</h2>
        <p class="bea-sr-progress__elapsed">Temps écoulé : {{ elapsed() }}</p>
        <div class="bea-sr-progress__bar" aria-hidden="true"><span></span></div>
        @if (steps().length) {
          <ol class="bea-sr-progress__steps">
            @for (s of steps(); track s) {
              <li>{{ s }}</li>
            }
          </ol>
        }
        <p class="bea-sr-progress__hint">
          Ne fermez pas cette page. L’opération est exécutée côté serveur et sera tracée dans l’historique et l’audit.
        </p>
      </div>
    </div>
  `,
})
export class SrProgressComponent implements OnInit, OnDestroy {
  readonly title = input.required<string>();
  readonly steps = input<string[]>([]);
  readonly tone = input<'primary' | 'danger'>('primary');
  readonly elapsed = signal('0 s');
  private readonly started = Date.now();
  private timer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.timer = setInterval(() => {
      const s = Math.floor((Date.now() - this.started) / 1000);
      this.elapsed.set(s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`);
    }, 1000);
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  @HostListener('window:beforeunload', ['$event'])
  onUnload(event: BeforeUnloadEvent): void {
    event.preventDefault();
    event.returnValue = '';
  }
}

/** Fiche détaillée d'une sauvegarde ou d'une restauration (modale). */
@Component({
  selector: 'bea-sr-details',
  imports: [DatePipe, DecimalPipe, CoreAdminIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-sr-modal" role="dialog" aria-modal="true" aria-labelledby="bea-sr-details-title" (click)="close()">
      <div class="bea-sr-modal__card" (click)="$event.stopPropagation()">
        <header class="bea-sr-modal__head">
          <div>
            <p class="bea-sr-head__kicker">{{ current().kind === 'backup' ? 'Sauvegarde' : 'Restauration' }}</p>
            <h2 id="bea-sr-details-title">
              @if (backup(); as b) {
                {{ b.perimetre }}
              } @else if (restore(); as r) {
                {{ r.perimetre }}
              } @else {
                Chargement…
              }
            </h2>
          </div>
          <button type="button" class="bea-sr-iconbtn" aria-label="Fermer" title="Fermer" (click)="close()">
            <bea-admin-icon name="close" />
          </button>
        </header>

        <div class="bea-sr-modal__body">
          @if (loading()) {
            <p class="bea-admin-dash__loading">Chargement…</p>
          } @else if (error()) {
            <p class="bea-sr-alert" data-tone="danger">{{ error() }}</p>
          } @else if (backup(); as b) {
            <div class="bea-sr-badges">
              <span class="bea-sr-badge" [attr.data-level]="b.level">{{ b.type }}</span>
              <em class="bea-sr-status" [attr.data-status]="b.status">{{ status(b.status) }}</em>
              @if (b.integrity_status) {
                <em class="bea-sr-status" [attr.data-status]="b.integrity_status === 'ok' ? 'success' : 'failed'">
                  Intégrité {{ b.integrity_status === 'ok' ? 'OK' : 'KO' }}
                </em>
              }
            </div>
            <dl class="bea-sr-summary">
              <div><dt>Identifiant</dt><dd class="bea-sr-mono">{{ b.id }}</dd></div>
              <div><dt>Nature</dt><dd>{{ backupType(b.backup_type) }}</dd></div>
              <div><dt>Date et heure</dt><dd>{{ b.created_at | date: 'dd/MM/yyyy HH:mm:ss' : tz }}</dd></div>
              <div><dt>Durée</dt><dd>{{ duration(b.duration_ms) }}</dd></div>
              <div><dt>Taille</dt><dd>{{ bytes(b.size_bytes) }}</dd></div>
              <div><dt>Administrateur</dt><dd>{{ user(b.administrateur) }}</dd></div>
              <div><dt>Adresse IP</dt><dd class="bea-sr-mono">{{ b.ip_address || '—' }}</dd></div>
              <div><dt>Contenu</dt><dd>
                {{ b.tables_count }} table(s)
                @if (b.rows_total != null) { · {{ b.rows_total | number: '1.0-0' : 'fr' }} ligne(s) }
                @if (b.ged_documents) { · {{ b.ged_documents }} doc. GED }
                @if (b.files_count) { · {{ b.files_count }} fichier(s) }
              </dd></div>
              @if (b.modules?.length) {
                <div class="bea-sr-summary__wide"><dt>Modules</dt><dd>{{ b.modules!.join(', ') }}</dd></div>
              }
              <div class="bea-sr-summary__wide"><dt>Emplacement</dt><dd class="bea-sr-mono">{{ b.emplacement || '—' }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Checksum SHA-256</dt><dd class="bea-sr-mono">{{ b.checksum_sha256 || '—' }}</dd></div>
              <div><dt>Révision schéma</dt><dd class="bea-sr-mono">{{ b.alembic_revision || '—' }}</dd></div>
              <div><dt>Format</dt><dd class="bea-sr-mono">{{ b.format }}</dd></div>
              @if (b.integrity_checked_at) {
                <div class="bea-sr-summary__wide">
                  <dt>Dernière vérification</dt>
                  <dd>{{ b.integrity_checked_at | date: 'dd/MM/yyyy HH:mm' : tz }} — {{ b.integrity_detail || '' }}</dd>
                </div>
              }
              @if (b.error_message) {
                <div class="bea-sr-summary__wide"><dt>Message</dt><dd class="bea-sr-error">{{ b.error_message }}</dd></div>
              }
            </dl>

            @if (artifacts().length) {
              <h3 class="bea-sr-subtitle">Artefacts</h3>
              <div class="bea-admin-table-wrap">
                <table class="bea-admin-table bea-sr-plain">
                  <thead><tr><th>Élément</th><th>Fichier</th><th>Taille</th><th>SHA-256</th></tr></thead>
                  <tbody>
                    @for (a of artifacts(); track a.key) {
                      <tr>
                        <td>{{ artifactLabel(a.key) }}</td>
                        <td class="bea-sr-mono">{{ a.file }}</td>
                        <td>{{ bytes(a.bytes) }}</td>
                        <td class="bea-sr-mono bea-sr-hash" [title]="a.sha256">{{ a.sha256 }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }

            @if (b.restores?.length) {
              <h3 class="bea-sr-subtitle">Restaurations depuis cette sauvegarde</h3>
              <ul class="bea-sr-list">
                @for (r of b.restores!; track r.id) {
                  <li>
                    <button type="button" class="bea-sr-list__row" (click)="open('restore', r.id)">
                      <em class="bea-sr-status" [attr.data-status]="r.status">{{ status(r.status) }}</em>
                      <span>{{ r.created_at | date: 'dd/MM/yyyy HH:mm' : tz }}</span>
                      <span>{{ user(r.administrateur) }}</span>
                    </button>
                  </li>
                }
              </ul>
            }
          } @else if (restore(); as r) {
            <div class="bea-sr-badges">
              <span class="bea-sr-badge" [attr.data-level]="r.level">{{ r.type }}</span>
              <em class="bea-sr-status" [attr.data-status]="r.status">{{ status(r.status) }}</em>
            </div>
            <dl class="bea-sr-summary">
              <div><dt>Identifiant</dt><dd class="bea-sr-mono">{{ r.id }}</dd></div>
              <div><dt>Date et heure</dt><dd>{{ r.created_at | date: 'dd/MM/yyyy HH:mm:ss' : tz }}</dd></div>
              <div><dt>Durée</dt><dd>{{ duration(r.duration_ms) }}</dd></div>
              <div><dt>Administrateur</dt><dd>{{ user(r.administrateur) }}</dd></div>
              <div><dt>Adresse IP</dt><dd class="bea-sr-mono">{{ r.ip_address || '—' }}</dd></div>
              <div><dt>Tables restaurées</dt><dd>{{ r.details?.tables_count ?? r.details?.tables?.length ?? '—' }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Motif</dt><dd>{{ r.reason || '—' }}</dd></div>
              <div class="bea-sr-summary__wide">
                <dt>Sauvegarde source</dt>
                <dd>
                  @if (r.backup_id) {
                    <button type="button" class="bea-admin-table__link bea-sr-mono" (click)="open('backup', r.backup_id)">{{ r.backup_id }}</button>
                  } @else if (r.deleted_backup; as d) {
                    Supprimée le {{ d.deleted_at | date: 'dd/MM/yyyy HH:mm' : tz }}
                    <span class="bea-sr-mono">({{ d.label || d.id }})</span>
                  } @else {
                    Supprimée
                  }
                </dd>
              </div>
              <div class="bea-sr-summary__wide">
                <dt>Sauvegarde de sécurité</dt>
                <dd>
                  @if (r.safety_backup_id) {
                    <button type="button" class="bea-admin-table__link bea-sr-mono" (click)="open('backup', r.safety_backup_id!)">{{ r.safety_backup_id }}</button>
                  } @else {
                    —
                  }
                </dd>
              </div>
              @if (r.options?.include_security) {
                <div class="bea-sr-summary__wide"><dt>Option</dt><dd>Plan de sécurité inclus (utilisateurs, rôles, sessions)</dd></div>
              }
              @if (r.details?.preserved_tables?.length) {
                <div class="bea-sr-summary__wide"><dt>Tables préservées</dt><dd>{{ r.details!.preserved_tables!.join(', ') }}</dd></div>
              }
              @if (r.details?.file_targets?.length) {
                <div class="bea-sr-summary__wide"><dt>Fichiers restaurés</dt><dd class="bea-sr-mono">{{ r.details!.file_targets!.join(', ') }}</dd></div>
              }
              @if (r.dependency_warning) {
                <div class="bea-sr-summary__wide"><dt>Dépendances</dt><dd>{{ r.dependency_warning }}</dd></div>
              }
              @if (r.error_message) {
                <div class="bea-sr-summary__wide"><dt>Message</dt><dd class="bea-sr-error">{{ r.error_message }}</dd></div>
              }
            </dl>
            @if (r.details?.tables?.length) {
              <details class="bea-sr-fold">
                <summary>Voir les {{ r.details!.tables!.length }} table(s) restaurée(s)</summary>
                <p class="bea-sr-mono">{{ r.details!.tables!.join(', ') }}</p>
              </details>
            }
          }
        </div>

        <footer class="bea-sr-modal__foot">
          @if (history().length > 1) {
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="back()">
              <bea-admin-icon name="arrow_back" /> Retour
            </button>
          }
          <span class="bea-sr-spacer"></span>
          @if (backup(); as b) {
            @if (b.status === 'success') {
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="busy()" (click)="verify(b)">
                <bea-admin-icon name="verified" /> Vérifier l’intégrité
              </button>
              @if (perms.download()) {
                <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="busy()" (click)="download(b)">
                  <bea-admin-icon name="download" /> Télécharger
                </button>
              }
              @if (perms.recoveryExec() && b.restorable) {
                <button type="button" class="bea-admin-btn bea-admin-btn--danger" (click)="goRestore(b.id)">
                  <bea-admin-icon name="settings_backup_restore" /> Restaurer
                </button>
              }
            }
            @if (perms.delete() && b.status !== 'running') {
              <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="busy()" (click)="remove(b)">
                <bea-admin-icon name="delete" /> Supprimer
              </button>
            }
          }
          <button type="button" class="bea-admin-btn" (click)="close()">Fermer</button>
        </footer>
      </div>
    </div>
  `,
})
export class SrDetailsComponent implements OnInit {
  readonly kind = input.required<'backup' | 'restore'>();
  readonly itemId = input.required<string>();
  readonly closed = output<void>();
  readonly changed = output<void>();

  private readonly api = inject(ApiService);
  private readonly actions = inject(SrActionsService);
  private readonly router = inject(Router);
  readonly perms = srPermissions();
  readonly tz = TZ;

  readonly history = signal<{ kind: 'backup' | 'restore'; id: string }[]>([]);
  readonly current = computed(() => this.history()[this.history().length - 1] ?? { kind: this.kind(), id: this.itemId() });
  readonly backup = signal<SrBackup | null>(null);
  readonly restore = signal<SrRestore | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);
  readonly artifacts = computed(() =>
    Object.entries(this.backup()?.artifacts ?? {}).map(([key, a]) => ({ key, ...a })),
  );

  readonly status = srStatusLabel;
  readonly backupType = srBackupTypeLabel;
  readonly bytes = srBytes;
  readonly duration = srDuration;
  readonly user = srUser;
  readonly artifactLabel = srArtifactLabel;

  ngOnInit(): void {
    this.open(this.kind(), this.itemId());
  }

  @HostListener('document:keydown.escape')
  close(): void {
    this.closed.emit();
  }

  open(kind: 'backup' | 'restore', id: string): void {
    this.history.update((h) => [...h, { kind, id }]);
    this.load();
  }

  back(): void {
    this.history.update((h) => h.slice(0, -1));
    this.load();
  }

  private load(): void {
    const { kind, id } = this.current();
    this.loading.set(true);
    this.error.set(null);
    this.backup.set(null);
    this.restore.set(null);
    const url = kind === 'backup' ? `${SR_API}/backups/${id}` : `${SR_API}/recovery/restores/${id}`;
    this.api.get<SrBackup | SrRestore>(url).subscribe({
      next: (row) => {
        if (kind === 'backup') this.backup.set(row as SrBackup);
        else this.restore.set(row as SrRestore);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Élément introuvable ou accès refusé.');
        this.loading.set(false);
      },
    });
  }

  verify(b: SrBackup): void {
    this.actions.verify(b.id, this.busy).subscribe(() => {
      this.load();
      this.changed.emit();
    });
  }

  download(b: SrBackup): void {
    this.actions.download(b.id, b.type, this.busy).subscribe();
  }

  async remove(b: SrBackup): Promise<void> {
    if (await this.actions.remove([{ id: b.id, label: srBackupLabel(b) }], this.busy)) {
      this.changed.emit();
      this.closed.emit();
    }
  }

  goRestore(id: string): void {
    this.closed.emit();
    void this.router.navigate(['/admin/sauvegardes/recovery'], { queryParams: { backup: id } });
  }
}

/** Sélecteur de périmètre : niveau → département → module (listes dynamiques). */
@Component({
  selector: 'bea-sr-scope',
  imports: [CoreAdminIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bea-sr-levels" role="radiogroup" aria-label="Niveau">
      @for (l of levels; track l.value) {
        <button
          type="button"
          role="radio"
          class="bea-sr-level"
          [class.bea-sr-level--on]="level() === l.value"
          [attr.aria-checked]="level() === l.value"
          [disabled]="disabled()"
          (click)="setLevel(l.value)"
        >
          <span class="bea-sr-level__icon"><bea-admin-icon [name]="l.icon" /></span>
          <span class="bea-sr-level__copy">
            <strong>{{ l.label }}</strong>
            <small>{{ l.hint }}</small>
          </span>
        </button>
      }
    </div>

    @if (level() !== 'global') {
      <div class="bea-sr-selects">
        <label class="bea-admin-field">
          <span>Département</span>
          <select [disabled]="disabled()" (change)="setEspace($any($event.target).value)">
            <option value="" [selected]="!espaceCode()">— Choisir un département —</option>
            @for (d of catalogue()?.departements ?? []; track d.code) {
              <option [value]="d.code" [selected]="d.code === espaceCode()">
                {{ d.label }} ({{ d.modules_count }} module(s))
              </option>
            }
          </select>
        </label>
        @if (level() === 'module') {
          <label class="bea-admin-field">
            <span>Module</span>
            <select [disabled]="disabled() || !espaceCode()" (change)="setModule($any($event.target).value)">
              <option value="" [selected]="!moduleCode()">
                {{ espaceCode() ? '— Choisir un module —' : 'Choisissez d’abord un département' }}
              </option>
              @for (m of modules(); track m.code) {
                <option [value]="m.code" [selected]="m.code === moduleCode()" [disabled]="!m.backupable">
                  {{ m.label }}{{ m.backupable ? '' : ' — aucune donnée propre' }}
                </option>
              }
            </select>
          </label>
        }
      </div>
      @if (level() === 'departement' && espaceCode()) {
        <div class="bea-sr-chips" aria-label="Modules identifiés automatiquement">
          <span class="bea-sr-chips__label">Modules inclus automatiquement :</span>
          @for (m of modules(); track m.code) {
            <span class="bea-sr-chip" [attr.data-off]="!m.backupable" [title]="m.backupable ? m.tables_count + ' table(s)' : 'Aucune donnée propre'">
              {{ m.label }}
            </span>
          } @empty {
            <span class="bea-sr-chip" data-off="true">Aucun module</span>
          }
        </div>
      }
    }
  `,
})
export class SrScopeComponent {
  readonly catalogue = input<SrCatalogue | null>(null);
  readonly level = input.required<SrLevel>();
  readonly espaceCode = input<string>('');
  readonly moduleCode = input<string>('');
  readonly disabled = input(false);
  readonly scopeChange = output<{ level: SrLevel; espace: string; module: string }>();
  readonly levels = SR_LEVELS;

  readonly modules = computed(
    () => this.catalogue()?.departements.find((d) => d.code === this.espaceCode())?.modules ?? [],
  );

  setLevel(level: SrLevel): void {
    this.scopeChange.emit({ level, espace: level === 'global' ? '' : this.espaceCode(), module: '' });
  }

  setEspace(espace: string): void {
    this.scopeChange.emit({ level: this.level(), espace, module: '' });
  }

  setModule(module: string): void {
    this.scopeChange.emit({ level: this.level(), espace: this.espaceCode(), module });
  }
}

function scopeReady(level: SrLevel, espace: string, module: string): boolean {
  return level === 'global' || (level === 'departement' && !!espace) || (level === 'module' && !!espace && !!module);
}

/* ------------------------------------------------------------------ */
/* Vue générale                                                        */
/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-core-admin-sauvegardes-overview',
  imports: [DatePipe, RouterLink, CoreAdminIconComponent, SrHeaderComponent, SrDetailsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr">
      <bea-sr-header title="Vue générale" subtitle="Continuité de service : sauvegardes globales, par département et par module, restaurations et contrôles d’intégrité.">
        <button type="button" class="bea-admin-btn bea-admin-btn--refresh" [disabled]="loading()" (click)="load()">
          <bea-admin-icon name="refresh" /> Actualiser
        </button>
      </bea-sr-header>

      @if (loading() && !dash()) {
        <p class="bea-admin-dash__loading">Chargement…</p>
      } @else if (dash(); as d) {
        <div class="bea-admin-kpis">
          <article class="bea-admin-kpi" data-tone="modules">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="task_alt" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Sauvegardes réussies</p>
              <p class="bea-admin-kpi__value">{{ d.success }} <small>/ {{ d.total }}</small></p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="org">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="public" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Dernière sauvegarde globale</p>
              <p class="bea-admin-kpi__value bea-sr-kpi-date">
                @if (d.derniere_globale; as g) {
                  {{ g.created_at | date: 'dd/MM/yyyy HH:mm' : tz }}
                } @else {
                  Aucune
                }
              </p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="sessions">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="settings_backup_restore" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Restaurations</p>
              <p class="bea-admin-kpi__value">{{ d.restores_success }} <small>/ {{ d.restores_total }}</small></p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="alert">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="error" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Erreurs</p>
              <p class="bea-admin-kpi__value">{{ d.failed + d.restores_failed + d.integrity_ko }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="actions">
            <span class="bea-admin-kpi__icon"><bea-admin-icon name="storage" /></span>
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Taille totale</p>
              <p class="bea-admin-kpi__value">{{ bytes(d.total_size_bytes) }}</p>
              @if (d.disk) {
                <p class="bea-sr-kpi-sub">{{ bytes(d.disk.free) }} libres sur {{ bytes(d.disk.total) }}</p>
              }
            </div>
          </article>
        </div>

        @if (perms.create() || perms.recoveryExec()) {
          <div class="bea-sr-quick">
            @if (perms.create()) {
              <a class="bea-admin-btn" routerLink="/admin/sauvegardes/sauvegarde">
                <bea-admin-icon name="backup" /> Nouvelle sauvegarde
              </a>
            }
            @if (perms.recoveryExec()) {
              <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/sauvegardes/recovery">
                <bea-admin-icon name="settings_backup_restore" /> Restaurer
              </a>
            }
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/sauvegardes/historique">
              <bea-admin-icon name="manage_history" /> Historique complet
            </a>
          </div>
        }

        <div class="bea-sr-columns">
          <section class="bea-admin-panel bea-sr-panel">
            <h2>Dernières sauvegardes</h2>
            <ul class="bea-sr-list">
              @for (b of d.dernieres_sauvegardes; track b.id) {
                <li>
                  <button type="button" class="bea-sr-list__row" (click)="details.set({ kind: 'backup', id: b.id })">
                    <span class="bea-sr-badge" [attr.data-level]="b.level">{{ b.type }}</span>
                    <span class="bea-sr-list__main">
                      <strong>{{ b.perimetre }}</strong>
                      <small>{{ b.created_at | date: 'dd/MM/yyyy HH:mm' : tz }} · {{ user(b.administrateur) }} · {{ bytes(b.size_bytes) }}</small>
                    </span>
                    <em class="bea-sr-status" [attr.data-status]="b.status">{{ status(b.status) }}</em>
                  </button>
                </li>
              } @empty {
                <li class="bea-admin-panel__empty">Aucune sauvegarde.</li>
              }
            </ul>
          </section>

          <section class="bea-admin-panel bea-sr-panel">
            <h2>Dernières restaurations</h2>
            <ul class="bea-sr-list">
              @for (r of d.dernieres_restaurations; track r.id) {
                <li>
                  <button type="button" class="bea-sr-list__row" (click)="details.set({ kind: 'restore', id: r.id })">
                    <span class="bea-sr-badge" [attr.data-level]="r.level">{{ r.type }}</span>
                    <span class="bea-sr-list__main">
                      <strong>{{ r.perimetre }}</strong>
                      <small>{{ r.created_at | date: 'dd/MM/yyyy HH:mm' : tz }} · {{ user(r.administrateur) }}</small>
                    </span>
                    <em class="bea-sr-status" [attr.data-status]="r.status">{{ status(r.status) }}</em>
                  </button>
                </li>
              } @empty {
                <li class="bea-admin-panel__empty">Aucune restauration.</li>
              }
            </ul>
          </section>
        </div>

        @if (d.erreurs.length) {
          <section class="bea-admin-panel bea-sr-panel">
            <h2>Erreurs récentes</h2>
            <ul class="bea-sr-list">
              @for (e of d.erreurs; track e.id) {
                <li>
                  <button type="button" class="bea-sr-list__row" (click)="details.set({ kind: e.kind, id: e.id! })">
                    <span class="bea-sr-badge" [attr.data-level]="e.level">{{ e.kind === 'backup' ? 'Sauvegarde' : 'Restauration' }}</span>
                    <span class="bea-sr-list__main">
                      <strong>{{ e.perimetre }}</strong>
                      <small class="bea-sr-error">{{ e.error_message || e.integrity_detail || 'Erreur' }}</small>
                    </span>
                    <span class="bea-sr-list__date">{{ e.created_at | date: 'dd/MM HH:mm' : tz }}</span>
                  </button>
                </li>
              }
            </ul>
          </section>
        }
      }
    </section>

    @if (details(); as dt) {
      <bea-sr-details [kind]="dt.kind" [itemId]="dt.id" (closed)="details.set(null)" (changed)="load()" />
    }
  `,
})
export class CoreAdminSauvegardesOverviewComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly perms = srPermissions();
  readonly tz = TZ;
  readonly dash = signal<SrDashboard | null>(null);
  readonly loading = signal(true);
  readonly details = signal<{ kind: 'backup' | 'restore'; id: string } | null>(null);
  readonly status = srStatusLabel;
  readonly bytes = srBytes;
  readonly user = srUser;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.get<SrDashboard>(`${SR_API}/backups/dashboard`).subscribe({
      next: (d) => {
        this.dash.set(d);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }
}

/* ------------------------------------------------------------------ */
/* Sauvegarde                                                          */
/* ------------------------------------------------------------------ */

interface SrBackupResult {
  ok: boolean;
  backup?: SrBackup;
  message?: string;
  requestId?: string | null;
  at: Date;
}

@Component({
  selector: 'bea-core-admin-sauvegardes-backup',
  imports: [DatePipe, DecimalPipe, CoreAdminIconComponent, SrHeaderComponent, SrProgressComponent, SrScopeComponent, SrDetailsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr">
      <bea-sr-header title="Sauvegarde" subtitle="Choisissez le niveau : globale, département ou module. Le périmètre et l’estimation sont calculés à partir des données réelles." />

      @if (!perms.create()) {
        <p class="bea-sr-alert" data-tone="warn">
          Votre profil permet de consulter les sauvegardes mais pas d’en lancer (permission <code>core.admin.backup.create</code>).
        </p>
      }

      <section class="bea-admin-panel bea-sr-panel">
        <h2>1. Niveau et périmètre</h2>
        <bea-sr-scope
          [catalogue]="catalogue()"
          [level]="level()"
          [espaceCode]="espace()"
          [moduleCode]="module()"
          [disabled]="busy()"
          (scopeChange)="onScope($event)"
        />
      </section>

      @if (ready()) {
        <section class="bea-admin-panel bea-sr-panel">
          <h2>2. Récapitulatif avant exécution</h2>
          @if (previewLoading()) {
            <p class="bea-admin-dash__loading">Calcul du périmètre…</p>
          } @else if (previewError()) {
            <p class="bea-sr-alert" data-tone="danger">{{ previewError() }}</p>
          } @else if (preview(); as p) {
            <dl class="bea-sr-summary">
              <div><dt>Type</dt><dd><span class="bea-sr-badge" [attr.data-level]="p.level">{{ p.type }}</span></dd></div>
              <div><dt>Périmètre</dt><dd>{{ p.perimetre }}</dd></div>
              <div><dt>Départements</dt><dd>{{ p.departements_count }}</dd></div>
              <div><dt>Modules</dt><dd>{{ p.modules_count }}</dd></div>
              <div><dt>Date et heure</dt><dd>{{ now() | date: 'dd/MM/yyyy HH:mm:ss' : tz }}</dd></div>
              <div><dt>Administrateur connecté</dt><dd>{{ user(p.administrateur) }}</dd></div>
              <div><dt>Taille estimée</dt><dd>≈ {{ bytes(p.estimated_bytes) }}</dd></div>
              <div><dt>Contenu</dt><dd>
                {{ p.tables_count }} table(s) · {{ p.rows_exact ? '' : '≈ ' }}{{ p.rows_total | number: '1.0-0' : 'fr' }} ligne(s)
                @if (p.ged_documents) { · {{ p.ged_documents }} doc. GED }
              </dd></div>
              @if (p.file_targets.length) {
                <div class="bea-sr-summary__wide"><dt>Fichiers inclus</dt><dd class="bea-sr-mono">{{ p.file_targets.join(', ') }}</dd></div>
              }
              @if (p.level !== 'global' && p.modules.length) {
                <div class="bea-sr-summary__wide"><dt>Modules couverts</dt><dd>{{ moduleLabels(p) }}</dd></div>
              }
            </dl>
            @if (p.warnings.length) {
              <ul class="bea-sr-alert" data-tone="warn">
                @for (w of p.warnings; track w) {
                  <li>{{ w }}</li>
                }
              </ul>
            }
            <div class="bea-sr-cta-row">
              <button
                type="button"
                class="bea-admin-btn bea-sr-cta"
                [disabled]="busy() || !p.backupable || !perms.create()"
                (click)="launch(p)"
              >
                <bea-admin-icon name="backup" />
                {{ ctaLabel() }}
              </button>
              @if (!p.backupable) {
                <span class="bea-sr-hint">Ce périmètre ne contient aucune donnée propre à sauvegarder.</span>
              }
            </div>
          }
        </section>
      }

      @if (result(); as r) {
        <section class="bea-admin-panel bea-sr-panel bea-sr-result" [attr.data-status]="r.ok ? 'success' : 'failed'" aria-live="polite">
          <h2>
            <bea-admin-icon [name]="r.ok ? 'task_alt' : 'error'" />
            Résultat : {{ r.ok ? 'Réussie' : 'Échec' }}
          </h2>
          @if (r.backup; as b) {
            <dl class="bea-sr-summary">
              <div><dt>Statut</dt><dd><em class="bea-sr-status" [attr.data-status]="b.status">{{ status(b.status) }}</em></dd></div>
              <div><dt>Date et heure</dt><dd>{{ b.created_at | date: 'dd/MM/yyyy HH:mm:ss' : tz }}</dd></div>
              <div><dt>Durée</dt><dd>{{ duration(b.duration_ms) }}</dd></div>
              <div><dt>Taille</dt><dd>{{ bytes(b.size_bytes) }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Identifiant</dt><dd class="bea-sr-mono">{{ b.id }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Emplacement</dt><dd class="bea-sr-mono">{{ b.emplacement || '—' }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Checksum SHA-256</dt><dd class="bea-sr-mono">{{ b.checksum_sha256 || '—' }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Message</dt><dd>{{ successMessage(b) }}</dd></div>
            </dl>
            <div class="bea-sr-cta-row">
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="details.set(b.id)">
                <bea-admin-icon name="visibility" /> Voir les détails
              </button>
            </div>
          } @else {
            <dl class="bea-sr-summary">
              <div><dt>Statut</dt><dd><em class="bea-sr-status" data-status="failed">Échec</em></dd></div>
              <div><dt>Date et heure</dt><dd>{{ r.at | date: 'dd/MM/yyyy HH:mm:ss' : tz }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Message</dt><dd class="bea-sr-error">{{ r.message }}</dd></div>
              @if (r.requestId) {
                <div class="bea-sr-summary__wide"><dt>Référence support</dt><dd class="bea-sr-mono">{{ r.requestId }}</dd></div>
              }
            </dl>
            <p class="bea-sr-hint">L’échec est enregistré dans l’historique et l’audit. Aucune donnée n’a été modifiée.</p>
          }
        </section>
      }
    </section>

    @if (busy()) {
      <bea-sr-progress [title]="'Sauvegarde ' + (preview()?.type ?? '').toLowerCase() + ' en cours…'" [steps]="steps" />
    }
    @if (details(); as id) {
      <bea-sr-details kind="backup" [itemId]="id" (closed)="details.set(null)" (changed)="result.set(null); refreshPreview()" />
    }
  `,
})
export class CoreAdminSauvegardesBackupComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(BeaAdminDialogService);
  private readonly route = inject(ActivatedRoute);
  readonly perms = srPermissions();
  readonly tz = TZ;

  readonly catalogue = signal<SrCatalogue | null>(null);
  readonly level = signal<SrLevel>('global');
  readonly espace = signal('');
  readonly module = signal('');
  readonly ready = computed(() => scopeReady(this.level(), this.espace(), this.module()));
  readonly preview = signal<SrBackupPreview | null>(null);
  readonly previewLoading = signal(false);
  readonly previewError = signal<string | null>(null);
  readonly busy = signal(false);
  readonly result = signal<SrBackupResult | null>(null);
  readonly details = signal<string | null>(null);
  readonly now = signal(new Date());
  readonly ctaLabel = computed(() =>
    this.level() === 'global'
      ? 'Lancer la sauvegarde globale'
      : this.level() === 'departement'
        ? 'Sauvegarder le département'
        : 'Sauvegarder le module',
  );
  readonly steps = [
    'Export PostgreSQL du périmètre (pg_dump)',
    'Export des lignes GED et des fichiers',
    'Calcul des empreintes SHA-256 et du manifeste',
    'Enregistrement dans l’historique et l’audit',
  ];

  readonly status = srStatusLabel;
  readonly bytes = srBytes;
  readonly duration = srDuration;
  readonly user = srUser;
  private clock: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.clock = setInterval(() => this.now.set(new Date()), 1000);
    const q = this.route.snapshot.queryParamMap;
    const lvl = q.get('niveau') as SrLevel | null;
    if (lvl && SR_LEVELS.some((l) => l.value === lvl)) {
      this.level.set(lvl);
      this.espace.set(q.get('departement') ?? '');
      this.module.set(q.get('module') ?? '');
    }
    this.api.get<SrCatalogue>(`${SR_API}/backups/catalogue`).subscribe((c) => this.catalogue.set(c));
    this.refreshPreview();
  }

  ngOnDestroy(): void {
    if (this.clock) clearInterval(this.clock);
  }

  onScope(s: { level: SrLevel; espace: string; module: string }): void {
    this.level.set(s.level);
    this.espace.set(s.espace);
    this.module.set(s.module);
    this.result.set(null);
    this.refreshPreview();
  }

  moduleLabels(p: SrBackupPreview): string {
    return p.modules.map((m) => m.label).join(', ');
  }

  successMessage(b: SrBackup): string {
    const parts = [`${b.tables_count} table(s)`];
    if (b.ged_documents) parts.push(`${b.ged_documents} document(s) GED`);
    if (b.files_count) parts.push(`${b.files_count} fichier(s)`);
    return `Sauvegarde ${b.type.toLowerCase()} terminée : ${parts.join(', ')}.`;
  }

  private params(): Record<string, string> {
    const params: Record<string, string> = { level: this.level() };
    if (this.level() !== 'global') params['espace_code'] = this.espace();
    if (this.level() === 'module') params['module_code'] = this.module();
    return params;
  }

  refreshPreview(): void {
    this.preview.set(null);
    this.previewError.set(null);
    if (!this.ready()) return;
    this.previewLoading.set(true);
    const key = JSON.stringify(this.params());
    this.api.get<SrBackupPreview>(`${SR_API}/backups/preview`, this.params()).subscribe({
      next: (p) => {
        if (key !== JSON.stringify(this.params())) return;
        this.preview.set(p);
        this.previewLoading.set(false);
      },
      error: () => {
        this.previewError.set('Impossible de calculer le périmètre de sauvegarde.');
        this.previewLoading.set(false);
      },
    });
  }

  async launch(p: SrBackupPreview): Promise<void> {
    const ok = await this.dialog.confirm({
      title: this.ctaLabel(),
      message:
        `Type : ${p.type}\nPérimètre : ${p.perimetre}\n` +
        `Départements : ${p.departements_count} · Modules : ${p.modules_count}\n` +
        `Tables : ${p.tables_count} · Taille estimée : ≈ ${srBytes(p.estimated_bytes)}\n\n` +
        `La sauvegarde est en lecture seule : aucune donnée n’est modifiée.`,
      confirmLabel: 'Lancer',
      tone: 'primary',
    });
    if (!ok) return;
    this.result.set(null);
    const body: Record<string, unknown> = { level: p.level, backup_type: 'manuelle' };
    if (p.level !== 'global') body['espace_code'] = p.espace_code;
    if (p.level === 'module') body['module_code'] = p.module_code;
    this.feedback
      .run(() => this.api.post<SrBackup>(`${SR_API}/backups`, body), {
        busy: this.busy,
        retry: false,
        errorTitle: 'Échec de la sauvegarde',
        onError: (e) => this.result.set({ ok: false, message: e.message, requestId: e.requestId, at: new Date() }),
        success: (b) => ({
          title: 'Sauvegarde réussie',
          message: `${b.perimetre} — ${srBytes(b.size_bytes)} en ${srDuration(b.duration_ms)}.`,
        }),
      })
      .subscribe((b) => {
        this.result.set({ ok: true, backup: b, at: new Date() });
        this.refreshPreview();
      });
  }
}

/* ------------------------------------------------------------------ */
/* Recovery                                                            */
/* ------------------------------------------------------------------ */

interface SrRestoreResult {
  ok: boolean;
  restore?: SrRestore;
  message?: string;
  requestId?: string | null;
  at: Date;
}

@Component({
  selector: 'bea-core-admin-sauvegardes-recovery',
  imports: [DatePipe, CoreAdminIconComponent, SrHeaderComponent, SrProgressComponent, SrScopeComponent, SrDetailsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr">
      <bea-sr-header title="Recovery" subtitle="Restaurer une sauvegarde au niveau global, d’un département ou d’un module. Chaque restauration est précédée d’une sauvegarde de sécurité et tracée." />

      @if (!perms.recoveryExec()) {
        <p class="bea-sr-alert" data-tone="warn">
          Consultation seule : la restauration requiert la permission <code>core.admin.recovery.execute</code>.
        </p>
      }

      <section class="bea-admin-panel bea-sr-panel">
        <h2>1. Niveau et périmètre</h2>
        <bea-sr-scope
          [catalogue]="catalogue()"
          [level]="level()"
          [espaceCode]="espace()"
          [moduleCode]="module()"
          [disabled]="busy()"
          (scopeChange)="onScope($event)"
        />
      </section>

      @if (ready()) {
        <section class="bea-admin-panel bea-sr-panel">
          <h2>2. Sauvegarde à restaurer</h2>
          @if (backupsLoading()) {
            <p class="bea-admin-dash__loading">Chargement des sauvegardes…</p>
          } @else if (backups().length === 0) {
            <p class="bea-admin-panel__empty">Aucune sauvegarde réussie pour ce périmètre.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table bea-sr-plain bea-sr-pick">
                <thead>
                  <tr><th></th><th>Date</th><th>Nature</th><th>Administrateur</th><th>Taille</th><th>Intégrité</th><th>Identifiant</th></tr>
                </thead>
                <tbody>
                  @for (b of backups(); track b.id) {
                    <tr [class.bea-sr-pick--on]="b.id === selectedId()" (click)="select(b)">
                      <td>
                        <input
                          type="radio"
                          name="sr-backup"
                          [checked]="b.id === selectedId()"
                          [disabled]="!b.restorable || busy()"
                          [attr.aria-label]="'Sélectionner la sauvegarde du ' + (b.created_at | date: 'dd/MM/yyyy HH:mm' : tz)"
                          (change)="select(b)"
                        />
                      </td>
                      <td>{{ b.created_at | date: 'dd/MM/yyyy HH:mm' : tz }}</td>
                      <td>{{ backupType(b.backup_type) }}{{ b.restorable ? '' : ' (non restaurable)' }}</td>
                      <td>{{ user(b.administrateur) }}</td>
                      <td>{{ bytes(b.size_bytes) }}</td>
                      <td>
                        @if (b.integrity_status) {
                          <em class="bea-sr-status" [attr.data-status]="b.integrity_status === 'ok' ? 'success' : 'failed'">{{ b.integrity_status === 'ok' ? 'OK' : 'KO' }}</em>
                        } @else {
                          <span class="bea-sr-hint">Non vérifiée</span>
                        }
                      </td>
                      <td class="bea-sr-mono">{{ b.id.slice(0, 8) }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </section>
      }

      @if (selected(); as b) {
        <section class="bea-admin-panel bea-sr-panel">
          <h2>3. Sauvegarde sélectionnée</h2>
          <dl class="bea-sr-summary">
            <div class="bea-sr-summary__wide"><dt>Identifiant</dt><dd class="bea-sr-mono">{{ b.id }}</dd></div>
            <div><dt>Type</dt><dd><span class="bea-sr-badge" [attr.data-level]="b.level">{{ b.type }}</span></dd></div>
            <div><dt>Date</dt><dd>{{ b.created_at | date: 'dd/MM/yyyy' : tz }}</dd></div>
            <div><dt>Heure</dt><dd>{{ b.created_at | date: 'HH:mm:ss' : tz }}</dd></div>
            <div><dt>Taille</dt><dd>{{ bytes(b.size_bytes) }}</dd></div>
            <div><dt>Statut</dt><dd><em class="bea-sr-status" [attr.data-status]="b.status">{{ status(b.status) }}</em></dd></div>
            <div><dt>Administrateur</dt><dd>{{ user(b.administrateur) }}</dd></div>
            <div class="bea-sr-summary__wide"><dt>Checksum SHA-256</dt><dd class="bea-sr-mono">{{ b.checksum_sha256 || '—' }}</dd></div>
          </dl>
          <div class="bea-sr-cta-row">
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="verifying() || busy()" (click)="verify(b)">
              <bea-admin-icon name="verified" /> Vérifier l’intégrité
            </button>
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="details.set(b.id)">
              <bea-admin-icon name="visibility" /> Détails
            </button>
          </div>

          @if (previewLoading()) {
            <p class="bea-admin-dash__loading">Analyse de l’impact…</p>
          } @else if (previewError()) {
            <p class="bea-sr-alert" data-tone="danger">{{ previewError() }}</p>
          } @else if (preview(); as p) {
            <div class="bea-sr-danger" role="alert">
              <h3><bea-admin-icon name="warning" /> Attention : les données existantes seront remplacées</h3>
              <p>
                La restauration remplace le contenu actuel {{ impactScope(p) }} par leur état au
                {{ b.created_at | date: 'dd/MM/yyyy à HH:mm' : tz }}. Les données saisies depuis seront perdues.
              </p>
              <p>
                Une <strong>sauvegarde de sécurité</strong> du même périmètre est créée automatiquement avant l’exécution.
                L’opération est atomique : en cas d’erreur, rien n’est modifié.
              </p>
              @if (p.warnings.length) {
                <ul>
                  @for (w of p.warnings; track w) {
                    <li>{{ w }}</li>
                  }
                </ul>
              }
              @if (p.dependencies.length) {
                <details class="bea-sr-fold" open>
                  <summary>{{ p.dependencies.length }} dépendance(s) avec d’autres modules</summary>
                  <ul>
                    @for (dep of p.dependencies; track dep.table + dep.references) {
                      <li>
                        <span class="bea-sr-mono">{{ dep.table }}</span>
                        {{ dep.direction === 'out' ? '→' : '←' }}
                        <span class="bea-sr-mono">{{ dep.references }}</span>
                        @if (dep.module_label) { ({{ dep.module_label }}) }
                      </li>
                    }
                  </ul>
                </details>
              }
              @if (p.preserved_tables.length) {
                <details class="bea-sr-fold">
                  <summary>{{ p.preserved_tables.length }} table(s) préservée(s) (non restaurées)</summary>
                  <p class="bea-sr-mono">{{ p.preserved_tables.join(', ') }}</p>
                </details>
              }
              <details class="bea-sr-fold">
                <summary>Voir les {{ p.tables_count }} table(s) restaurée(s)</summary>
                <div class="bea-admin-table-wrap">
                  <table class="bea-admin-table bea-sr-plain">
                    <thead><tr><th>Table</th><th>Lignes actuelles</th><th>Lignes sauvegardées</th></tr></thead>
                    <tbody>
                      @for (t of p.tables; track t.name) {
                        <tr>
                          <td class="bea-sr-mono">{{ t.name }}</td>
                          <td>{{ count(t.rows_current) }}</td>
                          <td>{{ count(t.rows_backup) }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              </details>
              @if (p.level === 'global') {
                <label class="bea-sr-check">
                  <input type="checkbox" [checked]="includeSecurity()" [disabled]="busy()" (change)="toggleSecurity($any($event.target).checked)" />
                  <span>
                    Restaurer aussi le plan de sécurité (utilisateurs, rôles, permissions, sessions).
                    <small>Déconseillé : peut révoquer des comptes ou votre propre session.</small>
                  </span>
                </label>
              }
              <label class="bea-sr-check">
                <input type="checkbox" [checked]="acknowledged()" [disabled]="busy()" (change)="acknowledged.set($any($event.target).checked)" />
                <span>J’ai compris que les données existantes du périmètre seront remplacées.</span>
              </label>
              <div class="bea-sr-cta-row">
                <button
                  type="button"
                  class="bea-admin-btn bea-admin-btn--danger bea-sr-cta"
                  [disabled]="busy() || !acknowledged() || !perms.recoveryExec()"
                  (click)="restore(b, p)"
                >
                  <bea-admin-icon name="settings_backup_restore" />
                  {{ ctaLabel() }}
                </button>
              </div>
            </div>
          }
        </section>
      }

      @if (result(); as r) {
        <section class="bea-admin-panel bea-sr-panel bea-sr-result" [attr.data-status]="r.restore?.status ?? 'failed'" aria-live="polite">
          <h2>
            <bea-admin-icon [name]="r.ok ? 'task_alt' : r.restore ? 'warning' : 'error'" />
            Résultat : {{ r.restore ? status(r.restore.status) : 'Échec' }}
          </h2>
          @if (r.restore; as x) {
            <dl class="bea-sr-summary">
              <div><dt>Date et heure</dt><dd>{{ x.created_at | date: 'dd/MM/yyyy HH:mm:ss' : tz }}</dd></div>
              <div><dt>Durée</dt><dd>{{ duration(x.duration_ms) }}</dd></div>
              <div><dt>Tables restaurées</dt><dd>{{ x.details?.tables_count ?? '—' }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Identifiant</dt><dd class="bea-sr-mono">{{ x.id }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Sauvegarde de sécurité</dt><dd class="bea-sr-mono">{{ x.safety_backup_id || '—' }}</dd></div>
              @if (x.error_message) {
                <div class="bea-sr-summary__wide"><dt>Message</dt><dd class="bea-sr-error">{{ x.error_message }}</dd></div>
              }
            </dl>
            <div class="bea-sr-cta-row">
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="restoreDetails.set(x.id)">
                <bea-admin-icon name="visibility" /> Voir les détails
              </button>
            </div>
          } @else {
            <dl class="bea-sr-summary">
              <div><dt>Date et heure</dt><dd>{{ r.at | date: 'dd/MM/yyyy HH:mm:ss' : tz }}</dd></div>
              <div class="bea-sr-summary__wide"><dt>Message</dt><dd class="bea-sr-error">{{ r.message }}</dd></div>
              @if (r.requestId) {
                <div class="bea-sr-summary__wide"><dt>Référence support</dt><dd class="bea-sr-mono">{{ r.requestId }}</dd></div>
              }
            </dl>
            <p class="bea-sr-hint">La transaction a été annulée : les données actuelles sont intactes. L’échec est tracé dans l’historique et l’audit.</p>
          }
        </section>
      }
    </section>

    @if (busy()) {
      <bea-sr-progress tone="danger" [title]="'Restauration ' + (selected()?.type ?? '').toLowerCase() + ' en cours…'" [steps]="steps" />
    }
    @if (details(); as id) {
      <bea-sr-details kind="backup" [itemId]="id" (closed)="details.set(null)" (changed)="loadBackups(selectedId())" />
    }
    @if (restoreDetails(); as id) {
      <bea-sr-details kind="restore" [itemId]="id" (closed)="restoreDetails.set(null)" />
    }
  `,
})
export class CoreAdminSauvegardesRecoveryComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly dialog = inject(BeaAdminDialogService);
  private readonly actions = inject(SrActionsService);
  private readonly route = inject(ActivatedRoute);
  readonly perms = srPermissions();
  readonly tz = TZ;

  readonly catalogue = signal<SrCatalogue | null>(null);
  readonly level = signal<SrLevel>('global');
  readonly espace = signal('');
  readonly module = signal('');
  readonly ready = computed(() => scopeReady(this.level(), this.espace(), this.module()));
  readonly backups = signal<SrBackup[]>([]);
  readonly backupsLoading = signal(false);
  readonly selectedId = signal<string | null>(null);
  readonly selected = computed(() => this.backups().find((b) => b.id === this.selectedId()) ?? null);
  readonly preview = signal<SrRestorePreview | null>(null);
  readonly previewLoading = signal(false);
  readonly previewError = signal<string | null>(null);
  readonly includeSecurity = signal(false);
  readonly acknowledged = signal(false);
  readonly busy = signal(false);
  readonly verifying = signal(false);
  readonly result = signal<SrRestoreResult | null>(null);
  readonly details = signal<string | null>(null);
  readonly restoreDetails = signal<string | null>(null);
  readonly ctaLabel = computed(() =>
    this.level() === 'global'
      ? 'Restaurer la plateforme'
      : this.level() === 'departement'
        ? 'Restaurer le département'
        : 'Restaurer le module',
  );
  readonly steps = [
    'Sauvegarde de sécurité du périmètre actuel',
    'Restauration transactionnelle des tables',
    'Contrôle d’intégrité référentielle',
    'Restauration des fichiers et traçabilité',
  ];

  readonly status = srStatusLabel;
  readonly backupType = srBackupTypeLabel;
  readonly bytes = srBytes;
  readonly duration = srDuration;
  readonly user = srUser;

  count(n: number | null | undefined): string {
    return n == null ? '—' : n.toLocaleString('fr-FR');
  }

  impactScope(p: SrRestorePreview): string {
    const parts = [`de ${p.tables_count} table(s)`];
    if (p.ged.module_codes.length) {
      parts.push(`des documents GED (${p.ged.rows_current} actuel(s) → ${p.ged.rows_backup ?? '?'})`);
    }
    if (p.file_targets.length) parts.push(`des fichiers ${p.file_targets.join(', ')}`);
    return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} et ${parts[parts.length - 1]}` : parts[0];
  }

  ngOnInit(): void {
    this.api.get<SrCatalogue>(`${SR_API}/backups/catalogue`).subscribe((c) => this.catalogue.set(c));
    const target = this.route.snapshot.queryParamMap.get('backup');
    if (target) {
      this.api.get<SrBackup>(`${SR_API}/backups/${target}`).subscribe({
        next: (b) => {
          this.level.set(b.level);
          this.espace.set(b.espace_code ?? '');
          this.module.set(b.module_code ?? '');
          this.loadBackups(b.id);
        },
        error: () => this.loadBackups(null),
      });
    } else {
      this.loadBackups(null);
    }
  }

  onScope(s: { level: SrLevel; espace: string; module: string }): void {
    this.level.set(s.level);
    this.espace.set(s.espace);
    this.module.set(s.module);
    this.result.set(null);
    this.loadBackups(null);
  }

  loadBackups(selectId: string | null): void {
    this.backups.set([]);
    this.resetSelection();
    if (!this.ready()) return;
    const params: Record<string, string | number> = { level: this.level(), status: 'success', size: 50 };
    if (this.level() !== 'global') params['espace_code'] = this.espace();
    if (this.level() === 'module') params['module_code'] = this.module();
    this.backupsLoading.set(true);
    this.api.get<{ items: SrBackup[] }>(`${SR_API}/backups`, params).subscribe({
      next: (res) => {
        this.backups.set(res.items);
        this.backupsLoading.set(false);
        const b = res.items.find((x) => x.id === selectId);
        if (b) this.select(b);
      },
      error: () => this.backupsLoading.set(false),
    });
  }

  private resetSelection(): void {
    this.selectedId.set(null);
    this.preview.set(null);
    this.previewError.set(null);
    this.acknowledged.set(false);
    this.includeSecurity.set(false);
  }

  select(b: SrBackup): void {
    if (!b.restorable || this.busy() || b.id === this.selectedId()) return;
    this.resetSelection();
    this.selectedId.set(b.id);
    this.loadPreview();
  }

  toggleSecurity(on: boolean): void {
    this.includeSecurity.set(on);
    this.acknowledged.set(false);
    this.loadPreview();
  }

  private loadPreview(): void {
    const id = this.selectedId();
    if (!id) return;
    this.previewLoading.set(true);
    this.previewError.set(null);
    this.api
      .get<SrRestorePreview>(`${SR_API}/recovery/${id}/preview`, { include_security: this.includeSecurity() })
      .subscribe({
        next: (p) => {
          if (this.selectedId() !== id) return;
          this.preview.set(p);
          this.previewLoading.set(false);
        },
        error: () => {
          this.previewError.set('Impossible d’analyser l’impact de cette restauration.');
          this.previewLoading.set(false);
        },
      });
  }

  verify(b: SrBackup): void {
    this.actions.verify(b.id, this.verifying).subscribe((r) => {
      this.backups.update((list) =>
        list.map((x) => (x.id === b.id ? { ...x, integrity_status: r.integrity_status, integrity_checked_at: r.checked_at } : x)),
      );
    });
  }

  async restore(b: SrBackup, p: SrRestorePreview): Promise<void> {
    const phrase = p.confirmation_phrase;
    const when = new Date(b.created_at ?? '').toLocaleString('fr-FR', { timeZone: TZ });
    const values = await this.dialog.prompt({
      title: `${this.ctaLabel()} — confirmation`,
      tone: 'danger',
      message:
        `Vous allez restaurer « ${b.perimetre} » à son état du ${when}.\n\n` +
        `Les données existantes de ${p.tables_count} table(s) seront REMPLACÉES. ` +
        `Une sauvegarde de sécurité sera créée juste avant.\n\n` +
        `Pour confirmer, saisissez exactement : ${phrase}`,
      fields: [
        { key: 'confirmation', label: `Phrase de confirmation (« ${phrase} »)`, autocomplete: 'off' },
        { key: 'motif', label: 'Motif de la restauration (10 caractères minimum)', autocomplete: 'off' },
      ],
      confirmLabel: 'Restaurer définitivement',
      validate: (v) => {
        if ((v['confirmation'] ?? '').trim().toUpperCase() !== phrase.toUpperCase()) {
          return `Saisissez exactement « ${phrase} ».`;
        }
        if ((v['motif'] ?? '').trim().length < 10) return 'Le motif est obligatoire (10 caractères minimum).';
        return null;
      },
    });
    if (!values) return;
    this.result.set(null);
    this.feedback
      .run(
        () =>
          this.api.post<SrRestore>(`${SR_API}/recovery/${b.id}`, {
            acknowledge_dependencies: true,
            confirmation: values['confirmation'].trim(),
            reason: values['motif'].trim(),
            include_security: p.level === 'global' && this.includeSecurity(),
          }),
        {
          busy: this.busy,
          retry: false,
          errorTitle: 'Restauration impossible',
          onError: (e) => this.result.set({ ok: false, message: e.message, requestId: e.requestId, at: new Date() }),
          success: (r) =>
            r.status === 'success'
              ? {
                  title: 'Restauration terminée',
                  message: `${r.perimetre} restauré en ${srDuration(r.duration_ms)}. Sauvegarde de sécurité : ${r.safety_backup_id?.slice(0, 8) ?? '—'}.`,
                }
              : null,
        },
      )
      .subscribe((r) => {
        if (r.status !== 'success') {
          this.feedback.warning({
            title: 'Restauration partielle',
            message: r.error_message ?? 'Les tables ont été restaurées mais certains fichiers n’ont pas pu l’être.',
            duration: 0,
          });
        }
        this.result.set({ ok: r.status === 'success', restore: r, at: new Date() });
        this.loadBackups(null);
      });
  }
}

/* ------------------------------------------------------------------ */
/* Historique                                                          */
/* ------------------------------------------------------------------ */

@Component({
  selector: 'bea-core-admin-sauvegardes-history',
  imports: [DatePipe, CoreAdminIconComponent, SrHeaderComponent, SrDetailsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="bea-admin-dash bea-sr">
      <bea-sr-header title="Historique" subtitle="Toutes les sauvegardes et restaurations, tous niveaux confondus." />

      <div class="bea-admin-toolbar bea-sr-filters">
        <label class="bea-admin-field">
          <span>Opération</span>
          <select (change)="setFilter('kind', $any($event.target).value)">
            <option value="">Toutes</option>
            <option value="backup">Sauvegardes</option>
            <option value="restore">Restaurations</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Type</span>
          <select (change)="setFilter('level', $any($event.target).value)">
            <option value="">Tous</option>
            <option value="global">GLOBAL</option>
            <option value="departement">DEPARTEMENT</option>
            <option value="module">MODULE</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Statut</span>
          <select (change)="setFilter('status', $any($event.target).value)">
            <option value="">Tous</option>
            <option value="success">Réussie</option>
            <option value="partial">Partielle</option>
            <option value="failed">Échec</option>
            <option value="running">En cours</option>
          </select>
        </label>
        <div class="bea-admin-toolbar__actions">
          @if (perms.delete() && selected().size) {
            <button type="button" class="bea-admin-btn bea-admin-btn--danger" [disabled]="rowBusy()" (click)="removeSelected()">
              <bea-admin-icon name="delete" /> Supprimer la sélection ({{ selected().size }})
            </button>
          }
          <button type="button" class="bea-admin-btn bea-admin-btn--refresh" [disabled]="loading()" (click)="load()">
            <bea-admin-icon name="refresh" /> Actualiser
          </button>
        </div>
      </div>

      <div class="bea-admin-panel">
        @if (loading() && !items().length) {
          <p class="bea-admin-dash__loading">Chargement de l’historique…</p>
        } @else if (!items().length) {
          <p class="bea-admin-panel__empty">Aucune opération pour ces critères.</p>
        } @else {
          <div class="bea-admin-table-wrap">
            <table class="bea-admin-table">
              <thead>
                <tr>
                  @if (perms.delete()) {
                    <th class="bea-sr-select">
                      <input
                        type="checkbox"
                        aria-label="Sélectionner toutes les sauvegardes de la page"
                        [checked]="allSelected()"
                        [disabled]="!deletable().length"
                        (change)="toggleAll($any($event.target).checked)"
                      />
                    </th>
                  }
                  <th>Date</th>
                  <th>Type</th>
                  <th>Périmètre</th>
                  <th>Administrateur</th>
                  <th>Taille</th>
                  <th>Statut</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                @for (row of items(); track row.kind + row.id) {
                  <tr [class.bea-sr-row--selected]="selected().has(row.id)">
                    @if (perms.delete()) {
                      <td class="bea-sr-select">
                        @if (canDelete(row)) {
                          <input
                            type="checkbox"
                            [attr.aria-label]="'Sélectionner la sauvegarde du ' + (row.created_at | date: 'dd/MM/yyyy HH:mm' : tz)"
                            [checked]="selected().has(row.id)"
                            (change)="toggle(row.id, $any($event.target).checked)"
                          />
                        }
                      </td>
                    }
                    <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' : tz }}</td>
                    <td>
                      <span class="bea-sr-badge" [attr.data-level]="row.level">{{ row.type }}</span>
                      <div class="bea-sr-subline">
                        <bea-admin-icon [name]="row.kind === 'backup' ? 'backup' : 'settings_backup_restore'" />
                        {{ row.kind === 'backup' ? 'Sauvegarde · ' + backupType(row.subtype) : 'Restauration' }}
                      </div>
                    </td>
                    <td>{{ row.perimetre }}</td>
                    <td>{{ user(row.administrateur) }}</td>
                    <td>{{ row.kind === 'backup' ? bytes(row.size_bytes) : '—' }}</td>
                    <td>
                      <em class="bea-sr-status" [attr.data-status]="row.status" [title]="row.error_message || ''">{{ status(row.status) }}</em>
                      @if (row.integrity_status) {
                        <div class="bea-sr-subline">Intégrité {{ row.integrity_status === 'ok' ? 'OK' : 'KO' }}</div>
                      }
                    </td>
                    <td class="bea-admin-table__actions">
                      <div class="bea-admin-row-actions">
                        <button type="button" class="bea-admin-icon-btn" title="Voir détails" aria-label="Voir détails" (click)="details.set({ kind: row.kind, id: row.id })">
                          <bea-admin-icon name="visibility" />
                        </button>
                        @if (row.kind === 'backup' && row.status === 'success') {
                          @if (perms.download()) {
                            <button type="button" class="bea-admin-icon-btn" title="Télécharger" aria-label="Télécharger" [disabled]="rowBusy()" (click)="download(row)">
                              <bea-admin-icon name="download" />
                            </button>
                          }
                          @if (perms.recoveryExec()) {
                            <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--danger" title="Restaurer" aria-label="Restaurer" (click)="goRestore(row.id)">
                              <bea-admin-icon name="settings_backup_restore" />
                            </button>
                          }
                          <button type="button" class="bea-admin-icon-btn" title="Vérifier intégrité" aria-label="Vérifier intégrité" [disabled]="rowBusy()" (click)="verify(row)">
                            <bea-admin-icon name="verified" />
                          </button>
                        }
                        @if (perms.delete() && canDelete(row)) {
                          <button type="button" class="bea-admin-icon-btn bea-admin-icon-btn--danger" title="Supprimer" aria-label="Supprimer la sauvegarde" [disabled]="rowBusy()" (click)="removeOne(row)">
                            <bea-admin-icon name="delete" />
                          </button>
                        }
                        @if (row.kind === 'restore' && row.backup_id; as sourceId) {
                          <button type="button" class="bea-admin-icon-btn" title="Sauvegarde source" aria-label="Sauvegarde source" (click)="details.set({ kind: 'backup', id: sourceId })">
                            <bea-admin-icon name="inventory_2" />
                          </button>
                        }
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="bea-admin-pager">
            <span>Page {{ page() }} / {{ totalPages() }} — {{ total() }} opération(s)</span>
            <div>
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() <= 1" (click)="go(page() - 1)">Précédent</button>
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" [disabled]="page() >= totalPages()" (click)="go(page() + 1)">Suivant</button>
            </div>
          </div>
        }
      </div>
    </section>

    @if (details(); as dt) {
      <bea-sr-details [kind]="dt.kind" [itemId]="dt.id" (closed)="details.set(null)" (changed)="load()" />
    }
  `,
})
export class CoreAdminSauvegardesHistoryComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly actions = inject(SrActionsService);
  private readonly router = inject(Router);
  readonly perms = srPermissions();
  readonly tz = TZ;
  readonly size = 20;

  readonly filters = signal<Record<string, string>>({});
  readonly items = signal<SrHistoryItem[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly loading = signal(false);
  readonly rowBusy = signal(false);
  readonly details = signal<{ kind: 'backup' | 'restore'; id: string } | null>(null);
  readonly selected = signal<Set<string>>(new Set());
  readonly deletable = computed(() => this.items().filter((r) => this.canDelete(r)));
  readonly allSelected = computed(
    () => this.deletable().length > 0 && this.deletable().every((r) => this.selected().has(r.id)),
  );

  readonly status = srStatusLabel;
  readonly backupType = srBackupTypeLabel;
  readonly bytes = srBytes;
  readonly user = srUser;
  readonly levelLabel = levelLabel;

  canDelete(row: SrHistoryItem): boolean {
    return row.kind === 'backup' && row.status !== 'running';
  }

  toggle(id: string, on: boolean): void {
    this.selected.update((s) => {
      const next = new Set(s);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  toggleAll(on: boolean): void {
    this.selected.set(on ? new Set(this.deletable().map((r) => r.id)) : new Set());
  }

  async removeOne(row: SrHistoryItem): Promise<void> {
    if (await this.actions.remove([{ id: row.id, label: srBackupLabel(row) }], this.rowBusy)) this.afterDelete();
  }

  async removeSelected(): Promise<void> {
    const rows = this.deletable().filter((r) => this.selected().has(r.id));
    const items = rows.map((r) => ({ id: r.id, label: srBackupLabel(r) }));
    if (await this.actions.remove(items, this.rowBusy)) this.afterDelete();
  }

  private afterDelete(): void {
    this.selected.set(new Set());
    this.load();
  }

  ngOnInit(): void {
    this.load();
  }

  setFilter(key: string, value: string): void {
    this.filters.update((f) => ({ ...f, [key]: value }));
    this.page.set(1);
    this.load();
  }

  go(page: number): void {
    this.page.set(page);
    this.load();
  }

  load(): void {
    const params: Record<string, string | number> = { page: this.page(), size: this.size };
    for (const [k, v] of Object.entries(this.filters())) if (v) params[k] = v;
    this.loading.set(true);
    this.api.get<{ items: SrHistoryItem[]; total: number }>(`${SR_API}/backups/history`, params).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.total.set(res.total);
        this.selected.update((s) => new Set([...s].filter((id) => res.items.some((i) => i.id === id))));
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  download(row: SrHistoryItem): void {
    this.actions.download(row.id, row.type, this.rowBusy).subscribe();
  }

  verify(row: SrHistoryItem): void {
    this.actions.verify(row.id, this.rowBusy).subscribe(() => this.load());
  }

  goRestore(id: string): void {
    void this.router.navigate(['/admin/sauvegardes/recovery'], { queryParams: { backup: id } });
  }
}
