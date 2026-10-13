"""Classement de masse SCORE : suivi des tâches côté serveur (progression, reprise). Additif.

Revision ID: 20261013_clientele_10
Revises: 20261012_clientele_09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261013_clientele_10"
down_revision: Union[str, None] = "20261012_clientele_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_T = "clientele_classif_taches"


def upgrade() -> None:
    op.create_table(
        _T,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("statut", sa.String(16), nullable=False, server_default="EN_ATTENTE"),
        sa.Column("profil", sa.String(16), nullable=True),
        sa.Column("code_agence", sa.String(16), nullable=True),
        sa.Column("motif", sa.Text(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("traites", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bilan", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("erreurs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("curseur", sa.String(6), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("debut", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("maj_le", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "statut IN ('EN_ATTENTE','EN_COURS','TERMINE','TERMINE_ERREURS','INTERROMPU','ECHEC')",
            name="ck_clientele_classif_taches_statut"),
    )
    op.create_index("ix_clientele_classif_taches_statut", _T, ["statut", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_clientele_classif_taches_statut", table_name=_T)
    op.drop_table(_T)
