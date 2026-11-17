"""Reporting BCM SM — référentiel documentaire (template, cellules, décisions).

Additif après rbcm_04. Ne pas appliquer en production v1.0.0.
Aucune suppression de données métier. excel_export GENERATED préservé.

Revision ID: 20261116_rbcm_05
Revises: 20261116_rbcm_04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261116_rbcm_05"
down_revision: Union[str, None] = "20261116_rbcm_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"

_NATURES = (
    "HEADER",
    "SEPARATOR",
    "CANVAS_NORM",
    "CANVAS_SCALE_FORMULA",
    "OCTOBER_LEAF",
    "OCTOBER_CONSTANT_FORMULA",
    "LEAF",
    "STRUCTURAL_FORMULA",
    "D09_PCT",
    "D09_REMAINDER",
    "CONCORDANCE_IF",
    "METIER_IF",
    "RATIO_DIV",
)
_NATURE_SQL = ", ".join(f"'{n}'" for n in _NATURES)
_DEC_TYPES = "('ZERO_CONFIRME','ZERO_MANUEL','VALEUR_DECIDEE','RETRAIT')"


def upgrade() -> None:
    op.create_table(
        "rbcm_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_code", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="CURRENT"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("extra", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint("version >= 1", name="ck_rbcm_template_version"),
        sa.CheckConstraint("status IN ('CURRENT','SUPERSEDED','ARCHIVED')", name="ck_rbcm_template_status"),
        sa.UniqueConstraint("sha256", name="uq_rbcm_template_sha256"),
        sa.UniqueConstraint("template_code", "version", name="uq_rbcm_template_code_version"),
    )
    op.create_index(
        "uq_rbcm_template_current",
        "rbcm_template",
        ["template_code"],
        unique=True,
        postgresql_where=sa.text("status = 'CURRENT'"),
    )

    op.create_table(
        "rbcm_template_cell",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_template.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sheet_name", sa.String(64), nullable=False),
        sa.Column("excel_address", sa.String(8), nullable=False),
        sa.Column("document_cell_key", sa.String(32), nullable=False),
        sa.Column("bcm_code", sa.String(16), nullable=True),
        sa.Column("axis", sa.String(4), nullable=True),
        sa.Column("nature", sa.String(32), nullable=False),
        sa.Column("formula_text", sa.Text(), nullable=True),
        sa.Column("writable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("completeness_group", sa.String(32), nullable=True),
        sa.Column("extra", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint(f"nature IN ({_NATURE_SQL})", name="ck_rbcm_template_cell_nature"),
        sa.UniqueConstraint("template_id", "sheet_name", "excel_address", name="uq_rbcm_template_cell_addr"),
        sa.UniqueConstraint("template_id", "document_cell_key", name="uq_rbcm_template_cell_key"),
    )
    op.create_index("ix_rbcm_template_cell_template_id", "rbcm_template_cell", ["template_id"])
    op.create_index("ix_rbcm_template_cell_key", "rbcm_template_cell", ["document_cell_key"])

    op.create_foreign_key(
        "fk_rbcm_campaign_template",
        "rbcm_campaign",
        "rbcm_template",
        ["template_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "rbcm_deliverable",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "rbcm_deliverable",
        sa.Column("document_seq", sa.Integer(), nullable=True),
    )
    op.add_column(
        "rbcm_deliverable",
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_rbcm_deliverable_template",
        "rbcm_deliverable",
        "rbcm_template",
        ["template_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_rbcm_deliverable_superseded_by",
        "rbcm_deliverable",
        "rbcm_deliverable",
        ["superseded_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_rbcm_deliverable_status_seq",
        "rbcm_deliverable",
        """
        (status = 'GENERATED' AND document_seq IS NULL AND template_id IS NULL)
        OR (status IN ('WORK', 'SUPERSEDED')
            AND document_seq IS NOT NULL AND document_seq >= 1
            AND template_id IS NOT NULL)
        """,
    )
    op.create_index(
        "uq_rbcm_deliverable_campaign_seq",
        "rbcm_deliverable",
        ["campaign_id", "document_seq"],
        unique=True,
        postgresql_where=sa.text("document_seq IS NOT NULL"),
    )
    op.create_index(
        "uq_rbcm_deliverable_one_work",
        "rbcm_deliverable",
        ["campaign_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'EXCEL' AND status = 'WORK'"),
    )

    op.create_table(
        "rbcm_document_decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "template_cell_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_template_cell.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("document_cell_key", sa.String(32), nullable=False),
        sa.Column(
            "deliverable_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_deliverable.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "calculation_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_calculation_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("calculated_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("decided_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("decision_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("justificatif_ref", sa.Text(), nullable=True),
        sa.Column(
            "decided_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "supersedes_decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_document_decision.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.CheckConstraint(f"decision_type IN {_DEC_TYPES}", name="ck_rbcm_document_decision_type"),
    )
    op.create_index("ix_rbcm_document_decision_campaign_id", "rbcm_document_decision", ["campaign_id"])
    op.create_index(
        "ix_rbcm_document_decision_current",
        "rbcm_document_decision",
        ["campaign_id", "document_cell_key", "decided_at"],
    )
    op.create_index("ix_rbcm_document_decision_supersedes", "rbcm_document_decision", ["supersedes_decision_id"])


def downgrade() -> None:
    op.drop_index("ix_rbcm_document_decision_supersedes", table_name="rbcm_document_decision")
    op.drop_index("ix_rbcm_document_decision_current", table_name="rbcm_document_decision")
    op.drop_index("ix_rbcm_document_decision_campaign_id", table_name="rbcm_document_decision")
    op.drop_table("rbcm_document_decision")
    op.drop_index("uq_rbcm_deliverable_one_work", table_name="rbcm_deliverable")
    op.drop_index("uq_rbcm_deliverable_campaign_seq", table_name="rbcm_deliverable")
    op.drop_constraint("ck_rbcm_deliverable_status_seq", "rbcm_deliverable", type_="check")
    op.drop_constraint("fk_rbcm_deliverable_superseded_by", "rbcm_deliverable", type_="foreignkey")
    op.drop_constraint("fk_rbcm_deliverable_template", "rbcm_deliverable", type_="foreignkey")
    op.drop_column("rbcm_deliverable", "superseded_by_id")
    op.drop_column("rbcm_deliverable", "document_seq")
    op.drop_column("rbcm_deliverable", "template_id")
    op.drop_constraint("fk_rbcm_campaign_template", "rbcm_campaign", type_="foreignkey")
    op.drop_index("ix_rbcm_template_cell_key", table_name="rbcm_template_cell")
    op.drop_index("ix_rbcm_template_cell_template_id", table_name="rbcm_template_cell")
    op.drop_table("rbcm_template_cell")
    op.drop_index("uq_rbcm_template_current", table_name="rbcm_template")
    op.drop_table("rbcm_template")
