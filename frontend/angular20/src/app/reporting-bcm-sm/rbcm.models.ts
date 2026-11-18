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
  last_calc_run_id?: string | null;
  last_calc_at?: string | null;
  work_document_id?: string | null;
  work_stale?: boolean;
}

export interface RbcmReviewCheck {
  code: string;
  title: string;
  state: 'ok' | 'fail' | 'missing' | 'wait' | 'stale' | string;
  detail: string;
  action?: string | null;
}

export interface RbcmReviewFinding {
  code: string;
  title: string;
  category: 'structure' | 'donnees' | 'anomalie' | string;
  severity: 'blocking' | 'warning' | 'info' | string;
  status: 'ok' | 'fail' | 'pending' | string;
  message: string;
  sheet?: string | null;
  cell?: string | null;
  action?: string | null;
}

export interface RbcmWorkflowBlocker {
  code: string;
  title: string;
  message: string;
}

export interface RbcmWorkflowAction {
  allowed: boolean;
  blockers: RbcmWorkflowBlocker[];
  reason_required?: boolean;
}

export interface RbcmWorkflow {
  campaign_id: string;
  status: string;
  gates: Record<string, boolean>;
  open_gates: { code: string; label: string }[];
  can_finalize_regulatory: boolean;
  work_stale: boolean;
  params_stale: boolean;
  submitted: { at: string | null; actor_id: string | null; work_id: string | null };
  control_visa: { at: string | null; actor_id: string | null };
  approved: { at: string | null; actor_id: string | null; work_id: string | null };
  rejected: { at: string | null };
  sod: {
    preparer_id: string | null;
    reporting_owner_id: string | null;
    current_user_id: string | null;
    same_as_preparer: boolean;
    same_as_owner: boolean;
  };
  submit: RbcmWorkflowAction;
  control_ok: RbcmWorkflowAction;
  approve: RbcmWorkflowAction;
  reject: RbcmWorkflowAction;
  work_download: {
    allowed: boolean;
    deliverable_id: string | null;
    filename: string;
    disclaimer: string;
  };
  final_download: {
    allowed: boolean;
    blockers: RbcmWorkflowBlocker[];
    deliverable_id: string | null;
    filename: string;
  };
  editable: boolean;
}

export const WORKFLOW_ACTION_LABELS: Record<string, string> = {
  SUBMIT_CONTROL: 'Soumission au contrôle',
  CONTROL_OK: 'Visa du contrôleur',
  CONTROL_REJECT: 'Retour en correction',
  APPROVE: 'Approbation',
  REJECT_APPROVAL: 'Refus d’approbation',
  REOPEN: 'Réouverture',
  CLOSE: 'Clôture',
  OWNER_ASSIGN: 'Changement de responsable',
};

export interface RbcmReview {
  campaign_id: string;
  preparation: {
    verdict: 'ready' | 'complements' | 'decision' | 'blocked' | string;
    verdict_label: string;
    can_verify: boolean;
    checks: RbcmReviewCheck[];
    missing_params: { code: string; label: string; cell_hint?: string | null; nature?: string }[];
    pending_manual: string[];
    pending_adjust: string[];
    decisions: { code: string; label: string; open: boolean; needed_for: string }[];
    work_stale: boolean;
    params_stale: boolean;
  };
  verification: {
    verdict: 'conforme' | 'a_corriger' | 'a_completer' | 'decision' | string;
    verdict_label: string;
    can_finalize_regulatory: boolean;
    stale: boolean;
    work_id: string | null;
    work_filename: string | null;
    calc_run_id: string | null;
    sheets: string[];
    missing_sheets: string[];
    findings: RbcmReviewFinding[];
    counts: { blocking: number; warning: number; info: number; pending: number };
  };
}

export const PREP_VERDICT_TONE: Record<string, 'ok' | 'warn' | 'danger' | 'info' | null> = {
  ready: 'ok',
  complements: 'warn',
  decision: 'warn',
  blocked: 'danger',
};

export const DOC_VERDICT_TONE: Record<string, 'ok' | 'warn' | 'danger' | 'info' | null> = {
  conforme: 'ok',
  a_completer: 'warn',
  decision: 'warn',
  a_corriger: 'danger',
};

export const CHECK_STATE_TONE: Record<string, 'ok' | 'warn' | 'danger' | 'info' | null> = {
  ok: 'ok',
  fail: 'danger',
  missing: 'warn',
  wait: 'warn',
  stale: 'warn',
};

