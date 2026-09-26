"""GED — metadonnees Archives MG.

Revision ID: 20260926_ged_archives_meta
Revises: 20260925_mg_contrats_v2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260926_ged_archives_meta"
down_revision: Union[str, None] = "20260925_mg_contrats_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ged_documents", sa.Column("title", sa.String(255), nullable=True))
    op.add_column("ged_documents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("ged_documents", sa.Column("doc_type", sa.String(80), nullable=True))
    op.add_column("ged_documents", sa.Column("reference", sa.String(120), nullable=True))
    op.add_column("ged_documents", sa.Column("date_document", sa.Date(), nullable=True))
    op.add_column(
        "ged_documents",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ged_documents",
        sa.Column("agence_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ged_documents",
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ged_documents",
        sa.Column("fournisseur_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ged_documents",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "ged_documents",
        sa.Column("parent_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ged_documents",
        sa.Column("deleted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ged_documents",
        sa.Column("delete_reason", sa.String(500), nullable=True),
    )
    op.create_foreign_key(
        "ged_documents_agence_id_fkey", "ged_documents", "agences", ["agence_id"], ["id"]
    )
    op.create_foreign_key(
        "ged_documents_department_id_fkey",
        "ged_documents",
        "departements",
        ["department_id"],
        ["id"],
    )
    op.create_foreign_key(
        "ged_documents_fournisseur_id_fkey",
        "ged_documents",
        "fournisseurs",
        ["fournisseur_id"],
        ["id"],
    )
    op.create_foreign_key(
        "ged_documents_parent_document_id_fkey",
        "ged_documents",
        "ged_documents",
        ["parent_document_id"],
        ["id"],
    )
    op.create_foreign_key(
        "ged_documents_deleted_by_id_fkey",
        "ged_documents",
        "users",
        ["deleted_by_id"],
        ["id"],
    )
    op.create_index("ix_ged_documents_doc_type", "ged_documents", ["doc_type"])
    op.create_index("ix_ged_documents_reference", "ged_documents", ["reference"])
    op.create_index("ix_ged_documents_archived_at", "ged_documents", ["archived_at"])
    op.create_index("ix_ged_documents_agence_id", "ged_documents", ["agence_id"])
    op.create_index("ix_ged_documents_department_id", "ged_documents", ["department_id"])
    op.create_index("ix_ged_documents_fournisseur_id", "ged_documents", ["fournisseur_id"])
    op.create_index(
        "ix_ged_documents_parent_document_id", "ged_documents", ["parent_document_id"]
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ged_documents_filename_trgm "
        "ON ged_documents USING gin (filename gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ged_documents_title_trgm "
        "ON ged_documents USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ged_documents_reference_trgm "
        "ON ged_documents USING gin (reference gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ged_documents_reference_trgm")
    op.execute("DROP INDEX IF EXISTS ix_ged_documents_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_ged_documents_filename_trgm")
    for name in (
        "ix_ged_documents_parent_document_id",
        "ix_ged_documents_fournisseur_id",
        "ix_ged_documents_department_id",
        "ix_ged_documents_agence_id",
        "ix_ged_documents_archived_at",
        "ix_ged_documents_reference",
        "ix_ged_documents_doc_type",
    ):
        op.drop_index(name, table_name="ged_documents")
    for name in (
        "ged_documents_deleted_by_id_fkey",
        "ged_documents_parent_document_id_fkey",
        "ged_documents_fournisseur_id_fkey",
        "ged_documents_department_id_fkey",
        "ged_documents_agence_id_fkey",
    ):
        op.drop_constraint(name, "ged_documents", type_="foreignkey")
    for col in (
        "delete_reason",
        "deleted_by_id",
        "parent_document_id",
        "version",
        "fournisseur_id",
        "department_id",
        "agence_id",
        "archived_at",
        "date_document",
        "reference",
        "doc_type",
        "description",
        "title",
    ):
        op.drop_column("ged_documents", col)
