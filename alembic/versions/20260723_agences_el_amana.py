"""Agences Banque El Amana — colonnes bancaires

Revision ID: 20260723_agences
Revises: 20260723_etape2
Create Date: 2026-07-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_agences"
down_revision: Union[str, None] = "20260723_etape2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agences", sa.Column("code_banque", sa.String(length=10), nullable=True))
    op.add_column("agences", sa.Column("banque_sigle", sa.String(length=20), nullable=True))
    op.add_column("agences", sa.Column("banque_raison_sociale", sa.String(length=255), nullable=True))
    op.add_column("agences", sa.Column("code_swift", sa.String(length=20), nullable=True))
    op.create_index("ix_agences_code_banque", "agences", ["code_banque"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agences_code_banque", table_name="agences")
    op.drop_column("agences", "code_swift")
    op.drop_column("agences", "banque_raison_sociale")
    op.drop_column("agences", "banque_sigle")
    op.drop_column("agences", "code_banque")
