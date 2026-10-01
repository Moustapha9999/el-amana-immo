"""Bons de commande MG — détail du moyen de paiement (RIB / n° Amanty, montant espèces).

Revision ID: 20260930_mg_bc_detail_paiement
Revises: 20260930_mg_notes_paiements
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260930_mg_bc_detail_paiement"
down_revision: Union[str, None] = "20260930_mg_notes_paiements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("mg_bons_commande")}
    if "ref_paiement" not in cols:
        op.add_column("mg_bons_commande", sa.Column("ref_paiement", sa.String(255), nullable=True))
    if "montant_paiement" not in cols:
        op.add_column(
            "mg_bons_commande", sa.Column("montant_paiement", sa.Numeric(18, 2), nullable=True)
        )


def downgrade() -> None:
    op.execute("ALTER TABLE mg_bons_commande DROP COLUMN IF EXISTS montant_paiement")
    op.execute("ALTER TABLE mg_bons_commande DROP COLUMN IF EXISTS ref_paiement")
