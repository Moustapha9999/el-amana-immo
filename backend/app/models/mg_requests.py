"""Demandes internes employés → Moyens Généraux (amont des Achats)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MgRequestCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_request_categories"
    __table_args__ = (
        UniqueConstraint("owner_espace_code", "code", name="uq_mg_request_categories_owner_code"),
    )

    code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    form_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    requires_stock_check: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_purchase: Mapped[bool] = mapped_column(Boolean, default=True)
    can_create_purchase: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_attachment: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_espace_code: Mapped[str] = mapped_column(String(80), default="moyens-generaux", index=True)
    target_espace_code: Mapped[str] = mapped_column(String(80), default="moyens-generaux", index=True)
    source_espaces: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class MgEmployeeRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_employee_requests"
    __table_args__ = (UniqueConstraint("request_number", name="uq_mg_employee_requests_number"),)

    request_number: Mapped[str] = mapped_column(String(40), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id"), nullable=True
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_request_categories.id"), index=True
    )
    source_espace_code: Mapped[str] = mapped_column(String(80), default="comptabilite", index=True)
    target_espace_code: Mapped[str] = mapped_column(String(80), default="moyens-generaux", index=True)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="NORMALE", index=True)
    status: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    complement_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    achat_demande_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_demandes.id"), nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_procurement_batches.id"), nullable=True
    )

    category: Mapped[MgRequestCategory] = relationship()
    items: Mapped[list[MgEmployeeRequestItem]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    approvals: Mapped[list[MgRequestApproval]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    comments: Mapped[list[MgRequestComment]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class MgEmployeeRequestItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_employee_request_items"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mg_employee_requests.id", ondelete="CASCADE"),
        index=True,
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("1"))
    quantity_granted: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="U")
    estimated_unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    estimated_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    stock_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    stock_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    stock_actuel: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="OUVERT", index=True)

    request: Mapped[MgEmployeeRequest] = relationship(back_populates="items")


class MgRequestComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_request_comments"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mg_employee_requests.id", ondelete="CASCADE"),
        index=True,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(20), default="SHARED")

    request: Mapped[MgEmployeeRequest] = relationship(back_populates="comments")


class MgRequestApproval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_request_approvals"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mg_employee_requests.id", ondelete="CASCADE"),
        index=True,
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    request: Mapped[MgEmployeeRequest] = relationship(back_populates="approvals")


class MgProcurementBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_procurement_batches"
    __table_args__ = (UniqueConstraint("batch_number", name="uq_mg_procurement_batches_number"),)

    batch_number: Mapped[str] = mapped_column(String(40), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_request_categories.id"), nullable=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id"), nullable=True
    )
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True
    )
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="NORMALE")
    status: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    validated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    achat_demande_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_demandes.id"), nullable=True
    )

    items: Mapped[list[MgProcurementBatchItem]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class MgProcurementBatchItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_procurement_batch_items"
    __table_args__ = (
        UniqueConstraint("request_item_id", name="uq_mg_procurement_batch_items_request_item"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mg_procurement_batches.id", ondelete="CASCADE"),
        index=True,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_employee_requests.id"), index=True
    )
    request_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_employee_request_items.id"), index=True
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("1"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), nullable=True
    )
    estimated_unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    estimated_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(30), default="INCLUS")

    batch: Mapped[MgProcurementBatch] = relationship(back_populates="items")