export const FINDING_CATEGORY_LABELS: Record<string, string> = {
  structure: 'Structure du document',
  donnees: 'Données comptables',
  anomalie: 'Anomalies et avertissements',
};

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

export interface RbcmNcgStructureCell {
  cell_ref: string;
  basis: string;
  sign: number;
}

export interface RbcmNcgStructureItem {
  ncg: string;
  libelle: string | null;
  tot_debit: string | null;
  tot_credit: string | null;
  status: string;
  present_zero: boolean;
  reapparu: boolean;
  covered_by_class: boolean;
  cells: RbcmNcgStructureCell[];
  first_seen_period: string | null;
  last_seen_period: string | null;
  immediate_previous_period: string | null;
}

export interface RbcmNcgStructureAbsent {
  ncg: string;
  status: string;
  cells: RbcmNcgStructureCell[];
  covered_by_class: boolean;
  first_seen_period: string | null;
  last_seen_period: string | null;
}

export interface RbcmNcgStructure {
  has_validated_det: boolean;
  period_year: number | null;
  period_month: number | null;
  campaign_id: string | null;
  import_id: string | null;
  ncg_count: number;
  history_period_count: number;
  available_periods: { period_year: number; period_month: number; label: string }[];
  counts: Record<string, number>;
  items: RbcmNcgStructureItem[];
  absents: RbcmNcgStructureAbsent[];
  orientation_auto: boolean;
  note: string | null;
}

export const NCG_STRUCTURE_STATUS_LABELS: Record<string, string> = {
  nouveau: 'Nouveau',
  connu_non_oriente: 'Connu non orienté',
  deja_mappe: 'Déjà mappé',
  absent_mappe: 'Absent (mappé)',
  absent_historique: 'Absent (historique)',
};

