import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import {
  CoreAdminGeneralSettings,
  CoreAdminMaintenanceSettings,
  coreAdminOpsError,
} from './core-admin-ops.models';

export { CoreAdminSecurityComponent } from './core-admin-security-center.component';

@Component({
  selector: 'bea-core-admin-general',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Général</h1>
          <p>Paramètres plateforme en lecture seule (variables d’environnement) — sans secrets.</p>
        </div>
        <div class="bea-admin-users__head-actions">
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/security">Sécurité</a>
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/maintenance">Maintenance</a>
        </div>
      </header>
      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement…</p>
      } @else if (data(); as d) {
        <div class="bea-admin-panel">
          <h2>Application</h2>
          <dl class="bea-admin-dl">
            <div><dt>Nom</dt><dd>{{ d.app_name }}</dd></div>
            <div><dt>Environnement</dt><dd>{{ d.app_env }}</dd></div>
            <div><dt>Debug</dt><dd>{{ d.app_debug ? 'Oui' : 'Non' }}</dd></div>
            <div><dt>Préfixe API</dt><dd><code>{{ d.api_v1_prefix }}</code></dd></div>
            <div><dt>Fuseau</dt><dd>{{ d.fuseau }}</dd></div>
            <div><dt>CORS</dt><dd>{{ d.cors_origins.join(', ') || '—' }}</dd></div>
            <div><dt>Upload</dt><dd><code>{{ d.upload_dir }}</code></dd></div>
            <div><dt>GED</dt><dd><code>{{ d.ged_dir }}</code></dd></div>
            <div><dt>Access token</dt><dd>{{ d.access_token_expire_minutes }} min</dd></div>
            <div><dt>Refresh platform</dt><dd>{{ d.refresh_token_expire_days }} j</dd></div>
            <div><dt>Refresh module</dt><dd>{{ d.module_refresh_token_expire_minutes }} min</dd></div>
          </dl>
        </div>
      }
    </section>
  `,
})
export class CoreAdminGeneralComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly data = signal<CoreAdminGeneralSettings | null>(null);

  ngOnInit(): void {
    this.api.get<CoreAdminGeneralSettings>('/plateforme/admin/settings/general').subscribe({
      next: (data) => {
        this.data.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger les paramètres.'));
      },
    });
  }
}

@Component({
  selector: 'bea-core-admin-maintenance',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash bea-admin-maint">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Maintenance</h1>
          <p>Santé runtime et mise en maintenance globale / par module.</p>
        </div>
        <div class="bea-admin-users__head-actions">
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/module-states"
            >État des modules</a
          >
          <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/supervision"
            >Supervision</a
          >
        </div>
      </header>
      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement…</p>
      } @else if (data(); as d) {
        <div class="bea-admin-panels bea-admin-panels--equal">
          <section class="bea-admin-panel bea-admin-maint__card">
            <p class="bea-admin-maint__kicker">Runtime</p>
            <h2>Santé</h2>
            <ul class="bea-admin-maint__health">
              @for (item of healthItems(d); track item.key; let i = $index) {
                <li [style.--delay]="i * 40 + 'ms'">
                  <span
                    class="bea-admin-health__dot"
                    [class.bea-admin-health__dot--ok]="item.ok"
                    [class.bea-admin-health__dot--ko]="!item.ok"
                  ></span>
                  <span class="bea-admin-maint__health-label">{{ item.label }}</span>
                  <strong
                    class="bea-admin-maint__badge"
                    [class.bea-admin-maint__badge--ok]="item.ok"
                    [class.bea-admin-maint__badge--ko]="!item.ok"
                  >
                    {{ item.ok ? 'OK' : 'KO' }}
                  </strong>
                </li>
              }
            </ul>
          </section>
          <section class="bea-admin-panel bea-admin-maint__card">
            <p class="bea-admin-maint__kicker">Plateforme</p>
            <h2>Runtime</h2>
            <div class="bea-admin-maint__stats">
              <article class="bea-admin-maint__stat">
                <span>Environnement</span>
                <strong>{{ d.app_env }}</strong>
              </article>
              <article class="bea-admin-maint__stat">
                <span>SKIP_MIGRATIONS</span>
                <strong>{{ d.skip_migrations ? '1 (actif)' : '0' }}</strong>
              </article>
              <article class="bea-admin-maint__stat">
                <span>Modules actifs</span>
                <strong>{{ d.modules_actifs }} / {{ d.modules_total }}</strong>
              </article>
              <article class="bea-admin-maint__stat">
                <span>Sessions actives</span>
                <strong>{{ d.sessions_actives }}</strong>
              </article>
              <article class="bea-admin-maint__stat">
                <span>Dossier upload</span>
                <strong>{{ d.upload_dir_exists ? 'Présent' : 'Absent' }}</strong>
              </article>
              <article class="bea-admin-maint__stat">
                <span>Dossier GED</span>
                <strong>{{ d.ged_dir_exists ? 'Présent' : 'Absent' }}</strong>
              </article>
            </div>
          </section>
        </div>
      }
      @if (control(); as c) {
        <section class="bea-admin-panel bea-admin-maint__card bea-admin-maint__global">
          <p class="bea-admin-maint__kicker">Continuité</p>
          <h2>Maintenance globale BEA-DIGITAL</h2>
          <div class="bea-admin-maint__form">
            <label class="bea-admin-maint__check">
              <input type="checkbox" [(ngModel)]="globalEnabled" />
              <span>Activer la maintenance globale</span>
            </label>
            <label class="bea-admin-field">
              <span>Titre</span>
              <input [(ngModel)]="globalTitle" />
            </label>
            <label class="bea-admin-field">
              <span>Message</span>
              <textarea rows="3" [(ngModel)]="globalMessage"></textarea>
            </label>
            <label class="bea-admin-maint__check">
              <input type="checkbox" [(ngModel)]="globalBypass" />
              <span>Administrateurs autorisés peuvent accéder</span>
            </label>
            <button type="button" class="bea-admin-btn bea-admin-maint__submit" (click)="saveGlobal()">
              Enregistrer
            </button>
          </div>
        </section>
      }
    </section>
  `,
})
export class CoreAdminMaintenanceComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly data = signal<CoreAdminMaintenanceSettings | null>(null);
  readonly control = signal<{ global: any } | null>(null);
  globalEnabled = false;
  globalTitle = '';
  globalMessage = '';
  globalBypass = true;

  ngOnInit(): void {
    this.api.get<CoreAdminMaintenanceSettings>('/plateforme/admin/settings/maintenance').subscribe({
      next: (data) => {
        this.data.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        const msg = coreAdminOpsError(err, 'Impossible de charger la maintenance.');
        this.erreur.set(msg);
        void this.dialogs.error(msg);
      },
    });
    this.api.get<{ global: any }>('/plateforme/admin/maintenance/control').subscribe({
      next: (c) => {
        this.control.set(c);
        this.globalEnabled = !!c.global?.enabled;
        this.globalTitle = c.global?.title || '';
        this.globalMessage = c.global?.message || '';
        this.globalBypass = c.global?.admins_bypass !== false;
      },
      error: () => undefined,
    });
  }

  async saveGlobal(): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: this.globalEnabled ? 'Activer la maintenance globale' : 'Désactiver la maintenance globale',
      message: this.globalEnabled
        ? 'BEA-DIGITAL passera en maintenance globale. Confirmer ?'
        : 'Retirer la maintenance globale et rouvrir la plateforme ?',
      confirmLabel: 'Confirmer',
      cancelLabel: 'Annuler',
      tone: this.globalEnabled ? 'warn' : 'success',
    });
    if (!ok) return;

    this.api
      .put('/plateforme/admin/maintenance/control/global', {
        enabled: this.globalEnabled,
        title: this.globalTitle,
        message: this.globalMessage,
        admins_bypass: this.globalBypass,
      })
      .subscribe({
        next: (g: any) => {
          this.control.update((c) => (c ? { ...c, global: g } : { global: g }));
          void this.dialogs.success(
            this.globalEnabled
              ? 'Maintenance globale activée.'
              : 'Maintenance globale désactivée.',
            'Maintenance',
          );
        },
        error: (err) => {
          const msg = coreAdminOpsError(err, 'Échec maintenance globale');
          this.erreur.set(msg);
          void this.dialogs.error(msg, 'Action impossible');
        },
      });
  }

  healthItems(d: CoreAdminMaintenanceSettings) {
    return Object.entries(d.etat ?? {}).map(([key, value]) => ({
      key,
      label: value.label,
      ok: value.ok,
    }));
  }
}
