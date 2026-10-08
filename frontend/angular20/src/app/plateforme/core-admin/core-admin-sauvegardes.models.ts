import { computed, inject } from '@angular/core';
import { AuthService } from '../../core/services/auth.service';

export type SrLevel = 'global' | 'departement' | 'module';

export interface SrUserRef {
  id: string;
  full_name?: string | null;
  email?: string | null;
}

export interface SrArtifact {
  file: string;
  bytes: number;
  sha256: string;
  files?: number;
  raw_bytes?: number;
}

export interface SrBackup {
  id: string;
  level: SrLevel;
  type: string;
  backup_type: string;
  espace_code?: string | null;
  module_code?: string | null;
  perimetre: string;
  status: string;
  emplacement?: string | null;
  artifacts?: Record<string, SrArtifact>;
  size_bytes: number;
  tables_count: number;
  rows_total?: number | null;
  ged_documents?: number | null;
  files_count?: number | null;
  modules?: string[] | null;
  departements?: string[] | null;
  alembic_revision?: string | null;
  error_message?: string | null;
  administrateur?: SrUserRef | null;
  ip_address?: string | null;
  label?: string | null;
  checksum_sha256?: string | null;
  integrity_status?: string | null;
  integrity_checked_at?: string | null;
  integrity_detail?: string | null;
  duration_ms?: number | null;
  format: string;
  restorable: boolean;
  confirmation_phrase: string;
  created_at?: string | null;
  finished_at?: string | null;
  restores?: SrRestore[];
  manifest?: Record<string, unknown> | null;
}

export interface SrDeletedBackup {
  id: string;
  label?: string | null;
  level?: string | null;
  created_at?: string | null;
  deleted_at?: string | null;
}

export interface SrRestore {
  id: string;
  backup_id: string | null;
  deleted_backup?: SrDeletedBackup | null;
  safety_backup_id?: string | null;
  level: SrLevel;
  type: string;
  espace_code?: string | null;
  module_code?: string | null;
  perimetre: string;
  status: string;
  reason?: string | null;
  dependency_warning?: string | null;
  options?: { include_security?: boolean } | null;
  details?: {
    tables?: string[];
    tables_count?: number;
    ged_codes?: string[];
    file_targets?: string[];
    preserved_tables?: string[];
  } | null;
  error_message?: string | null;
  ip_address?: string | null;
  duration_ms?: number | null;
  administrateur?: SrUserRef | null;
  created_at?: string | null;
  finished_at?: string | null;
}

export interface SrModule {
  code: string;
  label: string;
  statut?: string | null;
  known: boolean;
  tables: string[];
  tables_count: number;
  missing_tables: string[];
  ged_codes: string[];
  ged_documents?: number;
  backupable: boolean;
}

export interface SrDepartement {
  code: string;
  label: string;
  statut: string;
  modules: SrModule[];
  modules_count: number;
  backupable_modules: number;
  backupable: boolean;
}

export interface SrCatalogue {
  departements: SrDepartement[];
  departements_count: number;
  modules_count: number;
}

export interface SrBackupPreview {
  level: SrLevel;
  type: string;
  perimetre: string;
  espace_code?: string | null;
  module_code?: string | null;
  departements_count: number;
  modules_count: number;
  modules: SrModule[];
  tables_count: number;
  rows_total: number;
  rows_exact: boolean;
  ged_documents: number;
  file_targets: string[];
  estimated_bytes: number;
  backupable: boolean;
  warnings: string[];
  administrateur: SrUserRef;
  generated_at: string;
}

export interface SrRestorePreview {
  backup: SrBackup;
  level: SrLevel;
  type: string;
  include_security: boolean;
  tables: { name: string; rows_backup?: number | null; rows_current?: number | null }[];
  tables_count: number;
  preserved_tables: string[];
  ged: { module_codes: string[]; rows_backup?: number | null; rows_current: number };
  file_targets: string[];
  dependencies: {
    table: string;
    references: string;
    direction: string;
    module_code?: string | null;
    module_label?: string | null;
  }[];
  warnings: string[];
  confirmation_phrase: string;
  safety_backup: boolean;
  alembic: { backup?: string | null; current?: string | null };
}

