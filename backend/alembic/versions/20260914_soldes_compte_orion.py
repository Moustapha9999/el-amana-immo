"""Soldes Orion agrégés — natures non amortissables (140000 / 142000 / 145300).

Revision ID: 20260914_soldes_orion
Revises: 20260730_periodes_categories
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914_soldes_orion"
down_revision: Union[str, None] = "20260730_periodes_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "soldes_compte_orion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("compte_immobilisation", sa.String(length=20), nullable=False),
        sa.Column("valeur_brute", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="orion"),
        sa.Column("libelle", sa.String(length=120), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.UniqueConstraint("annee", "compte_immobilisation", name="uq_solde_compte_orion_annee_compte"),
    )
    op.create_index("ix_soldes_compte_orion_annee", "soldes_compte_orion", ["annee"])
    op.create_index(
        "ix_soldes_compte_orion_compte_immobilisation",
        "soldes_compte_orion",
        ["compte_immobilisation"],
    )


def downgrade() -> None:
    op.drop_index("ix_soldes_compte_orion_compte_immobilisation", table_name="soldes_compte_orion")
    op.drop_index("ix_soldes_compte_orion_annee", table_name="soldes_compte_orion")
    op.drop_table("soldes_compte_orion")
