import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import {
  CoreAdminGeneralSettings,
  CoreAdminMaintenanceSettings,
  CoreAdminSecuritySettings,
  coreAdminOpsError,
} from './core-admin-ops.models';

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
  selector: 'bea-core-admin-security',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Sécurité</h1>
          <p>Lockout Login 1 / Login 2 et indicateurs courants — configuration via variables d’environnement.</p>
        </div>
        <a class="bea-admin-btn" routerLink="/admin/alerts">Voir les alertes</a>
      </header>
      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement…</p>
      } @else if (data(); as d) {
        <div class="bea-admin-panel">
          <h2>Lockout</h2>
          <dl class="bea-admin-dl">
            <div><dt>Fenêtre</dt><dd>{{ d.login_lockout_window_minutes }} min</dd></div>
            <div><dt>Échecs max</dt><dd>{{ d.login_lockout_max_failures }}</dd></div>
            <div><dt>Algorithme JWT</dt><dd><code>{{ d.jwt_algorithm }}</code></dd></div>
            <div><dt>Alertes (fenêtre)</dt><dd>{{ d.alertes_fenetre }}</dd></div>
            <div><dt>Sessions actives</dt><dd>{{ d.sessions_actives }}</dd></div>
          </dl>
        </div>
      }
    </section>
  `,
})
export class CoreAdminSecurityComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly data = signal<CoreAdminSecuritySettings | null>(null);

  ngOnInit(): void {
    this.api.get<CoreAdminSecuritySettings>('/plateforme/admin/settings/security').subscribe({
      next: (data) => {
        this.data.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger la sécurité.'));
      },
    });
  }
}

@Component({
  selector: 'bea-core-admin-maintenance',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [],
  template: `
    <section class="bea-admin-dash">
      <header class="bea-admin-dash__head">
        <div>
          <h1>Maintenance</h1>
          <p>État runtime de la plateforme — pas d’action destructive depuis cet écran.</p>
        </div>
      </header>
      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement…</p>
      } @else if (data(); as d) {
        <div class="bea-admin-panels bea-admin-panels--equal">
          <section class="bea-admin-panel">
            <h2>Santé</h2>
            <ul class="bea-admin-health">
              @for (item of healthItems(d); track item.key) {
                <li>
                  <span
                    class="bea-admin-health__dot"
                    [class.bea-admin-health__dot--ok]="item.ok"
                    [class.bea-admin-health__dot--ko]="!item.ok"
                  ></span>
                  <span>{{ item.label }}</span>
                  <strong>{{ item.ok ? 'OK' : 'KO' }}</strong>
                </li>
              }
            </ul>
          </section>
          <section class="bea-admin-panel">
            <h2>Runtime</h2>
            <dl class="bea-admin-dl">
              <div><dt>Environnement</dt><dd>{{ d.app_env }}</dd></div>
              <div><dt>SKIP_MIGRATIONS</dt><dd>{{ d.skip_migrations ? '1 (actif)' : '0' }}</dd></div>
              <div><dt>Modules actifs</dt><dd>{{ d.modules_actifs }} / {{ d.modules_total }}</dd></div>
              <div><dt>Sessions actives</dt><dd>{{ d.sessions_actives }}</dd></div>
              <div><dt>Dossier upload</dt><dd>{{ d.upload_dir_exists ? 'Présent' : 'Absent' }}</dd></div>
              <div><dt>Dossier GED</dt><dd>{{ d.ged_dir_exists ? 'Présent' : 'Absent' }}</dd></div>
            </dl>
          </section>
        </div>
      }
    </section>
  `,
})
export class CoreAdminMaintenanceComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly data = signal<CoreAdminMaintenanceSettings | null>(null);

  ngOnInit(): void {
    this.api.get<CoreAdminMaintenanceSettings>('/plateforme/admin/settings/maintenance').subscribe({
      next: (data) => {
        this.data.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger la maintenance.'));
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
