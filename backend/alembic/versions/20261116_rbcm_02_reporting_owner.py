"""Reporting BCM SM — responsable du reporting + historique append-only.

Additif. Ne pas appliquer en production v1.0.0.

Backfill sûr : reporting_owner_id = preparer_id pour les SM existantes
(DEV 11/2026 conservée, aucune suppression).

Revision ID: 20261116_rbcm_02
Revises: 20261116_rbcm_01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261116_rbcm_02"
down_revision: Union[str, None] = "20261116_rbcm_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"


def upgrade() -> None:
    op.add_column(
        "rbcm_campaign",
        sa.Column(
            "reporting_owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "rbcm_campaign",
        sa.Column("reporting_owner_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_rbcm_campaign_reporting_owner_id",
        "rbcm_campaign",
        ["reporting_owner_id"],
    )

    op.create_table(
        "rbcm_reporting_owner_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "from_owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("motif", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_rbcm_reporting_owner_history_campaign_id",
        "rbcm_reporting_owner_history",
        ["campaign_id"],
    )

    op.execute(
        sa.text(
            """
            UPDATE rbcm_campaign
            SET reporting_owner_id = preparer_id,
                reporting_owner_set_at = COALESCE(reporting_owner_set_at, created_at)
            WHERE reporting_owner_id IS NULL
              AND preparer_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO rbcm_reporting_owner_history (
                id, campaign_id, from_owner_id, to_owner_id, actor_id, motif, created_at
            )
            SELECT gen_random_uuid(),
                   c.id,
                   NULL,
                   c.reporting_owner_id,
                   c.preparer_id,
                   'Désignation initiale (migration T3.5-1)',
                   c.created_at
            FROM rbcm_campaign c
            WHERE c.reporting_owner_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM rbcm_reporting_owner_history h
                  WHERE h.campaign_id = c.id
              )
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rbcm_reporting_owner_history_campaign_id",
        table_name="rbcm_reporting_owner_history",
    )
    op.drop_table("rbcm_reporting_owner_history")
    op.drop_index("ix_rbcm_campaign_reporting_owner_id", table_name="rbcm_campaign")
    op.drop_column("rbcm_campaign", "reporting_owner_set_at")
    op.drop_column("rbcm_campaign", "reporting_owner_id")
