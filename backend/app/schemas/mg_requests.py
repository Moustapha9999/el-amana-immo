"""Schémas Demandes employés / regroupements MG."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.nombres import Qty, QtyGe0, QtyPos


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None = None
    icon: str | None = None
    form_schema: dict | None = None
    requires_stock_check: bool
    requires_purchase: bool
    can_create_purchase: bool = True
    requires_attachment: bool = False
    owner_espace_code: str = "moyens-generaux"
    target_espace_code: str = "moyens-generaux"
    source_espaces: list | None = None
    active: bool
    sort_order: int


class CategoryIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    icon: str | None = None
    form_schema: dict | None = None
    requires_stock_check: bool = False
    requires_purchase: bool = True
    can_create_purchase: bool = True
    requires_attachment: bool = False
    owner_espace_code: str = "moyens-generaux"
    target_espace_code: str = "moyens-generaux"
    source_espaces: list | None = None
    active: bool = True
    sort_order: int = 0


class RequestItemIn(BaseModel):
    article_id: UUID | None = None
    description: str = Field(min_length=1, max_length=255)
    quantity: QtyPos
    unit: str = "U"
    estimated_unit_price: Decimal = Field(default=Decimal("0"), ge=0)


class RequestItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    article_id: UUID | None
    description: str
    quantity: Qty
    quantity_granted: Qty | None = None
    unit: str
    estimated_unit_price: Decimal
    estimated_total: Decimal
    stock_checked: bool
    stock_available: bool | None
    stock_actuel: Qty | None
    status: str


class RequestCreate(BaseModel):
    category_id: UUID
    agency_id: UUID | None = None
    department_id: UUID | None = None
    title: str | None = None
    description: str | None = None
    priority: str = "NORMALE"
    period: str | None = None
    items: list[RequestItemIn] = Field(default_factory=list)


class RequestUpdate(BaseModel):
    category_id: UUID | None = None
    agency_id: UUID | None = None
    department_id: UUID | None = None
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    period: str | None = None
    items: list[RequestItemIn] | None = None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    approver_id: UUID
    action: str
    status: str
    comment: str | None
    acted_at: datetime


class CommentIn(BaseModel):
    comment: str | None = None


class GrantedLineIn(BaseModel):
    item_id: UUID
    quantity_granted: QtyGe0 | None = None


class GrantedIn(BaseModel):
    lines: list[GrantedLineIn] = Field(default_factory=list)


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_id: UUID
    author_name: str | None = None
    body: str
    visibility: str
    created_at: datetime


class AssignIn(BaseModel):
    assigned_to_id: UUID | None = None


class RecategorizeIn(BaseModel):
    category_id: UUID


class StockHintOut(BaseModel):
    article_id: UUID
    designation: str
    stock_actuel: Qty
    stock_min: Qty | None
    quantity: Qty
    after: Qty
    available: bool


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_number: str
    requester_id: UUID
    requester_name: str | None = None
    department_id: UUID | None
    department_label: str | None = None
    agency_id: UUID
    agency_label: str | None = None
    category_id: UUID
    category_code: str | None = None
    category_name: str | None = None
    source_espace_code: str | None = None
    source_espace_label: str | None = None
    target_espace_code: str | None = None
    target_espace_label: str | None = None
    assigned_to_id: UUID | None = None
    assigned_to_name: str | None = None
    title: str
    description: str | None
    priority: str
    status: str
    period: str | None
    submitted_at: datetime | None
    received_at: datetime | None
    validated_at: datetime | None
    rejected_at: datetime | None
    closed_at: datetime | None
    rejection_reason: str | None
    validation_comment: str | None
    complement_comment: str | None
    achat_demande_id: UUID | None
    batch_id: UUID | None
    batch_number: str | None = None
    created_at: datetime
    items: list[RequestItemOut] = []
    approvals: list[ApprovalOut] = []
    comments: list[CommentOut] = []
    stock_hints: list[StockHintOut] = []


class RequestListOut(BaseModel):
    items: list[RequestOut]
    total: int
    page: int
    size: int


class DashboardOut(BaseModel):
    a_traiter: int
    a_completer: int
    validees: int
    refusees: int
    urgentes: int
    a_regrouper: int
    en_achat: int
    servies: int
    aujourd_hui: int
    par_categorie: list[dict]
    par_agence: list[dict]
    par_source: list[dict] = []


class InsightOut(BaseModel):
    tone: str
    title: str
    text: str
    statut: str | None = None


class MineDashboardOut(BaseModel):
    total: int
    brouillons: int
    a_completer: int
    en_cours: int
    soumises: int
    recues: int
    validees: int
    refusees: int
    servies: int
    annulees: int
    urgentes: int
    notifications_non_lues: int
    par_categorie: list[dict]
    par_statut: list[dict]
    recentes: list[RequestOut] = []
    insights: list[InsightOut] = []


class MineDocumentOut(BaseModel):
    id: UUID
    filename: str
    title: str | None = None
    description: str | None = None
    doc_type: str | None = None
    mime_type: str | None = None
    size_bytes: int = 0
    ocr_status: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    request_id: UUID
    request_number: str
    request_title: str
    request_status: str


class MineDocumentListOut(BaseModel):
    items: list[MineDocumentOut]
    total: int


class HistoryEventOut(BaseModel):
    id: str
    request_id: UUID
    request_number: str
    title: str
    action: str
    action_label: str
    status: str
    comment: str | None = None
    actor_name: str | None = None
    acted_at: datetime


class HistoryListOut(BaseModel):
    items: list[HistoryEventOut]
    total: int


class BatchCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    category_id: UUID | None = None
    department_id: UUID | None = None
    agency_id: UUID | None = None
    period: str | None = None
    priority: str = "NORMALE"
    request_ids: list[UUID] = Field(default_factory=list)


class BatchUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category_id: UUID | None = None
    department_id: UUID | None = None
    agency_id: UUID | None = None
    period: str | None = None
    priority: str | None = None


class BatchItemsIn(BaseModel):
    request_ids: list[UUID] = Field(min_length=1)


class ConsolidatedLineOut(BaseModel):
    key: str
    article_id: UUID | None
    description: str
    quantity: Qty
    estimated_total: Decimal
    request_count: int


class BatchItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    request_item_id: UUID
    article_id: UUID | None
    description: str
    quantity: Qty
    supplier_id: UUID | None
    estimated_unit_price: Decimal
    estimated_total: Decimal
    status: str


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_number: str
    category_id: UUID | None
    category_name: str | None = None
    department_id: UUID | None
    agency_id: UUID | None
    period: str | None
    title: str
    description: str | None
    priority: str
    status: str
    created_by: UUID
    validated_by: UUID | None
    achat_demande_id: UUID | None
    created_at: datetime
    request_count: int = 0
    item_count: int = 0
    employee_count: int = 0
    estimated_total: Decimal = Decimal("0")
    items: list[BatchItemOut] = []
    consolidated: list[ConsolidatedLineOut] = []


class BatchListOut(BaseModel):
    items: list[BatchOut]
    total: int
    page: int
    size: int


class RefOut(BaseModel):
    id: UUID
    label: str
    extra: str | None = None
