"""Reporting BCM SM — exécutions de contrôles append-only (T3.5-2).

Additif. Ne pas appliquer en production v1.0.0.

- Table ``rbcm_control_run`` (run_id).
- Colonnes de classification sur ``rbcm_reconcile_issue``.
- ``justificatif_ref`` sur les paramètres.
- Backfill des anomalies existantes (aucune suppression).

Revision ID: 20261116_rbcm_03
Revises: 20261116_rbcm_02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261116_rbcm_03"
down_revision: Union[str, None] = "20261116_rbcm_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"


def upgrade() -> None:
    op.create_table(
        "rbcm_control_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("result", sa.String(24), nullable=False, server_default="OK"),
        sa.Column(
            "previous_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_control_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "result IN ('OK','WARNINGS','INCOMPLETE','DECISIONS_PENDING','BLOCKING')",
            name="ck_rbcm_control_run_result",
        ),
    )
    op.create_index("ix_rbcm_control_run_campaign_id", "rbcm_control_run", ["campaign_id"])

    op.add_column(
        "rbcm_reconcile_issue",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rbcm_control_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("rbcm_reconcile_issue", sa.Column("category", sa.String(1), nullable=True))
    op.add_column("rbcm_reconcile_issue", sa.Column("item_key", sa.String(80), nullable=True))
    op.add_column("rbcm_reconcile_issue", sa.Column("title", sa.String(200), nullable=True))
    op.add_column(
        "rbcm_reconcile_issue",
        sa.Column("resolution_state", sa.String(24), nullable=False, server_default="OPEN"),
    )
    op.create_index("ix_rbcm_reconcile_issue_run_id", "rbcm_reconcile_issue", ["run_id"])
    op.create_index("ix_rbcm_reconcile_issue_category", "rbcm_reconcile_issue", ["category"])
    op.create_index("ix_rbcm_reconcile_issue_item_key", "rbcm_reconcile_issue", ["item_key"])
    op.create_check_constraint(
        "ck_rbcm_reconcile_issue_category",
        "rbcm_reconcile_issue",
        "category IS NULL OR category IN ('A','B','C','D')",
    )
    op.create_check_constraint(
        "ck_rbcm_reconcile_issue_resolution",
        "rbcm_reconcile_issue",
        "resolution_state IN ('OPEN','IN_PROGRESS','RESOLVED','STILL_BLOCKING','PENDING_DECISION','OK')",
    )

    op.add_column(
        "rbcm_parameter_value",
        sa.Column("justificatif_ref", sa.String(255), nullable=True),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO rbcm_control_run (id, campaign_id, actor_id, result, previous_run_id, summary, created_at)
            SELECT gen_random_uuid(),
                   i.campaign_id,
                   NULL,
                   'OK',
                   NULL,
                   jsonb_build_object('backfill', true, 'origin', 'T3.5-2'),
                   MIN(i.created_at)
            FROM rbcm_reconcile_issue i
            WHERE i.run_id IS NULL
            GROUP BY i.campaign_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE rbcm_reconcile_issue i
            SET run_id = r.id,
                category = COALESCE(i.category, 'A'),
                item_key = COALESCE(i.item_key, 'LEGACY:' || i.code),
                title = COALESCE(i.title, i.message),
                resolution_state = CASE WHEN i.resolved THEN 'RESOLVED' ELSE 'OK' END
            FROM rbcm_control_run r
            WHERE i.campaign_id = r.campaign_id
              AND i.run_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("rbcm_parameter_value", "justificatif_ref")
    op.drop_constraint("ck_rbcm_reconcile_issue_resolution", "rbcm_reconcile_issue", type_="check")
    op.drop_constraint("ck_rbcm_reconcile_issue_category", "rbcm_reconcile_issue", type_="check")
    op.drop_index("ix_rbcm_reconcile_issue_item_key", table_name="rbcm_reconcile_issue")
    op.drop_index("ix_rbcm_reconcile_issue_category", table_name="rbcm_reconcile_issue")
    op.drop_index("ix_rbcm_reconcile_issue_run_id", table_name="rbcm_reconcile_issue")
    op.drop_column("rbcm_reconcile_issue", "resolution_state")
    op.drop_column("rbcm_reconcile_issue", "title")
    op.drop_column("rbcm_reconcile_issue", "item_key")
    op.drop_column("rbcm_reconcile_issue", "category")
    op.drop_column("rbcm_reconcile_issue", "run_id")
    op.drop_index("ix_rbcm_control_run_campaign_id", table_name="rbcm_control_run")
    op.drop_table("rbcm_control_run")
