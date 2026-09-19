import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import {
  CoreAdminAuditPage,
  CoreAdminAuditRow,
  coreAdminAuditActionLabel,
} from './core-admin-audit.models';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import {
  CoreAdminSecurityCheck,
  CoreAdminSecuritySettings,
  coreAdminOpsError,
} from './core-admin-ops.models';
import {
  CoreAdminSessionKind,
  CoreAdminSessionPage,
  CoreAdminSessionRow,
  CoreAdminSessionStatus,
  sessionKindLabel,
  sessionStatusLabel,
} from './core-admin-sessions.models';
import { SecurityUserHit, SecurityUserSearchComponent } from './security-user-search.component';

export type SecPageId =
  | 'vue'
  | 'auth'
  | 'sessions'
  | 'mdp'
  | 'mfa'
  | 'infra'
  | 'audit'
  | 'continuite'
  | 'incidents'
  | 'controle';

interface SecCard {
  id: SecPageId;
  title: string;
  subtitle: string;
}

interface SecurityOverview {
  utilisateurs_total?: number;
  utilisateurs_actifs: number;
  sessions_actives: number;
  sessions_platform?: number;
  sessions_module?: number;
  mfa_actives?: number;
  mfa_pct: number;
  comptes_verrouilles: number;
  alertes: number;
  incidents_ouverts?: number;
  incidents_critiques?: number;
  dernier_audit?: string | null;
  derniere_sauvegarde?: string | null;
  etat?: Record<string, { ok: boolean; label: string; status?: string; detail?: string }>;
  verifie_at?: string | null;
  fuseau?: string;
  snapshot?: CoreAdminSecuritySettings;
}

interface SecurityUserDossier {
  id: string;
  full_name: string;
  email: string;
  phone?: string | null;
  login?: string;
  is_active?: boolean;
  totp_enabled?: boolean;
  is_superuser?: boolean;
  last_login_at?: string | null;
  sessions_actives?: number;
  login1: string;
  login2: string;
  password_shared: boolean;
  note_auth: string;
  espaces?: Array<{ code: string; label: string }>;
  modules?: Array<{ code: string; label: string }>;
}

