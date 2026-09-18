import { HttpErrorResponse } from '@angular/common/http';

export type CoreAdminSessionKind = 'tous' | 'platform' | 'module';
export type CoreAdminSessionStatus = 'tous' | 'actives' | 'expirees' | 'revoquees';

export interface CoreAdminSessionKpis {
  total: number;
  actives: number;
  platform: number;
  module: number;
  expirees: number;
  revoquees: number;
}

export interface CoreAdminSessionRow {
  id: string;
  user_id: string;
  user_email: string;
  user_full_name: string;
  kind: string;
  module_code?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  active: boolean;
  is_current: boolean;
}

export interface CoreAdminSessionPage {
  items: CoreAdminSessionRow[];
  total: number;
  page: number;
  size: number;
  kpis: CoreAdminSessionKpis;
  current_session_id?: string | null;
}

export function sessionKindLabel(kind: string): string {
  return kind === 'module' ? 'Module' : 'BEA DIGITAL';
}

export function sessionStatusLabel(row: CoreAdminSessionRow): string {
  if (row.revoked_at) {
    return 'Révoquée';
  }
  if (row.active) {
    return 'Active';
  }
  return 'Expirée';
}

export function coreAdminSessionsError(err: unknown, fallback: string): string {
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
