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
    module_code?: string | null;
    created_at?: string | null;
  }>;
  total: number;
  page: number;
  size: number;
  kpis: { total: number; non_lues: number; lues: number; systeme: number };
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
