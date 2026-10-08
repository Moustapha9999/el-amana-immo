import { computed, inject } from '@angular/core';
import { AuthService } from '../../core/services/auth.service';

export const CQ_API = '/plateforme/admin/core-query';

export type CqSource = 'assistant' | 'builder' | 'sql';
export type CqKind = 'number' | 'boolean' | 'date' | 'datetime' | 'interval' | 'json' | 'text' | 'uuid' | 'enum' | 'other';

export interface CqColumn {
  name: string;
  label: string;
  type: string;
  kind: CqKind;
  nullable: boolean;
  enum_values?: string[] | null;
  primary_key: boolean;
}

export interface CqTable {
  name: string;
  label: string;
  primary_key: string[];
  hidden_columns: number;
  columns: CqColumn[];
}

export interface CqRelation {
  name: string;
  table: string;
  columns: string[];
  ref_table: string;
  ref_columns: string[];
}

export interface CqSchema {
  fingerprint: string;
  tables: CqTable[];
  relations: CqRelation[];
  reader_role: { role: string; available: boolean; error?: string | null };
  examples: string[];
  permissions: { execute: boolean; sql: boolean; export: boolean; admin?: boolean; all_history: boolean };
  limits: { default: number; max: number; export: number };
}

export interface CqPeriod {
  label: string;
  date?: string | null;
  hours?: string | null;
}

export interface CqInterpretation {
  ok: boolean;
  intent: string;
  title: string;
  sql?: string | null;
  tables: string[];
  columns: string[];
  filters: string[];
  relations: string[];
  group_by: string[];
  order_by?: string | null;
  limit?: number | null;
  period?: CqPeriod | null;
  assumptions: string[];
  clarification?: string | null;
  suggestions: string[];
  confidence: 'haute' | 'moyenne' | 'faible';
  validation?: { ok: boolean; tables?: string[]; code?: string; message?: string } | null;
}

export interface CqStep {
  key: string;
  label: string;
  status: 'ok' | 'failed' | 'pending';
}

export interface CqResultColumn {
  name: string;
  type: string;
  kind: CqKind;
}

export interface CqResult {
  log_id: string;
  source: CqSource;
  question?: string | null;
  sql: string;
  tables: string[];
  columns: CqResultColumn[];
  rows: unknown[][];
  total: number;
  returned: number;
  truncated: boolean;
  limit: number;
  duration_ms: number;
  read_only_role: boolean;
  steps: CqStep[];
  executed_at: string;
  admin_mode?: boolean;
  dry_run?: boolean;
  is_write?: boolean;
  committed?: boolean;
  command_tag?: string | null;
  affected_rows?: number | null;
}

export interface CqFailure {
  code: string;
  reason: string;
  message: string;
  requestId?: string | null;
  steps: CqStep[];
  sql?: string | null;
}

export interface CqExecutePayload {
  mode?: CqSource;
  question?: string | null;
  expected_sql?: string | null;
  spec?: CqBuilderSpec | null;
  sql?: string | null;
  favorite_id?: string | null;
  limit?: number | null;
  admin?: boolean;
  dry_run?: boolean;
  reason?: string | null;
}

export interface CqBuilderJoin {
  relation: string;
  from: string;
  direction: 'out' | 'in';
  type: 'left' | 'inner';
}

export interface CqBuilderColumn {
  alias: string;
  column: string;
  aggregate?: string | null;
}

export interface CqBuilderFilter {
  alias: string;
  column: string;
  operator: string;
  value?: string | null;
  value2?: string | null;
}

export interface CqBuilderSpec {
  table: string;
  joins: CqBuilderJoin[];
  columns: CqBuilderColumn[];
  filters: CqBuilderFilter[];
  order_by: { alias: string; column: string; direction: 'asc' | 'desc' }[];
  distinct: boolean;
  limit?: number | null;
}

export interface CqBuildResult {
  sql: string;
  tables: string[];
  columns: string[];
  relations: string[];
  filters: string[];
  group_by: string[];
  order_by?: string | null;
  limit?: number | null;
}

export interface CqFavorite {
  id: string;
  name: string;
  description?: string | null;
  source: CqSource;
  question?: string | null;
  sql?: string | null;
  spec?: CqBuilderSpec | null;
  is_system: boolean;
  run_count: number;
  last_run_at?: string | null;
  created_at?: string | null;
}

export interface CqLog {
  id: string;
  user_name?: string | null;
  user_email?: string | null;
  source: CqSource;
  question?: string | null;
  sql?: string | null;
  tables: string[];
  status: 'success' | 'refused' | 'error';
  error_code?: string | null;
  error_message?: string | null;
  result_count?: number | null;
  truncated: boolean;
  duration_ms?: number | null;
  export_format?: string | null;
  admin_mode?: boolean;
  dry_run?: boolean;
  command_tag?: string | null;
  reason?: string | null;
  created_at?: string | null;
}

export interface CqDashboard {
  today: { total: number; success: number; refused: number; errors: number; avg_ms: number | null };
  recent: CqLog[];
  favorites: CqFavorite[];
  favorites_count: number;
  reader_role: { role: string; available: boolean; error?: string | null };
}

