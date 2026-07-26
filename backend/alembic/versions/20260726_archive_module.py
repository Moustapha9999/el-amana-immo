"""Module Archivage — dossiers / fichiers / lignes historiques.

Revision ID: 20260726_archive
Revises: 20260725_protocole
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260726_archive"
down_revision: Union[str, None] = "20260725_protocole"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archive_dossiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("libelle", sa.String(length=255), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.UniqueConstraint("annee", name="uq_archive_dossiers_annee"),
    )
    op.create_index("ix_archive_dossiers_annee", "archive_dossiers", ["annee"])

    op.create_table(
        "archive_fichiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dossier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nature_code", sa.String(length=40), nullable=True),
        sa.Column("sheet_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parse_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("lines_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dossier_id"], ["archive_dossiers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
    )
    op.create_index("ix_archive_fichiers_dossier_id", "archive_fichiers", ["dossier_id"])
    op.create_index("ix_archive_fichiers_kind", "archive_fichiers", ["kind"])
    op.create_index("ix_archive_fichiers_nature_code", "archive_fichiers", ["nature_code"])
    op.create_index("ix_archive_fichiers_parse_status", "archive_fichiers", ["parse_status"])

    op.create_table(
        "archive_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fichier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("categorie_code", sa.String(length=40), nullable=False),
        sa.Column("feuille", sa.String(length=120), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date_acquisition", sa.Date(), nullable=True),
        sa.Column("quantite", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("designation", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("valeur_brute", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("taux", sa.Numeric(10, 4), nullable=True),
        sa.Column("amt_n1", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("dotation", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("amt_fin", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vnc", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("agence_label", sa.String(length=120), nullable=True),
        sa.Column("is_report", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_kind", sa.String(length=32), nullable=False, server_default="excel_banque"),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fichier_id"], ["archive_fichiers.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_archive_lignes_fichier_id", "archive_lignes", ["fichier_id"])
    op.create_index("ix_archive_lignes_categorie_code", "archive_lignes", ["categorie_code"])
    op.create_index("ix_archive_lignes_date_acquisition", "archive_lignes", ["date_acquisition"])


def downgrade() -> None:
    op.drop_index("ix_archive_lignes_date_acquisition", table_name="archive_lignes")
    op.drop_index("ix_archive_lignes_categorie_code", table_name="archive_lignes")
    op.drop_index("ix_archive_lignes_fichier_id", table_name="archive_lignes")
    op.drop_table("archive_lignes")
    op.drop_index("ix_archive_fichiers_parse_status", table_name="archive_fichiers")
    op.drop_index("ix_archive_fichiers_nature_code", table_name="archive_fichiers")
    op.drop_index("ix_archive_fichiers_kind", table_name="archive_fichiers")
    op.drop_index("ix_archive_fichiers_dossier_id", table_name="archive_fichiers")
    op.drop_table("archive_fichiers")
    op.drop_index("ix_archive_dossiers_annee", table_name="archive_dossiers")
    op.drop_table("archive_dossiers")
