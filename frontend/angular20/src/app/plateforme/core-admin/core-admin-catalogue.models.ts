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
  icon?: string | null;
  modules_count: number;
  users_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export type CoreAdminDomaineStatut = 'actif' | 'bientot' | 'developpement' | 'inactif';

export interface CoreAdminDomaineRow {
  id: string;
  code: string;
  espace_id: string;
  espace_code: string;
  parent_id: string | null;
  parent_code: string | null;
  label: string;
  description: string;
  icon: string | null;
  statut: CoreAdminDomaineStatut | string;
  status_message: string;
  sort_order: number;
  is_active: boolean;
  modules_count: number;
  children_count: number;
}

export interface CoreAdminDomaineOption {
  id: string;
  code: string;
  label: string;
  espace_id: string;
  parent_id: string | null;
  is_active: boolean;
}

/** Nom de glyphe Material Icons (police déjà chargée) — même règle que le backend. */
export const ICON_NAME_PATTERN = /^[a-z0-9_]{1,60}$/;

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
  domaines?: CoreAdminDomaineRow[];
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
  icon?: string | null;
  domaine_id?: string | null;
  domaine_code?: string | null;
  domaine_label?: string | null;
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
  if (statut === 'developpement') {
    return 'En développement';
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
