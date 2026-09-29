"""Contrats MG — référence de paiement (compte virement, numéro Amanty).

Revision ID: 20260929_contrats_ref_paiement
Revises: 20260927_qty_granted
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260929_contrats_ref_paiement"
down_revision: Union[str, None] = "20260927_qty_granted"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("mg_contrats")}
    if "ref_paiement" not in cols:
        op.add_column("mg_contrats", sa.Column("ref_paiement", sa.String(120), nullable=True))


def downgrade() -> None:
    op.execute("ALTER TABLE mg_contrats DROP COLUMN IF EXISTS ref_paiement")
