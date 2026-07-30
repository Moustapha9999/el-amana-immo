"""Étape 2 — date de dernière comptabilisation amortissement.

Revision ID: 20260723_etape2
Revises: 20260723_etape1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_etape2"
down_revision: Union[str, None] = "20260723_etape1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("immobilisations", sa.Column("date_comptabilisation", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("immobilisations", "date_comptabilisation")
