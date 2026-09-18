import { HttpErrorResponse } from '@angular/common/http';

export type CoreAdminStatutFiltre = 'tous' | 'actif' | 'bientot' | 'inactif';

export interface CoreAdminCatalogueKpis {
  total: number;
  actifs: number;
  bientot: number;
  inactifs: number;
}

export interface CoreAdminEspaceRow {
  id: string;
  code: string;
  label: string;
  description: string;
  route?: string | null;
  statut: string;
  sort_order: number;
  is_active: boolean;
  locked: boolean;
  modules_count: number;
  users_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CoreAdminModuleSummary {
  id: string;
  code: string;
  label: string;
  statut: string;
  is_active: boolean;
  locked: boolean;
}

export interface CoreAdminEspaceFiche extends CoreAdminEspaceRow {
  modules: CoreAdminModuleSummary[];
}

export interface CoreAdminEspacePage {
  items: CoreAdminEspaceRow[];
  total: number;
  page: number;
  size: number;
  kpis: CoreAdminCatalogueKpis;
}

export interface CoreAdminModuleRow {
  id: string;
  code: string;
  label: string;
  description: string;
  entry_path?: string | null;
  statut: string;
  sort_order: number;
  is_active: boolean;
  locked: boolean;
  espace_id: string;
  espace_code: string;
  espace_label: string;
  users_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CoreAdminModulePage {
  items: CoreAdminModuleRow[];
  total: number;
  page: number;
  size: number;
  kpis: CoreAdminCatalogueKpis;
}

export interface CoreAdminEspaceOption {
  id: string;
  code: string;
  label: string;
  is_active: boolean;
}

export function catalogueStatut(row: { is_active: boolean; statut: string }): string {
  return row.is_active ? row.statut : 'inactif';
}

export function catalogueStatutLabel(statut: string): string {
  if (statut === 'actif') {
    return 'Actif';
  }
  if (statut === 'bientot') {
    return 'Bientôt';
  }
  if (statut === 'inactif') {
    return 'Inactif';
  }
  return statut;
}

export function coreAdminCatalogueError(err: unknown, fallback: string): string {
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
