export const RBCM_BASE = '/reporting-bcm-sm';
export const RBCM_API = '/reporting-bcm-sm';

export interface RbcmCampaign {
  id: string;
  period_year: number;
  period_month: number;
  closing_date: string | null;
  bank_code: string;
  status: string;
  campaign_version: number;
  reopened_from_id: string | null;
  preparer_id: string | null;
  preparer_name?: string | null;
  reporting_owner_id?: string | null;
  reporting_owner_name?: string | null;
  reporting_owner_set_at?: string | null;
  controller_id?: string | null;
  approver_id?: string | null;
  locked_at?: string | null;
  approved_at?: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface RbcmOwnerCandidate {
  id: string;
  full_name: string;
  email: string;
}

export interface RbcmOwnerHistory {
  id: string;
  campaign_id: string;
  from_owner_id: string | null;
  from_owner_name?: string | null;
  to_owner_id: string | null;
  to_owner_name?: string | null;
  actor_id: string | null;
  actor_name?: string | null;
  motif: string;
  created_at: string;
}

export interface RbcmCampaignList {
  items: RbcmCampaign[];
  total: number;
  page: number;
  page_size: number;
}

export interface RbcmChartSlice {
  label: string;
  value: number;
}

export interface RbcmDashboard {
  campaigns_total: number;
  campaigns_open: number;
  campaigns_pending: number;
  campaigns_closed: number;
  campaigns_in_progress?: number;
  campaigns_calculated?: number;
  campaigns_approved?: number;
  campaigns_archived?: number;
  imports_validated: number;
  imports_anomaly: number;
  parameters_missing: number;
  parameters_filled?: number;
  avg_progress_pct: number;
  by_status: RbcmChartSlice[];
  imports_by_type: RbcmChartSlice[];
  imports_monthly: { label: string; value: number }[];
  anomalies_by_code: RbcmChartSlice[];
  mapping_by_lifecycle?: RbcmChartSlice[];
  status_groups?: Record<string, string[]>;
  recent_campaigns?: { id: string; label: string; status: string; created_at: string | null }[];
  recent_imports?: {
    id: string;
    campaign_id: string;
    file_type: string;
    filename: string;
    status: string;
    created_at: string | null;
  }[];
}

export interface RbcmReconcileIssueList {
  items: RbcmReconcileIssue[];
  total: number;
  page: number;
  page_size: number;
}

export interface RbcmDeleteCheck {
  can_delete: boolean;
  can_archive: boolean;
  reasons: string[];
  dependencies: {
    imports: number;
    imports_confirmed?: number;
    imports_draft?: number;
    parameters: number;
    workflow_events: number;
    status: string;
  };
}

export interface RbcmImportList {
  items: RbcmImport[];
  total: number;
  page: number;
  page_size: number;
}

export interface RbcmCondLine {
  id: string;
  ncg: string;
  libelle: string | null;
  tot_debit: string | number;
  tot_credit: string | number;
  source: string;
  var: string | number | null;
}

export interface RbcmCondLineList {
  items: RbcmCondLine[];
  total: number;
  page: number;
  page_size: number;
}

export interface RbcmMappingSummary {
  total: number;
  by_lifecycle: Record<string, number>;
  a_valider: number;
  active: number;
  rejected: number;
  superseded: number;
  activation_policy: string;
}

export interface RbcmAccueil {
  module_code: string;
  open_campaigns: number;
  last_campaign: RbcmCampaign | null;
  pending_decisions: string[];
  ecart_policy: string;
  mapping_policy: string;
  dashboard?: RbcmDashboard | null;
}

export interface RbcmProgress {
  det_validated: boolean;
  cond_validated: boolean;
  parameters_filled: number;
  parameters_validated: number;
  parameters_total: number;
  steps_done: number;
  steps_total: number;
  pct: number;
  imports_count: number;
  imports_anomaly: number;
  last_control_run_id?: string | null;
  last_control_result?: string | null;
  last_control_at?: string | null;
  complements_open?: number;
}

export interface RbcmImport {
  id: string;
  campaign_id: string;
  file_type: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  status: string;
  period_year_detected: number | null;
  period_month_detected: number | null;
  control_report: Record<string, unknown> | null;
  row_count: number | null;
  sum_debit: string | number | null;
  sum_credit: string | number | null;
  created_at: string;
  validated_at?: string | null;
  uploaded_by_id?: string | null;
  validated_by_id?: string | null;
}

export interface RbcmDetLine {
  id: string;
  line_no: number;
  ncg: string | null;
  compte: string | null;
  libelle: string | null;
  devise: string | null;
  debit: string | number;
  credit: string | number;
}

export interface RbcmDetLineList {
  items: RbcmDetLine[];
  total: number;
  page: number;
  page_size: number;
}

export interface RbcmParamCatalog {
  code: string;
  label: string;
  calculable: boolean;
  value: string | null;
  value_id: string | null;
  source: string | null;
  justification: string | null;
  justificatif_ref?: string | null;
  status: string;
  authored_by_id: string | null;
  validated_by_id: string | null;
  created_at: string | null;
}

export interface RbcmParameterValue {
  id: string;
  campaign_id: string;
  parameter_code: string;
  value: string | number | null;
  source: string | null;
  justification: string | null;
  justificatif_ref?: string | null;
  status: string;
  authored_by_id: string | null;
  validated_by_id?: string | null;
  validated_at?: string | null;
  supersedes_value_id?: string | null;
  created_at: string;
}

export interface RbcmControlRun {
  id: string;
  campaign_id: string;
  actor_id: string | null;
  actor_name?: string | null;
  result: string;
  previous_run_id: string | null;
  summary: Record<string, unknown> | null;
  created_at: string | null;
  counts?: {
    total?: number;
    ok?: number;
    open?: number;
    blocking?: number;
    pending_decision?: number;
    by_category?: Record<string, number>;
  };
  issues?: RbcmComplementItem[];
}

export interface RbcmComplementItem {
  id: string;
  campaign_id: string;
  run_id: string | null;
  category: 'A' | 'B' | 'C' | 'D' | string | null;
  item_key: string | null;
  code: string;
  title: string;
  message: string;
  severity: string;
  resolution_state: string;
  resolved: boolean;
  ncg: string | null;
  observed: string | null;
  expected: string | null;
  source: string | null;
  expected_source: string | null;
  consequence: string | null;
  recommended_action: string | null;
  action_code: string | null;
  available_actions: string[];
  live_state: string | null;
  parameter_code?: string | null;
  current_value_id?: string | null;
  proposed_value?: string | null;
  unit?: string | null;
  details: Record<string, unknown> | null;
  created_at: string | null;
}

export interface RbcmComplements {
  run: RbcmControlRun | null;
  items: RbcmComplementItem[];
  by_category: Record<string, RbcmComplementItem[]>;
  counts: Record<string, number>;
  can_saisir?: boolean;
  can_control?: boolean;
  can_importer?: boolean;
  technical_failure?: boolean;
}

export interface RbcmReconcileIssue {
  id: string;
  campaign_id: string;
  ncg: string | null;
  severity: string;
  code: string;
  message: string;
  details: Record<string, unknown> | null;
  resolved: boolean;
  created_at: string;
}

export interface RbcmReconcile {
  campaign_id: string;
  ready: boolean;
  summary: Record<string, unknown> | null;
  summary_message: string | null;
  issues: RbcmReconcileIssue[];
  issues_count: number;
}

export interface RbcmHistoryEvent {
  id: string;
  campaign_id: string;
  action: string;
  from_status: string | null;
  to_status: string | null;
  comment: string | null;
  actor_id: string | null;
  created_at: string;
}

export const STATUS_LABELS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  IMPORTS: 'Imports',
  RAPPROCHEE: 'Contrôlée (DET)',
  PARAMETREE: 'Paramétrée',
  CALCULEE: 'Calculée',
  A_CONTROLER: 'En attente de validation',
  APPROUVEE: 'Approuvée',
  CLOTUREE: 'Clôturée',
  ROUVERTE: 'Rouverte',
};

