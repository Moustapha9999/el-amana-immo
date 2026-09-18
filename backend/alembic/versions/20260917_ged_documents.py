"""Table CORE GED (réservée, aucune donnée métier).

Revision ID: 20260917_ged_documents
Revises: 20260917_bea_comments
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_ged_documents"
down_revision: Union[str, None] = "20260917_bea_comments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ged_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("espace_code", sa.String(80), nullable=False),
        sa.Column("module_code", sa.String(80), nullable=False),
        sa.Column("entity", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
    )
    op.create_index("ix_ged_documents_espace_code", "ged_documents", ["espace_code"])
    op.create_index("ix_ged_documents_module_code", "ged_documents", ["module_code"])
    op.create_index("ix_ged_documents_entity", "ged_documents", ["entity"])
    op.create_index("ix_ged_documents_entity_id", "ged_documents", ["entity_id"])
    op.create_index("ix_ged_documents_uploaded_by_id", "ged_documents", ["uploaded_by_id"])
    op.execute(
        "COMMENT ON TABLE ged_documents IS "
        "'GED CORE — documents transverses. Non branchée ; pieces_jointes / archive_* restent immo.'"
    )


def downgrade() -> None:
    op.drop_index("ix_ged_documents_uploaded_by_id", table_name="ged_documents")
    op.drop_index("ix_ged_documents_entity_id", table_name="ged_documents")
    op.drop_index("ix_ged_documents_entity", table_name="ged_documents")
    op.drop_index("ix_ged_documents_module_code", table_name="ged_documents")
    op.drop_index("ix_ged_documents_espace_code", table_name="ged_documents")
    op.drop_table("ged_documents")