export interface RbcmNcgOrientation {
  id: string;
  ncg: string;
  ncg_libelle: string | null;
  sheet: string;
  cell_ref: string | null;
  currency_scope: string;
  residence_scope: string;
  operation: string | null;
  status: string;
  notes: string | null;
  prepared_by_id: string | null;
  prepared_at: string | null;
  submitted_by_id: string | null;
  submitted_at: string | null;
  validated_by_id: string | null;
  validated_at: string | null;
  rejected_by_id: string | null;
  rejected_at: string | null;
  deactivated_by_id: string | null;
  deactivated_at: string | null;
  decision_comment: string | null;
  supersedes_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RbcmNcgDetail {
  ncg: string;
  libelle: string | null;
  detection: Record<string, unknown> | null;
  structure_status: string | null;
  balances: {
    period_year: number;
    period_month: number;
    label: string;
    present: boolean;
    tot_debit: string | null;
    tot_credit: string | null;
    libelle: string | null;
  }[];
  catalog_mappings: { cell_ref: string; basis: string; sign: number; currency: string; source: string }[];
  orientations: RbcmNcgOrientation[];
  target_cells: { cell_ref: string; sheet: string; origin: string; notes: string | null; existing_ncgs: string[] }[];
  operations: string[];
  currency_scopes: string[];
  residence_scopes: string[];
  sheets: string[];
  statuses: string[];
  orientation_auto: boolean;
  note: string | null;
}

export const NCG_ORIENTATION_STATUS_LABELS: Record<string, string> = {
  A_ORIENTER: 'À orienter',
  EN_ATTENTE_VALIDATION: 'En attente de validation',
  VALIDE_ACTIF: 'Validé et actif',
  REJETE: 'Rejeté',
  DESACTIVE: 'Désactivé',
};

export const NCG_ORIENTATION_OPERATION_LABELS: Record<string, string> = {
  ADD_DEBIT: 'Ajouter le solde débiteur (DEB)',
  ADD_CREDIT: 'Ajouter le solde créditeur (CRE)',
  SUB_DEBIT: 'Soustraire le solde débiteur (DEB)',
  SUB_CREDIT: 'Soustraire le solde créditeur (CRE)',
};

export interface RbcmNcgReviewCompte {
  compte: string | null;
  devise: string | null;
  debit: string;
  credit: string;
  libelle: string | null;
}

export interface RbcmNcgReviewRow {
  ncg: string;
  libelle: string | null;
  structure_status: string;
  tot_debit: string | null;
  tot_credit: string | null;
  present_zero: boolean;
  reapparu: boolean;
  covered_by_class: boolean;
  first_seen_period: string | null;
  last_seen_period: string | null;
  immediate_previous_period: string | null;
  balances: RbcmNcgDetail['balances'];
  devises: string[];
  comptes: RbcmNcgReviewCompte[];
  line_count: number;
  catalog_mappings: RbcmNcgDetail['catalog_mappings'];
  latest_orientation: RbcmNcgOrientation | null;
  orientations: RbcmNcgOrientation[];
  proposed_cell_ref: string | null;
  proposed_operation: string | null;
  proposed_status: string | null;
  needs_decision: boolean;
  decision_deferred: boolean;
}

export interface RbcmNcgReviewBoard {
  campaign_id: string;
  period_year: number;
  period_month: number;
  has_validated_det: boolean;
  import_id: string | null;
  structure_counts: Record<string, number>;
  orientation_counts: Record<string, number>;
  ncg_a_reviser: RbcmNcgReviewRow[];
  orientations: RbcmNcgOrientation[];
  target_cells: RbcmNcgDetail['target_cells'];
  operations: string[];
  currency_scopes: string[];
  residence_scopes: string[];
  sheets: string[];
  statuses: string[];
  orientation_auto: boolean;
  note: string | null;
}

export interface RbcmParamCatalog {
  code: string;
  label: string;
  calculable: boolean;
  nature?: 'manuel' | 'calculable' | 'ajustement' | string;
  cell_hint?: string | null;
  value: string | null;
  value_id: string | null;
  source: string | null;
  justification: string | null;
  justificatif_ref?: string | null;
  status: string;
  filled?: boolean;
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
  { n: 1, key: 'infos', label: 'Situation mensuelle' },
  { n: 2, key: 'bal', label: 'Import BAL DET' },
  { n: 3, key: 'controles', label: 'Contrôles' },
  { n: 4, key: 'completer', label: 'Cellules manuelles' },
  { n: 5, key: 'preparer', label: 'Canevas SM' },
] as const;

/** Étape courante du parcours de travail (1–5). Un 6 signifie canevas généré (toutes les étapes terminées). Visa / approbation hors parcours. */
export function currentGuidedStep(_c: RbcmCampaign, p?: RbcmProgress | null): number {
  if (!p?.det_validated) return 2;
  if (!p.last_control_run_id) return 3;
  const missing = (p.parameters_total ?? 8) - (p.parameters_filled ?? 0);
  if (missing > 0 || !p.last_calc_run_id) return 4;
  if (!p.work_document_id || p.work_stale) return 5;
  return 6;
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
  AUTOMATIQUE: 'Calculé',
  SAISIE_MANUELLE: 'Saisi',
  A_AJUSTER: 'À ajuster',
  CORRECTION_MANUELLE: 'Corrigé manuellement',
  NON_RENSEIGNE: 'À compléter',
  A_CONFIRMER: 'À confirmer',
};

export const PARAM_STATUS_LABELS: Record<string, string> = {
  EN_ATTENTE: 'À compléter',
  SAISI: 'Saisi',
  CALCULE: 'Calculé',
  VALIDE: 'Saisi',
  REJETE: 'À compléter',
};

export const PARAM_NATURE_LABELS: Record<string, string> = {
  manuel: 'Saisie manuelle',
  calculable: 'Proposition BAL DET',
  ajustement: 'Ajustement',
};

export const CELL_ORIGIN_LABELS: Record<string, string> = {
  AUTO: 'Calculé',
  COPY: 'Calculé',
  PCT: 'Calculé',
  REMAINDER: 'Calculé',
  MANUAL: 'Saisie manuelle',
  AUTO_THEN_ADJUST: 'À ajuster',
};

export function paramIsFilled(p: Pick<RbcmParamCatalog, 'status' | 'filled'>): boolean {
  if (typeof p.filled === 'boolean') return p.filled;
  return p.status === 'SAISI' || p.status === 'CALCULE' || p.status === 'VALIDE';
}

export function paramStatusTone(status: string): 'ok' | 'warn' | 'info' | null {
  if (status === 'SAISI' || status === 'VALIDE') return 'ok';
  if (status === 'CALCULE') return 'info';
  return 'warn';
}

export function cellKind(
  origin: string | null | undefined,
): 'calculated' | 'manual' | 'adjust' | 'other' {
  if (origin === 'AUTO_THEN_ADJUST') return 'adjust';
  if (origin === 'MANUAL') return 'manual';
  if (origin === 'AUTO' || origin === 'COPY' || origin === 'PCT' || origin === 'REMAINDER') {
    return 'calculated';
  }
  return 'other';
}

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
