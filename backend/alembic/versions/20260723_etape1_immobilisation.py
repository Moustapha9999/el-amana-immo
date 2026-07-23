"""Fiche immobilisation §5.1 — champs et statuts §6.

Revision ID: 20260723_etape1
Revises: 20260723_el_amana
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_etape1"
down_revision: Union[str, None] = "20260723_el_amana"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_STATUT_VALUES = (
    "BROUILLON",
    "EN_COURS_ACQUISITION",
    "SUSPENDUE",
    "CEDEE",
    "MISE_AU_REBUT",
    "TRANSFEREE",
    "RECLASSEE",
    "ARCHIVEE",
)


def upgrade() -> None:
    for value in NEW_STATUT_VALUES:
        op.execute(
            sa.text(
                "DO $$ BEGIN "
                f"ALTER TYPE statutimmobilisation ADD VALUE IF NOT EXISTS '{value}'; "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
        )

    op.add_column("immobilisations", sa.Column("numero_facture", sa.String(length=80), nullable=True))
    op.add_column("immobilisations", sa.Column("quantite", sa.Integer(), server_default="1", nullable=False))
    op.add_column("immobilisations", sa.Column("observations", sa.Text(), nullable=True))
    op.add_column("immobilisations", sa.Column("duree_annees", sa.Integer(), nullable=True))
    op.add_column(
        "immobilisations",
        sa.Column("periodicite", sa.String(length=20), server_default="annuel", nullable=False),
    )
    op.add_column(
        "immobilisations",
        sa.Column("prorata_temporis", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("immobilisations", "prorata_temporis")
    op.drop_column("immobilisations", "periodicite")
    op.drop_column("immobilisations", "duree_annees")
    op.drop_column("immobilisations", "observations")
    op.drop_column("immobilisations", "quantite")
    op.drop_column("immobilisations", "numero_facture")
