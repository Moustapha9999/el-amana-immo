"""Reporting BCM SM — orientations NCG vers cellules catalogue.

Additif après rbcm_05. Table append-only logique (pas de drop métier).

Revision ID: 20261118_rbcm_06
Revises: 20261116_rbcm_05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261118_rbcm_06"
down_revision: Union[str, None] = "20261116_rbcm_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STAT = (
    "'A_ORIENTER','EN_ATTENTE_VALIDATION','VALIDE_ACTIF','REJETE','DESACTIVE'"
)
_OPS = "'ADD_DEBIT','ADD_CREDIT','SUB_DEBIT','SUB_CREDIT'"
_CUR = "'ALL','LOCAL','FX'"
_RES = "'RESIDENTS','NON_RESIDENTS','ALL'"
_SHEET = "'ETAT_A','ETAT_B'"


def upgrade() -> None:
    op.create_table(
        "rbcm_ncg_orientation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ncg", sa.String(32), nullable=False),
        sa.Column("ncg_libelle", sa.String(255), nullable=True),
        sa.Column("sheet", sa.String(16), nullable=False),
        sa.Column("cell_ref", sa.String(32), nullable=True),
        sa.Column("currency_scope", sa.String(16), nullable=False, server_default="ALL"),
        sa.Column("residence_scope", sa.String(16), nullable=False, server_default="RESIDENTS"),
        sa.Column("operation", sa.String(16), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="A_ORIENTER"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("prepared_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_ncg_orientation.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"status IN ({_STAT})", name="ck_rbcm_ncg_orientation_status"),
        sa.CheckConstraint(f"operation IS NULL OR operation IN ({_OPS})", name="ck_rbcm_ncg_orientation_operation"),
        sa.CheckConstraint(f"currency_scope IN ({_CUR})", name="ck_rbcm_ncg_orientation_currency"),
        sa.CheckConstraint(f"residence_scope IN ({_RES})", name="ck_rbcm_ncg_orientation_residence"),
        sa.CheckConstraint(f"sheet IN ({_SHEET})", name="ck_rbcm_ncg_orientation_sheet"),
    )
    op.create_index("ix_rbcm_ncg_orientation_ncg", "rbcm_ncg_orientation", ["ncg"])
    op.create_index("ix_rbcm_ncg_orientation_cell_ref", "rbcm_ncg_orientation", ["cell_ref"])
    op.create_index("ix_rbcm_ncg_orientation_status", "rbcm_ncg_orientation", ["status"])
    op.create_index(
        "ix_rbcm_ncg_orientation_active_key",
        "rbcm_ncg_orientation",
        ["ncg", "cell_ref", "operation", "currency_scope"],
    )


def downgrade() -> None:
    op.drop_table("rbcm_ncg_orientation")
