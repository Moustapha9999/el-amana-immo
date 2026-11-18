"""Schémas Pydantic — Reporting BCM SM."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignCreate(BaseModel):
    period_year: int = Field(..., ge=2000, le=2100)
    period_month: int = Field(..., ge=1, le=12)
    closing_date: date | None = None
    bank_code: str = Field(default="BEA", max_length=16)
    label: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    reporting_owner_id: UUID | None = None


class CampaignPatch(BaseModel):
    closing_date: date | None = None
    notes: str | None = None


class ReportingOwnerChangeIn(BaseModel):
    reporting_owner_id: UUID
    motif: str = Field(..., min_length=1, max_length=2000)


class ReportingOwnerCandidateOut(BaseModel):
    id: UUID
    full_name: str
    email: str


class ReportingOwnerHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    from_owner_id: UUID | None
    from_owner_name: str | None = None
    to_owner_id: UUID | None
    to_owner_name: str | None = None
    actor_id: UUID | None
    actor_name: str | None = None
    motif: str
    created_at: datetime


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    period_year: int
    period_month: int
    closing_date: date | None
    bank_code: str
    status: str
    campaign_version: int
    reopened_from_id: UUID | None
    preparer_id: UUID | None
    preparer_name: str | None = None
    reporting_owner_id: UUID | None = None
    reporting_owner_name: str | None = None
    reporting_owner_set_at: datetime | None = None
    controller_id: UUID | None
    approver_id: UUID | None
    locked_at: datetime | None
    approved_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CampaignListOut(BaseModel):
    items: list[CampaignOut]
    total: int
    page: int = 1
    page_size: int = 25


class CampaignProgressOut(BaseModel):
    det_validated: bool
    cond_validated: bool
    parameters_filled: int
    parameters_validated: int
    parameters_total: int
    steps_done: int
    steps_total: int
    pct: int
    imports_count: int
    imports_anomaly: int
    last_control_run_id: str | None = None
    last_control_result: str | None = None
    last_control_at: str | None = None
    complements_open: int = 0
    last_calc_run_id: str | None = None
    last_calc_at: str | None = None
    work_document_id: str | None = None
    work_stale: bool = False


class ValidationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    action: str
    from_status: str | None
    to_status: str | None
    comment: str | None
    actor_id: UUID | None
    created_at: datetime


class ParameterValueIn(BaseModel):
    parameter_code: str
    value: Decimal | None = None
    source: str | None = None
    justification: str | None = None
    justificatif_ref: str | None = Field(default=None, max_length=255)
    expected_value_id: UUID | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _no_float(cls, v):  # noqa: ANN001
        if v is None or v == "":
            return None
        if isinstance(v, float):
            raise ValueError("Les montants doivent être saisis en Decimal / chaîne, pas en float")
        return Decimal(str(v))


class ParameterValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    parameter_code: str
    value: Decimal | None
    source: str | None
    justification: str | None
    justificatif_ref: str | None = None
    status: str
    authored_by_id: UUID | None
    validated_by_id: UUID | None = None
    validated_at: datetime | None = None
    supersedes_value_id: UUID | None = None
    created_at: datetime


class ParameterActionIn(BaseModel):
    comment: str | None = None


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    file_type: str
    filename: str
    sha256: str
    size_bytes: int
    status: str
    period_year_detected: int | None
    period_month_detected: int | None
    control_report: dict | None
    row_count: int | None
    sum_debit: Decimal | None
    sum_credit: Decimal | None
    created_at: datetime
    validated_at: datetime | None = None
    uploaded_by_id: UUID | None = None
    validated_by_id: UUID | None = None


class ImportConfirmIn(BaseModel):
    replace_validated: bool = False


class DetLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_no: int
    ncg: str | None
    compte: str | None
    libelle: str | None
    devise: str | None
    debit: Decimal
    credit: Decimal


class DetLineListOut(BaseModel):
    items: list[DetLineOut]
    total: int
    page: int
    page_size: int


class ReconcileIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    ncg: str | None
    severity: str
    code: str
    message: str
    details: dict | None
    resolved: bool
    created_at: datetime
    run_id: UUID | None = None
    category: str | None = None
    item_key: str | None = None
    title: str | None = None
    resolution_state: str | None = None


class MappingRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mapping_version_id: UUID
    cell_ref: str
    match_type: str
    pattern: str
    exclusions: list | None
    amount_basis: str
    signed_balance_mode: str
    sign_multiplier: int
    priority: int
    provenance: str
    lifecycle_status: str
    notes: str | None


class MappingRuleListOut(BaseModel):
    items: list[MappingRuleOut]
    total: int
    page: int = 1
    page_size: int = 50


class WorkflowActionIn(BaseModel):
    comment: str | None = None


class ControlResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    control_code: str
    description: str
    severity: str
    result: str
    justification: str | None
    executed_at: datetime


class AccueilOut(BaseModel):
    module_code: str
    open_campaigns: int
    last_campaign: CampaignOut | None
    pending_decisions: list[str]
    ecart_policy: str
    mapping_policy: str
    dashboard: dict | None = None


class ChartSlice(BaseModel):
    label: str
    value: int


class DashboardOut(BaseModel):
    campaigns_total: int
    campaigns_open: int
    campaigns_pending: int
    campaigns_closed: int
    campaigns_in_progress: int = 0
    campaigns_calculated: int = 0
    campaigns_approved: int = 0
    campaigns_archived: int = 0
    imports_validated: int
    imports_anomaly: int
    parameters_missing: int
    parameters_filled: int = 0
    avg_progress_pct: int
    by_status: list[ChartSlice]
    imports_by_type: list[ChartSlice]
    imports_monthly: list[dict]
    anomalies_by_code: list[ChartSlice]
    mapping_by_lifecycle: list[ChartSlice] = []
    recent_campaigns: list[dict] = []
    recent_imports: list[dict] = []
    status_groups: dict | None = None


class ReconcileIssueListOut(BaseModel):
    items: list[ReconcileIssueOut]
    total: int
    page: int
    page_size: int


class DeleteEligibilityOut(BaseModel):
    can_delete: bool
    can_archive: bool
    reasons: list[str]
    dependencies: dict


class CondLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ncg: str
    libelle: str | None
    tot_debit: Decimal
    tot_credit: Decimal
    source: str
    var: Decimal | None = None


class CondLineListOut(BaseModel):
    items: list[CondLineOut]
    total: int
    page: int
    page_size: int


class ImportListOut(BaseModel):
    items: list[ImportOut]
    total: int
    page: int
    page_size: int


class DocumentOut(BaseModel):
    """Métadonnées publiques d'un livrable — jamais de stored_path."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    kind: str
    format: str
    status: str
    document_seq: int | None = None
    filename: str
    sha256: str | None = None
    sha256_available: bool = False
    created_at: datetime | None = None
    created_by_id: UUID | None = None
    created_by_name: str | None = None
    template_id: UUID | None = None
    superseded_by_id: UUID | None = None
    is_current_work: bool = False
    regulatory_validated: bool = False
    work_disclaimer: str | None = None
    generation_kind: str


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int


class DocumentHistoryItem(BaseModel):
    id: UUID
    status: str
    document_seq: int | None = None
    filename: str
    created_at: datetime | None = None
    is_current_work: bool = False


class DocumentDetailOut(DocumentOut):
    warnings: dict | None = None
    history: list[DocumentHistoryItem] = []


class CellResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cell_ref: str
    calculated_value: Decimal | None
    retained_value: Decimal | None
    value_status: str
    origin: str | None = None


class CellResultListOut(BaseModel):
    items: list[CellResultOut]
    total: int
    run_id: UUID | None = None
    report: dict | None = None


class DocumentDecisionIn(BaseModel):
    document_cell_key: str = Field(..., min_length=3, max_length=32)
    decision_type: str = Field(default="VALEUR_DECIDEE")
    decided_value: Decimal | None = None
    reason: str = Field(..., min_length=1, max_length=4000)
    justificatif_ref: str | None = Field(default=None, max_length=255)

    @field_validator("decision_type")
    @classmethod
    def _type_ok(cls, v: str) -> str:
        allowed = {"ZERO_CONFIRME", "ZERO_MANUEL", "VALEUR_DECIDEE", "RETRAIT"}
        if v not in allowed:
            raise ValueError("type de décision inconnu")
        return v
