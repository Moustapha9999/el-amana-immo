"""Demandes employés MG + regroupements + provenance DA.

Revision ID: 20260927_mg_employee_requests
Revises: 20260926_ged_version_comment
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260927_mg_employee_requests"
down_revision: Union[str, None] = "20260926_ged_version_comment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mg_request_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(40), nullable=True),
        sa.Column("form_schema", postgresql.JSONB(), nullable=True),
        sa.Column("requires_stock_check", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_purchase", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_request_categories_code", "mg_request_categories", ["code"], unique=True)

    op.create_table(
        "mg_procurement_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_number", sa.String(40), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_request_categories.id"), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departements.id"), nullable=True),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=True),
        sa.Column("period", sa.String(40), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(20), nullable=False, server_default="NORMALE"),
        sa.Column("status", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("validated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("achat_demande_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_achat_demandes.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_procurement_batches_number", "mg_procurement_batches", ["batch_number"], unique=True)
    op.create_index("ix_mg_procurement_batches_status", "mg_procurement_batches", ["status"])

    op.create_table(
        "mg_employee_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_number", sa.String(40), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departements.id"), nullable=True),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_request_categories.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(20), nullable=False, server_default="NORMALE"),
        sa.Column("status", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column("period", sa.String(40), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejected_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("validation_comment", sa.Text(), nullable=True),
        sa.Column("complement_comment", sa.Text(), nullable=True),
        sa.Column("achat_demande_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_achat_demandes.id"), nullable=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_procurement_batches.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_employee_requests_number", "mg_employee_requests", ["request_number"], unique=True)
    op.create_index("ix_mg_employee_requests_status", "mg_employee_requests", ["status"])
    op.create_index("ix_mg_employee_requests_requester", "mg_employee_requests", ["requester_id"])
    op.create_index("ix_mg_employee_requests_agency", "mg_employee_requests", ["agency_id"])

    op.create_table(
        "mg_employee_request_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_employee_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_articles.id"), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False, server_default="1"),
        sa.Column("unit", sa.String(20), nullable=False, server_default="U"),
        sa.Column("estimated_unit_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("estimated_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("stock_checked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stock_available", sa.Boolean(), nullable=True),
        sa.Column("stock_actuel", sa.Numeric(18, 3), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="OUVERT"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_employee_request_items_request", "mg_employee_request_items", ["request_id"])

    op.create_table(
        "mg_request_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_employee_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_request_approvals_request", "mg_request_approvals", ["request_id"])

    op.create_table(
        "mg_procurement_batch_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_procurement_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_employee_requests.id"), nullable=False),
        sa.Column("request_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_employee_request_items.id"), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_articles.id"), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False, server_default="1"),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fournisseurs.id"), nullable=True),
        sa.Column("estimated_unit_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("estimated_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="INCLUS"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("request_item_id", name="uq_mg_procurement_batch_items_request_item"),
    )
    op.create_index("ix_mg_procurement_batch_items_batch", "mg_procurement_batch_items", ["batch_id"])

    op.add_column("mg_achat_demandes", sa.Column("source_type", sa.String(40), nullable=True))
    op.add_column("mg_achat_demandes", sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_mg_achat_demandes_source", "mg_achat_demandes", ["source_type", "source_id"])


def downgrade() -> None:
    op.drop_index("ix_mg_achat_demandes_source", table_name="mg_achat_demandes")
    op.drop_column("mg_achat_demandes", "source_id")
    op.drop_column("mg_achat_demandes", "source_type")
    op.drop_table("mg_procurement_batch_items")
    op.drop_table("mg_request_approvals")
    op.drop_table("mg_employee_request_items")
    op.drop_table("mg_employee_requests")
    op.drop_table("mg_procurement_batches")
    op.drop_table("mg_request_categories")
