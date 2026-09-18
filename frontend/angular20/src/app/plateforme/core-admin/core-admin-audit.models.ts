import { HttpErrorResponse } from '@angular/common/http';

export interface CoreAdminAuditKpis {
  total: number;
  aujourd_hui: number;
  logins: number;
  mutations: number;
  core: number;
}

export interface CoreAdminAuditRow {
  id: string;
  user_id?: string | null;
  user_email?: string | null;
  user_full_name?: string | null;
  action: string;
  entity: string;
  entity_id?: string | null;
  ip_address?: string | null;
  espace_code?: string | null;
  module_code?: string | null;
  session_id?: string | null;
  created_at?: string | null;
}

export interface CoreAdminAuditPage {
  items: CoreAdminAuditRow[];
  total: number;
  page: number;
  size: number;
  kpis: CoreAdminAuditKpis;
  modules: string[];
  entities: string[];
}

const ACTION_LABELS: Record<string, string> = {
  login: 'Connexion',
  create: 'Création',
  update: 'Modification',
  delete: 'Suppression',
  revoke: 'Révocation',
  revoke_all: 'Révocation globale',
  deactivate: 'Désactivation',
  activate: 'Activation',
};

export function coreAdminAuditActionLabel(code: string): string {
  return ACTION_LABELS[code] ?? code;
}

export function coreAdminAuditError(err: unknown, fallback: string): string {
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