export interface SrHistoryItem {
  kind: 'backup' | 'restore';
  id: string;
  backup_id: string | null;
  created_at?: string | null;
  level: SrLevel;
  type: string;
  subtype: string;
  perimetre: string;
  espace_code?: string | null;
  module_code?: string | null;
  status: string;
  size_bytes: number;
  duration_ms?: number | null;
  integrity_status?: string | null;
  error_message?: string | null;
  label?: string | null;
  administrateur?: SrUserRef | null;
}

export interface SrDashboard {
  total: number;
  success: number;
  failed: number;
  restores_total: number;
  restores_success: number;
  restores_failed: number;
  integrity_ko: number;
  total_size_bytes: number;
  disk?: { total: number; free: number } | null;
  derniere_globale?: SrBackup | null;
  dernieres_sauvegardes: SrBackup[];
  dernieres_restaurations: SrRestore[];
  erreurs: (Partial<SrBackup & SrRestore> & { kind: 'backup' | 'restore' })[];
}

export interface SrVerifyResult {
  backup_id: string;
  integrity_status: string;
  checked_at?: string | null;
  checks: { artifact: string; ok: boolean; detail: string; sha256?: string }[];
}

export const SR_API = '/plateforme/admin';

export const SR_LEVELS: { value: SrLevel; label: string; icon: string; hint: string }[] = [
  { value: 'global', label: 'Globale', icon: 'public', hint: 'Toute la plateforme BEA DIGITAL' },
  { value: 'departement', label: 'Département', icon: 'domain', hint: 'Tous les modules d’un département' },
  { value: 'module', label: 'Module', icon: 'extension', hint: 'Un seul module' },
];

const STATUS_LABELS: Record<string, string> = {
  success: 'Réussie',
  failed: 'Échec',
  partial: 'Partielle',
  running: 'En cours',
  pending: 'En attente',
};

const BACKUP_TYPE_LABELS: Record<string, string> = {
  manuelle: 'Manuelle',
  automatique: 'Automatique',
  avant_maintenance: 'Avant maintenance',
  avant_mise_a_jour: 'Avant mise à jour',
  avant_migration: 'Avant migration',
  securite_recovery: 'Sécurité (avant recovery)',
  recovery: 'Restauration',
};

const ARTIFACT_LABELS: Record<string, string> = {
  dump: 'Base PostgreSQL (.dump)',
  ged_rows: 'Lignes GED du périmètre',
  files: 'Fichiers (GED / uploads)',
  manifest: 'Manifeste',
  sauvegarde: 'Sauvegarde',
};

export function srStatusLabel(status: string | null | undefined): string {
  return STATUS_LABELS[status ?? ''] ?? status ?? '—';
}

export function srBackupTypeLabel(type: string | null | undefined): string {
  return BACKUP_TYPE_LABELS[type ?? ''] ?? type ?? '—';
}

export function srArtifactLabel(key: string): string {
  return ARTIFACT_LABELS[key] ?? key;
}

export function srBytes(value: number | null | undefined): string {
  const n = Number(value ?? 0);
  if (!n) return '0 o';
  const units = ['o', 'Ko', 'Mo', 'Go', 'To'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toLocaleString('fr-FR', { maximumFractionDigits: i ? 1 : 0 })} ${units[i]}`;
}

export function srDuration(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${Math.round(s % 60)} s`;
}

export function srUser(u: SrUserRef | null | undefined): string {
  return u?.full_name || u?.email || '—';
}

/** Masquage UI seulement : chaque endpoint revérifie la permission. */
export function srPermissions() {
  const auth = inject(AuthService);
  const has = (code: string) =>
    computed(() => {
      const p = auth.user();
      if (!p) return false;
      const codes = p.permission_codes ?? [];
      return p.is_superuser || codes.includes('*') || codes.includes(code);
    });
  return {
    view: has('core.admin.backup.view'),
    create: has('core.admin.backup.create'),
    delete: has('core.admin.backup.delete'),
    download: has('core.admin.backup.download'),
    recoveryView: has('core.admin.recovery.view'),
    recoveryExec: has('core.admin.recovery.execute'),
  };
}

export function srSaveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
