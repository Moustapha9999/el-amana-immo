import { HttpErrorResponse } from '@angular/common/http';

export function coreAdminOpsError(err: unknown, fallback: string): string {
  if (!(err instanceof HttpErrorResponse)) {
    return fallback;
  }
  const detail = err.error?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === 'object' && typeof (detail as { message?: string }).message === 'string') {
    return (detail as { message: string }).message;
  }
  return fallback;
}

export interface CoreAdminActivityPage {
  items: Array<{
    id: string;
    user_id?: string | null;
    user_email?: string | null;
    user_full_name?: string | null;
    action: string;
    entity: string;
    entity_id?: string | null;
    module_code?: string | null;
    created_at?: string | null;
  }>;
  total: number;
  page: number;
  size: number;
  kpis: { total: number; derniere_heure: number; aujourd_hui: number; modules: number };
}

export interface CoreAdminAlertPage {
  items: Array<{
    id: string;
    email: string;
    ip_address?: string | null;
    login_kind: string;
    module_code?: string | null;
    success: boolean;
    created_at?: string | null;
  }>;
  total: number;
  page: number;
  size: number;
  kpis: { total: number; echecs_fenetre: number; succes_fenetre: number; emails_suspects: number };
  lockout_window_minutes: number;
  lockout_max_failures: number;
}

export interface CoreAdminNotificationPage {
  items: Array<{
    id: string;
    user_id: string;
    user_email?: string | null;
    user_full_name?: string | null;
    type_notification: string;
    titre: string;
    message: string;
    lu: boolean;
    archived?: boolean;
    entity?: string | null;
    entity_id?: string | null;
    espace_code?: string | null;
    module_code?: string | null;
    categorie?: string;
    categorie_label?: string;
    priorite?: string;
    priorite_label?: string;
    event_type?: string | null;
    event_code?: string | null;
    emetteur_type?: string;
    emetteur_label?: string;
    destinataire_type?: string;
    destinataire_label?: string | null;
    created_at?: string | null;
  }>;
  total: number;
  page: number;
  size: number;
  kpis: {
    total: number;
    non_lues: number;
    lues: number;
    alertes?: number;
    critiques?: number;
    systeme?: number;
    categories?: Record<string, string>;
    priorites?: Record<string, string>;
  };
}

export interface CoreAdminGedPage {
  items: Array<{
    id: string;
    espace_code: string;
    module_code: string;
    entity: string;
    entity_id: string;
    filename: string;
    mime_type?: string | null;
    size_bytes: number;
    created_at?: string | null;
  }>;
  total: number;
  page: number;
  size: number;
  kpis: { total: number; modules: number; taille_octets: number; reservee: boolean };
}

export interface CoreAdminGeneralSettings {
  app_name: string;
  app_env: string;
  app_debug: boolean;
  api_v1_prefix: string;
  fuseau: string;
  cors_origins: string[];
  upload_dir: string;
  ged_dir: string;
  access_token_expire_minutes: number;
  refresh_token_expire_days: number;
  module_refresh_token_expire_minutes: number;
}

export interface CoreAdminSecuritySettings {
  login_lockout_window_minutes: number;
  login_lockout_max_failures: number;
  jwt_algorithm: string;
  alertes_fenetre: number;
  sessions_actives: number;
  sessions_platform?: number;
  sessions_module?: number;
  access_token_expire_minutes?: number;
  refresh_token_expire_days?: number;
  module_refresh_token_expire_minutes?: number;
  password_policy?: {
    min_length: number;
    require_uppercase: boolean;
    require_lowercase: boolean;
    require_digit: boolean;
    require_special: boolean;
    hash_algorithm: string;
    history_reuse_current_forbidden: boolean;
  };
  mfa_required_for_core_admin?: boolean;
  mfa_users_enabled?: number;
  mfa_admins_without?: number;
  rate_limit_enabled?: boolean;
  rate_limit?: {
    login_per_minute: number;
    api_per_minute: number;
    sensitive_per_minute: number;
    password_reset_per_minute: number;
  };
  security_headers_enabled?: boolean;
  api_docs_enabled?: boolean;
  cors_origins?: string[];
  database_ssl?: string;
  secret_key_status?: string;
  upload_dir_exists?: boolean;
  ged_dir_exists?: boolean;
  app_env?: string;
  app_debug?: boolean;
  comptes_verrouilles?: { email: string; echecs: number; fenetre_minutes: number }[];
  etat?: Record<string, { ok: boolean; label: string }>;
  fuseau?: string;
  verifie_at?: string | null;
  policy_source?: string | null;
  policy_updated_at?: string | null;
  policy_editable?: boolean;
}

export interface CoreAdminSecurityCheckItem {
  key: string;
  label: string;
  status: 'ok' | 'warn' | 'ko';
  detail: string;
}

export interface CoreAdminSecurityCheck {
  items: CoreAdminSecurityCheckItem[];
  ok_count: number;
  warn_count: number;
  ko_count: number;
  verifie_at: string;
  fuseau: string;
}

export interface CoreAdminMaintenanceSettings {
  db_ok: boolean;
  skip_migrations: boolean;
  modules_actifs: number;
  modules_total: number;
  sessions_actives: number;
  upload_dir_exists: boolean;
  ged_dir_exists: boolean;
  app_env: string;
  etat: Record<string, { ok: boolean; label: string }>;
}
