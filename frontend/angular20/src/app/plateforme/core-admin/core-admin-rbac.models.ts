import { HttpErrorResponse } from '@angular/common/http';

export type CoreAdminRbacKind = 'tous' | 'systeme' | 'custom';

export interface CoreAdminRbacKpis {
  total: number;
  systeme: number;
  custom: number;
  with_users?: number;
  unused?: number;
}

export interface CoreAdminPermissionSummary {
  id: string;
  code: string;
  label: string;
  module: string;
  locked: boolean;
}

export interface CoreAdminRoleSummary {
  id: string;
  code: string;
  label: string;
  locked: boolean;
}

export interface CoreAdminRoleRow {
  id: string;
  code: string;
  label: string;
  description: string;
  locked: boolean;
  permissions_count: number;
  users_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CoreAdminRoleFiche extends CoreAdminRoleRow {
  permission_codes: string[];
  permissions: CoreAdminPermissionSummary[];
}

export interface CoreAdminRolePage {
  items: CoreAdminRoleRow[];
  total: number;
  page: number;
  size: number;
  kpis: CoreAdminRbacKpis;
}

export interface CoreAdminRoleOptions {
  permissions: CoreAdminPermissionSummary[];
  modules: string[];
}

export interface CoreAdminPermissionRow {
  id: string;
  code: string;
  label: string;
  module: string;
  locked: boolean;
  roles_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CoreAdminPermissionFiche extends CoreAdminPermissionRow {
  roles: CoreAdminRoleSummary[];
}

export interface CoreAdminPermissionPage {
  items: CoreAdminPermissionRow[];
  total: number;
  page: number;
  size: number;
  kpis: CoreAdminRbacKpis;
}

export interface CoreAdminPermissionOptions {
  modules: string[];
}

export interface CoreAdminMatrixKpis {
  roles: number;
  permissions: number;
  grants: number;
  modules: number;
}

export interface CoreAdminMatrixRead {
  roles: CoreAdminRoleSummary[];
  permissions: CoreAdminPermissionSummary[];
  grants: Record<string, string[]>;
  modules: string[];
  kpis: CoreAdminMatrixKpis;
}

export interface CoreAdminMatrixGrantResult {
  role_id: string;
  permission_code: string;
  granted: boolean;
}

export function rbacKindLabel(locked: boolean): string {
  return locked ? 'Système' : 'Personnalisé';
}

export function coreAdminRbacError(err: unknown, fallback: string): string {
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
