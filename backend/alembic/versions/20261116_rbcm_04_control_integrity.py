"""Reporting BCM SM — résultat FAILED + unicité (run_id, item_key).

Additif. Ne pas appliquer en production v1.0.0.
Aucune suppression de données métier.

Revision ID: 20261116_rbcm_04
Revises: 20261116_rbcm_03
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261116_rbcm_04"
down_revision: Union[str, None] = "20261116_rbcm_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"


def upgrade() -> None:
    op.drop_constraint("ck_rbcm_control_run_result", "rbcm_control_run", type_="check")
    op.create_check_constraint(
        "ck_rbcm_control_run_result",
        "rbcm_control_run",
        "result IN ('OK','WARNINGS','INCOMPLETE','DECISIONS_PENDING','BLOCKING','FAILED')",
    )
    op.create_index(
        "uq_rbcm_reconcile_issue_run_item",
        "rbcm_reconcile_issue",
        ["run_id", "item_key"],
        unique=True,
        postgresql_where="run_id IS NOT NULL AND item_key IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_rbcm_reconcile_issue_run_item", table_name="rbcm_reconcile_issue")
    op.drop_constraint("ck_rbcm_control_run_result", "rbcm_control_run", type_="check")
    op.create_check_constraint(
        "ck_rbcm_control_run_result",
        "rbcm_control_run",
        "result IN ('OK','WARNINGS','INCOMPLETE','DECISIONS_PENDING','BLOCKING')",
    )