export const CQ_OPERATORS: { value: string; label: string; needsValue: 0 | 1 | 2 }[] = [
  { value: 'eq', label: '=', needsValue: 1 },
  { value: 'ne', label: '!=', needsValue: 1 },
  { value: 'gt', label: '>', needsValue: 1 },
  { value: 'lt', label: '<', needsValue: 1 },
  { value: 'gte', label: '>=', needsValue: 1 },
  { value: 'lte', label: '<=', needsValue: 1 },
  { value: 'contains', label: 'contient', needsValue: 1 },
  { value: 'starts_with', label: 'commence par', needsValue: 1 },
  { value: 'between', label: 'entre', needsValue: 2 },
  { value: 'is_empty', label: 'est vide', needsValue: 0 },
  { value: 'is_not_empty', label: 'n’est pas vide', needsValue: 0 },
];

export const CQ_AGGREGATES: { value: string; label: string }[] = [
  { value: '', label: 'Valeur' },
  { value: 'count', label: 'Nombre' },
  { value: 'count_distinct', label: 'Nombre distinct' },
  { value: 'sum', label: 'Somme' },
  { value: 'avg', label: 'Moyenne' },
  { value: 'min', label: 'Minimum' },
  { value: 'max', label: 'Maximum' },
];

const SOURCE_LABELS: Record<string, string> = { assistant: 'Assistant', builder: 'Query Builder', sql: 'SQL' };
const STATUS_LABELS: Record<string, string> = { success: 'Réussie', refused: 'Refusée', error: 'Erreur' };
const KIND_LABELS: Record<string, string> = {
  number: 'nombre',
  boolean: 'oui / non',
  date: 'date',
  datetime: 'date et heure',
  interval: 'durée',
  json: 'json',
  text: 'texte',
  uuid: 'identifiant',
  enum: 'liste',
  other: 'autre',
};

export function cqSourceLabel(s: string | null | undefined): string {
  return SOURCE_LABELS[s ?? ''] ?? s ?? '—';
}

export function cqStatusLabel(s: string | null | undefined): string {
  return STATUS_LABELS[s ?? ''] ?? s ?? '—';
}

export function cqKindLabel(k: string | null | undefined): string {
  return KIND_LABELS[k ?? ''] ?? k ?? '';
}

export function cqDuration(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} s`;
}

/** Masquage UI seulement : chaque endpoint revérifie la permission. */
export function cqPermissions() {
  const auth = inject(AuthService);
  const has = (code: string) =>
    computed(() => {
      const p = auth.user();
      if (!p) return false;
      const codes = p.permission_codes ?? [];
      return p.is_superuser || codes.includes('*') || codes.includes(code);
    });
  return {
    view: has('core.admin.query.view'),
    execute: has('core.admin.query.execute'),
    sql: has('core.admin.query.sql'),
    export: has('core.admin.query.export'),
    admin: has('core.admin.query.admin'),
  };
}

const CQ_STRIP = /--[^\n]*|\/\*[\s\S]*?\*\/|\$([A-Za-z_]\w*|)\$[\s\S]*?\$\1\$|'(?:[^']|'')*'|"(?:[^"]|"")*"/g;
const CQ_WRITE =
  /\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|ALTER|DROP|GRANT|REVOKE|COMMENT|CALL|DO|REINDEX|CLUSTER|VACUUM|REFRESH|SECURITY|LOCK|SET|RESET|DISCARD|NOTIFY|SELECT\s[\s\S]*\bINTO)\b/i;

/** Indication UI (motif demandé) ; le backend reclasse la requête avec la même règle. */
export function cqIsWriteSql(sql: string): boolean {
  return CQ_WRITE.test(sql.replace(CQ_STRIP, ' '));
}

/* ------------------------------------------------------------------ coloration SQL */

export interface CqSqlToken {
  k: 'kw' | 'fn' | 'str' | 'num' | 'com' | 'id' | 'op' | 'ws';
  v: string;
}

const SQL_KEYWORDS = new Set(
  (
    'select from where and or not in is null as join left right inner full outer cross on using group by order ' +
    'having limit offset distinct case when then else end between like ilike exists union all intersect except ' +
    'with recursive asc desc nulls first last true false interval over partition filter within lateral cast ' +
    'insert update delete drop alter truncate create grant revoke'
  ).split(' '),
);

export function cqTokenizeSql(sql: string): CqSqlToken[] {
  const out: CqSqlToken[] = [];
  const re =
    /(--[^\n]*|\/\*[\s\S]*?\*\/)|('(?:[^']|'')*'?)|("(?:[^"]|"")*"?)|(\d+(?:\.\d+)?)|([A-Za-z_][A-Za-z0-9_]*)(?=\s*\()|([A-Za-z_][A-Za-z0-9_]*)|(\s+)|([^\sA-Za-z0-9_'"]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(sql))) {
    if (m[1]) out.push({ k: 'com', v: m[1] });
    else if (m[2]) out.push({ k: 'str', v: m[2] });
    else if (m[3]) out.push({ k: 'id', v: m[3] });
    else if (m[4]) out.push({ k: 'num', v: m[4] });
    else if (m[5]) out.push({ k: SQL_KEYWORDS.has(m[5].toLowerCase()) ? 'kw' : 'fn', v: m[5] });
    else if (m[6]) out.push({ k: SQL_KEYWORDS.has(m[6].toLowerCase()) ? 'kw' : 'id', v: m[6] });
    else if (m[7]) out.push({ k: 'ws', v: m[7] });
    else out.push({ k: 'op', v: m[8] ?? m[0] });
  }
  return out;
}
