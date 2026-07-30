"""Ajout type pièce protocole_accord.

Revision ID: 20260725_protocole
Revises: 20260725_pieces
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260725_protocole"
down_revision: Union[str, None] = "20260725_pieces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE typepiececomptable ADD VALUE IF NOT EXISTS 'protocole_accord'")


def downgrade() -> None:
    # PostgreSQL ne permet pas de retirer proprement une valeur d'enum.
    pass
