"""Verrouillage unique des soldes Orion (saisie une seule fois).

Revision ID: 20260914_orion_lock
Revises: 20260914_soldes_orion
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_orion_lock"
down_revision: Union[str, None] = "20260914_soldes_orion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "soldes_compte_orion",
        sa.Column("verrouille_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("soldes_compte_orion", "verrouille_at")
