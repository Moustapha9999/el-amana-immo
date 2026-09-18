import { HttpErrorResponse } from '@angular/common/http';

export interface CoreAdminRole {
  id: string;
  code: string;
  label: string;
}

export interface CoreAdminUserRow {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  is_superuser: boolean;
  is_active: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  created_at?: string | null;
  roles: CoreAdminRole[];
  espace_codes: string[];
  module_codes: string[];
  permission_codes?: string[];
}

export interface CoreAdminUserSession {
  id: string;
  kind: string;
  module_code?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  active: boolean;
}

export interface CoreAdminUserActivity {
  id: string;
  who: string;
  action: string;
  entity: string;
  entity_id?: string | null;
  module?: string | null;
  created_at?: string | null;
}

export interface CoreAdminUserFiche extends CoreAdminUserRow {
  sessions: CoreAdminUserSession[];
  activite: CoreAdminUserActivity[];
}

export interface CoreAdminCatalogueEspace {
  id: string;
  titre: string;
  statut: string;
  modules: { id: string; titre: string; statut: string }[];
}

export interface CoreAdminUserKpis {
  total: number;
  actifs: number;
  inactifs: number;
  superusers: number;
  totp: number;
  jamais_connectes: number;
}

export interface CoreAdminUserPage {
  items: CoreAdminUserRow[];
  total: number;
  page: number;
  size: number;
  kpis: CoreAdminUserKpis;
}

export function coreAdminApiError(err: unknown, fallback: string): string {
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