/** Libellés métier SM (Situation Mensuelle) — ne pas exposer « Campagne » à l’utilisateur. */
export const SM_TERM = {
  singular: 'SM',
  full: 'Situation Mensuelle',
  plural: 'Situations mensuelles',
  selectedNone: 'Aucune SM sélectionnée',
  selectOne: 'Sélectionnez une SM',
} as const;

/** Cycle de vie import (backend : ANALYZED / VALIDATED / SUPERSEDED / REJECTED). */
export const IMPORT_STATUS_LABELS: Record<string, string> = {
  ANALYZED: 'Analysé',
  VALIDATED: 'Confirmé',
  SUPERSEDED: 'Remplacé',
  REJECTED: 'Rejeté',
};

export const SM_GUIDED_STEPS = [
  { n: 1, key: 'infos', label: 'Informations de la SM' },
  { n: 2, key: 'bal', label: 'BAL DET' },
  { n: 3, key: 'controles', label: 'Contrôles' },
  { n: 4, key: 'completer', label: 'Informations à compléter' },
  { n: 5, key: 'preparer', label: 'Préparation' },
  { n: 6, key: 'verifier', label: 'Vérification du document' },
  { n: 7, key: 'valider', label: 'Validation et téléchargement' },
] as const;

/** Étape courante du parcours guidé (1–7). T3.5-2 : 5–7 restent ultérieures. */
export function currentGuidedStep(c: RbcmCampaign, p?: RbcmProgress | null): number {
  if (c.status === 'APPROUVEE' || c.status === 'CLOTUREE') return 7;
  if (c.status === 'A_CONTROLER') return 6;
  if (!p?.det_validated) return 2;
  if (!p.last_control_run_id) return 3;
  return 4;
}

