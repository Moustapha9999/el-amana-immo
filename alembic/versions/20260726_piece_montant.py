"""Pièces comptables — montant optionnel.

Revision ID: 20260726_piece_montant
Revises: 20260726_archive
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_piece_montant"
down_revision: Union[str, None] = "20260726_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pieces_jointes",
        sa.Column("montant", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pieces_jointes", "montant")
