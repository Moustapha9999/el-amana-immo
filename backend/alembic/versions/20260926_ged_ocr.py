"""GED — OCR + security_level (Document Service).

Revision ID: 20260926_ged_ocr
Revises: 20260926_ged_archives_meta
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260926_ged_ocr"
down_revision: Union[str, None] = "20260926_ged_archives_meta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ged_documents",
        sa.Column(
            "ocr_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("ged_documents", sa.Column("ocr_text", sa.Text(), nullable=True))
    op.add_column(
        "ged_documents",
        sa.Column("ocr_text_search", postgresql.TSVECTOR(), nullable=True),
    )
    op.add_column("ged_documents", sa.Column("ocr_error", sa.Text(), nullable=True))
    op.add_column(
        "ged_documents",
        sa.Column("ocr_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ged_documents",
        sa.Column(
            "security_level",
            sa.String(40),
            nullable=False,
            server_default="internal",
        ),
    )

    op.create_index("ix_ged_documents_ocr_status", "ged_documents", ["ocr_status"])
    op.create_index(
        "ix_ged_documents_security_level", "ged_documents", ["security_level"]
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ged_documents_ocr_text_search "
        "ON ged_documents USING gin (ocr_text_search)"
    )

    # Backfill : documents existants en attente OCR (pas de relance auto massique).
    op.execute(
        "UPDATE ged_documents SET ocr_status = 'pending' "
        "WHERE ocr_status IS NULL OR ocr_status = ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ged_documents_ocr_text_search")
    op.drop_index("ix_ged_documents_security_level", table_name="ged_documents")
    op.drop_index("ix_ged_documents_ocr_status", table_name="ged_documents")
    op.drop_column("ged_documents", "security_level")
    op.drop_column("ged_documents", "ocr_attempts")
    op.drop_column("ged_documents", "ocr_error")
    op.drop_column("ged_documents", "ocr_text_search")
    op.drop_column("ged_documents", "ocr_text")
    op.drop_column("ged_documents", "ocr_status")
