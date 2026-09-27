"""Quantité accordée saisie par le destinataire.

Revision ID: 20260927_qty_granted
Revises: 20260927_request_engine
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_qty_granted"
down_revision: Union[str, None] = "20260927_request_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mg_employee_request_items",
        sa.Column("quantity_granted", sa.Numeric(18, 3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mg_employee_request_items", "quantity_granted")