interface SecurityIncidentRow {
  id: string;
  titre: string;
  description?: string | null;
  type_incident: string;
  niveau: string;
  statut: string;
  responsable?: string | null;
  actions?: string | null;
  resolution?: string | null;
  module_code?: string | null;
  espace_code?: string | null;
  closed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface BackupRow {
  id: string;
  level: string;
  backup_type: string;
  status: string;
  size_bytes?: number;
  label?: string | null;
  created_at?: string | null;
}

const SEC_CARDS_TOP: SecCard[] = [
  { id: 'vue', title: 'Vue d’ensemble', subtitle: 'KPIs et état des composants' },
  { id: 'auth', title: 'Authentification', subtitle: 'Login 1 / 2, lockout, politique' },
  { id: 'sessions', title: 'Sessions', subtitle: 'Révoquer Login 1 / Login 2' },
  { id: 'audit', title: 'Audit', subtitle: 'Journal des actions sécurité' },
  { id: 'continuite', title: 'Continuité', subtitle: 'Sauvegardes et recovery' },
  { id: 'incidents', title: 'Incidents', subtitle: 'Suivi et traitement' },
];

const SEC_CARDS_BOTTOM: SecCard[] = [
  { id: 'mdp', title: 'Mots de passe', subtitle: 'Login partagé et reset admin' },
  { id: 'mfa', title: 'MFA', subtitle: 'TOTP et politique CORE ADMIN' },
  { id: 'infra', title: 'Infrastructure', subtitle: 'SSL, HTTPS, CORS, disques' },
  { id: 'controle', title: 'Contrôle', subtitle: 'Diagnostic et déverrouillage' },
];

const INCIDENT_TYPES = [
  'authentification',
  'compte_compromis',
  'tentatives',
  'acces',
  'donnee',
  'infrastructure',
  'malware',
  'configuration',
  'autre',
] as const;

const INCIDENT_NIVEAUX = ['faible', 'moyen', 'eleve', 'critique'] as const;
const INCIDENT_STATUTS = ['ouvert', 'en_analyse', 'en_traitement', 'resolu', 'clos'] as const;

@Component({
  selector: 'bea-core-admin-security',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, FormsModule, RouterLink, SecurityUserSearchComponent, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash bea-sec-hub" [class.bea-sec-hub--overlay]="!!activePage()">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Sécurité</h1>
          <p>Centre de contrôle CORE ADMIN — ouvrez une carte pour consulter ou agir.</p>
        </div>
        <div class="bea-admin-users__head-actions">
          <button
            type="button"
            class="bea-admin-btn bea-admin-btn--refresh"
            (click)="refreshHub()"
            [disabled]="loading()"
          >
            <bea-admin-icon name="refresh" />
            Actualiser
          </button>
        </div>
      </header>

      @if (hubErreur()) {
        <p class="bea-admin-dash__error">{{ hubErreur() }}</p>
      }

      <div class="bea-sec-hub__grids">
        <div class="bea-sec-hub__grid bea-sec-hub__grid--top" role="list">
          @for (card of cardsTop; track card.id) {
            <button
              type="button"
              class="bea-sec-card"
              role="listitem"
              (click)="openPage(card.id)"
            >
              <strong class="bea-sec-card__title">{{ card.title }}</strong>
              <span class="bea-sec-card__sub">{{ card.subtitle }}</span>
            </button>
          }
        </div>
        <div class="bea-sec-hub__grid bea-sec-hub__grid--bottom" role="list">
          @for (card of cardsBottom; track card.id) {
            <button
              type="button"
              class="bea-sec-card"
              role="listitem"
              (click)="openPage(card.id)"
            >
              <strong class="bea-sec-card__title">{{ card.title }}</strong>
              <span class="bea-sec-card__sub">{{ card.subtitle }}</span>
            </button>
          }
        </div>
      </div>

      @if (activePage(); as page) {
        <div class="bea-sec-overlay" role="dialog" [attr.aria-label]="pageTitle(page)">
          <header class="bea-sec-overlay__head">
            <button type="button" class="bea-sec-overlay__back" (click)="closePage()">
              ← Sécurité / {{ pageTitle(page) }}
            </button>
            <button
              type="button"
              class="bea-sec-overlay__close"
              (click)="closePage()"
              aria-label="Fermer"
            >
              ✕
            </button>
          </header>
          <div class="bea-sec-overlay__body bea-sec-page">
            @if (pageErreur()) {
              <p class="bea-admin-dash__error">{{ pageErreur() }}</p>
            }

            @switch (page) {
              @case ('vue') {
                <div class="bea-sec-page__toolbar">
                  <button
                    type="button"
                    class="bea-admin-btn bea-admin-btn--refresh"
                    (click)="loadOverview()"
                    [disabled]="loading()"
                  >
                    Actualiser
                  </button>
                </div>
                @if (loading()) {
                  <p class="bea-admin-dash__loading">Chargement de la vue…</p>
                } @else if (overview(); as o) {
                  <div class="bea-admin-kpis bea-sec-page__kpis">
                    <article class="bea-admin-kpi" data-tone="users">
                      <div class="bea-admin-kpi__copy">
                        <p class="bea-admin-kpi__label">Users actifs</p>
                        <p class="bea-admin-kpi__value">{{ o.utilisateurs_actifs }}</p>
                      </div>
                    </article>
                    <article class="bea-admin-kpi" data-tone="sessions">
                      <div class="bea-admin-kpi__copy">
                        <p class="bea-admin-kpi__label">Sessions</p>
                        <p class="bea-admin-kpi__value">{{ o.sessions_actives }}</p>
                      </div>
                    </article>
                    <article class="bea-admin-kpi" data-tone="modules">
                      <div class="bea-admin-kpi__copy">
                        <p class="bea-admin-kpi__label">MFA %</p>
                        <p class="bea-admin-kpi__value">{{ o.mfa_pct }}%</p>
                      </div>
                    </article>
                    <article class="bea-admin-kpi" data-tone="org">
                      <div class="bea-admin-kpi__copy">
                        <p class="bea-admin-kpi__label">Comptes verrouillés</p>
                        <p class="bea-admin-kpi__value">{{ o.comptes_verrouilles }}</p>
                      </div>
                    </article>
                    <article class="bea-admin-kpi" data-tone="org">
                      <div class="bea-admin-kpi__copy">
                        <p class="bea-admin-kpi__label">Alertes</p>
                        <p class="bea-admin-kpi__value">{{ o.alertes }}</p>
                      </div>
                    </article>
                    <article class="bea-admin-kpi" data-tone="users">
                      <div class="bea-admin-kpi__copy">
                        <p class="bea-admin-kpi__label">Incidents ouverts</p>
                        <p class="bea-admin-kpi__value">{{ o.incidents_ouverts ?? 0 }}</p>
                      </div>
                    </article>
                    <article class="bea-admin-kpi" data-tone="sessions">
                      <div class="bea-admin-kpi__copy">
                        <p class="bea-admin-kpi__label">Dernier audit</p>
                        <p class="bea-admin-kpi__value bea-sec-page__kpi-date">
                          @if (o.dernier_audit) {
                            {{ o.dernier_audit | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                          } @else {
                            —
                          }
                        </p>
                      </div>
                    </article>
                    <article class="bea-admin-kpi" data-tone="modules">
                      <div class="bea-admin-kpi__copy">
                        <p class="bea-admin-kpi__label">Dernière sauvegarde</p>
                        <p class="bea-admin-kpi__value bea-sec-page__kpi-date">
                          @if (o.derniere_sauvegarde) {
                            {{
                              o.derniere_sauvegarde | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott'
                            }}
                          } @else {
                            —
                          }
                        </p>
                      </div>
                    </article>
                  </div>
                  <div class="bea-admin-sec__etat">
                    @for (item of etatItems(o.etat); track item.key; let i = $index) {
                      <article
                        class="bea-admin-sec__chip"
                        [attr.data-ok]="item.ok"
                        [attr.data-status]="item.status"
                        [style.--delay]="i * 40 + 'ms'"
                      >
                        <span
                          class="bea-admin-health__dot"
                          [class.bea-admin-health__dot--ok]="item.ok && item.status !== 'non_verifie'"
                          [class.bea-admin-health__dot--ko]="!item.ok && item.status !== 'non_verifie'"
                        ></span>
                        <div>
                          <strong>{{ item.label }}</strong>
                          <em>{{ statusLabel(item.status) }}</em>
                          @if (item.detail) {
                            <small class="bea-admin-sec__chip-detail">{{ item.detail }}</small>
                          }
                        </div>
                        <span
                          class="bea-admin-sec__pill"
                          [attr.data-status]="item.status"
                          [attr.data-ok]="item.ok"
                        >
                          {{ statusShort(item.status) }}
                        </span>
                      </article>
                    }
                  </div>
                }
              }

              @case ('auth') {
                @if (loading()) {
                  <p class="bea-admin-dash__loading">Chargement…</p>
                } @else if (security(); as d) {
                  <div class="bea-sec-auth">
                    <header class="bea-sec-auth__intro">
                      <div>
                        <p class="bea-sec-auth__eyebrow">Politique d’authentification</p>
                        <h2>Sessions Login 1 / Login 2</h2>
                        <p>
                          Modifiez les durées, le verrouillage et le rate limiting. Les nouvelles
                          sessions appliquent immédiatement ces valeurs.
                        </p>
                      </div>
                      <span class="bea-sec-auth__source" [attr.data-source]="d.policy_source || 'environment'">
                        {{ d.policy_source === 'database' ? 'Overrides base' : 'Valeurs environnement' }}
                      </span>
                    </header>

                    <div class="bea-sec-auth__grid">
                      <section class="bea-sec-auth__card">
                        <h3>Durées de session</h3>
                        <p class="bea-sec-auth__hint">Tokens JWT — Login 1 plateforme et Login 2 module</p>
                        <div class="bea-admin-sec__form">
                          <label class="bea-admin-field">
                            <span>Access token (min)</span>
                            <input type="number" min="1" max="1440" [(ngModel)]="draft.accessMin" />
                          </label>
                          <label class="bea-admin-field">
                            <span>Refresh Login 1 (jours)</span>
                            <input type="number" min="1" max="90" [(ngModel)]="draft.refreshDays" />
                          </label>
                          <label class="bea-admin-field">
                            <span>Refresh Login 2 (min)</span>
                            <input type="number" min="5" max="1440" [(ngModel)]="draft.moduleRefreshMin" />
                          </label>
                        </div>
                      </section>

                      <section class="bea-sec-auth__card">
                        <h3>Protection attaques</h3>
                        <p class="bea-sec-auth__hint">Lockout après échecs de connexion</p>
                        <div class="bea-admin-sec__form">
                          <label class="bea-admin-field">
                            <span>Fenêtre lockout (min)</span>
                            <input type="number" min="1" max="1440" [(ngModel)]="draft.lockoutWindow" />
                          </label>
                          <label class="bea-admin-field">
                            <span>Échecs max</span>
                            <input type="number" min="1" max="50" [(ngModel)]="draft.lockoutMax" />
                          </label>
                        </div>
                      </section>

                      <section class="bea-sec-auth__card">
                        <h3>Rate limiting</h3>
                        <p class="bea-sec-auth__hint">Plafonds par minute (mémoire processus)</p>
                        <div class="bea-admin-sec__form">
                          <label class="bea-admin-sec__check bea-admin-field--full">
                            <input type="checkbox" [(ngModel)]="draft.rateEnabled" />
                            <span>Rate limiting activé</span>
                          </label>
                          <label class="bea-admin-field">
                            <span>Login / min</span>
                            <input type="number" min="1" [(ngModel)]="draft.rateLogin" [disabled]="!draft.rateEnabled" />
                          </label>
                          <label class="bea-admin-field">
                            <span>API / min</span>
                            <input type="number" min="1" [(ngModel)]="draft.rateApi" [disabled]="!draft.rateEnabled" />
                          </label>
                          <label class="bea-admin-field">
                            <span>Sensible / min</span>
                            <input type="number" min="1" [(ngModel)]="draft.rateSensitive" [disabled]="!draft.rateEnabled" />
                          </label>
                          <label class="bea-admin-field">
                            <span>Reset MDP / min</span>
                            <input type="number" min="1" [(ngModel)]="draft.rateReset" [disabled]="!draft.rateEnabled" />
                          </label>
                        </div>
                      </section>

                      <section class="bea-sec-auth__card">
                        <h3>Mots de passe & MFA</h3>
                        <p class="bea-sec-auth__hint">Règles de complexité et obligation MFA CORE ADMIN</p>
                        <div class="bea-admin-sec__form">
                          <label class="bea-admin-field">
                            <span>Longueur MDP min</span>
                            <input type="number" min="8" max="128" [(ngModel)]="draft.pwdMin" />
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
                        </div>
                      </section>
                    </div>

                    <footer class="bea-sec-auth__footer">
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
                        class="bea-admin-btn"
                        [disabled]="saving() || confirmPhrase.trim().toUpperCase() !== 'CONFIRMER'"
                        (click)="savePolicy()"
                      >
                        {{ saving() ? 'Enregistrement…' : 'Appliquer la politique' }}
                      </button>
                    </footer>
                  </div>
                }
              }

              @case ('sessions') {
                <div class="bea-sec-page__toolbar bea-sec-page__filters">
                  <label class="bea-admin-field">
                    <span>Recherche</span>
                    <input type="search" [(ngModel)]="sessionSearch" (keyup.enter)="loadSessions()" />
                  </label>
                  <label class="bea-admin-field">
                    <span>Type</span>
                    <select [(ngModel)]="sessionKind">
                      <option value="tous">Tous</option>
                      <option value="platform">Plateforme</option>
                      <option value="module">Module</option>
                    </select>
                  </label>
                  <label class="bea-admin-field">
                    <span>Statut</span>
                    <select [(ngModel)]="sessionStatus">
                      <option value="tous">Tous</option>
                      <option value="actives">Actives</option>
                      <option value="expirees">Expirées</option>
                      <option value="revoquees">Révoquées</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    class="bea-admin-btn bea-admin-btn--refresh"
                    (click)="loadSessions()"
                    [disabled]="loading()"
                  >
                    Actualiser
                  </button>
                </div>
                @if (loading()) {
                  <p class="bea-admin-dash__loading">Chargement des sessions…</p>
                } @else if (!sessions().length) {
                  <p class="bea-admin-panel__empty">Aucune session.</p>
                } @else {
                  <div class="bea-admin-table-wrap">
                    <table class="bea-admin-table">
                      <thead>
                        <tr>
                          <th>Utilisateur</th>
                          <th>E-mail</th>
                          <th>Type</th>
                          <th>Module</th>
                          <th>Créée</th>
                          <th>IP</th>
                          <th>UA</th>
                          <th>Statut</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        @for (row of sessions(); track row.id) {
                          <tr>
                            <td>
                              <strong>{{ row.user_full_name || '—' }}</strong>
                            </td>
                            <td>{{ row.user_email }}</td>
                            <td>{{ kindLabel(row.kind) }}</td>
                            <td>{{ row.module_code || '—' }}</td>
                            <td>
                              @if (row.created_at) {
                                {{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                              } @else {
                                —
                              }
                            </td>
                            <td>{{ row.ip_address || '—' }}</td>
                            <td class="bea-sec-page__ua" [title]="row.user_agent || ''">
                              {{ row.user_agent || '—' }}
                            </td>
                            <td>{{ statusSession(row) }}</td>
                            <td class="bea-admin-table__actions">
                              @if (row.active && !row.is_current) {
                                <button
                                  type="button"
                                  class="bea-admin-btn bea-admin-btn--ghost"
                                  (click)="revokeSession(row)"
                                >
                                  Révoquer
                                </button>
                              }
                              <button
                                type="button"
                                class="bea-admin-btn bea-admin-btn--ghost"
                                (click)="revokeAllForUser(row)"
                              >
                                Révoquer tout
                              </button>
                            </td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                  <p class="bea-sec-page__meta">{{ sessionsTotal() }} session(s)</p>
                }
              }

              @case ('mdp') {
                <div class="bea-sec-mdp">
                  <header class="bea-sec-mdp__intro">
                    <div>
                      <p class="bea-sec-mdp__eyebrow">Identifiants</p>
                      <h2>Mots de passe</h2>
                      <p>
                        Recherchez un utilisateur, puis réinitialisez le mot de passe ou changez
                        l’e-mail (Login 1 et Login 2 partagent le même identifiant).
                      </p>
                    </div>
                  </header>

                  <section class="bea-sec-mdp__card">
                    <bea-security-user-search (selectedChange)="onMdpUser($event)" />
                  </section>

                  @if (dossierLoading()) {
                    <p class="bea-admin-dash__loading">Chargement du dossier…</p>
                  } @else if (mdpDossier(); as u) {
                    <section class="bea-sec-mdp__card bea-sec-mdp__dossier">
                      <div class="bea-sec-mdp__dossier-head">
                        <div>
                          <h3>{{ u.full_name }}</h3>
                          <p>{{ u.email }}</p>
                        </div>
                        <span
                          class="bea-sec-inc__pill"
                          [attr.data-statut]="u.is_active ? 'resolu' : 'ouvert'"
                        >
                          {{ u.is_active ? 'Actif' : 'Inactif' }}
                        </span>
                      </div>

                      <p class="bea-admin-sec__warn">{{ u.note_auth }}</p>

                      <dl class="bea-admin-dl">
                        <div><dt>Téléphone</dt><dd>{{ u.phone || '—' }}</dd></div>
                        <div><dt>Sessions actives</dt><dd>{{ u.sessions_actives ?? 0 }}</dd></div>
                        <div>
                          <dt>Dernière connexion</dt>
                          <dd>
                            @if (u.last_login_at) {
                              {{
                                u.last_login_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott'
                              }}
                            } @else {
                              —
                            }
                          </dd>
                        </div>
                        <div>
                          <dt>Login 1 (plateforme)</dt>
                          <dd>{{ u.login1 }} · ••••••••</dd>
                        </div>
                        <div>
                          <dt>Login 2 (module)</dt>
                          <dd>{{ u.login2 }} · ••••••••</dd>
                        </div>
                        <div>
                          <dt>Mot de passe</dt>
                          <dd>
                            {{
                              u.password_shared
                                ? 'Partagé entre Login 1 et Login 2'
                                : '—'
                            }}
                          </dd>
                        </div>
                      </dl>

                      <div class="bea-sec-mdp__actions">
                        <label class="bea-admin-field">
                          <span>Nouveau login (e-mail)</span>
                          <input type="email" [(ngModel)]="newLogin" autocomplete="off" />
                        </label>
                        <button type="button" class="bea-admin-btn" (click)="changeLogin(u)">
                          Changer le login
                        </button>
                      </div>
                      <div class="bea-sec-mdp__actions">
                        <label class="bea-admin-field">
                          <span>Nouveau MDP (vide = généré automatiquement)</span>
                          <input
                            type="password"
                            [(ngModel)]="resetPwdPassword"
                            autocomplete="new-password"
                          />
                        </label>
                        <button type="button" class="bea-admin-btn" (click)="resetPassword(u)">
                          Réinitialiser le mot de passe
                        </button>
                      </div>
                    </section>
                  }
                </div>
              }

              @case ('mfa') {
                @if (security(); as d) {
                  <section class="bea-admin-panel bea-sec-page__panel">
                    <h2>Politique MFA</h2>
                    <dl class="bea-admin-dl">
                      <div>
                        <dt>MFA CORE ADMIN</dt>
                        <dd>
                          <span
                            class="bea-admin-sec__flag"
                            [attr.data-on]="!!d.mfa_required_for_core_admin"
                          >
                            {{ d.mfa_required_for_core_admin ? 'Activé' : 'Désactivé' }}
                          </span>
                        </dd>
                      </div>
                      <div><dt>Comptes 2FA</dt><dd>{{ d.mfa_users_enabled ?? 0 }}</dd></div>
                      <div>
                        <dt>Superusers sans MFA</dt>
                        <dd>{{ d.mfa_admins_without ?? 0 }}</dd>
                      </div>
                    </dl>
                    <label class="bea-admin-sec__check">
                      <input type="checkbox" [(ngModel)]="draft.mfaRequired" />
                      <span>MFA obligatoire CORE ADMIN</span>
                    </label>
                    <div class="bea-admin-sec__confirm">
                      <label class="bea-admin-field">
                        <span>Confirmation — CONFIRMER</span>
                        <input
                          type="text"
                          [(ngModel)]="confirmPhrase"
                          placeholder="CONFIRMER"
                          autocomplete="off"
                        />
                      </label>
                      <button
                        type="button"
                        class="bea-admin-btn"
                        [disabled]="saving() || confirmPhrase.trim().toUpperCase() !== 'CONFIRMER'"
                        (click)="saveMfaPolicy()"
                      >
                        {{ saving() ? 'Enregistrement…' : 'Appliquer MFA obligatoire' }}
                      </button>
                    </div>
                  </section>
                }
                <bea-security-user-search (selectedChange)="onMfaUser($event)" />
                @if (dossierLoading()) {
                  <p class="bea-admin-dash__loading">Chargement…</p>
                } @else if (mfaDossier(); as u) {
                  <section class="bea-admin-panel bea-sec-page__panel">
                    <h2>{{ u.full_name }}</h2>
                    <p>
                      MFA :
                      <strong>{{ u.totp_enabled ? 'Activé' : 'Désactivé' }}</strong>
                    </p>
                    <div class="bea-sec-page__actions">
                      <button
                        type="button"
                        class="bea-admin-btn bea-admin-btn--ghost"
                        [disabled]="!u.totp_enabled || saving()"
                        (click)="mfaDisable(u)"
                      >
                        Désactiver MFA
                      </button>
                      <button
                        type="button"
                        class="bea-admin-btn"
                        [disabled]="!u.totp_enabled || saving()"
                        (click)="mfaReset(u)"
                      >
                        Réinitialiser MFA
                      </button>
                    </div>
                  </section>
                } @else {
                  <p class="bea-admin-panel__empty">
                    Recherchez un utilisateur pour gérer son MFA.
                  </p>
                }
              }

              @case ('infra') {
                @if (loading()) {
                  <p class="bea-admin-dash__loading">Chargement…</p>
                } @else if (security(); as d) {
                  <section class="bea-admin-panel bea-sec-page__panel">
                    <h2>Infrastructure</h2>
                    <dl class="bea-admin-dl">
                      <div><dt>SSL base</dt><dd>{{ sslLabel(d.database_ssl) }}</dd></div>
                      <div>
                        <dt>Dossier upload</dt>
                        <dd>{{ d.upload_dir_exists ? 'Présent' : 'Absent' }}</dd>
                      </div>
                      <div>
                        <dt>Dossier GED</dt>
                        <dd>{{ d.ged_dir_exists ? 'Présent' : 'Absent' }}</dd>
                      </div>
                      <div>
                        <dt>HTTPS</dt>
                        <dd>{{ infraLabel(d.https_status) }}</dd>
                      </div>
                      <div><dt>Réseau</dt><dd>{{ infraLabel(d.reseau_status) }}</dd></div>
                      <div><dt>Serveur</dt><dd>{{ infraLabel(d.serveur_status) }}</dd></div>
                      <div>
                        <dt>Dépendances</dt>
                        <dd>{{ infraLabel(d.dependances_status) }}</dd>
                      </div>
                      <div>
                        <dt>Headers sécurité</dt>
                        <dd>{{ yesNo(!!d.security_headers_enabled) }}</dd>
                      </div>
                      <div>
                        <dt>CORS</dt>
                        <dd>{{ (d.cors_origins || []).join(', ') || '—' }}</dd>
                      </div>
                      <div><dt>Clé JWT</dt><dd>{{ secretLabel(d.secret_key_status) }}</dd></div>
                      <div>
                        <dt>Docs OpenAPI</dt>
                        <dd>{{ d.api_docs_enabled ? 'Exposées' : 'Désactivées' }}</dd>
                      </div>
                      <div><dt>Debug</dt><dd>{{ yesNo(!!d.app_debug) }}</dd></div>
                    </dl>
                  </section>
                }
              }

              @case ('audit') {
                <div class="bea-sec-page__toolbar bea-sec-page__filters">
                  <label class="bea-admin-field">
                    <span>Recherche</span>
                    <input type="search" [(ngModel)]="auditSearch" (keyup.enter)="loadAudit()" />
                  </label>
                  <label class="bea-admin-field">
                    <span>Action</span>
                    <input type="text" [(ngModel)]="auditAction" (keyup.enter)="loadAudit()" />
                  </label>
                  <button
                    type="button"
                    class="bea-admin-btn bea-admin-btn--refresh"
                    (click)="loadAudit()"
                    [disabled]="loading()"
                  >
                    Actualiser
                  </button>
                  <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/audit"
                    >Journal complet</a
                  >
                </div>
                @if (loading()) {
                  <p class="bea-admin-dash__loading">Chargement de l’audit…</p>
                } @else if (!auditRows().length) {
                  <p class="bea-admin-panel__empty">Aucun événement.</p>
                } @else {
                  <div class="bea-admin-table-wrap">
                    <table class="bea-admin-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Utilisateur</th>
                          <th>Action</th>
                          <th>Entité</th>
                          <th>Module</th>
                          <th>IP</th>
                        </tr>
                      </thead>
                      <tbody>
                        @for (row of auditRows(); track row.id) {
                          <tr>
                            <td>
                              @if (row.created_at) {
                                {{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                              } @else {
                                —
                              }
                            </td>
                            <td>{{ row.user_full_name || row.user_email || '—' }}</td>
                            <td>{{ actionLabel(row.action) }}</td>
                            <td>{{ row.entity }}</td>
                            <td>{{ row.module_code || '—' }}</td>
                            <td>{{ row.ip_address || '—' }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              }

              @case ('continuite') {
                <div class="bea-sec-page__toolbar">
                  <button
                    type="button"
                    class="bea-admin-btn bea-admin-btn--refresh"
                    (click)="loadBackups()"
                    [disabled]="loading()"
                  >
                    Actualiser
                  </button>
                  <a class="bea-admin-btn" routerLink="/admin/backups">Ouvrir Sauvegardes</a>
                  <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/recovery"
                    >Ouvrir Recovery</a
                  >
                </div>
                @if (loading()) {
                  <p class="bea-admin-dash__loading">Chargement…</p>
                } @else if (!backups().length) {
                  <p class="bea-admin-panel__empty">
                    Aucune sauvegarde récente. Utilisez Continuité → Sauvegardes.
                  </p>
                } @else {
                  <div class="bea-admin-table-wrap">
                    <table class="bea-admin-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Niveau</th>
                          <th>Type</th>
                          <th>Statut</th>
                          <th>Libellé</th>
                        </tr>
                      </thead>
                      <tbody>
                        @for (b of backups(); track b.id) {
                          <tr>
                            <td>
                              @if (b.created_at) {
                                {{ b.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}
                              } @else {
                                —
                              }
                            </td>
                            <td>{{ b.level }}</td>
                            <td>{{ b.backup_type }}</td>
                            <td>{{ b.status }}</td>
                            <td>{{ b.label || '—' }}</td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              }

              @case ('incidents') {
                <div class="bea-sec-inc">
                  <header class="bea-sec-inc__intro">
                    <div>
                      <p class="bea-sec-inc__eyebrow">Gestion des incidents</p>
                      <h2>{{ editingIncidentId() ? 'Modifier l’incident' : 'Nouvel incident' }}</h2>
                      <p>
                        Déclarez, suivez et clôturez les incidents de sécurité. Toute action est
                        journalisée dans l’audit.
                      </p>
                    </div>
                    @if (editingIncidentId()) {
                      <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="cancelIncidentEdit()">
                        Annuler l’édition
                      </button>
                    }
                  </header>

                  <section class="bea-sec-inc__form-card">
                    <div class="bea-admin-sec__form">
                      <label class="bea-admin-field">
                        <span>Titre</span>
                        <input [(ngModel)]="incidentForm.titre" placeholder="Résumé court" />
                      </label>
                      <label class="bea-admin-field">
                        <span>Type</span>
                        <select [(ngModel)]="incidentForm.type_incident">
                          @for (t of incidentTypes; track t) {
                            <option [value]="t">{{ t }}</option>
                          }
                        </select>
                      </label>
                      <label class="bea-admin-field">
                        <span>Niveau</span>
                        <select [(ngModel)]="incidentForm.niveau">
                          @for (n of incidentNiveaux; track n) {
                            <option [value]="n">{{ n }}</option>
                          }
                        </select>
                      </label>
                      <label class="bea-admin-field bea-admin-field--full">
                        <span>Description</span>
                        <textarea rows="2" [(ngModel)]="incidentForm.description"></textarea>
                      </label>
                      <label class="bea-admin-field">
                        <span>Statut</span>
                        <select [(ngModel)]="incidentForm.statut">
                          @for (s of incidentStatuts; track s) {
                            <option [value]="s">{{ s }}</option>
                          }
                        </select>
                      </label>
                      <label class="bea-admin-field">
                        <span>Responsable</span>
                        <input [(ngModel)]="incidentForm.responsable" />
                      </label>
                      <label class="bea-admin-field">
                        <span>Module</span>
                        <input [(ngModel)]="incidentForm.module_code" placeholder="ex. immobilisations" />
                      </label>
                      <label class="bea-admin-field">
                        <span>Département</span>
                        <input [(ngModel)]="incidentForm.espace_code" placeholder="code espace" />
                      </label>
                      <label class="bea-admin-field bea-admin-field--full">
                        <span>Actions prises</span>
                        <textarea rows="2" [(ngModel)]="incidentForm.actions"></textarea>
                      </label>
                      <label class="bea-admin-field bea-admin-field--full">
                        <span>Résolution</span>
                        <textarea rows="2" [(ngModel)]="incidentForm.resolution"></textarea>
                      </label>
                    </div>
                    <div class="bea-sec-inc__form-actions">
                      <button
                        type="button"
                        class="bea-admin-btn"
                        [disabled]="saving() || !incidentForm.titre.trim()"
                        (click)="saveIncident()"
                      >
                        @if (saving()) {
                          Enregistrement…
                        } @else if (editingIncidentId()) {
                          Enregistrer les modifications
                        } @else {
                          Créer l’incident
                        }
                      </button>
                    </div>
                  </section>

                  <section class="bea-sec-inc__list-card">
                    <div class="bea-sec-inc__list-head">
                      <div>
                        <h3>Incidents enregistrés</h3>
                        <p>{{ incidents().length }} élément(s)</p>
                      </div>
                      <button
                        type="button"
                        class="bea-admin-btn bea-admin-btn--refresh"
                        (click)="loadIncidents()"
                        [disabled]="loading()"
                      >
                        <bea-admin-icon name="refresh" />
                        Actualiser
                      </button>
                    </div>

                    @if (loading()) {
                      <p class="bea-admin-dash__loading">Chargement…</p>
                    } @else if (!incidents().length) {
                      <p class="bea-admin-panel__empty">Aucun incident enregistré.</p>
                    } @else {
                      <div class="bea-admin-table-wrap">
                        <table class="bea-admin-table bea-sec-inc__table">
                          <thead>
                            <tr>
                              <th>Titre</th>
                              <th>Type</th>
                              <th>Niveau</th>
                              <th>Statut</th>
                              <th>Responsable</th>
                              <th>Créé</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            @for (inc of incidents(); track inc.id) {
                              <tr [class.bea-sec-page__row--on]="editingIncidentId() === inc.id">
                                <td>
                                  <strong>{{ inc.titre }}</strong>
                                  @if (inc.description) {
                                    <div class="bea-sec-page__muted">{{ inc.description }}</div>
                                  }
                                </td>
                                <td>
                                  <span class="bea-sec-inc__chip">{{ inc.type_incident }}</span>
                                </td>
                                <td>
                                  <span class="bea-sec-inc__pill" [attr.data-niveau]="inc.niveau">
                                    {{ inc.niveau }}
                                  </span>
                                </td>
                                <td>
                                  <span class="bea-sec-inc__pill" [attr.data-statut]="inc.statut">
                                    {{ inc.statut }}
                                  </span>
                                </td>
                                <td>{{ inc.responsable || '—' }}</td>
                                <td>
                                  @if (inc.created_at) {
                                    {{
                                      inc.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott'
                                    }}
                                  } @else {
                                    —
                                  }
                                </td>
                                <td class="bea-admin-table__actions">
                                  <button
                                    type="button"
                                    class="bea-admin-icon-btn"
                                    title="Éditer"
                                    aria-label="Éditer"
                                    (click)="editIncident(inc)"
                                  >
                                    <bea-admin-icon name="edit" />
                                  </button>
                                  <button
                                    type="button"
                                    class="bea-admin-icon-btn"
                                    title="Voir"
                                    aria-label="Voir"
                                    (click)="viewIncident(inc)"
                                  >
                                    <bea-admin-icon name="visibility" />
                                  </button>
                                  <button
                                    type="button"
                                    class="bea-admin-icon-btn bea-admin-icon-btn--danger"
                                    title="Supprimer"
                                    aria-label="Supprimer"
                                    (click)="deleteIncident(inc)"
                                  >
                                    <bea-admin-icon name="delete" />
                                  </button>
                                </td>
                              </tr>
                            }
                          </tbody>
                        </table>
                      </div>
                    }
                  </section>
                </div>
              }

              @case ('controle') {
                <div class="bea-sec-page__toolbar">
                  <button
                    type="button"
                    class="bea-admin-btn"
                    [disabled]="checking()"
                    (click)="runCheck()"
                  >
                    {{ checking() ? 'Contrôle…' : 'Exécuter le contrôle' }}
                  </button>
                  <button
                    type="button"
                    class="bea-admin-btn bea-admin-btn--ghost"
                    (click)="loadSecurity()"
                    [disabled]="loading()"
                  >
                    Actualiser verrouillages
                  </button>
                </div>
                @if (check(); as c) {
                  <section class="bea-admin-panel bea-sec-page__panel">
                    <div class="bea-admin-users__list-head">
                      <h2>Contrôle de sécurité</h2>
                      <p>
                        {{ c.ok_count }} OK · {{ c.warn_count }} à vérifier ·
                        {{ c.ko_count }} problème(s)
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
                } @else {
                  <p class="bea-admin-panel__empty">
                    Lancez un contrôle pour diagnostiquer la configuration.
                  </p>
                }
                @if (security(); as d) {
                  <section class="bea-admin-panel bea-sec-page__panel">
                    <h2>Comptes verrouillés</h2>
                    @if (!d.comptes_verrouilles?.length) {
                      <p class="bea-admin-panel__empty">Aucun compte verrouillé.</p>
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
              }
            }
          </div>
        </div>
      }
    </section>
  `,
})
export class CoreAdminSecurityComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(BeaAdminDialogService);

  readonly cardsTop = SEC_CARDS_TOP;
  readonly cardsBottom = SEC_CARDS_BOTTOM;
  readonly incidentTypes = INCIDENT_TYPES;
  readonly incidentNiveaux = INCIDENT_NIVEAUX;
  readonly incidentStatuts = INCIDENT_STATUTS;

  readonly activePage = signal<SecPageId | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly checking = signal(false);
  readonly unlocking = signal('');
  readonly dossierLoading = signal(false);
  readonly hubErreur = signal('');
  readonly pageErreur = signal('');

  readonly overview = signal<SecurityOverview | null>(null);
  readonly security = signal<CoreAdminSecuritySettings | null>(null);
  readonly check = signal<CoreAdminSecurityCheck | null>(null);
  readonly sessions = signal<CoreAdminSessionRow[]>([]);
  readonly sessionsTotal = signal(0);
  readonly auditRows = signal<CoreAdminAuditRow[]>([]);
  readonly backups = signal<BackupRow[]>([]);
  readonly incidents = signal<SecurityIncidentRow[]>([]);
  readonly editingIncidentId = signal<string | null>(null);
  readonly mdpDossier = signal<SecurityUserDossier | null>(null);
  readonly mfaDossier = signal<SecurityUserDossier | null>(null);

  confirmPhrase = '';
  newLogin = '';
  resetPwdPassword = '';
  sessionSearch = '';
  sessionKind: CoreAdminSessionKind = 'tous';
  sessionStatus: CoreAdminSessionStatus = 'actives';
  auditSearch = '';
  auditAction = '';
  incidentForm = this.emptyIncidentForm();
  draft = {
    accessMin: 15,
    refreshDays: 1,
    moduleRefreshMin: 45,
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
    this.refreshHub();
  }

  pageTitle(id: SecPageId): string {
    return [...this.cardsTop, ...this.cardsBottom].find((c) => c.id === id)?.title ?? id;
  }

  openPage(id: SecPageId): void {
    this.activePage.set(id);
    this.pageErreur.set('');
    this.confirmPhrase = '';
    switch (id) {
      case 'vue':
        this.loadOverview();
        break;
      case 'auth':
      case 'infra':
      case 'controle':
      case 'mfa':
        this.loadSecurity();
        break;
      case 'sessions':
        this.loadSessions();
        break;
      case 'mdp':
        this.mdpDossier.set(null);
        break;
      case 'audit':
        this.loadAudit();
        break;
      case 'continuite':
        this.loadBackups();
        break;
      case 'incidents':
        this.loadIncidents();
        break;
    }
  }

  closePage(): void {
    this.activePage.set(null);
    this.pageErreur.set('');
  }

  refreshHub(): void {
    this.hubErreur.set('');
    this.loadOverview(true);
  }

  loadOverview(silent = false): void {
    if (!silent) this.loading.set(true);
    this.pageErreur.set('');
    this.api.get<SecurityOverview>('/plateforme/admin/settings/security/overview').subscribe({
      next: (data) => {
        this.overview.set(data);
        if (!silent) this.loading.set(false);
      },
      error: (err) => {
        if (!silent) this.loading.set(false);
        const msg = coreAdminOpsError(err, 'Impossible de charger la vue sécurité.');
        if (silent) this.hubErreur.set(msg);
        else this.pageErreur.set(msg);
      },
    });
  }

  loadSecurity(): void {
    this.loading.set(true);
    this.pageErreur.set('');
    this.api.get<CoreAdminSecuritySettings>('/plateforme/admin/settings/security').subscribe({
      next: (data) => {
        this.security.set(data);
        this.syncDraft(data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.pageErreur.set(coreAdminOpsError(err, 'Impossible de charger la sécurité.'));
      },
    });
  }

  syncDraft(d: CoreAdminSecuritySettings): void {
    this.draft = {
      accessMin: d.access_token_expire_minutes ?? 15,
      refreshDays: d.refresh_token_expire_days ?? 1,
      moduleRefreshMin: d.module_refresh_token_expire_minutes ?? 45,
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

  loadSessions(): void {
    this.loading.set(true);
    this.pageErreur.set('');
    const params: Record<string, string | number> = {
      page: 1,
      size: 50,
      kind: this.sessionKind,
      status: this.sessionStatus,
    };
    if (this.sessionSearch.trim()) params['search'] = this.sessionSearch.trim();
    this.api.get<CoreAdminSessionPage>('/plateforme/admin/sessions', params).subscribe({
      next: (data) => {
        this.sessions.set(data.items ?? []);
        this.sessionsTotal.set(data.total ?? 0);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.pageErreur.set(coreAdminOpsError(err, 'Impossible de charger les sessions.'));
      },
    });
  }

  loadAudit(): void {
    this.loading.set(true);
    this.pageErreur.set('');
    const params: Record<string, string | number> = { page: 1, size: 40 };
    if (this.auditSearch.trim()) params['search'] = this.auditSearch.trim();
    if (this.auditAction.trim()) params['action'] = this.auditAction.trim();
    this.api.get<CoreAdminAuditPage>('/plateforme/admin/audit', params).subscribe({
      next: (data) => {
        this.auditRows.set(data.items ?? []);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.pageErreur.set(coreAdminOpsError(err, 'Impossible de charger l’audit.'));
      },
    });
  }

  loadBackups(): void {
    this.loading.set(true);
    this.pageErreur.set('');
    this.api.get<{ items: BackupRow[] }>('/plateforme/admin/backups', { page: 1, size: 10 }).subscribe({
      next: (res) => {
        this.backups.set(res.items ?? []);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.pageErreur.set(coreAdminOpsError(err, 'Impossible de charger les sauvegardes.'));
      },
    });
  }

  loadIncidents(): void {
    this.loading.set(true);
    this.pageErreur.set('');
    this.api
      .get<{ items: SecurityIncidentRow[]; available?: boolean }>(
        '/plateforme/admin/settings/security/incidents',
      )
      .subscribe({
        next: (res) => {
          this.incidents.set(res.items ?? []);
          this.loading.set(false);
          if (res.available === false) {
            this.pageErreur.set(
              'Table incidents indisponible — appliquer les migrations sécurité.',
            );
          }
        },
        error: (err) => {
          this.loading.set(false);
          this.pageErreur.set(coreAdminOpsError(err, 'Impossible de charger les incidents.'));
        },
      });
  }

  onMdpUser(hit: SecurityUserHit | null): void {
    if (!hit) {
      this.mdpDossier.set(null);
      return;
    }
    this.loadDossier(hit.id, 'mdp');
  }

  onMfaUser(hit: SecurityUserHit | null): void {
    if (!hit) {
      this.mfaDossier.set(null);
      return;
    }
    this.loadDossier(hit.id, 'mfa');
  }

  private loadDossier(userId: string, target: 'mdp' | 'mfa'): void {
    this.dossierLoading.set(true);
    this.pageErreur.set('');
    this.api
      .get<SecurityUserDossier>(`/plateforme/admin/settings/security/users/${userId}/dossier`)
      .subscribe({
        next: (d) => {
          if (target === 'mdp') {
            this.mdpDossier.set(d);
            this.newLogin = d.login1 || d.email;
          } else {
            this.mfaDossier.set(d);
          }
          this.dossierLoading.set(false);
        },
        error: (err) => {
          this.dossierLoading.set(false);
          this.pageErreur.set(coreAdminOpsError(err, 'Dossier utilisateur introuvable.'));
        },
      });
  }

  etatItems(etat?: SecurityOverview['etat']) {
    return Object.entries(etat ?? {}).map(([key, value]) => ({
      key,
      label: value.label,
      ok: value.ok,
      status: value.status || (value.ok ? 'operational' : 'probleme'),
      detail: value.detail || '',
    }));
  }

  statusLabel(status?: string): string {
    switch (status) {
      case 'operational':
        return 'Opérationnel';
      case 'protege':
        return 'Protégé';
      case 'a_verifier':
        return 'À vérifier';
      case 'attention':
        return 'Attention';
      case 'probleme':
        return 'Problème détecté';
      case 'non_verifie':
        return 'Non vérifié';
      default:
        return status || '—';
    }
  }

  statusShort(status?: string): string {
    if (status === 'non_verifie') return '—';
    if (status === 'attention' || status === 'a_verifier') return '!';
    if (status === 'probleme') return 'KO';
    return 'OK';
  }

  infraLabel(status?: string): string {
    return this.statusLabel(status || 'non_verifie');
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

  kindLabel(kind: string): string {
    return sessionKindLabel(kind);
  }

  statusSession(row: CoreAdminSessionRow): string {
    return sessionStatusLabel(row);
  }

  actionLabel(action: string): string {
    return coreAdminAuditActionLabel(action);
  }

  async savePolicy(): Promise<void> {
    if (this.saving() || this.confirmPhrase.trim().toUpperCase() !== 'CONFIRMER') return;
    const ok = await this.dialogs.confirm({
      title: 'Appliquer la politique sécurité',
      message:
        'Ces paramètres s’appliquent immédiatement (durées de session, lockout, MDP, MFA, rate limit).\n' +
        'Confirmez-vous la modification ?',
      confirmLabel: 'Appliquer',
      cancelLabel: 'Annuler',
      tone: 'warn',
    });
    if (!ok) return;
    this.patchPolicy(true);
  }

  async saveMfaPolicy(): Promise<void> {
    if (this.saving() || this.confirmPhrase.trim().toUpperCase() !== 'CONFIRMER') return;
    const ok = await this.dialogs.confirm({
      title: 'Politique MFA',
      message: 'Modifier l’obligation MFA pour CORE ADMIN ?',
      confirmLabel: 'Appliquer',
      cancelLabel: 'Annuler',
      tone: 'warn',
    });
    if (!ok) return;
    this.patchPolicy(false);
  }

  private patchPolicy(full: boolean): void {
    this.saving.set(true);
    this.pageErreur.set('');
    const body: Record<string, unknown> = {
      confirmation_phrase: 'CONFIRMER',
      mfa_required_for_core_admin: this.draft.mfaRequired,
    };
    if (full) {
      Object.assign(body, {
        access_token_expire_minutes: Number(this.draft.accessMin),
        refresh_token_expire_days: Number(this.draft.refreshDays),
        module_refresh_token_expire_minutes: Number(this.draft.moduleRefreshMin),
        login_lockout_window_minutes: Number(this.draft.lockoutWindow),
        login_lockout_max_failures: Number(this.draft.lockoutMax),
        password_min_length: Number(this.draft.pwdMin),
        password_require_uppercase: this.draft.pwdUpper,
        password_require_lowercase: this.draft.pwdLower,
        password_require_digit: this.draft.pwdDigit,
        password_require_special: this.draft.pwdSpecial,
        rate_limit_enabled: this.draft.rateEnabled,
        rate_limit_login_per_minute: Number(this.draft.rateLogin),
        rate_limit_api_per_minute: Number(this.draft.rateApi),
        rate_limit_sensitive_per_minute: Number(this.draft.rateSensitive),
        rate_limit_password_reset_per_minute: Number(this.draft.rateReset),
      });
    }
    this.api
      .patch<CoreAdminSecuritySettings>('/plateforme/admin/settings/security/policy', body)
      .subscribe({
        next: async (data) => {
          this.saving.set(false);
          this.confirmPhrase = '';
          this.security.set(data);
          this.syncDraft(data);
          await this.dialogs.success('Politique sécurité mise à jour.', 'Enregistré');
        },
        error: (err) => {
          this.saving.set(false);
          const msg = coreAdminOpsError(err, 'Échec enregistrement politique.');
          this.pageErreur.set(msg);
          void this.dialogs.error(msg);
        },
      });
  }

  async revokeSession(row: CoreAdminSessionRow): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Révoquer la session',
      message: `Révoquer la session ${this.kindLabel(row.kind)} de ${row.user_full_name || row.user_email} ?`,
      tone: 'danger',
      confirmLabel: 'Révoquer',
    });
    if (!ok) return;
    this.api.post(`/plateforme/admin/sessions/${row.id}/revoke`, {}).subscribe({
      next: async () => {
        await this.dialogs.success('Session révoquée.');
        this.loadSessions();
      },
      error: (err) => {
        const msg = coreAdminOpsError(err, 'Révocation impossible.');
        this.pageErreur.set(msg);
        void this.dialogs.error(msg);
      },
    });
  }

  async revokeAllForUser(row: CoreAdminSessionRow): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Révoquer toutes les sessions',
      message: `Révoquer toutes les sessions de ${row.user_full_name || row.user_email} ?`,
      tone: 'danger',
      confirmLabel: 'Révoquer tout',
    });
    if (!ok) return;
    this.api.post(`/plateforme/admin/sessions/users/${row.user_id}/revoke-all`, {}).subscribe({
      next: async () => {
        await this.dialogs.success('Sessions révoquées.');
        this.loadSessions();
      },
      error: (err) => {
        const msg = coreAdminOpsError(err, 'Révocation globale impossible.');
        this.pageErreur.set(msg);
        void this.dialogs.error(msg);
      },
    });
  }

  async changeLogin(u: SecurityUserDossier): Promise<void> {
    const login = this.newLogin.trim().toLowerCase();
    if (!login || !login.includes('@')) {
      void this.dialogs.error('E-mail invalide.');
      return;
    }
    const ok = await this.dialogs.confirm({
      title: 'Changer le login',
      message:
        `Nouveau login (Login 1 et Login 2) : ${login}\n` +
        `Ancien : ${u.login1}\nTapez CONFIRMER sera envoyé automatiquement.`,
      confirmLabel: 'Changer',
      cancelLabel: 'Annuler',
      tone: 'warn',
    });
    if (!ok) return;
    this.saving.set(true);
    this.api
      .patch(`/plateforme/admin/settings/security/users/${u.id}/login`, {
        new_login: login,
        confirmation_phrase: 'CONFIRMER',
      })
      .subscribe({
        next: async () => {
          this.saving.set(false);
          await this.dialogs.success('Login mis à jour (Login 1 et Login 2).');
          this.loadDossier(u.id, 'mdp');
        },
        error: (err) => {
          this.saving.set(false);
          const msg = coreAdminOpsError(err, 'Changement de login impossible.');
          this.pageErreur.set(msg);
          void this.dialogs.error(msg);
        },
      });
  }

  async resetPassword(u: SecurityUserDossier): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Réinitialiser le mot de passe',
      message:
        `Réinitialiser le mot de passe de « ${u.email} » ?\n` +
        `Login 1 et Login 2 partagent ce mot de passe. Sessions révoquées.`,
      confirmLabel: 'Réinitialiser',
      cancelLabel: 'Annuler',
      tone: 'warn',
    });
    if (!ok) return;
    this.saving.set(true);
    const body: Record<string, string> = {
      user_id: u.id,
      confirmation_phrase: 'CONFIRMER',
    };
    if (this.resetPwdPassword.trim()) body['password'] = this.resetPwdPassword.trim();
    this.api
      .post<{ email: string; temporary_password: string; message: string }>(
        '/plateforme/admin/settings/security/reset-password',
        body,
      )
      .subscribe({
        next: async (res) => {
          this.saving.set(false);
          this.resetPwdPassword = '';
          await this.dialogs.success(
            `${res.message}\n\nMot de passe temporaire :\n${res.temporary_password}`,
            'Mot de passe réinitialisé',
          );
          this.loadDossier(u.id, 'mdp');
        },
        error: (err) => {
          this.saving.set(false);
          const msg = coreAdminOpsError(err, 'Réinitialisation impossible.');
          this.pageErreur.set(msg);
          void this.dialogs.error(msg);
        },
      });
  }

  async mfaDisable(u: SecurityUserDossier): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Désactiver MFA',
      message: `Désactiver le MFA de ${u.full_name} ?`,
      tone: 'warn',
      confirmLabel: 'Désactiver',
    });
    if (!ok) return;
    this.saving.set(true);
    this.api
      .post(`/plateforme/admin/settings/security/users/${u.id}/mfa/disable`, {
        confirmation_phrase: 'CONFIRMER',
      })
      .subscribe({
        next: async () => {
          this.saving.set(false);
          await this.dialogs.success('MFA désactivé.');
          this.loadDossier(u.id, 'mfa');
          this.loadSecurity();
        },
        error: (err) => {
          this.saving.set(false);
          const msg = coreAdminOpsError(err, 'Désactivation MFA impossible.');
          void this.dialogs.error(msg);
        },
      });
  }

  async mfaReset(u: SecurityUserDossier): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Réinitialiser MFA',
      message: `Révoquer le secret MFA de ${u.full_name} ? L’utilisateur devra ré-enrôler.`,
      tone: 'warn',
      confirmLabel: 'Réinitialiser',
    });
    if (!ok) return;
    this.saving.set(true);
    this.api
      .post(`/plateforme/admin/settings/security/users/${u.id}/mfa/reset`, {
        confirmation_phrase: 'CONFIRMER',
      })
      .subscribe({
        next: async () => {
          this.saving.set(false);
          await this.dialogs.success('MFA réinitialisé.');
          this.loadDossier(u.id, 'mfa');
          this.loadSecurity();
        },
        error: (err) => {
          this.saving.set(false);
          const msg = coreAdminOpsError(err, 'Réinitialisation MFA impossible.');
          void this.dialogs.error(msg);
        },
      });
  }

  emptyIncidentForm() {
    return {
      titre: '',
      description: '',
      type_incident: 'autre',
      niveau: 'moyen',
      statut: 'ouvert',
      responsable: '',
      module_code: '',
      espace_code: '',
      actions: '',
      resolution: '',
    };
  }

  resetIncidentForm(): void {
    this.editingIncidentId.set(null);
    this.incidentForm = this.emptyIncidentForm();
  }

  cancelIncidentEdit(): void {
    this.resetIncidentForm();
  }

  editIncident(inc: SecurityIncidentRow): void {
    this.editingIncidentId.set(inc.id);
    this.incidentForm = {
      titre: inc.titre || '',
      description: inc.description || '',
      type_incident: inc.type_incident || 'autre',
      niveau: inc.niveau || 'moyen',
      statut: inc.statut || 'ouvert',
      responsable: inc.responsable || '',
      module_code: inc.module_code || '',
      espace_code: inc.espace_code || '',
      actions: inc.actions || '',
      resolution: inc.resolution || '',
    };
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async viewIncident(inc: SecurityIncidentRow): Promise<void> {
    const lines = [
      `Titre : ${inc.titre}`,
      `Type : ${inc.type_incident}`,
      `Niveau : ${inc.niveau}`,
      `Statut : ${inc.statut}`,
      `Responsable : ${inc.responsable || '—'}`,
      `Module : ${inc.module_code || '—'}`,
      `Département : ${inc.espace_code || '—'}`,
      '',
      `Description :\n${inc.description || '—'}`,
      '',
      `Actions prises :\n${inc.actions || '—'}`,
      '',
      `Résolution :\n${inc.resolution || '—'}`,
    ];
    await this.dialogs.info(lines.join('\n'), 'Détail incident');
  }

  saveIncident(): void {
    if (this.saving() || !this.incidentForm.titre.trim()) return;
    this.saving.set(true);
    this.pageErreur.set('');
    const body = {
      titre: this.incidentForm.titre.trim(),
      description: this.incidentForm.description.trim() || null,
      type_incident: this.incidentForm.type_incident,
      niveau: this.incidentForm.niveau,
      statut: this.incidentForm.statut,
      responsable: this.incidentForm.responsable.trim() || null,
      module_code: this.incidentForm.module_code.trim() || null,
      espace_code: this.incidentForm.espace_code.trim() || null,
      actions: this.incidentForm.actions.trim() || null,
      resolution: this.incidentForm.resolution.trim() || null,
    };
    const editId = this.editingIncidentId();
    const req$ = editId
      ? this.api.patch<SecurityIncidentRow>(
          `/plateforme/admin/settings/security/incidents/${editId}`,
          body,
        )
      : this.api.post<SecurityIncidentRow>('/plateforme/admin/settings/security/incidents', body);
    req$.subscribe({
      next: async () => {
        this.saving.set(false);
        this.resetIncidentForm();
        await this.dialogs.success(editId ? 'Incident mis à jour.' : 'Incident créé.');
        this.loadIncidents();
      },
      error: (err) => {
        this.saving.set(false);
        const msg = coreAdminOpsError(
          err,
          editId ? 'Mise à jour incident impossible.' : 'Création incident impossible.',
        );
        this.pageErreur.set(msg);
        void this.dialogs.error(msg);
      },
    });
  }

  async deleteIncident(inc: SecurityIncidentRow): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Supprimer l’incident',
      message: `Supprimer définitivement « ${inc.titre} » ? Cette action est irréversible.`,
      confirmLabel: 'Supprimer',
      cancelLabel: 'Annuler',
      tone: 'danger',
    });
    if (!ok) return;
    this.api.delete(`/plateforme/admin/settings/security/incidents/${inc.id}`).subscribe({
      next: async () => {
        if (this.editingIncidentId() === inc.id) this.resetIncidentForm();
        await this.dialogs.success('Incident supprimé.');
        this.loadIncidents();
      },
      error: (err) => {
        const msg = coreAdminOpsError(err, 'Suppression impossible.');
        this.pageErreur.set(msg);
        void this.dialogs.error(msg);
      },
    });
  }

  runCheck(): void {
    if (this.checking()) return;
    this.checking.set(true);
    this.pageErreur.set('');
    this.api.post<CoreAdminSecurityCheck>('/plateforme/admin/settings/security/check', {}).subscribe({
      next: (res) => {
        this.check.set(res);
        this.checking.set(false);
      },
      error: (err) => {
        this.checking.set(false);
        this.pageErreur.set(coreAdminOpsError(err, 'Contrôle impossible.'));
      },
    });
  }

  async unlock(email: string): Promise<void> {
    if (this.unlocking()) return;
    const ok = await this.dialogs.confirm({
      title: 'Déverrouiller le compte',
      message: `Effacer les échecs de connexion pour « ${email} » ?`,
      confirmLabel: 'Déverrouiller',
      cancelLabel: 'Annuler',
      tone: 'warn',
    });
    if (!ok) return;
    this.unlocking.set(email);
    this.api
      .post<{ email: string; cleared_failures: number }>(
        '/plateforme/admin/settings/security/unlock',
        { email },
      )
      .subscribe({
        next: async (res) => {
          this.unlocking.set('');
          await this.dialogs.success(
            `${res.cleared_failures} échec(s) effacé(s) pour ${res.email}.`,
            'Compte déverrouillé',
          );
          this.loadSecurity();
        },
        error: (err) => {
          this.unlocking.set('');
          const msg = coreAdminOpsError(err, 'Déverrouillage impossible.');
          this.pageErreur.set(msg);
          void this.dialogs.error(msg);
        },
      });
  }
}
