import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import {
  CoreAdminGeneralSettings,
  CoreAdminMaintenanceSettings,
  CoreAdminSecurityCheck,
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
  imports: [DatePipe, FormsModule, RouterLink],
  template: `
    <section class="bea-admin-dash bea-admin-sec">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <p class="bea-admin-sec__kicker">CORE ADMIN · Paramètres</p>
          <h1>Sécurité</h1>
          <p>
            Centre de contrôle : supervision, actions, et politique éditable (persistée en base,
            appliquée immédiatement côté serveur).
          </p>
        </div>
        <div class="bea-admin-users__head-actions">
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reload()" [disabled]="loading()">
            Actualiser
          </button>
          <button
            type="button"
            class="bea-admin-btn bea-admin-btn--ghost"
            [disabled]="loading() || !data()"
            (click)="togglePolicyEditor()"
          >
            {{ editingPolicy() ? 'Masquer l’édition' : 'Modifier la politique' }}
          </button>
          <button type="button" class="bea-admin-btn" [disabled]="checking()" (click)="runCheck()">
            {{ checking() ? 'Contrôle…' : 'Lancer un contrôle' }}
          </button>
        </div>
      </header>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement du poste de sécurité…</p>
      } @else if (data(); as d) {
        <div class="bea-admin-kpis bea-admin-sec__kpis">
          <article class="bea-admin-kpi" data-tone="sessions">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Sessions actives</p>
              <p class="bea-admin-kpi__value">{{ d.sessions_actives }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="org">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Échecs (fenêtre)</p>
              <p class="bea-admin-kpi__value">{{ d.alertes_fenetre }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="modules">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">Comptes verrouillés</p>
              <p class="bea-admin-kpi__value">{{ d.comptes_verrouilles?.length || 0 }}</p>
            </div>
          </article>
          <article class="bea-admin-kpi" data-tone="users">
            <div class="bea-admin-kpi__copy">
              <p class="bea-admin-kpi__label">MFA actifs</p>
              <p class="bea-admin-kpi__value">{{ d.mfa_users_enabled ?? 0 }}</p>
            </div>
          </article>
        </div>

        <aside class="bea-admin-sec__banner" role="note">
          <strong>Politique runtime</strong>
          <span>
            Source :
            <em>{{ d.policy_source === 'database' ? 'base (overrides)' : 'environnement' }}</em>
            @if (d.policy_updated_at) {
              · maj {{ d.policy_updated_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
            }
            . Édition via
            <em>Modifier la politique</em>
            (confirmation
            <em>CONFIRMER</em>
            ) — JWT / secrets / credentials restent invisibles.
          </span>
        </aside>

        @if (editingPolicy()) {
          <section class="bea-admin-panel bea-admin-sec__panel bea-admin-sec__panel--edit">
            <p class="bea-admin-sec__kicker">Phase 3 · Édition</p>
            <h2>Modifier la politique</h2>
            <div class="bea-admin-sec__form">
              <label class="bea-admin-field">
                <span>Fenêtre lockout (min)</span>
                <input type="number" min="1" max="1440" [(ngModel)]="draft.lockoutWindow" />
              </label>
              <label class="bea-admin-field">
                <span>Échecs max</span>
                <input type="number" min="1" max="50" [(ngModel)]="draft.lockoutMax" />
              </label>
              <label class="bea-admin-field">
                <span>Longueur MDP min</span>
                <input type="number" min="8" max="128" [(ngModel)]="draft.pwdMin" />
              </label>
              <label class="bea-admin-field">
                <span>Login / min</span>
                <input type="number" min="1" [(ngModel)]="draft.rateLogin" />
              </label>
              <label class="bea-admin-field">
                <span>API / min</span>
                <input type="number" min="1" [(ngModel)]="draft.rateApi" />
              </label>
              <label class="bea-admin-field">
                <span>Sensible / min</span>
                <input type="number" min="1" [(ngModel)]="draft.rateSensitive" />
              </label>
              <label class="bea-admin-field">
                <span>Reset MDP / min</span>
                <input type="number" min="1" [(ngModel)]="draft.rateReset" />
              </label>
              <label class="bea-admin-sec__check">
                <input type="checkbox" [(ngModel)]="draft.pwdUpper" />
                <span>Exiger majuscule</span>
              </label>
              <label class="bea-admin-sec__check">
                <input type="checkbox" [(ngModel)]="draft.pwdLower" />
                <span>Exiger minuscule</span>
              </label>
              <label class="bea-admin-sec__check">
                <input type="checkbox" [(ngModel)]="draft.pwdDigit" />
                <span>Exiger chiffre</span>
              </label>
              <label class="bea-admin-sec__check">
                <input type="checkbox" [(ngModel)]="draft.pwdSpecial" />
                <span>Exiger caractère spécial</span>
              </label>
              <label class="bea-admin-sec__check">
                <input type="checkbox" [(ngModel)]="draft.mfaRequired" />
                <span>MFA obligatoire CORE ADMIN</span>
              </label>
              <label class="bea-admin-sec__check">
                <input type="checkbox" [(ngModel)]="draft.rateEnabled" />
                <span>Rate limiting activé</span>
              </label>
            </div>
            <div class="bea-admin-sec__confirm">
              <label class="bea-admin-field">
                <span>Confirmation — tapez CONFIRMER</span>
                <input
                  type="text"
                  [(ngModel)]="confirmPhrase"
                  placeholder="CONFIRMER"
                  autocomplete="off"
                />
              </label>
              <button
                type="button"
                class="bea-admin-btn bea-admin-btn--ghost"
                [disabled]="saving()"
                (click)="editingPolicy.set(false)"
              >
                Annuler
              </button>
              <button
                type="button"
                class="bea-admin-btn"
                [disabled]="saving() || confirmPhrase.trim().toUpperCase() !== 'CONFIRMER'"
                (click)="savePolicy()"
              >
                {{ saving() ? 'Enregistrement…' : 'Appliquer la politique' }}
              </button>
            </div>
          </section>
        }

        <div class="bea-admin-sec__etat">
          @for (item of etatItems(d); track item.key; let i = $index) {
            <article class="bea-admin-sec__chip" [attr.data-ok]="item.ok" [style.--delay]="i * 40 + 'ms'">
              <span
                class="bea-admin-health__dot"
                [class.bea-admin-health__dot--ok]="item.ok"
                [class.bea-admin-health__dot--ko]="!item.ok"
              ></span>
              <div>
                <strong>{{ item.label }}</strong>
                <em>{{ item.ok ? 'Opérationnel' : 'Dégradé' }}</em>
              </div>
              <span class="bea-admin-sec__pill" [attr.data-ok]="item.ok">
                {{ item.ok ? 'OK' : 'KO' }}
              </span>
            </article>
          }
        </div>
        @if (d.verifie_at) {
          <p class="bea-admin-sec__meta">
            Lecture :
            {{ d.verifie_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
            · {{ d.fuseau || 'Africa/Nouakchott' }} · env {{ d.app_env }}
          </p>
        }

        <nav class="bea-admin-sec__actions" aria-label="Actions sécurité">
          <a class="bea-admin-sec__action" routerLink="/admin/sessions">
            <span class="bea-admin-sec__action-kicker">Opération</span>
            <strong>Gérer les sessions</strong>
            <span>Révoquer Login 1 / Login 2</span>
          </a>
          <a class="bea-admin-sec__action" routerLink="/admin/alerts">
            <span class="bea-admin-sec__action-kicker">Supervision</span>
            <strong>Alertes login</strong>
            <span>Échecs et tentatives</span>
          </a>
          <a class="bea-admin-sec__action" routerLink="/admin/users">
            <span class="bea-admin-sec__action-kicker">Comptes</span>
            <strong>Utilisateurs & MDP</strong>
            <span>Reset accès, MFA</span>
          </a>
          <a class="bea-admin-sec__action" routerLink="/admin/audit">
            <span class="bea-admin-sec__action-kicker">Traçabilité</span>
            <strong>Journal d’audit</strong>
            <span>Login, unlock, revoke…</span>
          </a>
        </nav>

        @if (check(); as c) {
          <section class="bea-admin-panel bea-admin-sec__panel bea-admin-sec__panel--check">
            <p class="bea-admin-sec__kicker">Diagnostic</p>
            <div class="bea-admin-users__list-head">
              <h2>Contrôle de sécurité</h2>
              <p>
                {{ c.ok_count }} OK · {{ c.warn_count }} à vérifier · {{ c.ko_count }} problème(s)
              </p>
            </div>
            <ul class="bea-admin-sec__checks">
              @for (row of c.items; track row.key; let i = $index) {
                <li [attr.data-status]="row.status" [style.--delay]="i * 35 + 'ms'">
                  <span class="bea-admin-sec__mark">{{ statusMark(row.status) }}</span>
                  <div>
                    <strong>{{ row.label }}</strong>
                    <span>{{ row.detail }}</span>
                  </div>
                </li>
              }
            </ul>
          </section>
        }

        <div class="bea-admin-sec__grid">
          <section class="bea-admin-panel bea-admin-sec__panel">
            <p class="bea-admin-sec__kicker">Politique active</p>
            <h2>Authentification & lockout</h2>
            <dl class="bea-admin-dl">
              <div><dt>Fenêtre lockout</dt><dd>{{ d.login_lockout_window_minutes }} min</dd></div>
              <div><dt>Échecs max</dt><dd>{{ d.login_lockout_max_failures }}</dd></div>
              <div><dt>Échecs (fenêtre)</dt><dd>{{ d.alertes_fenetre }}</dd></div>
              <div><dt>Algorithme JWT</dt><dd><code>{{ d.jwt_algorithm }}</code></dd></div>
              <div><dt>Access token</dt><dd>{{ d.access_token_expire_minutes }} min</dd></div>
              <div><dt>Refresh plateforme</dt><dd>{{ d.refresh_token_expire_days }} j</dd></div>
              <div><dt>Refresh module</dt><dd>{{ d.module_refresh_token_expire_minutes }} min</dd></div>
              <div><dt>Clé JWT</dt><dd>{{ secretLabel(d.secret_key_status) }}</dd></div>
            </dl>
          </section>

          <section class="bea-admin-panel bea-admin-sec__panel">
            <p class="bea-admin-sec__kicker">Runtime</p>
            <h2>Sessions Login 1 / Login 2</h2>
            <div class="bea-admin-sec__stats">
              <article><span>Actives</span><strong>{{ d.sessions_actives }}</strong></article>
              <article><span>Plateforme</span><strong>{{ d.sessions_platform ?? '—' }}</strong></article>
              <article><span>Module</span><strong>{{ d.sessions_module ?? '—' }}</strong></article>
            </div>
            <a class="bea-admin-btn bea-admin-sec__cta" routerLink="/admin/sessions">Ouvrir Sessions</a>
          </section>

          <section class="bea-admin-panel bea-admin-sec__panel">
            <p class="bea-admin-sec__kicker">Politique active</p>
            <h2>Mots de passe</h2>
            @if (d.password_policy; as p) {
              <dl class="bea-admin-dl">
                <div><dt>Hash</dt><dd><code>{{ p.hash_algorithm }}</code></dd></div>
                <div><dt>Longueur min</dt><dd>{{ p.min_length }}</dd></div>
                <div><dt>Majuscule</dt><dd>{{ yesNo(p.require_uppercase) }}</dd></div>
                <div><dt>Minuscule</dt><dd>{{ yesNo(p.require_lowercase) }}</dd></div>
                <div><dt>Chiffre</dt><dd>{{ yesNo(p.require_digit) }}</dd></div>
                <div><dt>Spécial</dt><dd>{{ yesNo(p.require_special) }}</dd></div>
              </dl>
            }
            <a class="bea-admin-btn bea-admin-btn--ghost bea-admin-sec__cta" routerLink="/admin/users"
              >Reset accès utilisateur</a
            >
          </section>

          <section class="bea-admin-panel bea-admin-sec__panel">
            <p class="bea-admin-sec__kicker">Politique active</p>
            <h2>MFA & rate limit</h2>
            <dl class="bea-admin-dl">
              <div>
                <dt>MFA CORE ADMIN</dt>
                <dd>
                  <span class="bea-admin-sec__flag" [attr.data-on]="!!d.mfa_required_for_core_admin">
                    {{ d.mfa_required_for_core_admin ? 'Activé' : 'Désactivé' }}
                  </span>
                </dd>
              </div>
              <div><dt>Comptes 2FA</dt><dd>{{ d.mfa_users_enabled ?? 0 }}</dd></div>
              <div><dt>Superusers sans MFA</dt><dd>{{ d.mfa_admins_without ?? 0 }}</dd></div>
              <div>
                <dt>Rate limiting</dt>
                <dd>
                  <span class="bea-admin-sec__flag" [attr.data-on]="!!d.rate_limit_enabled">
                    {{ d.rate_limit_enabled ? 'Activé' : 'Désactivé' }}
                  </span>
                </dd>
              </div>
              @if (d.rate_limit; as r) {
                <div><dt>Login / min</dt><dd>{{ r.login_per_minute }}</dd></div>
                <div><dt>API / min</dt><dd>{{ r.api_per_minute }}</dd></div>
              }
            </dl>
          </section>

          <section class="bea-admin-panel bea-admin-sec__panel">
            <p class="bea-admin-sec__kicker">Transport</p>
            <h2>API & infrastructure</h2>
            <dl class="bea-admin-dl">
              <div><dt>Headers sécu</dt><dd>{{ yesNo(!!d.security_headers_enabled) }}</dd></div>
              <div><dt>Docs OpenAPI</dt><dd>{{ d.api_docs_enabled ? 'Exposées' : 'Désactivées' }}</dd></div>
              <div><dt>Debug</dt><dd>{{ yesNo(!!d.app_debug) }}</dd></div>
              <div><dt>SSL base</dt><dd>{{ sslLabel(d.database_ssl) }}</dd></div>
              <div><dt>Upload</dt><dd>{{ d.upload_dir_exists ? 'Présent' : 'Absent' }}</dd></div>
              <div><dt>GED</dt><dd>{{ d.ged_dir_exists ? 'Présent' : 'Absent' }}</dd></div>
            </dl>
          </section>
        </div>

        <section class="bea-admin-panel bea-admin-sec__panel bea-admin-sec__panel--blocks">
          <p class="bea-admin-sec__kicker">Actions</p>
          <div class="bea-admin-users__list-head">
            <div>
              <h2>Blocages (lockout)</h2>
              <p>Comptes au seuil d’échecs — déverrouillage immédiat possible.</p>
            </div>
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/alerts">Voir alertes</a>
          </div>
          @if (!d.comptes_verrouilles?.length) {
            <p class="bea-admin-panel__empty">Aucun compte verrouillé sur la fenêtre courante.</p>
          } @else {
            <div class="bea-admin-table-wrap">
              <table class="bea-admin-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Échecs</th>
                    <th>Fenêtre</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of d.comptes_verrouilles!; track row.email) {
                    <tr>
                      <td>
                        <strong>{{ row.email }}</strong>
                      </td>
                      <td>{{ row.echecs }}</td>
                      <td>{{ row.fenetre_minutes }} min</td>
                      <td class="bea-admin-table__actions">
                        <button
                          type="button"
                          class="bea-admin-btn bea-admin-btn--ghost"
                          [disabled]="unlocking() === row.email"
                          (click)="unlock(row.email)"
                        >
                          {{ unlocking() === row.email ? '…' : 'Déverrouiller' }}
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </section>
      }
    </section>
  `,
})
export class CoreAdminSecurityComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);
  readonly loading = signal(true);
  readonly checking = signal(false);
  readonly saving = signal(false);
  readonly editingPolicy = signal(false);
  readonly unlocking = signal('');
  readonly erreur = signal('');
  readonly data = signal<CoreAdminSecuritySettings | null>(null);
  readonly check = signal<CoreAdminSecurityCheck | null>(null);
  confirmPhrase = '';
  draft = {
    lockoutWindow: 15,
    lockoutMax: 5,
    pwdMin: 10,
    pwdUpper: true,
    pwdLower: true,
    pwdDigit: true,
    pwdSpecial: true,
    mfaRequired: false,
    rateEnabled: true,
    rateLogin: 20,
    rateApi: 300,
    rateSensitive: 60,
    rateReset: 10,
  };

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.erreur.set('');
    this.api.get<CoreAdminSecuritySettings>('/plateforme/admin/settings/security').subscribe({
      next: (data) => {
        this.data.set(data);
        this.syncDraft(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger la sécurité.'));
      },
    });
  }

  syncDraft(d: CoreAdminSecuritySettings): void {
    this.draft = {
      lockoutWindow: d.login_lockout_window_minutes,
      lockoutMax: d.login_lockout_max_failures,
      pwdMin: d.password_policy?.min_length ?? 10,
      pwdUpper: !!d.password_policy?.require_uppercase,
      pwdLower: !!d.password_policy?.require_lowercase,
      pwdDigit: !!d.password_policy?.require_digit,
      pwdSpecial: !!d.password_policy?.require_special,
      mfaRequired: !!d.mfa_required_for_core_admin,
      rateEnabled: d.rate_limit_enabled !== false,
      rateLogin: d.rate_limit?.login_per_minute ?? 20,
      rateApi: d.rate_limit?.api_per_minute ?? 300,
      rateSensitive: d.rate_limit?.sensitive_per_minute ?? 60,
      rateReset: d.rate_limit?.password_reset_per_minute ?? 10,
    };
  }

  togglePolicyEditor(): void {
    const next = !this.editingPolicy();
    this.editingPolicy.set(next);
    this.confirmPhrase = '';
    const current = this.data();
    if (next && current) this.syncDraft(current);
  }

  etatItems(d: CoreAdminSecuritySettings) {
    return Object.entries(d.etat ?? {}).map(([key, value]) => ({
      key,
      label: value.label,
      ok: value.ok,
    }));
  }

  yesNo(v: boolean): string {
    return v ? 'Oui' : 'Non';
  }

  statusMark(status: string): string {
    if (status === 'ok') return '✓';
    if (status === 'warn') return '⚠';
    return '✕';
  }

  secretLabel(status?: string): string {
    if (status === 'a_changer') return 'À changer (défaut)';
    if (status === 'configure') return 'Configurée';
    return 'Non vérifié';
  }

  sslLabel(status?: string): string {
    if (status === 'configure_verifie') return 'Configuré / vérifié';
    if (status === 'configure') return 'Configuré';
    if (status === 'non_configure') return 'Non configuré';
    return 'Non vérifié';
  }

  runCheck(): void {
    if (this.checking()) return;
    this.checking.set(true);
    this.erreur.set('');
    this.api.post<CoreAdminSecurityCheck>('/plateforme/admin/settings/security/check', {}).subscribe({
      next: (res) => {
        this.check.set(res);
        this.checking.set(false);
      },
      error: (err) => {
        this.checking.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Contrôle impossible.'));
      },
    });
  }

  async savePolicy(): Promise<void> {
    if (this.saving() || this.confirmPhrase.trim().toUpperCase() !== 'CONFIRMER') return;
    const ok = await this.dialogs.confirm({
      title: 'Appliquer la politique sécurité',
      message:
        'Ces paramètres s’appliquent immédiatement (lockout, MDP, MFA, rate limit).\n' +
        'Confirmez-vous la modification ?',
      confirmLabel: 'Appliquer',
      cancelLabel: 'Annuler',
      tone: 'warn',
    });
    if (!ok) return;

    this.saving.set(true);
    this.erreur.set('');
    this.api
      .patch<CoreAdminSecuritySettings>('/plateforme/admin/settings/security/policy', {
        confirmation_phrase: 'CONFIRMER',
        login_lockout_window_minutes: Number(this.draft.lockoutWindow),
        login_lockout_max_failures: Number(this.draft.lockoutMax),
        password_min_length: Number(this.draft.pwdMin),
        password_require_uppercase: this.draft.pwdUpper,
        password_require_lowercase: this.draft.pwdLower,
        password_require_digit: this.draft.pwdDigit,
        password_require_special: this.draft.pwdSpecial,
        mfa_required_for_core_admin: this.draft.mfaRequired,
        rate_limit_enabled: this.draft.rateEnabled,
        rate_limit_login_per_minute: Number(this.draft.rateLogin),
        rate_limit_api_per_minute: Number(this.draft.rateApi),
        rate_limit_sensitive_per_minute: Number(this.draft.rateSensitive),
        rate_limit_password_reset_per_minute: Number(this.draft.rateReset),
      })
      .subscribe({
        next: async (data) => {
          this.saving.set(false);
          this.confirmPhrase = '';
          this.editingPolicy.set(false);
          this.data.set(data);
          this.syncDraft(data);
          await this.dialogs.success('Politique sécurité mise à jour et appliquée.', 'Enregistré');
        },
        error: (err) => {
          this.saving.set(false);
          const msg = coreAdminOpsError(err, 'Échec enregistrement politique.');
          this.erreur.set(msg);
          void this.dialogs.error(msg);
        },
      });
  }

  async unlock(email: string): Promise<void> {
    if (this.unlocking()) return;
    const ok = await this.dialogs.confirm({
      title: 'Déverrouiller le compte',
      message:
        `Effacer les échecs de connexion récents pour « ${email} » ?\n` +
        `Le compte pourra à nouveau tenter Login 1 / Login 2.`,
      confirmLabel: 'Déverrouiller',
      cancelLabel: 'Annuler',
      tone: 'warn',
    });
    if (!ok) return;

    this.unlocking.set(email);
    this.erreur.set('');
    this.api
      .post<{ email: string; cleared_failures: number }>('/plateforme/admin/settings/security/unlock', {
        email,
      })
      .subscribe({
        next: async (res) => {
          this.unlocking.set('');
          await this.dialogs.success(
            `${res.cleared_failures} échec(s) effacé(s) pour ${res.email}.`,
            'Compte déverrouillé',
          );
          this.reload();
        },
        error: (err) => {
          this.unlocking.set('');
          const msg = coreAdminOpsError(err, 'Déverrouillage impossible.');
          this.erreur.set(msg);
          void this.dialogs.error(msg);
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
