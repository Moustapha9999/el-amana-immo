"""Cession — colonnes référence / observations (note banque).

Revision ID: 20260724_cession
Revises: 20260723_agences
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_cession"
down_revision: Union[str, None] = "20260723_agences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cessions", sa.Column("reference", sa.String(length=80), nullable=True))
    op.add_column("cessions", sa.Column("observations", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("cessions", "observations")
    op.drop_column("cessions", "reference")