export const CONTROL_CATEGORY_LABELS: Record<string, string> = {
  A: 'Données calculables (BAL DET)',
  B: 'Autre source requise',
  C: 'Saisie manuelle',
  D: 'Décision métier',
};

export const CONTROL_RESULT_LABELS: Record<string, string> = {
  OK: 'Contrôles aboutis',
  WARNINGS: 'Avertissements',
  INCOMPLETE: 'Informations incomplètes',
  DECISIONS_PENDING: 'Décisions métier en attente',
  BLOCKING: 'Anomalie bloquante',
  FAILED: 'Échec technique',
};

export const RESOLUTION_LABELS: Record<string, string> = {
  OPEN: 'Ouverte',
  IN_PROGRESS: 'En cours de traitement',
  RESOLVED: 'Résolue',
  STILL_BLOCKING: 'Toujours bloquante',
  PENDING_DECISION: 'En attente d’une décision métier',
  OK: 'OK',
  SAISIE_A_RECONTROLER: 'Saisie à recontrôler',
};

export function guidedStepState(
  step: number,
  current: number,
): 'done' | 'current' | 'wait' | 'blocked' {
  if (step < current) return 'done';
  if (step === current) return 'current';
  if (step >= 5) return 'blocked';
  return 'wait';
}

export function periodLabel(c: RbcmCampaign): string {
  return `${String(c.period_month).padStart(2, '0')}/${c.period_year} · v${c.campaign_version}`;
}

export function deleteCampaignConfirm(c: RbcmCampaign, chk?: RbcmDeleteCheck | null): string {
  const st = STATUS_LABELS[c.status] || c.status;
  const d = chk?.dependencies;
  const bits: string[] = [];
  if (d?.imports) bits.push(`${d.imports} import(s)`);
  if (d?.parameters) bits.push(`${d.parameters} paramètre(s)`);
  const extra = bits.length ? ` Seront aussi retirés : ${bits.join(', ')}.` : '';
  return (
    `${periodLabel(c)} (${st}) : suppression définitive, quel que soit le statut.` +
    extra +
    ' Tous les calculs, contrôles et documents liés seront retirés.'
  );
}

export function statusTone(status: string): 'ok' | 'warn' | 'danger' | 'info' | null {
  if (status === 'APPROUVEE' || status === 'CLOTUREE' || status === 'RAPPROCHEE') return 'ok';
  if (status === 'A_CONTROLER' || status === 'CALCULEE') return 'warn';
  if (status === 'BROUILLON') return 'info';
  return null;
}

export interface RbcmDocument {
  id: string;
  campaign_id: string;
  kind: string;
  format: string;
  status: string;
  document_seq: number | null;
  filename: string;
  sha256: string | null;
  sha256_available: boolean;
  created_at: string | null;
  created_by_id: string | null;
  created_by_name?: string | null;
  template_id: string | null;
  superseded_by_id: string | null;
  is_current_work: boolean;
  regulatory_validated: boolean;
  work_disclaimer: string | null;
  generation_kind: string;
}

export interface RbcmDocumentHistoryItem {
  id: string;
  status: string;
  document_seq: number | null;
  filename: string;
  created_at: string | null;
  is_current_work: boolean;
}

export interface RbcmDocumentDetail extends RbcmDocument {
  warnings: Record<string, unknown> | null;
  history: RbcmDocumentHistoryItem[];
}

