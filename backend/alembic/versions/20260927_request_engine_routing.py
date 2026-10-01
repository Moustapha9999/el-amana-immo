"""Routage inter-départements du moteur de demandes.

Revision ID: 20260927_request_engine
Revises: 20260927_mg_employee_requests
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260927_request_engine"
down_revision: Union[str, None] = "20260927_mg_employee_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mg_request_categories",
        sa.Column("can_create_purchase", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "mg_request_categories",
        sa.Column("requires_attachment", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "mg_request_categories",
        sa.Column("owner_espace_code", sa.String(80), server_default="moyens-generaux", nullable=False),
    )
    op.add_column(
        "mg_request_categories",
        sa.Column("target_espace_code", sa.String(80), server_default="moyens-generaux", nullable=False),
    )
    op.add_column(
        "mg_request_categories",
        sa.Column("source_espaces", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute("UPDATE mg_request_categories SET source_espaces = '[\"*\"]'::jsonb WHERE source_espaces IS NULL")
    op.drop_index("ix_mg_request_categories_code", table_name="mg_request_categories")
    op.create_index("ix_mg_request_categories_code", "mg_request_categories", ["code"])
    op.create_index("ix_mg_request_categories_owner", "mg_request_categories", ["owner_espace_code"])
    op.create_index("ix_mg_request_categories_target", "mg_request_categories", ["target_espace_code"])
    op.create_unique_constraint(
        "uq_mg_request_categories_owner_code",
        "mg_request_categories",
        ["owner_espace_code", "code"],
    )

    op.add_column(
        "mg_employee_requests",
        sa.Column("source_espace_code", sa.String(80), server_default="employe", nullable=False),
    )
    op.add_column(
        "mg_employee_requests",
        sa.Column("target_espace_code", sa.String(80), server_default="moyens-generaux", nullable=False),
    )
    op.add_column(
        "mg_employee_requests",
        sa.Column("assigned_to_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_mg_employee_requests_assigned",
        "mg_employee_requests",
        "users",
        ["assigned_to_id"],
        ["id"],
    )
    op.create_index("ix_mg_employee_requests_source", "mg_employee_requests", ["source_espace_code"])
    op.create_index("ix_mg_employee_requests_target", "mg_employee_requests", ["target_espace_code"])
    op.create_index("ix_mg_employee_requests_assigned", "mg_employee_requests", ["assigned_to_id"])

    op.create_table(
        "mg_request_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_employee_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="SHARED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mg_request_comments_request", "mg_request_comments", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_mg_request_comments_request", table_name="mg_request_comments")
    op.drop_table("mg_request_comments")
    op.drop_index("ix_mg_employee_requests_assigned", table_name="mg_employee_requests")
    op.drop_index("ix_mg_employee_requests_target", table_name="mg_employee_requests")
    op.drop_index("ix_mg_employee_requests_source", table_name="mg_employee_requests")
    op.drop_constraint("fk_mg_employee_requests_assigned", "mg_employee_requests", type_="foreignkey")
    op.drop_column("mg_employee_requests", "assigned_to_id")
    op.drop_column("mg_employee_requests", "target_espace_code")
    op.drop_column("mg_employee_requests", "source_espace_code")
    op.drop_constraint("uq_mg_request_categories_owner_code", "mg_request_categories", type_="unique")
    op.drop_index("ix_mg_request_categories_target", table_name="mg_request_categories")
    op.drop_index("ix_mg_request_categories_owner", table_name="mg_request_categories")
    op.drop_index("ix_mg_request_categories_code", table_name="mg_request_categories")
    op.create_index("ix_mg_request_categories_code", "mg_request_categories", ["code"], unique=True)
    op.drop_column("mg_request_categories", "source_espaces")
    op.drop_column("mg_request_categories", "target_espace_code")
    op.drop_column("mg_request_categories", "owner_espace_code")
    op.drop_column("mg_request_categories", "requires_attachment")
    op.drop_column("mg_request_categories", "can_create_purchase")
