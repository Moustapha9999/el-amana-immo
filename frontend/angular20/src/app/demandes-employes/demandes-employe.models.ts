export interface ReqCategory {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  icon?: string | null;
  requires_stock_check: boolean;
  requires_attachment?: boolean;
  target_espace_code?: string;
}

export interface ReqItem {
  id?: string;
  article_id?: string | null;
  description: string;
  quantity: number;
  unit: string;
  estimated_unit_price: number;
  estimated_total?: number;
}

export interface ApprovalRow {
  id: string;
  action: string;
  status: string;
  comment?: string | null;
  acted_at: string;
}

export interface CommentRow {
  id: string;
  author_name?: string | null;
  body: string;
  created_at?: string;
}

export interface RequestRow {
  id: string;
  request_number: string;
  title: string;
  description?: string | null;
  status: string;
  priority: string;
  category_id?: string;
  category_name?: string | null;
  agency_id?: string;
  agency_label?: string | null;
  period?: string | null;
  submitted_at?: string | null;
  received_at?: string | null;
  validated_at?: string | null;
  rejected_at?: string | null;
  closed_at?: string | null;
  complement_comment?: string | null;
  rejection_reason?: string | null;
  validation_comment?: string | null;
  batch_number?: string | null;
  achat_demande_id?: string | null;
  target_espace_label?: string | null;
  comments?: CommentRow[];
  approvals?: ApprovalRow[];
  items: ReqItem[];
  created_at: string;
}

export interface InsightRow {
  tone: string;
  title: string;
  text: string;
  statut?: string | null;
}

export interface ChartSlice {
  code: string;
  name: string;
  count: number;
}

export interface MineDashboard {
  total: number;
  brouillons: number;
  a_completer: number;
  en_cours: number;
  soumises: number;
  recues: number;
  validees: number;
  refusees: number;
  servies: number;
  annulees: number;
  urgentes: number;
  notifications_non_lues: number;
  par_categorie: ChartSlice[];
  par_statut: ChartSlice[];
  recentes: RequestRow[];
  insights: InsightRow[];
}

export interface MineDocument {
  id: string;
  filename: string;
  title?: string | null;
  description?: string | null;
  doc_type?: string | null;
  mime_type?: string | null;
  size_bytes: number;
  ocr_status?: string | null;
  archived_at?: string | null;
  created_at: string;
  request_id: string;
  request_number: string;
  request_title: string;
  request_status: string;
}

export interface HistoryEvent {
  id: string;
  request_id: string;
  request_number: string;
  title: string;
  action: string;
  action_label: string;
  status: string;
  comment?: string | null;
  actor_name?: string | null;
  acted_at: string;
}

export interface RefRow {
  id: string;
  label: string;
  extra?: string | null;
}

export interface RequestNotif {
  id: string;
  titre: string;
  message: string;
  lu: boolean;
  entity?: string | null;
  entity_id?: string | null;
  created_at: string;
}

export const STATUS_LABEL: Record<string, string> = {
  BROUILLON: 'Brouillon',
  SOUMISE: 'Soumise',
  RECUE: 'Reçue',
  EN_ANALYSE: 'En analyse',
  A_COMPLETER: 'À compléter',
  VALIDEE: 'Validée',
  A_REGROUPER: 'Validée',
  REGROUPEE: 'Regroupée',
  ACHAT_EN_COURS: 'En achat',
  COMMANDEE: 'Commandée',
  SERVIE: 'Servie',
  CLOTUREE: 'Clôturée',
  REFUSEE: 'Refusée',
  ANNULEE: 'Désactivée',
};

export const PRIORITY_LABEL: Record<string, string> = {
  NORMALE: 'Normale',
  HAUTE: 'Haute',
  URGENTE: 'Urgente',
  URGENT: 'Urgente',
};

export const ACTION_TONE: Record<string, string> = {
  CREATED: 'draft',
  SUBMITTED: 'sent',
  RECEIVED: 'ok',
  REQUESTED_INFO: 'warn',
  VALIDATED: 'ok',
  REJECTED: 'danger',
  CANCELLED: 'muted',
  SERVED: 'ok',
  COMMENTED: 'info',
  ASSIGNED: 'info',
  RECATEGORIZED: 'info',
};

export const EDITABLE = new Set(['BROUILLON', 'A_COMPLETER']);
export const CANCELLABLE = new Set(['BROUILLON', 'SOUMISE', 'A_COMPLETER', 'RECUE']);
export const DELETE_LOCKED = new Set([
  'VALIDEE',
  'A_REGROUPER',
  'REGROUPEE',
  'ACHAT_EN_COURS',
  'COMMANDEE',
  'SERVIE',
  'CLOTUREE',
]);

export function statusLabel(code: string): string {
  return STATUS_LABEL[code] || code;
}

export function priorityLabel(code: string): string {
  return PRIORITY_LABEL[code] || code;
}

export function canDeleteRequest(row: { status: string; batch_number?: string | null; achat_demande_id?: string | null }): boolean {
  if (DELETE_LOCKED.has(row.status)) return false;
  if (row.batch_number || row.achat_demande_id) return false;
  return true;
}

export function formatQty(n: number | string | null | undefined): string {
  const v = typeof n === 'number' ? n : Number(String(n ?? '').replace(',', '.'));
  if (!Number.isFinite(v)) return '—';
  return String(Math.round(v));
}

export const VISA_OPTIONS: { id: string; label: string }[] = [
  { id: 'demandeur', label: 'Visa demandeur' },
  { id: 'chef', label: 'Visa chef de département' },
  { id: 'agence', label: 'Visa Agence concernée' },
  { id: 'mg', label: 'Visa Service Moyens Généraux' },
  { id: 'direction', label: 'Visa Direction' },
];

export function emptyItem(): ReqItem {
  return { description: '', quantity: 1, unit: 'U', estimated_unit_price: 0, article_id: null };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function fileSizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

export function barWidth(count: number, max: number): string {
  if (!max) return '0%';
  return `${Math.max(8, Math.round((count / max) * 100))}%`;
}