export interface RbcmDocumentList {
  items: RbcmDocument[];
  total: number;
}

export interface RbcmCellResult {
  cell_ref: string;
  calculated_value: string | number | null;
  retained_value: string | number | null;
  value_status: string;
  origin?: string | null;
}

export interface RbcmCellResultList {
  items: RbcmCellResult[];
  total: number;
  run_id: string | null;
  report: Record<string, unknown> | null;
}

export const CELL_STATUS_LABELS: Record<string, string> = {
  AUTOMATIQUE: 'Calculé depuis la BAL DET',
  SAISIE_MANUELLE: 'Saisi',
  A_AJUSTER: 'À ajuster après téléchargement',
  CORRECTION_MANUELLE: 'Corrigé manuellement',
  NON_RENSEIGNE: 'À compléter',
  A_CONFIRMER: 'À confirmer',
};

/** Libellés métier — WORK n’est jamais « validé ». */
export const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  WORK: 'Document de travail',
  SUPERSEDED: 'Ancienne version',
  GENERATED: 'Export technique',
};

const DOCUMENT_GATE_LABELS: Record<string, string> = {
  D01: 'mapping',
  D02: 'écart',
  D06: 'paramètres',
  D09: 'crédits / dépôts',
  D15: 'TOTDEB / TOTCRE',
  D16_D17: 'D16 / D17',
  D22: 'D22',
};

export function documentStatusTone(status: string): 'ok' | 'warn' | 'danger' | 'info' | null {
  if (status === 'WORK') return 'warn';
  if (status === 'SUPERSEDED') return 'info';
  if (status === 'GENERATED') return null;
  return null;
}

export function formatDocumentKind(d: Pick<RbcmDocument, 'kind' | 'format'>): string {
  const fmt = (d.format || '').toLowerCase();
  if (fmt === 'xlsx' || d.kind === 'EXCEL') return 'Excel (xlsx)';
  if (fmt === 'pdf' || d.kind === 'PDF') return 'PDF';
  return d.format || d.kind || '—';
}

export function splitCampaignDocuments(items: RbcmDocument[]): {
  work: RbcmDocument | null;
  superseded: RbcmDocument[];
  generated: RbcmDocument[];
} {
  const work = items.find((d) => d.status === 'WORK' && d.is_current_work) ?? null;
  const superseded = items
    .filter((d) => d.status === 'SUPERSEDED')
    .sort((a, b) => (b.document_seq ?? 0) - (a.document_seq ?? 0));
  const generated = items.filter((d) => d.status === 'GENERATED');
  return { work, superseded, generated };
}

export function documentNeverValidated(d: Pick<RbcmDocument, 'status' | 'regulatory_validated'>): boolean {
  return d.status !== 'VALIDATED' && d.regulatory_validated !== true;
}

export function documentWarningLines(warnings: Record<string, unknown> | null | undefined): string[] {
  if (!warnings) return [];
  const lines: string[] = [];
  if (warnings['regulatory_validation'] === false) {
    lines.push('Ce fichier n’est pas un document réglementaire validé.');
  }
  const gates = warnings['gates_open'];
  if (gates && typeof gates === 'object') {
    const open = Object.entries(gates as Record<string, unknown>)
      .filter(([, v]) => v === true)
      .map(([k]) => DOCUMENT_GATE_LABELS[k] || k);
    if (open.length) {
      lines.push(`Décisions métier encore ouvertes : ${open.join(', ')}.`);
    }
  }
  if (warnings['div_zero_possible'] === true) {
    lines.push(
      'Certaines formules restent incomplètes tant que des cellules sont vides (une cellule vide n’est jamais un zéro).',
    );
  }
  if (warnings['concordance_true_if_empty'] === true) {
    lines.push('Un contrôle de concordance du canevas peut être trompeur si des cellules sont vides.');
  }
  const parseErr = warnings['graph_parse_errors'];
  if (Array.isArray(parseErr) && parseErr.length) {
    lines.push(`${parseErr.length} formule(s) du canevas n’ont pas pu être interprétées.`);
  }
  const pending = warnings['pending_manual'];
  if (Array.isArray(pending) && pending.length) {
    lines.push(`Cellules à compléter manuellement : ${pending.join(', ')}.`);
  }
  const filled = warnings['engine_filled'];
  if (typeof filled === 'number' && filled > 0) {
    lines.push(`${filled} cellule(s) alimentée(s) depuis la BAL DET.`);
  }
  return lines;
}
